import copy
import os
from pathlib import Path
import pytest
from quillgrain.corpus import inventory, prepare, extract
from quillgrain.io import QGError, bounded, read_json


def config(root, pack):
    return {"roots": [{"alias": "synthetic", "path": str(root), "source_kind": "synthetic",
                       "language": "ru", "register": "essay", "authorship": "owner_declared_human",
                       "permissions": pack["permissions"], "rights": "original test data",
                       "approval": {"by": "test", "basis": "synthetic"}}]}


def test_extract_preserves_raw_and_ignores_embeds_quotes_code():
    raw = '\ufeff---\r\ntitle: test\r\n---\r\nАвтор е\u0308 🪶\r\n> чужое\r\n— реплика\r\n![[secret]]\r\n```\r\nкод\r\n```'.encode("utf-8")
    value, ranges = extract(raw)
    assert value == "Автор ё 🪶"
    assert ranges == [{"start_line": 4, "end_line": 4}]
    with pytest.raises(QGError, match="MALFORMED"):
        extract(b"---\ntitle: broken")
    assert extract(b"")[0] == ""


def test_inventory_duplicate_work_split_and_mutation(tmp_path, pack):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.md").write_text("Авторский текст.", encoding="utf-8")
    (source / "copy.md").write_text("Авторский текст.", encoding="utf-8")
    (source / ".obsidian").mkdir()
    (source / ".obsidian/plugin.md").write_text("must not read", encoding="utf-8")
    cfg = config(source, pack)
    inventory(cfg, tmp_path / "inventory.json")
    items = read_json(tmp_path / "inventory.json")["items"]
    assert len(items) == 2 and items[0]["work_id"] == items[1]["work_id"]
    items[0]["selection"], items[1]["selection"] = "reference", "holdout"
    with pytest.raises(QGError, match="WORK_SPLIT_LEAKAGE"):
        prepare(items, cfg, tmp_path / "prepared")
    items[1]["selection"] = "reference"
    assert prepare(items, cfg, tmp_path / "prepared")["prepared"] == 2
    (source / "a.md").write_text("Changed", encoding="utf-8")
    with pytest.raises(QGError, match="SOURCE_MUTATED"):
        prepare(items, cfg, tmp_path / "new")
    with pytest.raises(QGError, match="SOURCE_WRITE_DENIED"):
        inventory(cfg, source / "inventory.json")


def test_path_escape_and_unknown_authorship(tmp_path, pack):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.md").write_text("Text", encoding="utf-8")
    with pytest.raises(QGError, match="PATH_ESCAPE"):
        bounded(root, "../outside")
    cfg = config(root, pack)
    cfg["roots"][0]["authorship"] = "unknown"
    inventory(cfg, tmp_path / "inv.json")
    items = read_json(tmp_path / "inv.json")["items"]
    items[0]["selection"] = "reference"
    with pytest.raises(QGError, match="AUTHORSHIP_UNCONFIRMED"):
        prepare(items, cfg, tmp_path / "out")


def test_symlink_escape(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_text("canary", encoding="utf-8")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import subprocess
        # NTFS junction creation does not require developer-mode symlink privileges.
        subprocess.run(["powershell", "-NoProfile", "-Command", "New-Item -ItemType Junction -Path $env:QG_TEST_LINK -Target $env:QG_TEST_TARGET -ErrorAction Stop | Out-Null"],
                       env={**os.environ, "QG_TEST_LINK": str(root / "link"), "QG_TEST_TARGET": str(outside)}, check=True)
    with pytest.raises(QGError, match="PATH_ESCAPE"):
        bounded(root, "link/secret.md")
