const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {review}=require('../activity-review.cjs'),policy=require('../activity-policy.cjs');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
function fixture(){
 const blocks=Array.from({length:6},(_,x)=>({x,y:64,z:0})),args={item:'diorite',support_face:'up',blocks};
 const start={kind:'action_started',action_id:'original',action:'build',arguments:args,time:'2026-11-17T14:09:03Z'};
 const end={...start,kind:'action_result',time:'2026-11-17T14:09:06Z',result:{placed:blocks.slice(0,4).map(position=>({position,actual:'diorite',verified:true})),failed_at:blocks[4],error:'Target is not empty'}};
 const h={data:{task:{id:'original-task',status:'review',turns:7,deadline:1},turn:null,last_turn:{activity:true,task_id:null,interrupted:false,started_at:'2026-11-17T14:07:14Z',actions:[{id:'original',status:'uncertain'}]},events:[start,end]},save(){}};
 const observation={position:{x:2.5,y:64,z:.5},inventory:{cursor:null,slots:[null]}};
 const input={generation:1,request_id:crypto.randomUUID(),expected_turn_sha256:hash(h.data.last_turn),expected_position:observation.position,expected_inventory_sha256:hash(observation.inventory),evidence_sha256:'b'.repeat(64),reviews:[{action_id:'original',receipt_sha256:hash(end),outcome:'settled_partial_build',reason:'Exact source and terminal: four verified placements followed by synchronous target refusal; preserve prefix and do not replay.'}]};
 return {h,start,end,input,observation,cfg:{human_engagement:{enabled:true,task_optional:true}}};
}
test('owner review retains a verified partial build and permits only fresh work',()=>{
 const f=fixture(),before=structuredClone(f.h.data);
 assert.equal(policy.reason(f.h,f.cfg),'unresolved_activity_effects');
 const result=review(f.h,f.cfg,f.input,f.observation);
 assert.equal(result.activity_allowed,true);assert.equal(result.replayed,false);assert.equal(result.future_work_only,true);
 assert.equal(f.h.data.last_turn.actions[0].status,'uncertain');assert.deepEqual(f.h.data.events,before.events);assert.deepEqual(f.h.data.task,before.task);
 assert.equal(policy.canContinue(f.h,f.cfg),false);
 f.h.data=JSON.parse(JSON.stringify(f.h.data));assert.equal(review(f.h,f.cfg,f.input,f.observation).duplicate,true);
 f.h.data.activity_stop={at:1};assert.equal(policy.reason(f.h,f.cfg),'explicit_stop');
});
for(const mode of ['no_effect','pending','timeout','unsettled','wrong_target','wrong_prefix','unverified','wrong_item','preparation_race','unknown_error','invalid_coordinate','empty_prefix','all_placed'])test('partial build owner review refuses '+mode,()=>{
 const f=fixture(),r=f.end.result;
 if(mode==='no_effect')f.input.reviews[0].outcome='no_effect';
 if(mode==='pending')f.h.data.last_turn.actions[0].status='pending';
 if(mode==='timeout')f.end.timeout=true;
 if(mode==='unsettled')r.operation_settled=false;
 if(mode==='wrong_target')r.failed_at={x:5,y:64,z:0};
 if(mode==='wrong_prefix')r.placed[1].position={x:9,y:64,z:0};
 if(mode==='unverified')delete r.placed[2].verified;
 if(mode==='wrong_item')r.placed[2].actual='granite';
 if(mode==='preparation_race')r.error='Placement target changed during preparation; inspect before retrying';
 if(mode==='unknown_error')r.error='Connection ended';
 if(mode==='invalid_coordinate')f.start.arguments.blocks[5].x=1.5;
 if(mode==='empty_prefix'){r.placed=[];r.failed_at=f.start.arguments.blocks[0];}
 if(mode==='all_placed')r.placed=f.start.arguments.blocks.map(position=>({position,actual:'diorite',verified:true}));
 f.input.expected_turn_sha256=hash(f.h.data.last_turn);f.input.reviews[0].receipt_sha256=hash(f.end);
 const before=JSON.stringify(f.h.data);assert.throws(()=>review(f.h,f.cfg,f.input,f.observation));assert.equal(JSON.stringify(f.h.data),before);
});
