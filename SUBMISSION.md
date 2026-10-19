# HW4 — submission

**AI assistance:** I used ChatGPT to help structure and draft Part A, review the tool specifications, and check the Q-09 calculations.

---

## Part A — Plan on paper (Easy)

> Commit this whole part before any `.py` file exists.

### A1 — The steps

| # | Step | What goes in (types) | What comes out (types) | When it goes wrong | Tool, loop, or model? |
|---|---|---|---|---|---|
| 1 | Understand the question | Question (`str`) | District names (`list[str]`), required fields (`list[str]`), years (`list[int]`), calculation type (`str`) | The question is unclear or a district name cannot be identified. | Model |
| 2 | Find the required data | District name (`str`), field (`str`), year (`int`) | Value (`float`), unit (`str`), source ID (`str`) | No matching data, multiple matches, or only an archived profile is found. Return an error instead of guessing. | `lookup` tool |
| 3 | Check and convert units | Retrieved values (`list[float]`), units (`list[str]`) | Values in compatible units (`list[float]`) | A unit is unknown or cannot be converted. | Model and `calculate` tool |
| 4 | Prepare the calculations | Required metric (`str`), verified values (`list[float]`) | Arithmetic expressions (`list[str]`) | Some required values are missing or the formula is not clear. | Model |
| 5 | Calculate the results | Arithmetic expressions (`list[str]`) | Calculated values (`list[float]`) | Division by zero, invalid expression, or numbers exceeding the tool's limits. Return an error. | `calculate` tool |
| 6 | Compare and give the answer | Calculated values (`list[float]`), question (`str`), unit (`str`) | Final answer (`str`) | The results are incomplete or cannot be compared. | Model |

**How the steps connect:**

1. The model reads the question and identifies the districts and required data.
2. The model requests the relevant facts through `lookup`. The loop executes the tool calls and returns the results.
3. The model checks the units and uses `calculate` if conversion is needed.
4. The model prepares arithmetic expressions for the required calculations.
5. The loop runs `calculate` and sends the numerical results back to the model.
6. The model compares the results, finds the difference if needed, and gives the final answer.

If a tool returns an error, the model can try another valid request. If the required information is still unavailable, the question should be marked as unanswered rather than answered with a guess.

**What I am assuming:**

- The district profiles from 2025 are used unless the question asks for another year.
- Archived profiles (NR-13 and NR-14) are not used for current data.
- The correction notice NR-16 takes priority over the original Brightwater profile. Its correct area is 921.4 km².
- District names must match exactly, especially Ossbridge and Ossford.
- One megalitre equals 1,000 cubic metres, and one cubic metre equals 1,000 litres.
- The water tariff for 2025 is 142.35 tenge per cubic metre.
- Calculations use unrounded values. Rounding is done only when preparing the final answer, to the required number of decimal places.
- Every retrieved fact should include its source document ID.

### A2 — The two tools

#### `lookup`

