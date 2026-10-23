"""Frozen four-way local editorial lab. No inference or private data in the client."""
import itertools
import random
import secrets
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .io import QGError, canonical, digest, sha, publish_bundle, read_json
from .contracts import validate

ARMS = ('ORIGINAL', 'MODEL_BASELINE', 'COMMON', 'SELECTED')
AXES = ('vividness', 'naturalness', 'clarity', 'conciseness', 'fidelity')
GROUPS = ('lanterra', 'frontier', 'news', 'denis')


def require(ok, code='DUEL_INVALID'):
    if not ok:
        raise QGError(code, 3)


def unsigned(value):
    return {k:v for k,v in value.items() if k != 'digest'}


def freeze(value):
    return {**unsigned(value), 'digest': digest(unsigned(value))}


def verify_frozen(value):
    require(value.get('digest') == digest(unsigned(value)), 'DUEL_DIGEST_MISMATCH')
    return value


def validate_case(case, *, synthetic=False):
    validate(case, 'duel-case')
    require(case.get('schema_version') == 'duel.case/v1')
    require(case.get('group') in GROUPS and case.get('language') == 'ru')
    require(case.get('status') == 'READY' and case.get('work_id'))
    require(isinstance(case.get('anchors'), list) and 2 <= len(case['anchors']) <= 5)
    require(all(isinstance(a, str) and a.strip() for a in case['anchors']))
    require(case.get('rights', {}).get('local_use_reviewed') is True, 'DUEL_RIGHTS_UNREVIEWED')
    require(case.get('overlap_reviewed') is True, 'DUEL_OVERLAP_UNREVIEWED')
    if not synthetic:
        require(case.get('editorial_audit', {}).get('status') == 'REVIEWED', 'DUEL_AUDIT_PENDING')
    variants = case.get('variants', {})
    require(set(variants) == set(ARMS), 'DUEL_FOUR_ARMS_REQUIRED')
    source_hash = sha(case['source_text'].encode('utf-8'))
    require(source_hash == case['source_sha256'] and variants['ORIGINAL']['text'] == case['source_text'], 'DUEL_SOURCE_MUTATED')
    inputs, models, options, seeds = set(), set(), set(), set()
    for arm, v in variants.items():
        text = v['text']
        require(isinstance(text, str) and text.strip() and len(text) <= 6000)
        require(v['sha256'] == sha(text.encode('utf-8')), 'DUEL_OUTPUT_MUTATED')
        require(1 <= v['sentences'] <= 5 and 1 <= v['words'] <= 110, 'DUEL_LENGTH_INVALID')
        if arm == 'ORIGINAL':
            require(v.get('status') == 'ORIGINAL')
            continue
        require(v.get('status') == ('MOCK' if synthetic else 'LIVE'), 'DUEL_REAL_EVIDENCE_REQUIRED')
        require(v.get('raw_text') == text, 'DUEL_EDITED_OUTPUT')
        require(v.get('source_sha256') == source_hash, 'DUEL_UNEQUAL_INPUTS')
        require(v.get('brief_sha256') == digest(case['anchors']), 'DUEL_UNEQUAL_INPUTS')
        inputs.add(v['common_input_hash'])
        models.add((v['model'], v['model_digest'], v['runtime']))
        options.add(digest(v['options']))
        seeds.add(v['seed'])
    require(len(inputs) == len(models) == len(options) == len(seeds) == 1, 'DUEL_UNEQUAL_CONDITIONS')
    verify_frozen(case)
    return case


