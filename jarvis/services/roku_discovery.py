# jarvis/services/roku_discovery.py
"""Roku device discovery and registry.

Discovers Roku devices on the local network via SSDP (Simple Service
Discovery Protocol), tracks them by serial number, and resolves
user-facing name hints like "bedroom TV" to a specific device IP.

Persistence follows the atomic-write pattern: write to .tmp, then
``os.replace`` into the final path.  Corrupt or missing state files
produce an empty registry rather than an exception.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

import httpx


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RokuDeviceInfo:
    """Immutable-ish snapshot of a Roku device on the network."""

    serial_number: str
    ip_address: str
    device_name: str = ""        # From Roku device-info XML (e.g. "Roku Ultra")
    friendly_name: str = ""      # User-assigned name (e.g. "Bedroom TV")
    model: str = ""
    software_version: str = ""
    last_seen: float = 0.0       # time.time()
    is_online: bool = False

    def to_dict(self) -> dict:
        return {
            "serial_number": self.serial_number,
            "ip_address": self.ip_address,
            "device_name": self.device_name,
            "friendly_name": self.friendly_name,
            "model": self.model,
            "software_version": self.software_version,
            "last_seen": self.last_seen,
            "is_online": self.is_online,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RokuDeviceInfo":
        return cls(
            serial_number=data["serial_number"],
            ip_address=data["ip_address"],
            device_name=data.get("device_name", ""),
            friendly_name=data.get("friendly_name", ""),
            model=data.get("model", ""),
            software_version=data.get("software_version", ""),
            last_seen=data.get("last_seen", 0.0),
            is_online=data.get("is_online", False),
        )


# ---------------------------------------------------------------------------
# SSDP helpers
# ---------------------------------------------------------------------------

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

MSEARCH_PAYLOAD = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    "ST: roku:ecp\r\n"
    "\r\n"
)


class _SSDPProtocol(asyncio.DatagramProtocol):
    """Collects SSDP M-SEARCH responses."""

    def __init__(self) -> None:
        self.locations: List[str] = []
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:  # noqa: ARG002
        try:
            text = data.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.upper().startswith("LOCATION:"):
                    location = line.split(":", 1)[1].strip()
                    if location not in self.locations:
                        self.locations.append(location)
        except Exception:
            pass

    def error_received(self, exc: Exception) -> None:  # pragma: no cover  # noqa: ARG002
        pass


async def _ssdp_search(timeout: float = 5.0) -> List[str]:
    """Send SSDP M-SEARCH for ``roku:ecp`` and return LOCATION URLs."""
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _SSDPProtocol,
        family=socket.AF_INET,
    )
    try:
        transport.sendto(MSEARCH_PAYLOAD.encode(), (SSDP_ADDR, SSDP_PORT))
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return protocol.locations


def _extract_ip_from_location(location: str) -> Optional[str]:
    """Pull the IP address out of a LOCATION URL like ``http://192.168.1.10:8060/``."""
    try:
        # Remove scheme
        after_scheme = location.split("://", 1)[1]
        host_port = after_scheme.split("/", 1)[0]
        host = host_port.split(":")[0]
        return host
    except (IndexError, ValueError):
        return None


