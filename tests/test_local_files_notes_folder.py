"""localFiles keeps Jarvis inside its notes folder and never destroys a file."""
import os

import pytest

from jarvis.tools.base import ToolContext
from jarvis.tools.builtin.local_files import LocalFilesTool

pytestmark = pytest.mark.unit


@pytest.fixture
def notes(monkeypatch, tmp_path, mock_config):
    home = tmp_path / "home"
    root = home / "Obsidian" / "Jarvis"
    root.mkdir(parents=True)
    original_expand = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda path: str(home) + path[1:] if path.startswith("~") else original_expand(path),
    )
    mock_config.local_files_root = "~/Obsidian/Jarvis"
    context = ToolContext(None, mock_config, "", "", "", 0, lambda message: None)
    return LocalFilesTool(), context, home, root


def test_new_note_is_created_inside_the_notes_folder(notes):
    tool, context, _home, root = notes

    result = tool.run({"operation": "write", "path": "ideias.md", "content": "café"}, context)

    assert result.success, result.reply_text
    assert (root / "ideias.md").read_text(encoding="utf-8") == "café"


@pytest.mark.parametrize("path", [
    "~/.env",
    "~/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/run.md",
    "../segredo.md",
])
def test_paths_outside_the_notes_folder_are_refused(notes, path):
    tool, context, home, _root = notes

    for operation in ("read", "write", "append", "list"):
        result = tool.run({"operation": operation, "path": path, "content": "x"}, context)
        assert not result.success, f"{operation} {path} escaped the notes folder"
    assert not (home / "segredo.md").exists()


def test_existing_note_is_never_overwritten(notes):
    tool, context, _home, root = notes
    (root / "diario.md").write_text("original", encoding="utf-8")

    result = tool.run({"operation": "write", "path": "diario.md", "content": "novo"}, context)

    assert not result.success
    assert (root / "diario.md").read_text(encoding="utf-8") == "original"


def test_append_keeps_existing_text(notes):
    tool, context, _home, root = notes
    (root / "diario.md").write_text("original", encoding="utf-8")

    result = tool.run({"operation": "append", "path": "diario.md", "content": " e mais"}, context)

    assert result.success, result.reply_text
    assert (root / "diario.md").read_text(encoding="utf-8") == "original e mais"


def test_delete_is_refused(notes):
    tool, context, _home, root = notes
    (root / "diario.md").write_text("original", encoding="utf-8")

    result = tool.run({"operation": "delete", "path": "diario.md"}, context)

    assert not result.success
    assert (root / "diario.md").exists()


@pytest.mark.parametrize("name", ["run.bat", "script.ps1", "tool.py", "sem_extensao"])
def test_only_text_notes_can_be_written(notes, name):
    tool, context, _home, root = notes

    for operation in ("write", "append"):
        result = tool.run({"operation": operation, "path": name, "content": "echo"}, context)
        assert not result.success
    assert not (root / name).exists()
