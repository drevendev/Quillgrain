"""Small CLI with stable, privacy-preserving error codes."""
import argparse
import json
import os
import platform
import sys
from pathlib import Path
from . import __version__, corpus, evaluation, feedback, duel, pairwise
from .adapters.scriptorium import analyze, import_observation
from .checks import check
from .compose import compile_context, load_chain
from .export import export
from .io import QGError, read_json, read_jsonl, sha, write_json, publish_bundle, canonical


def parser():
    p = argparse.ArgumentParser(prog="qg", description="Every voice has a grain.")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    cp = commands.add_parser("corpus").add_subparsers(dest="action", required=True)
    inv = cp.add_parser("inventory")
    inv.add_argument("--config", required=True)
    inv.add_argument("--out", required=True)
    prep = cp.add_parser("prepare")
    prep.add_argument("--selection", required=True)
    prep.add_argument("--config")
    prep.add_argument("--out", required=True)
    analysis = commands.add_parser("analyze")
    analysis.add_argument("--input", required=True)
    analysis.add_argument("--provider", choices=["scriptorium"], default="scriptorium")
    analysis.add_argument("--import", dest="import_path")
    analysis.add_argument("--checkout")
    analysis.add_argument("--python")
    analysis.add_argument("--revision")
    analysis.add_argument("--language", default="ru")
    analysis.add_argument("--register", default="essay")
    analysis.add_argument("--require-provider", action="store_true")
    analysis.add_argument("--out", required=True)
    pk = commands.add_parser("pack").add_subparsers(dest="action", required=True)
    for action in ("validate", "build"):
        cmd = pk.add_parser(action)
        cmd.add_argument("--pack", required=True, type=Path)
        cmd.add_argument("--bind", action="append", default=[], metavar="ID=PATH")
        if action == "build":
            cmd.add_argument("--register", required=True)
            cmd.add_argument("--language", default="ru")
            cmd.add_argument("--target", choices=["chatgpt", "codex", "patchpitch-legacy", "patchpitch"], default="chatgpt")
            cmd.add_argument("--host", default=None)
            cmd.add_argument("--tag", action="append", default=[])
            cmd.add_argument("--example-pool", help="Use only examples carrying this explicitly selected tag")
            cmd.add_argument("--max-chars", type=int, default=8000)
            cmd.add_argument("--public", action="store_true")
            cmd.add_argument("--lock")
            cmd.add_argument("--out", required=True)
    ck = commands.add_parser("check")
    ck.add_argument("--draft", required=True)
    ck.add_argument("--context", required=True)
    ck.add_argument("--scopes")
    ck.add_argument("--out", required=True)
    fb = commands.add_parser("feedback").add_subparsers(dest="action", required=True).add_parser("record")
    for name in ("before", "after", "context", "note", "out"):
        fb.add_argument("--" + name, required=True)
    fb.add_argument("--reason", default="unknown", choices=["voice", "fact", "structure", "taste", "project_constraint", "one_off", "unknown"])
    fb.add_argument("--run-id", default="unknown")
    fb.add_argument("--propose", action="append", default=[])
    ev = commands.add_parser("eval").add_subparsers(dest="action", required=True)
    ep = ev.add_parser("prepare")
    ep.add_argument("--cases", required=True)
    ep.add_argument("--out", required=True)
    er = ev.add_parser("record")
    er.add_argument("--manifest", required=True)
    er.add_argument("--output", required=True)
    for option in ("surface", "model", "session", "independence"):
        er.add_argument("--" + option)
    er.add_argument("--status", choices=["LIVE", "MOCK", "FAILED"], default="LIVE")
    rp = ev.add_parser("report")
    rp.add_argument("--runs", required=True)
    rp.add_argument("--out", required=True)
    du = commands.add_parser('duel').add_subparsers(dest='action', required=True)
    ds = du.add_parser('serve')
    ds.add_argument('--session', required=True)
    ds.add_argument('--port', type=int, default=8767)
    for name in ('prepare', 'pair-prepare'):
        dp = du.add_parser(name)
        dp.add_argument('--cases', required=True)
        dp.add_argument('--out', required=True)
        dp.add_argument('--order-seed', type=int, required=True)
        dp.add_argument('--mapping-seed', type=int, required=True)
        dp.add_argument('--synthetic', action='store_true')
        if name == 'pair-prepare':
            dp.add_argument('--reference-works', help='JSON array of Common/reference work IDs to exclude')
            dp.add_argument('--blog-category', choices=['denis', 'techprose'], default='denis', help='Explicit approved category replacement')
    for action in ('reveal', 'pair-reveal'):
        dr = du.add_parser(action)
        for name in ('session','answers','key','out'):
            dr.add_argument('--'+name, required=True)
    return p


def text(path):
    return Path(path).read_bytes().decode("utf-8-sig")


