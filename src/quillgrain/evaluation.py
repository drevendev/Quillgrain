"""Prompt packets and evidence recording; deliberately no model runner."""
import random
import uuid
from collections import Counter
from pathlib import Path
from . import __version__
from .contracts import validate, verify_context
from .io import QGError, digest, sha, read_json, write_json, write_bytes, canonical, publish_bundle


def prepare(cases, output):
    count, members = 0, {}
    for case_path in sorted(Path(cases).glob("*.json")):
        case = read_json(case_path)
        identity = case["id"]
        if not identity or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in identity):
            raise QGError("INVALID_CASE_ID")
        for arm in ("B0", "B1", "B2"):
            dest = Path(output) / identity / arm
            if dest.exists():
                raise QGError("RUN_ALREADY_EXISTS", 3)
            context = None
            if arm != "B0":
                path = Path(case["contexts"][arm])
                if not path.is_absolute():
                    path = case_path.parent / path
                context = verify_context(read_json(path))
            prompt = (case["baseline"] + "\n\nTASK BRIEF / FACTS / CANON:\n" + case["brief"]
                      + "\n\n" + (context["prompt_payload"] if context else ""))
            run = dict(schema_version="quillgrain.evaluation-run/v1", id=identity + "-" + arm,
                       case_id=identity, group_id=case.get("group_id", identity), split=case.get("split", "development"),
                       arm=arm, engine_version=__version__, pack_revisions=context["packs"] if context else [],
                       model_surface=case.get("model_surface"), model_id=case.get("model_id"),
                       generation_options=case.get("generation_options", {}),
                       input_hash=digest({"brief": case["brief"], "baseline": case["baseline"]}),
                       prompt_hash=sha(prompt.encode("utf-8")), raw_output=None, raw_output_hash=None,
                       edited_output=None, warnings=[], evaluator=None, human_decision=None,
                       status="NOT_RUN", quality_status="HUMAN_REVIEW_PENDING", session_id=None, independence=None)
            validate(run, "evaluation-run")
            prefix = identity + '/' + arm + '/'
            members[prefix + 'prompt.md'] = prompt.encode('utf-8')
            if context:
                members[prefix + 'context.json'] = canonical(context)
            members[prefix + 'run.json'] = canonical(run)
            count += 1
    publish_bundle(output, members)
    return {"packets": count, "status": "NOT_RUN"}


def verify_run(manifest):
    manifest = Path(manifest)
    run = validate(read_json(manifest), 'evaluation-run')
    prompt = (manifest.parent / 'prompt.md').read_bytes()
    if sha(prompt) != run['prompt_hash']:
        raise QGError('PROMPT_MUTATED', 3)
    if run['arm'] != 'B0':
        ctx = verify_context(read_json(manifest.parent / 'context.json'))
        if ctx['packs'] != run['pack_revisions'] or not prompt.endswith(ctx['prompt_payload'].encode('utf-8')):
            raise QGError('CONTEXT_RUN_MISMATCH', 3)
    if run['status'] != 'NOT_RUN':
        raw = (manifest.parent / 'raw-output.md').read_bytes()
        if sha(raw) != run['raw_output_hash'] or raw.decode('utf-8') != run['raw_output']:
            raise QGError('RAW_OUTPUT_MUTATED', 3)
    return run


def record(manifest, output, *, surface=None, model=None, session=None, independence=None, status="LIVE"):
    manifest = Path(manifest)
    run = verify_run(manifest)
    if run["status"] != "NOT_RUN":
        raise QGError("RUN_IMMUTABLE", 3)
    prompt = (manifest.parent / "prompt.md").read_bytes()
    if sha(prompt) != run["prompt_hash"]:
        raise QGError("PROMPT_MUTATED", 3)
    if status == "LIVE" and not all((surface, model, session, independence)):
        raise QGError("LIVE_IDENTITY_REQUIRED")
    raw = Path(output).read_bytes()
    text = raw.decode("utf-8")
    if not text.strip():
        raise QGError("EMPTY_MODEL_OUTPUT")
    if (manifest.parent / 'raw-output.md').exists():
        raise QGError('RAW_OUTPUT_ALREADY_EXISTS', 3)
    write_bytes(manifest.parent / 'raw-output.md', raw)
    run.update(status=status, raw_output=text, raw_output_hash=sha(raw), model_surface=surface,
               model_id=model, session_id=session, independence=independence)
    validate(run, "evaluation-run")
    write_json(manifest, run)
    return {"id": run["id"], "status": status, "quality_status": run["quality_status"]}


def report(runs, output):
    records = [verify_run(p) for p in sorted(Path(runs).rglob('run.json'))]
    counts = dict(Counter(r["status"] for r in records))
    groups = {}
    for run in records:
        groups.setdefault(run["group_id"], []).append(run)
    for group in groups.values():
        if len({r["input_hash"] for r in group}) > 1:
            raise QGError("UNEQUAL_COMPARISON_INPUTS", 3)
        live = [r for r in group if r["status"] == "LIVE"]
        if len({(r["model_surface"], r["model_id"], digest(r["generation_options"])) for r in live}) > 1:
            raise QGError("UNEQUAL_MODEL_CONDITIONS", 3)
    summary = {"counts": counts, "quality_status": "HUMAN_REVIEW_PENDING", 'review_set_id': uuid.uuid4().hex,
               'complete_live_groups': sum({r['arm'] for r in g if r['status'] == 'LIVE'} == {'B0', 'B1', 'B2'} and len(g) == 3 for g in groups.values()),
               'groups': len(groups),
               "independence": "Inspect recorded surface/session declarations; no unobserved guarantees.",
               "generation": "Quillgrain did not call a model."}
    members = {'report.json': canonical(summary)}
    key = []
    live = [r for r in records if r["status"] == "LIVE"]
    random.SystemRandom().shuffle(live)
    for index, run in enumerate(live, 1):
        name = f"sample-{index:02d}.md"
        members['blind/' + name] = run['raw_output'].encode('utf-8')
        key.append({"file": name, "run_id": run["id"]})
    members['review-key.private.json'] = canonical(key)
    publish_bundle(output, members)
    return summary
