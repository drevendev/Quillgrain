from quillgrain.cli import main
from quillgrain.io import read_json, write_json


def test_cli_error_codes_reports_and_no_private_terminal_text(pack, save, tmp_path, capsys):
    path = save(pack)
    assert main(["doctor"]) == 0
    assert main(["pack", "validate", "--pack", str(path)]) == 0
    pack["rules"][0]["conflicts_with"] = [pack["rules"][1]["id"]]
    save(pack)
    out = tmp_path / "conflicts"
    assert main(["pack", "build", "--pack", str(path), "--register", "essay", "--out", str(out)]) == 3
    error = read_json(out / "build-error.json")
    assert error["status"] == "CONFLICT" and error["details"]["rule_id"] == pack["rules"][0]["id"]
    assert main(["pack", "validate", "--pack", str(path)]) == 3
    captured = capsys.readouterr()
    assert str(tmp_path) not in captured.err
    assert pack["rules"][0]["instruction"] not in captured.err
    assert main(["check", "--draft", "nonexistent-private-file", "--context", "missing", "--out", str(out)]) == 5


def test_backend_absence_and_required_exit(tmp_path):
    text = tmp_path / "text.md"
    text.write_text("Synthetic text", encoding="utf-8")
    out = tmp_path / "metrics.json"
    assert main(["analyze", "--input", str(text), "--out", str(out)]) == 0
    assert read_json(out)["status"] == "METRICS_NOT_RUN"
    assert main(["analyze", "--input", str(text), "--out", str(out), "--require-provider"]) == 4
