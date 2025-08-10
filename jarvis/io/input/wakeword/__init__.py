from .base import WakeWordListener
from .mock import MockWakeWordListener

from .picovoice import PicovoiceWakeWordListener

if PicovoiceWakeWordListener is None:
    raise RuntimeError(
        "PicovoiceWakeWordListener unavailable. Install pvporcupine/picovoice/sounddevice "
        "and set PICOVOICE_ACCESS_KEY (or PORCUPINE_API_KEY)."
    )


__all__ = ["WakeWordListener", "MockWakeWordListener", "PicovoiceWakeWordListener"]