```
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Retrieve one numerical fact from the Nine Rivers Region documents by exact district name, field, and year. Use 2025 profiles for current facts, never use archived profiles as current data, and apply later correction notices before returning values. Return the value, unit, and source document IDs. Use district 'region' for the regional water tariff. Return household water use in megalitres, converting cubic metres if necessary.",
    "parameters": {
      "type": "object",
      "properties": {
        "district": {
          "type": "string",
          "description": "Exact district name or 'region' for water_tariff."
        },
        "field": {
          "type": "string",
          "enum": ["population", "area", "budget", "water_use", "schools", "pupils", "paved_road", "founded", "water_tariff"],
          "description": "The numerical field to find."
        },
        "year": {
          "type": "integer",
          "enum": [2020, 2025],
          "description": "2020 is available for census population; use 2025 for current district figures, founding year, school data for 2025/26, and the current water tariff."
        }
      },
      "required": ["district", "field", "year"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| Success | JSON containing `district`, `field`, `year`, `value`, `unit`, and `source_ids`, e.g. `{"value": 921.4, "unit": "km2", "source_ids": ["NR-05", "NR-16"]}`. |
| Unknown or misspelled district | `{"error": "District not found"}` with a suggested valid name if available. |
| Unsupported field or year | `{"error": "Field or year not available"}`. |
| Archived record requested as current data | `{"error": "Archived profile cannot be used as current data"}`. |
| Missing or ambiguous fact | `{"error": "No reliable value found"}`. |
| Invalid input | `{"error": "Invalid arguments"}`. |

**Worst thing it could do with strange or dangerous input:**

A misspelled district or an unsupported field could cause a wrong result. An unchecked input might also cause an unintended file access. I will validate names and fields, read only the local corpus, apply the corrections, and return errors instead of inventing data.

#### `calculate`

```
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Safely evaluate a basic arithmetic expression. Use it for densities, growth percentages, per-person rates, unit conversions, projections and differences. Only numerical constants, parentheses, and the operators +, -, *, / are allowed. Do not send Python code or function calls.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "description": "Arithmetic expression such as '44675 / 921.4', with at most 120 characters. No powers, functions or Python attributes."
        }
      },
      "required": ["expression"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| Success | JSON with the original expression and its numerical value, such as `{"expression": "44675 / 921.4", "value": 48.48599956587801}`. |
| Division by zero | `{"error": "Division by zero"}`. |
| Invalid expression | `{"error": "Invalid arithmetic expression"}`. |
| Unsafe or unsupported input | `{"error": "Unsupported operation"}`. |
| Excessively large calculation | `{"error": "Result exceeds allowed limits"}`. |
| Wrong input type | `{"error": "Invalid arguments"}`. |

**Worst thing it could do with strange or dangerous input:**

If I used eval(), the tool could execute dangerous Python code supplied by the model. A huge expression could also waste time or memory. I will use ast to allow only basic arithmetic, limit the expression length and numerical magnitude, and reject anything unsafe, including attributes, imports and exponentiation.

### A3 — Q-09 by hand

The user asks: "Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?"
The conversation I expect between the model and the tools is:

```
[
  {
    "role": "user",
    "content": "Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?"
  },
  {
    "role": "assistant",
    "tool_calls": [
      {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\":\"Brightwater\",\"field\":\"population\",\"year\":2025}"}},
      {"id": "call_2", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\":\"Brightwater\",\"field\":\"area\",\"year\":2025}"}},
      {"id": "call_3", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\":\"Millbrook\",\"field\":\"population\",\"year\":2025}"}},
      {"id": "call_4", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\":\"Millbrook\",\"field\":\"area\",\"year\":2025}"}}
    ]
  },
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"district\":\"Brightwater\",\"field\":\"population\",\"year\":2025,\"value\":44675,\"unit\":\"residents\",\"source_ids\":[\"NR-05\"]}"},
  {"role": "tool", "tool_call_id": "call_2", "content": "{\"district\":\"Brightwater\",\"field\":\"area\",\"year\":2025,\"value\":921.4,\"unit\":\"km2\",\"source_ids\":[\"NR-05\",\"NR-16\"]}"},
  {"role": "tool", "tool_call_id": "call_3", "content": "{\"district\":\"Millbrook\",\"field\":\"population\",\"year\":2025,\"value\":37203,\"unit\":\"residents\",\"source_ids\":[\"NR-11\"]}"},
  {"role": "tool", "tool_call_id": "call_4", "content": "{\"district\":\"Millbrook\",\"field\":\"area\",\"year\":2025,\"value\":758.6,\"unit\":\"km2\",\"source_ids\":[\"NR-11\"]}"},
  {
    "role": "assistant",
    "tool_calls": [
      {"id": "call_5", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\":\"44675 / 921.4\"}"}},
      {"id": "call_6", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\":\"37203 / 758.6\"}"}}
    ]
  },
  {"role": "tool", "tool_call_id": "call_5", "content": "{\"expression\":\"44675 / 921.4\",\"value\":48.48599956587801}"},
  {"role": "tool", "tool_call_id": "call_6", "content": "{\"expression\":\"37203 / 758.6\",\"value\":49.04165568151859}"},
  {
    "role": "assistant",
    "tool_calls": [
      {"id": "call_7", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\":\"49.04165568151859 - 48.48599956587801\"}"}}
    ]
  },
  {"role": "tool", "tool_call_id": "call_7", "content": "{\"expression\":\"49.04165568151859 - 48.48599956587801\",\"value\":0.55565611564058}"},
  {"role": "assistant", "content": "Millbrook has the higher population density in 2025, by 0.6 residents per square kilometre. ANSWER: Millbrook | 0.6"}
]
```

**My arithmetic:**

- Brightwater population: 44,675 (NR-05). Corrected area: 921.4 km² (NR-16, correcting NR-05).
- Millbrook population: 37,203; area: 758.6 km² (NR-11).
- Brightwater density = 44,675 / 921.4 = 48.4860 residents/km².
- Millbrook density = 37,203 / 758.6 = 49.0417 residents/km².
- Difference = 49.04165568 - 48.48599957 = 0.55565611 ≈ 0.6 residents/km², rounded to one decimal place.
So the expected answer is Millbrook | 0.6. Using the old, incorrect Brightwater area (912.4 km²) would change the comparison, which is why the correction matters.

### A4 — Why I split it this way

One alternative would be to make a single tool called answer_question that searches the documents, performs all calculations and returns the final answer. I did not choose this because it would mix fact retrieval, arithmetic and explanation in one step, making errors harder to identify. With separate lookup and calculate tools, I can check which document each value came from, apply the correction before calculating, and test the mathematical operations independently. The model only needs to decide which facts and formulas are required. The drawback is that this approach may require more tool calls and take longer, but I think the extra transparency is useful for these questions.

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

The original split into lookup and calculate stayed the same. In the code I added input and JSON validation, clear errors, a fixed 8-round limit and logs for each question. I also had to set reasoning_effort="none" after an API compatibility error during the first B3 test. This setting was then used consistently for all three strategies. The main tool definitions and the order of operations from Part A were not changed.

### B2 — Tests

I ran python -m pytest -v tests/test_tools.py without an API key. The 16 tests check the data lookup, similar and misspelled district names, the archived records, the corrected Brightwater area, normalized water units, arithmetic, division by zero and unsafe expressions.

```
collecting ... collected 16 items

tests/test_tools.py::test_lookup_2025_population PASSED
tests/test_tools.py::test_lookup_corrected_area PASSED
tests/test_tools.py::test_lookup_misspelled_district PASSED
tests/test_tools.py::test_lookup_similar_district_names PASSED
tests/test_tools.py::test_lookup_archived_year_cannot_replace_current PASSED
tests/test_tools.py::test_lookup_water_units_are_normalized PASSED
tests/test_tools.py::test_lookup_rejects_unsupported_year_or_field PASSED
tests/test_tools.py::test_calculate_required_multiplication PASSED
tests/test_tools.py::test_calculate_population_density PASSED
tests/test_tools.py::test_calculate_parentheses_and_subtraction PASSED
tests/test_tools.py::test_calculate_division_by_zero PASSED
tests/test_tools.py::test_calculate_rejects_unsafe_expressions[__import__('os').system('echo hi')] PASSED
tests/test_tools.py::test_calculate_rejects_unsafe_expressions[(1).__class__] PASSED
tests/test_tools.py::test_calculate_rejects_unsafe_expressions[9**9**9] PASSED
tests/test_tools.py::test_calculate_rejects_huge_result PASSED
tests/test_tools.py::test_calculate_rejects_invalid_input_type PASSED

============================== 16 passed in 0.05s ==============================
```

### B3 — The loop

- Round limit, and why: I set the maximum number of rounds to 8. The model needs time to look up several facts, calculate intermediate results and give the final answer. The limit prevents infinite tool-calling loops; if it is reached without a final answer, the question is marked unanswered.
- Where the logs are: The standalone Q-09 test produced outputs/Q-09_S3.json. In the two complete runs, the detailed tool conversations are under outputs/run_1/S3_logs/ and outputs/run_2/S3_logs/. These JSON logs record each tool call, its inputs, outputs, time, model rounds and token usage. The per-question strategy results are saved under the corresponding S1/, S2/ and S3/ folders.
- Real Q-09 conversation compared with my A3 version, what is different: The actual execution followed my planned steps. In round 1 the model made four lookup calls for both populations and areas, including Brightwater's corrected area of 921.4 km². In round 2 it made two calculate calls for population densities. In round 3 it calculated their difference, and in round 4 it gave the final answer, Millbrook | 0.6. The run used 4 rounds, 7 tool calls, 3,513 input tokens and 229 output tokens, taking 6.93 seconds. The main difference is that the real log also has actual call IDs, durations and usage counts; the mathematical steps and the answer matched the hand-written plan.

### B4 — Three strategies

**What I kept the same:**
- The model was gpt-5.6-luna for S1, S2 and S3, with reasoning_effort="none".
- All strategies answered exactly the same 20 questions from data/questions.json, in the same order, and used the same reference answers only for scoring after generation.
- Each strategy was instructed to finish with ANSWER: <name or yes/no> | <number> and use the question's requested number of decimals. The strategies differed only in how they used documents, reasoning samples or tools.
- S1 received the full corpus and made one model call. S2 received the same corpus, made 5 independent model calls per question (k = 5), and voted on the complete label-and-number answer (ties use the first observed answer). S3 did not receive the corpus in the prompt and used lookup and calculate, with a limit of 8 rounds.
- I did not explicitly set temperature in any strategy: all used the API default. S2 therefore relied on variation across separate requests rather than a custom temperature value. This is a limitation of the experiment.
- Input and output tokens were summed from the API usage counts of every call, including all five S2 samples and all rounds of S3. Time was measured as wall-clock seconds. The reported cost is an estimate using $0.20 per million input tokens and $1.20 per million output tokens, without prompt-caching discounts.

**My rule for a correct answer** (fixed in run.py before the first full run):
The final line must have a parsable ANSWER: label | number format. The label must match the reference exactly. The number is rounded to the specified decimals, and a difference of at most one unit in the last decimal place is allowed. A missing or invalid final line is counted as unanswered. A parsable answer with a wrong label or a number outside this tolerance is counted as incorrect. I used the same rule for every strategy and both runs.

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | 14/20 | 1 | 44,640 | 1,500 | 1.18 | 25.73 | 0.010728 |
| 1 | S2 think and vote (k = 5) | 14/20 | 1 | 226,400 | 10,774 | 7.69 | 149.94 | 0.058209 |
| 1 | S3 tools | 16/20 | 4 | 73,139 | 4,826 | 4.72 | 94.24 | 0.020419 |
| 2 | S1 direct | 11/20 | 1 | 44,640 | 1,398 | 1.22 | 25.94 | 0.010606 |
| 2 | S2 think and vote (k = 5) | 15/20 | 1 | 226,400 | 10,575 | 6.96 | 149.67 | 0.057970 |
| 2 | S3 tools | 18/20 | 2 | 67,169 | 4,698 | 4.72 | 90.59 | 0.019071 |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✓ | ✓ |
| Q-02 | ✓ | ✓ | ✗ |
| Q-03 | ✓ | ✓ | ✓ |
| Q-04 | ✓ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✓ | ✓ | ✓ |
| Q-07 | ✓ | ✓ | ✓ |
| Q-08 | ✓ | ✓ | ✗ |
| Q-09 | ✓ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✓ | ✓ | ✓ |
| Q-12 | ✓ | ✓ | ✓ |
| Q-13 | ✗ | ✗ | ✗ |
| Q-14 | ✓ | ✗ | ✓ |
| Q-15 | ✗ | ✗ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✗ |
| Q-18 | ✗ | ✓ | ✓ |
| Q-19 | ✓ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |

**Per question (run 2):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✓ | ✓ |
| Q-02 | ✓ | ✓ | ✓ |
| Q-03 | ✓ | ✓ | ✓ |
| Q-04 | ✓ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✓ | ✓ | ✓ |
| Q-07 | ✗ | ✓ | ✓ |
| Q-08 | ✗ | ✓ | ✗ |
| Q-09 | ✓ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✗ | ✓ | ✓ |
| Q-12 | ✓ | ✓ | ✓ |
| Q-13 | ✗ | ✗ | ✗ |
| Q-14 | ✗ | ✗ | ✓ |
| Q-15 | ✗ | ✗ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✓ | ✓ |
| Q-18 | ✓ | ✓ | ✓ |
| Q-19 | ✓ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |

These are the scores produced by my automatic checker, without changing the rule between runs. One relevant limitation is strict output formatting: a response that adds a unit after the number in the final ANSWER: line can be classified as unanswered even when its calculation in the main text is correct (for example, S3 on Q-08 and Q-13). I will discuss such errors in Part C rather than silently changing the results.

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?
I tested Q-02, Q-05, Q-08, Q-09 and Q-13 again with the lookup description replaced by "Looks things up.". I kept the same model, question, tool parameters, calculator and round limit. The table compares the detailed-description results from run 1 with the new vague-description test.

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| Q-02 | 7 | 7 | Harrowfield — 1.69 percentage points | Harrowfield — 1.69 percentage points |
| Q-05 | 7 | 7 | Coldharbour — 14235 | Coldharbour — 14235 |
| Q-08 | 4 | 6 | Brightwater — 72.46 million tenge | Brightwater — 72.46 million tenge |
| Q-09 | 7 | 7 | Millbrook — 0.6 | Millbrook — 0.6 |
| Q-13 | 9 | 9 | Coldharbour — 4.16% | Coldharbour — 4.16% |

The final answers were unchanged on all five questions. For Q-08, the number of calls increased from 4 to 6, and the tool inputs changed. For the other four questions, the number of calls and inputs remained the same. This suggests that a clear tool description can sometimes reduce unnecessary tool calls, but the five-question test does not show an improvement in accuracy. The parameter names, field choices, and system instructions were still detailed, so making only the lookup description vague did not remove all guidance.

Under my original strict answer parser, both versions scored only 2/5 correct: Q-05 and Q-09. Q-02, Q-08 and Q-13 had the right information but added units in the final ANSWER: line, which my parser rejected. I kept the original scoring rule and did not change these results after seeing them.

### C2 — Three mistakes explained

S1 — Direct, Q-05 (run 1). The model selected the correct district, Coldharbour, but made an arithmetic error when comparing 2025 budgets per resident. Its log says: Stonecairn: 2,884.6 million ÷ 14,926 = 193,155 tenge per resident, followed by ANSWER: Coldharbour | 14345. The correct Stonecairn figure is about 193,260 tenge per resident, and Coldharbour's is about 207,495, giving a difference of 14,235 tenge per resident. S1 had the necessary facts in the prompt, but it calculated the numerical result itself without a calculator to verify it.

S2 — Think and Vote, Q-14 (run 1). The vote counts were Tarnvale | 0.0 twice, Tarnvale | 0.2 once, Ashgrove | 4.8 once and Ashgrove | 4.7 once. The final vote therefore selected ANSWER: Tarnvale | 0.0, while the reference was Ashgrove | 4.9 litres per resident per day. In some samples, the model used 1,000 instead of 1,000,000 to convert megalitres to litres and got around 0.2 litres per resident per day. Asking five times can reduce random mistakes when most samples are independently likely to be correct, but it cannot reliably fix a shared conversion error; here the correct district's votes were also split between different numbers.

S3 — Tools, Q-17 (run 1). The first round correctly looked up Harrowfield's and Ossbridge's water use and population, plus the tariff. However, the model then sent 7146 * 1000000 * 142.35 / 90212 to calculate, which returned {"error": "Result exceeds allowed limits"}. The main problem was treating one megalitre as 1,000,000 cubic metres, although it equals 1,000 cubic metres. The model retried several calculations instead of fixing the unit conversion. It used 8 rounds and 13 tool calls, reached the round limit and finished with ANSWER: UNANSWERED | NA. In run 2 it used the correct conversion and answered Harrowfield | 884 in 4 rounds. The calculator stopped overly large calculations, but it could not know the unit conversion the model intended. 

These examples explain both the benefit and the cost of tools. A calculator can make arithmetic deterministic once the expression is correct, but it cannot correct a wrong formula or unit. Each extra S3 round also resends more conversation history; in Q-17 run 1, input tokens rose from 581 in round 1 to 1,379 in round 8, for 8,953 input tokens overall.

### C3 — Which strategy I would use, and what would change it

For these twenty questions, I would choose S3 — Tools. It scored 16/20 and 18/20 in the two runs, or 85% on average, compared with 72.5% for S2 and 62.5% for S1. Its estimated cost was $0.020419 and $0.019071 per run, compared with around $0.058 for S2. S3 also took about 4.72 seconds per question at the median, faster than S2 (6.96–7.69 seconds), although it was slower than S1. Across both runs, S1 used 89,280 input tokens and 2,898 output tokens, S2 used 452,800 input tokens and 21,349 output tokens, and S3 used 140,308 input tokens and 9,524 output tokens. S3 required more tokens than S1 but considerably fewer than S2.

I would not choose S1 as the default because its manual calculations were less reliable, despite being the cheapest and fastest. I would not choose S2 because five samples cost about 5.45 times as much as S1 across the two runs, and voting sometimes repeated or combined wrong calculations. S3 makes fact retrieval traceable to source documents and leaves arithmetic to a restricted calculator, although Q-17 shows that wrong units can still cause problems.

My choice would change with the situation. If a question were simple, such as Q-10 about founding years, and speed or budget were the main priority, I would use S1: all three strategies answered Q-10 correctly in both runs, and S1 was much faster. If I had 100,000 documents, I would still prefer a tool-based approach but replace the current full-file lookup with an indexed retrieval system. If there were no arithmetic and tool implementation was not available, S1 could also be sufficient. I would use S2 only if repeated answers gave a measurable reliability benefit on the relevant type of question and the extra cost was acceptable.

### C4 — How sure I can be

The two runs were not identical. S1 dropped from 14/20 to 11/20 (a 15-percentage-point change), S2 increased from 14/20 to 15/20 (5 points), and S3 improved from 16/20 to 18/20 (10 points). S3 beat S2 by 2 questions in run 1 and by 3 questions in run 2. Their average accuracy gap was 12.5 percentage points, which is close to the run-to-run changes seen in this experiment.

I therefore think S3 is the best choice for this homework, but I cannot claim that it will always be better. There were only 20 distinct questions about one fictional region, and repeating the same questions does not create 40 independent examples. I would want roughly 150–200 new, varied questions, preferably across several document collections, and more repeated runs before trusting a smaller accuracy gap. I would then compare paired results and uncertainty intervals instead of relying only on the winning percentage. The strict ANSWER: parser is another limitation because it marked some numerically correct responses as unanswered when they included units after the number.

### Final questions

1. When the model sends a tool_calls message, what has actually run so far?

Only the model's API call has run. The model has requested a function, but it has not executed lookup or calculate itself. My Python loop must validate the request, call the local function, and send its result back with the matching tool_call_id.

2. Why does arguments arrive as a string, and what goes wrong if you pass it straight into your function?

The model produces tool arguments as JSON text, so I need to parse it with json.loads() and check the required keys and types. Passing the raw string directly would not match the function's parameters and could cause errors. Validation also prevents unexpected arguments from reaching the tool.

3. How many tokens do your two tool definitions add to every S3 request? Measure it.

I measured the same messages with and without the two tool definitions, using tool_choice="none" in the tool-enabled request. The request used 169 input tokens without tools and 569 with tools, a difference of 400 input tokens. This is the measured prompt overhead for the two definitions in that test, not the total cost of running tools across multiple rounds.

4. How much more did S2 cost than S1? Give the number from your table and explain it.

Across both runs, S2 cost an estimated $0.116179, while S1 cost $0.021334. That is $0.094845 more, or about 5.45 times the cost of S1. S2 made five model calls per question instead of one, repeatedly sending the corpus; these are uncached-rate estimates, not exact billed amounts.

5. Which question needed the most rounds in S3, and why?

Q-17 in run 1 needed the most: it reached the limit of 8 rounds and made 13 tool calls without producing a valid answer. The model repeatedly used the wrong megalitre-to-cubic-metre conversion and received large-number errors. In run 2, the same question took 4 rounds and was answered correctly.

6. What would you change in lookup if there were 100,000 documents?

I would not read and search all documents again on each call. I would build a structured or full-text index of districts, fields, years, sources and correction notices, then retrieve only a few relevant records. This would make lookup faster and reduce irrelevant information while preserving source IDs.

7. What stops your calculate from running dangerous code? Could the model still make it misbehave?

My calculator uses Python's ast parser, not eval() or exec(), and accepts only numeric constants and basic +, -, *, / operations. It also limits expression length, nesting depth, numerical size and division by zero. The model cannot run arbitrary Python through it, but it can still supply a mathematically valid expression with wrong units or a wrong formula, as happened in Q-17.

8. For which kind of question did tools help most, and for which did they not help at all?

Tools helped most on multi-step numerical comparisons, especially budgets or rates per resident and unit conversions: S3 answered Q-05, Q-15 and Q-20 correctly in both runs when S1 and S2 did not. They added little benefit for simple factual comparisons such as Q-10, where all three strategies were correct and S1 was faster. Tools also could not prevent final-answer formatting mistakes on Q-08 and Q-13, even though the calculations were correct.
