import copy
import pytest

from quillgrain.compose import compile_context
from quillgrain.consumer import bundle, verify_bundle, loads_bundle
from quillgrain.io import QGError, canonical, digest


def test_consumer_roundtrip_and_scope(pack, save):
    ctx, lock = compile_context(save(pack), target="patchpitch", model_host="offline", tags=["social.telegram"])
    value = bundle(ctx, lock)
    assert loads_bundle(canonical(value).decode()) == value
    assert verify_bundle(value, model_host="offline", language="ru", register="essay", tags=["social.telegram"]) == ctx
    for scope in [{"model_host": "ollama"}, {"language": "en"}, {"register": "maker_announcement"}, {"tags": ["social.x"]}]:
        with pytest.raises(QGError):
            verify_bundle(value, **scope)
    modified = copy.deepcopy(value)
    modified["lock"]["engine_version"] = "changed"
    with pytest.raises(QGError, match="LOCK_DIGEST"):
        verify_bundle(modified)


def test_consumer_checks_assembly_not_only_self_hash(pack, save):
    ctx, lock = compile_context(save(pack))
    ctx["prompt_payload"] += "\nextra instruction"
    ctx["budget"]["used_codepoints"] = len(ctx["prompt_payload"])
    ctx["build_id"] = digest({k:v for k,v in ctx.items() if k != "build_id"})
    with pytest.raises(QGError, match="PAYLOAD_MISMATCH"):
        bundle(ctx, lock)
