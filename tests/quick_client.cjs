/* Original synthetic client regression. Optional jsdom adds DOM interaction checks. */
const assert=require('node:assert/strict'), fs=require('node:fs'), crypto=require('node:crypto');
global.crypto=crypto.webcrypto;
const Q=require('../src/quillgrain/web_quick/app.js');
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {blind:b,key:k,answers:a}=fixture;
const copy=x=>JSON.parse(JSON.stringify(x));
(async()=>{
  Q.validateBlind(b);await Q.frozen(b);await Q.validateKey(b,k);Q.validateAnswers(b,a);
  const r=await Q.report(b,a,k);assert.equal(r.committed.duels,3);assert.equal(r.committed.unique_sources,3);
  assert.equal(r.answers_digest,fixture.report.answers_digest);
  assert.equal(r.pairs.reduce((n,p)=>n+p.first_wins+p.second_wins,0),3);
  assert(r.pairs.some(p=>p.n===0));assert.equal(r.comment_fields_filled,0);
  assert(!JSON.stringify(r).includes('черновик'));
  r.pairs.forEach(p=>{const expected=fixture.report.pairs.find(e=>e.first===p.first && e.second===p.second).dimensions.overall;
    for(const field of ['n','first_wins','second_wins','ties','ambiguous','intensity'])assert.deepEqual(p[field],expected[field]);});
  for(const change of [x=>x.rounds.push(x.rounds[0]), x=>x.draft.vote='tie',x=>x.bundle_digest='bad']){
    const bad=copy(a);change(bad);assert.throws(()=>Q.validateAnswers(b,bad));
  }
  const badKey=copy(k);badKey.cases[0].identities={};const {digest,...unsigned}=badKey;badKey.digest=await Q.hash(Q.canonical(unsigned));
  await assert.rejects(()=>Q.validateKey(b,badKey));
  if(!process.env.QG_JSDOM_DIR){console.log('Core passed; jsdom DOM checks not requested');return;}
  const {JSDOM,VirtualConsole}=require(process.env.QG_JSDOM_DIR);
  const html=fs.readFileSync(process.argv[3],'utf8'), errors=[];let now=1000;
  const storageKey='ink-duel-quick-v1:'+b.session_id+':'+b.digest;
  const pause=()=>new Promise(r=>setTimeout(r,30));
  async function open(saved){
    const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
    const dom=new JSDOM(html,{url:'https://synthetic.invalid/',runScripts:'dangerously',virtualConsole:vc,beforeParse(w){
      Object.defineProperty(w.crypto,'subtle',{value:crypto.webcrypto.subtle});w.TextEncoder=TextEncoder;
      w.performance.now=()=>now;w.scrollTo=()=>{};w.URL.createObjectURL=()=> 'blob:synthetic';w.URL.revokeObjectURL=()=>{};
      w.HTMLAnchorElement.prototype.click=function(){};
      if(saved)w.localStorage.setItem(storageKey,JSON.stringify(saved));
    }});
    await pause();return dom;
  }
  let dom=await open();let w=dom.window,d=w.document;
  const state=()=>JSON.parse(w.localStorage.getItem(storageKey));
  const inputs=()=>[...d.querySelectorAll('textarea')];
  assert.equal(d.querySelectorAll('#vote-buttons button').length,5);assert.equal(inputs().length,2);
  assert(inputs().every(x=>!x.required && !x.value));assert(d.querySelector('#key-label').hidden);
  inputs()[0].value='Левая заметка';inputs()[0].dispatchEvent(new w.Event('input',{bubbles:true}));
  inputs()[1].value='Правая заметка';inputs()[1].dispatchEvent(new w.Event('input',{bubbles:true}));
  const saved=state();assert.equal(saved.rounds.length,0);assert.equal(saved.draft.vote,null);
  dom.window.close();dom=await open(saved);w=dom.window;d=w.document;
  assert.equal(inputs()[0].value,'Левая заметка');assert.equal(inputs()[1].value,'Правая заметка');
  inputs()[0].dispatchEvent(new w.KeyboardEvent('keydown',{key:'1',bubbles:true}));assert.equal(state().rounds.length,0);
  d.querySelector('#vote-buttons button').click();d.querySelector('#vote-buttons button').click();
  assert.equal(state().rounds.length,1);assert.equal(Object.values(state().rounds[0].comments).filter(Boolean).length,2);
  now+=700;d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'2',bubbles:true}));
  d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'2',repeat:true,bubbles:true}));assert.equal(state().rounds.length,2);
  inputs()[0].value='Незавершённый комментарий';inputs()[0].dispatchEvent(new w.Event('input',{bubbles:true}));
  const imported=copy(state());Object.defineProperty(d.querySelector('#import'),'files',{configurable:true,value:[{text:async()=>JSON.stringify(imported)}]});
  d.querySelector('#import').dispatchEvent(new w.Event('change'));await pause();assert.deepEqual(state(),imported);
  const withoutDraft=copy(imported);withoutDraft.draft=null;Object.defineProperty(d.querySelector('#import'),'files',{configurable:true,value:[{text:async()=>JSON.stringify(withoutDraft)}]});
  d.querySelector('#import').dispatchEvent(new w.Event('change'));await pause();assert.deepEqual(state(),imported);
  const conflicting=copy(imported);Object.keys(conflicting.draft.comments).forEach(c=>conflicting.draft.comments[c]='Старый комментарий');
  Object.defineProperty(d.querySelector('#import'),'files',{configurable:true,value:[{text:async()=>JSON.stringify(conflicting)}]});
  d.querySelector('#import').dispatchEvent(new w.Event('change'));await pause();assert.deepEqual(state(),imported);
  const wrong=copy(imported);wrong.bundle_digest='wrong';Object.defineProperty(d.querySelector('#import'),'files',{configurable:true,value:[{text:async()=>JSON.stringify(wrong)}]});
  d.querySelector('#import').dispatchEvent(new w.Event('change'));await pause();assert.deepEqual(state(),imported);
  d.querySelector('#stop').click();const stopped=state();assert.equal(stopped.state,'STOPPED_BY_OWNER');assert(stopped.draft);
  assert(d.querySelector('#votes').hidden);assert(!d.querySelector('#key-label').hidden);
  Object.defineProperty(d.querySelector('#key'),'files',{value:[{text:async()=>JSON.stringify(k)}]});d.querySelector('#key').dispatchEvent(new w.Event('change'));await pause();
  assert(!d.querySelector('#report-export').hidden);assert.equal(state().rounds.length,2);
  assert.equal(errors.length,0,errors.join('\n'));dom.window.close();
  // Exact equality permits only the center vote.
  const identical=copy(b);identical.cases.forEach(c=>{c.cards[1].text=c.cards[0].text;c.identical=true;});
  const data=copy(identical);delete data.digest;identical.digest=await Q.hash(Q.canonical(data));
  const bad=Q.empty(identical),c=identical.cases[0],row=Q.draft(c);row.vote='left_strong';row.committed_at='fixture';bad.rounds.push(row);
  assert.throws(()=>Q.validateAnswers(identical,bad));row.vote='tie';Q.validateAnswers(identical,bad);
  console.log('Core, persistence, reload, import, double click, keyboard, stop, draft exclusion and key checks passed');
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
