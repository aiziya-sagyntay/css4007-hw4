"""HW4 B1: safe, document-grounded lookup and arithmetic tools.

The return values of both tools are small JSON-serialisable dictionaries.
No API key or LLM is needed to run them.
"""

import ast
import difflib
import json
import math
import operator
import re
from pathlib import Path

CORPUS = Path(__file__).resolve().parent / "data" / "corpus.jsonl"
FIELDS = {
    "population", "area", "budget", "water_use", "schools", "pupils",
    "paved_road", "founded", "water_tariff",
}
_NUMBER = r"([\d,]+(?:\.\d+)?)"
_MAX_ABS = 1e12
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _number(raw):
    value = float(raw.replace(",", ""))
    if not math.isfinite(value):
        raise ValueError("Non-finite number")
    return int(value) if value.is_integer() else value


def _find(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _number(match.group(1))
    return None


def _read_corpus():
    with CORPUS.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def lookup(district, field, year):
    """Look up one sourced numeric fact; never let invalid inputs crash the caller."""
    try:
        if not isinstance(district, str) or not isinstance(field, str) or \
                type(year) is not int or len(district) > 80 or len(field) > 40:
            return {"error": "Invalid arguments"}

        docs = _read_corpus()
        names = {
            d["title"].split(" district profile")[0]: d
            for d in docs
            if d["id"] in {f"NR-{i:02d}" for i in range(1, 13)}
        }
        normalized = district.strip()
        if normalized.lower() == "region":
            if field != "water_tariff" or year != 2025:
                return {"error": "Field or year not available"}
            tariff_doc = next(d for d in docs if d["id"] == "NR-15")
            value = _find(tariff_doc["text"], [
                r"tariff is\s+" + _NUMBER + r"\s+tenge per cubic metre"
            ])
            if value is None:
                return {"error": "No reliable value found"}
            return {"district": "region", "field": field, "year": year,
                    "value": value, "unit": "tenge/m3", "source_ids": ["NR-15"]}

        if normalized not in names:
            suggestions = difflib.get_close_matches(normalized, list(names), n=3, cutoff=0.5)
            result = {"error": "District not found"}
            if suggestions:
                result["suggestions"] = suggestions
            return result

        if field not in FIELDS or field == "water_tariff" or year not in (2020, 2025):
            return {"error": "Field or year not available"}
        if year == 2020 and field != "population":
            return {"error": "Field or year not available"}

        doc = names[normalized]
        text = doc["text"]
        sources = [doc["id"]]

        if field == "population":
            if year == 2025:
                patterns = [
                    r"2025 census (?:recorded|counted)\s+" + _NUMBER,
                    r"census population:\s*[\d,]+\s+in 2020 and\s+" + _NUMBER + r"\s+in 2025",
                ]
            else:
                patterns = [
                    r"2020 census had recorded\s+" + _NUMBER,
                    r"census population:\s*" + _NUMBER + r"\s+in 2020",
                    r"from\s+" + _NUMBER + r"\s+at the 2020 census",
                ]
            value, unit = _find(text, patterns), "residents"
        elif field == "area":
            patterns = [
                r"covers\s+" + _NUMBER + r"\s+square kilometres",
                r"over\s+" + _NUMBER + r"\s+square kilometres",
                r"on an area of\s+" + _NUMBER + r"\s+square kilometres",
            ]
            value, unit = _find(text, patterns), "km2"
            if normalized == "Brightwater":
                correction = next(d for d in docs if d["id"] == "NR-16")
                corrected = _find(correction["text"], [
                    r"correct area is\s+" + _NUMBER + r"\s+square kilometres"
                ])
                if corrected is None:
                    return {"error": "No reliable value found"}
                value = corrected
                sources.append("NR-16")
        elif field == "budget":
            patterns = [
                r"budget for 2025 was set at\s+" + _NUMBER + r"\s+million tenge",
                r"2025 budget amounted to\s+" + _NUMBER + r"\s+million tenge",
                r"2025 budget was\s+" + _NUMBER + r"\s+million tenge",
            ]
            value, unit = _find(text, patterns), "million tenge"
        elif field == "water_use":
            match = re.search(
                r"(?:water use in 2025 came to|households used)\s+" + _NUMBER +
                r"\s+(megalitres|cubic metres)", text, re.IGNORECASE
            )
            value = _number(match.group(1)) if match else None
            if match and match.group(2).lower() == "cubic metres":
                value /= 1000  # Always return water use in megalitres.
            unit = "megalitres"
        elif field == "schools":
            value = _find(text, [r"(?:has|runs|are)\s+" + _NUMBER + r"\s+schools"])
            unit = "schools"
        elif field == "pupils":
            value = _find(text, [r"(?:attended by|enrolled|with)\s+" + _NUMBER + r"\s+pupils"])
            unit = "pupils"
        elif field == "paved_road":
            value = _find(text, [
                r"paved road network is\s+" + _NUMBER + r"\s+km long",
                r"(?:keeps|maintains)\s+" + _NUMBER + r"\s+km of paved road",
            ])
            unit = "km"
        else:  # founded
            value = _find(text, [r"founded in\s+" + _NUMBER])
            unit = "year"

        if value is None:
            return {"error": "No reliable value found"}
        return {"district": normalized, "field": field, "year": year,
                "value": value, "unit": unit, "source_ids": sources}
    except Exception:
        return {"error": "No reliable value found"}


def calculate(expression):
    """Evaluate only +, -, *, /, unary signs, numeric literals, parentheses."""
    if not isinstance(expression, str) or not 0 < len(expression) <= 120:
        return {"error": "Invalid arguments"}
    try:
        node = ast.parse(expression, mode="eval")

        def evaluate(item, depth=0):
            if depth > 25:
                raise ValueError("Expression too complex")
            if isinstance(item, ast.Expression):
                return evaluate(item.body, depth + 1)
            if isinstance(item, ast.Constant) and type(item.value) in (int, float):
                answer = item.value
            elif isinstance(item, ast.UnaryOp) and type(item.op) in _UNARY:
                answer = _UNARY[type(item.op)](evaluate(item.operand, depth + 1))
            elif isinstance(item, ast.BinOp) and type(item.op) in _OPERATORS:
                left = evaluate(item.left, depth + 1)
                right = evaluate(item.right, depth + 1)
                if isinstance(item.op, ast.Div) and right == 0:
                    raise ZeroDivisionError
                answer = _OPERATORS[type(item.op)](left, right)
            else:
                raise ValueError("Unsupported operation")
            if not isinstance(answer, (int, float)) or not math.isfinite(answer) or abs(answer) > _MAX_ABS:
                raise OverflowError
            return answer

        value = evaluate(node)
        return {"expression": expression, "value": value}
    except ZeroDivisionError:
        return {"error": "Division by zero"}
    except OverflowError:
        return {"error": "Result exceeds allowed limits"}
    except SyntaxError:
        return {"error": "Invalid arithmetic expression"}
    except (ValueError, TypeError, RecursionError):
        return {"error": "Unsupported operation"}
    except Exception:
        return {"error": "Invalid arithmetic expression"}
