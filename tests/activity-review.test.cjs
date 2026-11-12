const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {WorkshopState}=require('../workshop-state.cjs'),policy=require('../activity-policy.cjs'),{review}=require('../activity-review.cjs');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex'),cfg={human_engagement:{enabled:true,task_optional:true}};
function fixture(t){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'activity-review-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(home,'workshop.json'));h.data.task={id:'expired',status:'budget_exhausted',turns:8,deadline:1};
 h.data.last_turn={activity:true,task_id:null,interrupted:false,started_at:'2026-11-11T01:00:00Z',activity_report:{status:'running'},actions:[{id:'old-success',status:'succeeded'},{id:'refused',status:'uncertain'},{id:'partial',status:'uncertain'}]};
 for(const [id,mode] of [['refused','walk_only'],['partial','normal']])for(const kind of ['action_started','action_failed'])h.data.events.push({id:crypto.randomUUID(),action_id:id,action:'move',kind,time:'2026-11-11T01:00:01Z',arguments:{x:1,y:64,z:0,mode},...(kind==='action_failed'?{error:'retained failure'}:{})});
 const observation={position:{x:0.5,y:64,z:0.5},inventory:{slots:[null],cursor:null}};
 const input={generation:3,request_id:crypto.randomUUID(),expected_turn_sha256:digest(h.data.last_turn),expected_position:observation.position,expected_inventory_sha256:digest(observation.inventory),evidence_sha256:'a'.repeat(64),reviews:['refused','partial'].map(action_id=>({action_id,receipt_sha256:digest(h.data.events.find(e=>e.action_id===action_id&&e.kind==='action_failed')),outcome:action_id==='refused'?'no_effect':'settled_failed_movement',reason:'Owner inspected the exact terminal receipt, historical source, settled native tool and current world observation.'}))};h.save();return {h,input,observation};
}
test('atomic per-action review preserves original failures and allows fresh work, never continuation',t=>{
 const {h,input,observation}=fixture(t),before=structuredClone(h.data);
 assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
 const result=review(h,cfg,input,observation);assert.equal(result.activity_allowed,true);assert.equal(result.future_work_only,true);assert.equal(result.replayed,false);assert.equal(policy.canContinue(h,cfg),false);
 assert.deepEqual(h.data.events,before.events);assert.deepEqual(h.data.task,before.task);
 const saved=JSON.stringify(h.data);const reloaded=new WorkshopState(h.file);
 assert.equal(policy.allowed(reloaded,cfg),true);assert.equal(policy.canContinue(reloaded,cfg),false);
 assert.equal(review(reloaded,cfg,input,observation).duplicate,true);assert.equal(JSON.stringify(reloaded.data),saved);
 const stripped=structuredClone(h.data.last_turn);delete stripped.effect_review;for(const a of stripped.actions)delete a.review;
 assert.deepEqual(stripped,before.last_turn);assert.equal(h.data.last_turn.actions[2].status,'uncertain');
 assert.throws(()=>review(reloaded,cfg,{...input,request_id:crypto.randomUUID()},observation),/changed/);
 reloaded.data.activity_stop={at:Date.now()};assert.equal(policy.reason(reloaded,cfg),'explicit_stop');
});
for(const mode of ['pending','interrupted','active','task_turn','missing','extra','duplicate','receipt_changed','receipt_missing','multiple_terminals','arguments_changed','timeout','unsettled','non_move','older_start','normal_no_effect','position_changed','inventory_changed','stale_turn','empty_reason'])test('rejects '+mode+' without mutation',t=>{
 const {h,input,observation}=fixture(t),end=h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_failed');
 if(mode==='pending')h.data.last_turn.actions[1].status='pending';
 if(mode==='interrupted')h.data.last_turn.interrupted=true;
 if(mode==='active')h.data.turn={conversation_only:true};
 if(mode==='task_turn')h.data.last_turn.task_id='expired';
 if(mode==='missing')input.reviews.pop();
 if(mode==='extra')input.reviews.push({...input.reviews[0],action_id:'other'});
 if(mode==='duplicate')input.reviews[1]=input.reviews[0];
 if(mode==='receipt_changed')end.error='changed';
 if(mode==='receipt_missing')h.data.events=h.data.events.filter(e=>e!==end);
 if(mode==='multiple_terminals')h.data.events.push({...end,id:'another'});
 if(mode==='arguments_changed')end.arguments={...end.arguments,x:99};
 if(mode==='timeout')end.timeout=true;
 if(mode==='unsettled')end.operation_settled=false;
 if(mode==='non_move')end.action='dig';
 if(mode==='older_start')h.data.events[0].time='2026-11-10T01:00:00Z';
 if(mode==='normal_no_effect')input.reviews[1].outcome='no_effect';
 if(mode==='position_changed')observation.position={...observation.position,x:99};
 if(mode==='inventory_changed')observation.inventory.cursor={name:'stone',count:1};
 if(mode==='empty_reason')input.reviews[1].reason=' ';
 input.expected_turn_sha256=mode==='stale_turn'?'b'.repeat(64):digest(h.data.last_turn);
 // Exercise semantic checks as well as the receipt-hash guard.
 if(['timeout','unsettled','non_move','arguments_changed'].includes(mode))input.reviews[1].receipt_sha256=digest(end);
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation));assert.equal(JSON.stringify(h.data),before);
});
test('disk failure rolls back every review and policy remains held',t=>{
 const {h,input,observation}=fixture(t),before=JSON.stringify(h.data),disk=fs.readFileSync(h.file,'utf8');h.save=()=>{throw Error('disk full');};
 assert.throws(()=>review(h,cfg,input,observation),/disk full/);assert.equal(JSON.stringify(h.data),before);assert.equal(fs.readFileSync(h.file,'utf8'),disk);assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
});
for(const [action,args,error,outcome='no_effect'] of [
 ['place',{x:1,y:64,z:0,item:'cobblestone',support_face:'up'},'Target is not empty'],
 ['gather',{block:'wheat',count:2,targets:[{x:1,y:64,z:0},{x:2,y:64,z:0}]},'Movement ended without reaching the requested destination; inspect current position','settled_partial_gather'],
 ['gather',{block:'stone',count:3,targets:[{x:1,y:64,z:0}]},'Gather count must be 1–8 and no greater than the target selection'],
 ['container',{operation:'withdraw',count:1},'Transfer needs an exact item name and count from 1 to 64'],
 ['container',{operation:'withdraw',item:'wooden_pickaxe',count:1},'Named, enchanted, or component-bearing items need explicit selection: inspect, then supply source_slot and source_item_revision','settled_failed_storage'],
 ['move',{x:1000,y:64,z:0,mode:'normal'},'Coordinates must be whole blocks within 64 blocks of this player'],
 ['container',{x:1,y:64,z:0,operation:'inspect',expected:'barrel'},'Container is obstructed; inspect the observed blocker and choose a clear reachable position'],
 ['container',{x:8,y:64,z:0,operation:'inspect',expected:'barrel'},'Move within four blocks of the container first; no movement performed']
])test('owner can review legacy preflight refusal '+action+' '+error,t=>{
 const {h,input,observation}=fixture(t);
 for(const e of h.data.events.filter(e=>e.action_id==='partial')){e.action=action;e.arguments=args;if(e.kind==='action_failed')e.error=error;}
 const item=input.reviews[1];item.outcome=outcome;item.receipt_sha256=digest(h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_failed'));
 const before=structuredClone(h.data);assert.equal(review(h,cfg,input,observation).activity_allowed,true);
 assert.deepEqual(h.data.events,before.events);assert.deepEqual(h.data.task,before.task);assert.equal(policy.canContinue(h,cfg),false);
 assert.equal(policy.allowed(new WorkshopState(h.file),cfg),true);
});
for(const operation of ['deposit','withdraw','recover','inspect'])test('storage unknown/transfer is not cleared by legacy review '+operation,t=>{
 const {h,input,observation}=fixture(t);
 for(const e of h.data.events.filter(e=>e.action_id==='partial')){e.action='container';e.arguments={operation};if(e.kind==='action_failed')e.error=operation==='inspect'?'Window acknowledgment missing':'Container is obstructed; inspect the observed blocker and choose a clear reachable position';}
 input.reviews[1].outcome='no_effect';input.reviews[1].receipt_sha256=digest(h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_failed'));
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation));assert.equal(JSON.stringify(h.data),before);
});

