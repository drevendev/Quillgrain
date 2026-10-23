import copy
import importlib.util
from collections import Counter
from pathlib import Path
import pytest
from quillgrain import pairwise as p
from quillgrain.duel import freeze, ARMS, AXES
from quillgrain.io import QGError, digest, sha

spec=importlib.util.spec_from_file_location('pair_demo',Path(__file__).resolve().parents[1]/'scripts/pair_demo.py')
demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)

def answers(blind, count=30):
    rows=[]
    for c in blind['cases'][:count]:
        rows.append({'case_id':c['id'],'votes':{a:'tie' if c['identical'] else 'left' for a in AXES},
                     'guesses':{v['id']:'COMMON' for v in c['cards']},'note':'','committed_at':'fixture'})
    return {'schema_version':'duel.pair-answers/v2','session_id':blind['session_id'],
            'bundle_digest':blind['digest'],'rounds':rows,'draft':None}

def test_schedule_is_balanced_behind_blind_letters(tmp_path):
    source=demo.cases()
    for seed in range(16):
        b,k=p.make_session(source,tmp_path/str(seed),order_seed=seed,mapping_seed=seed,synthetic=True)
        assert len(b['cases'])==30 and all(len(c['cards'])==2 for c in b['cases'])
        assert not any(a in str(b) for a in ARMS)
        assert 'provenance' not in str(b) and 'work_id' not in str(b)
        exposure=Counter();lefts=Counter()
        for g in p.GROUPS:
            pairs=Counter();sides=Counter()
            for c,r in zip(b['cases'],k['cases']):
                if r['group']!=g:continue
                arms=[r['identities'][v['id']]['arm'] for v in c['cards']]
                pairs[tuple(sorted(arms))]+=1;exposure.update(arms);lefts[arms[0]]+=1;sides[arms[0]]+=1
            assert pairs==Counter({tuple(sorted(pair)):1 for pair in p.PAIRS})
            assert sorted(sides.values())==[1,1,2,2]
        assert set(exposure.values())=={15} and sorted(lefts.values())==[7,7,8,8]
        p.statistics_report(b,answers(b),k)

def test_partial_categorical_report_and_complete_reveal(tmp_path):
    b,k=p.make_session(demo.cases(),tmp_path/'s',order_seed=1,mapping_seed=2,synthetic=True)
    a=answers(b,5);r=p.statistics_report(b,a,k)
    assert r['completed_cases']==5 and r['status']=='PARTIAL'
    assert sum(x['clarity']['exposures'] for x in r['axes'].values())==10
    assert sum(x['clarity']['wins'] for x in r['axes'].values())==5
    assert r['guesses']['attempted']==10 # same guess for both is legitimate
    assert all(x['resemblance']['judged']==0 for x in r['axes'].values())
    with pytest.raises(QGError,match='NOT_COMPLETE'):p.reveal(b,a,k)
    assert p.reveal(b,answers(b),k)['report']['completed_cases']==30
    a['rounds'][0]['votes']['clarity']=5
    with pytest.raises(QGError):p.validate_answers(b,a)

def test_identical_outputs_are_ambiguous_not_exclusive_wins(tmp_path):
    cs=demo.cases()
    for c in cs:
        for arm,v in c['variants'].items():
            v.update(text=c['source_text'],sha256=c['source_sha256'],words=p.words(c['source_text']))
            if arm!='ORIGINAL':v['raw_text']=c['source_text']
    cs=[freeze(c) for c in cs]
    b,k=p.make_session(cs,tmp_path/'s',order_seed=4,mapping_seed=9,synthetic=True)
    a=answers(b);r=p.statistics_report(b,a,k)
    assert r['identical_rounds']==30 and r['guesses']['ambiguous_excluded']==60 and r['guesses']['attempted']==0
    assert all(x['clarity']['wins']==0 and x['clarity']['ambiguous']==15 for x in r['axes'].values())
    a['rounds'][0]['votes']['clarity']='left'
    with pytest.raises(QGError,match='IDENTICAL'):p.validate_answers(b,a)

@pytest.mark.parametrize('mutate',[
    lambda c:c['rights'].update(local_use_reviewed=False),
    lambda c:c['meaning'][0].update(evidence='Not in the source'),
    lambda c:c['meaning'][0].update(instruction='Repeat this silly directive'),
    lambda c:c['variants']['COMMON'].update(raw_text='Edited'),
    lambda c:c['variants']['COMMON'].update(seed=900),
    lambda c:c['variants']['COMMON'].update(common_input_hash='0'*64),
    lambda c:c.update(meaning_reviewed=False),
])
def test_bad_evidence_is_not_a_ready_case(mutate):
    c=demo.cases()[0];mutate(c)
    with pytest.raises(QGError):p.validate_case(freeze(c),synthetic=True)

def test_mock_cannot_be_mistaken_for_live_and_meaning_is_data():
    c=demo.cases()[0]
    with pytest.raises(QGError,match='REAL_EVIDENCE'):p.validate_case(c)
    request=p.generation_prompt(c)
    assert 'не готовые фразы' in request and '"evidence"' not in request and '"modality"' in request

def test_reference_works_cannot_be_reused_for_evaluation(tmp_path):
    with pytest.raises(QGError,match='REFERENCE_LEAKAGE'):
        p.make_session(demo.cases(),tmp_path/'s',order_seed=1,mapping_seed=1,synthetic=True,
                       reference_works=['fictional-work-0'])

def test_licensed_techprose_replacement_requires_explicit_campaign_choice(tmp_path):
    cs=demo.cases()
    for c in cs:
        if c['group']=='denis':c['group']='techprose'
    cs=[freeze(c) for c in cs]
    with pytest.raises(QGError,match='GROUP_QUOTA'):
        p.make_session(cs,tmp_path/'wrong',order_seed=7,mapping_seed=4,synthetic=True)
    b,k=p.make_session(cs,tmp_path/'approved',order_seed=7,mapping_seed=4,synthetic=True,blog_group='techprose')
    report=p.statistics_report(b,answers(b),k)
    assert report['group_completed']['techprose']==6 and 'denis' not in report['groups']

def test_wrong_key_and_draft_cannot_change_committed_round(tmp_path):
    b,k=p.make_session(demo.cases(),tmp_path/'s',order_seed=3,mapping_seed=5,synthetic=True)
    a=answers(b,1);a['draft']=copy.deepcopy(a['rounds'][0]);a['draft']['committed_at']=None
    with pytest.raises(QGError,match='ROUND_ORDER'):p.validate_answers(b,a)
    a['draft']=None;wrong=copy.deepcopy(k);wrong['cases'][0]['identities'].clear()
    with pytest.raises(QGError):p.statistics_report(b,a,freeze(wrong))
