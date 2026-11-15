"""Frozen fiction/rewrite inputs with explicit task and text provenance."""
from copy import deepcopy
import random
import re
import secrets
import unicodedata

from .duel import freeze, verify_frozen, require
from .io import canonical, digest, publish_bundle, sha
from .lengths import budget_report, count_words


TASKS = ('rewrite', 'continuation', 'new_scene')
RESEARCH_FIELDS = {'question', 'stage', 'word_budget', 'context_policy', 'comparison_goal',
                   'control_condition', 'controlled_factors', 'limitations'}
SOURCE_FIELDS = {'id', 'work_id', 'group', 'split', 'task_kind', 'source_text', 'fact_pack',
                 'purpose', 'rights', 'meaning_reviewed', 'authorship'}


def _string(value):
    return isinstance(value, str) and 0 < len(value) <= 4000


def _strings(value):
    return isinstance(value, list) and all(_string(x) for x in value)


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _normalize(value):
    if isinstance(value, str):
        return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip()
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def input_hash(source):
    return sha(canonical({'task_kind': source['task_kind'], 'source_text': source['source_text'],
                          'fact_pack': source['fact_pack']}))


def normalized_input(source):
    # A rewritten excerpt must not recur with a different brief. A scene has no
    # prose source: deduplicate its canonical, normalized fact pack instead.
    value = source['source_text'] if source['source_text'] is not None else source['fact_pack']
    return digest(_normalize(value))


def _fact_pack(value, task):
    require(isinstance(value, dict) and set(value) == {'characters', 'action', 'conflict', 'facts', 'stop',
                                                     'information_status', 'document_form'}, 'DUEL_FACT_PACK_INVALID')
    require(isinstance(value['characters'], list) and _strings(value['facts']))
    require(all(_string(value[f]) for f in ('action', 'conflict', 'stop')))
    require(value['information_status'] in ('fictional', 'concept', 'factual') and
            value['document_form'] in ('scene', 'direct_description', 'conditional_reasoning'))
    ids = []
    for actor in value['characters']:
        require(set(actor) == {'id', 'relations', 'knowledge'} and _string(actor['id'])
                and _strings(actor['relations']) and _strings(actor['knowledge']), 'DUEL_FACT_PACK_INVALID')
        ids.append(actor['id'])
    require(len(ids) == len(set(ids)))
    if task == 'new_scene':
        require(bool(ids) and value['document_form'] == 'scene', 'DUEL_SCENE_REQUIRED')


