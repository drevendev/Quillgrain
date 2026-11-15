import argparse
import subprocess
import sys

import pytest

from quillgrain import lengths


def test_counter_and_complete_budgets():
    assert lengths.count_words('— UI: 120, USB-C, кое-кто, Wi‑Fi\n# Heading\n```\nДва слова.\n```') == 7
    report = lengths.budget_report(['два слова', 'ещё два'], minimum=5, part_ranges=[(2, 3), (2, 3)])
    assert all(p['status'] == 'PASS' for p in report['parts']) and report['total']['status'] == 'UNDER'
    report = lengths.budget_report(['один', 'два три четыре'], minimum=4, maximum=4,
                                  part_ranges=[(2, 2), (2, 3)])
    assert report['total']['status'] == 'PASS' and report['parts'][0]['status'] == 'UNDER'


def test_planner_against_exhaustive_feasible_completions():
    for prefix in range(4):
        for minimum in range(7):
            for maximum in range(minimum, 8):
                report = lengths.plan_next(['слово ' * prefix], minimum=minimum, maximum=maximum,
                                           next_range=(1, 4), remaining_ranges=[(1, 2)])
                feasible = [n for n in range(1, 5) if any(minimum <= prefix + n + later <= maximum
                                                        for later in range(1, 3))]
                assert report['completion'] == 'INCOMPLETE'
                if feasible:
                    assert report['status'] == 'READY'
                    assert report['next'] == {'min': min(feasible), 'max': max(feasible)}
                else:
                    assert report['status'] == 'CONFLICT'


def test_empty_prefix_unbounded_and_conflict():
    assert lengths.plan_next([], minimum=10, maximum=12, next_range=(1, 20))['next'] == {'min': 10, 'max': 12}
    assert lengths.plan_next(['x ' * 13], maximum=12)['status'] == 'CONFLICT'
    assert lengths.plan_next([], minimum=10, next_range=(None, None), remaining_ranges=[(0, None)])['next'] == {'min': 0, 'max': None}
    with pytest.raises(ValueError):
        lengths.plan_next([], next_range=(4, 3))


def test_portable_cli_plan_and_one_word_miss(tmp_path):
    prefix = tmp_path / 'prefix.txt'; prefix.write_text('x ' * 16, encoding='utf-8')
    run = subprocess.run([sys.executable, '-I', '-S', lengths.__file__, '--input', str(prefix),
                          '--plan-next', '--next-range', '3:5', '--min-words', '20', '--max-words', '24'],
                         capture_output=True, text=True)
    assert run.returncode == 0 and '"min": 4' in run.stdout
    assert lengths.budget_report(['x ' * 19], minimum=20)['total']['status'] == 'UNDER'
    assert lengths.budget_report(['короткий ответ'])['status'] == 'PASS'


def test_engine_cli_plan_exit_status(capsys):
    from quillgrain.cli import main
    assert main(['length', '--plan-next', '--next-range', '2:4', '--min-words', '3']) == 0
    assert 'READY' in capsys.readouterr().out
    assert main(['length', '--plan-next', '--next-range', '2:4', '--max-words', '1']) == 1
    assert 'CONFLICT' in capsys.readouterr().out
