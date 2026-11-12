const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {WorkshopState}=require('../workshop-state.cjs'),{review}=require('../activity-review.cjs'),policy=require('../activity-policy.cjs');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex'),cfg={human_engagement:{enabled:true,task_optional:true}};
for(const mode of ['confirmed','no_effect','wrong_item','wrong_coordinate','missing_item','fractional','no_answer','unloaded','timeout','unsettled','missing_terminal','duplicate_terminal','interrupted_task'])test('historical single placement review '+mode,t=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'placement-review-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));const h=new WorkshopState(path.join(home,'state.json'));
 h.data.task={id:'existing',status:'running',turns:15,max_turns:40,deadline:Date.now()+60000,authority:{source:'original-human'},progress:[{summary:'prior work'}],recovery_attempts:2};
 h.data.last_turn={activity:true,task_id:null,interrupted:false,started_at:'2026-11-12T13:24:00Z',actions:[{id:'prior-move',status:'succeeded'},{id:'refused',status:'uncertain'}]};
 const args={x:-518,y:56,z:-558,item:'dirt',support_face:'west'};
 const end={id:'terminal',kind:'action_failed',action:'place',action_id:'refused',time:'2026-11-12T13:24:02Z',arguments:{...args},error:'Server refused to place dirt at (-518, 56, -558): the block is still air'};
 h.data.events=[{id:'start',kind:'action_started',action:'place',action_id:'refused',time:'2026-11-12T13:24:01Z',arguments:{...args}},end];
 if(mode==='wrong_item')end.error=end.error.replace('dirt','stone');if(mode==='wrong_coordinate')end.error=end.error.replace('-518','-519');
 if(mode==='missing_item')for(const e of h.data.events)delete e.arguments.item;
 if(mode==='fractional')for(const e of h.data.events)e.arguments.x=-518.5;
 if(mode==='no_answer')end.error='Server did not answer the placement';if(mode==='unloaded')end.error='Placement mismatch: expected dirt, observed undefined';
 if(mode==='timeout')end.timeout=true;if(mode==='unsettled')end.operation_settled=false;
 if(mode==='missing_terminal')h.data.events.pop();if(mode==='duplicate_terminal')h.data.events.push({...end,id:'second'});
 if(mode==='interrupted_task'){h.data.task.status='needs_review';Object.assign(h.data.last_turn,{activity:false,task_id:'existing',interrupted:true});}
 const observation={position:{x:-514.5,y:56,z:-557.5},inventory:{slots:[{name:'dirt',count:10}],cursor:null}};
 const input={generation:2,request_id:crypto.randomUUID(),expected_turn_sha256:hash(h.data.last_turn),expected_position:observation.position,expected_inventory_sha256:hash(observation.inventory),evidence_sha256:'a'.repeat(64),reviews:[{action_id:'refused',receipt_sha256:hash(end),outcome:mode==='no_effect'?'no_effect':'settled_failed_placement',reason:'Owner verified exact installed Mineflayer terminal path and current state; prior movement/equip retained, historical inventory delta unknown; no replay.'}],...(mode==='interrupted_task'?{expected_task_sha256:hash(h.data.task)}:{})};h.save();const before=structuredClone(h.data);
 if(mode==='confirmed'){
  const r=review(h,cfg,input,observation);assert.equal(r.activity_allowed,true);assert.equal(r.replayed,false);assert.equal(policy.canContinue(h,cfg),false);
  assert.deepEqual(h.data.task,before.task);assert.deepEqual(h.data.events,before.events);assert.equal(h.data.last_turn.actions[1].status,'uncertain');
  const reload=new WorkshopState(h.file),saved=JSON.stringify(reload.data);assert.equal(review(reload,cfg,input,observation).duplicate,true);assert.equal(JSON.stringify(reload.data),saved);assert.equal(policy.allowed(reload,cfg),true);
  reload.data.activity_stop={at:Date.now()};assert.equal(policy.reason(reload,cfg),'explicit_stop');
 }else{assert.throws(()=>review(h,cfg,input,observation,{taskEffects:mode==='interrupted_task'}));assert.deepEqual(h.data,before);}
});
