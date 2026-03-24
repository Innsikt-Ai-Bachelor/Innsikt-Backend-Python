import os
from elevenlabs.client import ElevenLabs


def _client() -> ElevenLabs:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    return ElevenLabs(api_key=api_key)


def get_voice_id() -> str:
    return os.getenv("ELEVENLABS_VOICE_ID", "uNsWM1StCcpydKYOjKyu")


def text_to_speech_stream(text: str):
    client = _client()
    return client.text_to_speech.stream(
        voice_id=get_voice_id(),
        text=text,
        model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128",
        language_code="no",
    )
