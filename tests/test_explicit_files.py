from quillgrain.corpus import inventory
from quillgrain.io import read_json


def test_explicit_file_allowlist_does_not_ingest_neighbours(pack, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "chosen.md").write_text("Original selected fixture.", encoding="utf-8")
    (source / "unrelated.md").write_bytes(b"\xff\xfe not UTF-8: must never be opened")
    config = {"roots": [{"alias": "selected", "path": str(source), "source_kind": "synthetic",
                          "language": "en", "register": "essay", "rights": "MIT synthetic", "permissions": pack["permissions"],
                          "approval": {"by": "test", "basis": "selected file only"}, "include_files": ["chosen.md"]}]}
    result = inventory(config, tmp_path / "inventory.json")
    assert result == {"items": 1, "skipped": {}}
    assert read_json(tmp_path / "inventory.json")["items"][0]["relative_locator"] == "chosen.md"
    config["roots"][0]["include_files"] = []
    assert inventory(config, tmp_path / "empty.json")["items"] == 0
