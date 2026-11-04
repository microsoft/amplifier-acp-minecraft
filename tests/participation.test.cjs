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
test('management briefs stay outside public candidates, messages and participants across reload',()=>{
 const f=fixture();try{
  const records=[
   {username:'Operator',message:'Legacy private management brief'},
   {username:'ControlAlias',message:'New private management brief',provenance:'operator_control'},
   {username:'OtherAlias',message:'Unknown private provenance',provenance:'future_private_source'},
   {username:'Whisperer',message:'Private whisper',whisper:true,provenance:'minecraft_whisper'}
  ].map(fields=>f.history.record({kind:'chat',source:'human',accepted:true,whisper:false,time:new Date().toISOString(),...fields}));
  for(const e of records)f.p.queue(e);
  assert.equal(f.p.proposal([]),null);
  const message=f.chat('What are you working on?');
  // Also cover a previously persisted queue containing private record IDs.
  f.history.data.participation_pending.push(...records.map(e=>e.id));f.history.save();
  const restored=new WorkshopState(f.history.file);
  const p=new Participation(restored,{username:'Builder',conversation_attention:{enabled:true}});
  const proposal=p.proposal(['Visitor']);
  assert.deepEqual(proposal.ids,[message.id]);
  assert.deepEqual(proposal.context.messages.map(m=>m.id),[message.id]);
  assert.deepEqual(proposal.context.participants.map(p=>p.id),['Builder','Visitor']);
  const inbox=[];p.apply(proposal,{signature:proposal.signature,action:'engage'},inbox);
  assert.deepEqual(inbox.map(m=>m.id),[message.id]);
  assert.equal(restored.data.events.filter(e=>records.some(r=>r.id===e.id)).length,4);
 }finally{f.close();}
});
test('explicit public game provenance permits a real player named Operator',()=>{
 const f=fixture();try{
  const e=f.history.record({kind:'chat',source:'human',username:'Operator',message:'Public hello',
   provenance:'minecraft_public_chat',whisper:false,time:new Date().toISOString()});
  f.p.queue(e);const p=f.p.proposal(['Operator']);
  assert.equal(p.context.trigger_id,e.id);assert.equal(p.context.messages[0].text,'Public hello');
 }finally{f.close();}
});
