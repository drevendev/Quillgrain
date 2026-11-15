"""Portable, deterministic word budgets. This exact file also ships in skills."""
import argparse
import json
import re
from pathlib import Path

COUNTER = 'qg-words/v1'
# Unicode letters/digits, with an internal hyphen; punctuation is not a word.
TOKEN = re.compile(r'[^\W_]+(?:[-‐‑][^\W_]+)*', re.UNICODE)
SERVICE = re.compile(r'^\s*(?:#{1,6}\s|```|~~~)')


def count_words(text, *, include_headings=False):
    lines = [line for line in text.splitlines()
             if not SERVICE.match(line) or include_headings and re.match(r'^\s*#{1,6}\s', line)]
    return len(TOKEN.findall('\n'.join(lines)))


def word_range(low, high):
    if (low is not None and (type(low) is not int or low < 0)
            or high is not None and (type(high) is not int or high < 0)
            or low is not None and high is not None and low > high):
        raise ValueError('INVALID_WORD_RANGE')
    return low, high


def plan_next(texts, *, minimum=None, maximum=None, next_range=(None, None),
              remaining_ranges=(), include_headings=False):
    """Intersect the next part with total feasibility, including future parts."""
    word_range(minimum, maximum)
    low, high = word_range(*next_range)
    remaining = [word_range(*r) for r in remaining_ranges]
    prefix = sum(count_words(t, include_headings=include_headings) for t in texts)
    future_min = sum(a or 0 for a, _ in remaining)
    future_max = None if any(b is None for _, b in remaining) else sum(b for _, b in remaining)
    low = low or 0
    if minimum is not None and future_max is not None:
        low = max(low, minimum - prefix - future_max)
    if maximum is not None:
        limit = maximum - prefix - future_min
        high = limit if high is None else min(high, limit)
    return {'schema_version': 'quillgrain.length-plan/v1', 'counter': COUNTER,
            'prefix_words': prefix, 'completion': 'INCOMPLETE', 'remaining_parts': len(remaining),
            'next': {'min': low, 'max': high},
            'status': 'CONFLICT' if high is not None and low > high else 'READY'}


def budget_report(texts, *, minimum=None, maximum=None, part_ranges=None, include_headings=False):
    def result(n, low, high):
        if low is not None and (type(low) is not int or low < 0) or high is not None and (type(high) is not int or high < 0):
            raise ValueError('INVALID_WORD_RANGE')
        if low is not None and high is not None and low > high:
            raise ValueError('INVALID_WORD_RANGE')
        return {'words': n, 'min': low, 'max': high,
                'status': 'UNDER' if low is not None and n < low else
                          'OVER' if high is not None and n > high else 'PASS'}
    texts = list(texts)
    if not texts or part_ranges is not None and len(part_ranges) != len(texts):
        raise ValueError('INVALID_PART_RANGES')
    counts = [count_words(t, include_headings=include_headings) for t in texts]
    parts = [result(n, *(part_ranges[i] if part_ranges else (None, None))) for i, n in enumerate(counts)]
    total = result(sum(counts), minimum, maximum)
    return {'schema_version': 'quillgrain.length/v1', 'counter': COUNTER,
            'headings_included': include_headings, 'parts': parts, 'total': total,
            'status': 'PASS' if total['status'] == 'PASS' and all(p['status'] == 'PASS' for p in parts) else 'FAIL'}


def arguments(parser):
    parser.add_argument('--input', type=Path, action='append', default=[], help='One file per part, in order')
    parser.add_argument('--min-words', type=int)
    parser.add_argument('--max-words', type=int)
    parser.add_argument('--part-range', action='append', metavar='MIN:MAX', help='One per part; blank endpoint is unbounded')
    parser.add_argument('--include-headings', action='store_true')
    parser.add_argument('--plan-next', action='store_true')
    parser.add_argument('--next-range', metavar='MIN:MAX')
    parser.add_argument('--remaining-range', action='append', default=[], metavar='MIN:MAX')
    return parser


def from_arguments(args):
    def parse_range(value):
        parts = value.split(':')
        if len(parts) != 2:
            raise ValueError('INVALID_WORD_RANGE')
        return word_range(*(int(x) if x else None for x in parts))
    texts = [p.read_text(encoding='utf-8-sig') for p in args.input]
    if args.plan_next:
        if args.next_range is None or args.part_range is not None:
            raise ValueError('NEXT_RANGE_REQUIRED')
        return plan_next(texts, minimum=args.min_words, maximum=args.max_words,
                         next_range=parse_range(args.next_range),
                         remaining_ranges=[parse_range(r) for r in args.remaining_range],
                         include_headings=args.include_headings)
    if args.next_range is not None or args.remaining_range:
        raise ValueError('PLAN_NEXT_REQUIRED')
    ranges = None
    if args.part_range is not None:
        ranges = [tuple(int(x) if x else None for x in r.split(':')) for r in args.part_range]
        if any(len(r) != 2 for r in ranges):
            raise ValueError('INVALID_PART_RANGES')
    return budget_report(texts,
                         minimum=args.min_words, maximum=args.max_words, part_ranges=ranges,
                         include_headings=args.include_headings)


if __name__ == '__main__':
    p = arguments(argparse.ArgumentParser(description='Check explicit word budgets without a model call.'))
    a = p.parse_args()
    try:
        report = from_arguments(a)
    except (ValueError, OSError, UnicodeError):
        p.error('INVALID_LENGTH_INPUT_OR_RANGE')
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if report['status'] in ('PASS', 'READY') else 1)
