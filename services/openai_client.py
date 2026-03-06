import json
import os
from typing import Any, Dict, List

from openai import AsyncOpenAI


def _client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=api_key)


def get_embedding_model() -> str:
    # models.rag.EMBED_DIM is 1536, so default to text-embedding-3-small.
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def get_chat_model() -> str:
    return os.getenv("CHAT_MODEL", "gpt-5-nano")


async def embed_texts(texts: List[str]) -> List[List[float]]:
    client = _client()
    model = get_embedding_model()
    resp = await client.embeddings.create(model=model, input=texts)
    # Keep order stable
    return [d.embedding for d in resp.data]


async def embed_query(text: str) -> List[float]:
    return (await embed_texts([text]))[0]


async def chat_complete(system: str, user: str) -> str:
    client = _client()
    model = get_chat_model()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""

async def chat_complete_messages(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
) -> str:
    """
    messages: [{"role": "system|user|assistant", "content": "..."}]
    """
    client = _client()
    model = get_chat_model()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return resp.choices[0].message.content or ""


async def chat_complete_json(system: str, user: str) -> dict:
    """Kaller OpenAI med JSON mode – returnerer alltid et dict."""
    client = _client()
    model = get_chat_model()
    resp = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return json.loads(resp.choices[0].message.content or "{}")