def validate_manifest(manifest):
    from .quickduel import _conditions, FACTORS
    require(isinstance(manifest, dict) and set(manifest) == {'schema_version', 'research', 'conditions',
                                                            'sources', 'reference_work_ids', 'quotas'}, 'DUEL_MANIFEST_FIELDS')
    require(manifest['schema_version'] == 'duel.quick-sources/v2')
    conditions = manifest['conditions']; _conditions(conditions)
    require(all(set(c) == {'id', 'kind', *FACTORS, 'profile_snapshot'} for c in conditions))
    for condition in conditions:
        snapshot = condition['profile_snapshot']
        if snapshot is None:
            require(condition['kind'] == 'original' or condition['profile'] == 'none', 'DUEL_PROFILE_SNAPSHOT_REQUIRED')
        else:
            require(condition['kind'] == 'model' and set(snapshot) == {'packs', 'context_build_id'}
                    and _hash(snapshot['context_build_id']) and isinstance(snapshot['packs'], list)
                    and bool(snapshot['packs']), 'DUEL_PROFILE_SNAPSHOT_REQUIRED')
            for pack in snapshot['packs']:
                require(set(pack) == {'id', 'version', 'digest'} and _string(pack['id'])
                        and _string(pack['version']) and _hash(pack['digest']), 'DUEL_PROFILE_SNAPSHOT_REQUIRED')
            require(len({p['id'] for p in snapshot['packs']}) == len(snapshot['packs']))
    research = manifest['research']
    require(isinstance(research, dict) and set(research) == RESEARCH_FIELDS, 'DUEL_RESEARCH_REQUIRED')
    require(all(_string(research[f]) for f in ('question', 'context_policy')) and
            research['stage'] in ('development', 'reserve') and _strings(research['limitations']))
    bounds = research['word_budget']
    require(set(bounds) == {'min', 'max'} and type(bounds['min']) is int and type(bounds['max']) is int
            and 1 <= bounds['min'] <= bounds['max'] <= 100000, 'DUEL_WORD_BUDGET_INVALID')
    require(_strings(research['controlled_factors']) and set(research['controlled_factors']) <= set(FACTORS))
    for factor in research['controlled_factors']:
        require(len({c[factor] for c in conditions}) == 1 and conditions[0][factor] != 'UNKNOWN', 'DUEL_CONTROLLED_FACTOR_MISMATCH')
    require(research['comparison_goal'] in ('screening', 'version_change'))
    control = research['control_condition']
    if research['comparison_goal'] == 'version_change':
        by_id = {c['id']: c for c in conditions}
        require(control in by_id and by_id[control]['kind'] == 'model'
                and by_id[control]['profile'] != 'UNKNOWN' and by_id[control]['profile_snapshot'] is not None
                and any(c['kind'] == 'model' and c['profile'] != by_id[control]['profile']
                        and c['profile'] != 'UNKNOWN' and c['profile_snapshot'] is not None
                        and c['profile_snapshot']['context_build_id'] != by_id[control]['profile_snapshot']['context_build_id']
                        for c in conditions), 'DUEL_PREVIOUS_SNAPSHOT_REQUIRED')
    else:
        require(control is None)
    references = manifest['reference_work_ids']; require(_strings(references))
    sources = manifest['sources']; require(isinstance(sources, list) and bool(sources))
    ids, hashes, work_splits = set(), set(), {}
    for source in sources:
        require(isinstance(source, dict) and set(source) == SOURCE_FIELDS, 'DUEL_SOURCE_FIELDS')
        require(all(_string(source[f]) for f in ('id', 'work_id', 'group', 'purpose')))
        require(source['task_kind'] in TASKS and source['split'] in ('development', 'reserve'))
        require(source['meaning_reviewed'] is True, 'DUEL_REVIEW_REQUIRED')
        require(source['authorship'] in ('human', 'ai_assisted', 'unknown', 'synthetic_ai_prepared'))
        rights = source['rights']
        require(set(rights) == {'reviewed', 'basis', 'evidence_ref', 'permitted_uses'} and rights['reviewed'] is True
                and _string(rights['basis']) and _string(rights['evidence_ref']) and _strings(rights['permitted_uses'])
                and 'local_evaluation' in rights['permitted_uses'], 'DUEL_RIGHTS_REQUIRED')
        if source['task_kind'] == 'new_scene':
            require(source['source_text'] is None, 'DUEL_SCENE_HAS_NO_ORIGINAL')
        else:
            require(isinstance(source['source_text'], str) and bool(source['source_text'].strip()), 'DUEL_SOURCE_REQUIRED')
        _fact_pack(source['fact_pack'], source['task_kind'])
        h = normalized_input(source)
        require(source['id'] not in ids and h not in hashes, 'DUEL_SOURCE_REPEATED')
        ids.add(source['id']); hashes.add(h)
        work = source['work_id']
        require(work not in references, 'DUEL_REFERENCE_OVERLAP')
        require(work not in work_splits or work_splits[work] == source['split'], 'DUEL_RESERVE_OVERLAP')
        work_splits[work] = source['split']
    quotas = manifest['quotas']
    require(quotas is None or isinstance(quotas, dict) and bool(quotas)
            and all(_string(k) and type(v) is int and v > 0 for k, v in quotas.items()), 'DUEL_QUOTA_INVALID')
    return manifest


