"""Export only the already checked, derived context. No consumer mutation."""
from .io import QGError, sha, canonical, publish_bundle
from .skills import SKILL_ROOTS, context_members, skill_members


def export(context, lock, output):
    members = context_members(context, lock)
    if context["target"] == "patchpitch":
        from .consumer import bundle
        members['voice-bundle.json'] = canonical(bundle(context, lock))
    if context['target'] in SKILL_ROOTS:
        prefix = SKILL_ROOTS[context['target']] + '/'
        members.update({prefix + name: data for name, data in skill_members(context, lock).items()})
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
