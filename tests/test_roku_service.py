"""
Tests for RokuService.

Tests verify:
1. Service initialization (with/without auth)
2. Device information methods (get_device_info, get_active_app, list_apps, search_app)
3. App control (launch_app, launch_app_by_name)
4. Remote control keys (press_key, press_multiple_keys)
5. Playback control (play, pause, rewind, fast_forward, instant_replay)
6. Navigation (home, back, select, navigate with directions)
7. Volume and power (volume_up, volume_down, volume_mute, power_off, power_on)
8. Input switching (switch_input)
9. Search and typing (search, type_character)
10. Player information (get_player_info)
11. Error handling for each method
12. Close method
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.services.roku_service import RokuService


@pytest.fixture
def roku_service():
    """Create a RokuService with a test device IP."""
    return RokuService(device_ip="192.168.1.100")


@pytest.fixture
def roku_service_with_auth():
    """Create a RokuService with authentication."""
    return RokuService(
        device_ip="192.168.1.100",
        username="admin",
        password="secret",
    )


def make_mock_response(status_code=200, text="", raise_for_status=None):
    """Helper to create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if raise_for_status:
        resp.raise_for_status = MagicMock(side_effect=raise_for_status)
    else:
        resp.raise_for_status = MagicMock()
    return resp


class TestRokuServiceInit:
    """Tests for RokuService initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        service = RokuService(device_ip="10.0.0.1")
        assert service.device_ip == "10.0.0.1"
        assert service.base_url == "http://10.0.0.1:8060"
        assert service.username is None
        assert service.password is None

    def test_init_with_auth(self):
        """Test initialization with authentication credentials."""
        service = RokuService(
            device_ip="10.0.0.1",
            username="user",
            password="pass",
        )
        assert service.username == "user"
        assert service.password == "pass"

    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        service = RokuService(device_ip="10.0.0.1", timeout=15.0)
        assert service.client is not None


class TestClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close(self, roku_service):
        """Test that close calls aclose on the client."""
        roku_service.client = AsyncMock()
        roku_service.client.aclose = AsyncMock()

        await roku_service.close()
        roku_service.client.aclose.assert_called_once()


class TestGetDeviceInfo:
    """Tests for get_device_info."""

    @pytest.mark.asyncio
    async def test_get_device_info_success(self, roku_service):
        """Test successful device info retrieval."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <device-info>
            <user-device-name>Living Room Roku</user-device-name>
            <model-name>Roku Ultra</model-name>
            <model-number>4800X</model-number>
            <serial-number>SN12345</serial-number>
            <software-version>11.5.0</software-version>
            <device-id>DEV001</device-id>
            <network-type>wifi</network-type>
            <power-mode>PowerOn</power-mode>
            <supports-ethernet>true</supports-ethernet>
            <supports-wifi-5ghz-band>true</supports-wifi-5ghz-band>
        </device-info>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_device_info()

        assert result["success"] is True
        assert result["device_name"] == "Living Room Roku"
        assert result["model"] == "Roku Ultra"
        assert result["model_number"] == "4800X"
        assert result["serial_number"] == "SN12345"
        assert result["supports_ethernet"] is True
        assert result["supports_wifi"] is True

    @pytest.mark.asyncio
    async def test_get_device_info_uses_friendly_name_fallback(self, roku_service):
        """Test fallback to friendly-device-name when user-device-name missing."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <device-info>
            <friendly-device-name>My Roku</friendly-device-name>
            <model-name>Roku Express</model-name>
        </device-info>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_device_info()

        assert result["success"] is True
        assert result["device_name"] == "My Roku"

    @pytest.mark.asyncio
    async def test_get_device_info_error(self, roku_service):
        """Test device info retrieval with error."""
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await roku_service.get_device_info()

        assert result["success"] is False
        assert "error" in result


class TestGetActiveApp:
    """Tests for get_active_app."""

    @pytest.mark.asyncio
    async def test_get_active_app_with_app(self, roku_service):
        """Test getting active app when an app is running."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <active-app>
            <app id="12345" version="4.5.6">Netflix</app>
        </active-app>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_active_app()

        assert result["success"] is True
        assert result["app_id"] == "12345"
        assert result["app_name"] == "Netflix"
        assert result["version"] == "4.5.6"

    @pytest.mark.asyncio
    async def test_get_active_app_home_screen(self, roku_service):
        """Test getting active app when on home screen."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <active-app>
        </active-app>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_active_app()

        assert result["success"] is True
        assert result["app_name"] == "Home Screen"

    @pytest.mark.asyncio
    async def test_get_active_app_error(self, roku_service):
        """Test getting active app with error."""
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(side_effect=Exception("Network error"))

        result = await roku_service.get_active_app()

        assert result["success"] is False


class TestListApps:
    """Tests for list_apps."""

    @pytest.mark.asyncio
    async def test_list_apps_success(self, roku_service):
        """Test successful app listing."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps>
            <app id="12345" type="appl" version="4.5">Netflix</app>
            <app id="67890" type="appl" version="1.0">YouTube</app>
            <app id="11111" type="appl" version="2.3">Hulu</app>
        </apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.list_apps()

        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["apps"]) == 3
        assert result["apps"][0]["id"] == "12345"
        assert result["apps"][0]["name"] == "Netflix"

    @pytest.mark.asyncio
    async def test_list_apps_empty(self, roku_service):
        """Test listing with no apps installed."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps></apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.list_apps()

        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_apps_error(self, roku_service):
        """Test listing apps with error."""
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(side_effect=Exception("Failed"))

        result = await roku_service.list_apps()

        assert result["success"] is False


class TestSearchApp:
    """Tests for search_app."""

    @pytest.mark.asyncio
    async def test_search_app_found(self, roku_service):
        """Test searching for an app that exists."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps>
            <app id="12345" type="appl" version="4.5">Netflix</app>
            <app id="67890" type="appl" version="1.0">YouTube</app>
        </apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.search_app("netflix")
        assert result == "12345"

    @pytest.mark.asyncio
    async def test_search_app_case_insensitive(self, roku_service):
        """Test that search is case-insensitive."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps>
            <app id="12345" type="appl" version="4.5">Netflix</app>
        </apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.search_app("NETFLIX")
        assert result == "12345"

    @pytest.mark.asyncio
    async def test_search_app_partial_match(self, roku_service):
        """Test searching with partial name match."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps>
            <app id="12345" type="appl" version="4.5">Netflix</app>
        </apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.search_app("net")
        assert result == "12345"

    @pytest.mark.asyncio
    async def test_search_app_not_found(self, roku_service):
        """Test searching for an app that does not exist."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps>
            <app id="12345" type="appl" version="4.5">Netflix</app>
        </apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.search_app("Disney+")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_app_list_fails(self, roku_service):
        """Test searching when list_apps fails."""
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(side_effect=Exception("Failed"))

        result = await roku_service.search_app("Netflix")
        assert result is None


class TestLaunchApp:
    """Tests for launch_app and launch_app_by_name."""

    @pytest.mark.asyncio
    async def test_launch_app_success(self, roku_service):
        """Test launching an app by ID."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.launch_app("12345")

        assert result["success"] is True
        assert "12345" in result["message"]

    @pytest.mark.asyncio
    async def test_launch_app_error(self, roku_service):
        """Test launching an app with error."""
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(side_effect=Exception("Failed"))

        result = await roku_service.launch_app("12345")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_launch_app_by_name_success(self, roku_service):
        """Test launching an app by name."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps>
            <app id="12345" type="appl" version="4.5">Netflix</app>
        </apps>"""

        get_response = make_mock_response(text=xml_response)
        post_response = make_mock_response()

        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=get_response)
        roku_service.client.post = AsyncMock(return_value=post_response)

        result = await roku_service.launch_app_by_name("Netflix")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_launch_app_by_name_not_found(self, roku_service):
        """Test launching an app by name when not found."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <apps></apps>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.launch_app_by_name("NonExistent")

        assert result["success"] is False
        assert "not found" in result["error"]


class TestPressKey:
    """Tests for press_key and press_multiple_keys."""

    @pytest.mark.asyncio
    async def test_press_key_success(self, roku_service):
        """Test pressing a single key."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.press_key("Home")

        assert result["success"] is True
        assert "Home" in result["message"]

    @pytest.mark.asyncio
    async def test_press_key_error(self, roku_service):
        """Test pressing a key with error."""
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(side_effect=Exception("Failed"))

        result = await roku_service.press_key("Home")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_press_multiple_keys_success(self, roku_service):
        """Test pressing multiple keys in sequence."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.press_multiple_keys(
            ["Up", "Down", "Select"], delay_ms=0
        )

        assert result["success"] is True
        assert result["message"] == "Pressed 3 keys"
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_press_multiple_keys_partial_failure(self, roku_service):
        """Test pressing multiple keys where one fails."""
        success_response = make_mock_response()

        call_count = 0

        async def mock_post(url):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Key failed")
            return success_response

        roku_service.client = AsyncMock()
        roku_service.client.post = mock_post

        result = await roku_service.press_multiple_keys(
            ["Up", "Down", "Select"], delay_ms=0
        )

        assert result["success"] is False


class TestPlaybackControl:
    """Tests for playback control methods."""

    @pytest.mark.asyncio
    async def test_play(self, roku_service):
        """Test play method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.play()
        assert result["success"] is True
        assert "Play" in result["message"]

    @pytest.mark.asyncio
    async def test_pause(self, roku_service):
        """Test pause method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.pause()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_rewind(self, roku_service):
        """Test rewind method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.rewind()
        assert result["success"] is True
        assert "Rev" in result["message"]

    @pytest.mark.asyncio
    async def test_fast_forward(self, roku_service):
        """Test fast forward method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.fast_forward()
        assert result["success"] is True
        assert "Fwd" in result["message"]

    @pytest.mark.asyncio
    async def test_instant_replay(self, roku_service):
        """Test instant replay method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.instant_replay()
        assert result["success"] is True
        assert "InstantReplay" in result["message"]


