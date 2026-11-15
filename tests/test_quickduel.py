import copy
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from quillgrain import quickduel as q, review
from quillgrain.cli import main
from quillgrain.duel import freeze
from quillgrain.io import QGError, canonical, read_json, sha, write_json


def manifest(n=30, arms=10):
    return {'schema_version': 'duel.quick-sources/v1', 'conditions': [
        {'id': f'condition{i}', 'kind': 'model', **{f: f'synthetic-{f}-{i}' for f in q.FACTORS}} for i in range(arms)],
        'sources': [{'id': f'source{i}', 'work_id': f'work{i//2}', 'group': f'group{i%5}',
                     'source_text': f'Придуманный мастер {i} ремонтирует фонарь.', 'purpose': 'Синтетическая заметка.',
                     'rights_reviewed': True, 'meaning_reviewed': True} for i in range(n)]}


def outputs(plan, *, identical=False):
    m = {s['id']: s for s in manifest(80)['sources']}
    conditions = {c['id']: c for c in plan['conditions']}
    result = []
    for row in plan['rows']:
        source = m[row['source_id']]['source_text']; variants = {}
        for arm in row['pair']:
            text = source + ('' if identical else ' Вариант ' + arm + '.')
            variants[arm] = {'text': text, 'sha256': sha(text.encode()), 'raw_sha256': sha(text.encode()),
                             'source_sha256': row['source_sha256'], 'status': 'MOCK',
                             'condition': conditions[arm], 'plan_digest': plan['digest']}
        result.append({'source_id': row['source_id'], 'source_text': source, 'variants': variants})
    return result


def answers(blind, n=5, stopped=True):
    rows = []
    for c in blind['cases'][:n]:
        rows.append({'case_id': c['id'], 'vote': 'tie' if c['identical'] else 'left_strong',
                     'comments': {v['id']: '' for v in c['cards']}, 'committed_at': 'synthetic-time'})
    c = blind['cases'][n] if n < len(blind['cases']) else None
    return {'schema_version': 'duel.quick-answers/v1', 'session_id': blind['session_id'], 'bundle_digest': blind['digest'],
            'state': 'COMPLETE' if c is None else 'STOPPED_BY_OWNER' if stopped else 'ACTIVE',
            'stopped_at': 'synthetic-time' if c is not None and stopped else None, 'rounds': rows,
            'draft': {'case_id': c['id'], 'vote': None, 'comments': {v['id']: 'черновик' for v in c['cards']}, 'committed_at': None} if c else None}


@pytest.mark.parametrize('arms', [2, 4, 10, 20])
def test_fixed_budget_source_once_and_balanced_conditions(arms):
    for seed in range(12):
        p = q.make_plan(manifest(80, arms), seed=seed)
        assert len(p['rows']) == 30
        assert len({r['source_id'] for r in p['rows']}) == 30
        counts = Counter(a for r in p['rows'] for a in r['pair'])
        assert max(counts.values()) - min(counts.values()) <= 1
        assert set(Counter(r['group'] for r in p['rows']).values()) == {6}
        left = Counter(r['pair'][0] for r in p['rows']); right = Counter(r['pair'][1] for r in p['rows'])
        assert max(abs(left[a]-right[a]) for a in counts) <= 1
        assert p == q.make_plan(manifest(80, arms), seed=seed)
    assert len(q.make_plan(manifest(3, arms), seed=1)['rows']) == 3
    assert len(q.make_plan(manifest(30, arms), seed=1, budget=7)['rows']) == 7


@pytest.mark.parametrize('change', [
    lambda m: m['sources'][1].update(id=m['sources'][0]['id']),
    lambda m: m['sources'][1].update(source_text='  Придуманный\nмастер 0 ремонтирует фонарь.  '),
    lambda m: m['sources'][1].update(source_text='Придуманный мастер ０ ремонтирует фонарь.'),
    lambda m: m['sources'][0].update(variants={}),
    lambda m: m['sources'][0].update(rights_reviewed=False),
])
def test_reject_duplicate_id_or_normalized_source_and_posthoc_inputs(change):
    m = manifest(); change(m)
    with pytest.raises(QGError): q.make_plan(m, seed=1)


def test_blind_packaging_privacy_integrity_and_no_overwrite(tmp_path):
    p = q.make_plan(manifest(), seed=1, budget=7); out = tmp_path/'game'
    b, k = q.make_session(p, outputs(p), out, synthetic=True)
    q.validate_key(b, k)
    assert len(b['cases']) == 7 and all(len(c['cards']) == 2 for c in b['cases'])
    html = (out/'Ink_Duel.html').read_text(encoding='utf-8')
    # Text may mention a synthetic condition; private mapping and profile data never appear.
    assert 'source_id' not in json.dumps(b) and '"identities":' not in html and 'synthetic-profile' not in html
    assert '/*QUICK_' not in html
    assert '<script src="/app.js">' in q.browser_html(b, standalone=False).decode()
    saved = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(QGError, match='ALREADY_EXISTS'): q.make_session(p, outputs(p), out, synthetic=True)
    assert saved == {p.name: p.read_bytes() for p in out.iterdir()}
    for mutate in [lambda x:x['cases'].reverse(), lambda x:x['cases'][0]['identities'].clear()]:
        bad = copy.deepcopy(k); mutate(bad)
        with pytest.raises(QGError): q.validate_key(b, freeze(bad))


