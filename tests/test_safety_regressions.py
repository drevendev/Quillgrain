"""Regression cases use invented sources only."""
import copy
import os
from pathlib import Path
import pytest
from quillgrain.corpus import inventory, prepare, extract, EXTRACTOR
from quillgrain.compose import compile_context, POLICY
from quillgrain.contracts import verify_context
from quillgrain.export import export
from quillgrain import evaluation
from quillgrain.io import QGError, read_json, write_json, write_bytes, digest
from test_corpus import config


def test_denied_roots_and_stale_selection_never_read(tmp_path, pack, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'a.md').write_text('Придуманный исходник.', encoding='utf-8')
    cfg = config(root, pack)
    inventory(cfg, tmp_path / 'inv.json')
    items = read_json(tmp_path / 'inv.json')['items']
    items[0]['selection'] = 'reference'
    original = Path.read_bytes
    reads = []
    def spy(p):
        if p.is_relative_to(root):
            reads.append(p)
        return original(p)
    monkeypatch.setattr(Path, 'read_bytes', spy)
    cfg['roots'][0]['permissions']['local_analysis'] = False
    inventory(cfg, tmp_path / 'denied.json')
    assert not reads
    with pytest.raises(QGError, match='SOURCE_DENIED'):
        prepare(items, cfg, tmp_path / 'denied')
    cfg['roots'][0]['permissions']['local_analysis'] = True
    cfg['roots'][0]['include_files'] = []
    with pytest.raises(QGError, match='NOT_ALLOWLISTED'):
        prepare(items, cfg, tmp_path / 'stale')
    assert not reads
    for bad in ('a.md', ['../a.md'], ['C:/a.md'], [1]):
        cfg['roots'][0]['include_files'] = bad
        with pytest.raises(QGError):
            inventory(cfg, tmp_path / 'bad.json')
    assert not reads


def test_create_only_exports_and_hardlink_source_safety(tmp_path, pack, save):
    ctx, lock = compile_context(save(pack), target='patchpitch-legacy')
    dest = tmp_path / 'out'
    export(ctx, lock, dest)
    before = {p.name: p.read_bytes() for p in dest.iterdir()}
    other, other_lock = compile_context(save(pack), target='chatgpt')
    with pytest.raises(QGError, match='OUTPUT_ALREADY_EXISTS'):
        export(other, other_lock, dest)
    assert {p.name: p.read_bytes() for p in dest.iterdir()} == before
    source, link = tmp_path / 'source.md', tmp_path / 'linked.md'
    source.write_bytes(b'KEEP')
    os.link(source, link)
    write_bytes(link, b'NEW')
    assert source.read_bytes() == b'KEEP'


def test_symlink_output_refused(tmp_path):
    source, link = tmp_path / 'source.md', tmp_path / 'linked.md'
    source.write_bytes(b'KEEP')
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip('File symlinks require Windows developer mode; junction tested separately')
    with pytest.raises(QGError, match='OUTPUT_LINK_DENIED'):
        write_bytes(link, b'REPLACE')
    assert source.read_bytes() == b'KEEP'


def test_output_junction_refused(tmp_path):
    from quillgrain.io import publish_bundle
    root, link = tmp_path / 'outside', tmp_path / 'linked'
    root.mkdir()
    if os.name == 'nt':
        import subprocess
        subprocess.run(['powershell', '-NoProfile', '-Command',
            'New-Item -ItemType Junction -Path $env:QG_LINK -Target $env:QG_TARGET -ErrorAction Stop | Out-Null'],
            env={**os.environ, 'QG_LINK': str(link), 'QG_TARGET': str(root)}, check=True)
    else:
        link.symlink_to(root, target_is_directory=True)
    with pytest.raises(QGError, match='OUTPUT_LINK_DENIED'):
        publish_bundle(link / 'out', {'a.txt': b'CANARY'})
    assert not list(root.iterdir())


