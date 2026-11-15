"""Read-only partial review. Never infer an overall vote from legacy axes."""
import itertools
from collections import Counter

from . import duel, pairwise, quickduel
from .io import digest


def _multi(blind, answers, key):
    """Read historical multi-v3 without converting or replacing its answer file."""
    duel.verify_frozen(blind); duel.verify_frozen(key)
    duel.require(blind['schema_version'] == 'duel.multi-blind/v3' and key['schema_version'] == 'duel.multi-key/v3')
    duel.require(answers['schema_version'] == 'duel.multi-answers/v3')
    duel.require(answers['session_id'] == key['session_id'] == blind['session_id'] and
                 answers['bundle_digest'] == key['bundle_digest'] == blind['digest'], 'DUEL_WRONG_SESSION')
    duel.require(len(key['cases']) == len(blind['cases']), 'DUEL_WRONG_KEY')
    arms = {i['arm'] for k in key['cases'] for i in k['identities'].values()}
    seen = []
    for c, k in zip(blind['cases'], key['cases']):
        duel.require(len(c['cards']) == 2 and c['id'] == k['id'] and
                     set(k['identities']) == {v['id'] for v in c['cards']}, 'DUEL_WRONG_KEY')
        duel.require(c['identical'] == (c['cards'][0]['text'] == c['cards'][1]['text']))
        duel.require(len({i['arm'] for i in k['identities'].values()}) == 2, 'DUEL_WRONG_KEY')
        for card in c['cards']:
            duel.require(k['identities'][card['id']]['label'] == card['label'], 'DUEL_WRONG_KEY')
        seen.extend([c['id'], *(v['id'] for v in c['cards'])])
    duel.require(len(seen) == len(set(seen)), 'DUEL_DUPLICATE_ID')
    rounds = answers['rounds']; draft = answers['draft']
    duel.require(len(rounds) <= len(blind['cases']))
    duel.require(draft is None or len(rounds) < len(blind['cases']))
    for index, r in enumerate(rounds + ([draft] if draft is not None else [])):
        c = blind['cases'][index]; committed = index < len(rounds)
        duel.require(set(r) == {'case_id', 'votes', 'guesses', 'note', 'committed_at'})
        duel.require(r['case_id'] == c['id'] and set(r['votes']) <= set(pairwise.DIMENSIONS))
        duel.require(all(v in pairwise.VOTES for v in r['votes'].values()))
        duel.require(set(r['guesses']) == {v['id'] for v in c['cards']} and
                     all(g in arms | {'unknown'} for g in r['guesses'].values()))
        duel.require(isinstance(r['note'], str) and len(r['note']) <= 4000)
        duel.require(bool(r['committed_at']) if committed else r['committed_at'] is None)
        if committed:
            duel.require(set(duel.AXES) <= set(r['votes']))
            duel.require(not c['identical'] or all(v in ('tie', 'unknown') for v in r['votes'].values()))


