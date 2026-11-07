const test=require('node:test'),assert=require('node:assert/strict');
const {ActivityParticipation}=require('../activity-participation.cjs');
const {ConversationAdmission}=require('../conversation-admission.cjs');
function fixture(){let now=1000000,saves=0;const history={data:{task:{id:'expired',status:'budget_exhausted',turns:12},events:[],inbox:[]},save(){saves++;}},cfg={username:'Builder',bot_names:['Peer'],human_engagement:{enabled:true,activity_scope:'conversation_only'}},a=new ActivityParticipation(history,cfg,{now:()=>now});
return {a,history,cfg,get now(){return now},advance:n=>now+=n,move(extra={}){a.observe({uuid:'12345678-1234-1234-1234-123456789abc',name:'Visitor',from:{x:0,y:64,z:0},to:{x:1,y:64,z:0},at:now,...extra});},get saves(){return saves}};}
test('activity is coalesced, original, durable and separately scoped from human input',()=>{
 const f=fixture();f.history.data.participation_pending=['human'];f.move();const p=f.a.proposal();
 assert.equal(p.context.messages.length,0);assert.equal(p.context.activities.length,1);assert.equal(p.occurred_at,f.now);
 for(let i=0;i<100;i++){f.advance(50);f.move();}assert.equal(f.a.proposal().signature,p.signature);assert.equal(f.saves,1);
 const reloaded=new ActivityParticipation(f.history,f.cfg,{now:()=>f.now});assert.equal(reloaded.proposal().signature,p.signature);
 f.advance(10000);f.move();assert.equal(f.a.proposal().signature,p.signature);assert.deepEqual(f.history.data.participation_pending,['human']);
 assert.equal(f.a.apply({source_id:p.context.trigger_id,signature:p.signature,action:'engage',offer:{id:'one',ticket:'one'}},[]).queued,true);
 f.move();const next=f.a.proposal();assert.notEqual(next.signature,p.signature);assert.equal(next.occurred_at,f.now);
});
test('ambient delivery is exactly once and only enables effect-free conversation, never old authority',()=>{
 const f=fixture();f.move();const p=f.a.proposal(),before=JSON.stringify(f.history.data.task),inbox=f.history.data.inbox;
 const payload={source_id:p.context.trigger_id,signature:p.signature,action:'engage',offer:{id:'event',ticket:'ticket'}};
 f.a.apply(payload,inbox);assert.equal(inbox[0].source,'activity');assert.equal(inbox[0].message,undefined);
 assert.throws(()=>f.a.apply(payload,inbox),/changed/);assert.equal(inbox.length,1);
 const admission=new ConversationAdmission(f.history,f.cfg,{now:()=>f.now});admission.start([inbox[0].id],inbox);
 assert.equal(f.history.data.turn.ambient_activity,true);assert.equal(f.history.data.turn.may_mutate,false);assert.equal(f.history.data.turn.task_id,null);assert.equal(JSON.stringify(f.history.data.task),before);
});
test('stop, disabled scope, AFK expiry, malformed sources and missing host offers do not grant activity turns',()=>{
 for(const mode of ['stop','disabled','expiry','peer','no-offer']){
  const f=fixture();if(mode==='peer'){f.move({name:'Peer'});assert.equal(f.a.proposal(),null);continue;}
  f.move();const p=f.a.proposal();
  if(mode==='stop')f.history.data.task.status='stopped';
  if(mode==='disabled')delete f.cfg.human_engagement.activity_scope;
  if(mode==='expiry')f.advance(120001);
  if(mode==='no-offer')assert.throws(()=>f.a.apply({source_id:p.context.trigger_id,signature:p.signature,action:'engage'},[]),/Invalid/);
  else assert.equal(f.a.proposal(),null);
  assert.equal(f.history.data.inbox.length,0);
 }
});

test('continuous walking cannot starve slow host judgment; expiry still invalidates old tickets',()=>{
 const f=fixture();f.move();const old=f.a.proposal();
 for(let i=0;i<10;i++){f.advance(10000);f.move();assert.deepEqual(f.a.proposal(),old);}
 assert.equal(f.saves,1);
 f.advance(20001);f.move();const fresh=f.a.proposal();assert.notEqual(fresh.signature,old.signature);
 assert.throws(()=>f.a.apply({source_id:old.context.trigger_id,signature:old.signature,action:'hold'},[]),/changed/);
});
test('interaction facts stay observations, not invented messages or actions with known outcomes',()=>{
 const f=fixture();f.move({kind:'interaction'});const p=f.a.proposal();
 assert.equal(p.context.activities[0].kind,'interaction');assert.equal(p.context.messages.length,0);
 assert.match(p.context.activities[0].summary,/target and result are unknown/);
 assert.equal(p.effect_scope,'conversation_only');assert.equal(f.history.data.task.turns,12);
});
