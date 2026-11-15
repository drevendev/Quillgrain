import copy

import pytest

from quillgrain import duel, pairwise, review
from quillgrain.io import QGError, canonical
from test_duel import cases as numeric_cases, votes as numeric_answers
from test_pairwise import demo, answers as pair_answers


def test_legacy_numeric_remains_numeric_and_read_only(tmp_path):
    b, k = duel.make_session(numeric_cases(), tmp_path/'numeric', order_seed=2, mapping_seed=4, synthetic=True)
    a = numeric_answers(b, k, count=5); before = canonical(a)
    r = review.partial_report(b, a, k, stopped_by_owner=True)
    assert r['committed']['duels'] == 5 and r['planned']['duels'] == 20
    assert not r['overall_available'] and r['legacy_numeric']['axes']
    assert all(not p['dimensions'] for p in r['pairs']) and canonical(a) == before
    assert not r['draft_present']
    bad = copy.deepcopy(k); bad['cases'][-1]['identities'].clear()
    with pytest.raises(QGError): review.partial_report(b, a, duel.freeze(bad), stopped_by_owner=True)


def test_pair_v2_axes_and_guesses_are_not_overall_preferences(tmp_path):
    b, k = pairwise.make_session(demo.cases(), tmp_path/'pair', order_seed=1, mapping_seed=3, synthetic=True)
    a = pair_answers(b, 4); r = review.partial_report(b, a, k, stopped_by_owner=True)
    assert not r['overall_available'] and r['legacy_numeric'] is None
    assert r['committed']['unique_sources'] == 4
    assert sum(p['dimensions']['clarity']['n'] for p in r['pairs']) == 4
    assert all('overall' not in p['dimensions'] for p in r['pairs'])
    assert r['guesses']['attempted'] == 8
    assert sum(p['dimensions']['resemblance']['unknown'] for p in r['pairs']) == 4


def test_multi_v3_unknown_sources_and_explicit_mapping(tmp_path):
    b, k = pairwise.make_session(demo.cases(), tmp_path/'pair', order_seed=1, mapping_seed=3, synthetic=True)
    a = pair_answers(b, 5)
    b = duel.freeze({**b, 'schema_version':'duel.multi-blind/v3'})
    k = duel.freeze({'schema_version':'duel.multi-key/v3','session_id':b['session_id'],'bundle_digest':b['digest'],
                     'cases':[{'id':r['id'],'group':r['group'],'identities':{
                         v:{f:x[f] for f in ('arm','label')} for v,x in r['identities'].items()}} for r in k['cases']]})
    a.update(schema_version='duel.multi-answers/v3', bundle_digest=b['digest'])
    a['draft'] = {'case_id':b['cases'][5]['id'],'votes':{},'guesses':{v['id']:'unknown' for v in b['cases'][5]['cards']},'note':'Unfinished note','committed_at':None}
    before = canonical(a)
    r = review.partial_report(b, a, k, stopped_by_owner=True)
    assert r['committed']['unique_sources'] is None and r['draft_present']
    assert r['comment_fields_filled'] == 0 and 'Unfinished note' not in canonical(r).decode()
    mapping = duel.freeze({'schema_version':'duel.source-map/v1','session_id':b['session_id'],'bundle_digest':b['digest'],
                           'cases':[{'id':c['id'],'source_id':str(i//2),'work_id':str(i//3)} for i,c in enumerate(b['cases'])]})
    r = review.partial_report(b, a, k, stopped_by_owner=True, source_map=mapping)
    assert r['committed']['unique_sources'] == 3 and r['committed']['repeated_source_exposures'] == 2
    assert r['committed']['unique_works'] == 2 and canonical(a) == before
    bad = copy.deepcopy(mapping);bad['cases'].reverse()
    with pytest.raises(QGError): review.partial_report(b, a, k, stopped_by_owner=True, source_map=duel.freeze(bad))
    bad = copy.deepcopy(a);bad['rounds'].append(bad['rounds'][0])
    with pytest.raises(QGError): review.partial_report(b, bad, k, stopped_by_owner=True)
