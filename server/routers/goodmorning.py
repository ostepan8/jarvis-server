from __future__ import annotations

import asyncio
import json as _json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from jarvis import JarvisSystem
from ..dependencies import get_jarvis
from jarvis.io.output.tts.openai import OpenAITTSEngine

router = APIRouter()


# ---------------------------
# HTTP handler
# ---------------------------
@router.post("")  # parent router mounts this at /goodmorning
async def goodmorning(request: Request, jarvis_system: JarvisSystem = Depends(get_jarvis)):
    return await _handle_goodmorning(request, jarvis_system)


async def _handle_goodmorning(request: Request, jarvis_system: JarvisSystem):
    """Webhook-style endpoint for scheduler to ping Jarvis in the morning."""
    raw_body = await request.body()

    # Best-effort parse JSON; never fail the request on parse errors
    try:
        json_body = await request.json()
    except Exception:
        json_body = None

    payload = {
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "body": raw_body.decode("utf-8", errors="replace"),
        "json": json_body,
    }

    print("[/goodmorning] Incoming request:")
    print(_json.dumps(payload, indent=2))

    # Fire-and-forget morning routine
    asyncio.create_task(_run_wake_sequence(jarvis_system, json_body or {}))

    return {"status": "ok", "message": "Good morning queued", "received": payload}


# ---------------------------
# Wake routine
# ---------------------------
async def _run_wake_sequence(jarvis: JarvisSystem, data: Dict[str, Any]) -> None:
    """Run morning wake routine: exit night mode, turn on lights, speak greeting."""
    try:
        # 1) Exit night mode if a wake protocol exists
        try:
            runtime = getattr(jarvis, "protocol_runtime", None)
            if runtime is not None and runtime.registry is not None:
                wake_proto = runtime.registry.get("wake_up")
                if wake_proto is not None:
                    await runtime.executor.run_protocol(wake_proto, arguments={})
        except Exception as exc:
            print(f"[goodmorning] Failed to run wake_up protocol: {exc}")

        # 2) Turn on the lights via protocol if lights agent is available
        try:
            agents = getattr(jarvis.network, "agents", {}) or {}
            if "PhillipsHueAgent" in agents:
                runtime = getattr(jarvis, "protocol_runtime", None)
                if runtime is not None and runtime.registry is not None:
                    lights_proto = runtime.registry.get("lights_on")
                    if lights_proto is not None:
                        await runtime.executor.run_protocol(lights_proto, arguments={})
                    else:
                        print("[goodmorning] 'lights_on' protocol not found")
                else:
                    print("[goodmorning] Protocol runtime not initialized")
            else:
                print("[goodmorning] Skipping lights_on: PhillipsHueAgent not active")
        except Exception as exc:
            print(f"[goodmorning] Failed to run lights_on protocol: {exc}")

        # 3) Build a short greeting from scheduler context
        greeting = _build_greeting(data)

        # 4) Speak via TTS (prefer ElevenLabs; fall back to OpenAI on any failure)
        await _speak_tts(greeting)

    except Exception as exc:
        print(f"[goodmorning] Wake sequence error: {exc}")


def _build_greeting(data: Dict[str, Any]) -> str:
    tz = data.get("timezone")
    wake_time = data.get("wake_time")
    ctx = data.get("context", {}) or {}

    # Format local time if provided
    time_str: Optional[str] = None
    try:
        if wake_time:
            dt = datetime.fromisoformat(wake_time.replace("Z", "+00:00"))
            if tz:
                dt = dt.astimezone(ZoneInfo(tz))
            time_str = dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        pass

    # Earliest event details
    first_title: Optional[str] = None
    first_start_local: Optional[str] = None
    earliest = ctx.get("earliest_event") or (ctx.get("first_events") or [{}])[0]
    try:
        if isinstance(earliest, dict):
            first_title = earliest.get("title")
            start_iso = earliest.get("start")
            if start_iso:
                sdt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                if tz:
                    sdt = sdt.astimezone(ZoneInfo(tz))
                first_start_local = sdt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        pass

    # Build message
    parts: list[str] = ["Good morning, sir."]
    if time_str:
        parts.append(f"It's {time_str}.")
    if first_title and first_start_local:
        parts.append(f"Your first event is {first_title} at {first_start_local}.")
    parts.append("I've turned on the lights. Time to rise and shine.")

    return " ".join(parts)


# ---------------------------
# TTS with robust fallback
# ---------------------------
async def _speak_tts(text: str) -> None:
    """Speak text using ElevenLabs if available; fall back to OpenAI on failure."""
    if not text:
        return

    eleven_key_present = bool(os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_LABS_API_KEY"))
    openai_key_present = bool(os.getenv("OPENAI_API_KEY"))

    # Try ElevenLabs first (if configured)
    if eleven_key_present:
        try:
            await _speak_with_elevenlabs(text)
            return
        except Exception as e:
            print(f"[goodmorning] ElevenLabs failed, will try OpenAI fallback: {e}")

    # Fallback: OpenAI TTS (if configured)
    if openai_key_present:
        try:
            await _speak_with_openai(text)
            return
        except Exception as e:
            print(f"[goodmorning] OpenAI TTS error: {e}")

    # If we get here, we have no working TTS
    if not eleven_key_present and not openai_key_present:
        print("[goodmorning] TTS skipped: neither ELEVENLABS_API_KEY nor OPENAI_API_KEY is set")
    else:
        print("[goodmorning] TTS failed: all providers errored")


async def _speak_with_elevenlabs(text: str) -> None:
    """Use the official ElevenLabs SDK per quickstart and play the audio.

    This mirrors:
      client = ElevenLabs(); audio = client.text_to_speech.convert(...); play(audio)
    and runs the blocking play() in a worker thread so we don't block the event loop.
    """
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import play
    except ImportError:
        raise Exception("elevenlabs package not installed. Run: pip install elevenlabs python-dotenv")

    api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_LABS_API_KEY")
    # client reads env automatically; passing api_key if present is fine
    client = ElevenLabs(api_key=api_key) if api_key else ElevenLabs()

    voice_id = os.getenv("ELEVEN_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    model_id = os.getenv("ELEVEN_MODEL_ID", "eleven_multilingual_v2")

    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format="mp3_44100_128",
    )

    # Offload blocking playback
    await asyncio.to_thread(play, audio)


async def _speak_with_openai(text: str) -> None:
    """OpenAI TTS fallback."""
    # Keep your existing default; allow override via env
    model = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")
    allowed = {"nova", "shimmer", "echo", "onyx", "fable", "alloy", "ash", "sage", "coral"}
    vreq = os.getenv("OPENAI_TTS_VOICE")
    voice = vreq if vreq in allowed else "alloy"

    tts = OpenAITTSEngine(model=model, voice=voice)
    await tts.speak(text)
