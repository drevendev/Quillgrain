import subprocess
import sys
from pathlib import Path

import pytest

from quillgrain import lengths
from quillgrain.cli import main


@pytest.mark.parametrize('text,n', [
    ('— Ты здесь? — Да.', 3), ('UI: 120, USB-C, кое-кто, Wi‑Fi', 5),
    ('# Служебный заголовок\n\n```text\nДве строки.\n```', 2),
    ('— — ... ___ 😀', 0), ('a_b a—b', 4), ('Ёж ест 2 яблока.', 4),
])
def test_counter(text, n):
    assert lengths.count_words(text) == n


def test_total_can_fail_when_every_part_passes():
    r = lengths.budget_report(['два слова', 'ещё два'], minimum=5, part_ranges=[(2, 3), (2, 3)])
    assert all(p['status'] == 'PASS' for p in r['parts'])
    assert r['status'] == 'FAIL' and r['total']['status'] == 'UNDER'
    assert lengths.budget_report(['слово ' * 6], maximum=5)['total']['status'] == 'OVER'
    assert lengths.count_words('# Раздел\nТекст', include_headings=True) == 2


def test_cli_and_portable_helper_are_identical(tmp_path, capsys):
    p = tmp_path / 'part.txt'; p.write_text('Два слова', encoding='utf-8')
    assert main(['length', '--input', str(p), '--min-words', '3']) == 1
    assert 'UNDER' in capsys.readouterr().out
    run = subprocess.run([sys.executable, str(Path(lengths.__file__)), '--input', str(p), '--max-words', '2'], capture_output=True, text=True)
    assert run.returncode == 0 and 'PASS' in run.stdout
    with pytest.raises(ValueError):
        lengths.budget_report(['a'], minimum=10, maximum=2)