def test_preparation_refuses_changed_plan_outputs_and_mock_as_live(tmp_path):
    p = q.make_plan(manifest(), seed=1, budget=2)
    with pytest.raises(QGError, match='REAL_EVIDENCE'): q.make_session(p, outputs(p), tmp_path/'live')
    for change in [lambda v:v.update(raw_sha256='0'*64), lambda v:v.update(plan_digest='0'*64), lambda v:v.update(condition={})]:
        o = outputs(p); change(next(iter(o[0]['variants'].values())))
        with pytest.raises(QGError): q.make_session(p, o, tmp_path/'bad', synthetic=True)
    assert not (tmp_path/'bad').exists()


def test_partial_reports_draft_exclusion_unknown_pairs_and_ordinal_votes(tmp_path):
    p = q.make_plan(manifest(), seed=5, budget=7)
    b, k = q.make_session(p, outputs(p), tmp_path/'game', synthetic=True); a = answers(b, 3)
    before = canonical(a); r = review.partial_report(b, a, k, input_sha256=sha(before))
    assert r['committed']['duels'] == 3 and r['planned']['duels'] == 7
    assert r['draft_present'] and r['draft_excluded'] and r['comment_fields_filled'] == 0
    assert r['committed']['unique_sources'] == 3 and r['committed']['repeated_source_exposures'] == 0
    assert r['causes'] == 'UNKNOWN_WITHOUT_COMMENTS' and canonical(a) == before
    dims = [p['dimensions']['overall'] for p in r['pairs']]
    assert sum(d['n'] for d in dims) == 3 and sum(d['first_wins']+d['second_wins'] for d in dims) == 3
    assert any(d['status'] == 'NO_OBSERVATIONS' and d['ties'] == d['first_wins'] == 0 for d in dims)
    assert sum(sum(d['intensity'].values()) for d in dims) == 3
    assert 'черновик' not in canonical(r).decode() and 'identities' not in r and 'cases' not in r
    with pytest.raises(QGError, match='STOP_ACTION'): review.partial_report(b, answers(b, 3, stopped=False), k)
    for change in [lambda x:x['rounds'].append(x['rounds'][0]), lambda x:x['draft'].update(vote='tie'), lambda x:x.update(bundle_digest='0'*64)]:
        bad = copy.deepcopy(a); change(bad)
        with pytest.raises(QGError): q.validate_answers(b, bad)


def test_identical_cards_tie_is_ambiguous_and_never_a_win(tmp_path):
    p = q.make_plan(manifest(), seed=2, budget=2)
    b, k = q.make_session(p, outputs(p, identical=True), tmp_path/'game', synthetic=True)
    a = answers(b, 2); r = review.partial_report(b, a, k)
    assert sum(d['dimensions']['overall']['ambiguous'] for d in r['pairs']) == 2
    assert sum(d['dimensions']['overall']['ties'] for d in r['pairs']) == 0
    a['rounds'][0]['vote'] = 'left_slight'
    with pytest.raises(QGError, match='IDENTICAL'): q.validate_answers(b, a)


def test_cli_plan_prepare_stop_report_is_create_only(tmp_path):
    m = tmp_path/'sources.json'; write_json(m, manifest())
    assert main(['duel','quick-plan','--sources',str(m),'--seed','6','--budget','7','--out',str(tmp_path/'plan')]) == 0
    p = read_json(tmp_path/'plan/plan.private.json'); write_json(tmp_path/'outputs.json',outputs(p))
    assert main(['duel','quick-prepare','--plan',str(tmp_path/'plan/plan.private.json'),'--cases',str(tmp_path/'outputs.json'),'--synthetic','--out',str(tmp_path/'game')]) == 0
    b = read_json(tmp_path/'game/blind-session.json'); a = answers(b, 3, stopped=False); file = tmp_path/'answers.json'
    raw = json.dumps(a,ensure_ascii=False,indent=3).encode();file.write_bytes(raw)
    args=['duel','report','--session',str(tmp_path/'game/blind-session.json'),'--answers',str(file),'--key',str(tmp_path/'game/answer-key.private.json'),'--out',str(tmp_path/'review')]
    assert main(args) == 3 and not (tmp_path/'review').exists()
    assert main([*args,'--stop']) == 0 and file.read_bytes() == raw
    assert read_json(tmp_path/'review/report.json')['input_sha256'] == sha(raw)


def test_node_client_core_and_browser(tmp_path):
    node = shutil.which('node')
    if not node: pytest.skip('Node is unavailable')
    p = q.make_plan(manifest(), seed=7, budget=7)
    b, k = q.make_session(p, outputs(p), tmp_path/'game', synthetic=True)
    fixture = tmp_path/'fixture.json'; a = answers(b,3)
    write_json(fixture, {'blind':b,'key':k,'answers':a,'report':review.partial_report(b,a,k)})
    run = subprocess.run([node, str(Path(__file__).with_name('quick_client.cjs')),str(fixture),str(tmp_path/'game/Ink_Duel.html')],capture_output=True,text=True,encoding='utf-8')
    assert run.returncode == 0, run.stdout+run.stderr
