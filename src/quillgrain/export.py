"""Export only the already checked, derived context. No consumer mutation."""
from importlib.resources import files
from pathlib import Path
from .contracts import verify_context
from .io import QGError, sha, canonical, publish_bundle, digest


def export(context, lock, output):
    verify_context(context)
    if digest(lock) != context['lock_digest']:
        raise QGError('LOCK_DIGEST_MISMATCH', 3)
    members = {'context.json': canonical(context), 'quillgrain.lock.json': canonical(lock)}
    if context["target"] == "patchpitch":
        from .consumer import bundle
        members['voice-bundle.json'] = canonical(bundle(context, lock))
    header = (f"# Voice context\n\nBuild: `{context['build_id']}`\n\n"
              f"Visibility: **{context['visibility']}** · Host: **{context['model_host']}**\n\n"
              "Use the separate brief for all facts and canon. Review before sharing.\n\n")
    members['VOICE_CONTEXT.md'] = (header + context['prompt_payload'] + '\n').encode('utf-8')
    if context["target"] == "codex":
        members['.agents/skills/quillgrain/SKILL.md'] = files('quillgrain').joinpath('resources/SKILL.md').read_bytes()
    if context["target"] == "patchpitch-legacy":
        payload = context["prompt_payload"].encode("utf-8")
        if len(context["prompt_payload"]) > 1200:
            raise QGError("PATCHPITCH_LIMIT", 3)
        members['voice_reference.txt'] = payload
        members['voice_reference.manifest.json'] = canonical({
            "build_id": context["build_id"], "sha256": sha(payload), "codepoints": len(context["prompt_payload"]),
            "packs": context["packs"], "visibility": context["visibility"], "model_host": context["model_host"],
            "application": "manual existing voice_reference field", "preset": "record Warm/Clear/Lively in the run"})
    publish_bundle(output, members)
