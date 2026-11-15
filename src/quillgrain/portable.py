"""Shared stdlib context invariants and relocatable skill verifier.

This exact file ships as scripts/voice_context.py. Full JSON Schema validation
belongs to the engine; integrity, lineage, lock and host checks are shared.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


class QGError(Exception):
    def __init__(self, code, exit_code=2, details=None):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(canonical(value))


def strict_json(text):
    def finite_float(token):
        value = float(token)
        if not math.isfinite(value):
            raise QGError('NONFINITE_JSON')
        return value

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise QGError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_float=finite_float,
                      parse_constant=lambda _: (_ for _ in ()).throw(QGError('NONFINITE_JSON')))


def _require(ok, code):
    if not ok:
        raise QGError(code, 3)


def _unique(items, field='id'):
    _require(len({item[field] for item in items}) == len(items), 'DUPLICATE_ID')


def verify_context(context):
    """Semantic invariants only. The engine additionally validates JSON Schema."""
    try:
        _require(context['schema_version'] in ('quillgrain.compiled-context/v1',
                                              'quillgrain.compiled-context/v2'), 'CONTEXT_VERSION_UNSUPPORTED')
        _require(context['canonicalization'] == 'qg-json-v1', 'CONTEXT_CANONICALIZATION_UNSUPPORTED')
        _require(digest({k: v for k, v in context.items() if k != 'build_id'}) == context['build_id'],
                 'CONTEXT_DIGEST_MISMATCH')
        payload, budget = context['prompt_payload'], context['budget']
        _require(isinstance(payload, str) and budget['unit'] == 'unicode_codepoints'
                 and type(budget['used_codepoints']) is int and type(budget['max_codepoints']) is int,
                 'CONTEXT_BUDGET_MISMATCH')
        _require(len(payload) == budget['used_codepoints'], 'CONTEXT_BUDGET_MISMATCH')
        _require(0 <= budget['used_codepoints'] <= budget['max_codepoints'], 'BUDGET_EXCEEDED')
        for field in ('packs', 'rules_applied', 'examples_selected'):
            _unique(context[field])
        _require(bool(context['packs']) and isinstance(context['model_host'], str)
                 and isinstance(context['language'], str) and isinstance(context['register'], str), 'CONTEXT_INVALID')
        for rule in context['rules_applied']:
            scope = rule['scope']
            _require(isinstance(scope, dict) and scope.get('channel', 'all') in ('all', 'narration', 'dialogue'),
                     'CONTEXT_RULE_INVALID')
            _require(all(isinstance(scope.get(f, []), list) and all(isinstance(v, str) for v in scope.get(f, []))
                         for f in ('languages', 'registers', 'tags', 'characters')), 'CONTEXT_RULE_INVALID')
            _require(rule['enforcement'] in ('human_review', 'required_literal', 'forbidden_literal', 'max_chars')
                     and isinstance(rule['instruction'], str), 'CONTEXT_RULE_INVALID')
            _require((not scope.get('languages') or context['language'] in scope['languages'])
                     and (not scope.get('registers') or context['register'] in scope['registers'])
                     and set(scope.get('tags', [])) <= set(context['tags']), 'CONTEXT_RULE_SCOPE')
        if context['schema_version'] == 'quillgrain.compiled-context/v2':
            _unique(context['corpora'])
            _unique(context['corpus_materials'], 'example_id')
            _unique(context['evidence_refs'], 'evidence_id')
            corpora = {c['id'] for c in context['corpora']}
            evidence_used = {i for r in context['rules_applied'] for i in r['evidence_ids']}
            _require(all(e['evidence_id'] in evidence_used and e['corpus_id'] in corpora
                         for e in context['evidence_refs']), 'CONTEXT_EVIDENCE_MISMATCH')
            examples = {e['id']: e for e in context['examples_selected']}
            for material in context['corpus_materials']:
                example = examples.get(material['example_id'])
                _require(example is not None and example['source_id'] == material['source_id']
                         and example['work_id'] == material['work_id']
                         and sha(example['text'].encode('utf-8')) == material['sha256']
                         and material['corpus_id'] in corpora, 'CONTEXT_CORPUS_LINEAGE_MISMATCH')
            _require(context['example_mode'] in ('auto', 'none'), 'CONTEXT_EXAMPLE_MODE_MISMATCH')
            _require(context['example_mode'] != 'none' or not context['examples_selected'],
                     'CONTEXT_EXAMPLE_MODE_MISMATCH')
        return context
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
        raise QGError('CONTEXT_INVALID', 3) from exc


def verify_lock(context, lock):
    try:
        expected = {'engine_version', 'packs'}
        if context['schema_version'] == 'quillgrain.compiled-context/v2':
            expected |= {'schema_version', 'corpora'}
            _require(lock['schema_version'] == 'quillgrain.lock/v2' and lock['corpora'] == context['corpora'],
                     'LOCK_DIGEST_MISMATCH')
        _require(set(lock) == expected and digest(lock) == context['lock_digest']
                 and lock['packs'] == context['packs'] and lock['engine_version'] == context['engine_version'],
                 'LOCK_DIGEST_MISMATCH')
    except (KeyError, TypeError, ValueError) as exc:
        raise QGError('LOCK_DIGEST_MISMATCH', 3) from exc


def verify_host(context, host, lock=None):
    verify_context(context)
    try:
        _require(context['model_host'] == host, 'CONTEXT_HOST_MISMATCH')
        permission = context['permissions']
        _require(permission['retrieval'] is True and isinstance(permission['approved_model_hosts'], list)
                 and host in permission['approved_model_hosts'], 'CONTEXT_HOST_DENIED')
        for example in context['examples_selected']:
            p = example['permissions']
            _require(p['retrieval'] is True and host in p['approved_model_hosts'], 'CONTEXT_HOST_DENIED')
            _require(example['language'] == context['language'] and example['register'] == context['register']
                     and set(example['tags']) <= set(context['tags']), 'CONTEXT_EXAMPLE_SCOPE')
        if lock is not None:
            verify_lock(context, lock)
        return context
    except (KeyError, TypeError, AttributeError) as exc:
        raise QGError('CONTEXT_INVALID', 3) from exc


def metadata(context, *, lock_verified=False):
    methods = {}
    for rule in context['rules_applied']:
        method = rule['enforcement']
        methods[method] = methods.get(method, 0) + 1
    return {'status': 'VERIFIED', 'build_id': context['build_id'], 'model_host': context['model_host'],
            'language': context['language'], 'register': context['register'], 'packs': context['packs'],
            'lock_verified': lock_verified, 'rule_methods': methods,
            'checks': ['digest', 'budget', 'scope', 'lineage', 'host', 'permissions'] + (['lock'] if lock_verified else []),
            'full_json_schema': 'NOT_RUN', 'voice_quality': 'NOT_MEASURED'}


def _read(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    _require(len(raw) <= 16 * 1024 * 1024, 'CONTEXT_TOO_LARGE')
    return strict_json(raw.decode('utf-8-sig'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify a portable Quillgrain context without the engine')
    references = Path(__file__).resolve().parent.parent / 'references'
    parser.add_argument('--context', type=Path, default=references / 'context.json')
    parser.add_argument('--lock', type=Path, default=references / 'quillgrain.lock.json')
    parser.add_argument('--host', required=True)
    parser.add_argument('--language')
    parser.add_argument('--register')
    parser.add_argument('--show', action='store_true', help='Print only the verified prompt payload')
    args = parser.parse_args(argv)
    try:
        context = verify_host(_read(args.context), args.host, _read(args.lock))
        _require(args.language is None or args.language == context['language'], 'CONTEXT_LANGUAGE_MISMATCH')
        _require(args.register is None or args.register == context['register'], 'CONTEXT_REGISTER_MISMATCH')
        print(context['prompt_payload'] if args.show else json.dumps(metadata(context, lock_verified=True), ensure_ascii=False))
        return 0
    except QGError as exc:
        print(exc.code, file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print('CONTEXT_UNAVAILABLE_OR_INVALID', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
