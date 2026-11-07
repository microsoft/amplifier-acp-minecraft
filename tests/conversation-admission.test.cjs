const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const {ConversationAdmission}=require('../conversation-admission.cjs');
function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'reply-admission-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const history=new WorkshopState(path.join(dir,'history.json'));history.data.inbox=[];
 return {history,admit:new ConversationAdmission(history,{human_reply_turns_per_hour:2}),add(source='human',extra={}){
 const e=history.record({kind:'chat',source,username:'Visitor',message:'How is the harbor?',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString(),...extra});
 history.data.inbox.push({id:e.id,source,username:'Visitor',message:e.message,...(extra.whisper?{whisper:true}:{})});history.save();return e.id;}};}
test('reply reservation preserves active, expired and stopped task authority and work recovery evidence',t=>{
 for(const status of ['running','waiting','budget_exhausted','stopped','needs_review','review']){
 const f=fixture(t),h=f.history;h.data.task={id:'old',status,deadline:Date.now()+600000,turns:30,max_turns:45,progress:[]};h.data.last_turn={task_id:'old',actions:[{id:'old-effect',status:'uncertain'}]};
 const before=JSON.stringify([h.data.task,h.data.last_turn]);const id=f.add();f.admit.start([id],h.data.inbox);
 assert.equal(h.data.turn.may_mutate,false);assert.equal(h.data.turn.task_id,null);assert.equal(h.data.inbox.length,0);
 h.checkpoint({position:'not a task update'});h.finish(true);
 assert.equal(JSON.stringify([h.data.task,h.data.last_turn]),before);
 assert.equal(f.admit.status([{id,source:'human'}]).eligible_ids.length,0);
 }
});
test('lost reservation reply and restart cannot replay or lose original construction effects',t=>{
 const f=fixture(t),h=f.history;h.data.task={id:'old',status:'running',deadline:Date.now()+600000,turns:1,max_turns:5,progress:[]};
 h.data.last_turn={task_id:'old',actions:[{id:'effect',status:'uncertain'}]};const before=JSON.stringify([h.data.task,h.data.last_turn]);
 const id=f.add();f.admit.start([id],h.data.inbox);
 const loaded=new WorkshopState(h.file),admit=new ConversationAdmission(loaded,{});
 assert.equal(JSON.stringify([loaded.data.task,loaded.data.last_turn]),before);assert.equal(loaded.data.last_conversation_turn.interrupted,true);
 assert.throws(()=>admit.start([id],[{id,source:'human'}]),/No fresh/);
});
test('reserve is bounded and excludes peer, management, stale and duplicate inputs',t=>{
 const f=fixture(t),h=f.history;
 for(const id of [f.add('agent'),f.add('human',{provenance:'operator_control'}),f.add('human',{time:new Date(Date.now()-600001).toISOString()})])assert.throws(()=>f.admit.start([id],h.data.inbox),/No fresh/);
 for(let i=0;i<2;i++){f.admit.start([f.add()],h.data.inbox);h.finish();}
 const id=f.add();assert.equal(f.admit.status(h.data.inbox).remaining,0);assert.throws(()=>f.admit.start([id],h.data.inbox),/No fresh/);
});
test('body reservation refuses a partial attention ticket even if controller selects only its human',t=>{
 const f=fixture(t),h=f.history,offer={id:'mixed',ticket:'opaque'};
 const human=f.add(),peer=f.add('agent');for(const m of h.data.inbox)m.attention_offer=offer;
 assert.throws(()=>f.admit.start([human],h.data.inbox),/remain whole/);
 assert.equal(h.data.turn,null);assert.equal(h.data.inbox.length,2);
 assert.throws(()=>f.admit.start([human,peer],h.data.inbox),/No fresh/);
});
test('human-priority policy removes only reply quota, retaining source deduplication and peer exclusion',t=>{
 const f=fixture(t),h=f.history;f.admit.cfg.human_engagement={enabled:true};f.admit.cfg.human_reply_turns_per_hour=0;
 for(let i=0;i<70;i++){const id=f.add();assert.equal(f.admit.status(h.data.inbox).remaining,null);assert.equal(f.admit.status(h.data.inbox).unmetered,true);f.admit.start([id],h.data.inbox);h.finish();assert.throws(()=>f.admit.start([id],[{id,source:'human'}]),/No fresh/);}
 assert.throws(()=>f.admit.start([f.add('agent')],h.data.inbox),/No fresh/);
 assert.equal(h.data.conversation_admissions.length,70);
});
