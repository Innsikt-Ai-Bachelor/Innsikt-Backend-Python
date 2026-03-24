from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.tts_service import text_to_speech_stream


router = APIRouter(prefix="/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str


@router.post("/speak")
async def speak(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    audio_stream = text_to_speech_stream(req.text)
    return StreamingResponse(audio_stream, media_type="audio/mpeg")
