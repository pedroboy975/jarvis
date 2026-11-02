"""The reply language follows the language the configured voice can speak."""
import json

from jarvis.output.tts import reply_language_instruction


def _write_piper_voice(tmp_path, voice_name, language=None):
    model = tmp_path / f"{voice_name}.onnx"
    model.write_bytes(b"onnx")
    if language is not None:
        (tmp_path / f"{voice_name}.onnx.json").write_text(
            json.dumps({"language": language}), encoding="utf-8"
        )
    return str(model)


def test_piper_voice_with_config_names_its_language(tmp_path):
    model = _write_piper_voice(
        tmp_path,
        "pt_BR-faber-medium",
        {"code": "pt_BR", "name_english": "Portuguese", "country_english": "Brazil"},
    )

    instruction = reply_language_instruction("piper", model)

    assert "Portuguese (Brazil)" in instruction
    assert "English" not in instruction


def test_piper_voice_without_config_falls_back_to_file_locale(tmp_path):
    model = _write_piper_voice(tmp_path, "de_DE-thorsten-medium")

    instruction = reply_language_instruction("piper", model)

    assert "de_DE" in instruction


def test_default_piper_voice_keeps_english_replies():
    instruction = reply_language_instruction("piper", None)

    assert "English" in instruction


def test_chatterbox_keeps_english_replies(tmp_path):
    model = _write_piper_voice(
        tmp_path,
        "pt_BR-faber-medium",
        {"code": "pt_BR", "name_english": "Portuguese", "country_english": "Brazil"},
    )

    instruction = reply_language_instruction("chatterbox", model)

    assert "English" in instruction


def test_unknown_engine_adds_no_language_rule():
    assert reply_language_instruction("none", None) is None
