"""Original synthetic corpus fixtures; private writing is never required by tests."""
import copy
import shutil
from pathlib import Path
import pytest
from quillgrain import catalog
from quillgrain.compose import compile_context, reference
from quillgrain.consumer import bundle, verify_bundle
from quillgrain.contracts import verify_context
from quillgrain.io import QGError, sha, write_json, read_json


@pytest.fixture
def corpus_setup(tmp_path, pack, save):
    root = tmp_path / 'corpus'
    approval = dict(by='synthetic-test', basis='Original synthetic fixture storage')
    catalog.init(root, approval=approval)
    permissions = copy.deepcopy(pack['permissions'])
    permissions.update(public_redistribution=False)
    metadata = dict(schema_version='quillgrain.corpus-source/v1', id='source.synthetic', work_id='work.synthetic',
                    title='Fictional lamp', authorship='synthetic_ai_prepared', language='ru', registers=['essay'],
                    tags=['lighting'], usage='reference', visibility='private', permissions=permissions,
                    storage=dict(mode='full', approval=approval), origin=dict(kind='synthetic', reference='', credits=['Original fixture'], notes=[]),
                    revoked=False, revisions=[])
    text = 'The fictional lamp lights a small desk. A switch changes the brightness.'
    rev = catalog.ingest(root, metadata, text.encode(), text)
    fragment = dict(schema_version='quillgrain.corpus-fragment/v1', id='fragment.synthetic', source_id=metadata['id'],
                    revision_id=rev['id'], start=0, end=len(text), sha256=sha(text.encode()), channel='narration',
                    authorship=metadata['authorship'], status='REVIEWED', tags=[])
    catalog.add_fragment(root, fragment)
    ref = dict(id='example.synthetic', corpus_id='quillgrain.corpus', source_id=metadata['id'], work_id=metadata['work_id'],
               revision_id=rev['id'], fragment_id=fragment['id'], sha256=fragment['sha256'], language='ru', register='essay',
               tags=['examples.synthetic'], priority=70, role='positive', status='REVIEWED', permissions=permissions, visibility='private')
    pack.update(schema_version='quillgrain.voice-pack/v2', compatibility={'engine':'0.1','schema':'v2'}, visibility='private',
                permissions=permissions, corpus_dependencies=[catalog.load(root)['identity']], example_refs=[ref], evidence_refs=[])
    path = save(pack)
    return root, metadata, rev, fragment, ref, pack, path


def build(setup, **kwargs):
    root, _, _, _, _, _, path = setup
    return compile_context(path, corpus_bindings={'quillgrain.corpus':root}, tags=['examples.synthetic'], **kwargs)


def test_roundtrip_portability_and_explanation(corpus_setup, tmp_path):
    root, metadata, rev, fragment, ref, pack, path = corpus_setup
    catalog.load(root, verify_content=True)
    ctx, lock = build(corpus_setup)
    verify_bundle(bundle(ctx, lock))
    relocated = tmp_path / 'elsewhere'
    shutil.copytree(root, relocated)
    again, _ = compile_context(path, corpus_bindings={'quillgrain.corpus':relocated}, tags=['examples.synthetic'])
    assert ctx == again
    assert ctx['corpus_materials'][0]['sha256'] == fragment['sha256']
    assert catalog.explain(ctx)['materials'] == ctx['corpus_materials']
    assert catalog.search(catalog.load(root), tags=['lighting'])[0]['id'] == metadata['id']


def test_rules_only_needs_no_corpus_and_no_silent_fallback(corpus_setup):
    root, _, _, _, _, _, path = corpus_setup
    ctx, lock = compile_context(path, examples_mode='none')
    assert not ctx['examples_selected'] and not ctx['corpus_materials']
    assert 'CORPUS_NOT_LOADED:RULES_ONLY' in ctx['warnings']
    verify_bundle(bundle(ctx, lock))
    with pytest.raises(QGError, match='CORPUS_UNAVAILABLE'):
        compile_context(path, tags=['examples.synthetic'])


def test_no_read_for_unselected_references(corpus_setup):
    *_, path = corpus_setup
    ctx, _ = compile_context(path)
    assert not ctx['examples_selected']
    assert {'id':'example.synthetic','reason':'explicit_tags'} in ctx['examples_omitted']


