"""Bounded, offline consumer interface. No source-pack or filesystem access."""
import json

from .contracts import verify_context, unique
from .compose import POLICY, rule_text, example_text, matches
from .io import QGError, canonical, digest

SCHEMA = "quillgrain.voice-bundle/v1"
MAX_BYTES = 512_000
MAX_CODEPOINTS = 24_000


def bundle(context, lock):
    result = {"schema_version": SCHEMA, "context": context, "lock": lock}
    verify_bundle(result)
    return result


def verify_bundle(value, *, model_host=None, language=None, register=None, tags=()):
    if not isinstance(value, dict) or set(value) != {"schema_version", "context", "lock"} or value["schema_version"] != SCHEMA:
        raise QGError("VOICE_BUNDLE_SCHEMA", 3)
    try:
        if len(canonical(value)) > MAX_BYTES:
            raise QGError("VOICE_BUNDLE_TOO_LARGE", 3)
        ctx = verify_context(value["context"])
        lock = value["lock"]
        expected = {'engine_version', 'packs'}
        if ctx['schema_version'] == 'quillgrain.compiled-context/v2':
            expected |= {'schema_version', 'corpora'}
        if not isinstance(lock, dict) or set(lock) != expected:
            raise QGError("VOICE_LOCK_SCHEMA", 3)
        if ctx['schema_version'] == 'quillgrain.compiled-context/v2' and (
                lock['schema_version'] != 'quillgrain.lock/v2' or lock['corpora'] != ctx['corpora']):
            raise QGError('VOICE_LOCK_SCHEMA', 3)
        if digest(lock) != ctx["lock_digest"] or lock["packs"] != ctx["packs"] or lock["engine_version"] != ctx["engine_version"]:
            raise QGError("LOCK_DIGEST_MISMATCH", 3)
        unique(ctx["packs"])
        unique(ctx["rules_applied"])
        unique(ctx["examples_selected"])
        if ctx["budget"]["max_codepoints"] > MAX_CODEPOINTS:
            raise QGError("VOICE_BUDGET_UNSUPPORTED", 3)
        if not ctx["permissions"]["retrieval"] or ctx["model_host"] not in ctx["permissions"]["approved_model_hosts"]:
            raise QGError("HOST_OR_RETRIEVAL_DENIED", 3)
        if model_host is not None and ctx["model_host"] != model_host:
            raise QGError("VOICE_HOST_MISMATCH", 3)
        if language is not None and ctx["language"] != language:
            raise QGError("VOICE_LANGUAGE_MISMATCH", 3)
        if register is not None and ctx["register"] != register:
            raise QGError("VOICE_REGISTER_MISMATCH", 3)
        if not set(tags) <= set(ctx["tags"]):
            raise QGError("VOICE_CHANNEL_MISMATCH", 3)
        for rule in ctx["rules_applied"]:
            if not matches(rule["scope"], ctx["language"], ctx["register"], ctx["tags"]):
                raise QGError("VOICE_RULE_SCOPE", 3)
        for ex in ctx["examples_selected"]:
            if (ex["language"] != ctx["language"] or ex["register"] != ctx["register"]
                    or not ex["permissions"]["retrieval"] or ctx["model_host"] not in ex["permissions"]["approved_model_hosts"]
                    or not set(ex["tags"]) <= set(ctx["tags"])):
                raise QGError("VOICE_EXAMPLE_PERMISSION_OR_SCOPE", 3)
        expected = POLICY + "".join("\n" + rule_text(r) for r in ctx["rules_applied"])
        expected += "".join("\n\n" + example_text(e) for e in ctx["examples_selected"])
        if expected != ctx["prompt_payload"]:
            raise QGError("VOICE_PAYLOAD_MISMATCH", 3)
        return ctx
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise QGError("VOICE_BUNDLE_SCHEMA", 3) from exc


def loads_bundle(text, **scope):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise QGError("VOICE_BUNDLE_TOO_LARGE", 3)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise QGError("DUPLICATE_JSON_KEY", 3)
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=pairs)
        verify_bundle(value, **scope)
        return value
    except (ValueError, RecursionError) as exc:
        raise QGError("VOICE_BUNDLE_SCHEMA", 3) from exc
