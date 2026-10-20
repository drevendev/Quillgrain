import importlib.util
import uuid
import zipfile
from pathlib import Path
import pytest


def test_archive_barrier_rejects_private_member_and_canary(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/audit_public.py"
    spec = importlib.util.spec_from_file_location("public_audit", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    canary = uuid.uuid4().hex.encode()
    archive = tmp_path / "package.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("quillgrain/example.txt", canary)
    with pytest.raises(ValueError, match="PRIVATE_CANARY"):
        module.audit(module.archive_members(archive), [canary])
    with pytest.raises(ValueError, match="PRIVATE_OR_UNSAFE"):
        module.audit([(".private/raw.txt", b"raw")])
    assert module.audit([("quillgrain/module.py", b"original synthetic module")], [canary]) == 1