def test_content_tamper_and_fragment_ranges(corpus_setup):
    root, _, rev, fragment, *_ = corpus_setup
    (root / 'objects' / rev['text_sha256']).write_bytes(b'corrupted')
    with pytest.raises(QGError, match='CORPUS_OBJECT_MUTATED'):
        build(corpus_setup)
    with pytest.raises(QGError, match='CORPUS_OBJECT_MUTATED'):
        catalog.load(root, verify_content=True)


def test_stale_dependency_and_revocation(corpus_setup):
    root, metadata, _, _, _, pack, path = corpus_setup
    metadata_path = root / 'sources' / metadata['id'] / 'source.json'
    value = read_json(metadata_path)
    value['revoked'] = True
    write_json(metadata_path, value)
    with pytest.raises(QGError, match='STALE_CORPUS'):
        build(corpus_setup)
    pack['corpus_dependencies'] = [catalog.load(root)['identity']]
    write_json(path / 'voice.json', pack)
    with pytest.raises(QGError, match='CORPUS_HOST_OR_RETRIEVAL_DENIED'):
        build(corpus_setup)


@pytest.mark.parametrize('mutation,error', [('usage','EVALUATION'),('protected','EVALUATION'),('host','HOST_OR_RETRIEVAL'),('unknown','AUTHORSHIP'),('range','RANGE')])
def test_permission_split_and_review_barriers(corpus_setup, mutation, error):
    root, metadata, _, fragment, _, pack, path = corpus_setup
    sp = root / 'sources' / metadata['id'] / 'source.json'
    fp = root / 'fragments' / (fragment['id'] + '.json')
    source = read_json(sp)
    frag = read_json(fp)
    if mutation == 'usage': source['usage'] = 'evaluation'
    if mutation == 'protected':
        manifest = read_json(root / 'corpus.json')
        manifest['protected_work_ids'] = [metadata['work_id']]
        write_json(root / 'corpus.json', manifest)
    if mutation == 'host': source['permissions']['approved_model_hosts'] = ['offline']
    if mutation == 'unknown': frag['authorship'] = 'unknown'
    if mutation == 'range': frag['end'] += 1000
    write_json(sp, source)
    write_json(fp, frag)
    pack['corpus_dependencies'] = [catalog.load(root)['identity']]
    write_json(path / 'voice.json', pack)
    assert not catalog.search(catalog.load(root)) if mutation in ('usage','protected') else True
    with pytest.raises(QGError, match=error):
        build(corpus_setup)


def test_duplicate_work_content_cannot_bypass_holdout(corpus_setup):
    root, metadata, rev, _, _, pack, path = corpus_setup
    copy_source = copy.deepcopy(metadata)
    copy_source.update(id='evaluation.copy',work_id='evaluation.other-id',usage='evaluation')
    raw = (root / 'objects' / rev['text_sha256']).read_bytes()
    catalog.ingest(root, copy_source, raw, raw.decode())
    pack['corpus_dependencies'] = [catalog.load(root)['identity']]
    write_json(path / 'voice.json', pack)
    with pytest.raises(QGError, match='WORK_SPLIT_LEAKAGE'):
        build(corpus_setup)


def test_private_public_and_context_lineage(corpus_setup):
    with pytest.raises(QGError, match='PRIVATE_CORPUS'):
        build(corpus_setup, public=True)
    context, _ = build(corpus_setup)
    context['corpus_materials'][0]['sha256'] = '0' * 64
    from quillgrain.io import digest
    context['build_id'] = digest({k:v for k,v in context.items() if k != 'build_id'})
    with pytest.raises(QGError, match='LINEAGE_MISMATCH'):
        verify_context(context)


def test_new_revision_preserves_old_and_impact(corpus_setup):
    root, metadata, old, _, _, pack, path = corpus_setup
    new = catalog.ingest(root, metadata, b'A changed fictional lamp.', 'A changed fictional lamp.')
    assert new['id'] != old['id']
    assert len(catalog.load(root)['sources'][metadata['id']]['revisions']) == 2
    assert catalog.impact(metadata['id'], [path])['affected'][0]['examples'] == ['example.synthetic']


def test_storage_and_ci_rejected(corpus_setup, tmp_path):
    root, metadata, *_ = corpus_setup
    value = copy.deepcopy(metadata)
    value['visibility'] = 'local_only'
    with pytest.raises(QGError, match='STORAGE_DENIED'):
        catalog.ingest(root, value, b'fixture', 'fixture')
    (root / '.github').mkdir()
    with pytest.raises(QGError, match='CI_DENIED'):
        catalog.load(root)


