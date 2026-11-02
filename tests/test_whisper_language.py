"""A configured Whisper language reaches every transcription path."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.config import _normalise_whisper_language, get_default_config, whisper_language_code
from jarvis.dictation import dictation_engine
from jarvis.dictation.dictation_engine import DictationEngine
from jarvis.listening.listener import VoiceListener

pytestmark = pytest.mark.unit


class _Whisper:
    def __init__(self):
        self.languages = []

    def transcribe(self, audio, language=None, **kwargs):
        self.languages.append(language)
        return [SimpleNamespace(text="que horas são")], SimpleNamespace(language=language or "en")


def test_language_is_detected_per_utterance_by_default():
    assert get_default_config()["whisper_language"] == ""
    assert whisper_language_code(SimpleNamespace(whisper_language="")) is None


@pytest.mark.parametrize("value,expected", [
    ("pt", "pt"), (" PT ", "pt"), ("haw", "haw"), ("auto", ""), ("", ""),
    (None, ""), (12, ""), ("pt-BR", ""), ("portuguese", ""), ("p", ""),
])
def test_language_codes_are_normalised(value, expected):
    assert _normalise_whisper_language(value) == expected


@pytest.mark.parametrize("language,expected", [("pt", "pt"), ("", None)])
def test_dictation_and_push_to_talk_transcribe_in_the_configured_language(monkeypatch, language, expected):
    monkeypatch.setattr(dictation_engine, "pynput_keyboard", MagicMock())
    model = _Whisper()
    engine = DictationEngine(
        whisper_model_ref=lambda: model, whisper_backend_ref=lambda: "faster-whisper",
        mlx_repo_ref=lambda: None, hotkey="alt+cmd",
        cfg=SimpleNamespace(whisper_language=language),
    )

    assert engine._transcribe(np.zeros(16000, dtype=np.float32)) == "que horas são"
    assert model.languages == [expected]


@pytest.fixture
def voice(mock_config):
    mock_config.whisper_language = "pt"
    with patch("jarvis.listening.listener.create_intent_judge", return_value=None):
        subject = VoiceListener(None, mock_config, None, None)
    yield subject
    subject.stop()


def test_ambient_listening_transcribes_in_the_configured_language(voice):
    model = _Whisper()
    voice.model = model
    voice._whisper_backend = "faster-whisper"
    voice._whisper_device = "cpu"
    voice.cfg.whisper_no_speech_threshold = 0.5

    voice._decode_faster_whisper(np.zeros(16000, dtype=np.float32))

    assert model.languages == ["pt"]


def test_push_to_talk_shows_what_whisper_heard(voice, capsys):
    voice.set_capture_paused("user", True)

    with patch("jarvis.reply.engine.run_reply_engine", return_value="resposta"):
        voice.dispatch_push_to_talk("  que horas são ")

    assert '📝 Heard (push-to-talk): "que horas são"' in capsys.readouterr().out
