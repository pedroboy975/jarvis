"""Usage log: per-request timings, never words, written once when enabled."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jarvis.config import get_default_config
from jarvis.dictation import dictation_engine
from jarvis.dictation.dictation_engine import DictationEngine
from jarvis.listening.listener import VoiceListener
from jarvis.usage_log import (FILE_NAME, RequestTiming, daily_summary, read_records,
                              usage_log_path, write_timing)

pytestmark = pytest.mark.unit


def _cfg(tmp_path, enabled=True):
    return SimpleNamespace(usage_log_enabled=enabled, db_path=str(tmp_path / "jarvis.db"))


def test_the_log_is_off_by_default():
    assert get_default_config()["usage_log_enabled"] is False


@pytest.mark.parametrize("enabled,db,expected", [
    (True, "jarvis.db", FILE_NAME), (False, "jarvis.db", None), ("yes", "jarvis.db", None),
    (True, ":memory:", None), (True, "", None),
])
def test_the_log_sits_beside_the_database_only_when_enabled(tmp_path, enabled, db, expected):
    cfg = SimpleNamespace(usage_log_enabled=enabled, db_path=str(tmp_path / db) if db not in ("", ":memory:") else db)

    path = usage_log_path(cfg)

    assert (path.name if path else None) == expected


def test_a_request_is_written_once_with_timings_only(tmp_path):
    cfg = _cfg(tmp_path)
    timing = RequestTiming(source="push_to_talk", started=10.0, heard=11.3,
                           replied=14.0, voice=14.1, speech_seconds=2.04)

    write_timing(cfg, timing)
    write_timing(cfg, timing)

    lines = (tmp_path / FILE_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["transcribe_s"] == 1.3
    assert record["reply_s"] == 2.7
    assert record["wait_to_voice_s"] == 4.1
    assert record["speech_s"] == 2.04
    assert record["ok"] is True
    assert set(record) == {"ts", "source", "transcribe_s", "reply_s", "wait_to_voice_s", "speech_s", "ok"}


def test_nothing_is_written_while_disabled(tmp_path):
    write_timing(_cfg(tmp_path, enabled=False), RequestTiming(source="ambient", started=1.0))

    assert not (tmp_path / FILE_NAME).exists()


def test_the_daily_summary_counts_and_takes_the_median(tmp_path):
    path = tmp_path / FILE_NAME
    rows = [
        {"ts": "2026-11-03T09:00:00", "wait_to_voice_s": 4.0, "ok": True},
        {"ts": "2026-11-03T10:00:00", "wait_to_voice_s": 6.0, "ok": False},
        {"ts": "2026-11-03T11:00:00", "wait_to_voice_s": 5.0, "ok": True},
        {"ts": "2026-11-04T09:00:00", "wait_to_voice_s": None, "ok": True},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n[]\n", encoding="utf-8")

    summary = daily_summary(read_records(path))

    assert summary == [
        {"day": "2026-11-03", "requests": 3, "failed": 1, "median_wait_s": 5.0, "worst_wait_s": 6.0},
        {"day": "2026-11-04", "requests": 1, "failed": 0, "median_wait_s": None, "worst_wait_s": None},
    ]


def test_releasing_the_hotkey_records_the_moment(monkeypatch):
    monkeypatch.setattr(dictation_engine, "pynput_keyboard", MagicMock())
    engine = DictationEngine(whisper_model_ref=lambda: None, whisper_backend_ref=lambda: None,
                             mlx_repo_ref=lambda: None, hotkey="alt+cmd")
    monkeypatch.setattr(engine, "_finalise_and_transcribe", lambda *args: None)
    engine._recording = True
    engine._record_start_time = 0.0

    engine._stop_recording()

    assert isinstance(engine.last_release_at, float)


class _Voice:
    enabled = True

    def __init__(self):
        self.spoken = []

    def speak(self, text, completion_callback=None, duration_callback=None, *, terminal_callback=None):
        self.spoken.append(text)
        duration_callback(2.0)
        terminal_callback("completed")


@pytest.fixture
def voice(mock_config, tmp_path):
    mock_config.usage_log_enabled = True
    mock_config.db_path = str(tmp_path / "jarvis.db")
    with patch("jarvis.listening.listener.create_intent_judge", return_value=None):
        subject = VoiceListener(None, mock_config, None, None)
    subject.tts = _Voice()
    yield subject
    subject.stop()


def test_a_push_to_talk_answer_is_logged_without_its_words(voice, tmp_path):
    timing = RequestTiming(source="push_to_talk", started=0.0, heard=0.0)
    voice.set_capture_paused("user", True)

    with patch("jarvis.reply.engine.run_reply_engine", return_value="São 13h40."):
        voice.dispatch_push_to_talk("que horas são", timing=timing)

    text = (tmp_path / FILE_NAME).read_text(encoding="utf-8")
    record = json.loads(text)
    assert voice.tts.spoken == ["São 13h40."]
    assert record["source"] == "push_to_talk"
    assert record["speech_s"] == 2.0
    assert record["wait_to_voice_s"] is not None
    assert "horas" not in text and "13h40" not in text


def test_a_failed_reply_is_logged_as_failed(voice, tmp_path):
    voice.set_capture_paused("user", True)

    with patch("jarvis.reply.engine.run_reply_engine", side_effect=RuntimeError("boom")):
        voice.dispatch_push_to_talk("que horas são")

    record = json.loads((tmp_path / FILE_NAME).read_text(encoding="utf-8"))
    assert record["ok"] is False
