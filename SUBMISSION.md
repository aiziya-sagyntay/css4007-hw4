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

<!-- what changed in your plan, and why. "None" is an answer too. -->

### B2 — Tests

```text
<!-- pytest output -->
```

### B3 — The loop

- Round limit, and why:
- Where the logs are:
- Real Q-09 conversation compared with my A3 version, what is different:

### B4 — Three strategies

**What I kept the same:**

<!-- model, temperature, k, prompts, answer format, anything else -->

**My rule for a correct answer** (written before the first full run):

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | | | | | | | |
| 1 | S2 think and vote (k = ) | | | | | | | |
| 1 | S3 tools | | | | | | | |
| 2 | S1 direct | | | | | | | |
| 2 | S2 think and vote (k = ) | | | | | | | |
| 2 | S3 tools | | | | | | | |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | | | |
| Q-02 | | | |
| Q-03 | | | |
| Q-04 | | | |
| Q-05 | | | |
| Q-06 | | | |
| Q-07 | | | |
| Q-08 | | | |
| Q-09 | | | |
| Q-10 | | | |
| Q-11 | | | |
| Q-12 | | | |
| Q-13 | | | |
| Q-14 | | | |
| Q-15 | | | |
| Q-16 | | | |
| Q-17 | | | |
| Q-18 | | | |
| Q-19 | | | |
| Q-20 | | | |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

### C2 — Three mistakes explained

### C3 — Which strategy I would use, and what would change it

### C4 — How sure I can be

### Final questions

1.
2.
3.
4.
5.
6.
7.
8.
