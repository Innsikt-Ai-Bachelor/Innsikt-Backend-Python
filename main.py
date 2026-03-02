from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import users
from routers import chat, rag, scenarios
from database import init_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(chat.router)
app.include_router(rag.router)
app.include_router(scenarios.router)


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.get("/")
def read_root():
    return {"Hello": "World"}
