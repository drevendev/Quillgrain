"""Portable agent skills; the current assistant remains the writer."""
from importlib.resources import files
from pathlib import Path

from .contracts import verify_context
from .io import QGError, canonical, digest, publish_bundle, read_json


SKILL_ROOTS = {"codex": ".agents/skills/quillgrain", "claude": ".claude/skills/quillgrain"}


def context_members(context, lock):
    verify_context(context)
    if digest(lock) != context['lock_digest']:
        raise QGError('LOCK_DIGEST_MISMATCH', 3)
    header = (f"# Voice context\n\nBuild: `{context['build_id']}`\n\n"
              f"Visibility: **{context['visibility']}** · Host: **{context['model_host']}**\n\n"
              "Use the separate brief for all facts and canon. Review before sharing.\n\n")
    return {'context.json': canonical(context), 'quillgrain.lock.json': canonical(lock),
            'VOICE_CONTEXT.md': (header + context['prompt_payload'] + '\n').encode('utf-8')}


def verify_skill_context(context, host, lock=None):
    verify_context(context)
    if context['model_host'] != host:
        raise QGError('CONTEXT_HOST_MISMATCH', 3)
    if not context['permissions']['retrieval'] or host not in context['permissions']['approved_model_hosts']:
        raise QGError('CONTEXT_HOST_DENIED', 3)
    if lock is not None and digest(lock) != context['lock_digest']:
        raise QGError('LOCK_DIGEST_MISMATCH', 3)
    return context


def skill_members(context=None, lock=None):
    resources = files('quillgrain').joinpath('resources')
    members = {'SKILL.md': resources.joinpath('SKILL.md').read_bytes(),
               'references/cli.md': resources.joinpath('skill-cli.md').read_bytes(),
               'agents/openai.yaml': resources.joinpath('openai.yaml').read_bytes()}
    members['scripts/lengths.py'] = files('quillgrain').joinpath('lengths.py').read_bytes()
    if context is not None:
        members.update({'references/' + name: data for name, data in context_members(context, lock).items()})
    return members


def install(agent, *, project=None, output=None, bundle=None):
    if agent not in SKILL_ROOTS:
        raise QGError('SKILL_AGENT_UNSUPPORTED')
    if (project is None) == (output is None):
        raise QGError('SKILL_DESTINATION_REQUIRED')
    context, lock = None, None
    if bundle is not None:
        bundle = Path(bundle)
        context, lock = read_json(bundle / 'context.json'), read_json(bundle / 'quillgrain.lock.json')
        verify_skill_context(context, agent, lock)
    destination = Path(project) / SKILL_ROOTS[agent] if project is not None else Path(output)
    # Only packaged instructions and verified, derived data are installed. Never
    # copy executable content or arbitrary neighbours from a supplied bundle.
    publish_bundle(destination, skill_members(context, lock))
    return {'status': 'INSTALLED', 'agent': agent, 'skill': 'quillgrain',
            'context_bound': context is not None, 'model_required': False}
