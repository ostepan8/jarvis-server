"""Tests for RokuDeviceRegistry and RokuDeviceInfo.

Covers:
- Empty registry creation
- Manual registration (create + update + friendly_name preservation)
- Persistence round-trip (save / load)
- Persistence edge-cases (corrupt file, missing file)
- Friendly name and default setters
- Online / offline toggling
- Device resolution cascade (exact, fuzzy, device_name, preference, default,
  last_used, single-online, no match)
- Clear registry
- SSDP discovery with mocked UDP + httpx
- Merge-on-rediscovery preserves friendly_name
"""

from __future__ import annotations

import socket
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from jarvis.services.roku_discovery import (
    RokuDeviceInfo,
    RokuDeviceRegistry,
    _SSDPProtocol,
    _decode_xml_bytes,
    _extract_ip_from_location,
    _fetch_device_info,
    _ssdp_search,
    normalize_for_match,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def registry(tmp_path: Path, monkeypatch):
    """Return a fresh RokuDeviceRegistry whose STATE_FILE lives in tmp_path."""
    state_file = tmp_path / "roku_devices.json"
    monkeypatch.setattr(RokuDeviceRegistry, "STATE_FILE", state_file)
    return RokuDeviceRegistry()


DEVICE_INFO_XML = """\
<?xml version="1.0" encoding="UTF-8" ?>
<device-info>
    <serial-number>{serial}</serial-number>
    <user-device-name>{device_name}</user-device-name>
    <model-name>{model}</model-name>
    <software-version>{sw_version}</software-version>
</device-info>
"""


# ---------------------------------------------------------------------------
# Basic creation
# ---------------------------------------------------------------------------

class TestEmptyRegistry:

    def test_empty_registry_creation(self, registry: RokuDeviceRegistry):
        """A fresh registry starts with zero devices and no defaults."""
        assert len(registry.devices) == 0
        assert registry.default_serial is None
        assert registry.last_used_serial is None


# ---------------------------------------------------------------------------
# Manual registration
# ---------------------------------------------------------------------------

class TestManualRegistration:

    def test_register_manual_creates_device(self, registry: RokuDeviceRegistry):
        """register_manual should produce a properly populated RokuDeviceInfo."""
        dev = registry.register_manual(
            ip="192.168.1.50",
            serial="ABC123",
            device_name="Roku Express",
            model="3930X",
        )
        assert dev.serial_number == "ABC123"
        assert dev.ip_address == "192.168.1.50"
        assert dev.device_name == "Roku Express"
        assert dev.model == "3930X"
        assert dev.is_online is True
        assert dev.last_seen > 0
        assert "ABC123" in registry.devices

    def test_register_manual_preserves_friendly_name(self, registry: RokuDeviceRegistry):
        """Re-registering the same serial must not clobber a user-assigned friendly_name."""
        registry.register_manual(ip="192.168.1.50", serial="ABC123")
        registry.set_friendly_name("ABC123", "Living Room")

        # Second registration — should update IP but keep friendly_name
        dev = registry.register_manual(
            ip="192.168.1.99",
            serial="ABC123",
            device_name="Roku Ultra",
        )
        assert dev.ip_address == "192.168.1.99"
        assert dev.friendly_name == "Living Room"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:

    def test_persistence_round_trip(self, registry: RokuDeviceRegistry):
        """Saving then loading should reproduce all fields faithfully."""
        registry.register_manual(ip="10.0.0.1", serial="S1", device_name="Roku Express", model="3930")
        registry.set_friendly_name("S1", "Kitchen")
        registry.set_default("S1")
        registry.last_used_serial = "S1"
        registry.save()

        loaded = RokuDeviceRegistry.load()

        assert "S1" in loaded.devices
        dev = loaded.devices["S1"]
        assert dev.ip_address == "10.0.0.1"
        assert dev.device_name == "Roku Express"
        assert dev.model == "3930"
        assert dev.friendly_name == "Kitchen"
        assert loaded.default_serial == "S1"
        assert loaded.last_used_serial == "S1"

    def test_persistence_corrupt_file(self, registry: RokuDeviceRegistry):
        """Corrupt JSON on disk should yield an empty registry, not an explosion."""
        RokuDeviceRegistry.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RokuDeviceRegistry.STATE_FILE.write_text("{{{not json at all")

        loaded = RokuDeviceRegistry.load()

        assert len(loaded.devices) == 0
        assert loaded.default_serial is None

    def test_persistence_missing_file(self, registry: RokuDeviceRegistry):
        """No file at all should produce an empty registry."""
        loaded = RokuDeviceRegistry.load()
        assert len(loaded.devices) == 0


# ---------------------------------------------------------------------------
# Setters
# ---------------------------------------------------------------------------

class TestSetters:

    def test_set_friendly_name(self, registry: RokuDeviceRegistry):
        """set_friendly_name should persist through a save/load cycle."""
        registry.register_manual(ip="10.0.0.1", serial="SN1")
        registry.set_friendly_name("SN1", "Bedroom TV")

        loaded = RokuDeviceRegistry.load()
        assert loaded.devices["SN1"].friendly_name == "Bedroom TV"

    def test_set_default(self, registry: RokuDeviceRegistry):
        """The default serial should resolve when no name_hint is given."""
        registry.register_manual(ip="10.0.0.1", serial="SN1")
        registry.register_manual(ip="10.0.0.2", serial="SN2")
        registry.set_default("SN2")

        result = registry.resolve_device()
        assert result is not None
        assert result.serial_number == "SN2"

    def test_mark_last_used(self, registry: RokuDeviceRegistry):
        """mark_last_used should update the transient last_used_serial field."""
        registry.register_manual(ip="10.0.0.1", serial="SN1")
        registry.mark_last_used("SN1")
        assert registry.last_used_serial == "SN1"


# ---------------------------------------------------------------------------
# Online / offline toggling
# ---------------------------------------------------------------------------

class TestOnlineOffline:

    def test_mark_online_offline(self, registry: RokuDeviceRegistry):
        """Toggling online/offline should update the device state."""
        registry.register_manual(ip="10.0.0.1", serial="SN1")
        assert registry.devices["SN1"].is_online is True

        registry.mark_offline("SN1")
        assert registry.devices["SN1"].is_online is False

        registry.mark_online("SN1", "10.0.0.99")
        dev = registry.devices["SN1"]
        assert dev.is_online is True
        assert dev.ip_address == "10.0.0.99"
        assert dev.last_seen > 0


# ---------------------------------------------------------------------------
# Resolution cascade
# ---------------------------------------------------------------------------

class TestResolveDevice:

    def _seed_registry(self, registry: RokuDeviceRegistry) -> None:
        """Plant a few devices for resolution tests."""
        registry.register_manual(ip="10.0.0.1", serial="SN1", device_name="Roku Ultra")
        registry.set_friendly_name("SN1", "Living Room")

        registry.register_manual(ip="10.0.0.2", serial="SN2", device_name="Roku Express")
        registry.set_friendly_name("SN2", "Bedroom TV")

        registry.register_manual(ip="10.0.0.3", serial="SN3", device_name="Roku Stick")
        # SN3 has no friendly_name

    def test_resolve_exact_friendly_name(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        result = registry.resolve_device(name_hint="Living Room")
        assert result is not None
        assert result.serial_number == "SN1"

    def test_resolve_exact_friendly_name_case_insensitive(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        result = registry.resolve_device(name_hint="living room")
        assert result is not None
        assert result.serial_number == "SN1"

    def test_resolve_fuzzy_friendly_name(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        result = registry.resolve_device(name_hint="bedroom")
        assert result is not None
        assert result.serial_number == "SN2"

    def test_resolve_device_name(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        result = registry.resolve_device(name_hint="Roku Stick")
        assert result is not None
        assert result.serial_number == "SN3"

    def test_resolve_preference_hint(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        result = registry.resolve_device(preference_hint="Bedroom TV")
        assert result is not None
        assert result.serial_number == "SN2"

    def test_resolve_default_serial(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        registry.set_default("SN3")
        result = registry.resolve_device()
        assert result is not None
        assert result.serial_number == "SN3"

    def test_resolve_last_used(self, registry: RokuDeviceRegistry):
        self._seed_registry(registry)
        registry.mark_last_used("SN2")
        # No default set, no name_hint — should fall through to last_used
        result = registry.resolve_device()
        assert result is not None
        assert result.serial_number == "SN2"

    def test_resolve_only_one_online(self, registry: RokuDeviceRegistry):
        """When exactly one device is online and no other hint applies, return it."""
        registry.register_manual(ip="10.0.0.1", serial="SN1")
        registry.register_manual(ip="10.0.0.2", serial="SN2")
        registry.mark_offline("SN1")
        # SN2 is still online
        result = registry.resolve_device()
        assert result is not None
        assert result.serial_number == "SN2"

    def test_resolve_no_match(self, registry: RokuDeviceRegistry):
        """Nothing matches when the registry is empty."""
        result = registry.resolve_device(name_hint="phantom")
        assert result is None


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:

    def test_clear_registry(self, registry: RokuDeviceRegistry):
        """clear() should nuke everything and persist the empty state."""
        registry.register_manual(ip="10.0.0.1", serial="SN1")
        registry.set_default("SN1")
        registry.mark_last_used("SN1")

        registry.clear()

        assert len(registry.devices) == 0
        assert registry.default_serial is None
        assert registry.last_used_serial is None

        # Reload from disk — should also be empty
        loaded = RokuDeviceRegistry.load()
        assert len(loaded.devices) == 0


# ---------------------------------------------------------------------------
# SSDP discovery (mocked)
# ---------------------------------------------------------------------------

class TestDiscovery:

    @pytest.mark.asyncio
    async def test_discover_ssdp_mocked(self, registry: RokuDeviceRegistry):
        """Mock the UDP layer and httpx to verify the full discover() flow."""
        # Mock _ssdp_search to return a fake location
        with patch(
            "jarvis.services.roku_discovery._ssdp_search",
            new_callable=AsyncMock,
            return_value=["http://192.168.1.42:8060/"],
        ):
            # Mock _fetch_device_info to return a parsed device
            mock_device = RokuDeviceInfo(
                serial_number="DISC001",
                ip_address="192.168.1.42",
                device_name="Roku Ultra",
                model="4800X",
                software_version="11.5.0",
                last_seen=time.time(),
                is_online=True,
            )
            with patch(
                "jarvis.services.roku_discovery._fetch_device_info",
                new_callable=AsyncMock,
                return_value=mock_device,
            ):
                newly = await registry.discover(timeout=0.1)

        assert len(newly) == 1
        assert newly[0].serial_number == "DISC001"
        assert "DISC001" in registry.devices
        assert registry.devices["DISC001"].ip_address == "192.168.1.42"
        assert registry.devices["DISC001"].is_online is True

    @pytest.mark.asyncio
    async def test_merge_preserves_friendly_names(self, registry: RokuDeviceRegistry):
        """Re-discovering an already-known device must keep its friendly_name."""
        # Pre-register with a friendly name
        registry.register_manual(ip="192.168.1.42", serial="DISC001", device_name="Roku Ultra")
        registry.set_friendly_name("DISC001", "Den TV")

        rediscovered = RokuDeviceInfo(
            serial_number="DISC001",
            ip_address="192.168.1.99",
            device_name="Roku Ultra",
            model="4800X",
            software_version="12.0.0",
            last_seen=time.time(),
            is_online=True,
        )

        with patch(
            "jarvis.services.roku_discovery._ssdp_search",
            new_callable=AsyncMock,
            return_value=["http://192.168.1.99:8060/"],
        ), patch(
            "jarvis.services.roku_discovery._fetch_device_info",
            new_callable=AsyncMock,
            return_value=rediscovered,
        ):
            newly = await registry.discover(timeout=0.1)

        # Not "newly discovered" — it was already registered
        assert len(newly) == 0
        dev = registry.devices["DISC001"]
        assert dev.friendly_name == "Den TV"
        assert dev.ip_address == "192.168.1.99"
        assert dev.software_version == "12.0.0"


# ---------------------------------------------------------------------------
# Internal helpers — bonus coverage
# ---------------------------------------------------------------------------

class TestSSDPProtocol:

    def test_datagram_received_parses_location(self):
        """_SSDPProtocol should capture LOCATION headers from response data."""
        proto = _SSDPProtocol()
        proto.connection_made(MagicMock())

        ssdp_response = (
            "HTTP/1.1 200 OK\r\n"
            "LOCATION: http://192.168.1.10:8060/\r\n"
            "ST: roku:ecp\r\n"
            "\r\n"
        )
        proto.datagram_received(ssdp_response.encode(), ("192.168.1.10", 1900))

        assert "http://192.168.1.10:8060/" in proto.locations

    def test_duplicate_locations_ignored(self):
        """Same LOCATION appearing twice should only be stored once."""
        proto = _SSDPProtocol()
        proto.connection_made(MagicMock())

        data = b"HTTP/1.1 200 OK\r\nLOCATION: http://10.0.0.1:8060/\r\n\r\n"
        proto.datagram_received(data, ("10.0.0.1", 1900))
        proto.datagram_received(data, ("10.0.0.1", 1900))

        assert len(proto.locations) == 1


class TestSSDPSearchAddressFamily:
    """Regression tests for the SSDP search address family bug.

    macOS can default to AF_INET6 when family=0, but SSDP multicast
    (239.255.255.250) is IPv4-only.  Sending to an IPv4 multicast
    address on an IPv6 socket raises "unexpected address family."
    """

    @pytest.mark.asyncio
    async def test_ssdp_search_uses_af_inet(self):
        """_ssdp_search must request AF_INET to avoid IPv6 mismatch."""
        captured_kwargs = {}

        async def fake_create_datagram_endpoint(factory, **kwargs):
            captured_kwargs.update(kwargs)
            transport = MagicMock()
            transport.sendto = MagicMock()
            transport.close = MagicMock()
            protocol = factory()
            protocol.connection_made(transport)
            return transport, protocol

        mock_loop = MagicMock()
        mock_loop.create_datagram_endpoint = fake_create_datagram_endpoint

        with patch("asyncio.get_running_loop", return_value=mock_loop), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await _ssdp_search(timeout=0.01)

        assert captured_kwargs.get("family") == socket.AF_INET, (
            "SSDP search must use AF_INET — IPv6 sockets cannot send to "
            "239.255.255.250 and will raise 'unexpected address family'"
        )

    @pytest.mark.asyncio
    async def test_ssdp_search_sends_to_multicast_address(self):
        """The M-SEARCH packet must target the SSDP multicast address on port 1900."""
        sent_args = []

        async def fake_create_datagram_endpoint(factory, **kwargs):
            transport = MagicMock()
            transport.sendto = lambda data, addr: sent_args.append((data, addr))
            transport.close = MagicMock()
            protocol = factory()
            protocol.connection_made(transport)
            return transport, protocol

        mock_loop = MagicMock()
        mock_loop.create_datagram_endpoint = fake_create_datagram_endpoint

        with patch("asyncio.get_running_loop", return_value=mock_loop), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await _ssdp_search(timeout=0.01)

        assert len(sent_args) == 1
        _data, (host, port) = sent_args[0]
        assert host == "239.255.255.250"
        assert port == 1900


class TestExtractIpFromLocation:

    def test_standard_roku_location(self):
        assert _extract_ip_from_location("http://192.168.1.10:8060/") == "192.168.1.10"

    def test_no_trailing_slash(self):
        assert _extract_ip_from_location("http://10.0.0.5:8060") == "10.0.0.5"

    def test_with_path(self):
        assert _extract_ip_from_location("http://172.16.0.1:8060/query/device-info") == "172.16.0.1"

    def test_garbage_returns_none(self):
        assert _extract_ip_from_location("not-a-url") is None


class TestFetchDeviceInfo:

    @pytest.mark.asyncio
    async def test_fetch_device_info_success(self):
        """_fetch_device_info should parse XML and return a RokuDeviceInfo."""
        xml = DEVICE_INFO_XML.format(
            serial="XYZ789",
            device_name="Test Roku",
            model="TestModel",
            sw_version="1.0.0",
        )
        mock_resp = MagicMock()
        mock_resp.content = xml.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()

        with patch("jarvis.services.roku_discovery.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _fetch_device_info("http://192.168.1.5:8060/")

        assert result is not None
        assert result.serial_number == "XYZ789"
        assert result.device_name == "Test Roku"
        assert result.ip_address == "192.168.1.5"

    @pytest.mark.asyncio
    async def test_fetch_device_info_network_error(self):
        """Network errors should yield None, not an exception."""
        with patch("jarvis.services.roku_discovery.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _fetch_device_info("http://192.168.1.5:8060/")

        assert result is None


# ---------------------------------------------------------------------------
# Unicode / encoding helpers
# ---------------------------------------------------------------------------


class TestDecodeXmlBytes:

    def test_utf8_smart_quote(self):
        """UTF-8 encoded smart quotes should decode correctly."""
        raw = "Owen\u2019s Roku".encode("utf-8")
        assert _decode_xml_bytes(raw) == "Owen\u2019s Roku"

    def test_latin1_fallback(self):
        """Bytes invalid in UTF-8 but valid in Latin-1 should decode via fallback."""
        # \x92 is RIGHT SINGLE QUOTATION MARK in Windows-1252 / displayable in Latin-1
        raw = b"Owen\x92s Roku"
        result = _decode_xml_bytes(raw)
        # Latin-1 maps \x92 to U+0092 (a control character), but it shouldn't crash
        assert "Owen" in result
        assert "Roku" in result

    def test_pure_ascii(self):
        assert _decode_xml_bytes(b"Roku Ultra") == "Roku Ultra"


class TestNormalizeForMatch:

    def test_smart_quote_matches_ascii(self):
        """'Owen\u2019s' and 'Owen's' should normalize to the same string."""
        assert normalize_for_match("Owen\u2019s Roku") == normalize_for_match("Owen's Roku")

    def test_replacement_chars_stripped(self):
        """U+FFFD replacement characters should be stripped for matching."""
        assert normalize_for_match("Owen\ufffds Roku") == normalize_for_match("Owens Roku")

    def test_replacement_chars_match_ascii_apostrophe(self):
        """The actual bug: Roku sends U+FFFD chars where an apostrophe was.

        'Owen\\ufffd\\ufffd\\ufffds Roku' (garbled encoding) must match
        'Owen's Roku' (what the user types).  Both should converge to
        'owens roku' after stripping FFFD and apostrophes.
        """
        assert normalize_for_match("Owen\ufffd\ufffd\ufffds Roku") == normalize_for_match("Owen's Roku")

    def test_case_insensitive(self):
        assert normalize_for_match("LIVING ROOM") == normalize_for_match("living room")

    def test_accented_characters(self):
        """Accented characters should normalize for matching."""
        assert normalize_for_match("café") == normalize_for_match("cafe")


class TestFetchDeviceInfoEncoding:

    @pytest.mark.asyncio
    async def test_smart_quote_in_device_name(self):
        """Device names with smart quotes should be preserved, not mangled."""
        xml = DEVICE_INFO_XML.format(
            serial="SQ001",
            device_name="Owen\u2019s Roku",
            model="TestModel",
            sw_version="1.0.0",
        )
        mock_resp = MagicMock()
        mock_resp.content = xml.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()

        with patch("jarvis.services.roku_discovery.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await _fetch_device_info("http://192.168.1.5:8060/")

        assert result is not None
        assert "\ufffd" not in result.device_name
        assert "\u2019" in result.device_name or "'" in result.device_name
