'use strict';
const ARMS=['ORIGINAL','MODEL_BASELINE','COMMON','SELECTED'];
const AXES=['vividness','naturalness','clarity','conciseness','fidelity'];
const DIMENSIONS=[...AXES,'resemblance'];
const TITLES={vividness:'Живость',naturalness:'Естественность',clarity:'Понятность',conciseness:'Лаконичность',fidelity:'Точность смысла',resemblance:'Похожесть на мою подачу · необязательно'};
const ROLES={ORIGINAL:'Исходный текст',MODEL_BASELINE:'Без профиля',COMMON:'Common',SELECTED:'Авторский профиль',unknown:'Не знаю'};
function assert(ok,message='Некорректный файл'){if(!ok)throw new Error(message);}
function plain(x){return x!==null&&typeof x==='object'&&!Array.isArray(x);}
function keys(x,list){assert(plain(x)&&Object.keys(x).every(k=>list.includes(k)));}
function canonical(x){if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';if(plain(x))return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';assert(x===null||['string','boolean','number'].includes(typeof x));if(typeof x==='number')assert(Number.isFinite(x));return JSON.stringify(x);}
async function hash(x){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(x)+'\n')))).map(x=>x.toString(16).padStart(2,'0')).join('');}
async function frozen(x){const {digest,...rest}=x;assert(digest===await hash(rest),'Контрольная сумма не совпала');}
function checkBundle(b){
 keys(b,['schema_version','session_id','mode','language','rubric_version','cases','digest']);
 assert(b.schema_version==='duel.pair-blind/v2','Этот экран принимает только парные наборы v2. Старую игру открой по прежнему адресу.');
 assert(['private','synthetic'].includes(b.mode)&&b.language==='ru'&&b.rubric_version==='ru-pair-v2');
 assert(typeof b.session_id==='string'&&b.session_id.length>0&&typeof b.digest==='string');
 assert(Array.isArray(b.cases)&&b.cases.length===30);const ids=new Set();
 for(const c of b.cases){keys(c,['id','purpose','meaning','cards','identical']);assert(typeof c.id==='string'&&!ids.has(c.id));ids.add(c.id);assert(typeof c.purpose==='string'&&c.purpose.length<=4000);assert(Array.isArray(c.meaning)&&c.meaning.length>=1&&c.meaning.length<=12);
  for(const s of c.meaning){keys(s,['entity','relation','value','modality']);for(const k of ['entity','relation','value'])assert(typeof s[k]==='string'&&s[k].length>0&&s[k].length<=300);assert(['asserted','possible','proposal'].includes(s.modality));}
  assert(Array.isArray(c.cards)&&c.cards.length===2);assert(c.cards[0].label!==c.cards[1].label);
  for(const v of c.cards){keys(v,['id','label','text']);assert(typeof v.id==='string'&&!ids.has(v.id));ids.add(v.id);assert('ABCD'.includes(v.label)&&v.label.length===1&&typeof v.text==='string'&&v.text.length>0&&v.text.length<=6000);}
  assert(c.identical===(c.cards[0].text===c.cards[1].text));
 }return b;
}
function empty(b){return {schema_version:'duel.pair-answers/v2',session_id:b.session_id,bundle_digest:b.digest,rounds:[],draft:null};}
function draft(c){return {case_id:c.id,votes:{},guesses:Object.fromEntries(c.cards.map(v=>[v.id,'unknown'])),note:'',committed_at:null};}
function checkRecord(c,r,committed){
 keys(r,['case_id','votes','guesses','note','committed_at']);assert(r.case_id===c.id);keys(r.votes,DIMENSIONS);assert(Object.values(r.votes).every(x=>['left','tie','right','unknown'].includes(x)));
 assert(plain(r.guesses)&&Object.keys(r.guesses).length===2&&c.cards.every(v=>[...ARMS,'unknown'].includes(r.guesses[v.id])));
 assert(typeof r.note==='string'&&r.note.length<=4000);
 if(committed){assert(AXES.every(a=>a in r.votes),'Выбери ответ для каждого из пяти критериев');assert(typeof r.committed_at==='string'&&r.committed_at.length>0);if(c.identical)assert(Object.values(r.votes).every(v=>['tie','unknown'].includes(v)),'Одинаковые тексты нельзя различить по качеству');}
 else assert(r.committed_at===null);
}
function validateProgress(b,p){
 keys(p,['schema_version','session_id','bundle_digest','rounds','draft']);assert(p.schema_version==='duel.pair-answers/v2'&&p.session_id===b.session_id&&p.bundle_digest===b.digest,'Прогресс относится к другому набору');
 assert(Array.isArray(p.rounds)&&p.rounds.length<=30);p.rounds.forEach((r,i)=>checkRecord(b.cases[i],r,true));
 assert(p.draft===null||p.rounds.length<30);if(p.draft!==null)checkRecord(b.cases[p.rounds.length],p.draft,false);return p;
}
function commit(b,p,now=new Date().toISOString()){
 assert(p.rounds.length<30&&p.draft);const r=structuredClone(p.draft);r.committed_at=now;checkRecord(b.cases[p.rounds.length],r,true);p.rounds.push(r);p.draft=null;return p;
}
if(typeof module!=='undefined')module.exports={AXES,DIMENSIONS,canonical,hash,checkBundle,empty,draft,validateProgress,commit};
if(typeof document!=='undefined'){
 const app=document.getElementById('app'),notice=document.getElementById('notice');let bundle=null,progress=null,view=null,storageOn=true,storageFailed=false,mobile='both';
 function el(tag,attrs={},...children){const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k.startsWith('on'))n.addEventListener(k.slice(2),v);else if(k==='class')n.className=v;else if(k in n)n[k]=v;else n.setAttribute(k,v);}for(const c of children.flat(Infinity))if(c!==null&&c!==undefined)n.append(typeof c==='string'?document.createTextNode(c):c);return n;}
 function safe(fn){return async()=>{try{await fn();}catch(e){notice.textContent=e.message;notice.scrollIntoView({block:'nearest'});}};}
 function button(text,fn,cls=''){return el('button',{type:'button',class:cls,onclick:safe(fn)},text);}
 function storageKey(){return 'ink-duel-pair-v2:'+bundle.session_id;}
 function save(){if(!storageOn)return;try{localStorage.setItem(storageKey(),JSON.stringify(progress));storageFailed=false;}catch{storageFailed=true;notice.textContent='Браузер не сохранил ответы. Скачай прогресс кнопкой сверху.';}}
 function download(name,value){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=el('a',{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 function exportAnswers(){assert(progress,'Сначала загрузи набор');download('ink-duel-pair-answers.json',progress);}
 async function loadBundle(b){checkBundle(b);await frozen(b);bundle=b;progress=empty(b);view=null;notice.textContent='';try{const stored=localStorage.getItem(storageKey());if(stored)progress=validateProgress(b,JSON.parse(stored));}catch{notice.textContent='Сохранённый прогресс не подходит. Можно импортировать резервный файл.';}home();}
 function header(){document.getElementById('progress').textContent=bundle?`${progress.rounds.length} из 30 · два текста за раунд`:'Парное сравнение';}
 function home(){header();view=null;app.replaceChildren(el('section',{class:'intro'},el('span',{class:'eyebrow'},'Парное сравнение · v2'),el('h1',{},'Два текста. Какой лучше?'),el('p',{},'По каждому критерию выбери левый текст, правый или равенство. Если не можешь решить — так и отметь. Пять ответов и один переход дальше.'),el('p',{class:'meta'},'Всего 30 раундов, пять категорий. A/B/C/D остаются анонимными: в каждом раунде видна только одна пара. Догадки о стиле необязательны.'),el('p',{class:'meta'},bundle?.mode==='synthetic'?'Это вымышленный демонстрационный набор для проверки интерфейса. Здесь нет реальных ответов Gemma.':'Тексты подготовлены заранее. Генерации во время игры нет.'),el('label',{class:'storage'},el('input',{type:'checkbox',checked:storageOn,onchange:e=>{storageOn=e.target.checked;if(storageOn)save();else try{localStorage.removeItem(storageKey());}catch{}}}),'Сохранять ответы в этом браузере. Тексты и ключ в сохранение не входят.'),el('div',{class:'actions'},bundle?button(progress.rounds.length?'Продолжить':'Начать сравнение',render,'primary'):null,button('Загрузить набор',()=>document.getElementById('bundle-file').click()))));}
 function criterion(c,r,axis,locked){const f=el('fieldset',{class:'criterion'},el('legend',{},TITLES[axis])),choices=el('div',{class:'choices'});
  for(const[value,label]of [['left',`← ${c.cards[0].label}`],['tie','Равно'],['right',`${c.cards[1].label} →`],['unknown','Не могу оценить']]){
   const disabled=locked||(c.identical&&['left','right'].includes(value));const input=el('input',{type:'radio',name:axis,value,checked:r.votes[axis]===value,disabled,onchange:()=>{r.votes[axis]=value;save();}});
   choices.append(el('label',{class:value==='unknown'?'unknown':'',title:value==='left'?'Левый текст лучше':value==='right'?'Правый текст лучше':label},input,label));
  }f.append(choices);return f;
 }
 function textCard(v,side){return el('article',{class:`text-card ${side}${mobile!=='both'&&mobile!==side?' mobile-hidden':''}`},el('div',{class:'card-head'},el('span',{class:'letter'},v.label),side==='left'?'Левый текст':'Правый текст'),el('div',{class:'prose',tabIndex:0,'aria-label':`Текст ${v.label}`},v.text));}
 function render(){assert(bundle,'Загрузи набор');header();notice.textContent='';const n=progress.rounds.length;if(view===null&&n===30){complete();return;}
  const i=view??n,c=bundle.cases[i],locked=i<n;if(!locked&&!progress.draft){progress.draft=draft(c);save();}const r=locked?progress.rounds[i]:progress.draft;
  const nav=el('nav',{class:'rounds','aria-label':'Раунды'});for(let j=0;j<30;j++){const b=button(String(j+1),()=>{view=j;render();},j===i?'current':j<n?'done':'');b.disabled=j>n;nav.append(b);}
  const meaning=el('details',{class:'meaning'},el('summary',{},'Смысловые данные · для проверки точности'),el('ul',{},c.meaning.map(s=>el('li',{},`${s.entity} · ${s.relation} · ${s.value}${s.modality==='possible'?' (возможно)':s.modality==='proposal'?' (предложение)':''}`))));
  app.replaceChildren(el('span',{class:'eyebrow'},bundle.mode==='synthetic'?'Демо · вымышленные тексты':'Слепое сравнение'),el('h1',{},`Раунд ${i+1} из 30`),el('p',{class:'meta'},c.purpose),nav,meaning);
  const tabs=el('div',{class:'mobile-tabs'});for(const[value,label]of [['both','Оба текста'],['left',c.cards[0].label],['right',c.cards[1].label]])tabs.append(button(label,()=>{mobile=value;render();}));app.append(tabs);
  const criteria=el('section',{class:'criteria','aria-label':'Сравнить тексты'});
  if(c.identical)criteria.append(el('p',{class:'duplicate'},'Тексты совпадают дословно. Для них доступны равенство и «не могу оценить». Догадки сохранятся, но в точность узнавания не попадут.'));
  for(const axis of DIMENSIONS)criteria.append(criterion(c,r,axis,locked));
  const guesses=el('section',{class:'guesses'},el('p',{class:'meta'},'Предположить стиль · необязательно'));
  const row=el('div',{class:'guess-row'});for(const v of c.cards){const s=el('select',{'aria-label':`Предположить стиль ${v.label}`,disabled:locked,onchange:e=>{r.guesses[v.id]=e.target.value;save();}});for(const a of ['unknown',...ARMS])s.append(el('option',{value:a,selected:r.guesses[v.id]===a},ROLES[a]));row.append(el('label',{},`Текст ${v.label}`,s));}guesses.append(row);criteria.append(guesses);
  const submit=el('div',{class:'submit-area'},el('textarea',{'aria-label':'Заметка к паре',placeholder:'Заметка к паре — необязательно',maxLength:4000,value:r.note,disabled:locked,oninput:e=>{r.note=e.target.value;save();}}));
  if(locked)submit.append(el('p',{class:'saved'},'Раунд сохранён. Ответы доступны для чтения.'),button(n===30?'К завершению':'К текущему раунду',()=>{view=null;render();},'primary'));
  else submit.append(button('Сохранить и дальше',()=>{commit(bundle,progress);save();view=null;render();document.querySelector('h1')?.focus();},'primary'),el('p',{class:'meta'},'Пять критериев обязательны. Похожесть и догадки можно пропустить.'));
  criteria.append(submit);app.append(el('div',{class:'duel'},textCard(c.cards[0],'left'),criteria,textCard(c.cards[1],'right')));
 }
 function complete(){header();app.replaceChildren(el('section',{class:'intro'},el('span',{class:'eyebrow'},'30 из 30'),el('h1',{},'Сравнения сохранены.'),el('p',{},'Скачай ответы. Соответствия остаются закрытыми: раскрытие загружается отдельным файлом, если ты решишь посмотреть результаты.'),el('div',{class:'actions'},button('Скачать ответы',exportAnswers,'primary'),button('Перечитать раунды',()=>{view=0;render();}),button('Загрузить раскрытие',()=>document.getElementById('reveal-file').click()))));}
 async function reveal(value){assert(progress.rounds.length===30,'Сначала заверши 30 раундов');await frozen(value);assert(value.schema_version==='duel.pair-reveal/v2'&&value.session_id===bundle.session_id&&value.bundle_digest===bundle.digest&&value.answers_digest===await hash(progress),'Раскрытие относится к другим ответам');assert(Array.isArray(value.cases)&&value.cases.length===30);
  const report=value.report;app.replaceChildren(el('h1',{},'Твои парные сравнения'),el('p',{class:'meta'},'Победы, равенства и пропуски учитываются отдельно. Числовые оценки здесь не восстанавливаются.'));
  for(const axis of DIMENSIONS){const table=el('table',{},el('thead',{},el('tr',{},['Условие','Победы','Равно','Поражения','Не оценено','Совпадения'].map(t=>el('th',{},t))))),body=el('tbody');for(const arm of ARMS){const x=report.axes[arm][axis];body.append(el('tr',{},[ROLES[arm],x.wins,x.ties,x.losses,x.abstentions,x.ambiguous].map(t=>el('td',{},String(t)))));}table.append(body);app.append(el('h2',{},TITLES[axis]),el('div',{class:'table-wrap'},table));}
  app.append(el('p',{},`Догадки: ${report.guesses.correct} из ${report.guesses.attempted}; не угадано/пропущено: ${report.guesses.unknown}; исключено из-за совпадений: ${report.guesses.ambiguous_excluded}.`),el('p',{class:'meta'},report.limitations.join(' ')),button('Скачать отчёт без текстов',()=>download('ink-duel-pair-summary.json',report)));
  value.cases.forEach((k,i)=>{const c=bundle.cases[i];assert(k.id===c.id);const d=el('details',{class:'reveal-case'},el('summary',{},`Раунд ${i+1} · соответствия`));for(const v of c.cards){const id=k.identities[v.id];assert(id&&id.label===v.label);d.append(el('h2',{},`${v.label} — ${ROLES[id.arm]}`),el('div',{class:'prose'},v.text));}app.append(d);});
 }
 async function fileValue(input){assert(input.files.length===1&&input.files[0].size<2000000,'Выбери JSON меньше 2 МБ');return JSON.parse(await input.files[0].text());}
 document.getElementById('export').onclick=safe(exportAnswers);
 document.querySelector('.brand').onclick=e=>{e.preventDefault();home();};
 document.getElementById('bundle-file').onchange=safe(async()=>{if(progress?.rounds.length&&!confirm('Текущий прогресс сохранён? Загрузить другой набор?'))return;await loadBundle(await fileValue(document.getElementById('bundle-file')));});
 document.getElementById('progress-file').onchange=safe(async()=>{assert(bundle,'Сначала загрузи набор');const next=validateProgress(bundle,await fileValue(document.getElementById('progress-file')));if(progress.rounds.length&&!confirm('Заменить текущие ответы импортированными?'))return;progress=next;save();view=null;render();});
 document.getElementById('reveal-file').onchange=safe(async()=>reveal(await fileValue(document.getElementById('reveal-file'))));
 window.addEventListener('beforeunload',e=>{if(progress&&progress.rounds.length<30&&(!storageOn||storageFailed)){e.preventDefault();e.returnValue='';}});
 if(['http:','https:'].includes(location.protocol))fetch('session.json',{cache:'no-store'}).then(r=>{assert(r.ok,'Загрузи локальный набор через меню «Файлы»');return r.json();}).then(loadBundle).catch(e=>{home();notice.textContent=e.message;});else home();
}