def make_plan(manifest, *, seed, budget=30):
    from . import quickduel as q
    validate_manifest(manifest)
    require(type(seed) is int and -(2**53-1) <= seed <= 2**53-1, 'DUEL_SEED_INVALID')
    require(type(budget) is int and 1 <= budget <= 1000, 'DUEL_BUDGET_INVALID')
    eligible = [s for s in manifest['sources'] if s['split'] == manifest['research']['stage']]
    require(bool(eligible), 'DUEL_STAGE_EMPTY')
    quotas = manifest['quotas']
    if quotas is not None:
        require(sum(quotas.values()) <= budget, 'DUEL_QUOTA_EXCEEDS_BUDGET')
        rng = random.Random(seed); selected = []
        for group, count in sorted(quotas.items()):
            candidates = sorted((s for s in eligible if s['group'] == group), key=lambda s: s['id'])
            require(len(candidates) >= count, 'DUEL_QUOTA_UNAVAILABLE')
            rng.shuffle(candidates); selected.extend(candidates[:count])
        eligible = selected
    if any(c['kind'] == 'original' for c in manifest['conditions']):
        require(all(s['task_kind'] == 'rewrite' for s in eligible), 'DUEL_ORIGINAL_INCOMPATIBLE_TASK')
    converted = {'schema_version':'duel.quick-sources/v1', 'conditions':manifest['conditions'], 'sources':[
        {'id':s['id'], 'work_id':s['work_id'], 'group':s['group'], 'source_text':normalized_input(s),
         'purpose':s['purpose'], 'rights_reviewed':True, 'meaning_reviewed':True} for s in eligible]}
    skeleton = q.make_plan(converted, seed=seed, budget=budget)
    by_id = {s['id']: s for s in eligible}; rows = []
    for row in skeleton['rows']:
        source = by_id[row['source_id']]
        rows.append({k:v for k,v in row.items() if k not in ('source_sha256', 'normalized_sha256')})
        rows[-1].update(input_sha256=input_hash(source), normalized_sha256=normalized_input(source),
                        task_kind=source['task_kind'])
    return freeze({'schema_version':'duel.quick-plan/v2', 'seed':seed, 'budget':budget,
                   'candidate_sources':len(eligible), 'conditions':deepcopy(manifest['conditions']),
                   'rows':rows, 'manifest':deepcopy(manifest)})


def validate_plan(plan):
    verify_frozen(plan)
    require(plan['schema_version'] == 'duel.quick-plan/v2')
    expected = make_plan(plan['manifest'], seed=plan['seed'], budget=plan['budget'])
    require(plan == expected, 'DUEL_PLAN_MISMATCH')
    return plan


def summary(plan):
    originals = {c['id'] for c in plan['conditions'] if c['kind'] == 'original'}
    return {'task_kinds':sorted({r['task_kind'] for r in plan['rows']}),
            'original_in_design':any(originals.intersection(r['pair']) for r in plan['rows'])}


def make_session(plan, outputs, output, *, synthetic=False):
    from . import quickduel as q
    validate_plan(plan)
    require(isinstance(outputs, list) and len(outputs) == len(plan['rows']), 'DUEL_OUTPUT_COUNT')
    by_source = {o['source_id']:o for o in outputs}
    require(len(by_source) == len(outputs) and set(by_source) == {r['source_id'] for r in plan['rows']}, 'DUEL_PLAN_MISMATCH')
    sources = {s['id']:s for s in plan['manifest']['sources']}
    conditions = {c['id']:c for c in plan['conditions']}
    bounds = plan['manifest']['research']['word_budget']
    sid = secrets.token_hex(16); blind_rows, key_rows = [], []
    for row in plan['rows']:
        case, source = by_source[row['source_id']], sources[row['source_id']]
        require(set(case) == {'source_id', 'input_sha256', 'variants'} and case['input_sha256'] == input_hash(source), 'DUEL_INPUT_MUTATED')
        require(set(case['variants']) == set(row['pair']), 'DUEL_PLAN_MISMATCH')
        cid = secrets.token_hex(12); cards, identities, origins = [], {}, {}
        for arm in row['pair']:
            v = case['variants'][arm]; condition = conditions[arm]; text = v['text']
            require(isinstance(text, str) and bool(text.strip()))
            require(v['sha256'] == v['raw_sha256'] == sha(text.encode('utf-8')), 'DUEL_EDITED_OUTPUT')
            require(v['input_sha256'] == row['input_sha256'] and v['plan_digest'] == plan['digest']
                    and v['condition'] == condition, 'DUEL_PLAN_MISMATCH')
            require(v['status'] == ('MOCK' if synthetic else 'ORIGINAL' if condition['kind'] == 'original' else 'LIVE'),
                    'DUEL_REAL_EVIDENCE_REQUIRED')
            original = condition['kind'] == 'original'
            if original:
                require(source['task_kind'] == 'rewrite' and text == source['source_text'], 'DUEL_SOURCE_MUTATED')
            length = budget_report([text], minimum=bounds['min'], maximum=bounds['max'])
            require(original or length['status'] == 'PASS', 'DUEL_WORD_BUDGET_MISS')
            vid = secrets.token_hex(12)
            cards.append({'id':vid, 'text':text})
            identities[vid] = {'arm':arm, 'sha256':v['sha256']}
            origins[vid] = {'kind':'unchanged_source' if original else 'model_output',
                            'authorship':source['authorship'] if original else 'model_generated',
                            'words':count_words(text), 'length_status':length['status']}
        blind_rows.append({'id':cid, 'purpose':row['purpose'], 'task_kind':row['task_kind'],
                           'cards':cards, 'identical':cards[0]['text'] == cards[1]['text']})
        key_rows.append({'id':cid, **row, 'identities':identities, 'origins':origins})
    blind = freeze({'schema_version':'duel.quick-blind/v2', 'session_id':sid,
                    'mode':'synthetic' if synthetic else 'private', 'study':summary(plan), 'cases':blind_rows})
    key = freeze({'schema_version':'duel.quick-key/v2', 'session_id':sid, 'bundle_digest':blind['digest'],
                  'plan':plan, 'cases':key_rows})
    validate_key(blind, key)
    publish_bundle(output, {'blind-session.json':canonical(blind), 'answer-key.private.json':canonical(key),
                            'plan.private.json':canonical(plan), 'Ink_Duel.html':q.browser_html(blind)})
    return blind, key


