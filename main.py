from typing import Union

from fastapi import FastAPI

from .routers import users
from .database import init_db

app = FastAPI()

app.include_router(users.router)


@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/")
def read_root():
    return {"Hello": "World"}