"""Canonical serialization and bounded, non-executing local IO."""

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path


class QGError(Exception):
    def __init__(self, code, exit_code=2, details=None):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}


def canonical(value):
    # qg-json-v1: sorted keys, compact separators, UTF-8, no NaN, trailing LF.
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise QGError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(QGError("NONFINITE_JSON")))


def write_json(path, value):
    write_bytes(path, canonical(value))


def write_bytes(path, value):
    path = safe_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_destination(path)
    temporary = path.with_name('.qg-write-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        safe_destination(path)
        # Replacing a regular hardlink replaces the directory entry, never its source.
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def is_link(path):
    """Includes Windows reparse points, not just symbolic links."""
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def safe_destination(path):
    # Do not resolve first: that would hide a link in the supplied path.
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        if is_link(part):
            raise QGError('OUTPUT_LINK_DENIED', 3)
    return path


def publish_bundle(output, members):
    """Create-only bundle. Failed staging is never exposed as the final output."""
    output = safe_destination(output)
    if os.path.lexists(output):
        raise QGError('OUTPUT_ALREADY_EXISTS', 3)
    files = {}
    for name, data in members.items():
        rel = Path(name)
        if rel.is_absolute() or rel.drive or '..' in rel.parts or not rel.parts:
            raise QGError('PATH_ESCAPE', 3)
        if not isinstance(data, bytes):
            raise QGError('BUNDLE_BYTES_REQUIRED')
        files[rel] = data
    output.parent.mkdir(parents=True, exist_ok=True)
    safe_destination(output)
    staging = output.with_name('.qg-incomplete-' + uuid.uuid4().hex)
    staging.mkdir()
    for rel, data in files.items():
        write_bytes(staging / rel, data)
    safe_destination(output)
    if os.path.lexists(output):
        raise QGError('OUTPUT_ALREADY_EXISTS', 3)
    # Single-operator local transaction; not a lock against a malicious concurrent writer.
    staging.rename(output)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def bounded(root, relative):
    root = Path(root).resolve(strict=True)
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or relative.drive:
        raise QGError("PATH_ESCAPE", 3)
    target = (root / relative).resolve(strict=True)
    if not target.is_relative_to(root):
        raise QGError("PATH_ESCAPE", 3)
    return target
