const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const {TaskIntake,digest}=require('../task-intake.cjs');
const {ChatProvenance}=require('../chat-provenance.cjs');
function fixture(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'task-intake-')),file=path.join(dir,'state.json');
 const cfg={incoming_chat_only:true,task_max_turns:12,task_max_seconds:2400,human_task_intake:{enabled:true,max_turns:135,max_seconds:10800}};
 const h=new WorkshopState(file),intake=new TaskIntake(h,cfg);
 function human(message='Please build a shop.',username='AnyVisitor',overrides={}){
  const e=h.record({time:new Date().toISOString(),kind:'chat',source:'human',username,message,accepted:true,whisper:false,provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',username,uuid:'00000000-0000-0000-0000-000000000001'},...overrides});
  h.data.turn={conversation_only:true,request_ids:[e.id],actions:[],may_mutate:false};h.save();return e;
 }
 return {h,cfg,intake,human,file,close(){fs.rmSync(dir,{recursive:true,force:true});}};
}
test('any verified human can accept once without effects or spent turn; greeting alone creates no task',()=>{
 const f=fixture();try{const e=f.human('Hello!');assert.equal(f.h.task(),null);const request=f.human();const args={request_id:request.id,goal:'Build a shop'};const result=f.intake.accept(args);assert.equal(result.turns,0);assert.equal(result.max_turns,12);assert.equal(result.execution_started,false);assert.equal(f.h.data.turn.may_mutate,false);assert.equal(f.h.task().requested_by,'AnyVisitor');assert.deepEqual(f.intake.accept(args),{...result,duplicate:true,current_status:'running'});assert.equal(f.h.data.task_authorizations.length,1);assert.notEqual(e.id,request.id);}finally{f.close();}
});
test('durable acceptance survives a lost response/reload without a second task',()=>{
 const f=fixture();try{const e=f.human();const args={request_id:e.id,goal:'shop'};const first=f.intake.accept(args);const h=new WorkshopState(f.file),intake=new TaskIntake(h,f.cfg);assert.equal(intake.accept(args).task_id,first.task_id);assert.equal(h.data.task_authorizations.length,1);assert.equal(h.task().turns,0);assert.throws(()=>intake.accept({...args,goal:'different'}),/different transition/);}finally{f.close();}
});
test('parsed labels, peer text, whispers, future/stale and unbound sources cannot grant work',()=>{
 for(const change of [{transport:null},{source:'agent'},{whisper:true},{provenance:'operator_control'},{time:new Date(Date.now()+60000).toISOString()},{time:new Date(Date.now()-700000).toISOString()}]){
  const f=fixture();try{const e=f.human('build','Visitor',change);assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop'}));assert.equal(f.h.task(),null);}finally{f.close();}
 }
 const f=fixture();try{const e=f.human();f.h.data.turn.request_ids=[];assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop'}));}finally{f.close();}
});
test('transport attribution requires matching server UUID/name and cannot be forged by display text',()=>{
 const p=new ChatProvenance(),m={},players={Human:{uuid:'00000000-0000-0000-0000-000000000001'},Scribe:{uuid:'00000000-0000-0000-0000-000000000002'}};
 p.observe(m,'chat',players.Scribe.uuid,false,players);assert.equal(p.get('Human',m),null);assert.equal(p.get('Scribe',m).signature_verified,false);assert.equal(p.get('Scribe',{}),null);
 const system={};p.observe(system,'system',players.Human.uuid,true,players);assert.equal(p.get('Human',system),null);
});
test('mode flip does not revive expired or stopped legacy assignments',()=>{
 for(const status of ['budget_exhausted','stopped','running']){const f=fixture();try{f.h.data.task={id:'old',status,deadline:Date.now()+600000,turns:4,max_turns:10};const copy=JSON.stringify(f.h.task());assert.equal(f.intake.runnable(),false);assert.equal(JSON.stringify(f.h.task()),copy);}finally{f.close();}}
});
test('fresh acceptance archives an expired task without modifying its evidence',()=>{
 const f=fixture();try{const old={id:'expired',status:'budget_exhausted',turns:120,max_turns:135,deadline:1,unknown_receipts:['unknown']};f.h.data.task=old;const e=f.human();f.intake.accept({request_id:e.id,goal:'new'});assert.deepEqual(f.h.data.task_history[0],old);assert.notEqual(f.h.task().id,old.id);}finally{f.close();}
});
test('amendment is source bound, revision checked and cumulative; any human can request it',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});const t=f.h.task();t.turns=7;const request=f.human('Continue longer','OtherHuman');const args={request_id:request.id,task_id:t.id,expected_revision:1,max_turns:30,deadline:Date.now()+3600000};const r=f.intake.amend(args);assert.equal(r.turns,7);assert.equal(r.authority_revision,2);assert.equal(f.h.task().authority.source.username,'AnyVisitor');assert.equal(f.h.data.task_authorizations.at(-1).source.username,'OtherHuman');assert.equal(f.intake.amend(args).duplicate,true);assert.equal(f.h.data.task_authorizations.length,2);const e2=f.human();assert.throws(()=>f.intake.amend({...args,request_id:e2.id}),/authority changed/);}finally{f.close();}
});
test('ceilings and spent counts cannot be reset; stopped/unknown work cannot be reopened',()=>{
 const f=fixture();try{const e=f.human();assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop',max_turns:136}));f.intake.accept({request_id:e.id,goal:'shop'});const t=f.h.task();t.turns=8;const next=f.human();const args={request_id:next.id,task_id:t.id,expected_revision:1};const checkedAt=Date.now();f.intake.now=()=>checkedAt;for(const a of [{max_turns:-1},{max_turns:136},{deadline:checkedAt+10800001},{deadline:0}])assert.throws(()=>f.intake.amend({...args,...a}));for(const status of ['stopped','needs_review']){t.status=status;assert.throws(()=>f.intake.amend({...args,max_turns:30,resume:true}));}assert.equal(t.turns,8);assert.equal(t.authority_revision,1);}finally{f.close();}
});
test('expiry needs an explicit resume amendment, not a policy change',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});const t=f.h.task();t.deadline=1;assert.equal(f.intake.runnable(),false);const next=f.human('Please continue another hour');const args={request_id:next.id,task_id:t.id,expected_revision:1,max_turns:20,deadline:Date.now()+3600000};assert.throws(()=>f.intake.amend(args),/explicit/);f.intake.amend({...args,resume:true});assert.equal(f.intake.runnable(),true);}finally{f.close();}
});
test('full current final turn remains authorized but no next turn is eligible',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop',max_turns:1});f.h.finish();f.h.startTurn();assert.equal(f.intake.runnable(),true);f.h.finish();assert.equal(f.intake.runnable(),false);}finally{f.close();}
});
test('reviewed retained source keeps original text and explicit evidence origin, never invents transport proof',()=>{
 const f=fixture();try{const e=f.human('Please build the supermarket','Visitor',{transport:null,time:new Date(Date.now()-3600000).toISOString()});f.h.finish();assert.throws(()=>f.intake.reviewSource({request_id:e.id,expected_source_hash:'wrong',reason:'Human request independently reviewed'}));const r=f.intake.reviewSource({request_id:e.id,expected_source_hash:digest(e),reason:'Human request independently reviewed'});assert.equal(r.source.message,e.message);assert.throws(()=>f.intake.reviewSource({request_id:e.id,expected_source_hash:digest(e),reason:'Repeat review'}));f.human('Are you ready?');const result=f.intake.accept({request_id:e.id,goal:'stocked supermarket'});assert.equal(result.accepted,true);assert.equal(f.h.task().authority.source.evidence_origin,'authenticated_operator_review');assert.equal(f.h.task().authority.source.transport,null);assert.deepEqual(f.intake.capabilities().reviewed_requests,[]);}finally{f.close();}
});
test('configured mode and temporary reply reserve have distinct capabilities; no hidden delegation',()=>{
 const f=fixture();try{f.cfg.human_task_intake.enabled=false;assert.equal(f.intake.capabilities().blocked_reason,'installation_chat_only');f.cfg.incoming_chat_only=false;f.human();assert.equal(f.intake.capabilities().blocked_reason,'reply_turn_no_world_effects');assert.equal(f.intake.capabilities().can_delegate_execution,false);f.cfg.human_task_intake.enabled=true;assert.equal(f.intake.capabilities().can_accept,true);}finally{f.close();}
});
test('failed persistence cannot leave newly accepted authority live in memory',()=>{
 const f=fixture();try{const e=f.human(),before=JSON.stringify(f.h.data);f.h.save=()=>{throw Error('disk failed');};assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop'}),/disk failed/);assert.equal(JSON.stringify(f.h.data),before);assert.equal(f.intake.runnable(),false);}finally{f.close();}
});
test('Stop invalidates unused retained source; duplicate receipts do not claim resumed execution',()=>{
 const f=fixture();try{const e=f.human();f.h.finish();f.intake.reviewSource({request_id:e.id,expected_source_hash:digest(e),reason:'Explicit reviewed human request'});f.intake.revokeSources();assert.deepEqual(f.intake.capabilities().reviewed_requests,[]);f.human('Hello');assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop'}),/public human/);}finally{f.close();}
});
test('equivalent argument key order is idempotent',()=>{
 const f=fixture();try{const e=f.human();const first=f.intake.accept({request_id:e.id,goal:'shop'});const repeat=f.intake.accept({goal:'shop',request_id:e.id});assert.equal(repeat.task_id,first.task_id);assert.equal(repeat.duplicate,true);}finally{f.close();}
});

test('expiry cannot hide an unresolved turn to permit amendment or replacement',()=>{
 const f=fixture();try{
  const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});f.h.finish();f.h.startTurn();f.h.actionStarted('uncertain-effect');f.h.finish(true);
  const task=f.h.task();task.deadline=1;assert.equal(f.h.task().status,'budget_exhausted');
  const next=f.human('Please continue');assert.equal(f.intake.capabilities().can_amend,false);assert.equal(f.intake.capabilities().can_accept,false);assert.equal(f.intake.capabilities().work_blocked_reason,'unresolved_interruption');
  assert.throws(()=>f.intake.amend({request_id:next.id,task_id:task.id,expected_revision:1,deadline:Date.now()+3600000,resume:true}),/effects review/);
  assert.throws(()=>f.intake.accept({request_id:next.id,goal:'replacement'}),/effects review/);assert.equal(f.h.task().id,task.id);
 }finally{f.close();}
});