test('an opened storage inspection is not falsely reviewed as no effect',t=>{
 const {h,input,observation}=fixture(t);
 for(const e of h.data.events.filter(e=>e.action_id==='partial')){e.action='container';e.arguments={operation:'withdraw',item:'wooden_pickaxe',count:1};if(e.kind==='action_failed')e.error='Named, enchanted, or component-bearing items need explicit selection: inspect, then supply source_slot and source_item_revision';}
 input.reviews[1].outcome='no_effect';input.reviews[1].receipt_sha256=digest(h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_failed'));
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation));assert.equal(JSON.stringify(h.data),before);
});
for(const error of ['Requested support face has no solid supporting block','Placement target changed during preparation; inspect before retrying','Target is not empty after movement','Connection closed'])test('placement preparation or unknown failure is not initial no-effect review: '+error,t=>{
 const {h,input,observation}=fixture(t);
 for(const e of h.data.events.filter(e=>e.action_id==='partial')){e.action='place';e.arguments={x:1,y:64,z:0,item:'cobblestone',support_face:'up'};if(e.kind==='action_failed')e.error=error;}
 input.reviews[1].outcome='no_effect';input.reviews[1].receipt_sha256=digest(h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_failed'));
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation));assert.equal(JSON.stringify(h.data),before);
});

