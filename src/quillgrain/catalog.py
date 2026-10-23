"""Private, versioned corpus data. Explicit local IO; no network or source execution."""
from pathlib import Path, PureWindowsPath
from .contracts import validate, unique, verify_context
from .io import QGError, read_json, write_json, write_bytes, sha, digest, is_link, safe_destination

SCHEMA = 'quillgrain.corpus/v1'


def read_member(root, relative):
    root = Path(root).absolute()
    rel = Path(relative)
    if rel.is_absolute() or rel.drive or PureWindowsPath(relative).drive or '..' in rel.parts or '\\' in str(relative):
        raise QGError('CORPUS_PATH_ESCAPE', 3)
    for part in (*reversed(root.parents), root, *[root.joinpath(*rel.parts[:i]) for i in range(1, len(rel.parts) + 1)]):
        if is_link(part):
            raise QGError('CORPUS_LINK_DENIED', 3)
    candidate = root / rel
    if not candidate.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise QGError('CORPUS_PATH_ESCAPE', 3)
    return candidate


def load(root, *, verify_content=False):
    root = Path(root)
    manifest = validate(read_json(read_member(root, 'corpus.json')), 'corpus')
    for field in ('source_ids', 'fragment_ids', 'protected_work_ids'):
        if len(manifest[field]) != len(set(manifest[field])):
            raise QGError('DUPLICATE_CORPUS_ID', 3)
    if (root / '.github').exists():
        raise QGError('PRIVATE_CORPUS_CI_DENIED', 3)
    sources, fragments = {}, {}
    for identity in manifest['source_ids']:
        item = validate(read_json(read_member(root, f'sources/{identity}/source.json')), 'corpus-source')
        if item['id'] != identity:
            raise QGError('CORPUS_ID_MISMATCH', 3)
        unique(item['revisions'])
        if item['storage']['mode'] == 'metadata_only' and item['revisions']:
            raise QGError('CORPUS_STORAGE_DENIED', 3)
        if item['visibility'] == 'local_only' and item['revisions']:
            raise QGError('LOCAL_ONLY_STORAGE_DENIED', 3)
        for revision in item['revisions']:
            if revision['id'] != revision_id(revision):
                raise QGError('CORPUS_REVISION_MISMATCH', 3)
        sources[identity] = item
    for identity in manifest['fragment_ids']:
        fragment = validate(read_json(read_member(root, f'fragments/{identity}.json')), 'corpus-fragment')
        if fragment['id'] != identity or fragment['source_id'] not in sources:
            raise QGError('CORPUS_FRAGMENT_SOURCE', 3)
        source = sources[fragment['source_id']]
        if fragment['revision_id'] not in {r['id'] for r in source['revisions']}:
            raise QGError('CORPUS_FRAGMENT_REVISION', 3)
        if fragment['end'] <= fragment['start']:
            raise QGError('CORPUS_FRAGMENT_RANGE', 3)
        fragments[identity] = fragment
    result = dict(root=root, manifest=manifest, sources=sources, fragments=fragments)
    result['identity'] = dict(id=manifest['id'], version=manifest['version'], digest=digest({
        'manifest': manifest, 'sources': sorted(sources.values(), key=lambda x: x['id']),
        'fragments': sorted(fragments.values(), key=lambda x: x['id'])}))
    if verify_content:
        for source in sources.values():
            for revision in source['revisions']:
                for key in ('original_sha256', 'text_sha256'):
                    value = read_member(root, 'objects/' + revision[key]).read_bytes()
                    if sha(value) != revision[key]:
                        raise QGError('CORPUS_OBJECT_MUTATED', 3)
        for fragment in fragments.values():
            fragment_text(result, fragment)
    return result


def revision_id(revision):
    return digest({k: v for k, v in revision.items() if k != 'id'})


def fragment_text(catalog, fragment):
    source = catalog['sources'][fragment['source_id']]
    revision = next(r for r in source['revisions'] if r['id'] == fragment['revision_id'])
    raw = read_member(catalog['root'], 'objects/' + revision['text_sha256']).read_bytes()
    if sha(raw) != revision['text_sha256']:
        raise QGError('CORPUS_OBJECT_MUTATED', 3)
    text = raw.decode('utf-8')
    if fragment['end'] > len(text):
        raise QGError('CORPUS_FRAGMENT_RANGE', 3)
    value = text[fragment['start']:fragment['end']]
    if sha(value.encode('utf-8')) != fragment['sha256']:
        raise QGError('CORPUS_FRAGMENT_MUTATED', 3)
    return value


