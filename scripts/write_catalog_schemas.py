"""Generate versioned corpus/reference contracts using only synthetic definitions."""
import copy
import runpy
from pathlib import Path
import json

D = runpy.run_path(str(Path(__file__).with_name('write_schemas.py')))
S, H, I, B = (D[k] for k in ('S', 'H', 'I', 'B'))
obj, arr, enum = (D[k] for k in ('obj', 'arr', 'enum'))
ID = {'type': 'string', 'pattern': '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,159}$'}
APPROVAL = obj(dict(by=S, basis=S))
IDENTITY = obj(dict(id=ID, version=S, digest=H))
REV = obj(dict(id=H, original_sha256=H, text_sha256=H, extraction_profile=S,
               upstream_sha256=H), ['id', 'original_sha256', 'text_sha256', 'extraction_profile'])
SOURCE = obj(dict(schema_version={'const': 'quillgrain.corpus-source/v1'}, id=ID,
                  work_id=ID, title=S, authorship=S, language=S, registers=arr(), tags=arr(),
                  usage=enum('reference', 'candidate', 'evaluation', 'excluded'),
                  visibility=D['VIS'], permissions=D['PERMS'],
                  storage=obj(dict(mode=enum('full', 'excerpt', 'metadata_only'), approval=APPROVAL)),
                  origin=obj(dict(kind=S, reference=S, credits=arr(), notes=arr())),
                  revisions=arr(REV), revoked=B))
FRAGMENT = obj(dict(schema_version={'const': 'quillgrain.corpus-fragment/v1'}, id=ID,
                    source_id=ID, revision_id=H, start=I, end=I, sha256=H,
                    channel=enum('narration', 'dialogue'), authorship=S,
                    status=enum('CANDIDATE', 'REVIEWED', 'RETIRED'), tags=arr()))
CORPUS = obj(dict(schema_version={'const': 'quillgrain.corpus/v1'}, id=ID, version=S,
                  visibility={'const': 'private'}, source_ids=arr(ID), fragment_ids=arr(ID),
                  protected_work_ids=arr(ID), approval=APPROVAL))
EXREF = obj(dict(id=ID, corpus_id=ID, source_id=ID, revision_id=H, fragment_id=ID,
                 sha256=H, work_id=ID, language=S, register=S, tags=arr(), priority=I,
                 permissions=D['PERMS'], visibility=D['VIS'],
                 role=enum('positive', 'negative'), status=enum('CANDIDATE', 'REVIEWED', 'RETIRED')))
EVREF = obj(dict(evidence_id=S, corpus_id=ID, source_id=ID, revision_id={'anyOf':[H,{'type':'null'}]}))
MATERIAL = obj(dict(example_id=ID, corpus_id=ID, source_id=ID, work_id=ID,
                    revision_id=H, fragment_id=ID, sha256=H))
PACK = copy.deepcopy(D['PACK'])
PACK['properties']['schema_version'] = {'const': 'quillgrain.voice-pack/v2'}
PACK['properties']['compatibility']['properties']['schema'] = {'const': 'v2'}
PACK['properties'].update(corpus_dependencies=arr(IDENTITY), example_refs=arr(EXREF), evidence_refs=arr(EVREF))
PACK['required'] += ['corpus_dependencies', 'example_refs', 'evidence_refs']
CONTEXT = copy.deepcopy(D['CONTEXT'])
CONTEXT['properties']['schema_version'] = {'const': 'quillgrain.compiled-context/v2'}
CONTEXT['properties'].update(corpora=arr(IDENTITY), corpus_materials=arr(MATERIAL),
                             example_mode=enum('auto', 'none'), evidence_refs=arr(EVREF))
CONTEXT['required'] += ['corpora', 'corpus_materials', 'example_mode', 'evidence_refs']

if __name__ == '__main__':
    for name, schema in {'corpus': CORPUS, 'corpus-source': SOURCE, 'corpus-fragment': FRAGMENT,
                         'voice-pack-v2': PACK, 'compiled-context-v2': CONTEXT}.items():
        path = D['DEST'] / (name + '.json')
        path.write_text(json.dumps({'$schema': 'https://json-schema.org/draft/2020-12/schema', **schema}, indent=2) + '\n', encoding='utf-8', newline='\n')
