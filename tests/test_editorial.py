"""Review exports preserve human decisions and the old mechanical report."""
import copy

import pytest

from quillgrain import editorial
from quillgrain.checks import check
from quillgrain.cli import main
from quillgrain.compose import compile_context
from quillgrain.io import QGError, canonical, read_json, write_json


def test_review_uses_only_applied_human_rules_and_keeps_unknown_characters(pack, save):
    base = copy.deepcopy(pack['rules'][0])
    for id, scope in [('en', {'languages':['en']}), ('other-register', {'registers':['conversational']}),
                      ('character', {'channel':'dialogue','characters':['Mira']})]:
        pack['rules'].append({**base, 'id':id, 'scope':scope})
    ctx, _ = compile_context(save(pack), model_host='codex', register='essay')
    text = 'A fictional lamp lights a desk.'
    before = canonical(ctx); report = check(text, ctx)
    items = editorial.review_list(text, ctx)
    assert {i['rule_id'] for i in items['items']} == {'synthetic.clarity', 'character'}
    assert all(i['status'] == 'NOT_REVIEWED' for i in items['items'])
    character = next(i for i in items['items'] if i['rule_id']=='character')
    assert character['applicability'] == 'CHARACTER_SCOPE_UNAVAILABLE'
    reviewed = editorial.review_list(text, ctx, [{'character':'Mira','start':0,'end':len(text)}])
    assert all(i['applicability'] == 'AVAILABLE' for i in reviewed['items'])
    assert canonical(ctx) == before and check(text, ctx) == report
    assert editorial.markdown(items) == editorial.markdown(editorial.review_list(text, ctx))
    assert 'NOT_REVIEWED' in editorial.markdown(items).decode()
    ctx['prompt_payload'] += 'tampered'
    with pytest.raises(QGError): editorial.review_list(text, ctx)


def test_coverage_distinguishes_human_missing_character_and_executed(pack, save):
    pack['rules'][1]['scope']={'channel':'dialogue','characters':['Mira']}
    ctx, _ = compile_context(save(pack))
    text = 'Лампа светит.'
    covered = editorial.coverage(text, ctx)
    assert covered['executed_rule_ids'] == []
    assert covered['unavailable_character_rule_ids'] == ['synthetic.no-unshipped']
    assert covered['human_review_rule_ids'] == ['synthetic.clarity']
    covered = editorial.coverage(text, ctx, [{'character':'Mira','start':0,'end':len(text)}])
    assert covered['executed_rule_ids'] == ['synthetic.no-unshipped']
    pack['rules'] = pack['rules'][:1]
    ctx, _ = compile_context(save(pack))
    assert editorial.coverage(text,ctx)['mechanical_coverage'] == 'NONE'


def test_cli_opt_in_exports_and_collisions_preserve_inputs(pack, save, tmp_path):
    ctx, _ = compile_context(save(pack))
    context = tmp_path / 'context.json'; write_json(context, ctx)
    draft = tmp_path / 'draft.md'; draft.write_text('Лампа светит.',encoding='utf-8')
    before = draft.read_bytes()
    args=['check','--draft',str(draft),'--context',str(context),'--out',str(tmp_path/'check.json')]
    assert main([*args,'--review-json',str(tmp_path/'review.json'),'--review-md',str(tmp_path/'review.md')]) == 0
    assert read_json(tmp_path/'check.json') == check(before.decode('utf-8'),ctx)
    assert read_json(tmp_path/'review.json')['items'][0]['status'] == 'NOT_REVIEWED'
    assert main([*args,'--review-json',str(tmp_path/'review.json')]) == 3
    assert main([*args,'--review-md',str(draft)]) == 3
    assert draft.read_bytes() == before
