import copy
from collections import Counter
import itertools
import pytest
from quillgrain.duel import (ARMS, AXES, GROUPS, freeze, make_session, reveal, statistics_report, validate_answers, validate_case)
from quillgrain.io import QGError, digest, sha


def cases():
    result=[]
    for index in range(20):
        text=f'Вымышленный мастер номер {index} чинит часы. Он не берёт плату.'
        anchors=['Мастер чинит часы.','Плата не нужна.']
        c=dict(schema_version='duel.case/v1', id=f'c{index}', group=GROUPS[index//5],language='ru',
            status='READY',work_id=f'work{index}',anchors=anchors,source_text=text,source_sha256=sha(text.encode()),
            purpose='Вымышленная заметка для технического теста.',rights={'local_use_reviewed':True},
            overlap_reviewed=True,provenance={'note':'Original synthetic test fixture.'},authorship='synthetic',variants={})
        for arm in ARMS:
            out=text if arm=='ORIGINAL' else text+' Хорошая работа.'
            v=dict(text=out,sha256=sha(out.encode()),sentences=2 if arm=='ORIGINAL' else 3,words=12,
                   status='ORIGINAL' if arm=='ORIGINAL' else 'MOCK')
            if arm!='ORIGINAL':v.update(raw_text=out,model='synthetic',model_digest='not-live',runtime='fixture',
                options={'temperature':1},seed=index,common_input_hash=digest([text,anchors]),
                source_sha256=c['source_sha256'],brief_sha256=digest(anchors))
            c['variants'][arm]=v
        result.append(freeze(c))
    return result


def votes(blind, key, count=20):
    rounds=[]
    for c,k in zip(blind['cases'][:count],key['cases'][:count]):
        q={}
        for card in c['cards']:
            arm=k['identities'][card['id']]['arm']
            # Selected wins by 2 over Common, with missing accuracy in Common.
            n={'ORIGINAL':1,'MODEL_BASELINE':2,'COMMON':3,'SELECTED':5}[arm]
            q[card['id']]={'scores':{a:None if a=='fidelity' and arm=='COMMON' else n for a in AXES},'note':'','quotes':[]}
        rounds.append(dict(case_id=c['id'],quality=q,quality_committed_at='fixture',round_committed_at='fixture',
            preference=next(v['label'] for v in c['cards'] if k['identities'][v['id']]['arm']=='SELECTED'),
            guesses={v['label']:k['identities'][v['id']]['arm'] for v in c['cards']},recognition='no'))
    return dict(schema_version='duel.session/v1',session_id=blind['session_id'],bundle_digest=blind['digest'],rounds=rounds)


def test_balanced_unique_cases_and_no_key_in_blind(tmp_path):
    blind,key=make_session(cases(),tmp_path/'session',order_seed=42,mapping_seed=8,synthetic=True)
    assert len(blind['cases'])==20
    count=Counter((identity['label'],identity['arm']) for c in key['cases'] for identity in c['identities'].values())
    assert set(count.values())=={5} and len(count)==16
    first=Counter(c['group'] for c in key['cases'][:10])
    assert sorted(first.values())==[2,2,3,3]
    assert len({tuple(c['identities'][v['id']]['arm'] for v in b['cards']) for c,b in zip(key['cases'],blind['cases'])})==20
    assert not any(a in str(blind) for a in ARMS)
    assert 'mapping_seed' not in blind and 'provenance' not in str(blind)


def test_statistics_pairing_nulls_and_reveal_gate(tmp_path):
    b,k=make_session(cases(),tmp_path/'session',order_seed=5,mapping_seed=99,synthetic=True)
    a=votes(b,k)
    report=statistics_report(b,a,k)
    assert report['axes']['SELECTED']['clarity']['mean']==5
    assert report['axes']['COMMON']['fidelity']['n']==0
    pair=report['paired']['SELECTED-COMMON']['clarity']
    assert pair['n']==20 and pair['mean_difference']==2 and pair['wins']==20 and pair['ties']==pair['losses']==0
    assert pair['distribution']['2']==20
    assert report['paired']['SELECTED-COMMON']['fidelity']['n']==0
    assert report['paired']['SELECTED-COMMON']['fidelity']['missing_pairs']==20
    assert report['axes']['COMMON']['fidelity']['missing']==20
    assert all(s['cases']==5 for s in report['slices']['group'].values())
    assert report['slices']['recognition']['no']['cases']==20
    assert report['guesses']['abstained_rounds']==0
    assert report['owner_style']['SELECTED']['n']==0
    assert report['guesses']['correct']==80 and report['guesses']['exact_rounds']==20
    assert report['favorites']=={'SELECTED':20}
    assert reveal(b,a,k)['report']['completed_cases']==20
    assert type(reveal(b,a,k)['report']['axes']['SELECTED']['clarity']['mean']) is int
    with pytest.raises(QGError,match='NOT_COMPLETE'):reveal(b,votes(b,k,10),k)
    partial=statistics_report(b,votes(b,k,3),k)
    assert partial['completed_cases']==3 and partial['quality_status']=='PARTIAL'


@pytest.mark.parametrize('mutation',[
    lambda c:c['variants']['COMMON'].update(status='LIVE'),
    lambda c:c['variants']['COMMON'].update(seed=999),
    lambda c:c['variants']['COMMON'].update(text='Altered'),
    lambda c:c['variants']['COMMON'].update(raw_text='Altered'),
    lambda c:c['variants']['COMMON'].update(model='different'),
    lambda c:c['variants']['COMMON'].update(sentences=6),
    lambda c:c.update(overlap_reviewed=False),
])
def test_invalid_evidence_never_becomes_eligible(mutation):
    c=cases()[0];mutation(c)
    with pytest.raises(QGError):validate_case(freeze(c),synthetic=True)


def test_all_24_display_permutations_keep_scoring_identity(tmp_path):
    b,k=make_session(cases(),tmp_path/'session',order_seed=0,mapping_seed=0,synthetic=True)
    for permutation in itertools.permutations(ARMS):
        copykey=copy.deepcopy(k)
        for i,card in enumerate(b['cases'][0]['cards']):copykey['cases'][0]['identities'][card['id']]['arm']=permutation[i]
        copykey=freeze(copykey)
        report=statistics_report(b,votes(b,copykey),copykey)
        assert report['guesses']['correct']==80


def test_wrong_key_and_duplicate_guesses_rejected(tmp_path):
    b,k=make_session(cases(),tmp_path/'session',order_seed=0,mapping_seed=0,synthetic=True)
    a=votes(b,k)
    a['rounds'][0]['guesses']['A']=a['rounds'][0]['guesses']['B']
    with pytest.raises(QGError,match='GUESS'):validate_answers(b,a)
    a=votes(b,k)
    k['cases'][0]['identities'][b['cases'][0]['cards'][0]['id']]['sha256']='0'*64
    with pytest.raises(QGError,match='WRONG_KEY'):reveal(b,a,freeze(k))
