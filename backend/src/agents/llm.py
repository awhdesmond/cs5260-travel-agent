from functools import lru_cache
from langchain_google_genai import ChatGoogleGenerativeAI


@lru_cache(maxsize=1)
def get_gemini_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0,
        max_output_tokens=65536,
        thinking_budget=0,
    )
