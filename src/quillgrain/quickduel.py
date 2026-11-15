"""Source-once duels: freeze a budget before outputs; never invoke a model."""
import itertools
import random
import re
import secrets
import unicodedata
from collections import Counter
from importlib.resources import files

from .duel import freeze, verify_frozen, require
from .io import canonical, digest, publish_bundle, sha

VOTES = ('left_strong', 'left_slight', 'tie', 'right_slight', 'right_strong')
FACTORS = ('model', 'profile', 'examples', 'brief', 'reasoning', 'session')


def normalized_hash(text):
    return sha(re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip().encode())


def _string(value):
    return isinstance(value, str) and 0 < len(value) <= 4000


def _conditions(conditions):
    require(isinstance(conditions, list) and 2 <= len(conditions) <= 100)
    require(len({c['id'] for c in conditions}) == len(conditions), 'DUEL_DUPLICATE_CONDITION')
    for c in conditions:
        require(_string(c['id']) and c['kind'] in ('model', 'original'))
        require(all(_string(c[f]) for f in FACTORS), 'DUEL_PROVENANCE_REQUIRED')


def _balance_sides(rows, rng):
    """Orient each multigraph via Euler walks; every arm differs by at most one."""
    adjacency = {}; degree = Counter()
    def edge(a, b, index):
        adjacency.setdefault(a, []).append((b, index))
        adjacency.setdefault(b, []).append((a, index))
    for i, r in enumerate(rows):
        a, b = r['pair']; edge(a, b, i); degree.update((a, b))
    for i, a in enumerate(sorted(a for a, n in degree.items() if n % 2)):
        edge(a, None, len(rows)+i)
    for items in adjacency.values():
        rng.shuffle(items)
    used = set()
    for root in list(adjacency):
        stack = [root]
        while stack:
            a = stack[-1]
            while adjacency[a] and adjacency[a][-1][1] in used:
                adjacency[a].pop()
            if not adjacency[a]:
                stack.pop(); continue
            b, index = adjacency[a].pop(); used.add(index)
            if index < len(rows):
                rows[index]['pair'] = [a, b]
            stack.append(b)


def make_plan(manifest, *, seed, budget=30):
    """Input has no outputs. Category-stratified, greedily balanced incomplete design."""
    if manifest.get('schema_version') == 'duel.quick-sources/v2':
        from .quickv2 import make_plan as v2_plan
        return v2_plan(manifest, seed=seed, budget=budget)
    require(manifest['schema_version'] == 'duel.quick-sources/v1')
    require(type(budget) is int and 1 <= budget <= 1000 and type(seed) is int, 'DUEL_BUDGET_INVALID')
    conditions, sources = manifest['conditions'], manifest['sources']
    _conditions(conditions)
    require(isinstance(sources, list) and bool(sources))
    require(len({s['id'] for s in sources}) == len(sources), 'DUEL_SOURCE_REPEATED')
    hashes = set(); buckets = {}
    for source in sources:
        require(set(source) == {'id', 'work_id', 'group', 'source_text', 'purpose', 'rights_reviewed', 'meaning_reviewed'}, 'DUEL_SOURCE_FIELDS')
        require(all(_string(source[f]) for f in ('id', 'work_id', 'group', 'purpose')))
        require(isinstance(source['source_text'], str) and bool(source['source_text'].strip()))
        require(source['rights_reviewed'] is True and source['meaning_reviewed'] is True, 'DUEL_REVIEW_REQUIRED')
        h = normalized_hash(source['source_text'])
        require(h not in hashes, 'DUEL_SOURCE_REPEATED'); hashes.add(h)
        buckets.setdefault(source['group'], []).append(source)
    rng = random.Random(seed)
    for group in sorted(buckets):
        buckets[group].sort(key=lambda s: s['id']); rng.shuffle(buckets[group])
    groups = sorted(buckets); rng.shuffle(groups)
    chosen, works = [], Counter()
    while len(chosen) < min(budget, len(sources)):
        for group in groups:
            if not buckets[group] or len(chosen) >= budget:
                continue
            # Favor a fresh work, without requiring a different work for every source.
            source = min(buckets[group], key=lambda s: works[s['work_id']])
            buckets[group].remove(source); chosen.append(source); works[source['work_id']] += 1
    ids = sorted(c['id'] for c in conditions)
    exposures, categories, pairs, left, right = Counter(), Counter(), Counter(), Counter(), Counter()
    rows = []
    for source in chosen:
        options = list(itertools.combinations(ids, 2)); rng.shuffle(options)
        def score(pair):
            return (sum((exposures[a] + (a in pair)) ** 2 for a in ids),
                    sum((categories[source['group'], a] + (a in pair)) ** 2 for a in ids), pairs[pair])
        pair = min(options, key=score); pairs[pair] += 1
        orientations = [pair, tuple(reversed(pair))]; rng.shuffle(orientations)
        a, b = min(orientations, key=lambda p: sum(
            (left[i] + (i == p[0]) - right[i] - (i == p[1])) ** 2 for i in ids))
        left[a] += 1; right[b] += 1
        for arm in (a, b):
            exposures[arm] += 1; categories[source['group'], arm] += 1
        rows.append({'source_id': source['id'], 'work_id': source['work_id'], 'group': source['group'],
                     'source_sha256': sha(source['source_text'].encode()),
                     'normalized_sha256': normalized_hash(source['source_text']),
                     'purpose': source['purpose'], 'pair': [a, b]})
    _balance_sides(rows, rng)
    rng.shuffle(rows)
    return freeze({'schema_version': 'duel.quick-plan/v1', 'seed': seed, 'budget': budget,
                   'candidate_sources': len(sources), 'conditions': conditions, 'rows': rows})