def init(root, *, identity='quillgrain.corpus', approval):
    root = safe_destination(root)
    if root.exists() and any(root.iterdir()):
        raise QGError('OUTPUT_ALREADY_EXISTS', 3)
    manifest = dict(schema_version=SCHEMA, id=identity, version='1.0.0', visibility='private',
                    source_ids=[], fragment_ids=[], protected_work_ids=[], approval=approval)
    validate(manifest, 'corpus')
    write_json(root / 'corpus.json', manifest)
    return manifest


def ingest(root, metadata, original, text, *, extraction_profile='verbatim-utf8-v1', upstream_sha256=None):
    """Caller supplies trusted metadata and explicit bytes; never dereference origin URLs."""
    catalog = load(root)
    source = dict(metadata)
    source['revisions'] = []
    validate(source, 'corpus-source')
    if source['storage']['mode'] == 'metadata_only' or source['visibility'] == 'local_only':
        raise QGError('CORPUS_STORAGE_DENIED', 3)
    if not source['storage']['approval']['basis'].strip() or not source['storage']['approval']['by'].strip():
        raise QGError('CORPUS_STORAGE_APPROVAL_REQUIRED', 3)
    if not text or not source['permissions']['local_analysis']:
        raise QGError('CORPUS_SOURCE_DENIED', 3)
    revision = dict(original_sha256=sha(original), text_sha256=sha(text.encode('utf-8')),
                    extraction_profile=extraction_profile)
    if upstream_sha256:
        revision['upstream_sha256'] = upstream_sha256
    revision['id'] = revision_id(revision)
    previous = catalog['sources'].get(source['id'])
    if previous:
        if {k: v for k, v in previous.items() if k != 'revisions'} != {k: v for k, v in source.items() if k != 'revisions'}:
            raise QGError('CORPUS_METADATA_CHANGE_REQUIRES_REVIEW', 3)
        source['revisions'] = previous['revisions'].copy()
    if revision not in source['revisions']:
        source['revisions'].append(revision)
    for blob in (original, text.encode('utf-8')):
        path = Path(root) / 'objects' / sha(blob)
        if path.exists():
            if read_member(root, 'objects/' + sha(blob)).read_bytes() != blob:
                raise QGError('CORPUS_OBJECT_MUTATED', 3)
        else:
            write_bytes(path, blob)
    write_json(Path(root) / 'sources' / source['id'] / 'source.json', source)
    manifest = catalog['manifest']
    manifest['source_ids'] = sorted(set(manifest['source_ids']) | {source['id']})
    if source['usage'] == 'evaluation':
        manifest['protected_work_ids'] = sorted(set(manifest['protected_work_ids']) | {source['work_id']})
    write_json(Path(root) / 'corpus.json', manifest)
    return revision


def add_fragment(root, fragment):
    validate(fragment, 'corpus-fragment')
    catalog = load(root)
    if fragment['id'] in catalog['fragments']:
        if catalog['fragments'][fragment['id']] != fragment:
            raise QGError('IMMUTABLE_FRAGMENT', 3)
        return
    source = catalog['sources'].get(fragment['source_id'])
    if not source or fragment['revision_id'] not in {r['id'] for r in source['revisions']}:
        raise QGError('CORPUS_FRAGMENT_REVISION', 3)
    fragment_text(catalog, fragment)
    write_json(Path(root) / 'fragments' / (fragment['id'] + '.json'), fragment)
    manifest = catalog['manifest']
    manifest['fragment_ids'] = sorted(manifest['fragment_ids'] + [fragment['id']])
    write_json(Path(root) / 'corpus.json', manifest)


