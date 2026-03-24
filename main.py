import os

from fastapi import FastAPI
from dotenv import load_dotenv
import uvicorn
from routers import users, chat, rag, scenarios, tts
from database import init_db

load_dotenv()

app = FastAPI()

app.include_router(users.router)
app.include_router(chat.router)
app.include_router(rag.router)
app.include_router(scenarios.router)
app.include_router(tts.router)


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.get("/")
def read_root():
    return {"Hello": "World"}


if __name__ == "__main__":
    reload = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=reload)