def validate_plan(plan):
    if plan.get('schema_version') == 'duel.quick-plan/v2':
        from .quickv2 import validate_plan as v2_plan
        return v2_plan(plan)
    verify_frozen(plan)
    require(plan['schema_version'] == 'duel.quick-plan/v1')
    _conditions(plan['conditions'])
    rows = plan['rows']; ids = {c['id'] for c in plan['conditions']}
    require(type(plan['budget']) is int and 1 <= len(rows) <= plan['budget'] <= 1000)
    for field in ('source_id', 'normalized_sha256'):
        require(len({r[field] for r in rows}) == len(rows), 'DUEL_SOURCE_REPEATED')
    for r in rows:
        require(len(r['pair']) == 2 and len(set(r['pair'])) == 2 and set(r['pair']) <= ids)
    return plan


def make_session(plan, outputs, output, *, synthetic=False):
    if plan.get('schema_version') == 'duel.quick-plan/v2':
        from .quickv2 import make_session as v2_session
        return v2_session(plan, outputs, output, synthetic=synthetic)
    validate_plan(plan)
    require(isinstance(outputs, list) and len(outputs) == len(plan['rows']), 'DUEL_OUTPUT_COUNT')
    require(len({c['source_id'] for c in outputs}) == len(outputs), 'DUEL_SOURCE_REPEATED')
    by_source = {c['source_id']: c for c in outputs}
    require(set(by_source) == {r['source_id'] for r in plan['rows']}, 'DUEL_PLAN_MISMATCH')
    conditions = {c['id']: c for c in plan['conditions']}
    sid = secrets.token_hex(16); blind_rows, key_rows = [], []
    for row in plan['rows']:
        case = by_source[row['source_id']]
        require(sha(case['source_text'].encode()) == row['source_sha256'] and
                normalized_hash(case['source_text']) == row['normalized_sha256'], 'DUEL_SOURCE_MUTATED')
        require(set(case['variants']) == set(row['pair']), 'DUEL_PLAN_MISMATCH')
        cid = secrets.token_hex(12); cards, identities = [], {}
        for arm in row['pair']:
            v = case['variants'][arm]; text = v['text']; condition = conditions[arm]
            require(isinstance(text, str) and bool(text.strip()))
            require(v['sha256'] == sha(text.encode()) and v['raw_sha256'] == v['sha256'], 'DUEL_EDITED_OUTPUT')
            require(v['source_sha256'] == row['source_sha256'] and v['condition'] == condition and
                    v['plan_digest'] == plan['digest'], 'DUEL_PLAN_MISMATCH')
            expected = 'MOCK' if synthetic else 'ORIGINAL' if condition['kind'] == 'original' else 'LIVE'
            require(v['status'] == expected, 'DUEL_REAL_EVIDENCE_REQUIRED')
            if condition['kind'] == 'original':
                require(text == case['source_text'], 'DUEL_SOURCE_MUTATED')
            vid = secrets.token_hex(12)
            cards.append({'id': vid, 'text': text})
            identities[vid] = {'arm': arm, 'sha256': v['sha256']}
        blind_rows.append({'id': cid, 'purpose': row['purpose'], 'cards': cards,
                           'identical': cards[0]['text'] == cards[1]['text']})
        key_rows.append({'id': cid, **row, 'identities': identities})
    blind = freeze({'schema_version': 'duel.quick-blind/v1', 'session_id': sid,
                    'mode': 'synthetic' if synthetic else 'private', 'cases': blind_rows})
    key = freeze({'schema_version': 'duel.quick-key/v1', 'session_id': sid, 'bundle_digest': blind['digest'],
                  'plan': plan, 'cases': key_rows})
    validate_key(blind, key)
    publish_bundle(output, {'blind-session.json': canonical(blind), 'answer-key.private.json': canonical(key),
                            'plan.private.json': canonical(plan), 'Ink_Duel.html': browser_html(blind)})
    return blind, key