class TestNavigation:
    """Tests for navigation methods."""

    @pytest.mark.asyncio
    async def test_home(self, roku_service):
        """Test home method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.home()
        assert result["success"] is True
        assert "Home" in result["message"]

    @pytest.mark.asyncio
    async def test_back(self, roku_service):
        """Test back method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.back()
        assert result["success"] is True
        assert "Back" in result["message"]

    @pytest.mark.asyncio
    async def test_select(self, roku_service):
        """Test select method."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.select()
        assert result["success"] is True
        assert "Select" in result["message"]

    @pytest.mark.asyncio
    async def test_navigate_valid_directions(self, roku_service):
        """Test navigate method with valid directions."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        for direction in ["up", "down", "left", "right"]:
            result = await roku_service.navigate(direction)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_navigate_case_insensitive(self, roku_service):
        """Test navigate method is case-insensitive."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.navigate("UP")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_navigate_invalid_direction(self, roku_service):
        """Test navigate method with invalid direction."""
        result = await roku_service.navigate("diagonal")
        assert result["success"] is False
        assert "Invalid direction" in result["error"]


class TestVolumeAndPower:
    """Tests for volume and power methods."""

    @pytest.mark.asyncio
    async def test_volume_up(self, roku_service):
        """Test volume up."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.volume_up()
        assert result["success"] is True
        assert "VolumeUp" in result["message"]

    @pytest.mark.asyncio
    async def test_volume_down(self, roku_service):
        """Test volume down."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.volume_down()
        assert result["success"] is True
        assert "VolumeDown" in result["message"]

    @pytest.mark.asyncio
    async def test_volume_mute(self, roku_service):
        """Test volume mute."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.volume_mute()
        assert result["success"] is True
        assert "VolumeMute" in result["message"]

    @pytest.mark.asyncio
    async def test_power_off(self, roku_service):
        """Test power off."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.power_off()
        assert result["success"] is True
        assert "PowerOff" in result["message"]

    @pytest.mark.asyncio
    async def test_power_on(self, roku_service):
        """Test power on."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.power_on()
        assert result["success"] is True
        assert "PowerOn" in result["message"]


