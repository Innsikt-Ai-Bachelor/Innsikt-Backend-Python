import os

import requests
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/stt", tags=["stt"])


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY is not set")

    audio_bytes = await file.read()
    response = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": api_key},
        files={"file": (file.filename, audio_bytes, file.content_type)},
        data={"model_id": "scribe_v2"},
    )
    response.raise_for_status()
    return {"text": response.json()["text"]}
