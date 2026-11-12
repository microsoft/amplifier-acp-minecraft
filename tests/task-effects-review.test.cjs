const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {WorkshopState}=require('../workshop-state.cjs'),{review}=require('../activity-review.cjs'),policy=require('../activity-policy.cjs');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex'),cfg={human_engagement:{enabled:true,task_optional:true}};
function fixture(t){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'task-effects-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(home,'workshop.json'));
 h.data.task={id:'original-task',status:'needs_review',turns:4,max_turns:12,deadline:Date.now()+600000,progress:[],recovery_attempts:1,authority:{source:'original-human'}};
 h.data.last_turn={task_id:'original-task',interrupted:true,started_at:'2026-11-12T11:37:00Z',actions:[{id:'done',status:'succeeded'},{id:'move',status:'uncertain'},{id:'dig',status:'uncertain'}]};
 for(const id of ['move','dig'])for(const kind of ['action_started','action_failed'])h.data.events.push({id:crypto.randomUUID(),kind,action_id:id,action:id,time:'2026-11-12T11:37:01Z',arguments:{x:1,y:63,z:0},...(kind==='action_failed'?{error:id==='move'?'Movement ended without reaching the requested destination; inspect current position':'Refusing to remove a block supporting a player; move to safe footing first'}:{})});
 const observation={position:{x:0.5,y:64,z:0.5},inventory:{slots:[],cursor:null}};
 const input={request_id:crypto.randomUUID(),generation:3,expected_turn_sha256:digest(h.data.last_turn),expected_task_sha256:digest(h.data.task),expected_position:observation.position,expected_inventory_sha256:digest(observation.inventory),evidence_sha256:'a'.repeat(64),reviews:['move','dig'].map(action_id=>({action_id,receipt_sha256:digest(h.data.events.find(e=>e.action_id===action_id&&e.kind==='action_failed')),outcome:action_id==='move'?'settled_failed_movement':'no_effect',reason:'Owner inspected exact original source, terminal receipts and current observation; no pending worker or replay.'}))};h.save();return {h,input,observation};
}
test('task-effects review alone grants nothing; separately bound resume preserves spent authority and failed history',t=>{
 const {h,input,observation}=fixture(t),before=structuredClone(h.data);
 assert.equal(review(h,cfg,input,observation,{taskEffects:true}).activity_allowed,false);
 assert.deepEqual(h.data.task,before.task);assert.equal(policy.reason(h,cfg),'unresolved_task_effects');
 const saved=JSON.stringify(h.data);assert.equal(review(h,cfg,input,observation,{taskEffects:true}).duplicate,true);assert.equal(JSON.stringify(h.data),saved);
 const reload=new WorkshopState(h.file);
 assert.throws(()=>reload.resumeReviewed({task_id:'original-task',reason:'Inspected'}),/exact task-effects/);
 reload.resumeReviewed({task_id:'original-task',reason:'Original provider turn is terminal; inspect current world and continue fresh without replay.',effects_review_id:input.request_id});
 assert.equal(reload.data.task.status,'running');assert.equal(policy.allowed(reload,cfg),true);
 for(const k of ['turns','max_turns','deadline','authority','recovery_attempts'])assert.deepEqual(reload.data.task[k],before.task[k]);
 assert.deepEqual(reload.data.events,before.events);assert.equal(reload.data.last_turn.interrupted,true);assert.deepEqual(reload.data.last_turn.actions.map(a=>a.status),['succeeded','uncertain','uncertain']);
 assert.equal(policy.canContinue(reload,cfg),false);assert.equal(policy.allowed(new WorkshopState(h.file),cfg),true);
 reload.data.activity_stop={at:Date.now()};assert.equal(policy.reason(reload,cfg),'explicit_stop');
});
for(const mutation of ['task_changed','pending','active','missing','different_task','dig_ack_unknown','timeout','movement_no_effect'])test('rejects task-effects '+mutation+' without mutation',t=>{
 const {h,input,observation}=fixture(t);
 if(mutation==='task_changed')h.data.task.turns++;
 if(mutation==='pending')h.data.last_turn.actions[0].status='pending';
 if(mutation==='active')h.data.turn={};
 if(mutation==='missing')input.reviews.pop();
 if(mutation==='different_task')h.data.last_turn.task_id='other';
 if(mutation==='movement_no_effect')input.reviews[0].outcome='no_effect';
 const e=h.data.events.find(e=>e.action_id==='dig'&&e.kind==='action_failed');
 if(mutation==='dig_ack_unknown')e.error='Server did not confirm removal';
 if(mutation==='timeout')e.timeout=true;
 if(['dig_ack_unknown','timeout'].includes(mutation))input.reviews[1].receipt_sha256=digest(e);
 input.expected_turn_sha256=digest(h.data.last_turn);
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation,{taskEffects:true}));assert.equal(JSON.stringify(h.data),before);
});
for(const mutation of ['task_changed','expired','spent','wrong_review','stopped','active'])test('review cannot resume changed task '+mutation,t=>{
 const {h,input,observation}=fixture(t);review(h,cfg,input,observation,{taskEffects:true});
 if(mutation==='task_changed')h.data.task.authority={source:'different'};
 if(mutation==='expired')h.data.task.deadline=1;
 if(mutation==='spent')h.data.task.turns=12;
 if(mutation==='stopped')h.data.task.status='stopped';
 if(mutation==='active')h.data.turn={};
 assert.throws(()=>h.resumeReviewed({task_id:'original-task',reason:'Review',effects_review_id:mutation==='wrong_review'?crypto.randomUUID():input.request_id}));
 assert.equal(h.data.last_turn.effect_review.resumed_task_id,undefined);assert.equal(policy.reason(h,cfg),'unresolved_task_effects');
});
test('failed resume persistence cannot leave in-memory permission open',t=>{
 const {h,input,observation}=fixture(t);review(h,cfg,input,observation,{taskEffects:true});const before=JSON.stringify(h.data);
 h.save=()=>{throw Error('disk full');};assert.throws(()=>h.resumeReviewed({task_id:'original-task',reason:'Review',effects_review_id:input.request_id}),/disk full/);
 assert.equal(JSON.stringify(h.data),before);assert.equal(policy.reason(h,cfg),'unresolved_task_effects');
});
for(const error of ['Action cancelled','Transport closed before movement settlement','Unexpected movement worker error','Took to long to decide path to goal!'])test('interrupted movement terminal classification: '+error,t=>{
 const {h,input,observation}=fixture(t),e=h.data.events.find(e=>e.action_id==='move'&&e.kind==='action_failed');
 e.error=error;input.reviews[0].receipt_sha256=digest(e);const before=JSON.stringify(h.data);
 if(error==='Took to long to decide path to goal!')assert.equal(review(h,cfg,input,observation,{taskEffects:true}).activity_allowed,false);
 else{assert.throws(()=>review(h,cfg,input,observation,{taskEffects:true}),/affirmative supported terminal/);assert.equal(JSON.stringify(h.data),before);}
});
