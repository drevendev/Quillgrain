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
    unsigned = {k: v for k, v in context.items() if k != "build_id"}
    if digest(unsigned) != context["build_id"]:
        raise QGError("CONTEXT_DIGEST_MISMATCH", 3)
    if len(context["prompt_payload"]) != context["budget"]["used_codepoints"]:
        raise QGError("CONTEXT_BUDGET_MISMATCH", 3)
    if not 0 <= context['budget']['used_codepoints'] <= context['budget']['max_codepoints']:
        raise QGError('BUDGET_EXCEEDED', 3)
    if context.get('schema_version') == 'quillgrain.compiled-context/v2':
        from .io import sha
        unique(context['corpora'])
        unique(context['corpus_materials'], 'example_id')
        unique(context['evidence_refs'], 'evidence_id')
        evidence_used = {identity for rule in context['rules_applied'] for identity in rule['evidence_ids']}
        if any(e['evidence_id'] not in evidence_used or e['corpus_id'] not in {c['id'] for c in context['corpora']}
               for e in context['evidence_refs']):
            raise QGError('CONTEXT_EVIDENCE_MISMATCH', 3)
        examples = {e['id']: e for e in context['examples_selected']}
        for material in context['corpus_materials']:
            example = examples.get(material['example_id'])
            if (not example or example['source_id'] != material['source_id'] or example['work_id'] != material['work_id']
                    or sha(example['text'].encode('utf-8')) != material['sha256']
                    or material['corpus_id'] not in {c['id'] for c in context['corpora']}):
                raise QGError('CONTEXT_CORPUS_LINEAGE_MISMATCH', 3)
        if context['example_mode'] == 'none' and context['examples_selected']:
            raise QGError('CONTEXT_EXAMPLE_MODE_MISMATCH', 3)
    return context
