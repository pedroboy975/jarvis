"""Push-to-talk: the start beep means the mic is live, and each phase is timed."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.dictation import dictation_engine
from jarvis.dictation.dictation_engine import DictationEngine
from jarvis.usage_log import RequestTiming

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _keyboard(monkeypatch):
    monkeypatch.setattr(dictation_engine, "pynput_keyboard", MagicMock())
    monkeypatch.setattr(dictation_engine, "np", np)


def _engine():
    model = SimpleNamespace(transcribe=lambda audio, **kw: ([SimpleNamespace(text="que horas são")], None))
    return DictationEngine(whisper_model_ref=lambda: model, whisper_backend_ref=lambda: "faster-whisper",
                           mlx_repo_ref=lambda: None, hotkey="alt+cmd", deliver=lambda text: None,
                           record_history=False, cfg=SimpleNamespace(whisper_language="pt"),
                           voice_device="1")


def _start(engine, events, supersede=False):
    stream = MagicMock()
    stream.start.side_effect = lambda: events.append("mic live")
    with patch.object(dictation_engine, "sd") as sd, \
         patch.object(dictation_engine, "_play_beep", side_effect=lambda wav: events.append("beep")):
        sd.query_devices.return_value = {"max_input_channels": 1, "default_samplerate": 16000}
        sd.InputStream.return_value = stream
        engine._start_recording()
        token = engine._session
        if supersede:
            engine._session += 1
        with patch.object(dictation_engine.threading, "Thread"):
            engine._begin_recording(token)
    return stream


def test_the_start_beep_plays_only_after_the_microphone_is_live():
    engine, events = _engine(), []
    with patch.object(dictation_engine.threading, "Thread"):
        _start(engine, events)

    assert events == ["mic live", "beep"]
    assert isinstance(engine.last_timings["mic_open_s"], float)


def test_a_superseded_press_gets_no_start_beep():
    engine, events = _engine(), []
    with patch.object(dictation_engine.threading, "Thread"):
        _start(engine, events, supersede=True)

    assert "beep" not in events
    assert "mic_open_s" not in engine.last_timings


def test_transcription_and_closing_are_timed():
    engine = _engine()
    with patch.object(dictation_engine, "_play_beep"), patch.object(dictation_engine, "_close_stream"):
        engine._finalise_and_transcribe(MagicMock(), [np.full(32000, 0.1, dtype=np.float32)],
                                        0.0, 16000, engine._session)

    assert set(engine.last_timings) >= {"mic_close_s", "whisper_s", "audio_s"}
    assert engine.last_timings["audio_s"] == 2.0


def test_phases_join_the_usage_record_without_replacing_its_fields():
    timing = RequestTiming(source="push_to_talk", started=0.0, heard=1.0, replied=2.0, voice=2.1,
                           phases={"whisper_s": 0.9, "mic_open_s": 0.4, "ok": 0.0, "flag": True})

    record = timing.record()

    assert record["whisper_s"] == 0.9 and record["mic_open_s"] == 0.4
    assert record["ok"] is True
    assert "flag" not in record
