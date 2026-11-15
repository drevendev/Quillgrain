"""Portable agent skills; the current assistant remains the writer."""
from importlib.resources import files
import json
import posixpath
import re
from pathlib import Path, PurePosixPath

from .contracts import verify_context
from .io import QGError, canonical, publish_bundle, read_json, is_link
from .portable import verify_host, verify_lock


SKILL_ROOTS = {"codex": ".agents/skills/quillgrain", "claude": ".claude/skills/quillgrain"}


def skill_name(context=None, requested=None):
    name = requested
    if name is None:
        identity = context['packs'][-1]['id'] if context is not None else None
        name = 'quillgrain-' + identity.removeprefix('quillgrain.').replace('.', '-') if identity else 'quillgrain'
    if not isinstance(name, str) or len(name) > 64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        raise QGError('SKILL_NAME_INVALID', 3)
    return name


def skill_path(agent, name):
    if agent not in SKILL_ROOTS:
        raise QGError('SKILL_AGENT_UNSUPPORTED')
    return Path(SKILL_ROOTS[agent]).parent / name


def context_members(context, lock):
    verify_context(context)
    verify_lock(context, lock)
    header = (f"# Voice context\n\nBuild: `{context['build_id']}`\n\n"
              f"Visibility: **{context['visibility']}** · Host: **{context['model_host']}**\n\n"
              "Use the separate brief for all facts and canon. Review before sharing.\n\n")
    return {'context.json': canonical(context), 'quillgrain.lock.json': canonical(lock),
            'VOICE_CONTEXT.md': (header + context['prompt_payload'] + '\n').encode('utf-8')}


def verify_skill_context(context, host, lock=None):
    verify_context(context)
    return verify_host(context, host, lock)


def skill_members(context=None, lock=None, *, name=None, agent=None):
    resources = files('quillgrain').joinpath('resources')
    name = skill_name(context, name)
    if context is not None:
        verify_skill_context(context, agent or context['model_host'], lock)
    role = 'Generic tool; use the explicitly selected voice.'
    if context is not None:
        pack = context['packs'][-1]
        role = f"Bound voice {pack['id']} {pack['version']}; build {context['build_id']}."
    instructions = resources.joinpath('SKILL.md').read_text(encoding='utf-8')
    instructions = instructions.replace('name: quillgrain', 'name: ' + name, 1)
    instructions = re.sub(r'^description: (.*)$', lambda m: 'description: ' + json.dumps(m[1] + ' ' + role),
                          instructions, count=1, flags=re.M)
    guide = resources.joinpath('skill-cli.md').read_text(encoding='utf-8')
    ui = ('interface:\n  display_name: ' + json.dumps(name) + '\n  short_description: '
          + json.dumps('Selected voice' if context is not None else 'Choose a voice and write or edit')
          + '\n  default_prompt: ' + json.dumps('Use $' + name + ' with my task brief and chosen voice.') + '\n')
    members = {'SKILL.md': instructions.encode('utf-8'), 'references/cli.md': guide.encode('utf-8'),
               'agents/openai.yaml': ui.encode('utf-8')}
    for path in ('SKILL.md', 'references/cli.md'):
        members[path] = members[path].replace(b'$quillgrain', ('$' + name).encode()).replace(
            b'/quillgrain ', ('/' + name + ' ').encode())
    members['scripts/lengths.py'] = files('quillgrain').joinpath('lengths.py').read_bytes()
    members['scripts/voice_context.py'] = files('quillgrain').joinpath('portable.py').read_bytes()
    if context is not None:
        members.update({'references/' + name: data for name, data in context_members(context, lock).items()})
    return members


