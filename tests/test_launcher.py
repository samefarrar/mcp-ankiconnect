"""Auto-launch: open Anki when nothing listens on AnkiConnect's port.

The subprocess and the `version` probe are faked, so these tests need no Anki.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_ankiconnect.ankiconnect_client import (
    AnkiAction,
    AnkiConnectClient,
    AnkiConnectionError,
)
from mcp_ankiconnect.launcher import (
    AnkiLauncher,
    LaunchSettings,
    launch_command,
    parse_bool,
)
from mcp_ankiconnect.server import handle_anki_connection_error

URL = "http://localhost:8765"


class FakeClock:
    """Monotonic clock that only moves when the fake sleep is awaited."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


class FakeProcess:
    """Stands in for subprocess.Popen: running unless given a return code."""

    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


class FakeAnki:
    """Answers `version` once `ready_after` probes have been refused."""

    def __init__(self, ready_after: int | None) -> None:
        self.ready_after = ready_after
        self.probes = 0
        self.spawned: list[list[str]] = []

    async def probe(self, base_url: str) -> bool:
        self.probes += 1
        if not self.spawned or self.ready_after is None:
            return False
        return self.probes > self.ready_after

    def spawn(self, command: list[str]) -> FakeProcess:
        self.spawned.append(command)
        return FakeProcess()


def make_launcher(anki: FakeAnki, clock: FakeClock, **overrides) -> AnkiLauncher:
    settings = LaunchSettings(
        enabled=overrides.pop("enabled", True),
        timeout=overrides.pop("timeout", 30.0),
        platform=overrides.pop("platform", "darwin"),
        **overrides,
    )
    return AnkiLauncher(
        settings,
        spawn=anki.spawn,
        probe=anki.probe,
        clock=clock,
        sleep=clock.sleep,
    )


def refused_then_ok(result=6):
    """httpx.post side effect: refused once, then a normal AnkiConnect reply."""
    ok = MagicMock(spec=httpx.Response)
    ok.raise_for_status = MagicMock()
    ok.json.return_value = {"result": result, "error": None}
    return [httpx.ConnectError("[Errno 61] Connection refused"), ok]


# --- env parsing -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, True),
        ("", True),
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("FALSE", False),
        (" 0 ", False),
        ("no", False),
        ("off", False),
        # A plugin host that leaves the placeholder unexpanded keeps the default.
        ("${user_config.auto_launch_anki}", True),
    ],
)
def test_parse_bool(raw, expected):
    assert parse_bool(raw, default=True) is expected


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("ANKI_AUTO_LAUNCH", "false")
    monkeypatch.setenv("ANKI_LAUNCH_TIMEOUT", "12")
    monkeypatch.setenv("ANKI_APP_PATH", "/Applications/Anki 2.app")
    settings = LaunchSettings.from_env()
    assert settings.enabled is False
    assert settings.timeout == 12.0
    assert settings.app == "/Applications/Anki 2.app"


def test_settings_from_env_defaults(monkeypatch):
    for name in ("ANKI_AUTO_LAUNCH", "ANKI_LAUNCH_TIMEOUT", "ANKI_APP_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANKI_LAUNCH_TIMEOUT", "not a number")
    settings = LaunchSettings.from_env()
    assert settings.enabled is True
    assert settings.timeout == 30.0
    assert settings.app is None


def test_launch_commands_per_platform():
    assert launch_command(LaunchSettings(platform="darwin")) == [
        "open", "-g", "-a", "Anki",
    ]
    mac_custom = LaunchSettings(platform="darwin", app="/Apps/Anki.app")
    assert launch_command(mac_custom) == ["open", "-g", "-a", "/Apps/Anki.app"]
    assert launch_command(LaunchSettings(platform="linux")) == ["anki"]
    linux_custom = LaunchSettings(platform="linux", app="/opt/anki/bin/anki")
    assert launch_command(linux_custom) == ["/opt/anki/bin/anki"]
    assert launch_command(LaunchSettings(platform="win32"))[0].endswith("anki.exe")


