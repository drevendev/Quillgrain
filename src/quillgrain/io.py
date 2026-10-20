"""Canonical serialization and bounded, non-executing local IO."""

import hashlib
import json
from pathlib import Path


class QGError(Exception):
    def __init__(self, code, exit_code=2):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


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