def make_session(cases, output, *, order_seed, mapping_seed, synthetic=False):
    require(len(cases) == 20, 'DUEL_TWENTY_REQUIRED')
    for case in cases:
        validate_case(case, synthetic=synthetic)
    require(Counter(c['group'] for c in cases) == Counter({g:5 for g in GROUPS}), 'DUEL_GROUP_QUOTA')
    require(len({c['work_id'] for c in cases}) == 20, 'DUEL_WORK_REPEATED')
    require(len({c['source_sha256'] for c in cases}) == 20, 'DUEL_SOURCE_REPEATED')
    models = {(v['model'], v['model_digest'], v['runtime'], digest(v['options']))
              for c in cases for a,v in c['variants'].items() if a != 'ORIGINAL'}
    require(len(models) == 1, 'DUEL_UNEQUAL_CONDITIONS')
    rng = random.Random(order_seed)
    extra = set(rng.sample(list(GROUPS), 2))
    first, second = [], []
    for group in GROUPS:
        rows = sorted((c for c in cases if c['group'] == group), key=lambda c:c['work_id'])
        rng.shuffle(rows)
        n = 3 if group in extra else 2
        first.extend(rows[:n]); second.extend(rows[n:])
    rng.shuffle(first); rng.shuffle(second)
    mask_rng = random.Random(mapping_seed)
    latin = list(ARMS); mask_rng.shuffle(latin)
    removed = {tuple(latin[i:] + latin[:i]) for i in range(4)}
    permutations = [p for p in itertools.permutations(ARMS) if p not in removed]
    mask_rng.shuffle(permutations)
    session_id = secrets.token_hex(16)
    rows, key_rows = [], []
    for case, mapping in zip(first + second, permutations):
        cid = secrets.token_hex(12)
        cards, identities = [], {}
        for label, arm in zip('ABCD', mapping):
            vid = secrets.token_hex(12)
            cards.append({'id':vid, 'label':label, 'text':case['variants'][arm]['text']})
            identities[vid] = {'arm':arm, 'label':label, 'sha256':case['variants'][arm]['sha256']}
        rows.append({'id':cid, 'purpose':case['purpose'], 'anchors':case['anchors'], 'cards':cards})
        key_rows.append({'id':cid, 'case_id':case['id'], 'group':case['group'], 'work_id':case['work_id'],
                         'provenance':case['provenance'], 'authorship':case['authorship'],
                         'dimensions':{'register':case.get('register','unspecified'),
                                       'source_words':case['variants']['ORIGINAL']['words']},
                         'technical':case.get('technical_summary',{}),
                         'editorial_audit':case.get('editorial_audit', {}), 'identities':identities})
    blind = freeze({'schema_version':'duel.blind-session/v1', 'session_id':session_id,
        'mode':'synthetic' if synthetic else 'private', 'language':'ru', 'rubric_version':'ru-v1', 'cases':rows})
    key = freeze({'schema_version':'duel.key/v1', 'session_id':session_id, 'bundle_digest':blind['digest'],
        'order_seed':order_seed, 'mapping_seed':mapping_seed, 'cases':key_rows,
        'source_pack_digest':digest([c['digest'] for c in cases])})
    validate(blind, 'duel-blind-session')
    validate(key, 'duel-key')
    publish_bundle(output, {'blind-session.json':canonical(blind), 'answer-key.private.json':canonical(key)})
    return blind, key


def validate_answers(blind, answers, *, completed=False):
    validate(blind, 'duel-blind-session')
    validate(answers, 'duel-session')
    verify_frozen(blind)
    require(answers.get('schema_version') == 'duel.session/v1')
    require(answers.get('session_id') == blind['session_id'] and answers.get('bundle_digest') == blind['digest'], 'DUEL_WRONG_SESSION')
    records = answers.get('rounds', [])
    require(isinstance(records, list) and len(records) <= 20)
    seen = set()
    for index, record in enumerate(records):
        case = blind['cases'][index]
        require(record.get('case_id') == case['id'] and record['case_id'] not in seen, 'DUEL_ROUND_ORDER')
        seen.add(record['case_id'])
        quality = record.get('quality', {})
        require(set(quality) == {c['id'] for c in case['cards']})
        require(bool(record.get('quality_committed_at')))
        for card in case['cards']:
            vote = quality[card['id']]
            require(set(vote['scores']) == set(AXES))
            for axis, score in vote['scores'].items():
                require((axis == 'fidelity' and score is None) or type(score) is int and 1 <= score <= 5)
            require(isinstance(vote.get('note',''), str) and len(vote.get('note','')) <= 4000)
            for quote in vote.get('quotes', []):
                require(type(quote['start']) is int and type(quote['end']) is int)
                require(0 <= quote['start'] < quote['end'] <= len(card['text']))
                require(card['text'][quote['start']:quote['end']] == quote['text'], 'DUEL_QUOTE_MISMATCH')
        locked = bool(record.get('round_committed_at'))
        require(locked or index == len(records)-1, 'DUEL_ROUND_ORDER')
        if locked:
            labels = {c['label'] for c in case['cards']}
            require(record.get('preference') in labels | {'tie','none'})
            require(record.get('recognition') in ('no','maybe','yes'))
            guesses = record.get('guesses')
            require(guesses is None or isinstance(guesses, dict) and set(guesses) == labels and set(guesses.values()) == set(ARMS), 'DUEL_GUESS_INVALID')
            for vid, score in record.get('owner_style', {}).items():
                require(vid in quality and (score is None or type(score) is int and 1 <= score <= 5))
    if completed:
        require(len(records) == 20 and all(r.get('round_committed_at') for r in records), 'DUEL_NOT_COMPLETE')
    return answers


