const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const {ConversationAdmission}=require('../conversation-admission.cjs');
const {TaskIntake}=require('../task-intake.cjs');
const {ActionLease}=require('../action-lease.cjs');
const work=require('../reply-work.cjs');
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'reply-work-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(dir,'history.json')),cfg={incoming_chat_only:true,human_engagement:{enabled:true},human_task_intake:{enabled:true}};
 const intake=new TaskIntake(h,cfg),admission=new ConversationAdmission(h,cfg);
 h.data.task={id:'same',authority:{kind:'human_game_request'},authority_revision:1,status:'running',deadline:Date.now()+3600000,turns:8,max_turns:12,progress:[],recovery_attempts:2};
 function reply(extra={}){const e=h.record({kind:'chat',source:'human',username:'Visitor',message:'Go stand by it',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString(),transport:{kind:'server_player_uuid',username:'Visitor',uuid:'verified'},...extra});h.data.inbox=[{id:e.id,source:'human',username:'Visitor',message:e.message}];admission.start([e.id],h.data.inbox);work.bind(h,cfg,intake.runnable()&&!intake.requiresReview(h.task()));}
 return {h,cfg,intake,reply};
}
test('human reply uses existing authority only when an effect is requested, with one durable work reservation',t=>{
 const f=fixture(t),before=structuredClone(f.h.task());f.reply();
 assert.deepEqual(f.h.task(),before);assert.equal(f.intake.capabilities().reply_work_allowed,true);assert.equal(f.intake.capabilities().blocked_reason,null);
 work.promote(f.h,f.intake.runnable());assert.equal(f.h.task().turns,9);assert.equal(f.h.task().deadline,before.deadline);assert.equal(f.h.task().recovery_attempts,2);
 assert.equal(f.h.data.turn.task_id,'same');assert.equal(f.h.data.turn.conversation_only,false);
 assert.throws(()=>work.promote(f.h,true),/unchanged/);
 const lease=new ActionLease();assert.equal(lease.begin(f.h.data.turn,f.h.task(),true).renewable,true);
 f.h.actionStarted('move');f.h.actionSettled('move',true);f.h.report({status:'running',summary:'Arrived at the requested existing site'});f.h.finish();assert.equal(f.h.task().status,'running');
});
test('pure conversation does not spend a task turn or overwrite work recovery evidence',t=>{
 const f=fixture(t);f.h.data.last_turn={task_id:'same',actions:[]};const before=structuredClone([f.h.task(),f.h.data.last_turn]);f.reply();f.h.finish();assert.deepEqual([f.h.task(),f.h.data.last_turn],before);
});
test('stopped, blocked, expired, exhausted and interrupted assignments never become reply effects',t=>{
 for(const status of ['stopped','blocked','needs_review','review','budget_exhausted']){const f=fixture(t);f.h.task().status=status;f.reply();assert.equal(f.intake.capabilities().reply_work_allowed,false);assert.throws(()=>work.promote(f.h,f.intake.runnable()));}
 for(const change of [h=>h.task().deadline=1,h=>h.task().max_turns=8,h=>h.data.last_turn={task_id:'same',interrupted:true,started_at:new Date().toISOString(),actions:[{status:'pending'}]}]){const f=fixture(t);change(f.h);f.reply();assert.equal(f.intake.capabilities().reply_work_allowed,false);}
});
test('authority changes, unattributed sources and non-human opportunities cannot inherit the binding',t=>{
 for(const mutate of [f=>f.h.task().authority_revision++,f=>f.h.task().id='different',f=>f.h.task().turns++,f=>f.h.data.turn.ambient_activity=true,f=>f.h.data.turn.peer_proposal=true]){const f=fixture(t);f.reply();mutate(f);assert.throws(()=>work.promote(f.h,true));}
 const f=fixture(t);f.reply({transport:null});assert.throws(()=>work.promote(f.h,true));
});
test('lost response/restart after promotion preserves consumed work and unresolved effects',t=>{
 const f=fixture(t);f.reply();work.promote(f.h,true);f.h.actionStarted('unknown');
 const loaded=new WorkshopState(f.h.file);assert.equal(loaded.task().turns,9);assert.equal(loaded.task().status,'needs_review');assert.equal(loaded.data.last_turn.actions[0].status,'pending');assert.equal(loaded.data.last_turn.reply_origin,true);
});
test('failed persistence cannot leave an unsaved effect allowance in memory',t=>{
 const f=fixture(t);f.reply();const before=structuredClone(f.h.data);f.h.save=()=>{throw Error('disk full');};assert.throws(()=>work.promote(f.h,true),/disk full/);assert.deepEqual(f.h.data,before);
});