def browser_html(blind, *, standalone=True):
    assets = files('quillgrain').joinpath('web_quick')
    html = assets.joinpath('index.html').read_text(encoding='utf-8')
    if not standalone:
        return html.replace('<style>/*QUICK_CSS*/</style>', '<link rel="stylesheet" href="/styles.css">').replace(
            '<script>/*QUICK_JS*/</script>', '<script src="/app.js"></script>').replace('/*QUICK_SESSION*/', 'null').encode()
    embedded = canonical(blind).decode().replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return html.replace('/*QUICK_CSS*/', assets.joinpath('styles.css').read_text(encoding='utf-8')).replace(
        '/*QUICK_JS*/', assets.joinpath('app.js').read_text(encoding='utf-8')).replace('/*QUICK_SESSION*/', embedded).encode()


def validate_blind(blind):
    if blind.get('schema_version') == 'duel.quick-blind/v2':
        from .quickv2 import validate_blind as v2_blind
        return v2_blind(blind)
    verify_frozen(blind)
    require(blind['schema_version'] == 'duel.quick-blind/v1' and 1 <= len(blind['cases']) <= 1000)
    ids = []
    for c in blind['cases']:
        require(len(c['cards']) == 2 and c['identical'] == (c['cards'][0]['text'] == c['cards'][1]['text']))
        ids.extend([c['id'], *(v['id'] for v in c['cards'])])
    require(len(ids) == len(set(ids)), 'DUEL_DUPLICATE_ID')
    return blind


def validate_key(blind, key):
    if blind.get('schema_version') == 'duel.quick-blind/v2':
        from .quickv2 import validate_key as v2_key
        return v2_key(blind, key)
    validate_blind(blind); verify_frozen(key); validate_plan(key['plan'])
    require(key['schema_version'] == 'duel.quick-key/v1')
    require(key['session_id'] == blind['session_id'] and key['bundle_digest'] == blind['digest'], 'DUEL_WRONG_KEY')
    require(len(key['cases']) == len(blind['cases']) == len(key['plan']['rows']), 'DUEL_WRONG_KEY')
    for b, k, r in zip(blind['cases'], key['cases'], key['plan']['rows']):
        require(b['id'] == k['id'] and all(k[f] == v for f, v in r.items()), 'DUEL_WRONG_KEY')
        require(set(k['identities']) == {v['id'] for v in b['cards']}, 'DUEL_WRONG_KEY')
        for card, arm in zip(b['cards'], r['pair']):
            require(k['identities'][card['id']] == {'arm': arm, 'sha256': sha(card['text'].encode())}, 'DUEL_WRONG_KEY')


def validate_answers(blind, answers):
    validate_blind(blind)
    require(set(answers) == {'schema_version', 'session_id', 'bundle_digest', 'state', 'stopped_at', 'rounds', 'draft'})
    require(answers['schema_version'] == 'duel.quick-answers/v1' and
            answers['session_id'] == blind['session_id'] and answers['bundle_digest'] == blind['digest'], 'DUEL_WRONG_SESSION')
    rounds = answers['rounds']; n = len(rounds); total = len(blind['cases'])
    require(isinstance(rounds, list) and n <= total)
    require(answers['state'] in ('ACTIVE', 'COMPLETE', 'STOPPED_BY_OWNER'))
    require((answers['state'] == 'COMPLETE') == (n == total), 'DUEL_STATE_INVALID')
    require((answers['stopped_at'] is not None) == (answers['state'] == 'STOPPED_BY_OWNER'))
    def record(c, r, committed):
        require(set(r) == {'case_id', 'vote', 'comments', 'committed_at'})
        require(r['case_id'] == c['id'] and set(r['comments']) == {v['id'] for v in c['cards']}, 'DUEL_ROUND_ORDER')
        require(all(isinstance(x, str) and len(x) <= 4000 for x in r['comments'].values()))
        require(r['vote'] in VOTES if committed else r['vote'] is None, 'DUEL_VOTE_INVALID')
        require(_string(r['committed_at']) if committed else r['committed_at'] is None)
        require(not committed or not c['identical'] or r['vote'] == 'tie', 'DUEL_IDENTICAL_DECISION')
    for c, r in zip(blind['cases'], rounds):
        record(c, r, True)
    if answers['draft'] is not None:
        require(n < total, 'DUEL_DRAFT_AFTER_COMPLETE'); record(blind['cases'][n], answers['draft'], False)
    return answers