def describe(values, expected=None):
    n = len(values)
    return {'n':n, 'mean':sum(values)/n if n else None,
            'median':statistics.median(values) if n else None,
            'distribution':{str(k):values.count(k) for k in range(1,6)},
            'missing':max(0,expected-n) if expected is not None else 0}


def statistics_report(blind, answers, key):
    validate_answers(blind, answers)
    verify_frozen(key)
    require(key['session_id'] == blind['session_id'] and key['bundle_digest'] == blind['digest'], 'DUEL_WRONG_KEY')
    require([c['id'] for c in key['cases']] == [c['id'] for c in blind['cases']], 'DUEL_WRONG_KEY')
    samples = {a:{axis:[] for axis in AXES} for a in ARMS}
    favorites, preference_other = Counter(), Counter()
    confusion = {a:{g:0 for g in ARMS} for a in ARMS}
    pairs = {(a,b):{axis:[] for axis in AXES} for a,b in
             [('COMMON','MODEL_BASELINE'),('SELECTED','MODEL_BASELINE'),('SELECTED','COMMON')]
             +[(a,'ORIGINAL') for a in ARMS if a != 'ORIGINAL']}
    rows, attempted, correct, exact, abstained = [], 0, 0, 0, 0
    owner_style = {a:[] for a in ARMS}
    annotations = {'notes':0, 'quotes':0}
    for case, identities, record in zip(blind['cases'], key['cases'], answers['rounds']):
        if not record.get('round_committed_at'):
            break
        require(set(identities['identities']) == {c['id'] for c in case['cards']}, 'DUEL_WRONG_KEY')
        scores, by_label = {}, {}
        for card in case['cards']:
            identity = identities['identities'][card['id']]
            require(identity['label'] == card['label'] and identity['sha256'] == sha(card['text'].encode('utf-8')), 'DUEL_WRONG_KEY')
            arm = identity['arm']; by_label[card['label']] = arm
            scores[arm] = record['quality'][card['id']]['scores']
            owner = record.get('owner_style',{}).get(card['id'])
            if owner is not None:owner_style[arm].append(owner)
            vote = record['quality'][card['id']]
            annotations['notes'] += bool(vote.get('note'))
            annotations['quotes'] += len(vote.get('quotes',[]))
            for axis, score in scores[arm].items():
                if score is not None:samples[arm][axis].append(score)
        require(set(scores) == set(ARMS), 'DUEL_WRONG_KEY')
        for (a,b), dimensions in pairs.items():
            for axis in AXES:
                if scores[a][axis] is not None and scores[b][axis] is not None:
                    dimensions[axis].append(scores[a][axis]-scores[b][axis])
        favorite = record['preference']
        if favorite in by_label:favorites[by_label[favorite]] += 1
        else:preference_other[favorite] += 1
        guesses = record['guesses']
        if guesses:
            round_correct = 0
            for label, guess in guesses.items():
                actual = by_label[label]; confusion[actual][guess] += 1
                attempted += 1; correct += actual == guess; round_correct += actual == guess
            exact += round_correct == 4
        else:abstained += 1
        rows.append({'case_id':case['id'], 'group':identities['group'], 'scores':scores,
                     'recognition':record['recognition'], **identities.get('dimensions',{})})
    def slice_report(subset):
        return {'cases':len(subset),'axes':{a:{axis:describe(
            [r['scores'][a][axis] for r in subset if r['scores'][a][axis] is not None],len(subset))
            for axis in AXES} for a in ARMS}}
    def by_dimension(name,values):
        return {v:slice_report([r for r in rows if r.get(name)==v]) for v in values}
    technical = Counter()
    for item in key['cases']:
        for field in ('initial_requests','retries','technical_failures','final_requests'):
            technical[field] += item.get('technical',{}).get(field,0)
    return {'schema_version':'duel.report/v1', 'session_id':blind['session_id'], 'completed_cases':len(rows),
        'expected_cases':20, 'quality_status':'OWNER_REVIEW_RECORDED' if len(rows)==20 else 'PARTIAL',
        'axes':{a:{axis:describe(vals,len(rows)) for axis,vals in dimensions.items()} for a,dimensions in samples.items()},
        'paired':{a+'-'+b:{axis:{'n':len(vals),'mean_difference':sum(vals)/len(vals) if vals else None,
            'wins':sum(v>0 for v in vals),'ties':sum(v==0 for v in vals),'losses':sum(v<0 for v in vals),
            'missing_pairs':len(rows)-len(vals),'distribution':{str(k):vals.count(k) for k in range(-4,5)}}
            for axis,vals in dimensions.items()} for (a,b),dimensions in pairs.items()},
        'favorites':dict(favorites), 'decisive_favorite_cases':sum(favorites.values()), 'other_preferences':dict(preference_other),
        'favorite_shares':{a:favorites[a]/sum(favorites.values()) if sum(favorites.values()) else None for a in ARMS},
        'guesses':{'attempted':attempted,'correct':correct,'exact_rounds':exact,'abstained_rounds':abstained,'confusion':confusion},
        'slices':{'group':by_dimension('group',GROUPS),'recognition':by_dimension('recognition',('no','maybe','yes')),
                  'register':by_dimension('register',sorted({r.get('register','unspecified') for r in rows})),
                  'source_length':{'1–25':slice_report([r for r in rows if 1<=r.get('source_words',0)<=25]),
                                   '26–60':slice_report([r for r in rows if 26<=r.get('source_words',0)<=60]),
                                   '61–110':slice_report([r for r in rows if 61<=r.get('source_words',0)<=110])}},
        'technical':dict(technical), 'owner_style':{a:describe(vals,len(rows)) for a,vals in owner_style.items()},
        'annotations':annotations,'rows':rows, 'voice_status':'CANDIDATE', 'limitations':[
            'Один оценщик и одна модель; результаты описательные.',
            'Естественность не определяет авторство.',
            'Это калибровочная выборка; Denis Sexy IT ранее влиял на разработку профиля. Знакомство модели с публикациями неизвестно.']}