def validate_blind(blind):
    verify_frozen(blind)
    require(set(blind) == {'schema_version', 'session_id', 'mode', 'study', 'cases', 'digest'})
    require(blind['schema_version'] == 'duel.quick-blind/v2' and 1 <= len(blind['cases']) <= 1000)
    require(set(blind['study']) == {'task_kinds', 'original_in_design'}
            and type(blind['study']['original_in_design']) is bool
            and set(blind['study']['task_kinds']) <= set(TASKS))
    ids = []
    for case in blind['cases']:
        require(set(case) == {'id', 'purpose', 'task_kind', 'cards', 'identical'} and case['task_kind'] in TASKS)
        require(len(case['cards']) == 2 and case['identical'] == (case['cards'][0]['text'] == case['cards'][1]['text']))
        require(all(set(c) == {'id', 'text'} and isinstance(c['text'], str) and bool(c['text'].strip()) for c in case['cards']))
        ids.extend([case['id'], *(c['id'] for c in case['cards'])])
    require(len(ids) == len(set(ids)), 'DUEL_DUPLICATE_ID')
    require(blind['study']['task_kinds'] == sorted({c['task_kind'] for c in blind['cases']}))
    return blind


def validate_key(blind, key):
    validate_blind(blind); verify_frozen(key); validate_plan(key['plan'])
    plan = key['plan']
    require(key['schema_version'] == 'duel.quick-key/v2' and blind['study'] == summary(plan), 'DUEL_WRONG_KEY')
    require(key['session_id'] == blind['session_id'] and key['bundle_digest'] == blind['digest'], 'DUEL_WRONG_KEY')
    require(len(key['cases']) == len(blind['cases']) == len(plan['rows']), 'DUEL_WRONG_KEY')
    sources = {s['id']:s for s in plan['manifest']['sources']}
    conditions = {c['id']:c for c in plan['conditions']}
    bounds = plan['manifest']['research']['word_budget']
    for b, k, row in zip(blind['cases'], key['cases'], plan['rows']):
        require(b['id'] == k['id'] and all(k[f] == v for f,v in row.items())
                and b['purpose'] == row['purpose'] and b['task_kind'] == row['task_kind'], 'DUEL_WRONG_KEY')
        require(set(k['identities']) == set(k['origins']) == {c['id'] for c in b['cards']}, 'DUEL_WRONG_KEY')
        for card, arm in zip(b['cards'], row['pair']):
            require(k['identities'][card['id']] == {'arm':arm, 'sha256':sha(card['text'].encode())}, 'DUEL_WRONG_KEY')
            original = conditions[arm]['kind'] == 'original'
            source = sources[row['source_id']]
            if original:
                require(card['text'] == source['source_text'], 'DUEL_SOURCE_MUTATED')
            length = budget_report([card['text']], minimum=bounds['min'], maximum=bounds['max'])
            require(original or length['status'] == 'PASS', 'DUEL_WORD_BUDGET_MISS')
            require(k['origins'][card['id']] == {'kind':'unchanged_source' if original else 'model_output',
                    'authorship':source['authorship'] if original else 'model_generated',
                    'words':count_words(card['text']), 'length_status':length['status']}, 'DUEL_WRONG_KEY')