def run(a):
    if a.command == 'duel':
        if a.action == 'serve':
            duel.serve(a.session, port=a.port)
            return {'status':'STOPPED'}
        engine = pairwise if a.action.startswith('pair-') else duel
        if a.action in ('prepare', 'pair-prepare'):
            cases = read_json(a.cases)
            extra = {'reference_works': read_json(a.reference_works) if a.reference_works else None, 'blog_group': a.blog_category} if a.action == 'pair-prepare' else {}
            blind, _ = engine.make_session(cases, a.out, order_seed=a.order_seed,
                mapping_seed=a.mapping_seed, synthetic=a.synthetic, **extra)
            return {'status':'READY_FOR_OWNER' if not a.synthetic else 'SYNTHETIC', 'cases':len(blind['cases']),
                    'session_id':blind['session_id'], 'correspondence':'WITHHELD'}
        revealed = engine.reveal(read_json(a.session), read_json(a.answers), read_json(a.key))
        publish_bundle(a.out, {'reveal.json':canonical(revealed)})
        return {'status':'REVEAL_PREPARED', 'cases':len(revealed['cases'])}
    if a.command == "doctor":
        return dict(engine=__version__, python=platform.python_version(), platform=platform.system(),
                    model_required=False, telemetry=False, scriptorium="OPTIONAL_NOT_PROBED")
    if a.command == "corpus":
        cfg = a.config
        if not cfg:
            private_home = os.environ.get("QUILLGRAIN_PRIVATE_HOME")
            if not private_home:
                raise QGError("PRIVATE_CONFIG_REQUIRED")
            cfg = str(Path(private_home) / "config/source-roots.local.json")
        config = read_json(cfg)
        if a.action == "inventory":
            return corpus.inventory(config, a.out)
        return corpus.prepare(read_jsonl(a.selection), config, a.out)
    if a.command == "pack":
        bindings = {}
        for binding in a.bind:
            if "=" not in binding:
                raise QGError("BINDING_REQUIRES_ID_EQUALS_PATH")
            identity, path = binding.split("=", 1)
            if identity in bindings:
                raise QGError("DUPLICATE_BINDING")
            bindings[identity] = Path(path)
        if a.action == "validate":
            chain = load_chain(a.pack, bindings)
            final = chain[-1]
            modes = final.get("modes", [{"language": lang, "register": reg} for lang in final["languages"] for reg in final["registers"]])
            if final["permissions"]["retrieval"] and final["permissions"]["approved_model_hosts"]:
                for mode in modes:
                    compile_context(a.pack, bindings=bindings, language=mode["language"], register=mode["register"],
                                    model_host=final["permissions"]["approved_model_hosts"][0], max_chars=1000000)
            return {"status": "VALID", "packs": [p["id"] for p in chain]}
        host = a.host or {"chatgpt": "chatgpt", "codex": "codex", "patchpitch-legacy": "ollama", "patchpitch": "ollama"}[a.target]
        try:
            context, lock = compile_context(a.pack, bindings=bindings, register=a.register, language=a.language,
                                            target=a.target, model_host=host, tags=a.tag, max_chars=a.max_chars,
                                            public=a.public, lock=a.lock, example_pool=a.example_pool)
        except QGError as exc:
            # Keep potentially private rule IDs in the explicitly chosen local output,
            # while terminal diagnostics remain short and path/text-free.
            try:
                publish_bundle(a.out, {'build-error.json':canonical({
                    'status':'CONFLICT' if 'CONFLICT' in exc.code else 'ERROR',
                    'code':exc.code, 'details':{} if a.public else exc.details})})
            except QGError:
                pass  # Never contaminate an occupied export or follow its links on failure.
            raise
        export(context, lock, a.out)
        return {"status": "BUILT", "build_id": context["build_id"], "visibility": context["visibility"],
                "codepoints": context["budget"]["used_codepoints"], "warnings": context["warnings"]}
    if a.command == "check":
        result = check(text(a.draft), read_json(a.context), read_json(a.scopes) if a.scopes else [])
        write_json(a.out, result)
        if result["errors"] or any(f["severity"] == "error" for f in result["findings"]):
            raise QGError("CHECK_FAILED", 3)
        return {"findings": len(result["findings"]), "human_review_checks": len(result["skipped_checks"])}
    if a.command == "analyze":
        prepared = text(a.input)
        result = import_observation(a.import_path, sha(prepared.encode("utf-8"))) if a.import_path else analyze(
            prepared, a.checkout, a.python, a.revision, a.language, a.register)
        write_json(a.out, result)
        if a.require_provider and result["status"] == "METRICS_NOT_RUN":
            raise QGError("PROVIDER_UNAVAILABLE", 4)
        return {"status": result.get("status", "IMPORTED")}
    if a.command == "feedback":
        result = feedback.record(text(a.before), text(a.after), read_json(a.context), text(a.note),
                                 reason=a.reason, run_id=a.run_id, proposed=a.propose)
        write_json(a.out, result)
        return {"status": "CANDIDATE", "rules_activated": 0}
    if a.command == "eval":
        if a.action == "prepare":
            return evaluation.prepare(a.cases, a.out)
        if a.action == "record":
            return evaluation.record(a.manifest, a.output, surface=a.surface, model=a.model,
                                     session=a.session, independence=a.independence, status=a.status)
        return evaluation.report(a.runs, a.out)


def main(argv=None):
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except QGError as exc:
        print(exc.code, file=sys.stderr)
        return exc.exit_code
    except (json.JSONDecodeError, UnicodeError, KeyError, ValueError, TypeError):
        print("INVALID_INPUT", file=sys.stderr)
        return 2
    except (OSError, RuntimeError):
        print("IO_OR_RUNTIME_ERROR", file=sys.stderr)
        return 5
