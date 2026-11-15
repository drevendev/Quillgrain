"""New scenes are facts, not disguised originals; all text here is synthetic."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from quillgrain import quickduel as q, quickv2, review
from quillgrain.cli import main
from quillgrain.duel import freeze
from quillgrain.io import QGError, canonical, read_json, sha, write_json
from test_quickduel import answers


def manifest(n=6):
    value = read_json(Path(__file__).resolve().parents[1] / 'examples/synthetic/fiction-duel-v2.json')
    template = value['sources'][0]
    for i in range(6, n):
        source = copy.deepcopy(template)
        source.update(id='scene-'+str(i), work_id='work-'+str(i))
        source['fact_pack']['action'] = 'Mira opens fictional locker '+str(i)
        value['sources'].append(source)
    value['sources'] = value['sources'][:n]
    return value


def outputs(plan):
    conditions = {c['id']:c for c in plan['conditions']}
    rows = []
    for row in plan['rows']:
        variants = {}
        for side, arm in enumerate(row['pair']):
            text = ('Mira opened the locker and found a brass key beside the sealed envelope. '
                    'She gave the key to the keeper, keeping the envelope closed. '
                    + ('The keeper waited by the door.' if side else 'At the door the keeper waited.'))
            if conditions[arm]['kind'] == 'original':
                text = next(s['source_text'] for s in plan['manifest']['sources'] if s['id'] == row['source_id'])
            variants[arm] = {'text':text,'sha256':sha(text.encode()),'raw_sha256':sha(text.encode()),
                             'input_sha256':row['input_sha256'],'condition':conditions[arm],
                             'plan_digest':plan['digest'],'status':'MOCK'}
        rows.append({'source_id':row['source_id'],'input_sha256':row['input_sha256'],'variants':variants})
    return rows


def test_source_once_fiction_plan_is_frozen_and_budgeted():
    m = manifest(35)
    first = q.make_plan(m,seed=8)
    assert first['schema_version'] == 'duel.quick-plan/v2' and len(first['rows']) == 30
    assert first == q.make_plan(m,seed=8)
    assert len({r['normalized_sha256'] for r in first['rows']}) == 30
    assert len(q.make_plan(m,seed=8,budget=4)['rows']) == 4
    changed = copy.deepcopy(first);changed['rows'][0]['pair'].reverse()
    with pytest.raises(QGError,match='PLAN_MISMATCH'): q.validate_plan(freeze(changed))


@pytest.mark.parametrize('change,code', [
    (lambda m:m['sources'][1].update(fact_pack=copy.deepcopy(m['sources'][0]['fact_pack'])), 'REPEATED'),
    (lambda m:m['reference_work_ids'].append(m['sources'][0]['work_id']), 'REFERENCE_OVERLAP'),
    (lambda m:m['sources'][1].update(work_id=m['sources'][0]['work_id'],split='reserve'), 'RESERVE_OVERLAP'),
    (lambda m:m['sources'][0].update(source_text='A fabricated original'), 'NO_ORIGINAL'),
    (lambda m:m['research'].update(control_condition='absent'), 'PREVIOUS_SNAPSHOT'),
    (lambda m:m['conditions'][0].update(profile_snapshot=None), 'SNAPSHOT'),
    (lambda m:m['sources'][0]['rights'].update(permitted_uses=[]), 'RIGHTS'),
])
def test_invalid_provenance_and_leakage_are_rejected(change,code):
    m = manifest();change(m)
    with pytest.raises(QGError,match=code): q.make_plan(m,seed=1)


def test_quotas_are_explicit_and_never_expand_budget():
    m=manifest();m['quotas']={'choice':2,'discovery':1}
    p=q.make_plan(m,seed=2,budget=3)
    assert len(p['rows'])==3 and sum(r['group']=='choice' for r in p['rows'])==2
    with pytest.raises(QGError,match='EXCEEDS_BUDGET'):q.make_plan(m,seed=2,budget=2)
    m['quotas']={'absent':1}
    with pytest.raises(QGError,match='QUOTA_UNAVAILABLE'):q.make_plan(m,seed=2)
    with pytest.raises(QGError,match='SEED_INVALID'):q.make_plan(m,seed=2**53)


def test_scene_packaging_records_origin_and_rejects_changed_or_short_outputs(tmp_path):
    p=q.make_plan(manifest(),seed=4)
    b,k=q.make_session(p,outputs(p),tmp_path/'game',synthetic=True)
    assert b['schema_version']=='duel.quick-blind/v2' and b['study']=={'task_kinds':['new_scene'],'original_in_design':False}
    assert all(origin['kind']=='model_output' for c in k['cases'] for origin in c['origins'].values())
    blind_json=json.dumps(b)
    for private in ('profile_snapshot','fact_pack','input_sha256','identities','rights'):
        assert private not in blind_json
    for mutate,code in [
        (lambda o:o[0].update(input_sha256='0'*64),'INPUT_MUTATED'),
        (lambda o:next(iter(o[0]['variants'].values())).update(raw_sha256='0'*64),'EDITED_OUTPUT'),
        (lambda o:next(iter(o[0]['variants'].values())).update(text='Short.',sha256=sha(b'Short.'),raw_sha256=sha(b'Short.')),'WORD_BUDGET_MISS'),
    ]:
        o=outputs(p);mutate(o)
        with pytest.raises(QGError,match=code):q.make_session(p,o,tmp_path/'bad',synthetic=True)
        assert not (tmp_path/'bad').exists()
    bad=copy.deepcopy(k);next(iter(bad['cases'][0]['origins'].values()))['kind']='unchanged_source'
    with pytest.raises(QGError,match='WRONG_KEY'):q.validate_key(b,freeze(bad))


def test_original_is_explicit_and_exact_and_not_allowed_in_a_new_scene(tmp_path):
    m=manifest();m['research'].update(comparison_goal='screening',control_condition=None,controlled_factors=[])
    m['conditions'][0].update(kind='original',profile='none',profile_snapshot=None)
    with pytest.raises(QGError,match='ORIGINAL_INCOMPATIBLE_TASK'):q.make_plan(m,seed=1)
    for i,s in enumerate(m['sources']):s.update(task_kind='rewrite',source_text='A fictional unchanged source '+str(i)+'.')
    p=q.make_plan(m,seed=1,budget=2);b,k=q.make_session(p,outputs(p),tmp_path/'original',synthetic=True)
    assert b['study']['original_in_design']
    r=review.partial_report(b,answers(b,2),k)
    assert r['provenance']['committed_text_origins']=={'unchanged_source':2,'model_output':2}
    bad=outputs(p);arm=m['conditions'][0]['id'];v=bad[0]['variants'][arm];v['text']+=' Changed';v['sha256']=v['raw_sha256']=sha(v['text'].encode())
    with pytest.raises(QGError,match='SOURCE_MUTATED'):q.make_session(p,bad,tmp_path/'bad',synthetic=True)


def test_declared_but_unassigned_original_is_not_described_as_displayed(tmp_path):
    m=manifest();m['research'].update(comparison_goal='screening',control_condition=None,controlled_factors=[])
    original=copy.deepcopy(m['conditions'][0]);original.update(id='original',kind='original',profile_snapshot=None)
    m['conditions'].append(original)
    for i,s in enumerate(m['sources']):s.update(task_kind='rewrite',source_text='Unchanged fictional passage '+str(i))
    for seed in range(20):
        p=q.make_plan(m,seed=seed,budget=1)
        if 'original' not in p['rows'][0]['pair']:
            b,k=q.make_session(p,outputs(p),tmp_path/'game',synthetic=True)
            assert not b['study']['original_in_design']
            assert review.partial_report(b,answers(b,1),k)['provenance']['source_role']=='INPUT_ONLY'
            break
    else:
        pytest.fail('No synthetic unassigned-original seed found')


def test_partial_feedback_preserves_votes_and_card_links_without_inventing_approval(tmp_path):
    p=q.make_plan(manifest(),seed=4)
    b,k=q.make_session(p,outputs(p),tmp_path/'game',synthetic=True);a=answers(b,4)
    votes=['left_strong','tie','right_slight','left_slight']
    notes=[['Both are heavy; this is clearer.',''],['Both are unsatisfying.','Both are unsatisfying.'],
           ['The same word appears.','The same word appears.'],['Keep the useful term.','']]
    for i,r in enumerate(a['rounds']):
        r['vote']=votes[i];r['comments']={c['id']:note for c,note in zip(b['cases'][i]['cards'],notes[i])}
    before=canonical(a);r=review.partial_report(b,a,k)
    assert canonical(a)==before and r['absolute_satisfaction']=='UNKNOWN'
    assert r['duplicate_comment_pairs']==2 and r['comment_rounds']==4
    dims=[p['dimensions']['overall'] for p in r['pairs']]
    assert sum(d['first_wins']+d['second_wins'] for d in dims)==3 and sum(d['ties'] for d in dims)==1
    assert sum(s['n'] for s in r['slices'])==4
    assert 'Both are heavy' not in canonical(r).decode() and not r['feedback_semantics']['automatic_rule_promotion']
    private=review.comment_review(b,a,k)
    assert private['notes'][0]['raw_vote']=='left_strong'
    assert private['notes'][0]['side']=='left' and private['notes'][0]['card_id']==b['cases'][0]['cards'][0]['id']
    duplicate=[n for n in private['notes'] if n['case_id']==b['cases'][1]['id']]
    assert len(duplicate)==2 and duplicate[0]['within_round_comment_group']==duplicate[1]['within_round_comment_group']
    assert all(n['cause']=='UNKNOWN' and n['status']=='NOT_REVIEWED' for n in private['notes'])


def test_v2_cli_and_browser_use_compatible_answers_and_report_semantics(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    m=manifest();write_json(tmp_path/'sources.json',m)
    assert main(['duel','quick-plan','--sources',str(tmp_path/'sources.json'),'--seed','5','--out',str(tmp_path/'plan')])==0
    p=read_json(tmp_path/'plan/plan.private.json');write_json(tmp_path/'outputs.json',outputs(p))
    assert main(['duel','quick-prepare','--plan',str(tmp_path/'plan/plan.private.json'),'--cases',str(tmp_path/'outputs.json'),'--synthetic','--out',str(tmp_path/'game')])==0
    b=read_json(tmp_path/'game/blind-session.json');k=read_json(tmp_path/'game/answer-key.private.json');a=answers(b,3)
    write_json(tmp_path/'answers.json',a)
    assert main(['duel','report','--session',str(tmp_path/'game/blind-session.json'),'--key',str(tmp_path/'game/answer-key.private.json'),'--answers',str(tmp_path/'answers.json'),'--out',str(tmp_path/'report'),'--comments-out',str(tmp_path/'private-notes')])==0
    write_json(tmp_path/'fixture.json',{'blind':b,'key':k,'answers':a,'report':review.partial_report(b,a,k)})
    run=subprocess.run([node,str(Path(__file__).with_name('quick_client.cjs')),str(tmp_path/'fixture.json'),str(tmp_path/'game/Ink_Duel.html')],capture_output=True,encoding='utf-8')
    assert run.returncode==0,run.stdout+run.stderr
