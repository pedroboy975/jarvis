"""whisper_cpu_threads caps the CPU threads faster-whisper uses."""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis.config import get_default_config, load_settings, whisper_cpu_thread_count
from jarvis.listening import listener

pytestmark = pytest.mark.unit


def test_every_core_is_used_by_default():
    assert get_default_config()["whisper_cpu_threads"] == 0
    assert whisper_cpu_thread_count(SimpleNamespace(whisper_cpu_threads=0)) == (os.cpu_count() or 4)
    assert whisper_cpu_thread_count(SimpleNamespace()) == (os.cpu_count() or 4)


@pytest.mark.parametrize("value,expected", [(8, 8), ("8", 8), (6.0, 6), (0, None), (-2, None),
                                            (True, None), (None, None), ("eight", None), ([8], None)])
def test_only_a_positive_count_caps_the_threads(value, expected):
    count = whisper_cpu_thread_count(SimpleNamespace(whisper_cpu_threads=value))

    assert count == (expected or os.cpu_count() or 4)


def test_settings_load_the_thread_count(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"whisper_cpu_threads": 8}), encoding="utf-8")

    with patch.dict(os.environ, {"JARVIS_CONFIG_PATH": str(path)}):
        assert load_settings().whisper_cpu_threads == 8


def test_the_listener_reads_threads_from_the_configuration():
    # Both CPU load paths (startup and CUDA-failure recovery) go through the helper.
    source = open(listener.__file__, encoding="utf-8").read()

    assert source.count("whisper_cpu_thread_count(self.cfg)") == 2
    assert "cpu_threads = os.cpu_count()" not in source
    assert "(os.cpu_count() or 4) if try_device" not in source
