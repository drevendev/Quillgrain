"""Allowlist repository/archive members and scan caller-supplied private canaries."""
import argparse
import tarfile
import zipfile
import subprocess
from pathlib import Path, PurePosixPath

ROOT_FILES = {"README.md", "AGENTS.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md",
              "pyproject.toml", "MANIFEST.in", ".gitignore", "requirements-dev.lock.txt"}
ROOT_DIRS = {"src", "schemas", "tests", "examples", "scripts", "docs", ".github", "templates", "skills"}
DENIED = {".private", "corpus", "runs", "exports", "Quillgrain_Dreven", "Quillgrain_Corpus", "Quillgrain_Voice_Dreven", "voice_reference.txt", "source-roots.local.json"}
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist"}


def source_members(root):
    if (root / ".git").exists():
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout
        untracked = subprocess.run(['git','-C',str(root),'ls-files','--others','--exclude-standard','-z'], capture_output=True, check=True).stdout
        candidates = [root / name.decode('utf-8') for name in set((tracked + untracked).split(b'\0')) if name]
    else:
        candidates = root.rglob("*")
    for file in candidates:
        relative = file.relative_to(root)
        if any(part in SKIP or part.endswith(".egg-info") for part in relative.parts):
            continue
        if file.is_file():
            if relative.parts[0] not in ROOT_DIRS and relative.as_posix() not in ROOT_FILES:
                raise ValueError("UNAPPROVED_PUBLIC_FILE")
            yield relative.as_posix(), file.read_bytes()


def archive_members(path):
    if path.suffix == ".whl" or path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if not member.is_dir():
                    yield member.filename, archive.read(member)
    else:
        with tarfile.open(path) as archive:
            for member in archive:
                if member.isfile():
                    yield member.name, archive.extractfile(member).read()
                elif member.issym() or member.islnk():
                    raise ValueError("ARCHIVE_LINK_DENIED")


def audit(members, tokens=()):
    count = 0
    for name, data in members:
        parts = PurePosixPath(name).parts
        if ".." in parts or any(p in DENIED for p in parts) or name.startswith("/"):
            raise ValueError("PRIVATE_OR_UNSAFE_ARCHIVE_MEMBER")
        if any(token in data for token in tokens):
            raise ValueError("PRIVATE_CANARY_FOUND")
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--archive", type=Path, action="append", default=[])
    parser.add_argument("--deny-token-file", type=Path)
    args = parser.parse_args()
    tokens = [line for line in args.deny_token_file.read_bytes().splitlines() if line] if args.deny_token_file else []
    count = audit(source_members(args.source), tokens) if args.source else 0
    for path in args.archive:
        count += audit(archive_members(path), tokens)
    print("PUBLIC_AUDIT_OK", count)
