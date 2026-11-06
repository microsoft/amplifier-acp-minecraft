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
 const f=fixture();try{const e=f.human();assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop',max_turns:136}));f.intake.accept({request_id:e.id,goal:'shop'});const t=f.h.task();t.turns=8;const next=f.human();const args={request_id:next.id,task_id:t.id,expected_revision:1};for(const a of [{max_turns:7},{max_turns:136},{deadline:Date.now()+10800001},{deadline:1}])assert.throws(()=>f.intake.amend({...args,...a}));for(const status of ['stopped','needs_review']){t.status=status;assert.throws(()=>f.intake.amend({...args,max_turns:30,resume:true}));}assert.equal(t.turns,8);assert.equal(t.authority_revision,1);}finally{f.close();}
});
test('expiry needs an explicit resume amendment, not a policy change',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});const t=f.h.task();t.deadline=1;assert.equal(f.intake.runnable(),false);const next=f.human('Please continue another hour');const args={request_id:next.id,task_id:t.id,expected_revision:1,max_turns:20,deadline:Date.now()+3600000};assert.throws(()=>f.intake.amend(args),/explicit/);f.intake.amend({...args,resume:true});assert.equal(f.intake.runnable(),true);}finally{f.close();}
});
test('full current final turn remains authorized but no next turn is eligible',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop',max_turns:1});f.h.finish();f.h.startTurn();assert.equal(f.intake.runnable(),true);f.h.finish();assert.equal(f.intake.runnable(),false);}finally{f.close();}
});
test('reviewed retained source keeps original text and explicit evidence origin, never invents transport proof',()=>{
 const f=fixture();try{const e=f.human('Please build the supermarket','Visitor',{transport:null,time:new Date(Date.now()-3600000).toISOString()});f.h.finish();assert.throws(()=>f.intake.reviewSource({request_id:e.id,expected_source_hash:'wrong',reason:'Human request independently reviewed'}));const r=f.intake.reviewSource({request_id:e.id,expected_source_hash:digest(e),reason:'Human request independently reviewed'});assert.equal(r.source.message,e.message);assert.throws(()=>f.intake.reviewSource({request_id:e.id,expected_source_hash:digest(e),reason:'Repeat review'}));f.human('Are you ready?');const result=f.intake.accept({request_id:e.id,goal:'stocked supermarket'});assert.equal(result.accepted,true);assert.equal(f.h.task().authority.source.evidence_origin,'authenticated_operator_review');assert.equal(f.h.task().authority.source.transport,null);}finally{f.close();}
});
test('configured mode and temporary reply reserve have distinct capabilities; no hidden delegation',()=>{
 const f=fixture();try{f.cfg.human_task_intake.enabled=false;assert.equal(f.intake.capabilities().blocked_reason,'installation_chat_only');f.cfg.incoming_chat_only=false;f.human();assert.equal(f.intake.capabilities().blocked_reason,'reply_turn_no_world_effects');assert.equal(f.intake.capabilities().can_delegate_execution,false);f.cfg.human_task_intake.enabled=true;assert.equal(f.intake.capabilities().can_accept,true);}finally{f.close();}
});
test('failed persistence cannot leave newly accepted authority live in memory',()=>{
 const f=fixture();try{const e=f.human(),before=JSON.stringify(f.h.data);f.h.save=()=>{throw Error('disk failed');};assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop'}),/disk failed/);assert.equal(JSON.stringify(f.h.data),before);assert.equal(f.intake.runnable(),false);}finally{f.close();}
});
test('Stop invalidates unused retained source; duplicate receipts do not claim resumed execution',()=>{
 const f=fixture();try{const e=f.human();f.h.finish();f.intake.reviewSource({request_id:e.id,expected_source_hash:digest(e),reason:'Explicit reviewed human request'});f.intake.revokeSources();f.human('Hello');assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop'}),/public human/);}finally{f.close();}
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
