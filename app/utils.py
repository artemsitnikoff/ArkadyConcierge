import json
import re


def parse_json_response(raw: str) -> dict:
    """Extract a JSON **object** from an AI response.

    Handles markdown fences and embedded prose. Always returns a dict —
    bare lists/scalars are rejected (downstream consumers expect keyed data).
    """
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    parsed: object | None = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            parsed = json.loads(raw[start:end + 1])
        else:
            raise ValueError(f"Cannot parse JSON from AI response: {raw[:200]}")

    if not isinstance(parsed, dict):
        raise ValueError(
            f"AI returned JSON of type {type(parsed).__name__}, expected object"
        )
    return parsed
