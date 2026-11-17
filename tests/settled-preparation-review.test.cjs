const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {review}=require('../activity-review.cjs'),policy=require('../activity-policy.cjs');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
function fixture(kind){
 const storage=kind==='container',args=storage?{x:1,y:64,z:1,expected:'chest',operation:'deposit',item:'stone',count:5,contents_revision:'a'.repeat(64)}:{x:1,y:64,z:1,item:'cobblestone',support_face:'up'};
 const terminal={kind:'action_failed',action_id:'original',action:kind,arguments:args,time:'2026-11-17T03:00:01Z',error:storage?'Container contents changed since inspection; reconsider the handoff. No items transferred.':'Movement ended without reaching the requested destination; inspect current position',...(!storage?{repair:{code:'arrival_mismatch'}}:{})};
 const h={data:{task:{id:'original-task',status:'review',turns:7,deadline:1},turn:null,last_turn:{activity:true,task_id:null,interrupted:false,started_at:'2026-11-17T03:00:00Z',actions:[{id:'original',status:'uncertain'}]},events:[{...terminal,kind:'action_started'},terminal]},save(){}};
 delete h.data.events[0].error;delete h.data.events[0].repair;
 const observation={position:{x:.5,y:64,z:.5},inventory:{cursor:null,slots:[null]}};
 const input={generation:1,request_id:crypto.randomUUID(),expected_turn_sha256:hash(h.data.last_turn),expected_position:observation.position,expected_inventory_sha256:hash(observation.inventory),evidence_sha256:'b'.repeat(64),reviews:[{action_id:'original',receipt_sha256:hash(terminal),outcome:storage?'settled_failed_storage':'settled_failed_placement',reason:'Exact source/terminal and fresh owner observation; historical preparation effects are retained, no replay.'}]};
 return {h,observation,input,terminal,cfg:{human_engagement:{enabled:true,task_optional:true}}};
}
for(const kind of ['container','place']){
 test(kind+' exact owner review permits fresh work while retaining original records',()=>{
  const f=fixture(kind),before=structuredClone(f.h.data);
  assert.equal(policy.reason(f.h,f.cfg),'unresolved_activity_effects');
  const result=review(f.h,f.cfg,f.input,f.observation);assert.equal(result.activity_allowed,true);assert.equal(result.replayed,false);
  assert.equal(f.h.data.last_turn.actions[0].status,'uncertain');assert.deepEqual(f.h.data.events,before.events);assert.deepEqual(f.h.data.task,before.task);assert.equal(policy.canContinue(f.h,f.cfg),false);
  assert.equal(review(f.h,f.cfg,f.input,f.observation).duplicate,true);
  f.h.data.activity_stop={at:1};assert.equal(policy.reason(f.h,f.cfg),'explicit_stop');
 });
 for(const mode of ['no_effect','pending','timeout','unsettled','wrong_error','missing_evidence','occupied_cursor'])test(kind+' preserves refusal for '+mode,()=>{
  const f=fixture(kind);
  if(mode==='no_effect')f.input.reviews[0].outcome='no_effect';
  if(mode==='pending')f.h.data.last_turn.actions[0].status='pending';
  if(mode==='timeout')f.terminal.timeout=true;
  if(mode==='unsettled')f.terminal.operation_settled=false;
  if(mode==='wrong_error')f.terminal.error='Connection ended';
  if(mode==='missing_evidence'){if(kind==='place')delete f.terminal.repair;else{delete f.terminal.arguments.contents_revision;}}
  if(mode==='occupied_cursor'){f.observation.inventory.cursor={name:'stone',count:1};}
  f.input.expected_turn_sha256=hash(f.h.data.last_turn);f.input.expected_inventory_sha256=hash(f.observation.inventory);f.input.reviews[0].receipt_sha256=hash(f.terminal);
  const before=JSON.stringify(f.h.data);assert.throws(()=>review(f.h,f.cfg,f.input,f.observation));assert.equal(JSON.stringify(f.h.data),before);
 });
}
