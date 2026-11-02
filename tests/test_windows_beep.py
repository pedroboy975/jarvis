"""Windows beeps play: winsound cannot play a memory image asynchronously."""
import threading
from types import SimpleNamespace

import pytest

from jarvis.dictation import dictation_engine

pytestmark = pytest.mark.unit


@pytest.fixture
def windows_sound(monkeypatch):
    played, done = [], threading.Event()

    def play_sound(data, flags):
        # CPython's winsound refuses SND_MEMORY together with SND_ASYNC.
        if flags & fake.SND_MEMORY and flags & fake.SND_ASYNC:
            raise RuntimeError("Cannot play asynchronously from memory")
        played.append((data, flags, threading.current_thread().name))
        done.set()

    fake = SimpleNamespace(SND_MEMORY=4, SND_ASYNC=1, SND_NODEFAULT=2, PlaySound=play_sound)
    monkeypatch.setitem(__import__("sys").modules, "winsound", fake)
    monkeypatch.setattr(dictation_engine.platform, "system", lambda: "Windows")
    return fake, played, done


@pytest.mark.parametrize("beep", [dictation_engine._get_start_beep, dictation_engine._get_stop_beep])
def test_beeps_play_from_memory_on_windows(windows_sound, beep):
    fake, played, done = windows_sound

    dictation_engine._play_beep(beep())

    assert done.wait(2), "the beep never reached PlaySound"
    data, flags, thread = played[0]
    assert data == beep()
    assert flags & fake.SND_MEMORY and not flags & fake.SND_ASYNC
    assert thread == "jarvis-beep", "the caller must not block on playback"


def test_a_playback_error_never_escapes(windows_sound, monkeypatch):
    fake, played, done = windows_sound
    failed = threading.Event()

    def broken(data, flags):
        failed.set()
        raise RuntimeError("no audio device")

    monkeypatch.setattr(fake, "PlaySound", broken)

    dictation_engine._play_beep(dictation_engine._get_start_beep())

    assert failed.wait(2)
