import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from quillgrain.compose import compile_context, reference
from quillgrain.contracts import verify_context
from quillgrain.io import QGError, canonical, digest, read_json, write_json
from quillgrain.portable_context import load_mode, verify
from quillgrain.skill_profiles import build, compare


@pytest.fixture
def inputs(tmp_path):
    original = Path(__file__).parents[1] / 'examples/synthetic/common/voice.json'
    pack = read_json(original)
    pack['permissions']['approved_model_hosts'] = ['codex']
    pack['permissions']['public_redistribution'] = False
    write_json(tmp_path / 'pack/voice.json', pack)
    recipe = {
        'schema_version': 'quillgrain.skill-recipe/v1', 'profile': 'Synthetic',
        'skill_name': 'synthetic-voice', 'description': 'Write synthetic Russian prose.',
        'display_name': 'Synthetic voice', 'short_description': 'Write with a synthetic test profile',
        'deployment_id': 'synthetic.deployment', 'deployment_version': '0.1.0',
        'visibility': 'private', 'language': 'ru', 'default_register': 'essay',
        'registers': {'essay': 'Analysis', 'fiction_narration': 'Scenes'},
        'max_chars': 8000, 'source_profiles': [reference(pack)], 'hosts': {'codex': {}},
    }
    write_json(tmp_path / 'recipe.json', recipe)
    return tmp_path, pack, recipe


def test_reproducible_relocatable_rules_only_bundle(inputs):
    root, pack, recipe = inputs
    a = build(root / 'recipe.json', root / 'pack', {}, root / 'a')
    b = build(root / 'recipe.json', root / 'pack', {}, root / 'b')
    assert a == b
    assert (root / 'a/codex.zip').read_bytes() == (root / 'b/codex.zip').read_bytes()
    assert compare(root / 'a', root / 'b')['status'] == 'IDENTICAL'
    moved = root / 'relocated'
    shutil.copytree(root / 'a/codex/synthetic-voice', moved)
    shutil.rmtree(root / 'pack')
    run = subprocess.run([sys.executable, '-I', '-S', str(moved / 'scripts/voice_context.py'),
                          '--host', 'codex', '--verify-all'], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    for register in recipe['registers']:
        context = load_mode(moved, register, 'codex')
        assert not context['examples_selected'] and not context['corpus_materials']
        verify_context(context)
    with pytest.raises(QGError, match='OUTPUT_ALREADY_EXISTS'):
        # Restore the input to exercise the output guard, independently of relocation.
        write_json(root / 'pack/voice.json', pack)
        build(root / 'recipe.json', root / 'pack', {}, root / 'a')


def test_host_grant_must_pin_denied_sources(inputs):
    root, pack, recipe = inputs
    recipe['hosts'] = {'claude': {'snapshot_suffix': 'test.1'}}
    write_json(root / 'recipe.json', recipe)
    with pytest.raises(QGError, match='EXPLICIT_RULES_HOST_GRANT_REQUIRED'):
        build(root / 'recipe.json', root / 'pack', {}, root / 'denied')
    assert not (root / 'denied').exists()
    recipe['hosts']['claude']['rules_only_grant'] = {
        'id': 'synthetic-test-grant', 'host': 'claude', 'basis': 'Synthetic test authorization',
        'source_profiles': [reference(pack)]}
    write_json(root / 'recipe.json', recipe)
    build(root / 'recipe.json', root / 'pack', {}, root / 'allowed')
    skill = root / 'allowed/claude/synthetic-voice'
    assert load_mode(skill, 'essay', 'claude')['permissions']['approved_model_hosts'] == ['claude']
    assert read_json(root / 'pack/voice.json') == pack
    with pytest.raises(ValueError, match='CONTEXT_HOST_MISMATCH'):
        load_mode(skill, 'essay', 'codex')


def test_corruption_mode_and_lock_are_rejected(inputs):
    root, _, _ = inputs
    build(root / 'recipe.json', root / 'pack', {}, root / 'a')
    skill = root / 'a/codex/synthetic-voice'
    path = skill / 'references/modes/essay/context.json'
    original = path.read_bytes()
    path.write_bytes(original + b' ')
    with pytest.raises(ValueError, match='PROFILE_FILE_DIGEST_MISMATCH'):
        load_mode(skill, 'essay', 'codex')
    path.write_bytes(original)
    manifest_path = skill / 'references/profile.json'
    manifest = read_json(manifest_path)
    manifest['modes']['essay'] = copy.deepcopy(manifest['modes']['fiction_narration'])
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match='CONTEXT_MODE_MISMATCH'):
        load_mode(skill, 'essay', 'codex')
    manifest['modes']['essay']['path'] = '../outside'
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match='PATH_ESCAPE'):
        load_mode(skill, 'essay', 'codex')


def test_shared_digest_vectors(inputs):
    root, _, _ = inputs
    build(root / 'recipe.json', root / 'pack', {}, root / 'a')
    mode = root / 'a/codex/synthetic-voice/references/modes/essay'
    context, lock = read_json(mode / 'context.json'), read_json(mode / 'quillgrain.lock.json')
    assert verify_context(context) == verify(context, 'codex', lock)
    for key, value in [('prompt_payload', 'corrupted'), ('build_id', '0' * 64)]:
        bad = {**context, key: value}
        with pytest.raises(QGError):
            verify_context(bad)
        with pytest.raises(ValueError):
            verify(bad, 'codex', lock)
    with pytest.raises(ValueError, match='LOCK_DIGEST_MISMATCH'):
        verify(context, 'codex', {**lock, 'engine_version': 'different'})
    bad = copy.deepcopy(context)
    bad['rules_applied'][0]['scope']['languages'] = ['en']
    bad['build_id'] = digest({k: v for k, v in bad.items() if k != 'build_id'})
    with pytest.raises(QGError, match='CONTEXT_RULE_SCOPE'):
        verify_context(bad)
    with pytest.raises(ValueError, match='CONTEXT_RULE_SCOPE'):
        verify(bad, 'codex', lock)


def test_recipe_pins_and_compare_without_installing(inputs):
    root, pack, recipe = inputs
    recipe['source_profiles'][0]['digest'] = '0' * 64
    write_json(root / 'recipe.json', recipe)
    with pytest.raises(QGError, match='STALE_RECIPE_INPUT'):
        build(root / 'recipe.json', root / 'pack', {}, root / 'stale')
    (root / 'candidate').mkdir(); (root / 'installed').mkdir()
    (root / 'candidate/a').write_bytes(b'new'); (root / 'installed/a').write_bytes(b'old')
    assert compare(root / 'candidate', root / 'installed')['changed'] == ['a']
    assert (root / 'installed/a').read_bytes() == b'old'