async def _fetch_device_info(location: str) -> Optional[RokuDeviceInfo]:
    """GET ``/query/device-info`` from a discovered Roku and parse the XML."""
    base = location.rstrip("/")
    url = f"{base}/query/device-info"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception:
        return None

    try:
        root = ET.fromstring(resp.text)
        info: Dict[str, str] = {}
        for child in root:
            info[child.tag] = child.text or ""

        serial = info.get("serial-number", "").strip()
        if not serial:
            return None

        ip = _extract_ip_from_location(location) or ""

        return RokuDeviceInfo(
            serial_number=serial,
            ip_address=ip,
            device_name=info.get("user-device-name", "") or info.get("friendly-device-name", ""),
            model=info.get("model-name", ""),
            software_version=info.get("software-version", ""),
            last_seen=time.time(),
            is_online=True,
        )
    except ET.ParseError:
        return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class RokuDeviceRegistry:
    """Track and resolve Roku devices across the local network.

    Devices are keyed by ``serial_number``.  The registry persists to
    ``~/.jarvis/roku_devices.json`` using the atomic write pattern.
    """

    STATE_FILE: ClassVar[Path] = Path.home() / ".jarvis" / "roku_devices.json"

    def __init__(self) -> None:
        self.devices: Dict[str, RokuDeviceInfo] = {}
        self.default_serial: Optional[str] = None
        self.last_used_serial: Optional[str] = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Atomic write to disk."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.STATE_FILE.with_suffix(".tmp")
        payload = {
            "devices": {sn: dev.to_dict() for sn, dev in self.devices.items()},
            "default_serial": self.default_serial,
            "last_used_serial": self.last_used_serial,
        }
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(str(tmp), str(self.STATE_FILE))

    @classmethod
    def load(cls) -> "RokuDeviceRegistry":
        """Load from disk.  Returns a fresh empty registry on missing or corrupt file."""
        registry = cls()
        if not cls.STATE_FILE.exists():
            return registry
        try:
            data = json.loads(cls.STATE_FILE.read_text())
            for sn, dev_dict in data.get("devices", {}).items():
                registry.devices[sn] = RokuDeviceInfo.from_dict(dev_dict)
            registry.default_serial = data.get("default_serial")
            registry.last_used_serial = data.get("last_used_serial")
        except (json.JSONDecodeError, KeyError, TypeError):
            return cls()
        return registry

    def clear(self) -> None:
        """Remove all devices, reset defaults, save."""
        self.devices.clear()
        self.default_serial = None
        self.last_used_serial = None
        self.save()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def discover(self, timeout: float = 5.0) -> List[RokuDeviceInfo]:
        """SSDP M-SEARCH for ``roku:ecp``, then fetch device-info.

        Merges results into the registry: existing entries get updated
        IP / online / last_seen while preserving their ``friendly_name``.

        Returns the list of newly discovered devices.
        """
        locations = await _ssdp_search(timeout)

        newly_discovered: List[RokuDeviceInfo] = []
        for loc in locations:
            info = await _fetch_device_info(loc)
            if info is None:
                continue

            existing = self.devices.get(info.serial_number)
            if existing is not None:
                # Merge — preserve user-assigned friendly_name
                existing.ip_address = info.ip_address
                existing.device_name = info.device_name
                existing.model = info.model
                existing.software_version = info.software_version
                existing.last_seen = info.last_seen
                existing.is_online = True
            else:
                self.devices[info.serial_number] = info
                newly_discovered.append(info)

        self.save()
        return newly_discovered

    # ------------------------------------------------------------------
    # Manual registration
    # ------------------------------------------------------------------

    def register_manual(
        self,
        ip: str,
        serial: str,
        device_name: str = "",
        model: str = "",
    ) -> RokuDeviceInfo:
        """Register (or update) a device from environment-variable config.

        Does NOT overwrite ``friendly_name`` if the device already exists
        and has one set.
        """
        existing = self.devices.get(serial)
        if existing is not None:
            existing.ip_address = ip
            if device_name:
                existing.device_name = device_name
            if model:
                existing.model = model
            existing.last_seen = time.time()
            existing.is_online = True
            self.save()
            return existing

        device = RokuDeviceInfo(
            serial_number=serial,
            ip_address=ip,
            device_name=device_name,
            model=model,
            last_seen=time.time(),
            is_online=True,
        )
        self.devices[serial] = device
        self.save()
        return device

    # ------------------------------------------------------------------
    # Setters
    # ------------------------------------------------------------------

    def set_friendly_name(self, serial: str, name: str) -> None:
        """Set the user-facing friendly name for a device and save."""
        if serial in self.devices:
            self.devices[serial].friendly_name = name
            self.save()

    def set_default(self, serial: str) -> None:
        """Designate a device as the default and save."""
        self.default_serial = serial
        self.save()

    def mark_last_used(self, serial: str) -> None:
        """Record the last-used device. Transient — not persisted."""
        self.last_used_serial = serial

    def mark_offline(self, serial: str) -> None:
        """Flag a device as offline."""
        if serial in self.devices:
            self.devices[serial].is_online = False

    def mark_online(self, serial: str, ip: str) -> None:
        """Flag a device as online and update its IP + last_seen."""
        if serial in self.devices:
            dev = self.devices[serial]
            dev.is_online = True
            dev.ip_address = ip
            dev.last_seen = time.time()

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve_device(
        self,
        name_hint: Optional[str] = None,
        preference_hint: Optional[str] = None,
    ) -> Optional[RokuDeviceInfo]:
        """Resolve a human name-hint to a device, cascading through:

        1. Exact ``friendly_name`` match (case-insensitive)
        2. Fuzzy ``friendly_name`` match (substring, case-insensitive)
        3. Exact ``device_name`` match (case-insensitive)
        4. ``preference_hint`` match (friendly_name then device_name)
        5. ``default_serial``
        6. ``last_used_serial``
        7. Only one online device -> return it

        Returns ``None`` when nothing matches.
        """
        if name_hint:
            hint_lower = name_hint.lower()

            # 1 — exact friendly_name
            for dev in self.devices.values():
                if dev.friendly_name.lower() == hint_lower:
                    return dev

            # 2 — fuzzy friendly_name (substring)
            for dev in self.devices.values():
                if hint_lower in dev.friendly_name.lower() and dev.friendly_name:
                    return dev

            # 3 — exact device_name
            for dev in self.devices.values():
                if dev.device_name.lower() == hint_lower:
                    return dev

        # 4 — preference_hint
        if preference_hint:
            pref_lower = preference_hint.lower()
            for dev in self.devices.values():
                if dev.friendly_name and dev.friendly_name.lower() == pref_lower:
                    return dev
            for dev in self.devices.values():
                if dev.device_name and dev.device_name.lower() == pref_lower:
                    return dev

        # 5 — default
        if self.default_serial and self.default_serial in self.devices:
            return self.devices[self.default_serial]

        # 6 — last used
        if self.last_used_serial and self.last_used_serial in self.devices:
            return self.devices[self.last_used_serial]

        # 7 — only one online
        online = self.get_online_devices()
        if len(online) == 1:
            return online[0]

        return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_online_devices(self) -> List[RokuDeviceInfo]:
        """Return all devices currently marked as online."""
        return [d for d in self.devices.values() if d.is_online]

    def get_all_devices(self) -> List[RokuDeviceInfo]:
        """Return every registered device."""
        return list(self.devices.values())

    def get_device_by_serial(self, serial: str) -> Optional[RokuDeviceInfo]:
        """Look up a single device by serial number."""
        return self.devices.get(serial)
