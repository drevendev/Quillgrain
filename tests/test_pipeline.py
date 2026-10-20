import copy
import pytest
from quillgrain.compose import compile_context, reference, POLICY
from quillgrain.contracts import load_pack, verify_context
from quillgrain.export import export
from quillgrain.checks import check
from quillgrain.feedback import record
from quillgrain.io import QGError, canonical, read_json, write_json, digest


def test_reproducible_export_and_no_input_mutation(pack, save, tmp_path):
    path = save(pack)
    raw = (path / "voice.json").read_bytes()
    a, lock = compile_context(path)
    b, _ = compile_context(path)
    assert canonical(a) == canonical(b)
    export(a, lock, tmp_path / "a")
    export(b, lock, tmp_path / "b")
    assert (tmp_path / "a/context.json").read_bytes() == (tmp_path / "b/context.json").read_bytes()
    assert (path / "voice.json").read_bytes() == raw
    assert check("Лампа.", a)["findings"] == []
    assert check("телепортация", a)["findings"][0]["severity"] == "error"


@pytest.mark.parametrize("mutation", [lambda p: p.update(schema_version="v99"),
    lambda p: p.update(shell_hook="arbitrary"), lambda p: p["rules"].append(p["rules"][0]),
    lambda p: p.update(status="VALIDATED")])
def test_bad_contracts(pack, save, mutation):
    mutation(pack)
    with pytest.raises(QGError):
        load_pack(save(pack))


def test_explicit_override_and_permission_narrowing(pack, save):
    root = save(pack, "base")
    child = copy.deepcopy(pack)
    child.update(id="author", extends=[reference(pack)], examples=[], visibility="private")
    rule = copy.deepcopy(pack["rules"][0])
    rule.update(id="author.clarity", overrides=[rule["id"]], instruction="Use a slower pace.")
    child["rules"] = [rule]
    child["permissions"]["public_redistribution"] = False
    path = save(child, "author")
    context, _ = compile_context(path, bindings={pack["id"]: root})
    assert context["rules_overridden"] == [{"id": "synthetic.clarity", "by": "author.clarity"}]
    assert context["visibility"] == "private"
    with pytest.raises(QGError, match="PRIVATE_TO_PUBLIC"):
        compile_context(path, bindings={pack["id"]: root}, public=True)
    pack["permissions"]["approved_model_hosts"] = ["offline"]
    root = save(pack, "base")
    child["extends"] = [reference(pack)]
    with pytest.raises(QGError, match="PERMISSION_ESCALATION"):
        compile_context(save(child, "author"), bindings={pack["id"]: root})


def test_no_silent_constraint_override(pack, save):
    root = save(pack, "base")
    child = copy.deepcopy(pack)
    child.update(id="child", extends=[reference(pack)], rules=[copy.deepcopy(pack["rules"][0])])
    child["rules"][0].update(id="child.rule", overrides=["synthetic.no-unshipped"])
    with pytest.raises(QGError, match="MANDATORY_CONFLICT"):
        compile_context(save(child, "child"), bindings={pack["id"]: root})


def test_missing_and_stale_parent(pack, save):
    base = save(pack, "base")
    child = copy.deepcopy(pack)
    child.update(id="child", extends=[reference(pack)], rules=[])
    path = save(child, "child")
    with pytest.raises(QGError, match="PARENT_UNAVAILABLE"):
        compile_context(path)
    pack["version"] = "0.2.0"
    save(pack, "base")
    with pytest.raises(QGError, match="STALE_DEPENDENCY"):
        compile_context(path, bindings={pack["id"]: base})


def test_lock_tampering_and_context_digest(pack, save):
    path = save(pack)
    context, lock = compile_context(path)
    write_json(path / "quillgrain.lock.json", lock)
    assert compile_context(path)[0] == context
    lock["engine_version"] = "future"
    write_json(path / "quillgrain.lock.json", lock)
    with pytest.raises(QGError, match="STALE_LOCK"):
        compile_context(path)
    context["prompt_payload"] += " injected"
    with pytest.raises(QGError, match="CONTEXT_DIGEST"):
        verify_context(context)


def test_whole_elements_and_unicode_budget(pack, save, tmp_path):
    # Exact len() boundary with a non-BMP character; never slice a required rule.
    pack["rules"] = [pack["rules"][1]]
    pack["rules"][0]["instruction"] = "🪶" * (1200 - len(POLICY) - len("\n[synthetic.no-unshipped / narration] "))
    path = save(pack)
    context, lock = compile_context(path, target="patchpitch-legacy", max_chars=1200)
    export(context, lock, tmp_path / "out")
    assert len((tmp_path / "out/voice_reference.txt").read_text(encoding="utf-8")) == 1200
    assert read_json(tmp_path / "out/voice_reference.manifest.json")["codepoints"] == 1200
    pack["rules"][0]["instruction"] += "x"
    with pytest.raises(QGError, match="BUDGET_EXCEEDED"):
        compile_context(save(pack), target="patchpitch-legacy", max_chars=1201)


def test_code_quotes_offsets_and_character_scopes(pack, save):
    context, _ = compile_context(save(pack))
    text = '🪶 «телепортация»\n> телепортация\n`телепортация`\n```\nтелепортация\n```\n— телепортация\nтелепортация'
    findings = check(text, context)["findings"]
    assert len(findings) == 1
    assert text[findings[0]["start"]:findings[0]["end"]] == "телепортация"
    assert findings[0]["start"] == text.rfind("телепортация")
    pack["rules"][1]["scope"] = {"channel": "dialogue", "characters": ["a"]}
    context, _ = compile_context(save(pack))
    text = "телепортация телепортация"
    assert not check(text, context)["findings"]
    spans = [{"start": 0, "end": 12, "character": "b"}, {"start": 13, "end": 25, "character": "a"}]
    assert check(text, context, spans)["findings"][0]["start"] == 13


def test_feedback_is_candidate_and_facts_not_voice(pack, save):
    path = save(pack)
    context, _ = compile_context(path)
    before = (path / "voice.json").read_bytes()
    feedback = record("one", "two", context, "fact correction", reason="fact")
    assert feedback["decision_status"] == "CANDIDATE"
    assert (path / "voice.json").read_bytes() == before
    with pytest.raises(QGError, match="NOT_VOICE_RULE"):
        record("one", "two", context, "", reason="fact", proposed=["rule"])


def test_conflicting_literals_fail(pack, save):
    rule = copy.deepcopy(pack["rules"][1])
    rule.update(id="required", enforcement="required_literal")
    pack["rules"].append(rule)
    with pytest.raises(QGError, match="MANDATORY_CONFLICT"):
        compile_context(save(pack))


def test_host_denied_and_unknown_language(pack, save):
    path = save(pack)
    with pytest.raises(QGError, match="HOST_OR_RETRIEVAL"):
        compile_context(path, model_host="new-service")
    with pytest.raises(QGError, match="LANGUAGE_OR_REGISTER"):
        compile_context(path, language="unknown")