@pytest.mark.parametrize('raw', [
    b'Own.\n<!-- external\nCANARY\n-->\n\nClosing.',
    b'Own.\n\n> external\nCANARY\n\nClosing.',
    b'Own. <!-- CANARY --> Closing.',
    b'Own.\n<!-- CANARY',
    b'Own.\n\n> nested\n>> CANARY\nlazy CANARY\n\nClosing.',
])
def test_comment_quote_boundaries(raw):
    text, _ = extract(raw)
    assert 'CANARY' not in text
    assert 'Own.' in text
    assert EXTRACTOR.endswith('v2')


def test_scope_containment_and_noncontradictory_overlap(pack, save):
    required = copy.deepcopy(pack['rules'][1])
    required.update(id='required', enforcement='required_literal', parameters={'literal':'MARK'})
    forbidden = copy.deepcopy(required)
    forbidden.update(id='forbidden', enforcement='forbidden_literal')
    for narrow, broad in [({'channel':'narration'}, {'channel':'all'}),
                          ({'channel':'dialogue','characters':['a']}, {'channel':'all'}),
                          ({'channel':'dialogue','characters':['a']}, {'channel':'dialogue','characters':['a','b']})]:
        required['scope'], forbidden['scope'] = narrow, broad
        pack['rules'] = [required, forbidden]
        with pytest.raises(QGError, match='MANDATORY_CONFLICT'):
            compile_context(save(pack))
    # A requirement on all text can be satisfied in dialogue when narration forbids it.
    required['scope'], forbidden['scope'] = {'channel':'all'}, {'channel':'narration'}
    compile_context(save(pack))
    required['scope'], forbidden['scope'] = {'channel':'dialogue','characters':['a']}, {'channel':'dialogue','characters':['b']}
    compile_context(save(pack))


def test_fixed_prefix_budget_and_semantic_verification(pack, save):
    pack['rules'], pack['examples'] = [], []
    path = save(pack)
    with pytest.raises(QGError, match='BUDGET_EXCEEDED'):
        compile_context(path, max_chars=1)
    ctx, _ = compile_context(path, max_chars=len(POLICY))
    ctx['budget']['max_codepoints'] -= 1
    ctx['build_id'] = digest({k:v for k,v in ctx.items() if k != 'build_id'})
    with pytest.raises(QGError, match='BUDGET_EXCEEDED'):
        verify_context(ctx)


@pytest.mark.parametrize('changed', ['manifest', 'output', 'prompt', 'context'])
def test_report_revalidates_saved_evidence(tmp_path, pack, save, changed):
    ctx, _ = compile_context(save(pack))
    write_json(tmp_path / 'ctx.json', ctx)
    write_json(tmp_path / 'cases/c.json', dict(id='case', baseline='Neutral', brief='Invented facts.',
        contexts={'B1':'../ctx.json','B2':'../ctx.json'}))
    runs = tmp_path / 'runs'
    evaluation.prepare(tmp_path / 'cases', runs)
    response = tmp_path / 'answer.md'
    response.write_bytes(b'Synthetic response, not a model experiment.')
    runpath = runs / 'case/B1/run.json'
    evaluation.record(runpath, response, status='MOCK')
    if changed == 'manifest':
        record = read_json(runpath)
        record['raw_output'] = 'ALTERED'
        write_json(runpath, record)
    elif changed == 'output':
        write_bytes(runpath.parent / 'raw-output.md', b'ALTERED')
    elif changed == 'prompt':
        write_bytes(runpath.parent / 'prompt.md', b'ALTERED')
    else:
        copyctx = read_json(runpath.parent / 'context.json')
        copyctx['prompt_payload'] += 'ALTERED'
        write_json(runpath.parent / 'context.json', copyctx)
    with pytest.raises(QGError):
        evaluation.report(runs, tmp_path / 'report')
    assert not (tmp_path / 'report').exists()
