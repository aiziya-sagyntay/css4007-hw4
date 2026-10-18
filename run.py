"""HW4 B4: reproducible S1 direct, S2 think-and-vote, S3 tools experiments.

Run from Colab (after cloning the fork):

    from run import run_experiment
    run_experiment(client, run_label='pilot', question_ids=['Q-01', 'Q-09'])
    run_experiment(client, run_label='run_1')
    run_experiment(client, run_label='run_2')

Files are saved immediately under outputs/<run_label>/, allowing resumption.
Never put an API key into this file or any saved JSON.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import time
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from strategies import MODEL, MAX_ROUNDS, run_tools

ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
K = 5
REASONING_EFFORT = "none"  # The same across S1, S2, and S3 on Chat Completions.
# No temperature override for ANY strategy: use the model's API default throughout.
TEMPERATURE_SETTING = "API default (not set)"
# Published GPT-5.6 Luna standard API rates as of October 2026, USD per million tokens.
# Conservative estimates below bill all input tokens at the uncached price.
INPUT_USD_PER_M = 0.20
OUTPUT_USD_PER_M = 1.20

ANSWER_RE = re.compile(
    r"(?im)^\s*ANSWER:\s*([^|\n]+?)\s*\|\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*$"
)


def load_questions():
    return json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))


def load_corpus():
    """Put full documents in S1/S2 prompts without leaking answer keys."""
    lines = (ROOT / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
    docs = [json.loads(line) for line in lines if line.strip()]
    return "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in docs)


def parse_answer(text):
    """Return (label, Decimal), or None for missing/UNANSWERED final line."""
    matches = list(ANSWER_RE.finditer(text or ""))
    if not matches:
        return None
    last = matches[-1]
    label = last.group(1).strip()
    if not label or label.upper() == "UNANSWERED":
        return None
    try:
        value = Decimal(last.group(2))
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return label, value


def formatted_answer(parsed, decimals):
    if parsed is None:
        return "ANSWER: UNANSWERED | NA"
    label, value = parsed
    quantum = Decimal(1).scaleb(-decimals)
    return f"ANSWER: {label} | {value.quantize(quantum, rounding=ROUND_HALF_UP)}"


def is_correct(text, gold):
    """Rule fixed BEFORE first full run: exact label + ±1 in final decimal place."""
    parsed = parse_answer(text)
    if parsed is None:
        return False
    label, value = parsed
    if label != gold["answer"]:
        return False
    places = int(gold["decimals"])
    quantum = Decimal(1).scaleb(-places)
    predicted = value.quantize(quantum, rounding=ROUND_HALF_UP)
    expected = Decimal(str(gold["value"])).quantize(quantum, rounding=ROUND_HALF_UP)
    return abs(predicted - expected) <= quantum


def price_estimate(input_tokens, output_tokens):
    """USD estimate without any caching discounts (so not exact provider invoice)."""
    return round((input_tokens * INPUT_USD_PER_M +
                  output_tokens * OUTPUT_USD_PER_M) / 1_000_000, 8)


def usage_counts(response):
    usage = response.usage
    if usage is None:
        raise RuntimeError("API usage was missing; cannot report correct token totals")
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return int(usage.prompt_tokens), int(usage.completion_tokens), int(cached)


def common_instructions(decimals):
    return (
        "Answer the fictional Nine Rivers Region question using the provided context. "
        "Use the correct 2025 documents unless the question says otherwise. "
        "Ignore archived profiles as current data, apply later correction notices, "
        "and convert units when necessary. Do not invent missing facts. "
        "Give the result, ending with exactly one final line in this format: "
        "ANSWER: <district or yes/no> | <number>. "
        "If reliable facts are missing, use ANSWER: UNANSWERED | NA. "
        f"Round the requested result to {decimals} decimal places, only at the end."
    )


def call_plain(client, question, corpus, *, reflect=False):
    instructions = common_instructions(question["decimals"])
    if reflect:
        instructions += (
            " Before answering, work through the relevant numerical comparisons "
            "and verify units and corrections. You may give a brief calculation "
            "explanation, but finish with the exact ANSWER line."
        )
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": "DOCUMENTS:\n" + corpus + "\n\nQUESTION:\n" + question["question"]},
    ]
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=MODEL, messages=messages, reasoning_effort=REASONING_EFFORT
    )
    seconds = time.perf_counter() - started
    in_tok, out_tok, cached = usage_counts(response)
    text = response.choices[0].message.content or ""
    return {
        "text": text,
        "parsed_final_answer": formatted_answer(parse_answer(text), question["decimals"]),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cached_input_tokens": cached,
        "seconds": round(seconds, 4),
        "finish_reason": response.choices[0].finish_reason,
    }


def run_s1(client, question, corpus):
    item = call_plain(client, question, corpus)
    return {
        "question_id": question["id"], "strategy": "S1", "model": MODEL,
        "answer": item["parsed_final_answer"], "raw_answer": item["text"],
        "samples": [item], "input_tokens": item["input_tokens"],
        "output_tokens": item["output_tokens"],
        "cached_input_tokens": item["cached_input_tokens"],
        "seconds": item["seconds"],
        "unanswered": parse_answer(item["text"]) is None,
    }


def run_s2(client, question, corpus):
    started = time.perf_counter()
    samples = []
    # Five separate calls; the answer key is NEVER included in any prompt.
    for sample_number in range(1, K + 1):
        sample = call_plain(client, question, corpus, reflect=True)
        sample["sample_number"] = sample_number
        samples.append(sample)
    # Vote on the WHOLE label + rounded numeric answer, not only district name.
    votes = [sample["parsed_final_answer"] for sample in samples
             if parse_answer(sample["text"]) is not None]
    winner = Counter(votes).most_common(1)[0][0] if votes else "ANSWER: UNANSWERED | NA"
    # Counter preserves first-seen order to resolve ties deterministically.
    return {
        "question_id": question["id"], "strategy": "S2", "model": MODEL,
        "k": K, "vote_counts": dict(Counter(votes)),
        "answer": winner, "samples": samples,
        "input_tokens": sum(s["input_tokens"] for s in samples),
        "output_tokens": sum(s["output_tokens"] for s in samples),
        "cached_input_tokens": sum(s["cached_input_tokens"] for s in samples),
        "seconds": round(time.perf_counter() - started, 4),
        "unanswered": not votes,
    }


def run_s3(client, question, run_folder):
    # Use exactly the existing B3 implementation that was tested on Q-09.
    s3_folder = run_folder / "S3_logs"
    result = run_tools(
        client=client,
        question=question["question"],
        question_id=question["id"],
        decimals=question["decimals"],
        model=MODEL,
        max_rounds=MAX_ROUNDS,
        output_dir=str(s3_folder),
    )
    return {
        "question_id": question["id"], "strategy": "S3", "model": MODEL,
        "answer": result["answer"], "rounds": result["rounds"],
        "tool_calls": result["tool_calls"],
        "logfile": str(Path(result["logfile"]).relative_to(ROOT))
        if Path(result["logfile"]).is_relative_to(ROOT) else result["logfile"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cached_input_tokens": None,  # Existing B3 log does not track this.
        "seconds": result["seconds"],
        "unanswered": result["unanswered"],
    }


def _write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")


def write_reports(run_folder, questions):
    """Rebuild CSV/Markdown summaries from saved per-question outputs."""
    ids = [q["id"] for q in questions]
    records = {}
    for q in questions:
        records[q["id"]] = {}
        for strategy in ("S1", "S2", "S3"):
            file = run_folder / strategy / f"{q['id']}.json"
            if file.exists():
                records[q["id"]][strategy] = json.loads(file.read_text(encoding="utf-8"))

    # One record per question and strategy, with actual measurements.
    details = []
    for q in questions:
        for strategy, r in records[q["id"]].items():
            details.append({
                "question_id": q["id"], "strategy": strategy,
                "correct": int(r["correct"]),
                "unanswered": int(r["unanswered"]),
                "answer": r["answer"], "reference_answer": q["answer"],
                "reference_value": q["value"],
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "seconds": r["seconds"],
                "estimated_cost_usd": r["estimated_cost_usd"],
            })
    columns = list(details[0]) if details else [
        "question_id", "strategy", "correct", "unanswered", "answer",
        "reference_answer", "reference_value", "input_tokens", "output_tokens",
        "seconds", "estimated_cost_usd",
    ]
    with (run_folder / "per_question.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(details)

    summary = []
    for strategy in ("S1", "S2", "S3"):
        found = [records[qid][strategy] for qid in ids if strategy in records[qid]]
        if not found:
            continue
        summary.append({
            "run": run_folder.name,
            "strategy": strategy,
            "questions_finished": len(found),
            "correct": sum(r["correct"] for r in found),
            "unanswered": sum(r["unanswered"] for r in found),
            "input_tokens": sum(r["input_tokens"] for r in found),
            "output_tokens": sum(r["output_tokens"] for r in found),
            "median_seconds_per_question": round(statistics.median(r["seconds"] for r in found), 4),
            "total_seconds": round(sum(r["seconds"] for r in found), 4),
            "estimated_cost_usd": round(sum(r["estimated_cost_usd"] for r in found), 6),
        })
    _write_json(run_folder / "summary.json", summary)
    with (run_folder / "summary.csv").open("w", encoding="utf-8", newline="") as out:
        if summary:
            writer = csv.DictWriter(out, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)

    # Copyable Markdown tables for SUBMISSION.md.
    lines = [f"## {run_folder.name}", "",
             "| Run | Strategy | Correct | Unanswered | Input tokens | Output tokens | Median seconds/question | Total seconds | Estimated cost ($) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        lines.append(
            f"| {r['run']} | {r['strategy']} | {r['correct']}/{r['questions_finished']} | "
            f"{r['unanswered']} | {r['input_tokens']} | {r['output_tokens']} | "
            f"{r['median_seconds_per_question']:.2f} | {r['total_seconds']:.2f} | "
            f"{r['estimated_cost_usd']:.6f} |"
        )
    lines += ["", "| Question | S1 | S2 | S3 |", "|---|:---:|:---:|:---:|"]
    for qid in ids:
        marks = []
        for strategy in ("S1", "S2", "S3"):
            r = records[qid].get(strategy)
            marks.append("✓" if r and r["correct"] else "✗" if r else "—")
        lines.append(f"| {qid} | {' | '.join(marks)} |")
    lines += ["", "*Estimated cost uses standard uncached token prices ($0.20/M input, $1.20/M output).",
              "Actual billed cost may be lower due to prompt caching.*", ""]
    (run_folder / "tables.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def run_experiment(client, run_label, question_ids=None):
    """Run or resume a pilot / full replicate. No API call for completed cases.

    Usage:
        run_experiment(client, "pilot", ["Q-01", "Q-09"])
        run_experiment(client, "run_1")
        run_experiment(client, "run_2")
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_label):
        raise ValueError("run_label must contain only letters, digits, - or _")
    all_questions = load_questions()
    if question_ids is not None:
        allowed = {q["id"] for q in all_questions}
        if not question_ids or len(set(question_ids)) != len(question_ids) or not set(question_ids) <= allowed:
            raise ValueError("question_ids must be a nonempty list of unique valid IDs")
        selected = [q for q in all_questions if q["id"] in question_ids]
    else:
        selected = all_questions
    folder = OUTPUTS_DIR / run_label
    folder.mkdir(parents=True, exist_ok=True)
    # This file fixes the scoring rule and experimental settings before any run.
    settings_file = folder / "settings.json"
    settings = {
        "model": MODEL, "questions": [q["id"] for q in selected],
        "strategy": ["S1 direct", "S2 think+vote", "S3 tools"],
        "s2_samples": K, "max_tool_rounds": MAX_ROUNDS,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": TEMPERATURE_SETTING,
        "answer_format": "ANSWER: <name or yes/no> | <number>",
        "correctness_rule": "Exact label; rounded number within 1 last decimal place of reference value",
        "reference_answers_used_only_after_model_response": True,
        "estimated_cost_price_per_million_usd": {
            "uncached_input": INPUT_USD_PER_M, "output": OUTPUT_USD_PER_M,
        },
    }
    if settings_file.exists():
        previous = json.loads(settings_file.read_text(encoding="utf-8"))
        if previous != settings:
            raise RuntimeError("Existing run settings differ. Use a new run_label instead of mixing results.")
    else:
        _write_json(settings_file, settings)
    corpus = load_corpus()
    for idx, question in enumerate(selected, start=1):
        for strategy, worker in (
            ("S1", lambda: run_s1(client, question, corpus)),
            ("S2", lambda: run_s2(client, question, corpus)),
            ("S3", lambda: run_s3(client, question, folder)),
        ):
            file = folder / strategy / f"{question['id']}.json"
            if file.exists():
                print(f"[{run_label}] {idx}/{len(selected)} {question['id']} {strategy}: already saved, skipped")
                continue
            print(f"[{run_label}] {idx}/{len(selected)} {question['id']} {strategy}: running...", flush=True)
            # Network errors propagate. Saved cases are skipped when the user restarts.
            result = worker()
            result["correct"] = is_correct(result["answer"], question)
            result["estimated_cost_usd"] = price_estimate(result["input_tokens"], result["output_tokens"])
            _write_json(file, result)
            print(f"    {'CORRECT' if result['correct'] else 'WRONG/UNANSWERED'} | "
                  f"{result['input_tokens']} in / {result['output_tokens']} out | "
                  f"{result['seconds']:.2f}s | ${result['estimated_cost_usd']:.5f}")
            # Save a summary after EACH completed question-strategy pair.
            write_reports(folder, selected)
    summary = write_reports(folder, selected)
    print(f"\nDone: {run_label}. Summary: {folder / 'tables.md'}")
    for row in summary:
        print(f"  {row['strategy']}: {row['correct']}/{row['questions_finished']} correct; "
              f"estimated ${row['estimated_cost_usd']:.6f}")
    return summary


if __name__ == "__main__":
    print("Import run_experiment from your Colab notebook, where the API client uses Colab Secrets.")