test('human reductions close exhausted work without resetting consumed counts or needing resume',()=>{
 for(const reduction of [{max_turns:3},{max_turns:7},{max_turns:0},{deadline:1}]){
  const f=fixture();try{
   const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});const original=f.h.task();original.turns=7;
   const next=f.human('Reduce the allowance','AnotherHuman');const args={request_id:next.id,task_id:original.id,expected_revision:1,...reduction};
   const result=f.intake.amend(args);assert.equal(result.turns,7);assert.equal(result.status,'budget_exhausted');assert.equal(f.intake.runnable(),false);assert.equal(f.h.task().id,original.id);assert.equal(f.h.task().authority.source.id,e.id);
   const capabilities=f.intake.capabilities();assert.equal(capabilities.assignment.consumed_turns,7);assert.equal(capabilities.assignment.remaining_turns,Math.max(0,result.max_turns-7));assert.equal(capabilities.capacity.provider_remaining,null);
   assert.equal(f.intake.amend(args).duplicate,true);assert.equal(f.h.data.task_authorizations.length,2);
   assert.deepEqual(f.h.data.task_authorizations.at(-1).previous,{status:'running',max_turns:12,deadline:original.deadline,turns:7,authority_revision:1});
  }finally{f.close();}
 }
});
test('an exhausted reduction wins over resume and never opens world authority',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});const task=f.h.task();task.turns=5;const next=f.human();f.intake.amend({request_id:next.id,task_id:task.id,expected_revision:1,max_turns:0,resume:true});assert.equal(f.intake.runnable(),false);assert.equal(f.h.task().status,'budget_exhausted');}finally{f.close();}
});
test('source receipt has immutable source revision, original actor/time and explicit public audience',()=>{
 const f=fixture();try{const e=f.human();const before=f.intake.source(e.id);e.routing_debug='context changed';const after=f.intake.source(e.id);assert.equal(before.revision,after.revision);assert.notEqual(before.source_hash,after.source_hash);assert.equal(after.time,e.time);assert.equal(after.actor.server_player_uuid,e.transport.uuid);assert.deepEqual(after.audience,{kind:'public',experience:'minecraft'});f.intake.accept({request_id:e.id,goal:'shop'});assert.equal(f.h.task().authority.source.revision,before.revision);}finally{f.close();}
});

