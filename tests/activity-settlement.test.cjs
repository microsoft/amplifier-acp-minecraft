const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {WorkshopState}=require('../workshop-state.cjs'),policy=require('../activity-policy.cjs');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex'),cfg={human_engagement:{enabled:true,task_optional:true}};
const review=(...args)=>require('../activity-settlement.cjs').review(...args);
function fixture(t){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'activity-settlement-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(home,'workshop.json'));
 h.data.task={id:'preserved',status:'blocked',turns:8,max_turns:12,deadline:1,progress:[{summary:'Prior work'}],recovery_attempts:2,authority:{source:'original'}};
 const position={x:1.5,y:64,z:.5},failed={kind:'settled_failed_movement',before:position,position,reached:false,replayed:false};
 const speech={sent:'The route is blocked.',operation_id:'utterance',packet_count:1,transport_submitted:true,recipient_delivery_verified:false};
 h.data.last_turn={activity:true,task_id:null,interrupted:true,started_at:'2026-11-11T01:00:00Z',request_ids:['old-input'],activity_report:{status:'running'},actions:[{id:'walk',status:'succeeded'},{id:'place',status:'succeeded'},{id:'speak',status:'succeeded'},{id:'failed',status:'failed_settled',outcome:failed}],speech_operations:[{id:'utterance',status:'submitted',packets:[{text:speech.sent,status:'submitted',receipt:{sent:speech.sent}}],result:speech}]};
 const actions=[['walk','move',{x:1,y:64,z:0,mode:'normal'},{position,target:{x:1,y:64,z:0},reached:true}],['place','place',{x:2,y:63,z:0,item:'cobblestone'},{position:{x:2,y:63,z:0},actual:'cobblestone',verified:true}],['speak','chat',{text:speech.sent},speech],['failed','move',{x:2,y:64,z:0,mode:'normal'},null]];
 for(const [i,[id,action,args,result]] of actions.entries()){
  h.data.events.push({id:crypto.randomUUID(),kind:'action_started',action_id:id,action,arguments:args,time:`2026-11-11T01:00:0${i+1}Z`});
  h.data.events.push({id:crypto.randomUUID(),kind:result?'action_result':'action_failed',action_id:id,action,arguments:args,time:`2026-11-11T01:00:0${i+1}.500Z`,...(result?{result}:{error:'No path to the goal!',settled_failure:failed})});
 }
 const observation={position,inventory:{slots:[],cursor:null}};
 const input={generation:3,request_id:crypto.randomUUID(),expected_turn_sha256:digest(h.data.last_turn),expected_task_sha256:digest(h.data.task),expected_position:position,expected_inventory_sha256:digest(observation.inventory),evidence_sha256:'a'.repeat(64),reason:'Owner verified terminal engine and domain receipts, no active worker, current inventory and position; no prior input or effect will be replayed.',receipts:actions.map(([action_id])=>({action_id,receipt_sha256:digest(h.data.events.find(e=>e.action_id===action_id&&e.kind!=='action_started'))}))};
 h.save();return {h,input,observation};
}
test('review retains interrupted activity and all effects, permits fresh admission but never continuation',t=>{
 const {h,input,observation}=fixture(t),before=structuredClone(h.data);
 assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
 const result=review(h,cfg,input,observation);assert.equal(result.activity_allowed,true);assert.equal(result.future_work_only,true);assert.equal(result.replayed,false);assert.equal(result.task_changed,false);
 assert.equal(policy.canContinue(h,cfg),false);assert.equal(h.data.last_turn.interrupted,true);
 const stripped=structuredClone(h.data.last_turn);delete stripped.effect_review;assert.deepEqual(stripped,before.last_turn);
 assert.deepEqual(h.data.task,before.task);assert.deepEqual(h.data.events,before.events);
 const saved=JSON.stringify(h.data),reload=new WorkshopState(h.file);
 assert.equal(policy.allowed(reload,cfg),true);assert.equal(review(reload,cfg,input,observation).duplicate,true);assert.equal(JSON.stringify(reload.data),saved);
 assert.throws(()=>review(reload,cfg,{...input,request_id:crypto.randomUUID()},observation),/reviewed/);
 reload.data.activity_stop={at:Date.now()};assert.equal(policy.reason(reload,cfg),'explicit_stop');
});
for(const mutation of ['pending','uncertain','active','not_interrupted','task_turn','disabled','stopped','missing_action','duplicate_action','extra_receipt','missing_receipt','changed_receipt','missing_terminal','duplicate_terminal','arguments_changed','old_start','end_before_start','timeout','unsettled','unknown_move','unverified_place','wrong_place','wrong_move','no_arrival','async_action','old_unsettled_sequence','current_sequence','incomplete_speech','unsubmitted_packet','changed_speech','outcome_changed','task_changed','turn_changed','position_changed','inventory_changed','cursor_held','empty_reason'])test('settled interruption refuses '+mutation+' without mutation',t=>{
 const {h,input,observation}=fixture(t),end=id=>h.data.events.find(e=>e.action_id===id&&e.kind!=='action_started'),start=id=>h.data.events.find(e=>e.action_id===id&&e.kind==='action_started');
 let config=cfg;
 if(mutation==='pending')h.data.last_turn.actions[0].status='pending';
 if(mutation==='uncertain')h.data.last_turn.actions[0].status='uncertain';
 if(mutation==='active')h.data.turn={conversation_only:true};
 if(mutation==='not_interrupted')h.data.last_turn.interrupted=false;
 if(mutation==='task_turn')h.data.last_turn.task_id='preserved';
 if(mutation==='disabled')config={};
 if(mutation==='stopped')h.data.activity_stop={at:Date.now()};
 if(mutation==='missing_action')h.data.last_turn.actions.pop();
 if(mutation==='duplicate_action')h.data.last_turn.actions.push(h.data.last_turn.actions[0]);
 if(mutation==='extra_receipt')input.receipts.push({...input.receipts[0],action_id:'extra'});
 if(mutation==='missing_receipt')input.receipts.pop();
 if(mutation==='changed_receipt')end('walk').result.position.y++;
 if(mutation==='missing_terminal')h.data.events=h.data.events.filter(e=>e!==end('walk'));
 if(mutation==='duplicate_terminal')h.data.events.push({...end('walk'),id:crypto.randomUUID()});
 if(mutation==='arguments_changed')end('walk').arguments={...end('walk').arguments,x:88};
 if(mutation==='old_start')start('walk').time='2026-11-10T01:00:00Z';
 if(mutation==='end_before_start')end('walk').time='2026-11-11T01:00:00Z';
 if(mutation==='timeout')end('failed').timeout=true;
 if(mutation==='unsettled')end('failed').operation_settled=false;
 if(mutation==='unknown_move')end('failed').error='Transport closed before settlement';
 if(mutation==='unverified_place')end('place').result.verified=false;
 if(mutation==='wrong_place')end('place').result.position.x++;
 if(mutation==='wrong_move')end('walk').result.target.x++;
 if(mutation==='no_arrival')end('walk').result.reached=false;
 if(mutation==='async_action'){start('walk').action='start_sequence';end('walk').action='start_sequence';}
 if(mutation==='old_unsettled_sequence')h.data.action_sequences=[{id:'old',status:'running',started_at:'2026-11-10T01:00:00Z'}];
 if(mutation==='current_sequence')h.data.action_sequences=[{id:'current',status:'completed',started_at:'2026-11-11T01:00:01Z'}];
 if(mutation==='incomplete_speech')h.data.last_turn.speech_operations[0].status='incomplete';
 if(mutation==='unsubmitted_packet')h.data.last_turn.speech_operations[0].packets[0].status='submitting';
 if(mutation==='changed_speech')h.data.last_turn.speech_operations[0].packets[0].receipt.sent='Other text';
 if(mutation==='outcome_changed')h.data.last_turn.actions.at(-1).outcome={...h.data.last_turn.actions.at(-1).outcome,reached:true};
 if(mutation==='task_changed')h.data.task.turns++;
 if(mutation==='turn_changed')h.data.last_turn.request_ids.push('different-input');
 if(mutation==='position_changed')observation.position={...observation.position,y:65};
 if(mutation==='inventory_changed')observation.inventory.slots.push({name:'dirt'});
 if(mutation==='cursor_held'){observation.inventory.cursor={name:'dirt'};input.expected_inventory_sha256=digest(observation.inventory);}
 if(mutation==='empty_reason')input.reason='';
 // Semantic exclusions must fail even when an owner supplied hashes of them.
 if(!['changed_receipt','task_changed','turn_changed'].includes(mutation)){
  input.expected_turn_sha256=digest(h.data.last_turn);
  for(const item of input.receipts){const e=end(item.action_id);if(e)item.receipt_sha256=digest(e);}
 }
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,config,input,observation));assert.equal(JSON.stringify(h.data),before);
});
test('failed persistence keeps the interruption guard closed in memory and on disk',t=>{
 const {h,input,observation}=fixture(t),before=JSON.stringify(h.data);h.save=()=>{throw Error('disk full');};
 assert.throws(()=>review(h,cfg,input,observation),/disk full/);assert.equal(JSON.stringify(h.data),before);assert.equal(policy.allowed(new WorkshopState(h.file),cfg),false);
});
test('review cannot be carried onto a changed interrupted turn or newly pending action',t=>{
 const {h,input,observation}=fixture(t);review(h,cfg,input,observation);
 h.data.last_turn.actions[0].status='pending';assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
 h.data.last_turn.actions[0].status='succeeded';h.data.last_turn.request_ids.push('new-source');assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
});
