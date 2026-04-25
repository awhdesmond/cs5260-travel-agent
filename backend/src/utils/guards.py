import os
from google import genai

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
PER_REQUEST_TOKEN_CAP: int = int(os.getenv("PER_REQUEST_TOKEN_CAP", "8000"))

_client: genai.Client | None = None

def _get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def check_token_budget(user_request: str) -> tuple[bool, int]:
    try:
        client = _get_genai_client()
        result = client.models.count_tokens(model=DEFAULT_GEMINI_MODEL, contents=user_request)
        token_count = result.total_tokens
        return token_count <= PER_REQUEST_TOKEN_CAP, token_count
    except Exception:
        return True, 0
