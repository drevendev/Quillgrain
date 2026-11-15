"""Public synthetic export acceptance, including a Python-only relocated skill."""
import copy
import json
import shutil
import subprocess
import sys

import pytest

from quillgrain import portable, skills
from quillgrain.cli import main
from quillgrain.compose import compile_context
from quillgrain.contracts import verify_context
from quillgrain.export import export
from quillgrain.io import QGError, digest, read_json, write_json
from test_catalog import corpus_setup, build


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_export_rejects_incompatible_and_denied_host_before_publication(agent, pack, save, tmp_path):
    path = save(pack)
    out = tmp_path / 'bad'
    assert main(['pack', 'build', '--pack', str(path), '--register', 'essay', '--target', agent,
                 '--host', 'ollama', '--out', str(out)]) == 3
    assert not out.exists()
    ctx, lock = compile_context(path, target=agent, model_host=agent)
    ctx['permissions']['retrieval'] = False
    ctx['build_id'] = digest({k: v for k, v in ctx.items() if k != 'build_id'})
    with pytest.raises(QGError, match='HOST_DENIED'):
        export(ctx, lock, out)
    assert not out.exists()


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_name_and_generated_tree_validation(agent, tmp_path):
    dest = tmp_path / 'wrong'
    with pytest.raises(QGError, match='NAME_MISMATCH'):
        skills.install(agent, output=dest, user_roots=[])
    assert not dest.exists()
    result = skills.install(agent, output=dest, name='wrong', user_roots=[])
    assert result['skill'] == 'wrong'
    assert skills.validate_skill_tree(dest)['name'] == 'wrong'
    assert '$wrong' in (dest / 'agents/openai.yaml').read_text()
    source = dest / 'SKILL.md'
    source.write_text(source.read_text(encoding='utf-8') + '\n[Missing](references/absent.md)\n', encoding='utf-8')
    with pytest.raises(QGError, match='RESOURCE_MISSING'):
        skills.validate_skill_tree(dest)


@pytest.mark.parametrize('name', ['Upper', '-bad', 'bad-', 'bad--name', '../escape', 'x'*65, 'голос'])
def test_invalid_names_are_never_installed(name, tmp_path):
    with pytest.raises(QGError, match='NAME_INVALID'):
        skills.install('codex', project=tmp_path, name=name, user_roots=[])
    assert not list(tmp_path.iterdir())


def test_failed_staging_validation_does_not_leave_a_ready_skill(tmp_path, monkeypatch):
    original = skills.skill_members
    def incomplete(*args, **kwargs):
        members = original(*args, **kwargs)
        del members['scripts/voice_context.py']
        return members
    monkeypatch.setattr(skills, 'skill_members', incomplete)
    with pytest.raises(QGError, match='RESOURCE_MISSING'):
        skills.install('codex', output=tmp_path / 'quillgrain', user_roots=[])
    assert not list(tmp_path.iterdir())


def test_known_same_name_diagnostics_preserve_both_profiles(pack, save, tmp_path):
    ctx, lock = compile_context(save(pack), target='codex', model_host='codex')
    first = tmp_path / 'first'; export(ctx, lock, first)
    user = tmp_path / 'user'
    installed = skills.install('codex', output=user / 'shared', bundle=first, name='shared', user_roots=[])
    before = (user / 'shared/references/context.json').read_bytes()
    pack['id'] = 'quillgrain.other'
    ctx2, lock2 = compile_context(save(pack, 'other'), target='codex', model_host='codex')
    second = tmp_path / 'second'; export(ctx2, lock2, second)
    result = skills.install('codex', project=tmp_path / 'project', bundle=second, name='shared', user_roots=[user])
    assert result['collisions']['same_name'][0]['build_id'] == ctx['build_id']
    assert result['collisions']['same_name'][0]['packs'] != ctx2['packs']
    assert (user / 'shared/references/context.json').read_bytes() == before
    assert 'Bound voice quillgrain.other' in (tmp_path / 'project/.agents/skills/shared/SKILL.md').read_text()


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_relocated_helper_runs_without_site_packages_or_engine(agent, pack, save, tmp_path):
    source = save(pack)
    ctx, lock = compile_context(source, target=agent, model_host=agent)
    out = tmp_path / 'export'; export(ctx, lock, out)
    relocated = tmp_path / 'quillgrain-synthetic'
    shutil.copytree(out / skills.skill_path(agent, relocated.name), relocated)
    out.rename(tmp_path / 'unavailable-export'); source.rename(tmp_path / 'unavailable-pack')
    script = relocated / 'scripts/voice_context.py'
    command = [sys.executable, '-I', '-S', str(script), '--host', agent]
    run = subprocess.run(command + ['--show'], capture_output=True, encoding='utf-8', check=True)
    assert run.stdout.rstrip('\r\n') == ctx['prompt_payload']
    meta = json.loads(subprocess.run(command, capture_output=True, encoding='utf-8', check=True).stdout)
    assert meta['lock_verified'] and meta['full_json_schema'] == 'NOT_RUN'
    assert meta['rule_methods']['human_review'] == 1
    write_json(relocated / 'references/quillgrain.lock.json', {**lock, 'engine_version': 'tampered'})
    run = subprocess.run(command, capture_output=True, encoding='utf-8')
    assert run.returncode == 3 and run.stdout == '' and 'LOCK_DIGEST_MISMATCH' in run.stderr


def test_engine_and_portable_share_v2_lineage_and_lock_vectors(corpus_setup):
    ctx, lock = build(corpus_setup, model_host='codex')
    assert portable.verify_host(ctx, 'codex', lock) == skills.verify_skill_context(ctx, 'codex', lock)
    for mutate, code in [
        (lambda c: c['corpus_materials'][0].update(sha256='0'*64), 'LINEAGE'),
        (lambda c: c['budget'].update(max_codepoints=1), 'BUDGET'),
        (lambda c: c['permissions'].update(approved_model_hosts=['ollama']), 'HOST_DENIED'),
    ]:
        changed = copy.deepcopy(ctx); mutate(changed)
        changed['build_id'] = digest({k: v for k, v in changed.items() if k != 'build_id'})
        for verifier in (portable.verify_host, skills.verify_skill_context):
            with pytest.raises(QGError, match=code): verifier(changed, 'codex', lock)


def test_portable_rejects_unknown_versions_and_ambiguous_json(pack, save):
    ctx, _ = compile_context(save(pack))
    ctx['schema_version'] = 'quillgrain.compiled-context/v99'
    with pytest.raises(QGError, match='VERSION_UNSUPPORTED'):
        portable.verify_context(ctx)
    for value in ('{"x":1,"x":2}', '{"x":1e999}', '{"x":NaN}'):
        with pytest.raises(QGError): portable.strict_json(value)


def test_skill_name_is_not_silently_ignored_by_other_targets(pack, save, tmp_path):
    ctx,lock=compile_context(save(pack),target='chatgpt')
    with pytest.raises(QGError,match='TARGET_UNSUPPORTED'):
        export(ctx,lock,tmp_path/'no-skill',name='chosen')
    assert not (tmp_path/'no-skill').exists()
