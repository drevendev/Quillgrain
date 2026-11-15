/* Offline source-once client. No key or model identities are loaded while voting. */
'use strict';
const QuickDuel = (() => {
  const votes = ['left_strong','left_slight','tie','right_slight','right_strong'];
  const labels = ['← Сильно лучше','← Чуть лучше','Равно','Чуть лучше →','Сильно лучше →'];
  const require = (ok, code='Некорректный файл') => { if (!ok) throw Error(code); };
  const keyOrder = (a,b) => {const left=Array.from(a,c=>c.codePointAt(0)),right=Array.from(b,c=>c.codePointAt(0));for(let i=0;i<Math.min(left.length,right.length);i++)if(left[i]!==right[i])return left[i]-right[i];return left.length-right.length;};
  function encode(value){
    if(Array.isArray(value))return '['+value.map(encode).join(',')+']';
    if(value && typeof value==='object')return '{'+Object.keys(value).sort(keyOrder).map(k=>JSON.stringify(k)+':'+encode(value[k])).join(',')+'}';
    require(value===null||['string','boolean','number'].includes(typeof value));
    if(typeof value==='number')require(Number.isFinite(value));return JSON.stringify(value);
  }
  const canonical = value => encode(value)+'\n';
  const hash = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const frozen = async value => { const {digest,...data}=value; require(digest===await hash(canonical(data)),'Не совпала контрольная сумма'); };
  const exactKeys = (obj,keys) => obj && typeof obj==='object' && !Array.isArray(obj) && Object.keys(obj).sort().join('|')===keys.slice().sort().join('|');
  function validateBlind(b) {
    require(['duel.quick-blind/v1','duel.quick-blind/v2'].includes(b.schema_version) && typeof b.session_id==='string' && b.cases.length>0 && b.cases.length<=1000);
    if(b.schema_version==='duel.quick-blind/v2')require(exactKeys(b.study,['task_kinds','original_in_design']) && typeof b.study.original_in_design==='boolean' && b.study.task_kinds.every(t=>['rewrite','continuation','new_scene'].includes(t)));
    const ids=[];
    b.cases.forEach(c=>{require(c.cards.length===2 && c.identical===(c.cards[0].text===c.cards[1].text));if(b.study)require(b.study.task_kinds.includes(c.task_kind));ids.push(c.id,...c.cards.map(v=>v.id));});
    require(ids.length===new Set(ids).size); return b;
  }
  const empty = b => ({schema_version:'duel.quick-answers/v1',session_id:b.session_id,bundle_digest:b.digest,state:'ACTIVE',stopped_at:null,rounds:[],draft:null});
  const draft = c => ({case_id:c.id,vote:null,comments:Object.fromEntries(c.cards.map(v=>[v.id,''])),committed_at:null});
  function validateAnswers(b,a) {
    validateBlind(b);
    require(exactKeys(a,['schema_version','session_id','bundle_digest','state','stopped_at','rounds','draft']));
    require(a.schema_version==='duel.quick-answers/v1' && a.session_id===b.session_id && a.bundle_digest===b.digest,'Ответы относятся к другой игре');
    require(Array.isArray(a.rounds) && a.rounds.length<=b.cases.length);
    require(['ACTIVE','STOPPED_BY_OWNER','COMPLETE'].includes(a.state));
    require((a.state==='COMPLETE')===(a.rounds.length===b.cases.length));
    require((a.stopped_at!==null)===(a.state==='STOPPED_BY_OWNER'));
    const row=(c,r,committed)=>{
      require(exactKeys(r,['case_id','vote','comments','committed_at']) && r.case_id===c.id);
      require(exactKeys(r.comments,c.cards.map(v=>v.id)) && Object.values(r.comments).every(s=>typeof s==='string' && Array.from(s).length<=4000));
      require(committed ? votes.includes(r.vote) && typeof r.committed_at==='string' && r.committed_at.length>0 : r.vote===null && r.committed_at===null);
      require(!committed || !c.identical || r.vote==='tie','Совпадающим текстам нельзя присудить победу');
    };
    a.rounds.forEach((r,i)=>row(b.cases[i],r,true));
    if(a.draft!==null){require(a.rounds.length<b.cases.length);row(b.cases[a.rounds.length],a.draft,false);}
    return a;
  }
  async function validateKey(b,k) {
    await frozen(k); await frozen(k.plan);
    const version=b.schema_version.endsWith('/v2')?'v2':'v1';
    require(k.schema_version==='duel.quick-key/'+version && k.plan.schema_version==='duel.quick-plan/'+version);
    if(version==='v2')require(validStudy(k.plan,b.study));
    require(k.session_id===b.session_id && k.bundle_digest===b.digest,'Ключ относится к другой игре');
    require(k.cases.length===b.cases.length && k.plan.rows.length===b.cases.length);
    const sourceIds=new Set(), hashes=new Set(), conditions=new Set(k.plan.conditions.map(c=>c.id));
    require(conditions.size===k.plan.conditions.length && conditions.size>=2 && k.plan.budget>=k.cases.length);
    for(let i=0;i<b.cases.length;i++){
      const c=b.cases[i],r=k.cases[i],p=k.plan.rows[i];
      require(c.id===r.id && exactKeys(r.identities,c.cards.map(v=>v.id)));
      require(Object.keys(p).every(f=>canonical(p[f])===canonical(r[f])));
      require(!sourceIds.has(r.source_id) && !hashes.has(r.normalized_sha256));sourceIds.add(r.source_id);hashes.add(r.normalized_sha256);
      require(p.pair.length===2 && p.pair[0]!==p.pair[1] && p.pair.every(a=>conditions.has(a)));
      for(let s=0;s<2;s++)require(r.identities[c.cards[s].id].arm===p.pair[s] && r.identities[c.cards[s].id].sha256===await hash(c.cards[s].text));
      if(version==='v2'){
        const source=k.plan.manifest.sources.find(s=>s.id===r.source_id);
        require(source && source.task_kind===r.task_kind && c.task_kind===r.task_kind && c.purpose===r.purpose);
        require(r.input_sha256===await hash(canonical({task_kind:source.task_kind,source_text:source.source_text,fact_pack:source.fact_pack})));
        require(exactKeys(r.origins,c.cards.map(v=>v.id)));
        for(let s=0;s<2;s++){
          const condition=k.plan.conditions.find(x=>x.id===p.pair[s]), origin=r.origins[c.cards[s].id];
          require(origin.kind===(condition.kind==='original'?'unchanged_source':'model_output'));
          if(condition.kind==='original')require(source.task_kind==='rewrite' && c.cards[s].text===source.source_text);
        }
      }
    }
  }
  function validStudy(plan,study){
    const originals=new Set(plan.conditions.filter(c=>c.kind==='original').map(c=>c.id));
    return canonical(study.task_kinds)===canonical([...new Set(plan.rows.map(r=>r.task_kind))].sort()) && study.original_in_design===plan.rows.some(r=>r.pair.some(c=>originals.has(c))) && canonical(plan.conditions)===canonical(plan.manifest.conditions);
  }
  async function report(b,a,k) {
    validateAnswers(b,a);require(a.state!=='ACTIVE','Сначала остановите оценивание');
    await frozen(b);await validateKey(b,k);
    const arms=k.plan.conditions.map(c=>c.id).sort(), pairs=[];
    for(let i=0;i<arms.length;i++)for(let j=i+1;j<arms.length;j++)pairs.push({first:arms[i],second:arms[j],n:0,first_wins:0,second_wins:0,ties:0,ambiguous:0,intensity:Object.fromEntries(votes.map(v=>[v,0]))});
    const coverage=n=>{
      const rows=k.cases.slice(0,n), conditions=Object.fromEntries(arms.map(a=>[a,{total:0,left:0,right:0,categories:{}}]));
      rows.forEach(r=>r.pair.forEach((a,s)=>{const x=conditions[a];x.total++;x[s?'right':'left']++;x.categories[r.group]=(x.categories[r.group]||0)+1;}));
      return {duels:n,unique_sources:new Set(rows.map(r=>r.source_id)).size,unique_works:new Set(rows.map(r=>r.work_id)).size,conditions};
    };
    a.rounds.forEach((r,i)=>{
      const c=b.cases[i], row=k.cases[i], [left,right]=row.pair, p=pairs.find(p=>p.first===[left,right].sort()[0] && p.second===[left,right].sort()[1]);
      p.n++;let vote=r.vote;if(left!==p.first && vote!=='tie')vote=vote.replace('left','TEMP').replace('right','left').replace('TEMP','right');p.intensity[vote]++;
      if(c.identical)p.ambiguous++;else if(r.vote==='tie')p.ties++;else p[(r.vote.startsWith('left')?left:right)===p.first?'first_wins':'second_wins']++;
    });
    const origins={},slices=new Map();let duplicateComments=0,commentRounds=0;
    a.rounds.forEach((r,i)=>{
      const row=k.cases[i],task=row.task_kind||'UNKNOWN',group=row.group||'UNKNOWN',id=canonical([task,group]);
      if(!slices.has(id))slices.set(id,{task_kind:task,group,n:0,ordinal_votes:Object.fromEntries(votes.map(v=>[v,0]))});
      const bucket=slices.get(id);bucket.n++;bucket.ordinal_votes[r.vote]++;
      const notes=Object.values(r.comments).map(s=>s.trim()).filter(Boolean);if(notes.length)commentRounds++;if(notes.length===2 && notes[0]===notes[1])duplicateComments++;
      b.cases[i].cards.forEach(c=>{const origin=row.origins?.[c.id]?.kind||'UNKNOWN';origins[origin]=(origins[origin]||0)+1;});
    });
    return {schema_version:'duel.quick-browser-report/v2',session_id:b.session_id,bundle_digest:b.digest,answers_digest:await hash(canonical(a)),
      status:a.state==='COMPLETE'?'COMPLETE':'PARTIAL',stop_reason:a.state,planned:coverage(b.cases.length),committed:coverage(a.rounds.length),
      draft_present:a.draft!==null,draft_excluded:true,conditions:k.plan.conditions,pairs,
      comment_fields_filled:a.rounds.reduce((n,r)=>n+Object.values(r.comments).filter(s=>s.trim()).length,0),
      comment_rounds:commentRounds,duplicate_comment_pairs:duplicateComments,absolute_satisfaction:'UNKNOWN',
      provenance:{task_kinds:[...new Set(k.cases.map(r=>r.task_kind||'UNKNOWN'))].sort(),original_in_design:b.study?.original_in_design??null,committed_text_origins:origins,source_role:b.study?(b.study.original_in_design?'INPUT_AND_ORIGINAL':'INPUT_ONLY'):'UNKNOWN'},
      slices:[...slices.values()],feedback_semantics:{literal_comments:'PRIVATE_ANSWER_FILE',phrase_presence:'NOT_REVIEWED',editorial_interpretation:'NOT_REVIEWED',causal_explanation:'UNKNOWN',automatic_rule_promotion:false},
      limitations:['Наблюдения предварительные: разные соперники и малая выборка не устанавливают рейтинг.','n=0 означает отсутствие наблюдений. Сильный голос не считается за два.','Модель, профиль, примеры, brief, reasoning и сессия могут смешивать эффекты. Без комментариев причины неизвестны.','Относительная победа не означает, что текст понравился или готов к публикации. Одинаковая заметка на двух карточках не является двумя независимыми дефектами.']};
  }
  return {votes,labels,canonical,hash,frozen,validateBlind,validateAnswers,validateKey,empty,draft,report};
})();
if (typeof module!=='undefined') module.exports=QuickDuel;
if (typeof document!=='undefined') (async()=>{
  const $=id=>document.getElementById(id), Q=QuickDuel;
  const status=text=>{$('status').textContent=text;};
  let blind, answers, storageKey, stats=null, busy=false, lastCommit=-Infinity, viewIndex=null;
  const download=(name,data)=>{const url=URL.createObjectURL(new Blob([Q.canonical(data)],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const save=next=>{Q.validateAnswers(blind,next);localStorage.setItem(storageKey,Q.canonical(next));answers=next;};
  const clone=x=>JSON.parse(JSON.stringify(x));
  function render(){
    const n=answers.rounds.length,active=answers.state==='ACTIVE',reading=viewIndex!==null;
    const history=$('history');history.replaceChildren();
    const latest=document.createElement('option');latest.value='';latest.textContent='Текущая пара или итоги';history.append(latest);
    answers.rounds.forEach((r,i)=>{const option=document.createElement('option');option.value=String(i);option.textContent='Раунд '+(i+1);history.append(option);});history.value=reading?String(viewIndex):'';
    $('progress').textContent=`${n} / ${blind.cases.length}`;
    $('cards').replaceChildren();$('vote-buttons').replaceChildren();$('votes').hidden=!active||reading;$('purpose').hidden=!active&&!reading;
    $('stop').disabled=!active;$('key-label').hidden=active;$('identical').hidden=true;$('results').hidden=active||reading;
    const taskNames={rewrite:'Переработка заданного текста',continuation:'Продолжение',new_scene:'Новая сцена по факт-пакету'};
    $('study').textContent=blind.study?blind.study.task_kinds.map(t=>taskNames[t]).join('; ')+'. '+(blind.study.original_in_design?'Неизменённые оригиналы также участвуют в исследовании.':'Источник используется только на входе. ORIGINAL не участвует.'):'Тип задания и участие оригинала в старом формате не указаны.';
    if(!active&&!reading){
      $('results').replaceChildren();const p=document.createElement('p');p.textContent=`${answers.state==='COMPLETE'?'Готово':'Остановлено владельцем'}. Оценено ${n} из ${blind.cases.length}. Черновик сохранён и не включён в итоги.`;$('results').append(p);
      const hint=document.createElement('p');hint.textContent='Сохраните ответы в меню. Для сравнения условий откройте ключ этой игры через меню — только после остановки.';$('results').append(hint);
      return;
    }
    const c=blind.cases[reading?viewIndex:n];const current=reading?answers.rounds[viewIndex]:answers.draft||Q.draft(c);
    $('purpose').textContent=c.purpose;$('identical').hidden=!c.identical;
    c.cards.forEach((card,i)=>{
      const article=document.createElement('article'),title=document.createElement('h2'),text=document.createElement('div'),label=document.createElement('label'),input=document.createElement('textarea');
      title.textContent=i?'Текст справа':'Текст слева';text.className='text';text.textContent=card.text;
      label.textContent='Комментарий к этому тексту · необязательно';input.maxLength=4000;input.value=current.comments[card.id];input.dataset.cardId=card.id;
      input.readOnly=reading;
      if(!reading)input.addEventListener('input',()=>{try{const next=clone(answers);next.draft=next.draft||Q.draft(c);next.draft.comments[card.id]=input.value;save(next);status('');}catch(e){status('Не удалось сохранить: '+e.message+' Сохраните ответы через меню.');}});
      label.append(input);article.append(title,text,label);$('cards').append(article);
    });
    Q.votes.forEach((vote,i)=>{const button=document.createElement('button');button.textContent=Q.labels[i];button.dataset.vote=vote;button.disabled=reading||c.identical&&vote!=='tie';button.addEventListener('click',e=>{if(e.detail>1)return;commit(vote);});$('vote-buttons').append(button);});
    if(reading)status('Раунд '+(viewIndex+1)+'. Сохранённая оценка: '+Q.labels[Q.votes.indexOf(current.vote)]);
  }
  function commit(vote){
    if(busy || viewIndex!==null || answers.state!=='ACTIVE' || performance.now()-lastCommit<650)return;
    busy=true;
    try{
      const next=clone(answers),c=blind.cases[next.rounds.length];if(c.identical && vote!=='tie')return;
      const r=next.draft||Q.draft(c);r.vote=vote;r.committed_at=new Date().toISOString();next.rounds.push(r);next.draft=null;
      if(next.rounds.length===blind.cases.length)next.state='COMPLETE';
      save(next);lastCommit=performance.now();render();status('Оценка сохранена');window.scrollTo(0,0);
      const heading=$('cards').querySelector('h2');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}
    }catch(e){status('Оценка не сохранена: '+e.message);}finally{busy=false;}
  }
  try{
    const embedded=$('session').textContent.trim();blind=embedded && embedded!=='null'?JSON.parse(embedded):await (await fetch('/session.json',{cache:'no-store'})).json();
    Q.validateBlind(blind);await Q.frozen(blind);storageKey='ink-duel-quick-v1:'+blind.session_id+':'+blind.digest;
    answers=Q.empty(blind);
    try{const saved=localStorage.getItem(storageKey);if(saved)answers=Q.validateAnswers(blind,JSON.parse(saved));}catch(e){status('Сохранённые ответы не загружены: '+e.message+'. Файл можно импортировать через меню.');}
    render();
    $('history').onchange=e=>{viewIndex=e.target.value===''?null:Number(e.target.value);render();};
    $('export').onclick=()=>download('ink-duel-quick-answers.json',answers);
    $('import').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;const next=Q.validateAnswers(blind,JSON.parse(await file.text()));requireImport(next);save(next);stats=null;$('report-export').hidden=true;render();status('Ответы загружены');}catch(err){status(err.message);}finally{e.target.value='';}};
    function requireImport(next){
      if(next.rounds.length<answers.rounds.length)throw Error('В файле меньше оценок. Сначала сохраните текущие ответы; импорт в эту игру не выполнен.');
      for(let i=0;i<answers.rounds.length;i++)if(Q.canonical(next.rounds[i])!==Q.canonical(answers.rounds[i]))throw Error('Файл изменяет уже сохранённую оценку');
      if(answers.state!=='ACTIVE' && next.state!==answers.state)throw Error('Остановленная игра доступна только для просмотра');
      if(answers.draft && Object.values(answers.draft.comments).some(s=>s.trim())){
        const index=answers.rounds.length;
        if(next.rounds.length===index && !next.draft)next.draft=clone(answers.draft);
        const target=next.rounds[index]||next.draft;
        for(const [card,text] of Object.entries(answers.draft.comments)){
          if(!text.trim())continue;
          if(target.comments[card]!==text){
            if(next.rounds.length===index && !target.comments[card].trim())target.comments[card]=text;
            else throw Error('Файл заменяет незавершённый комментарий. Сохраните его через меню перед заменой.');
          }
        }
      }
    }
    $('stop').onclick=()=>{try{const next=clone(answers);next.state='STOPPED_BY_OWNER';next.stopped_at=new Date().toISOString();save(next);viewIndex=null;render();$('menu').open=false;status('Оценивание остановлено. Ответы и черновик сохранены.');download('ink-duel-quick-answers.json',answers);}catch(e){status('Не удалось сохранить остановку: '+e.message);}};
    $('key').onchange=async e=>{try{
      if(answers.state==='ACTIVE')throw Error('Сначала остановите оценивание');const file=e.target.files[0];if(!file)return;const key=JSON.parse(await file.text());stats=await Q.report(blind,answers,key);
      $('results').replaceChildren();const p=document.createElement('p');p.textContent=`${stats.status}: ${stats.committed.duels} из ${stats.planned.duels}; исходников ${stats.committed.unique_sources}, произведений ${stats.committed.unique_works}. Черновик исключён.`;$('results').append(p);
      const table=document.createElement('table');const header=document.createElement('tr');['Пара условий','n','Победы первого','Равно','Победы второго','Совпадения'].forEach(t=>{const th=document.createElement('th');th.textContent=t;header.append(th);});table.append(header);
      stats.pairs.forEach(p=>{const tr=document.createElement('tr');[`${p.first} / ${p.second}`,p.n,p.n?p.first_wins:'Нет данных',p.n?p.ties:'Нет данных',p.n?p.second_wins:'Нет данных',p.ambiguous].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});table.append(tr);});$('results').append(table);
      const details=document.createElement('details'),title=document.createElement('summary'),versions=document.createElement('pre');title.textContent='Условия и версии';versions.textContent=JSON.stringify(stats.conditions,null,2);details.append(title,versions);$('results').append(details);
      stats.limitations.forEach(t=>{const p=document.createElement('p');p.textContent=t;$('results').append(p);});$('report-export').hidden=false;status('Ключ проверен. Сводка готова; тексты и комментарии в неё не включены.');
    }catch(err){status(err.message);}finally{e.target.value='';}};
    $('report-export').onclick=()=>{if(stats)download('ink-duel-quick-summary.json',stats);};
    document.addEventListener('keydown',e=>{if(e.repeat || e.ctrlKey || e.metaKey || e.altKey || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.target.isContentEditable || $('menu').open)return;if(/^[1-5]$/.test(e.key)){e.preventDefault();commit(Q.votes[Number(e.key)-1]);}});
  }catch(e){status('Не удалось открыть игру: '+e.message);$('votes').hidden=true;}
})();