# --- launcher --------------------------------------------------------------


async def test_recover_launches_and_records_note():
    # Probe 1 (before launching) and 2 are refused, probe 3 answers: 2 polls.
    anki, clock = FakeAnki(ready_after=2), FakeClock()
    launcher = make_launcher(anki, clock)
    with launcher.capture_notes() as notes:
        assert await launcher.recover(URL) is True
    assert anki.spawned == [["open", "-g", "-a", "Anki"]]
    assert len(notes) == 1
    assert notes[0].startswith("NOTE: Anki was closed, so I opened it")
    assert "took 1 s" in notes[0]


async def test_recover_disabled_says_how_to_enable():
    anki, clock = FakeAnki(ready_after=0), FakeClock()
    launcher = make_launcher(anki, clock, enabled=False)
    with pytest.raises(AnkiConnectionError) as excinfo:
        await launcher.recover(URL)
    assert anki.spawned == []
    message = str(excinfo.value)
    assert "closed" in message
    assert "ANKI_AUTO_LAUNCH" in message


async def test_recover_skips_remote_hosts():
    """Launching local Anki cannot fix an AnkiConnect on another machine."""
    anki, clock = FakeAnki(ready_after=0), FakeClock()
    launcher = make_launcher(anki, clock)
    assert await launcher.recover("http://192.168.1.20:8765") is False
    assert anki.spawned == []


async def test_launch_timeout_mentions_profile_picker():
    anki, clock = FakeAnki(ready_after=None), FakeClock()
    launcher = make_launcher(anki, clock, timeout=5.0)
    with pytest.raises(AnkiConnectionError) as excinfo:
        await launcher.recover(URL)
    message = str(excinfo.value)
    assert "profile" in message
    assert "AnkiConnect" in message
    assert "5 s" in message


async def test_failed_launch_backs_off():
    anki, clock = FakeAnki(ready_after=None), FakeClock()
    launcher = make_launcher(anki, clock, timeout=5.0)
    with pytest.raises(AnkiConnectionError):
        await launcher.recover(URL)
    clock.now += 10
    with pytest.raises(AnkiConnectionError) as excinfo:
        await launcher.recover(URL)
    assert len(anki.spawned) == 1  # no second launch inside the backoff window
    assert "again" in str(excinfo.value)
    clock.now += 60
    with pytest.raises(AnkiConnectionError):
        await launcher.recover(URL)
    assert len(anki.spawned) == 2  # window over: one more try


async def test_launch_command_failing_is_reported_fast():
    anki, clock = FakeAnki(ready_after=None), FakeClock()
    anki.spawn = lambda command: FakeProcess(returncode=1)
    launcher = make_launcher(anki, clock)
    with pytest.raises(AnkiConnectionError) as excinfo:
        await launcher.recover(URL)
    assert "exited with code 1" in str(excinfo.value)
    assert clock.now - 1000.0 < 2  # did not sit out the full timeout


async def test_missing_executable_is_reported():
    anki, clock = FakeAnki(ready_after=None), FakeClock()

    def missing(command):
        raise FileNotFoundError(command[0])

    anki.spawn = missing
    launcher = make_launcher(anki, clock, platform="linux")
    with pytest.raises(AnkiConnectionError) as excinfo:
        await launcher.recover(URL)
    assert "ANKI_APP_PATH" in str(excinfo.value)


async def test_concurrent_recoveries_launch_once():
    anki, clock = FakeAnki(ready_after=4), FakeClock()
    launcher = make_launcher(anki, clock)
    results = await asyncio.gather(*(launcher.recover(URL) for _ in range(5)))
    assert results == [True] * 5
    assert len(anki.spawned) == 1


# --- client seam -----------------------------------------------------------


