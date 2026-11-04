const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs'),{Participation}=require('../participation.cjs');
function fixture(){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'participation-'));
 const history=new WorkshopState(path.join(home,'state.json'));
 history.data.task={id:'old',status:'budget_exhausted',deadline:1,turns:12,max_turns:12};
 history.data.inbox=[];
 const p=new Participation(history,{username:'Builder',bot_names:['Builder','Lead'],conversation_attention:{enabled:true}});
 return {p,history,inbox:history.data.inbox,chat(text,username='Visitor',whisper=false){
  const e=history.record({kind:'chat',source:'human',accepted:false,message:text,username,whisper,time:new Date().toISOString()});
  if(!whisper)p.queue(e);return e;
 },close(){fs.rmSync(home,{recursive:true,force:true});}};
}
test('unnamed room question is a decision candidate, then admission preserves evidence and old task',()=>{
 const f=fixture();try{
  const e=f.chat("hey, what are y'all working on?");
  const before=JSON.stringify(f.history.task()),r=f.p.proposal(['Builder','Lead','Visitor']);
  assert.equal(r.context.trigger_id,e.id);assert.equal(f.inbox.length,0);assert.equal(e.accepted,false);
  assert.equal(f.p.apply(r,{signature:r.signature,action:'engage'},f.inbox).queued,true);
  assert.equal(f.inbox[0].id,e.id);assert.equal(e.accepted,true);assert.equal(JSON.stringify(f.history.task()),before);
  assert.equal(f.p.proposal([]),null);
 }finally{f.close();}
});
test('holding consumes the candidate without a turn or private-context disclosure',()=>{
 const f=fixture();try{
  f.chat('Private unrelated detail','Visitor',true);const e=f.chat('Thanks!');
  const r=f.p.proposal([]);assert.equal(r.context.messages.length,1);
  assert.equal(f.p.apply(r,{signature:r.signature,action:'hold'},f.inbox).queued,false);
  assert.equal(e.accepted,false);assert.equal(f.inbox.length,0);assert.equal(f.history.data.turn,null);
  assert.equal(f.p.proposal([]),null);
 }finally{f.close();}
});
test('new replies invalidate a delayed decision; newest snapshot remains eligible',()=>{
 const f=fixture();try{
  f.chat('What is the plan?');const old=f.p.proposal([]);
  f.chat('Lead already answered that.');const fresh=f.p.proposal([]);
  assert.throws(()=>f.p.apply(fresh,{signature:old.signature,action:'engage'},f.inbox),/changed/);
  assert.equal(f.inbox.length,0);assert.ok(f.p.proposal([]));
 }finally{f.close();}
});
test('candidate bursts stay bounded and expired messages cannot authorize replay',()=>{
 const f=fixture();try{
  for(let i=0;i<30;i++)f.chat('Question '+i);
  const r=f.p.proposal([]);assert.equal(r.ids.length,8);assert.ok(r.context.messages.length<=24);
  f.p.apply(r,{signature:r.signature,action:'hold'},f.inbox);assert.equal(f.p.proposal([]),null);
  const e=f.chat('Old question');e.time='2000-01-01T00:00:00Z';assert.equal(f.p.proposal([]),null);
 }finally{f.close();}
});