class TestInputSwitching:
    """Tests for input switching."""

    @pytest.mark.asyncio
    async def test_switch_input_hdmi1(self, roku_service):
        """Test switching to HDMI1."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.switch_input("HDMI1")
        assert result["success"] is True
        assert "InputHDMI1" in result["message"]

    @pytest.mark.asyncio
    async def test_switch_input_tuner(self, roku_service):
        """Test switching to Tuner."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.switch_input("Tuner")
        assert result["success"] is True


class TestTypeCharacter:
    """Tests for type_character."""

    @pytest.mark.asyncio
    async def test_type_character_success(self, roku_service):
        """Test typing a single character."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.type_character("a")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_type_character_special_char(self, roku_service):
        """Test typing a special character that needs URL encoding."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        result = await roku_service.type_character(" ")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_type_character_error(self, roku_service):
        """Test typing a character with error."""
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(side_effect=Exception("Failed"))

        result = await roku_service.type_character("a")
        assert result["success"] is False


class TestSearch:
    """Tests for search method."""

    @pytest.mark.asyncio
    async def test_search_success(self, roku_service):
        """Test search opens search and types query."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await roku_service.search("hello")

        assert result["success"] is True
        assert "hello" in result["message"]

    @pytest.mark.asyncio
    async def test_search_error_when_exception_propagates(self, roku_service):
        """Test search when an unhandled exception propagates from asyncio.sleep."""
        mock_response = make_mock_response()
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(return_value=mock_response)

        async def bad_sleep(duration):
            raise RuntimeError("Unexpected error during search")

        with patch("asyncio.sleep", side_effect=bad_sleep):
            result = await roku_service.search("test")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_search_continues_when_individual_keys_fail(self, roku_service):
        """Test that search returns success even if individual press_key calls fail internally.

        This tests the current behavior: press_key catches exceptions
        and returns a dict, so the search method never sees the error.
        """
        roku_service.client = AsyncMock()
        roku_service.client.post = AsyncMock(side_effect=Exception("Failed"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await roku_service.search("ab")

        # Current behavior: search completes successfully even though key presses fail
        # because press_key/type_character catch their own exceptions
        assert result["success"] is True


class TestGetPlayerInfo:
    """Tests for get_player_info."""

    @pytest.mark.asyncio
    async def test_get_player_info_playing(self, roku_service):
        """Test getting player info when playing."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <player state="play" error="false">
            <plugin id="12345" name="Netflix" bandwidth="5000kbps"/>
            <format audio="aac" video="h264" captions="srt"/>
            <position>120000 ms</position>
            <duration>3600000 ms</duration>
        </player>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_player_info()

        assert result["success"] is True
        assert result["state"] == "play"
        assert result["error"] is False
        assert result["plugin_id"] == "12345"
        assert result["plugin_name"] == "Netflix"
        assert result["audio"] == "aac"
        assert result["video"] == "h264"
        assert result["position_ms"] == 120000
        assert result["duration_ms"] == 3600000

    @pytest.mark.asyncio
    async def test_get_player_info_paused(self, roku_service):
        """Test getting player info when paused."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <player state="pause" error="false">
            <position>60000ms</position>
            <duration>1800000ms</duration>
        </player>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_player_info()

        assert result["success"] is True
        assert result["state"] == "pause"
        assert result["position_ms"] == 60000
        assert result["duration_ms"] == 1800000

    @pytest.mark.asyncio
    async def test_get_player_info_closed(self, roku_service):
        """Test getting player info when no player active."""
        xml_response = """<?xml version="1.0" encoding="UTF-8" ?>
        <player state="close" error="false">
        </player>"""

        mock_response = make_mock_response(text=xml_response)
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(return_value=mock_response)

        result = await roku_service.get_player_info()

        assert result["success"] is True
        assert result["state"] == "close"

    @pytest.mark.asyncio
    async def test_get_player_info_error(self, roku_service):
        """Test getting player info with error."""
        roku_service.client = AsyncMock()
        roku_service.client.get = AsyncMock(side_effect=Exception("Failed"))

        result = await roku_service.get_player_info()

        assert result["success"] is False