def resolve(catalog, reference, *, model_host, public=False):
    source = catalog['sources'].get(reference['source_id'])
    fragment = catalog['fragments'].get(reference['fragment_id'])
    if not source or not fragment:
        raise QGError('CORPUS_REFERENCE_UNAVAILABLE', 3)
    if (source['work_id'] in catalog['manifest']['protected_work_ids'] or source['usage'] != 'reference'):
        raise QGError('EVALUATION_OR_UNSELECTED_SOURCE_DENIED', 3)
    permissions = {k: sorted(set(v) & set(reference['permissions'][k])) if isinstance(v, list)
                   else v and reference['permissions'][k] for k, v in source['permissions'].items()}
    protected = {s['id'] for s in catalog['sources'].values() if s['usage'] == 'evaluation'
                 or s['work_id'] in catalog['manifest']['protected_work_ids']}
    hashes = {r[k] for identity in protected for r in catalog['sources'][identity]['revisions']
              for k in ('original_sha256', 'text_sha256')}
    if any(r[k] in hashes for r in source['revisions'] for k in ('original_sha256', 'text_sha256')):
        raise QGError('WORK_SPLIT_LEAKAGE', 3)
    if source['revoked'] or not permissions['retrieval'] or model_host not in permissions['approved_model_hosts']:
        raise QGError('CORPUS_HOST_OR_RETRIEVAL_DENIED', 3)
    if public:
        raise QGError('PRIVATE_CORPUS_TO_PUBLIC_DENIED', 3)
    if (fragment['source_id'] != source['id'] or fragment['revision_id'] != reference['revision_id']
            or fragment['sha256'] != reference['sha256'] or source['work_id'] != reference['work_id']):
        raise QGError('CORPUS_REFERENCE_MISMATCH', 3)
    if reference['language'] != source['language'] or reference['register'] not in source['registers']:
        raise QGError('CORPUS_REFERENCE_SCOPE', 3)
    if fragment['status'] != 'REVIEWED' or reference['status'] != 'REVIEWED':
        raise QGError('CORPUS_FRAGMENT_UNREVIEWED', 3)
    if fragment['authorship'] in ('quoted', 'unknown'):
        raise QGError('CORPUS_FRAGMENT_AUTHORSHIP', 3)
    example = dict(id=reference['id'], text=fragment_text(catalog, fragment),
                   language=reference['language'], register=reference['register'], source_id=source['id'],
                   work_id=source['work_id'], channel=fragment['channel'], permissions=permissions,
                   visibility=max((source['visibility'], reference['visibility']), key={'public':0,'private':1,'local_only':2}.get), role=reference['role'],
                   tags=reference['tags'], priority=reference['priority'], authorship=fragment['authorship'], status='REVIEWED')
    lineage = dict(example_id=reference['id'], corpus_id=catalog['manifest']['id'], source_id=source['id'],
                   work_id=source['work_id'], revision_id=reference['revision_id'],
                   fragment_id=fragment['id'], sha256=fragment['sha256'])
    return example, lineage


def search(catalog, *, tags=(), language=None, register=None):
    """Metadata-only search; held-out works are never read or offered as examples."""
    return [dict(id=s['id'], work_id=s['work_id'], title=s['title'], usage=s['usage'], tags=s['tags'])
            for s in sorted(catalog['sources'].values(), key=lambda x: x['id'])
            if s['usage'] == 'reference' and not s['revoked']
            and s['work_id'] not in catalog['manifest']['protected_work_ids']
            and set(tags) <= set(s['tags']) and (not language or language == s['language'])
            and (not register or register in s['registers'])]


def explain(context):
    verify_context(context)
    return dict(build_id=context['build_id'], mode=context.get('example_mode', 'none' if 'EXAMPLES_DISABLED:RULES_ONLY' in context['warnings'] else 'auto'),
                rules=[dict(id=r['id'], origin=r['origin'], evidence_ids=r['evidence_ids']) for r in context['rules_applied']],
                materials=context.get('corpus_materials', []), omitted=context['examples_omitted'],
                rules_omitted=context['rules_omitted'], corpora=context.get('corpora', []), evidence_refs=context.get('evidence_refs', []),
                permission_state='Pinned local snapshot; remote permission changes are not queried.')


def impact(source_id, packs, contexts=()):
    from .compose import reference
    from .contracts import load_pack
    affected = []
    for path in packs:
        pack = load_pack(Path(path))
        refs = [r for r in pack.get('example_refs', []) if r['source_id'] == source_id]
        evidence = [r for r in pack.get('evidence_refs', []) if r['source_id'] == source_id]
        evidence_ids = {r['evidence_id'] for r in evidence}
        rules = [r['id'] for r in pack['rules'] if evidence_ids & set(r['evidence_ids'])]
        if refs or evidence:
            affected.append(dict(pack=reference(pack), examples=[r['id'] for r in refs], rules=rules))
    builds = []
    for context in contexts:
        verify_context(context)
        if any(m['source_id'] == source_id for m in context.get('corpus_materials', [])):
            builds.append(context['build_id'])
    return dict(source_id=source_id, affected=affected, registered_builds=builds,
                scope='Only explicitly supplied packs and contexts; existing copies cannot be recalled.')
