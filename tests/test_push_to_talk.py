"""Push-to-talk reaches the assistant while ambient listening stays paused."""
from unittest.mock import patch

import numpy as np
import pytest

from jarvis.config import get_default_config
from jarvis.dictation import dictation_engine
from jarvis.dictation.dictation_engine import DictationEngine
from jarvis.listening.listener import VoiceListener

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _keyboard(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(dictation_engine, "pynput_keyboard", MagicMock())
    monkeypatch.setattr(dictation_engine, "np", np)


class _History:
    def __init__(self):
        self.entries = []

    def add(self, text, duration=0.0):
        self.entries.append(text)
        return {"text": text}


def _engine(deliver, history):
    return DictationEngine(
        whisper_model_ref=lambda: None,
        whisper_backend_ref=lambda: None,
        mlx_repo_ref=lambda: None,
        hotkey="alt+cmd",
        history=history,
        deliver=deliver,
        record_history=False,
    )


def test_push_to_talk_delivers_speech_to_the_assistant_instead_of_pasting(monkeypatch):
    delivered, history = [], _History()
    engine = _engine(delivered.append, history)
    monkeypatch.setattr(engine, "_transcribe", lambda audio: "que horas são")
    pasted = []
    monkeypatch.setattr(dictation_engine, "_clipboard_paste", pasted.append)

    engine._transcribe_and_paste([np.ones(16000, dtype=np.float32)], 16000)

    assert delivered == ["que horas são"]
    assert pasted == []
    assert history.entries == []


def test_dictation_without_delivery_still_pastes_and_records(monkeypatch):
    history = _History()
    engine = DictationEngine(
        whisper_model_ref=lambda: None, whisper_backend_ref=lambda: None,
        mlx_repo_ref=lambda: None, hotkey="ctrl+cmd", history=history,
    )
    monkeypatch.setattr(engine, "_transcribe", lambda audio: "texto ditado")
    pasted = []
    monkeypatch.setattr(dictation_engine, "_clipboard_paste", pasted.append)

    engine._transcribe_and_paste([np.ones(16000, dtype=np.float32)], 16000)

    assert pasted == ["texto ditado"]
    assert history.entries == ["texto ditado"]


@pytest.fixture
def voice(mock_config):
    with patch("jarvis.listening.listener.create_intent_judge", return_value=None):
        subject = VoiceListener(None, mock_config, None, None)
    yield subject
    subject.stop()


def test_push_to_talk_query_is_answered_while_listening_is_paused(voice):
    voice.set_capture_paused("user", True)
    replies = []

    with patch("jarvis.reply.engine.run_reply_engine",
               side_effect=lambda *args, **kwargs: replies.append(args[3]) or "resposta"):
        voice.dispatch_push_to_talk("qual é o meu próximo compromisso")

    assert replies == ["qual é o meu próximo compromisso"]
    assert voice.capture_paused


def test_ambient_query_is_still_discarded_while_paused(voice):
    voice.set_capture_paused("user", True)
    replies = []

    with patch("jarvis.reply.engine.run_reply_engine",
               side_effect=lambda *args, **kwargs: replies.append(args[3]) or "resposta"):
        voice._dispatch_query("conversa da sala", language=None, generation=voice._capture_generation)

    assert replies == []


def test_listening_starts_paused_with_a_push_to_talk_hotkey_by_default():
    defaults = get_default_config()

    assert defaults["voice_listening_start_paused"] is True
    assert defaults["push_to_talk_hotkey"]
    assert defaults["push_to_talk_hotkey"] != defaults["dictation_hotkey"]