def test_bad_ids_and_immutable_fragment(corpus_setup):
    root, metadata, _, fragment, *_ = corpus_setup
    value = copy.deepcopy(metadata)
    value['id'] = '../outside'
    with pytest.raises(QGError, match='SCHEMA_INVALID'):
        catalog.ingest(root, value, b'fixture', 'fixture')
    value = copy.deepcopy(fragment)
    value['start'] = 1
    with pytest.raises(QGError, match='IMMUTABLE_FRAGMENT'):
        catalog.add_fragment(root, value)


def test_optional_budget_omission_preserves_lineage(corpus_setup):
    ctx, _ = build(corpus_setup)
    minimal, _ = build(corpus_setup, max_chars=ctx['budget']['used_codepoints']-1)
    assert not minimal['examples_selected'] and not minimal['corpus_materials']
    assert {'id':'example.synthetic','reason':'budget'} in minimal['examples_omitted']


def test_v1_rules_only_retains_existing_dependency_lock(pack, save):
    path = save(pack)
    _, lock = compile_context(path)
    write_json(path / 'quillgrain.lock.json', lock)
    context, again = compile_context(path, examples_mode='none')
    assert again == lock
    assert catalog.explain(context)['mode'] == 'none'
    verify_bundle(bundle(context, again))


def test_v2_requested_empty_pool_fails(corpus_setup):
    *_, path = corpus_setup
    with pytest.raises(QGError, match='NO_EXAMPLES_SELECTED'):
        compile_context(path, tags=['examples.missing'], example_pool='examples.missing')


def test_evidence_without_retrieval_and_lineage(corpus_setup):
    root, metadata, revision, _, _, pack, path = corpus_setup
    evidence_id = pack['rules'][0]['evidence_ids'] = ['evidence.synthetic']
    pack['evidence_refs'] = [dict(evidence_id=evidence_id[0], corpus_id='quillgrain.corpus',
                                 source_id=metadata['id'],revision_id=revision['id'])]
    write_json(path/'voice.json',pack)
    ctx, _ = compile_context(path,examples_mode='none')
    assert catalog.explain(ctx)['evidence_refs'] == pack['evidence_refs']
    assert not ctx['examples_selected']


def test_corpus_parent_junction_is_denied(corpus_setup, tmp_path):
    import os, subprocess
    root, *_ = corpus_setup
    alias = tmp_path/'alias'
    try:
        alias.symlink_to(root.parent,target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        subprocess.run(['powershell','-NoProfile','-Command',
                        'New-Item -ItemType Junction -Path $env:QG_ALIAS -Target $env:QG_REAL -ErrorAction Stop | Out-Null'],
                       env={**os.environ,'QG_ALIAS':str(alias),'QG_REAL':str(root.parent)},check=True)
    with pytest.raises(QGError,match='CORPUS_LINK_DENIED'):
        catalog.load(alias/root.name)


@pytest.mark.parametrize('relative',['C:/outside.txt','C:outside.txt','//server/share/file.txt','../outside.txt'])
def test_cross_platform_absolute_paths_denied(corpus_setup, relative):
    root, *_ = corpus_setup
    with pytest.raises(QGError,match='CORPUS_PATH_ESCAPE'):
        catalog.read_member(root,relative)


def test_cli_catalog_and_compilation(corpus_setup, tmp_path):
    from quillgrain.cli import main
    root, metadata, _, _, _, _, path = corpus_setup
    assert main(['corpus','validate','--corpus',str(root),'--verify-content']) == 0
    assert main(['corpus','search','--corpus',str(root),'--tag','lighting','--out',str(tmp_path/'search.json')]) == 0
    assert read_json(tmp_path/'search.json')[0]['id'] == metadata['id']
    assert main(['pack','validate','--pack',str(path),'--corpus-bind','quillgrain.corpus='+str(root)]) == 0
    assert main(['pack','build','--pack',str(path),'--corpus-bind','quillgrain.corpus='+str(root),
                 '--register','essay','--tag','examples.synthetic','--out',str(tmp_path/'export')]) == 0
    assert main(['explain','--context',str(tmp_path/'export/context.json'),'--out',str(tmp_path/'explain.json')]) == 0
    assert read_json(tmp_path/'explain.json')['materials']
    assert main(['corpus','impact','--corpus',str(root),'--source-id',metadata['id'],'--pack',str(path),
                 '--context',str(tmp_path/'export/context.json'),'--out',str(tmp_path/'impact.json')]) == 0
    assert read_json(tmp_path/'impact.json')['registered_builds']
