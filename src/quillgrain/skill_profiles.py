"""Build private rules-only multi-register skills from a pinned data recipe.

No model calls, installation, corpus reads or implicit host grants.
Run with python -m quillgrain.skill_profiles --help.
"""
import argparse
import copy
import io
import json
import re
import tempfile
import zipfile
from importlib.resources import files
from pathlib import Path

from .compose import compile_context, load_chain, reference
from .contracts import verify_context
from .io import QGError, bounded, canonical, digest, publish_bundle, read_json, sha, write_json
from .portable_context import verify, load_mode


def context_members(context, lock):
    verify_context(context)
    verify(context, context['model_host'], lock)
    return {'context.json': canonical(context), 'quillgrain.lock.json': canonical(lock),
            'VOICE_CONTEXT.md': (context['prompt_payload'] + '\n').encode('utf-8')}


def skill_text(recipe, host):
    routes = '\n'.join(f"| {label} | `{r}` |" for r, label in recipe['registers'].items())
    notes = '\n'.join(recipe.get('instructions', []))
    return f'''---
name: {recipe['skill_name']}
description: {json.dumps(recipe['description'], ensure_ascii=False)}
---

Write and edit directly in this {host} session with the bundled {recipe['profile']} rules.
Facts, canon, characters and personal experience come from the separate task brief.
The profile is CANDIDATE / HUMAN_REVIEW_PENDING; resemblance is not validated.
No model server, API key, source repository or corpus checkout is required.
Follow a directly requested different voice without mixing this default.

Choose only the relevant {recipe['language']} register:

| Task | Register |
| --- | --- |
{routes}

Default to `{recipe['default_register']}` only when no more specific register fits.
Run the portable verifier using an absolute path inside this skill folder:

```text
python SKILL_DIRECTORY/scripts/voice_context.py --host {host} --register REGISTER --show
```

Read and apply the verified payload. `--verify-all` checks every bundled register.
The verifier checks file/context/lock digests, host, mode and rules-only scope;
it does not authenticate a publisher or measure writing quality.
If execution is unavailable, read the selected context.json and VOICE_CONTEXT.md
at the relative path in references/profile.json; use JSON prompt_payload after
checking mode and host. Report unavailable verification only when material.
On failed verification or denied host, stop applying the profile; do not relabel it.
All paths in the manifest are relative to this skill folder.

{notes}

For an explicit word budget, count the actual draft with the bundled lengths.py:

```text
python SKILL_DIRECTORY/scripts/lengths.py --input DRAFT --min-words MIN --max-words MAX
```

For ordered parts, repeat --input and supply --part-range MIN:MAX once per part.
Before the next part, use --plan-next, --next-range MIN:MAX, the actual prefix
files as --input, and --remaining-range MIN:MAX for each later part. Pass the
overall --min-words/--max-words. A conflict requires reporting infeasible constraints;
an unfinished prefix is not a completed under-length text. Check the part and final
sum afterwards. The exact engine qg-words/v1 counter is bundled unchanged.
No numeric brief means no invented quota. Report a miss; do not pad, silently
regenerate or require an expensive editor. Unavailable execution is NOT_RUN.

Review meaning and prose editorially. Use qg check only for relevant executable
checks in the chosen context; human_review items are not programmatic passes.
Return the useful text first; do not print a mandatory checklist in fiction.
Feedback remains a candidate, not automatic promotion or corpus ingestion.

This private rules-only bundle contains no personal examples. Keep profile files,
manifests and source metadata in personal skill storage; do not copy them into
other projects, public artifacts or messages. Requested writing may be returned
to the owner. Installation, sharing and publishing are separate actions.
'''


