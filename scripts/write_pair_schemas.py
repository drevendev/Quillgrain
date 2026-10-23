"""Generate portable v2 contracts without changing any legacy v1 contract."""
from pathlib import Path
from quillgrain.io import write_json

ROOT = Path(__file__).resolve().parents[1] / 'src/quillgrain/schemas'
ARMS = ['ORIGINAL', 'MODEL_BASELINE', 'COMMON', 'SELECTED']
GROUPS = ['lanterra', 'frontier', 'news', 'denis', 'techprose', 'classics']
AXES = ['vividness', 'naturalness', 'clarity', 'conciseness', 'fidelity', 'resemblance']
S = {'type': 'string', 'minLength': 1, 'maxLength': 4000}
H = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
def obj(props, required=None, extra=False):
    return {'type': 'object', 'properties': props, 'required': list(props) if required is None else required,
            'additionalProperties': extra}
def arr(item, minimum=0, maximum=30):
    return {'type': 'array', 'items': item, 'minItems': minimum, 'maxItems': maximum}
def save(name, value):
    write_json(ROOT / (name + '.json'), {'$schema': 'https://json-schema.org/draft/2020-12/schema', **value})
def slot(evidence=False):
    fields = {k: {'type': 'string', 'minLength': 1, 'maxLength': 300} for k in ('entity', 'relation', 'value')}
    fields['modality'] = {'enum': ['asserted', 'possible', 'proposal']}
    if evidence:fields['evidence'] = {'type': 'string', 'minLength': 1, 'maxLength': 1200}
    return obj(fields)
variant = obj({'text': {'type': 'string', 'minLength': 1, 'maxLength': 6000}, 'sha256': H,
               'words': {'type': 'integer', 'minimum': 1, 'maximum': 6000},
               'status': {'enum': ['ORIGINAL', 'LIVE', 'MOCK']}, 'raw_text': S,
               'model': S, 'model_digest': S, 'runtime': S, 'options': {'type': 'object'},
               'seed': {'type': 'integer'}, 'source_sha256': H, 'brief_sha256': H, 'common_input_hash': H},
              required=['text', 'sha256', 'words', 'status'])
variant['allOf'] = [{'if': {'properties': {'status': {'enum': ['LIVE', 'MOCK']}}},
                     'then': {'required': ['raw_text', 'model', 'model_digest', 'runtime', 'options', 'seed',
                                           'source_sha256', 'brief_sha256', 'common_input_hash']}}]
save('duel-pair-case', obj({'schema_version': {'const': 'duel.pair-case/v2'}, 'id': S,
    'group': {'enum': GROUPS}, 'work_id': S, 'language': {'const': 'ru'}, 'source_text': S,
    'source_sha256': H, 'purpose': S, 'meaning': arr(slot(True), 1, 12),
    'meaning_reviewed': {'type': 'boolean'}, 'overlap_reviewed': {'type': 'boolean'},
    'rights': obj({'local_use_reviewed': {'type': 'boolean'}}, extra=True),
    'editorial_audit': obj({'status': {'const': 'REVIEWED'}}, extra=True),
    'provenance': {'type': 'object'}, 'authorship': S,
    'variants': obj({a: variant for a in ARMS}), 'digest': H}))
card = obj({'id': S, 'label': {'enum': list('ABCD')}, 'text': {'type': 'string', 'minLength': 1, 'maxLength': 6000}})
blind_case = obj({'id': S, 'purpose': S, 'meaning': arr(slot(), 1, 12), 'cards': arr(card, 2, 2),
                  'identical': {'type': 'boolean'}})
save('duel-pair-blind', obj({'schema_version': {'const': 'duel.pair-blind/v2'}, 'session_id': S,
    'mode': {'enum': ['private', 'synthetic']}, 'language': {'const': 'ru'},
    'rubric_version': {'const': 'ru-pair-v2'}, 'cases': arr(blind_case, 30, 30), 'digest': H}))
record = obj({'case_id': S, 'votes': obj({a: {'enum': ['left', 'tie', 'right', 'unknown']} for a in AXES}, required=[]),
    'guesses': {'type': 'object', 'minProperties': 2, 'maxProperties': 2,
                'additionalProperties': {'enum': ARMS + ['unknown']}},
    'note': {'type': 'string', 'maxLength': 4000}, 'committed_at': {'type': ['string', 'null']}})
save('duel-pair-answers', obj({'schema_version': {'const': 'duel.pair-answers/v2'}, 'session_id': S,
    'bundle_digest': H, 'rounds': arr(record), 'draft': {'anyOf': [record, {'type': 'null'}]}}))
identity = obj({'arm': {'enum': ARMS}, 'label': {'enum': list('ABCD')}, 'sha256': H})
key_case = obj({'id': S, 'case_id': S, 'group': {'enum': GROUPS}, 'work_id': S,
    'identities': {'type': 'object', 'minProperties': 2, 'maxProperties': 2, 'additionalProperties': identity},
    'provenance': {'type': 'object'}, 'authorship': S, 'editorial_audit': {'type': 'object'}})
save('duel-pair-key', obj({'schema_version': {'const': 'duel.pair-key/v2'}, 'session_id': S, 'bundle_digest': H,
    'order_seed': {'type': 'integer'}, 'mapping_seed': {'type': 'integer'}, 'source_pack_digest': H,
    'cases': arr(key_case, 30, 30), 'digest': H}))
save('duel-pair-reveal', obj({'schema_version': {'const': 'duel.pair-reveal/v2'}, 'session_id': S,
    'bundle_digest': H, 'answers_digest': H, 'cases': arr(key_case, 30, 30), 'report': {'type': 'object'}, 'digest': H}))
