"""Explicit local human-review lists; never an automatic style score."""
from copy import deepcopy

from .checks import check
from .contracts import verify_context, validate
from .io import sha


def coverage(text, context, scopes=(), *, report=None):
    verify_context(context)
    report = check(text, context, scopes) if report is None else report
    human = [r['id'] for r in context['rules_applied'] if r['enforcement'] == 'human_review']
    unavailable = [s.removesuffix(':CHARACTER_SCOPE_UNAVAILABLE') for s in report['skipped_checks']
                   if s.endswith(':CHARACTER_SCOPE_UNAVAILABLE')]
    executed = [r['id'] for r in context['rules_applied']
                if r['enforcement'] != 'human_review' and r['id'] not in unavailable]
    return {'executed_rule_ids': executed, 'human_review_rule_ids': human,
            'unavailable_character_rule_ids': unavailable,
            'mechanical_coverage': 'EXECUTED' if executed else 'NONE', 'voice_quality': 'NOT_MEASURED'}


def review_list(text, context, scopes=()):
    verify_context(context)
    # Reuse the checker's span validation, including bounds and overlap checks.
    check(text, context, scopes)
    characters = {s['character'] for s in scopes if s['start'] < s['end']}
    items = []
    for rule in context['rules_applied']:
        if rule['enforcement'] != 'human_review':
            continue
        named = set(rule['scope'].get('characters', []))
        items.append({'rule_id': rule['id'], 'instruction': rule['instruction'],
                      'language': context['language'], 'register': context['register'],
                      'tags': list(context['tags']), 'scope': deepcopy(rule['scope']),
                      'applicability': 'CHARACTER_SCOPE_UNAVAILABLE' if named and not named & characters else 'AVAILABLE',
                      'status': 'NOT_REVIEWED'})
    result = {'schema_version': 'quillgrain.editorial-review/v1', 'context_build_id': context['build_id'],
              'draft_sha256': sha(text.encode('utf-8')), 'items': items}
    return validate(result, 'editorial-review')


def markdown(review):
    lines = ['# Editorial review', '', 'Read the whole draft before using this list.', '',
             'Context: `' + review['context_build_id'] + '`', '',
             'Draft SHA-256: `' + review['draft_sha256'] + '`', '',
             'Record decisions separately; an unanswered item remains NOT_REVIEWED.', '']
    for item in review['items']:
        lines.extend(['## ' + item['rule_id'].replace('\n', ' '), '', item['instruction'], '',
                      '- Status: NOT_REVIEWED', '- Applicability: ' + item['applicability'],
                      '- Language / register: ' + item['language'] + ' / ' + item['register'],
                      '- Tags: ' + ', '.join(item['tags']),
                      '- Scope: ' + repr(item['scope']), ''])
    return ('\n'.join(lines) + '\n').encode('utf-8')
