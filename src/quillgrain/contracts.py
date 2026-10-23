"""Draft 2020-12 contracts plus semantic invariants."""

from importlib.resources import files
from jsonschema import Draft202012Validator
from .io import QGError, read_json, digest


def validate(value, name):
    schema = read_json(files("quillgrain").joinpath("schemas", name + ".json"))
    if next(Draft202012Validator(schema).iter_errors(value), None):
        raise QGError("SCHEMA_INVALID:" + name)
    return value


def unique(items, label="id"):
    ids = [item[label] for item in items]
    if len(ids) != len(set(ids)):
        raise QGError("DUPLICATE_ID")


def load_pack(path):
    pack = validate(read_json(path / "voice.json"), "voice-pack")
    unique(pack["rules"])
    unique(pack["examples"])
    if pack["status"] == "VALIDATED" and not pack.get("human_review"):
        raise QGError("HUMAN_REVIEW_REQUIRED", 3)
    for rule in pack["rules"]:
        method = rule["enforcement"]
        params = rule.get("parameters", {})
        if method in ("required_literal", "forbidden_literal") and not params.get("literal"):
            raise QGError("LITERAL_REQUIRED")
        if method == "max_chars" and (type(params.get("max_chars")) is not int or params["max_chars"] < 1):
            raise QGError("MAX_CHARS_REQUIRED")
        if rule["origin"] == "observed" and not rule["evidence_ids"]:
            raise QGError("OBSERVATION_NEEDS_EVIDENCE")
    return pack


def verify_context(context):
    validate(context, "compiled-context")
    unsigned = {k: v for k, v in context.items() if k != "build_id"}
    if digest(unsigned) != context["build_id"]:
        raise QGError("CONTEXT_DIGEST_MISMATCH", 3)
    if len(context["prompt_payload"]) != context["budget"]["used_codepoints"]:
        raise QGError("CONTEXT_BUDGET_MISMATCH", 3)
    if not 0 <= context['budget']['used_codepoints'] <= context['budget']['max_codepoints']:
        raise QGError('BUDGET_EXCEEDED', 3)
    return context
