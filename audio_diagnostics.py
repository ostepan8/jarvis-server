#!/usr/bin/env python3
"""
Audio system diagnostics for troubleshooting voice input issues.
Run this script to check your audio setup before running the voice system.
"""

import os
import sys
import asyncio
from typing import Optional


def check_audio_devices():
    """Check available audio devices."""
    print("=== Audio Device Check ===")
    try:
        import sounddevice as sd

        print("Available audio devices:")
        devices = sd.query_devices()

        if not devices:
            print("❌ No audio devices found!")
            return False

        for i, device in enumerate(devices):
            marker = "📍" if i == sd.default.device[0] else "  "
            print(
                f"{marker} {i}: {device['name']} ({device['max_input_channels']} in, {device['max_output_channels']} out)"
            )

        print(f"\nDefault input device: {sd.default.device[0]}")
        print(f"Default output device: {sd.default.device[1]}")

        return True

    except ImportError:
        print("❌ sounddevice not installed")
        return False
    except Exception as e:
        print(f"❌ Error checking audio devices: {e}")
        return False


def check_picovoice():
    """Check Picovoice setup."""
    print("\n=== Picovoice Check ===")

    access_key = os.getenv("PICOVOICE_ACCESS_KEY")
    if not access_key:
        print("❌ PICOVOICE_ACCESS_KEY not set in environment")
        return False

    try:
        import pvporcupine

        # Try to create a simple porcupine instance
        porcupine = pvporcupine.create(access_key=access_key, keywords=["jarvis"])

        print(f"✅ Picovoice initialized successfully")
        print(f"   Sample rate: {porcupine.sample_rate}")
        print(f"   Frame length: {porcupine.frame_length}")

        porcupine.delete()
        return True

    except ImportError:
        print("❌ pvporcupine not installed")
        return False
    except Exception as e:
        print(f"❌ Picovoice error: {e}")
        return False


def check_openai():
    """Check OpenAI setup."""
    print("\n=== OpenAI Check ===")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set in environment")
        return False

    try:
        import openai

        # Test client creation
        client = openai.AsyncOpenAI(api_key=api_key)
        print("✅ OpenAI client created successfully")
        return True

    except ImportError:
        print("❌ openai package not installed")
        return False
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return False


def check_elevenlabs():
    """Check ElevenLabs setup."""
    print("\n=== ElevenLabs Check ===")

    api_key = os.getenv("ELEVEN_API_KEY")
    if not api_key:
        print("❌ ELEVEN_API_KEY not set in environment")
        return False

    voice_id = os.getenv("ELEVEN_VOICE_ID")
    if not voice_id:
        print("⚠️  ELEVEN_VOICE_ID not set, will use default")
    else:
        print(f"✅ Voice ID: {voice_id}")

    try:
        import httpx

        print("✅ httpx available for ElevenLabs")
        return True
    except ImportError:
        print("❌ httpx not installed")
        return False


async def test_basic_audio():
    """Test basic audio recording."""
    print("\n=== Basic Audio Test ===")

    try:
        import sounddevice as sd
        import numpy as np

        print("Testing basic audio recording for 2 seconds...")

        # Record 2 seconds of audio
        duration = 2  # seconds
        sample_rate = 16000

        audio_data = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()  # Wait until recording is finished

        # Check if we got any data
        if len(audio_data) > 0:
            volume = np.sqrt(np.mean(audio_data**2))
            print(f"✅ Recorded {len(audio_data)} samples")
            print(f"   Average volume: {volume:.4f}")
            if volume > 0.001:
                print("   🎤 Audio input detected!")
            else:
                print("   ⚠️  Very quiet - check microphone")
            return True
        else:
            print("❌ No audio data recorded")
            return False

    except Exception as e:
        print(f"❌ Audio test failed: {e}")
        return False


def check_environment():
    """Check environment variables."""
    print("\n=== Environment Variables ===")

    required_vars = ["OPENAI_API_KEY", "PORCUPINE_API_KEY", "ELEVEN_LABS_API_KEY"]

    optional_vars = ["ELEVEN_VOICE_ID", "PICOVOICE_KEYWORD_PATHS"]

    all_good = True

    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {'*' * len(value[:8])}...")
        else:
            print(f"❌ {var}: Not set")
            all_good = False

    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"⚠️  {var}: Not set (optional)")

    return all_good


async def main():
    """Run all diagnostics."""
    print("🔍 Jarvis Voice System Diagnostics")
    print("=" * 40)

    # Check all components
    env_ok = check_environment()
    audio_ok = check_audio_devices()
    picovoice_ok = check_picovoice()
    openai_ok = check_openai()
    elevenlabs_ok = check_elevenlabs()

    if audio_ok:
        basic_audio_ok = await test_basic_audio()
    else:
        basic_audio_ok = False

    print("\n" + "=" * 40)
    print("📊 Summary:")

    components = [
        ("Environment", env_ok),
        ("Audio Devices", audio_ok),
        ("Basic Audio", basic_audio_ok),
        ("Picovoice", picovoice_ok),
        ("OpenAI", openai_ok),
        ("ElevenLabs", elevenlabs_ok),
    ]

    for name, status in components:
        icon = "✅" if status else "❌"
        print(f"{icon} {name}")

    all_ok = all([status for _, status in components])

    if all_ok:
        print("\n🎉 All systems check! Voice system should work.")
    else:
        print("\n⚠️  Some issues found. Fix the ❌ items above.")

        # Provide specific help
        if not audio_ok:
            print("\n💡 Audio issues:")
            print("   - Check microphone permissions")
            print("   - Try a different audio device")
            print("   - On macOS: System Preferences > Security & Privacy > Microphone")

        if not env_ok:
            print("\n💡 Environment issues:")
            print("   - Create a .env file with your API keys")
            print("   - Or export them as environment variables")


if __name__ == "__main__":
    asyncio.run(main())
