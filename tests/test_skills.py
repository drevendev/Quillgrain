import shutil

import pytest

from quillgrain.cli import main
from quillgrain.compose import compile_context
from quillgrain.contracts import verify_context
from quillgrain.export import export
from quillgrain.io import QGError, digest, read_json, write_json
from quillgrain.skills import SKILL_ROOTS, install, verify_skill_context, skill_path


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_cli_builds_a_relocatable_bound_skill(agent, pack, save, tmp_path):
    source = save(pack)
    output = tmp_path / 'export'
    assert main(['pack', 'build', '--pack', str(source), '--register', 'essay',
                 '--target', agent, '--out', str(output)]) == 0
    context = read_json(output / 'context.json')
    assert context['model_host'] == agent
    skill = output / skill_path(agent, 'quillgrain-synthetic')
    # Move only the skill; neither the export nor its original pack remains here.
    relocated = tmp_path / 'another-project' / skill_path(agent, 'quillgrain-synthetic')
    shutil.copytree(skill, relocated)
    output.rename(tmp_path / 'old-export')
    source.rename(tmp_path / 'old-pack')
    references = relocated / 'references'
    assert read_json(references / 'context.json') == context
    assert main(['context', 'verify', '--context', str(references / 'context.json'),
                 '--host', agent, '--lock', str(references / 'quillgrain.lock.json')]) == 0
    draft = tmp_path / 'draft.md'
    draft.write_text('Лампа освещает стол.', encoding='utf-8')
    assert main(['check', '--draft', str(draft), '--context', str(references / 'context.json'),
                 '--out', str(tmp_path / 'report.json')]) == 0
    assert (relocated / 'SKILL.md').is_file()
    assert (relocated / 'agents/openai.yaml').is_file()
    assert (references / 'cli.md').is_file()
    assert context['prompt_payload'] in (references / 'VOICE_CONTEXT.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_generic_install_is_data_free_and_never_overwrites(agent, tmp_path):
    project = tmp_path / 'project'
    args = ['skill', 'install', '--agent', agent, '--project', str(project)]
    assert main(args) == 0
    installed = project / SKILL_ROOTS[agent]
    assert {p.relative_to(installed).as_posix() for p in installed.rglob('*') if p.is_file()} == {
        'SKILL.md', 'references/cli.md', 'agents/openai.yaml', 'scripts/lengths.py', 'scripts/voice_context.py'}
    original = (installed / 'SKILL.md').read_bytes()
    assert main(args) == 3
    assert (installed / 'SKILL.md').read_bytes() == original


def test_bound_install_regenerates_markdown_and_ignores_bundle_code(pack, save, tmp_path):
    context, lock = compile_context(save(pack), target='codex', model_host='codex')
    bundle = tmp_path / 'export'
    export(context, lock, bundle)
    (bundle / 'VOICE_CONTEXT.md').write_text('unverified replacement', encoding='utf-8')
    (bundle / 'run.py').write_text('raise RuntimeError("must not run")', encoding='utf-8')
    destination = tmp_path / 'portable-skill'
    assert main(['skill', 'install', '--agent', 'codex', '--bundle', str(bundle),
                 '--out', str(destination), '--skill-name', 'portable-skill']) == 0
    assert (destination / 'references/VOICE_CONTEXT.md').read_bytes() != (bundle / 'VOICE_CONTEXT.md').read_bytes()
    assert context['prompt_payload'] in (destination / 'references/VOICE_CONTEXT.md').read_text(encoding='utf-8')
    assert not (destination / 'run.py').exists()
    assert not (destination / 'references/run.py').exists()


def test_bound_install_refuses_cross_host_and_tampered_data(pack, save, tmp_path):
    context, lock = compile_context(save(pack), target='codex', model_host='codex')
    bundle = tmp_path / 'bundle'
    export(context, lock, bundle)
    destination = tmp_path / 'must-not-exist'
    with pytest.raises(QGError, match='CONTEXT_HOST_MISMATCH'):
        install('claude', output=destination, bundle=bundle)
    assert not destination.exists()
    changed = dict(context, prompt_payload=context['prompt_payload'] + 'changed')
    write_json(bundle / 'context.json', changed)
    with pytest.raises(QGError, match='CONTEXT_DIGEST_MISMATCH'):
        install('codex', output=destination, bundle=bundle)
    write_json(bundle / 'context.json', context)
    write_json(bundle / 'quillgrain.lock.json', dict(lock, engine_version='changed'))
    with pytest.raises(QGError, match='LOCK_DIGEST_MISMATCH'):
        install('codex', output=destination, bundle=bundle)
    assert not destination.exists()


def test_host_verification_checks_permissions_not_just_digest(pack, save):
    context, lock = compile_context(save(pack), model_host='codex')
    context['permissions']['approved_model_hosts'] = ['ollama']
    context['build_id'] = digest({k: v for k, v in context.items() if k != 'build_id'})
    verify_context(context)
    with pytest.raises(QGError, match='CONTEXT_HOST_DENIED'):
        verify_skill_context(context, 'codex', lock)


def test_claude_target_does_not_expand_pack_permissions(pack, save, tmp_path):
    pack['permissions']['approved_model_hosts'] = ['ollama', 'codex']
    path = save(pack)
    original = (path / 'voice.json').read_bytes()
    assert main(['pack', 'build', '--pack', str(path), '--register', 'essay',
                 '--target', 'claude', '--out', str(tmp_path / 'denied')]) == 3
    assert (path / 'voice.json').read_bytes() == original
    assert not (tmp_path / 'denied').exists()


def test_install_rejects_linked_destination(tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    link = tmp_path / 'linked'
    try:
        link.symlink_to(other, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable')
    with pytest.raises(QGError, match='OUTPUT_LINK_DENIED'):
        install('codex', output=link / 'quillgrain')
    assert not list(other.iterdir())
