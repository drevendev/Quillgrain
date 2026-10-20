import copy
import pytest
from quillgrain.compose import compile_context, load_chain, reference
from quillgrain.io import QGError, digest


def example(pack, identity, work, text="Synthetic original sample."):
    return dict(id=identity, work_id=work, text=text, source_id="synthetic-test", language="ru", register="essay",
                channel="narration", permissions=copy.deepcopy(pack["permissions"]), visibility="public", role="positive",
                tags=[], priority=50, authorship="synthetic_ai_prepared", status="REVIEWED")


def test_selection_permissions_tags_diversity_and_omission(pack, save):
    pack["examples"] = [example(pack, "a1", "a"), example(pack, "a2", "a"), example(pack, "b1", "b")]
    pack["examples"] += [example(pack, "denied", "d"), example(pack, "unreviewed", "u"), example(pack, "tagged", "t")]
    pack["examples"][3]["permissions"]["retrieval"] = False
    pack["examples"][4]["status"] = "CANDIDATE"
    pack["examples"][5]["tags"] = ["special"]
    context, _ = compile_context(save(pack))
    assert [e["id"] for e in context["examples_selected"]] == ["a1", "b1", "a2"]
    reasons = {e["id"]: e["reason"] for e in context["examples_omitted"]}
    assert reasons == {"denied": "permissions", "unreviewed": "unreviewed", "tagged": "explicit_tags"}
    path = save(pack)
    smaller, _ = compile_context(path, max_chars=context["budget"]["used_codepoints"] - 1)
    assert len(smaller["examples_selected"]) == 2
    assert any(e["reason"] == "budget" for e in smaller["examples_omitted"])
    for selected in smaller["examples_selected"]:
        assert selected["text"] in smaller["prompt_payload"]


def test_private_example_visibility_never_downgrades(pack, save):
    private = example(pack, "private", "private", "PRIVATE_SYNTHETIC_CONTENT")
    private["visibility"] = "private"
    private["permissions"]["public_redistribution"] = False
    pack["examples"] = [private]
    context, _ = compile_context(save(pack))
    assert context["visibility"] == "private"
    public, _ = compile_context(save(pack), public=True)
    assert public["examples_selected"] == []
    assert "PRIVATE_SYNTHETIC_CONTENT" not in public["prompt_payload"]


def test_negative_examples_marked_and_modes_restricted(pack, save):
    negative = example(pack, "negative", "n")
    negative["role"] = "negative"
    pack["examples"] = [negative]
    pack["modes"] = [{"language": "ru", "register": "essay", "status": "UNVALIDATED_ADAPTATION"}]
    context, _ = compile_context(save(pack))
    assert "EXAMPLE DATA (negative;" in context["prompt_payload"]
    assert any("UNVALIDATED_ADAPTATION" in w for w in context["warnings"])
    with pytest.raises(QGError, match="LANGUAGE_OR_REGISTER"):
        compile_context(save(pack), language="en")


def test_duplicate_ids_across_packs_and_scope_override(pack, save):
    path = save(pack, "base")
    child = copy.deepcopy(pack)
    child.update(id="child", extends=[reference(pack)])
    with pytest.raises(QGError, match="DUPLICATE_RULE_ID"):
        compile_context(save(child, "child"), bindings={pack["id"]: path})
    child["rules"] = [copy.deepcopy(pack["rules"][0])]
    child["rules"][0].update(id="new.rule", overrides=["synthetic.clarity"], scope={"channel": "dialogue"})
    with pytest.raises(QGError, match="OVERRIDE_SCOPE_MISMATCH"):
        compile_context(save(child, "child"), bindings={pack["id"]: path})


def test_cycle_rejected_before_compilation(pack, save):
    # A self-reference cannot have a fixed SHA-256; stale digest or active-cycle gate
    # must reject it rather than recurse or load any network content.
    pack["extends"] = [reference(pack)]
    with pytest.raises(QGError):
        load_chain(save(pack))