def reveal(blind, answers, key):
    validate_answers(blind, answers, completed=True)
    report = statistics_report(blind, answers, key)
    # JSON.parse loses Python's distinction between 3.0 and 3. Normalize integral
    # report numbers before hashing so browser JSON.stringify verifies the file.
    def browser_numbers(value):
        if isinstance(value, float) and value.is_integer():return int(value)
        if isinstance(value, list):return [browser_numbers(v) for v in value]
        if isinstance(value, dict):return {k:browser_numbers(v) for k,v in value.items()}
        return value
    return freeze(browser_numbers({'schema_version':'duel.reveal/v1', 'session_id':blind['session_id'],
                   'bundle_digest':blind['digest'], 'answers_digest':digest(answers),
                   'cases':key['cases'], 'report':report}))


def serve(blind_path, *, port=8767):
    """Whitelisted code and one blinded file only; never expose its parent directory."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from importlib.resources import files
    blind = verify_frozen(read_json(blind_path))
    if blind.get('schema_version') == 'duel.pair-blind/v2':
        from .pairwise import validate_blind
        validate_blind(blind)
        asset_dir = 'web_pairwise'
    else:
        validate(blind, 'duel-blind-session')
        asset_dir = 'web'
    assets = files('quillgrain').joinpath(asset_dir)
    routes = {'/':('text/html; charset=utf-8', lambda:assets.joinpath('index.html').read_bytes()),
              '/app.js':('text/javascript; charset=utf-8', lambda:assets.joinpath('app.js').read_bytes()),
              '/styles.css':('text/css; charset=utf-8', lambda:assets.joinpath('styles.css').read_bytes()),
              '/session.json':('application/json; charset=utf-8', canonical(blind))}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}'):
                self.send_error(403); return
            if self.path not in routes:
                self.send_error(404); return
            kind, body = routes[self.path]
            if callable(body):body = body()
            self.send_response(200)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args):pass
    print(f'Ink Duel: http://127.0.0.1:{port}/', flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