def validate_skill_tree(root, *, expected_name=None, final_name=None):
    """Inspect the generated staging tree before publishing it as a ready skill."""
    root = Path(root)
    name = skill_name(requested=expected_name or root.name)
    if (final_name or root.name) != name:
        raise QGError('SKILL_NAME_MISMATCH', 3)
    for path in root.rglob('*'):
        if is_link(path):
            raise QGError('SKILL_RESOURCE_LINK_DENIED', 3)
    source = (root / 'SKILL.md').read_text(encoding='utf-8')
    match = re.match(r'\A---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---\n', source)
    if not match or match[1] != name or not match[2].strip():
        raise QGError('SKILL_FRONTMATTER_INVALID', 3)
    description = json.loads(match[2]) if match[2].startswith('"') else match[2]
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise QGError('SKILL_DESCRIPTION_INVALID', 3)
    for rel in ('references/cli.md', 'agents/openai.yaml', 'scripts/lengths.py', 'scripts/voice_context.py'):
        if not (root / rel).is_file():
            raise QGError('SKILL_RESOURCE_MISSING', 3)
    for md in root.rglob('*.md'):
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', md.read_text(encoding='utf-8')):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', link) or link.startswith('#'):
                continue
            target = posixpath.normpath(str(md.relative_to(root).parent.as_posix()) + '/' + link.split('#')[0])
            if PurePosixPath(target).is_absolute() or '..' in PurePosixPath(target).parts or not (root / target).is_file():
                raise QGError('SKILL_RESOURCE_MISSING', 3)
    return {'status': 'VALID', 'name': name}


def standard_user_roots(agent):
    return ([Path.home() / '.agents/skills', Path.home() / '.codex/skills'] if agent == 'codex'
            else [Path.home() / '.claude/skills'])


def collision_diagnostics(agent, name, *, project=None, user_roots=None):
    roots = list(user_roots) if user_roots is not None else standard_user_roots(agent)
    if project is not None:
        roots.append(Path(project) / Path(SKILL_ROOTS[agent]).parent)
    checked, matches = [], []
    for root in dict.fromkeys(Path(r).absolute() for r in roots):
        checked.append(str(root))
        candidate = root / name
        if (candidate / 'SKILL.md').is_file():
            item = {'path': str(candidate), 'name': name, 'role': 'UNKNOWN', 'build_id': 'UNKNOWN'}
            context_file = candidate / 'references/context.json'
            if context_file.is_file() and context_file.stat().st_size <= 16 * 1024 * 1024:
                try:
                    context = verify_skill_context(read_json(context_file), agent)
                    item.update(role='bound', build_id=context['build_id'], packs=context['packs'])
                except (QGError, OSError, ValueError, TypeError, KeyError):
                    item['role'] = 'UNVERIFIED'
            matches.append(item)
    return {'checked_locations': checked, 'same_name': matches, 'scope': 'KNOWN_LOCATIONS_ONLY'}


def install(agent, *, project=None, output=None, bundle=None, name=None, user_roots=None):
    if agent not in SKILL_ROOTS:
        raise QGError('SKILL_AGENT_UNSUPPORTED')
    if (project is None) == (output is None):
        raise QGError('SKILL_DESTINATION_REQUIRED')
    context, lock = None, None
    if bundle is not None:
        bundle = Path(bundle)
        context, lock = read_json(bundle / 'context.json'), read_json(bundle / 'quillgrain.lock.json')
        verify_skill_context(context, agent, lock)
    name = skill_name(context, name)
    destination = Path(project) / skill_path(agent, name) if project is not None else Path(output)
    if destination.name != name:
        raise QGError('SKILL_NAME_MISMATCH', 3)
    diagnostics = collision_diagnostics(agent, name, project=project, user_roots=user_roots)
    # Only packaged instructions and verified, derived data are installed. Never
    # copy executable content or arbitrary neighbours from a supplied bundle.
    publish_bundle(destination, skill_members(context, lock, name=name, agent=agent),
                   validator=lambda root: validate_skill_tree(root, expected_name=name, final_name=destination.name))
    return {'status': 'INSTALLED', 'agent': agent, 'skill': name, 'destination': str(destination),
            'context_bound': context is not None, 'model_required': False, 'collisions': diagnostics}
