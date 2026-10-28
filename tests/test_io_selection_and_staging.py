"""Synthetic selection ambiguity and handled publication failures."""
from pathlib import Path

import pytest

from quillgrain import io


@pytest.mark.parametrize('loader', [io.read_json, io.read_jsonl])
@pytest.mark.parametrize(('text', 'code'), [
    ('{"selection":"excluded","selection":"reference"}', 'DUPLICATE_JSON_KEY'),
    ('{"nested":{"a":1,"a":2}}', 'DUPLICATE_JSON_KEY'),
    ('{"score":NaN}', 'NONFINITE_JSON'),
    ('{"score":Infinity}', 'NONFINITE_JSON'),
    ('{"score":-Infinity}', 'NONFINITE_JSON'),
    ('{"score":1e999}', 'NONFINITE_JSON'),
    ('{"score":-1e999}', 'NONFINITE_JSON'),
    ('{"nested":{"score":1e999}}', 'NONFINITE_JSON'),
    ('{"nested":[-1e999]}', 'NONFINITE_JSON'),
])
def test_json_and_selection_jsonl_reject_the_same_ambiguities(tmp_path, loader, text, code):
    path = tmp_path / 'selection.jsonl'
    path.write_text(text + '\n', encoding='utf-8')
    with pytest.raises(io.QGError, match=code):
        loader(path)


def test_jsonl_preserves_bom_blank_lines_and_valid_values(tmp_path):
    path = tmp_path / 'selection.jsonl'
    path.write_text('\ufeff\n{"selection":"reference","note":"NaN"}\n \t\n'
                    '{"selection":"evaluation","score":1.25}\n', encoding='utf-8')
    assert io.read_jsonl(path) == [
        {'selection': 'reference', 'note': 'NaN'},
        {'selection': 'evaluation', 'score': 1.25},
    ]


@pytest.mark.parametrize('failed_write', [1, 2])
def test_write_failure_removes_only_owned_staging(tmp_path, monkeypatch, failed_write):
    neighbor = tmp_path / 'neighbor'
    neighbor.mkdir()
    (neighbor / 'keep').write_bytes(b'UNCHANGED')
    write = io.write_bytes
    calls = 0
    def failing_write(path, data):
        nonlocal calls
        calls += 1
        if calls == failed_write:
            raise OSError('synthetic write failure')
        write(path, data)
    monkeypatch.setattr(io, 'write_bytes', failing_write)
    with pytest.raises(OSError, match='synthetic write failure'):
        io.publish_bundle(tmp_path / 'final', {'a': b'FIRST', 'b': b'SECOND'})
    assert list(tmp_path.iterdir()) == [neighbor]
    assert (neighbor / 'keep').read_bytes() == b'UNCHANGED'


def test_rename_failure_leaves_no_staging(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('synthetic rename failure')
    monkeypatch.setattr(Path, 'rename', fail)
    with pytest.raises(OSError, match='synthetic rename failure'):
        io.publish_bundle(tmp_path / 'final', {'a': b'FIRST'})
    assert not list(tmp_path.iterdir())


def test_existing_destination_created_during_staging_is_preserved(tmp_path, monkeypatch):
    final = tmp_path / 'final'
    write = io.write_bytes
    def competing_write(path, data):
        write(path, data)
        final.mkdir()
        (final / 'keep').write_bytes(b'EXISTING')
    monkeypatch.setattr(io, 'write_bytes', competing_write)
    with pytest.raises(io.QGError, match='OUTPUT_ALREADY_EXISTS'):
        io.publish_bundle(final, {'a': b'FIRST'})
    assert list(tmp_path.iterdir()) == [final]
    assert (final / 'keep').read_bytes() == b'EXISTING'


def test_cleanup_failure_keeps_original_error_and_a_safe_note(tmp_path, monkeypatch):
    def write_failure(*args):
        raise OSError('original failure')
    def cleanup_failure(*args):
        raise PermissionError('private path must not enter the note')
    monkeypatch.setattr(io, 'write_bytes', write_failure)
    monkeypatch.setattr(io.shutil, 'rmtree', cleanup_failure)
    with pytest.raises(OSError, match='original failure') as caught:
        io.publish_bundle(tmp_path / 'final', {'a': b'FIRST'})
    assert caught.value.__notes__ == ['Incomplete bundle retained because staging cleanup failed.']
    assert not (tmp_path / 'final').exists()
    assert len(list(tmp_path.glob('.qg-incomplete-*'))) == 1