def archive(members, folder):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(folder + '/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            out.writestr(info, data)
    return stream.getvalue()


def build(recipe_path, pack, bindings, output):
    recipe_path, pack = Path(recipe_path), Path(pack)
    recipe = read_json(recipe_path)
    if recipe['schema_version'] != 'quillgrain.skill-recipe/v1':
        raise QGError('SKILL_RECIPE_UNSUPPORTED')
    chain = load_chain(pack, bindings)
    refs = [reference(p) for p in chain]
    if refs != recipe['source_profiles']:
        raise QGError('STALE_RECIPE_INPUT', 3)
    if recipe['default_register'] not in recipe['registers']:
        raise QGError('SKILL_DEFAULT_REGISTER_UNAVAILABLE', 3)
    if recipe['visibility'] != 'private' or any(p['status'] == 'VALIDATED' for p in chain):
        raise QGError('CANDIDATE_PRIVATE_RECIPE_REQUIRED', 3)
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', recipe['skill_name']):
        raise QGError('SKILL_NAME_INVALID')
    if not recipe['hosts'] or not set(recipe['hosts']) <= {'codex', 'claude'}:
        raise QGError('SKILL_HOST_UNSUPPORTED')
    assets = {name: bounded(recipe_path.parent, relative).read_bytes()
              for name, relative in recipe.get('assets', {}).items()}
    if any(not n.startswith('references/') or not n.endswith('.md') for n in assets):
        raise QGError('SKILL_ASSET_INVALID')
    engine = files('quillgrain')
    helpers = {name: engine.joinpath(name).read_bytes() for name in
               ('portable_context.py', 'lengths.py', 'skill_profiles.py', 'compose.py', 'contracts.py', 'io.py')}
    result = {}
    receipt = {'schema_version': 'quillgrain.skill-build/v1', 'recipe_digest': digest(recipe),
               'source_profiles': refs, 'engine_files': {k: sha(v) for k, v in helpers.items()}, 'hosts': {}}
    with tempfile.TemporaryDirectory(prefix='qg-profile-') as temporary:
        scratch = Path(temporary)
        for host, settings in recipe['hosts'].items():
            copies = copy.deepcopy(chain)
            denied = [reference(p) for p in chain if host not in p['permissions']['approved_model_hosts']]
            if denied:
                grant = settings.get('rules_only_grant', {})
                if (grant.get('source_profiles') != denied or not grant.get('basis') or
                        not grant.get('id') or grant.get('host') != host):
                    raise QGError('EXPLICIT_RULES_HOST_GRANT_REQUIRED', 3)
            current_bindings = {}
            for i, data in enumerate(copies):
                if host not in data['permissions']['approved_model_hosts']:
                    data['version'] += '-' + settings['snapshot_suffix']
                    data['permissions']['approved_model_hosts'].append(host)
                    data['provenance'].append({'id': grant['id'], 'kind': 'owner_authorization', 'note': grant['basis']})
                if i:
                    data['extends'] = [reference(copies[i - 1])]
                # Grants cover derived rules only. Do not retain example-bearing fields
                # even in intermediate permission snapshots.
                if denied:
                    data['examples'] = []
                    if 'example_refs' in data:
                        data['example_refs'] = []
                directory = scratch / host / str(i)
                write_json(directory / 'voice.json', data)
                current_bindings[data['id']] = directory
            # Example removal changes digests; rebuild parent pins in sequence.
            for i, data in enumerate(copies):
                if i:
                    data['extends'] = [reference(copies[i - 1])]
                write_json(current_bindings[data['id']] / 'voice.json', data)
            wrapper = copy.deepcopy(copies[-1])
            wrapper.update(id=recipe['deployment_id'], version=recipe['deployment_version'],
                           schema_version='quillgrain.voice-pack/v2', compatibility={'engine': '0.1', 'schema': 'v2'},
                           extends=[reference(copies[-1])], visibility='private', status='CANDIDATE',
                           rules=[], examples=[], example_refs=[], evidence_refs=[], corpus_dependencies=[],
                           languages=[recipe['language']], registers=list(recipe['registers']),
                           modes=[{'language': recipe['language'], 'register': r, 'status': 'CANDIDATE'} for r in recipe['registers']])
            wrapper['permissions']['approved_model_hosts'] = [host]
            root = scratch / host / 'deployment'
            write_json(root / 'voice.json', wrapper)
            members = {'SKILL.md': skill_text(recipe, host).encode('utf-8'),
                       'scripts/voice_context.py': helpers['portable_context.py'],
                       'scripts/lengths.py': helpers['lengths.py'], **assets}
            members['agents/openai.yaml'] = (
                'interface:\n  display_name: ' + json.dumps(recipe['display_name'], ensure_ascii=False) +
                '\n  short_description: ' + json.dumps(recipe['short_description'], ensure_ascii=False) +
                '\npolicy:\n  allow_implicit_invocation: true\n').encode('utf-8')
            manifest = {'schema_version': 'quillgrain.skill-profile/v2', 'profile': recipe['profile'],
                        'model_host': host, 'language': recipe['language'], 'visibility': 'private',
                        'source_profiles': refs, 'recipe_digest': digest(recipe), 'modes': {}}
            for register in recipe['registers']:
                context, lock = compile_context(root, bindings=current_bindings, language=recipe['language'],
                                                register=register, target=host, model_host=host,
                                                examples_mode='none', max_chars=recipe['max_chars'])
                if any(r['reason'] == 'budget' for r in context['rules_omitted']):
                    raise QGError('PROFILE_RULE_BUDGET_LOSS', 3)
                artifacts = context_members(context, lock)
                directory = 'references/modes/' + register
                members.update({directory + '/' + n: b for n, b in artifacts.items()})
                manifest['modes'][register] = {'path': directory, 'build_id': context['build_id'],
                                             'files': {n: sha(b) for n, b in artifacts.items()}}
            members['references/profile.json'] = canonical(manifest)
            stage = scratch / host / 'verify' / recipe['skill_name']
            publish_bundle(stage, members)
            for register in recipe['registers']:
                load_mode(stage, register, host)
            result.update({host + '/' + recipe['skill_name'] + '/' + n: b for n, b in members.items()})
            zip_name = host + '.zip'
            result[zip_name] = archive(members, recipe['skill_name'])
            receipt['hosts'][host] = {'archive': zip_name, 'sha256': sha(result[zip_name]),
                                      'files': {n: sha(b) for n, b in members.items()}}
    result['build-receipt.json'] = canonical(receipt)
    publish_bundle(Path(output), result)
    return receipt


def compare(candidate, installed):
    def inventory(root):
        root = Path(root)
        return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*')
                if p.is_file() and not p.is_symlink()}
    if not Path(installed).exists():
        return {'status': 'NOT_INSTALLED', 'added': [], 'removed': [], 'changed': []}
    a, b = inventory(candidate), inventory(installed)
    return {'status': 'IDENTICAL' if a == b else 'DIFFERENT',
            'added': sorted(a.keys() - b.keys()), 'removed': sorted(b.keys() - a.keys()),
            'changed': sorted(k for k in a.keys() & b.keys() if a[k] != b[k])}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe', required=True, type=Path)
    p.add_argument('--pack', required=True, type=Path)
    p.add_argument('--bind', action='append', default=[])
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--compare-installed', type=Path)
    args = p.parse_args(argv)
    try:
        bindings = dict(v.split('=', 1) for v in args.bind)
        receipt = build(args.recipe, args.pack, bindings, args.out)
        report = {'status': 'BUILT', 'hosts': list(receipt['hosts'])}
        if args.compare_installed:
            report['installed'] = compare(args.out / 'codex' / read_json(args.recipe)['skill_name'], args.compare_installed)
        print(json.dumps(report))
        return 0
    except (QGError, ValueError, KeyError, TypeError, OSError):
        print('SKILL_PROFILE_BUILD_FAILED')
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
