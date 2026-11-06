from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings


def get_chat_model() -> ChatOpenAI:
    settings = get_settings()
    # Ollama OpenAI compatibility: set OPENAI_API_BASE to http://host:11434/v1 and any non-empty OPENAI_API_KEY (e.g. ollama)
    api_key = settings.openai_api_key.strip() or (
        "ollama" if settings.openai_api_base.strip() else "not-set"
    )
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": api_key,
        "temperature": 0.2,
    }
    base = settings.openai_api_base.strip().rstrip("/")
    if base:
        kwargs["base_url"] = base
    return ChatOpenAI(**kwargs)


async def llm_text(system: str, user: str, *, fallback: str) -> str:
    settings = get_settings()
    if not settings.llm_configured:
        return fallback
    model = get_chat_model()
    response = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = response.content
    if isinstance(content, str):
        return content.strip()
    return fallback