async def test_client_recovers_from_refused_connection():
    launcher = MagicMock()
    launcher.recover = AsyncMock(return_value=True)
    client = AnkiConnectClient(base_url=URL, launcher=launcher)
    with patch.object(client.client, "post", AsyncMock(side_effect=refused_then_ok())):
        assert await client.invoke(AnkiAction.DECK_NAMES) == 6
    launcher.recover.assert_awaited_once_with(URL)
    await client.close()


@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_client_does_not_launch_on_timeout(mock_sleep):
    launcher = MagicMock()
    launcher.recover = AsyncMock(return_value=True)
    client = AnkiConnectClient(base_url=URL, launcher=launcher)
    busy = AsyncMock(side_effect=httpx.ReadTimeout("busy"))
    with (
        patch.object(client.client, "post", busy),
        pytest.raises(AnkiConnectionError),
    ):
        await client.invoke(AnkiAction.DECK_NAMES)
    launcher.recover.assert_not_awaited()
    await client.close()


async def test_client_propagates_launch_failure():
    launcher = MagicMock()
    launcher.recover = AsyncMock(side_effect=AnkiConnectionError("Anki is closed"))
    client = AnkiConnectClient(base_url=URL, launcher=launcher)
    refused = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    with (
        patch.object(client.client, "post", refused),
        pytest.raises(AnkiConnectionError, match="Anki is closed"),
    ):
        await client.invoke(AnkiAction.DECK_NAMES)
    assert refused.await_count == 1  # no pointless retries against a closed port
    await client.close()


# --- telling the user ------------------------------------------------------


@pytest.fixture
def launching_client(monkeypatch):
    """Route get_anki_client to a real client whose launcher fakes Anki."""
    anki, clock = FakeAnki(ready_after=2), FakeClock()
    launcher = make_launcher(anki, clock)
    monkeypatch.setattr("mcp_ankiconnect.launcher.LAUNCHER", launcher)
    return anki


async def test_tool_result_starts_with_note_after_launch(launching_client):
    from mcp_ankiconnect.server import num_cards_due_today

    with patch(
        "httpx.AsyncClient.post",
        AsyncMock(side_effect=refused_then_ok(result=[])),
    ):
        result = await num_cards_due_today()
    first, rest = result.split("\n", 1)
    assert first.startswith("NOTE: Anki was closed, so I opened it in the background")
    assert rest == "There are 0 cards due today across all decks."
    assert len(launching_client.spawned) == 1


async def test_no_note_without_launch():
    @handle_anki_connection_error
    async def tool() -> str:
        return "plain"

    assert await tool() == "plain"


async def test_note_goes_into_dict_results_and_skips_images():
    from mcp_ankiconnect import launcher as launcher_module

    @handle_anki_connection_error
    async def dict_tool() -> dict:
        launcher_module.record_note("NOTE: opened")
        return {"ok": True}

    @handle_anki_connection_error
    async def image_tool() -> object:
        launcher_module.record_note("NOTE: opened")
        return sentinel

    sentinel = object()
    assert await dict_tool() == {"ok": True, "note": "NOTE: opened"}
    assert await image_tool() is sentinel


async def test_error_result_after_launch_keeps_note():
    from mcp_ankiconnect import launcher as launcher_module

    @handle_anki_connection_error
    async def tool() -> str:
        launcher_module.record_note("NOTE: opened")
        raise ValueError("AnkiConnect error: deck not found")

    result = await tool()
    assert result.startswith("NOTE: opened\nSYSTEM_ERROR:")


async def test_disabled_launch_error_reaches_tool_result(monkeypatch):
    anki, clock = FakeAnki(ready_after=0), FakeClock()
    monkeypatch.setattr(
        "mcp_ankiconnect.launcher.LAUNCHER",
        make_launcher(anki, clock, enabled=False),
    )
    from mcp_ankiconnect.server import num_cards_due_today

    refused = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    with patch("httpx.AsyncClient.post", refused):
        result = await num_cards_due_today()
    assert result.startswith("SYSTEM_ERROR:")
    assert "closed" in result
    assert "ANKI_AUTO_LAUNCH" in result
