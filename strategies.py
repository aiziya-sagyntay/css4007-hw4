"""HW4 — Strategy S3: OpenAI Chat Completions tool-calling loop.

Runs using the caller's OpenAI client. Never stores or prints an API key.
Logs each question to outputs/ so the actual conversation can be compared to A3.
S1 and S2 will be added in B4.
"""

import json
import re
import time
from pathlib import Path

from tools import calculate, lookup

MODEL = "gpt-5.6-luna"
MAX_ROUNDS = 8

# These are the same tool definitions described in Part A of SUBMISSION.md.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": (
                "Retrieve one numerical fact from the Nine Rivers Region documents "
                "by exact district name, field, and year. Use 2025 profiles for "
                "current facts, never use archived profiles as current data, and "
                "apply later correction notices before returning values. Return "
                "the value, unit, and source document IDs. Use district 'region' "
                "for the regional water tariff. Return household water use in "
                "megalitres, converting cubic metres if necessary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "Exact district name or 'region' for water_tariff.",
                    },
                    "field": {
                        "type": "string",
                        "enum": [
                            "population", "area", "budget", "water_use", "schools",
                            "pupils", "paved_road", "founded", "water_tariff",
                        ],
                        "description": "The numerical field to find.",
                    },
                    "year": {
                        "type": "integer",
                        "enum": [2020, 2025],
                        "description": (
                            "2020 is available for census population; use 2025 "
                            "for current district figures, founding year, school "
                            "data for 2025/26, and the current water tariff."
                        ),
                    },
                },
                "required": ["district", "field", "year"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Safely evaluate a basic arithmetic expression. Use it for "
                "densities, growth percentages, per-person rates, unit "
                "conversions, projections and differences. Only numerical "
                "constants, parentheses, and the operators +, -, *, / are "
                "allowed. Do not send Python code or function calls."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "Arithmetic expression such as '44675 / 921.4', "
                            "with at most 120 characters. No powers, functions "
                            "or Python attributes."
                        ),
                    },
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
]


def _run_tool(name, raw_arguments):
    """Validate JSON and argument types BEFORE calling a local tool."""
    try:
        arguments = json.loads(raw_arguments)
    except (TypeError, ValueError):
        return {"error": "Invalid JSON arguments"}, None

    if not isinstance(arguments, dict):
        return {"error": "Invalid arguments"}, arguments

    if name == "lookup":
        if set(arguments) != {"district", "field", "year"}:
            return {"error": "Invalid arguments"}, arguments
        district, field, year = (arguments[k] for k in ("district", "field", "year"))
        if not isinstance(district, str) or not isinstance(field, str) or type(year) is not int:
            return {"error": "Invalid arguments"}, arguments
        return lookup(district, field, year), arguments

    if name == "calculate":
        if set(arguments) != {"expression"} or not isinstance(arguments["expression"], str):
            return {"error": "Invalid arguments"}, arguments
        return calculate(arguments["expression"]), arguments

    return {"error": "Unknown tool"}, arguments


def run_tools(client, question, question_id, decimals=None, *, model=MODEL,
              max_rounds=MAX_ROUNDS, output_dir="outputs"):
    """Run one question with tools, recording every API/tool turn as JSON.

    `client` is an existing OpenAI() client from Colab. Never pass an answer
    key, expected value or reference sources into this function.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a nonempty string")
    if not isinstance(question_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", question_id):
        raise ValueError("question_id must contain only letters, digits, _ or -")
    if type(max_rounds) is not int or max_rounds < 1:
        raise ValueError("max_rounds must be a positive integer")
    if decimals is not None and (type(decimals) is not int or not 0 <= decimals <= 8):
        raise ValueError("decimals must be between 0 and 8")

    instructions = (
        "Answer the fictional Nine Rivers Region question using ONLY the "
        "provided lookup and calculate tools. You do NOT have the documents. "
        "Look up every required factual value and use calculate for all "
        "arithmetic, including the final difference. Trust any correction "
        "notices applied by lookup. Do not invent values or use the 2019 "
        "archived profiles as current facts. If a tool fails, correct the "
        "request or report that you cannot answer. "
        "Finish with one line exactly like: ANSWER: <district or yes/no> | <number>. "
        "If the answer cannot be established, use ANSWER: UNANSWERED | NA."
    )
    if decimals is not None:
        instructions += f" Round only the final difference or requested quantity to {decimals} decimal places."

    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": question},
    ]
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    logfile = output_path / f"{question_id}_S3.json"

    tool_log = []
    api_log = []
    input_tokens = 0
    output_tokens = 0
    final_text = ""
    unanswered = True
    start_total = time.perf_counter()

    try:
        for round_num in range(1, max_rounds + 1):
            start_api = time.perf_counter()
            response = client.chat.completions.create(
                model=model, messages=messages, tools=TOOL_SCHEMAS,
                tool_choice="auto",
                reasoning_effort="none",
            )
            api_elapsed = time.perf_counter() - start_api
            usage = response.usage
            in_count = usage.prompt_tokens if usage else 0
            out_count = usage.completion_tokens if usage else 0
            input_tokens += in_count
            output_tokens += out_count
            message = response.choices[0].message

            api_log.append({
                "round": round_num,
                "duration_seconds": round(api_elapsed, 4),
                "input_tokens": in_count,
                "output_tokens": out_count,
                "finish_reason": response.choices[0].finish_reason,
            })

            # Append the model's message with tool_calls intact, before tool replies.
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                final_text = message.content or ""
                unanswered = not bool(re.search(
                    r"(?m)^ANSWER:\s*(?!UNANSWERED\b)[^|\n]+\|\s*[-+]?\d+(?:\.\d+)?\s*$",
                    final_text,
                ))
                break

            # Each tool_call_id receives exactly one answer, including invalid calls.
            for call in message.tool_calls:
                start_tool = time.perf_counter()
                name = call.function.name if call.function else ""
                raw_args = call.function.arguments if call.function else ""
                result, parsed_args = _run_tool(name, raw_args)
                elapsed_tool = time.perf_counter() - start_tool
                tool_log.append({
                    "round": round_num,
                    "tool_call_id": call.id,
                    "tool": name,
                    "arguments_raw": raw_args,
                    "arguments_parsed": parsed_args,
                    "result": result,
                    "duration_seconds": round(elapsed_tool, 6),
                })
                messages.append({
                    "role": "tool", "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
    finally:
        duration = time.perf_counter() - start_total
        record = {
            "question_id": question_id,
            "question": question,
            "model": model,
            "max_rounds": max_rounds,
            "rounds_used": len(api_log),
            "unanswered": unanswered,
            "answer": final_text if final_text else "ANSWER: UNANSWERED | NA",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_seconds": round(duration, 4),
            "api_calls": api_log,
            "tool_calls": tool_log,
            "messages": messages,
        }
        logfile.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "question_id": question_id,
        "answer": record["answer"],
        "unanswered": unanswered,
        "rounds": record["rounds_used"],
        "tool_calls": len(tool_log),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "seconds": record["total_seconds"],
        "logfile": str(logfile),
    }