def partial_report(blind, answers, key, *, stopped_by_owner=False, source_map=None, input_sha256=None):
    version = blind['schema_version']
    quick = version == 'duel.quick-blind/v1'
    numeric = version == 'duel.blind-session/v1'
    legacy_numeric = None
    if quick:
        quickduel.validate_key(blind, key); quickduel.validate_answers(blind, answers)
    elif version == 'duel.pair-blind/v2':
        pairwise.validate_answers(blind, answers); pairwise._key(blind, key)
    elif version == 'duel.multi-blind/v3':
        _multi(blind, answers, key)
    else:
        # The legacy validator rejects unknown formats. Keep numeric scores separate.
        duel.validate_answers(blind, answers)
        legacy_numeric = duel.statistics_report(blind, answers, key)
        numeric = True
        duel.require(len(key['cases']) == len(blind['cases']), 'DUEL_WRONG_KEY')
        for c, k in zip(blind['cases'], key['cases']):
            duel.require(c['id'] == k['id'] and set(k['identities']) == {v['id'] for v in c['cards']}, 'DUEL_WRONG_KEY')
            for card in c['cards']:
                identity = k['identities'][card['id']]
                duel.require(identity['label'] == card['label'] and identity['sha256'] == duel.sha(card['text'].encode()), 'DUEL_WRONG_KEY')
    duel.require(stopped_by_owner or quick and answers['state'] in ('STOPPED_BY_OWNER', 'COMPLETE'), 'DUEL_STOP_ACTION_REQUIRED')
    cases = blind['cases']; count = len(answers['rounds']); planned = len(cases)
    if numeric:
        count = legacy_numeric['completed_cases']
    if source_map is not None:
        duel.verify_frozen(source_map)
        duel.require(source_map['schema_version'] == 'duel.source-map/v1' and
                     source_map['session_id'] == blind['session_id'] and source_map['bundle_digest'] == blind['digest'], 'DUEL_WRONG_SOURCE_MAP')
        duel.require([r['id'] for r in source_map['cases']] == [c['id'] for c in cases], 'DUEL_WRONG_SOURCE_MAP')
        sources = source_map['cases']
    else:
        sources = key['cases']
    arms = sorted({i['arm'] for k in key['cases'] for i in k['identities'].values()})
    if quick:
        arms = sorted(c['id'] for c in key['plan']['conditions'])
    dimensions = ('overall',) if quick else () if numeric else pairwise.DIMENSIONS
    pairs = []
    for a, b in itertools.combinations(arms, 2):
        pairs.append({'first': a, 'second': b, 'dimensions': {
            d: {'n': 0, 'status': 'NO_OBSERVATIONS', 'first_wins': 0, 'second_wins': 0,
                'ties': 0, 'unknown': 0, 'ambiguous': 0,
                **({'intensity': {v: 0 for v in quickduel.VOTES}} if quick else {})} for d in dimensions}})
    pair_index = {(p['first'], p['second']): p for p in pairs}
    def coverage(n):
        selected = key['cases'][:n]; source_rows = sources[:n]
        known_sources = all('source_id' in r or 'case_id' in r for r in source_rows)
        known_works = all('work_id' in r for r in source_rows)
        source_counts = Counter(r.get('normalized_sha256', r.get('source_id', r.get('case_id'))) for r in source_rows) if known_sources else None
        work_counts = Counter(r['work_id'] for r in source_rows) if known_works else None
        exposure = {a: {'total': 0, 'left': 0, 'right': 0, 'categories': {}} for a in arms}
        for c, k in zip(cases[:n], selected):
            for side, card in enumerate(c['cards']):
                e = exposure[k['identities'][card['id']]['arm']]; e['total'] += 1
                if len(c['cards']) == 2:
                    e['left' if side == 0 else 'right'] += 1
                g = k.get('group', 'unspecified'); e['categories'][g] = e['categories'].get(g, 0) + 1
        return {'duels': n, 'unique_sources': len(source_counts) if source_counts is not None else None,
                'repeated_source_exposures': sum(v-1 for v in source_counts.values()) if source_counts is not None else None,
                'source_exposure_histogram': dict(Counter(source_counts.values())) if source_counts is not None else None,
                'unique_works': len(work_counts) if work_counts is not None else None,
                'work_exposure_histogram': dict(Counter(work_counts.values())) if work_counts is not None else None,
                'categories': dict(Counter(k.get('group', 'unspecified') for k in selected)), 'conditions': exposure}
    guesses = {'attempted': 0, 'correct': 0, 'unknown': 0, 'ambiguous_excluded': 0}
    comments = 0
    for c, k, r in zip(cases[:count], key['cases'], answers['rounds']):
        if numeric:
            continue
        left, right = [k['identities'][v['id']]['arm'] for v in c['cards']]
        p = pair_index[tuple(sorted((left, right)))]
        for d in dimensions:
            vote = r['vote'] if quick else r['votes'].get(d, 'unknown')
            x = p['dimensions'][d]; x['n'] += 1; x['status'] = 'OBSERVED'
            if quick:
                # Record ordinal intensity, never double the weight of a strong vote.
                first_side = 'left' if left == p['first'] else 'right'
                canonical_vote = vote if first_side == 'left' or vote == 'tie' else vote.replace('left', 'TEMP').replace('right', 'left').replace('TEMP', 'right')
                x['intensity'][canonical_vote] += 1
            if c['identical']:
                x['ambiguous'] += 1
            elif vote == 'unknown':
                x['unknown'] += 1
            elif vote == 'tie':
                x['ties'] += 1
            else:
                winner = left if vote.startswith('left') else right
                x['first_wins' if winner == p['first'] else 'second_wins'] += 1
        comments += sum(bool(v.strip()) for v in r['comments'].values()) if quick else bool(r['note'].strip())
        if not quick:
            for card in c['cards']:
                g = r['guesses'][card['id']]
                guesses['ambiguous_excluded' if c['identical'] else 'unknown' if g == 'unknown' else 'attempted'] += 1
                if not c['identical'] and g != 'unknown':
                    guesses['correct'] += g == k['identities'][card['id']]['arm']
    return {'schema_version': 'duel.partial-report/v1', 'session_id': blind['session_id'],
            'bundle_digest': blind['digest'], 'answers_digest': digest(answers), 'input_sha256': input_sha256,
            'source_format': answers['schema_version'], 'status': 'COMPLETE' if count == planned else 'PARTIAL',
            'stop_reason': 'STOPPED_BY_OWNER' if count < planned else 'COMPLETED',
            'planned': coverage(planned), 'committed': coverage(count), 'draft_present': answers.get('draft') is not None,
            'draft_excluded': True, 'pairs': pairs, 'overall_available': quick,
            'legacy_numeric': {f: legacy_numeric[f] for f in ('axes', 'paired', 'owner_style', 'guesses')} if numeric else None,
            'guesses': None if quick or numeric else guesses,
            'comment_fields_filled': comments, 'causes': 'UNKNOWN_WITHOUT_COMMENTS' if comments == 0 else 'OWNER_COMMENTS_REQUIRE_SEPARATE_REVIEW',
            'conditions': key['plan']['conditions'] if quick else [{'id': a, **{f: 'UNKNOWN' for f in quickduel.FACTORS}} for a in arms],
            'limitations': ['Descriptive observations from one owner; small and unequal opponent samples do not establish a ranking.',
                           'No observations means unknown, not a tie or a loss. No win-rate league is computed.',
                           'Model, profile, examples, brief, reasoning and session may be confounded; text effects are not causal evidence.',
                           'Legacy quality axes, resemblance, guesses and numeric scores are separate; no overall vote or intensity is inferred.',
                           'Repeated sources and works are dependent observations. Missing source IDs remain unknown.',
                           'Digests verify file consistency, not publisher authenticity. Legacy multi-v3 keys have no independent card text hashes.']}
