const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {review}=require('../activity-review.cjs'),policy=require('../activity-policy.cjs');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
function fixture(){
 const events=[],actions=[];
 for(let i=0;i<2;i++){
  const args={entity_id:42+i,uuid:'00000000-0000-4000-8000-000000000001',seconds:3};
  const start={kind:'action_started',action:'follow',action_id:'original-'+i,arguments:args,time:'2026-11-17T14:29:54.505Z'},end={...start,kind:'action_failed',time:'2026-11-17T14:29:54.517Z',error:'Target identity changed or is not visible; inspect entities again'};
  events.push(start,end);actions.push({id:start.action_id,status:'uncertain'});
 }
 const h={data:{task:{id:'original-task',status:'review',turns:8,deadline:1},turn:null,last_turn:{activity:true,task_id:null,interrupted:false,started_at:'2026-11-17T14:25:40Z',actions},events},save(){}};
 const observation={position:{x:1,y:64,z:1},inventory:{cursor:null,slots:[null]}},input={generation:1,request_id:crypto.randomUUID(),expected_turn_sha256:hash(h.data.last_turn),expected_position:observation.position,expected_inventory_sha256:hash(observation.inventory),evidence_sha256:'a'.repeat(64),reviews:actions.map((a,i)=>({action_id:a.id,receipt_sha256:hash(events[i*2+1]),outcome:'no_effect',reason:'Exact legacy initial identity refusal before setGoal. Preserve original receipts and allow only fresh work.'}))};
 return {h,input,observation,cfg:{human_engagement:{enabled:true,task_optional:true}},start:events[0],end:events[1]};
}
test('exact two-action legacy review preserves originals across duplicate/reload and Stop',()=>{
 const f=fixture(),before=structuredClone(f.h.data);assert.equal(policy.reason(f.h,f.cfg),'unresolved_activity_effects');
 const result=review(f.h,f.cfg,f.input,f.observation);assert.equal(result.activity_allowed,true);assert.equal(result.future_work_only,true);assert.equal(result.replayed,false);
 assert.deepEqual(f.h.data.events,before.events);assert.deepEqual(f.h.data.task,before.task);assert.ok(f.h.data.last_turn.actions.every(a=>a.status==='uncertain'));assert.equal(policy.canContinue(f.h,f.cfg),false);
 f.h.data=JSON.parse(JSON.stringify(f.h.data));assert.equal(review(f.h,f.cfg,f.input,f.observation).duplicate,true);
 f.h.data.activity_stop={at:1};assert.equal(policy.reason(f.h,f.cfg),'explicit_stop');
});
for(const mode of ['missing_review','wrong_receipt','pending','timeout','unsettled','after_start','transport','invalid_uuid','fractional_id','invalid_duration','ambiguous','extra_field','wrong_outcome','changed_inventory','changed_turn','interrupted','duplicate_terminal'])test('follow review refuses '+mode+' without mutation',()=>{
 const f=fixture();
 if(mode==='missing_review')f.input.reviews.pop();if(mode==='pending')f.h.data.last_turn.actions[1].status='pending';
 if(mode==='timeout')f.end.timeout=true;if(mode==='unsettled')f.end.operation_settled=false;
 if(mode==='after_start')f.end.error='Target is no longer loaded';if(mode==='transport')f.end.error='Connection ended';
 if(mode==='invalid_uuid')f.start.arguments.uuid='unknown';if(mode==='fractional_id')f.start.arguments.entity_id=1.5;
 if(mode==='invalid_duration')f.start.arguments.seconds=31;if(mode==='ambiguous')f.start.arguments.player='Friend';if(mode==='extra_field')f.start.arguments.extra=true;
 if(mode==='wrong_outcome')f.input.reviews[0].outcome='settled_failed_movement';
 if(mode==='changed_inventory')f.observation.inventory.cursor={name:'stone'};
 if(mode==='interrupted')f.h.data.last_turn.interrupted=true;if(mode==='duplicate_terminal')f.h.data.events.push({...f.end});
 f.input.expected_turn_sha256=hash(f.h.data.last_turn);f.input.reviews[0].receipt_sha256=hash(f.end);
 if(mode==='wrong_receipt')f.input.reviews[0].receipt_sha256='0'.repeat(64);if(mode==='changed_turn')f.input.expected_turn_sha256='0'.repeat(64);
 const before=JSON.stringify(f.h.data);assert.throws(()=>review(f.h,f.cfg,f.input,f.observation));assert.equal(JSON.stringify(f.h.data),before);
});

test('exact older named-player initial refusal is also read-only failure',()=>{
 const f=fixture();f.start.arguments={player:'Friend',seconds:3};f.end.arguments=f.start.arguments;f.input.reviews[0].receipt_sha256=hash(f.end);
 const before=JSON.stringify(f.h.data.events);assert.equal(review(f.h,f.cfg,f.input,f.observation).activity_allowed,true);assert.equal(JSON.stringify(f.h.data.events),before);
});
