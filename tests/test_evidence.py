import copy
import pytest
from quillgrain import evaluation
from quillgrain.adapters.scriptorium import analyze, import_observation, SCHEMA, PROFILES
from quillgrain.compose import compile_context
from quillgrain.io import QGError, read_json, sha, write_json


def test_metrics_import_preserves_units_and_nulls(tmp_path):
    native = {"schema_version": SCHEMA, "profiles": PROFILES, "metrics": {"mean_sentence_length_chars": {"value": 7, "unit": "characters/sentence"},
                                                 "dictionary": {"value": None, "unit": "words"}}}
    wrapper = {"provider": "scriptorium", "revision": "synthetic-test-revision", "schema_profile": SCHEMA,
               "input_sha256": sha(b"text"), "metrics": native}
    path = tmp_path / "metrics.json"
    write_json(path, wrapper)
    assert import_observation(path, sha(b"text"))["metrics"] == native
    with pytest.raises(QGError, match="INPUT_MISMATCH"):
        import_observation(path, sha(b"different"))
    wrapper["metrics"]["schema_version"] = "future"
    write_json(path, wrapper)
    with pytest.raises(QGError, match="NATIVE_METRICS"):
        import_observation(path, sha(b"text"))
    assert analyze("short text")["status"] == "METRICS_NOT_RUN"


def test_evaluation_packets_and_immutable_live_evidence(pack, save, tmp_path):
    context, _ = compile_context(save(pack))
    write_json(tmp_path / "context.json", context)
    case = dict(id="case", baseline="Baseline", brief="Exactly these facts. 100 words.",
                contexts={"B1": "../context.json", "B2": "../context.json"})
    write_json(tmp_path / "cases/case.json", case)
    runs = tmp_path / "runs"
    assert evaluation.prepare(tmp_path / "cases", runs)["packets"] == 3
    manifests = [read_json(p) for p in runs.rglob("run.json")]
    assert len({r["input_hash"] for r in manifests}) == 1
    assert {r["status"] for r in manifests} == {"NOT_RUN"}
    raw = tmp_path / "answer.md"
    raw.write_text("Real tool output supplied by the caller.", encoding="utf-8")
    with pytest.raises(QGError, match="LIVE_IDENTITY"):
        evaluation.record(runs / "case/B0/run.json", raw)
    evaluation.record(runs / "case/B0/run.json", raw, status="MOCK")
    with pytest.raises(QGError, match="IMMUTABLE"):
        evaluation.record(runs / "case/B0/run.json", raw, status="MOCK")
    result = evaluation.report(runs, tmp_path / "report")
    assert result["counts"] == {"MOCK": 1, "NOT_RUN": 2}
    assert read_json(tmp_path / "report/review-key.private.json") == []


def test_public_build_rejects_private_pack_before_export(pack, save):
    pack["visibility"] = "local_only"
    with pytest.raises(QGError, match="PRIVATE_TO_PUBLIC"):
        compile_context(save(pack), public=True)
