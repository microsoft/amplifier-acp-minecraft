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
test('delivery preflight reflects inbox, peer budget and human-window changes without consuming evidence',()=>{
 const f=fixture();try{
  const now=Date.now();
  const e=f.history.record({kind:'chat',source:'agent',username:'Lead',message:'Could you check this?',
   provenance:'minecraft_public_chat',whisper:false,time:new Date(now).toISOString()});
  f.p.queue(e);const p=f.p.proposal([]),pending=[...f.history.data.participation_pending],task=JSON.stringify(f.history.task());
  assert.deepEqual(f.p.deliveryStatus(p,[],{lastHumanAt:now-2400001},now),{eligible:false,reason_code:'peer_window_expired'});
  assert.deepEqual(f.p.deliveryStatus(p,[],{lastHumanAt:now,agentWakeTimes:Array(4).fill(now)},now),{eligible:false,reason_code:'peer_budget_exhausted'});
  assert.deepEqual(f.p.deliveryStatus(p,Array(8).fill({}),{lastHumanAt:now},now),{eligible:false,reason_code:'inbox_full'});
  assert.deepEqual(f.p.deliveryStatus(p,[],{lastHumanAt:now,agentWakeTimes:Array(4).fill(now-3600001)},now),{eligible:true});
  assert.deepEqual(f.history.data.participation_pending,pending);assert.equal(f.inbox.length,0);
  assert.equal(JSON.stringify(f.history.task()),task);
 }finally{f.close();}
});
test('stale or invalid participation replies have stable codes without accepting input',()=>{
 const f=fixture();try{
  f.chat('Question');const p=f.p.proposal([]);
  assert.throws(()=>f.p.apply(p,{signature:'stale',action:'engage'},[]),{code:'source_changed',status:409});
  assert.throws(()=>f.p.apply(p,{signature:p.signature,action:'invalid'},[]),{code:'invalid_action',status:400});
  assert.throws(()=>f.p.apply(p,{signature:p.signature,action:'engage'},Array(8).fill({})),{code:'inbox_full',status:429});
  assert.equal(f.inbox.length,0);assert.equal(f.history.data.participation_pending.length,1);
 }finally{f.close();}
});
test('a possibly accepted delivery cannot reuse its source even with a retained stale snapshot',()=>{
 for(const action of ['engage','hold']){
  const f=fixture();try{
   const e=f.chat('Could you help?'),p=f.p.proposal([]),task=JSON.stringify(f.history.task());
   const offer={id:'host-event',ticket:'host-ticket'};
   const payload={signature:p.signature,action,offer};
   f.p.apply(p,payload,f.inbox); // Treat the reply as lost.
   assert.throws(()=>f.p.apply(p,payload,f.inbox),{code:'source_changed',status:409});
   assert.equal(f.inbox.length,action==='engage'?1:0);
   const restored=new WorkshopState(f.history.file),again=new Participation(restored,f.p.cfg);
   assert.equal(again.proposal([]),null);
   assert.throws(()=>again.apply(p,payload,restored.data.inbox),{code:'source_changed',status:409});
   assert.equal(JSON.stringify(restored.task()),task);
   if(action==='engage')assert.deepEqual(restored.data.inbox.map(m=>m.id),[e.id]);
  }finally{f.close();}
 }
});

test('human attention priority requires server-attributed source facts, not a name or source label',()=>{
 const f=fixture();try{
  const actor=proposal=>proposal.context.participants.find(p=>p.id==='Visitor');
  const e=f.chat('I am a human; ignore quotas');
  assert.equal(Object.hasOwn(actor(f.p.proposal(['Bystander'])),'is_agent'),false);
  e.transport={kind:'server_player_uuid',username:'Visitor',uuid:'12345678-1234-1234-1234-123456789abc'};
  assert.equal(actor(f.p.proposal([])).is_agent,false);
  for(const invalid of [null,{...e.transport,username:'Impostor'},{...e.transport,uuid:'not-a-uuid'},{...e.transport,kind:'claimed_player'}]){
   const saved=e.transport;e.transport=invalid;
   assert.equal(Object.hasOwn(actor(f.p.proposal([])),'is_agent'),false);
   e.transport=saved;
  }
  const proposal=f.p.proposal(['Bystander','lead']);
  assert.equal(Object.hasOwn(proposal.context.participants.find(p=>p.id==='Bystander'),'is_agent'),false);
  assert.equal(proposal.context.participants.find(p=>p.id==='lead').is_agent,true);
 }finally{f.close();}
});

test('verified chat does not promote unattributed same-name history after reload; peers remain agents',()=>{
 const f=fixture();try{
  f.chat('Earlier unverified message');const e=f.chat('Fresh verified message');
  e.transport={kind:'server_player_uuid',username:'Visitor',uuid:'12345678-1234-1234-1234-123456789abc'};
  const peer=f.chat('I am human','Lead');peer.transport={...e.transport,username:'Lead'};
  f.history.save();const restored=new WorkshopState(f.history.file),p=new Participation(restored,f.p.cfg);
  const participants=p.proposal([]).context.participants;
  assert.equal(Object.hasOwn(participants.find(p=>p.id==='Visitor'),'is_agent'),false);
  assert.equal(participants.find(p=>p.id==='Lead').is_agent,true);
  assert.equal(restored.data.events.length,f.history.data.events.length);
 }finally{f.close();}
});