test('reported reply pacing uses the same validated limit as admission',()=>{
 const f=fixture();try{assert.equal(f.intake.capabilities().capacity.reply_turns_per_hour,12);f.cfg.human_reply_turns_per_hour=61;assert.equal(f.intake.capabilities().capacity.reply_turns_per_hour,0);f.cfg.human_reply_turns_per_hour=4;assert.equal(f.intake.capabilities().capacity.reply_turns_per_hour,4);}finally{f.close();}
});

for (const [label, restriction] of [['lower cumulative cap', {max_turns:7}], ['elapsed deadline', {deadline:1}]]) {
 test(`${label} survives lost acknowledgment and restart without reviving larger authority`,()=>{
  const f=fixture();try{
   const original=f.human();const acceptance={request_id:original.id,goal:'shop'};
   f.intake.accept(acceptance);const task=f.h.task();task.turns=8;
   task.unknown_receipts=[{id:'historical-unknown',state:'unknown'}];
   const source=f.human('Reduce the allowance now','AnotherHuman');
   const args={request_id:source.id,task_id:task.id,expected_revision:1,...restriction};
   // Persist the amendment, then discard its reply and crash before /finish.
   f.intake.amend(args);
   const stored=JSON.parse(fs.readFileSync(f.file,'utf8'));
   assert.equal(stored.task.status,'budget_exhausted');
   assert.equal(stored.turn.conversation_only,true);
   const h=new WorkshopState(f.file),intake=new TaskIntake(h,f.cfg);
   assert.equal(h.data.turn,null);assert.equal(h.data.last_conversation_turn.interrupted,true);
   assert.deepEqual(h.task(),stored.task);assert.equal(h.task().turns,8);
   assert.equal(h.task().authority_revision,2);
   assert.equal(intake.capabilities().autonomous_work_allowed,false);
   assert.deepEqual(h.task().unknown_receipts,[{id:'historical-unknown',state:'unknown'}]);
   assert.deepEqual(h.task().authority.source,task.authority.source);
   const before=fs.readFileSync(f.file,'utf8');
   const retry=intake.amend(args);
   assert.equal(retry.duplicate,true);assert.equal(retry.current_status,'budget_exhausted');
   assert.equal(retry.turns,8);assert.equal(retry.execution_started,false);
   assert.equal(intake.accept(acceptance).current_status,'budget_exhausted');
   assert.throws(()=>intake.amend({...args,max_turns:12,deadline:Date.now()+600000,resume:true}),/different transition/);
   assert.equal(fs.readFileSync(f.file,'utf8'),before);
   const again=new WorkshopState(f.file);
   assert.deepEqual(again.task(),stored.task);assert.equal(again.data.task_authorizations.length,2);
   assert.equal(new TaskIntake(again,f.cfg).runnable(),false);
  }finally{f.close();}
 });
}

