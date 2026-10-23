"""Read-only, allowlisted Markdown/plain-text intake. No embed expansion."""
import os
import re
import unicodedata
from pathlib import Path, PureWindowsPath
from .checks import regions
from .contracts import validate
from .io import QGError, bounded, digest, sha, read_json, write_json, canonical, publish_bundle, is_link

EXTRACTOR = "qg-narration-nfc-v2"
IGNORED = {".obsidian", ".git", ".trash", "plugins", "attachments", "assets", "secrets", "node_modules"}


def extract(raw):
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines(keepends=True)
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
        if end is None:
            raise QGError("MALFORMED_FRONTMATTER")
        start = end + 1
    labels = regions(text)
    offset, pieces, ranges = 0, [], []
    for number, line in enumerate(lines):
        if number >= start and "![[" not in line and not line.lstrip().startswith("<!--"):
            cleaned = "".join(char if labels[offset + i] == "narration" else " " for i, char in enumerate(line))
            if cleaned.strip():
                pieces.append(cleaned.strip())
                ranges.append({"start_line": number + 1, "end_line": number + 1})
        offset += len(line)
    return unicodedata.normalize("NFC", "\n".join(pieces)), ranges


def config_roots(config):
    if not isinstance(config, dict) or not isinstance(config.get('roots'), list):
        raise QGError('INVALID_SOURCE_CONFIG')
    entries = config['roots']
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('alias'), str) or not entry['alias']:
            raise QGError('INVALID_SOURCE_CONFIG')
        permissions = entry.get('permissions')
        if not isinstance(permissions, dict) or any(type(permissions.get(k)) is not bool for k in
                ('local_analysis', 'retrieval', 'private_git_excerpt', 'public_redistribution')):
            raise QGError('INVALID_SOURCE_PERMISSIONS')
        hosts = permissions.get('approved_model_hosts')
        if not isinstance(hosts, list) or any(not isinstance(h, str) for h in hosts):
            raise QGError('INVALID_SOURCE_PERMISSIONS')
        if 'include_files' in entry:
            included = entry['include_files']
            if not isinstance(included, list) or any(not isinstance(s, str) or not s for s in included):
                raise QGError('INVALID_SOURCE_ALLOWLIST')
            for name in included:
                rel = Path(name)
                if rel.is_absolute() or rel.drive or PureWindowsPath(name).drive or '..' in rel.parts or '\\' in name:
                    raise QGError('INVALID_SOURCE_ALLOWLIST')
        if type(entry.get('max_files', 10000)) is not int or entry.get('max_files', 10000) < 0:
            raise QGError('INVALID_SOURCE_LIMIT')
    if len({entry["alias"] for entry in entries}) != len(entries):
        raise QGError("DUPLICATE_SOURCE_ALIAS")
    for entry in entries:
        root = Path(entry["path"])
        if not root.is_absolute() or not root.is_dir():
            raise QGError("SOURCE_ROOT_UNAVAILABLE", 3)
    return {entry["alias"]: entry for entry in entries}


def authorize(entry, relative):
    """Called immediately before every source content read, including stale selections."""
    if not entry['permissions']['local_analysis']:
        raise QGError('SOURCE_DENIED', 3)
    rel = Path(relative)
    if rel.is_absolute() or rel.drive or PureWindowsPath(relative).drive or '..' in rel.parts or '\\' in relative:
        raise QGError('PATH_ESCAPE', 3)
    if 'include_files' in entry and rel.as_posix() not in entry['include_files']:
        raise QGError('SOURCE_NOT_ALLOWLISTED', 3)
    if rel.suffix.lower() not in ('.md', '.txt') or any(p.startswith('.') or p.lower() in IGNORED for p in rel.parts):
        raise QGError('SOURCE_TYPE_DENIED', 3)
    if re.search(r'secret|credential|password|token|api[_-]?key', rel.name, re.I):
        raise QGError('SOURCE_TYPE_DENIED', 3)
    root = Path(entry['path'])
    if is_link(root):
        raise QGError('SOURCE_LINK_DENIED', 3)
    candidate = root
    for part in rel.parts:
        candidate = candidate / part
        if is_link(candidate):
            raise QGError('SOURCE_LINK_DENIED', 3)
    candidate = bounded(root, rel)
    if not candidate.is_file():
        raise QGError('SOURCE_TYPE_DENIED', 3)
    return candidate


def guard_output(config, output):
    resolved = Path(output).resolve()
    for entry in config_roots(config).values():
        if resolved.is_relative_to(Path(entry["path"]).resolve()):
            raise QGError("SOURCE_WRITE_DENIED", 3)


