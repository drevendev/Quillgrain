"""Import native observations or invoke a pinned external Python checkout."""
import json
import subprocess
from pathlib import Path
from ..io import QGError, read_json, sha

SCHEMA = "scriptorium-deterministic-metrics-v4"
PROFILES = dict(normalization="scriptorium-text-v1", metrics="scriptorium-metrics-v4",
                punctuation="scriptorium-punctuation-v2", dialogue="scriptorium-dialogue-v1",
                vocabulary="scriptorium-vocabulary-v1")


def verify_native(native):
    if not isinstance(native, dict) or native.get("schema_version") != SCHEMA or native.get("profiles") != PROFILES:
        raise QGError("NATIVE_METRICS_PROFILE_MISMATCH")


def import_observation(path, expected_hash):
    value = read_json(path)
    if value.get("provider") != "scriptorium" or value.get("input_sha256") != expected_hash:
        raise QGError("METRICS_INPUT_MISMATCH")
    if value.get("schema_profile") != SCHEMA or not value.get("revision"):
        raise QGError("METRICS_PROFILE_MISMATCH")
    native = value.get("metrics")
    verify_native(native)
    # Retain native keys, units and nulls verbatim. No substitute metrics.
    return value


BRIDGE = """
import json, sys
sys.dont_write_bytecode = True
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, sys.argv[1])
from scriptorium import analyze_deterministic_metrics
print(json.dumps(analyze_deterministic_metrics(sys.stdin.read()), ensure_ascii=False))
"""


def analyze(text, checkout=None, python=None, revision=None, language="ru", register="essay"):
    if not checkout or not python or not revision:
        return {"status": "METRICS_NOT_RUN", "provider": "scriptorium", "reason": "Pinned external checkout/runtime required"}
    checkout = Path(checkout).resolve(strict=True)
    try:
        actual = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=20).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(checkout), "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=20).stdout
    except subprocess.SubprocessError:
        raise QGError("PROVIDER_UNAVAILABLE", 4) from None
    if actual != revision or dirty:
        raise QGError("PROVIDER_REVISION_MISMATCH", 3)
    try:
        result = subprocess.run([str(python), "-I", "-c", BRIDGE, str(checkout)], input=text,
                                encoding="utf-8", capture_output=True, timeout=60)
    except subprocess.SubprocessError:
        raise QGError("PROVIDER_UNAVAILABLE", 4) from None
    if result.returncode:
        raise QGError("PROVIDER_UNAVAILABLE", 4)
    native = json.loads(result.stdout)
    verify_native(native)
    return dict(status="LIVE", provider="scriptorium", revision=revision, schema_profile=SCHEMA,
                input_sha256=sha(text.encode("utf-8")), extractor_revision="caller-supplied-prepared-text",
                language=language, register=register, profiles=native["profiles"],
                sample_counts={"characters": native["metrics"]["fantlab.general.characters"]["value"],
                               "words": native["metrics"]["fantlab.general.words"]["value"]},
                limitations=["Short input is diagnostic, not calibrated authorship."], metrics=native)