test('authenticated local operator source accepts with its own provenance, not a fabricated player UUID',()=>{
 const f=fixture();try{
  const e=f.human('Inspect a safe route only','Operator',{provenance:'operator_control',transport:{kind:'authenticated_operator_control'}});
  const a={request_id:e.id,goal:'Inspect safe route',max_turns:3,seconds:300};
  const r=f.intake.accept(a);assert.equal(r.accepted,true);assert.equal(f.h.data.turn.may_mutate,false);
  const source=f.h.task().authority.source;assert.equal(source.evidence_origin,'authenticated_operator_control');assert.equal(source.actor.server_player_uuid,null);assert.equal(source.audience.kind,'private');
  const reloaded=new TaskIntake(new WorkshopState(f.file),f.cfg);assert.equal(reloaded.accept(a).task_id,r.task_id);assert.equal(reloaded.accept(a).duplicate,true);
 }finally{f.close();}
});
test('stale or unbound operator controls and matching text on another transport never grant new authority',()=>{
 for(const changes of [{time:new Date(Date.now()-700000).toISOString()},{transport:{kind:'server_player_uuid'}},{transport:null}]){
  const f=fixture();try{const e=f.human('Build','Operator',{provenance:'operator_control',transport:{kind:'authenticated_operator_control'},...changes});assert.throws(()=>f.intake.accept({request_id:e.id,goal:'Build'}));assert.equal(f.h.task(),null);}finally{f.close();}
 }
 const f=fixture();try{const e=f.human('Build','Operator',{provenance:'operator_control',transport:{kind:'authenticated_operator_control'}});f.h.data.turn.request_ids=[];assert.throws(()=>f.intake.accept({request_id:e.id,goal:'Build'}));}finally{f.close();}
});