def inventory(config, output):
    guard_output(config, output)
    items, skipped, hashes = [], {}, {}
    for alias, entry in sorted(config_roots(config).items()):
        if not entry['permissions']['local_analysis']:
            skipped['permission_denied'] = skipped.get('permission_denied', 0) + 1
            continue
        root = Path(entry["path"]).resolve()
        found = 0
        for directory, dirs, names in os.walk(root, followlinks=False):
            safe_dirs = []
            for name in sorted(dirs):
                child = Path(directory) / name
                if name.lower() in IGNORED or name.startswith(".") or child.is_symlink() or getattr(child, "is_junction", lambda: False)():
                    continue
                if child.resolve().is_relative_to(root):
                    safe_dirs.append(name)
            dirs[:] = safe_dirs
            for name in sorted(names):
                candidate = Path(directory) / name
                if candidate.suffix.lower() not in (".md", ".txt") or name.startswith(".") or re.search(r"secret|credential|password|token|api[_-]?key", name, re.I):
                    continue
                if candidate.is_symlink():
                    skipped["symlink"] = skipped.get("symlink", 0) + 1
                    continue
                relative = candidate.relative_to(root).as_posix()
                included = entry.get("include_files")
                if included is not None and relative not in included:
                    continue
                candidate = bounded(root, relative)
                if found >= entry.get("max_files", 10000):
                    skipped["inventory_limit"] = skipped.get("inventory_limit", 0) + 1
                    continue
                candidate = authorize(entry, relative)
                raw = candidate.read_bytes()
                try:
                    text, ranges = extract(raw)
                except (QGError, UnicodeError):
                    skipped["encoding_or_frontmatter"] = skipped.get("encoding_or_frontmatter", 0) + 1
                    continue
                raw_hash, extracted_hash = sha(raw), sha(text.encode("utf-8"))
                title = re.sub(r"(?:[ _-](?:v\d+|draft|final|черновик|редакция)\w*)+$", "", candidate.stem, flags=re.I)
                group = entry.get("work_groups", {}).get(relative, title.casefold())
                work_id = "work-" + digest(group)[:16]
                item = dict(schema_version="quillgrain.corpus-item/v1", id="source-" + digest([alias, relative])[:16],
                            work_id=work_id, source_kind=entry["source_kind"], source_alias=alias,
                            relative_locator=relative, raw_sha256=raw_hash, extraction_profile=EXTRACTOR,
                            extracted_sha256=extracted_hash, language=entry["language"], register=entry["register"],
                            authorship=entry.get("authorship", "unknown"), selection="candidate", rights=entry["rights"],
                            permissions=entry["permissions"], approval=entry["approval"], visibility="local_only",
                            ranges=ranges, limitations=["Narration-only extraction; authorship and work grouping require review."])
                if extracted_hash in hashes:
                    item["duplicate_of"], item["work_id"] = hashes[extracted_hash]
                else:
                    hashes[extracted_hash] = (item["id"], work_id)
                validate(item, "corpus-item")
                items.append(item)
                found += 1
    result = {"extraction_profile": EXTRACTOR, "items": items, "counts": {"items": len(items), "skipped": skipped}}
    write_json(output, result)
    return result["counts"]


def prepare(selection, config, output):
    guard_output(config, output)
    roots = config_roots(config)
    selected = [validate(item, "corpus-item") for item in selection if item["selection"] != "excluded"]
    by_work, by_hash, seen_ids, plans = {}, {}, set(), []
    for item in selected:
        if item["id"] in seen_ids or not re.fullmatch(r"[a-zA-Z0-9_.-]+", item["id"]):
            raise QGError("INVALID_OR_DUPLICATE_SOURCE_ID")
        seen_ids.add(item["id"])
        for lookup, key in ((by_work, item["work_id"]), (by_hash, item["extracted_sha256"])):
            if key in lookup and lookup[key] != item["selection"]:
                raise QGError("WORK_SPLIT_LEAKAGE", 3)
            lookup[key] = item["selection"]
        if item["source_alias"] not in roots or not item["permissions"]["local_analysis"]:
            raise QGError("SOURCE_DENIED", 3)
        # Selection cannot grant rights omitted by the trusted root configuration.
        trusted = roots[item["source_alias"]]["permissions"]
        if not trusted['local_analysis']:
            raise QGError('SOURCE_DENIED', 3)
        for key, value in item["permissions"].items():
            if (isinstance(value, list) and not set(value) <= set(trusted[key])) or (value is True and trusted[key] is not True):
                raise QGError("PERMISSION_ESCALATION", 3)
        source = authorize(roots[item['source_alias']], item['relative_locator'])
        raw = source.read_bytes()
        if sha(raw) != item["raw_sha256"]:
            raise QGError("SOURCE_MUTATED", 3)
        text, ranges = extract(raw)
        if item["extraction_profile"] != EXTRACTOR or sha(text.encode("utf-8")) != item["extracted_sha256"] or ranges != item["ranges"]:
            raise QGError("EXTRACTION_MISMATCH", 3)
        if item["selection"] == "reference" and item["authorship"] not in ("owner_declared_human", "human_edited"):
            raise QGError("AUTHORSHIP_UNCONFIRMED", 3)
        plans.append((item, text))
    # Validate the full batch before writing any derived text.
    members = {item['id'] + '.txt': text.encode('utf-8') for item, text in plans}
    members['manifest.json'] = canonical({'items': selected, 'extraction_profile': EXTRACTOR})
    publish_bundle(output, members)
    return {"prepared": len(plans), "source_mutation": False}
