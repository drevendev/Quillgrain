"""Draft 2020-12 contracts plus semantic invariants."""

from importlib.resources import files
from jsonschema import Draft202012Validator
from .io import QGError, read_json, digest
from .portable import verify_context as verify_semantics


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
    raw = read_json(path / "voice.json")
    pack = validate(raw, "voice-pack-v2" if raw.get('schema_version') == 'quillgrain.voice-pack/v2' else "voice-pack")
    unique(pack["rules"])
    unique(pack["examples"] + pack.get('example_refs', []))
    unique(pack.get('corpus_dependencies', []))
    unique(pack.get('evidence_refs', []), 'evidence_id')
    dependencies = {c['id'] for c in pack.get('corpus_dependencies', [])}
    if any(r['corpus_id'] not in dependencies for r in pack.get('example_refs', []) + pack.get('evidence_refs', [])):
        raise QGError('CORPUS_DEPENDENCY_UNDECLARED', 3)
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
    validate(context, "compiled-context-v2" if context.get('schema_version') == 'quillgrain.compiled-context/v2' else "compiled-context")
    return verify_semantics(context)
