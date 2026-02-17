import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-5-nano")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

settings = Settings()

if not settings.openai_api_key:
    raise RuntimeError("OPENAI_API_KEY mangler. Legg den i .env")
