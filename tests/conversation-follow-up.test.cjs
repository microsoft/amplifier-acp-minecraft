const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const {ConversationFollowUp}=require('../conversation-follow-up.cjs');
const {ConversationAdmission}=require('../conversation-admission.cjs');
function fixture(t,cfg={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'conversation-follow-up-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(dir,'state.json'));h.data.inbox=[];
 let now=10000,blocked=null;
 const admission=new ConversationAdmission(h,cfg,{now:()=>now});
 const wake=new ConversationFollowUp(h,{now:()=>now,blocked:()=>blocked,conversationAllowed:()=>admission.limit()!==0});
 admission.followUpEligible=m=>wake.eligible(m);
 return {h,wake,admission,advance:ms=>now+=ms,block:reason=>blocked=reason};
}
test('one durable reminder survives restart and admission is never replayed after lost acknowledgement',t=>{
 const {h,wake,admission,advance}=fixture(t),saved=wake.set({after_seconds:3600,goal:'Check the current discussion'});
 assert.equal(wake.poll().status,'scheduled');advance(3600000);wake.poll();wake.poll();
 assert.equal(h.data.inbox.length,1);
 const loaded=new WorkshopState(h.file);assert.equal(loaded.data.conversation_follow_up.id,saved.id);
 assert.deepEqual(loaded.data.inbox,h.data.inbox);
 admission.start([saved.id],h.data.inbox); // response lost, no second admission
 const restarted=new WorkshopState(h.file),again=new ConversationFollowUp(restarted);
 assert.equal(again.poll().status,'admitted');assert.equal(restarted.data.inbox.length,0);
 assert.equal(restarted.data.last_conversation_turn.interrupted,true);
 assert.equal(restarted.data.last_conversation_turn.may_mutate,false);
 assert.equal(restarted.data.last_conversation_turn.task_id,null);
});
test('replacement and zero cancel only the pending self-authored input',t=>{
 const {h,wake,advance}=fixture(t);const one=wake.set({after_seconds:1,goal:'old'});advance(1000);wake.poll();
 h.data.inbox.push({id:'human',source:'human',message:'preserve'});
 const two=wake.set({after_seconds:2,goal:'new'});assert.notEqual(one.id,two.id);
 assert.deepEqual(h.data.inbox.map(m=>m.id),['human']);advance(2000);wake.poll();
 wake.set({after_seconds:0});assert.equal(wake.view().status,'cancelled');
 assert.deepEqual(h.data.inbox.map(m=>m.id),['human']);wake.poll();assert.equal(h.data.inbox.length,1);
});
test('Stop cancels pending and queued wakes durably without altering retained unknown receipts',t=>{
 for(const queue of [false,true]){
  const {h,wake,advance}=fixture(t);h.data.last_turn={actions:[{id:'unknown',status:'uncertain'}]};
  wake.set({after_seconds:1,goal:'later'});if(queue){advance(1000);wake.poll();}
  h.stop();const loaded=new WorkshopState(h.file);
  assert.equal(loaded.data.conversation_follow_up.status,'cancelled');assert.equal(loaded.data.inbox.length,0);
  assert.deepEqual(loaded.data.last_turn,h.data.last_turn);
 }
});
test('Stop, disallowed conversation and unresolved effects refuse scheduling and due admission',t=>{
 for(const reason of ['explicit_stop','unresolved_interruption','unresolved_activity_effects']){
  const {h,wake,admission,advance,block}=fixture(t);wake.set({after_seconds:1,goal:'later'});advance(1000);block(reason);
  assert.equal(wake.poll().blocked_reason,reason);assert.equal(h.data.inbox.length,0);
  assert.throws(()=>wake.set({after_seconds:1,goal:'new'}),/unavailable/);block(null);wake.poll();block(reason);
  assert.deepEqual(admission.status(h.data.inbox).eligible_ids,[]);
  wake.set({after_seconds:0});assert.equal(wake.view().status,'cancelled');
 }
 const {wake}=fixture(t,{human_reply_turns_per_hour:0});assert.throws(()=>wake.set({after_seconds:1,goal:'later'}),/conversation_disabled/);
});
test('native Stop and conversation uncertainty remain blockers independently of optional work policy',t=>{
 const {h,wake}=fixture(t);h.data.activity_stop={at:1000};assert.throws(()=>wake.set({after_seconds:1,goal:'later'}),/explicit_stop/);
 delete h.data.activity_stop;h.data.task={status:'stopped'};assert.throws(()=>wake.set({after_seconds:1,goal:'later'}),/explicit_stop/);
 h.data.task=null;h.data.last_conversation_turn={actions:[{status:'uncertain'}]};assert.throws(()=>wake.set({after_seconds:1,goal:'later'}),/unresolved/);
});
test('delay and goal validation do not create a timer or accept coerced values',t=>{
 const {h,wake}=fixture(t);
 for(const n of [-1,3601,0.5,NaN,Infinity,true,'5',null,undefined])assert.throws(()=>wake.set({after_seconds:n,goal:'later'}),/integer/);
 for(const goal of ['',null,12,'x'.repeat(2001)])assert.throws(()=>wake.set({after_seconds:1,goal}),/goal/);
 assert.equal(h.data.conversation_follow_up,undefined);assert.deepEqual(wake.set({after_seconds:0}),{status:'none'});
});
test('forged source, changed goal, private audience and cancelled identifiers cannot be admitted',t=>{
 const {h,wake,admission,advance}=fixture(t);wake.set({after_seconds:1,goal:'later'});advance(1000);wake.poll();
 const m=h.data.inbox[0];assert.equal(wake.eligible(m),true);
 for(const delta of [{id:'fake'},{source:'human'},{message:'different'},{reply_scope:'public'},{whisper:true},{attention_offer:{ticket:'forged'}},{source_fact:{id:m.id}}])assert.equal(wake.eligible({...m,...delta}),false);
 wake.set({after_seconds:0});assert.equal(wake.eligible(m),false);assert.throws(()=>admission.start([m.id],[m]),/No fresh/);
});
test('existing reply pacing applies to self-authored reminders, including across restart',t=>{
 const {h,wake,admission,advance}=fixture(t,{human_reply_turns_per_hour:1});
 wake.set({after_seconds:1,goal:'one'});advance(1000);wake.poll();admission.start([h.data.inbox[0].id],h.data.inbox);h.finish();
 wake.set({after_seconds:1,goal:'two'});advance(1000);wake.poll();
 assert.equal(admission.status(h.data.inbox).remaining,0);assert.throws(()=>admission.start([h.data.inbox[0].id],h.data.inbox),/No fresh/);
 assert.equal(new WorkshopState(h.file).data.conversation_admissions.length,1);
 advance(3600000);admission.start([h.data.inbox[0].id],h.data.inbox);assert.equal(h.data.turn.follow_up,true);
});
test('failed durable schedule or delivery does not leave an in-memory wake eligible',t=>{
 const {h,wake,advance}=fixture(t),save=h.save;h.save=()=>{throw Error('disk failure');};
 assert.throws(()=>wake.set({after_seconds:1,goal:'later'}),/disk/);assert.equal(wake.view().status,'none');
 h.save=save;wake.set({after_seconds:1,goal:'later'});advance(1000);const inbox=h.data.inbox;h.save=()=>{throw Error('disk failure');};
 assert.throws(()=>wake.poll(),/disk/);assert.equal(wake.view().status,'scheduled');assert.equal(inbox,h.data.inbox);assert.equal(inbox.length,0);
});
test('a new self-authored follow-up does not requeue an already admitted one',t=>{
 const {h,wake,admission,advance}=fixture(t);wake.set({after_seconds:1,goal:'one'});advance(1000);wake.poll();
 const id=h.data.inbox[0].id;admission.start([id],h.data.inbox);wake.set({after_seconds:1,goal:'two'});
 assert.deepEqual(h.data.turn.request_ids,[id]);assert.notEqual(wake.view().id,id);
 wake.set({after_seconds:0});assert.deepEqual(h.data.turn.request_ids,[id]);
});
