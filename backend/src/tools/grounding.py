import re
import json


def get_grounding_tool() -> dict:
    return {"google_search": {}}


def get_maps_grounding_tool() -> dict:
    """
    Use for activities, meals, and other place-based searches.
    Cannot be combined with google_search in the same request.
    """
    return {"google_maps": {}}


def normalize_content(content: str | list) -> str:
    """Normalize LLM response content to a plain string.

    Gemini 3 returns list of dicts with 'text' keys instead of plain strings.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "\n".join(
            part if isinstance(part, str)
            else part.get("text", "") if isinstance(part, dict) and "text" in part
            else json.dumps(part)
            for part in content
        )

    return str(content)


def extract_json_from_response(response: str | list) -> dict:
    """Extract JSON from LLM response, handling markdown code fences and multi-part grounding.

    When Google Search grounding is active, response.content may be a list of parts.
    Raises json.JSONDecodeError if the response is not valid JSON.
    """
    response = normalize_content(response)

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if json_match:
        inner = json_match.group(1).strip()
        if inner:  # Guard against empty code fences
            return json.loads(inner)

    # Handle truncated code fence (no closing ```) — common with long responses
    trunc_match = re.search(r"```(?:json)?\s*\n?(.*)", response, re.DOTALL)
    if trunc_match:
        inner = trunc_match.group(1).strip()
        if inner:
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                repaired = _repair_truncated_json(inner)
                if repaired is not None:
                    return repaired

    # Try parsing the whole response as JSON (strip whitespace)
    stripped = response.strip()
    if stripped:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(stripped)
            if repaired is not None:
                return repaired

    raise json.JSONDecodeError("Empty response", "", 0)


def _repair_truncated_json(text: str) -> dict | None:
    """Attempt to repair truncated JSON by closing open braces/brackets."""
    # Strip trailing comma or incomplete value
    text = re.sub(r',\s*$', '', text)

    # Remove last incomplete key-value pair (e.g. truncated string)
    text = re.sub(r',?\s*"[^"]*":\s*"[^"]*$', '', text)
    text = re.sub(r',?\s*"[^"]*":\s*$', '', text)

    # Count open vs close braces/brackets
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')

    # Close them
    text = text.rstrip()
    if text.endswith(','):
        text = text[:-1]
    text += ']' * max(0, open_brackets)
    text += '}' * max(0, open_braces)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
