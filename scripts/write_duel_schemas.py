"""Portable structural contracts; duel.py adds pairing, state and digest invariants."""
from pathlib import Path
from quillgrain.io import write_json

ROOT=Path(__file__).resolve().parents[1]/'src/quillgrain/schemas'
S={'type':'string'}
H={'type':'string','pattern':'^[0-9a-f]{64}$'}
ARMS=['ORIGINAL','MODEL_BASELINE','COMMON','SELECTED']
GROUPS=['lanterra','frontier','news','denis']
AXES=['vividness','naturalness','clarity','conciseness','fidelity']
def obj(props,required=None,extra=False):
    return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':extra}
def arr(item,minimum=0,maximum=None):
    r={'type':'array','items':item,'minItems':minimum}
    if maximum is not None:r['maxItems']=maximum
    return r
def save(name,schema):write_json(ROOT/(name+'.json'),{'$schema':'https://json-schema.org/draft/2020-12/schema',**schema})
anchors=arr({'type':'string','minLength':1,'maxLength':3000},2,5)
card=obj({'id':S,'label':{'enum':list('ABCD')},'text':{'type':'string','minLength':1,'maxLength':6000}})
blind_case=obj({'id':S,'purpose':S,'anchors':anchors,'cards':arr(card,4,4)})
blind=obj({'schema_version':{'const':'duel.blind-session/v1'},'session_id':S,'mode':{'enum':['private','synthetic']},
    'language':{'const':'ru'},'rubric_version':S,'cases':arr(blind_case,20,20),'digest':H})
save('duel-blind-session',blind)
variant=obj({'text':S,'sha256':H,'sentences':{'type':'integer','minimum':1,'maximum':5},
    'words':{'type':'integer','minimum':1,'maximum':110},'status':{'enum':['ORIGINAL','LIVE','MOCK','FAILED','NOT_RUN']}},extra=True)
source_props={'schema_version':{'const':'duel.source-case/v1'},'id':S,'group':{'enum':GROUPS},'language':{'const':'ru'},
    'work_id':S,'source_text':S,'source_sha256':H,'anchors':anchors,'purpose':S,'provenance':{'type':'object'},
    'authorship':S,'rights':obj({'local_use_reviewed':{'type':'boolean'}},extra=True),'overlap_reviewed':{'type':'boolean'}}
save('duel-source-case',obj(source_props,extra=True))
case_props={**source_props,'schema_version':{'const':'duel.case/v1'},'status':{'enum':['READY','INCOMPLETE','FAILED']},
    'variants':obj({a:variant for a in ARMS}),'digest':H}
save('duel-case',obj(case_props,extra=True))
score={'type':'integer','minimum':1,'maximum':5}
scores=obj({a:({'anyOf':[score,{'type':'null'}]} if a=='fidelity' else score) for a in AXES})
quote=obj({'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':1},'text':S})
vote=obj({'scores':scores,'note':{'type':'string','maxLength':4000},'quotes':arr(quote,0,30)},required=['scores'],extra=False)
round_schema=obj({'case_id':S,'quality':{'type':'object','additionalProperties':vote,'minProperties':4,'maxProperties':4},
    'quality_committed_at':S,'round_committed_at':{'type':['string','null']},'preference':S,'recognition':S,
    'guesses':{'anyOf':[{'type':'null'},obj({c:{'enum':ARMS+['']} for c in 'ABCD'})]},
    'owner_style':{'type':'object','additionalProperties':{'anyOf':[score,{'type':'null'}]}}},
    required=['case_id','quality','quality_committed_at','round_committed_at','preference','recognition','guesses'])
session=obj({'schema_version':{'const':'duel.session/v1'},'session_id':S,'bundle_digest':H,'rounds':arr(round_schema,0,20),
    'draft':{'type':['object','null']},'block2_acknowledged':{'type':'boolean'}},
    required=['schema_version','session_id','bundle_digest','rounds'])
save('duel-session',session)
save('duel-rating',{'$defs':{},**round_schema})
key_case=obj({'id':S,'case_id':S,'group':{'enum':GROUPS},'work_id':S,'provenance':{'type':['object','string']},
    'dimensions':{'type':'object'},'technical':{'type':'object'},
    'authorship':S,'editorial_audit':{'type':'object'},'identities':{'type':'object','minProperties':4,'maxProperties':4,
    'additionalProperties':obj({'arm':{'enum':ARMS},'label':{'enum':list('ABCD')},'sha256':H})}},
    required=['id','case_id','group','work_id','provenance','authorship','editorial_audit','identities'])
save('duel-key',obj({'schema_version':{'const':'duel.key/v1'},'session_id':S,'bundle_digest':H,
    'order_seed':{'type':'integer'},'mapping_seed':{'type':'integer'},'source_pack_digest':H,'cases':arr(key_case,20,20),'digest':H}))
save('duel-reveal',obj({'schema_version':{'const':'duel.reveal/v1'},'session_id':S,'bundle_digest':H,
    'answers_digest':H,'cases':arr(key_case,20,20),'report':{'type':'object'},'digest':H}))
print('DUEL_SCHEMAS_WRITTEN',7)
