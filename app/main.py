from fastapi import FastAPI
from app.routers import users, rag

app = FastAPI(title="Innsikt Backend")

app.include_router(users.router)
app.include_router(rag.router)

@app.get("/")
def root():
    return {"status": "ok"}
