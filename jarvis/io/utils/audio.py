import io
import sounddevice as sd
import soundfile as sf


def play_audio_bytes(audio_bytes: bytes) -> None:
    """Play raw ``audio_bytes`` asynchronously using ``sounddevice``."""
    with sf.SoundFile(io.BytesIO(audio_bytes)) as f:
        data = f.read(dtype="float32")
        sd.play(data, f.samplerate, blocking=False)