for(const [error,outcome] of [
 ['Movement ended without reaching the requested destination; inspect current position','no_effect'],
 ['Server did not confirm block removal','settled_partial_gather'],
 ['Movement stalled without position progress','settled_partial_gather']
])test('legacy gather review preserves unknown effects and partial-harvest distinction '+error+' '+outcome,t=>{
 const {h,input,observation}=fixture(t);
 for(const e of h.data.events.filter(e=>e.action_id==='partial')){e.action='gather';e.arguments={block:'wheat',count:1,targets:[{x:1,y:64,z:0}]};if(e.kind==='action_failed')e.error=error;}
 input.reviews[1].outcome=outcome;input.reviews[1].receipt_sha256=digest(h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_failed'));
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation));assert.equal(JSON.stringify(h.data),before);
});
for(const mode of ['confirmed','unknown','prefix','later_missing','later_earlier','timeout','no_effect'])test('historical partial build review '+mode,t=>{
 const {h,input,observation}=fixture(t),args={item:'cobblestone',blocks:[{x:1,y:64,z:1},{x:2,y:64,z:1}]};
 for(const e of h.data.events.filter(e=>e.action_id==='partial')){e.action='build';e.arguments=args;if(e.kind==='action_failed'){e.kind='action_result';delete e.error;e.result={placed:[{position:args.blocks[0],actual:'cobblestone',verified:true}],failed_at:args.blocks[1],error:'Server refused to place cobblestone at (2, 64, 1): the block is still air'};}}
 const end=h.data.events.find(e=>e.action_id==='partial'&&e.kind==='action_result');
 const later={id:'later',kind:'action_result',action:'place',time:'2026-11-11T01:00:03Z',arguments:{...args.blocks[1],item:'cobblestone'},result:{position:args.blocks[1],actual:'cobblestone',verified:true}};
 if(mode!=='later_missing')h.data.events.push(later);
 if(mode==='later_earlier')later.time='2026-11-11T01:00:00Z';
 if(mode==='unknown')end.result.error='Server did not answer';
 if(mode==='prefix')end.result.placed[0].verified=false;
 if(mode==='timeout')end.timeout=true;
 input.reviews[1].outcome=mode==='no_effect'?'no_effect':'settled_partial_build';input.reviews[1].receipt_sha256=digest(end);
 const before=structuredClone(h.data);
 if(mode==='confirmed'){assert.equal(review(h,cfg,input,observation).activity_allowed,true);assert.equal(policy.canContinue(h,cfg),false);assert.deepEqual(h.data.events,before.events);assert.deepEqual(h.data.task,before.task);assert.equal(policy.allowed(new WorkshopState(h.file),cfg),true);}
 else{assert.throws(()=>review(h,cfg,input,observation));assert.deepEqual(h.data,before);}
});