test('authenticated operator can resume the same waiting task with durable source and lost-ack idempotence',()=>{
 const f=fixture();try{
  const initial=f.human();f.intake.accept({request_id:initial.id,goal:'shop'});
  Object.assign(f.h.task(),{status:'waiting',turns:4,wait_for:'adapter repair',recovery_attempts:1,unknown_receipts:['retain']});
  const before=structuredClone(f.h.task());
  const e=f.human('Repair installed; continue existing work','Operator',{provenance:'operator_control',transport:{kind:'authenticated_operator_control'}});
  const args={task_id:before.id,expected_revision:before.authority_revision,request_id:e.id,reason:'The reported adapter defect is repaired; inspect and continue existing work'};
  const result=f.intake.resume(args);assert.equal(result.execution_started,false);assert.equal(result.status,'running');
  for(const key of ['id','turns','max_turns','deadline','authority','authority_revision','recovery_attempts','unknown_receipts'])assert.deepEqual(f.h.task()[key],before[key]);
  assert.deepEqual(f.h.data.work_resumptions[0].source,e);assert.equal(f.h.data.work_resumptions[0].source.transport.uuid,undefined);
  const h=new WorkshopState(f.file),intake=new TaskIntake(h,f.cfg),unchanged=JSON.stringify(h.data);
  assert.equal(intake.resume(args).duplicate,true);assert.equal(JSON.stringify(h.data),unchanged);
  h.data.task.status='stopped';h.save();assert.equal(intake.resume(args).current_status,'stopped');assert.equal(h.task().status,'stopped');
 }finally{f.close();}
});
test('operator resume does not accept forged, stale, future, private-player, unbound or Stop-fenced evidence',()=>{
 const cases=[{transport:null},{source:'agent'},{whisper:true},{accepted:false},{time:new Date(Date.now()-700000).toISOString()},{time:new Date(Date.now()+60000).toISOString()},{unbound:true},{cutoff:true}];
 for(const change of cases){const f=fixture();try{
  const initial=f.human();f.intake.accept({request_id:initial.id,goal:'shop'});f.h.task().status='waiting';
  const e=f.human('continue','Operator',{provenance:'operator_control',transport:{kind:'authenticated_operator_control'},...change});
  if(change.unbound)f.h.data.turn.request_ids=[];if(change.cutoff)f.h.data.task_source_cutoff=Date.now()+1;
  const before=JSON.stringify(f.h.data);assert.throws(()=>f.intake.resume({task_id:f.h.task().id,expected_revision:1,request_id:e.id,reason:'continue'}));assert.equal(JSON.stringify(f.h.data),before);
 }finally{f.close();}}
});
test('operator resume retains original bounds, revision and interrupted-task refusal',()=>{
 for(const change of [{deadline:1},{turns:12},{status:'stopped'},{status:'needs_review'},{authority_revision:2}]){
  const f=fixture();try{
   const initial=f.human();f.intake.accept({request_id:initial.id,goal:'shop'});Object.assign(f.h.task(),{status:'waiting'},change);
   const e=f.human('continue','Operator',{provenance:'operator_control',transport:{kind:'authenticated_operator_control'}}),task_id=f.h.task().id,before=JSON.stringify(f.h.data);
   assert.throws(()=>f.intake.resume({task_id,expected_revision:1,request_id:e.id,reason:'continue'}));assert.equal(JSON.stringify(f.h.data),before);
  }finally{f.close();}
 }
});

test('scoped installation input retains caller-asserted human and original audience in durable task source',()=>{
 const f=fixture();try{
  const inputs=require('../installation-inputs.cjs'),caller={id:'fixture-voice',label:'Fixture voice',token:'v'.repeat(40)},source={version:1,request_id:'2cb10552-052d-44c2-a54b-8c00ae106693',call_id:'call1',intent_id:'intent1',revision:'1',occurred_at:new Date().toISOString(),actor:{id:'external-person',label:'Fixture human'},audience:{kind:'private',experience:'voice',id:'audience1'}};
  const queued=inputs.enqueue(f.h,caller,{text:'Original request',source});f.h.data.turn={conversation_only:true,request_ids:[queued.receipt.request_id],actions:[],may_mutate:false};
  f.intake.accept({request_id:queued.receipt.request_id,goal:'Requested work'});const saved=f.h.task().authority.source;
  assert.equal(saved.actor.name,'Fixture human');assert.equal(saved.actor.identity_asserted_by,caller.id);assert.equal(saved.actor.server_player_uuid,null);assert.deepEqual(saved.audience,source.audience);assert.deepEqual(saved.installation_source,{caller:{id:caller.id,label:caller.label},...source});assert.equal(saved.message,'Original request');assert.equal(saved.transport.kind,'authenticated_operator_control');
 }finally{f.close();}
});
