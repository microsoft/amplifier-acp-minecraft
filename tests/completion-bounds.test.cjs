const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const bounds=require('../task-bounds.cjs');
const {WorkshopState}=require('../workshop-state.cjs');
const {TaskIntake}=require('../task-intake.cjs');
const {ActionLease}=require('../action-lease.cjs');
const helpers=require('../helper-capabilities.cjs');
const bridge=require('../watch-bridge.cjs');
function fixture(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'completion-bounds-')),file=path.join(dir,'workshop.json');
 const h=new WorkshopState(file),cfg={incoming_chat_only:true,human_task_intake:{enabled:true,default_bound_mode:'completion_bound',max_turns:135,max_seconds:10800}};
 const intake=new TaskIntake(h,cfg,{completionSupported:()=>true});
 function human(){const e=h.record({time:new Date().toISOString(),kind:'chat',source:'human',username:'Visitor',message:'Please finish the whole commission.',accepted:true,provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',username:'Visitor',uuid:'human-uuid'}});h.data.turn={conversation_only:true,request_ids:[e.id],actions:[],may_mutate:false};h.save();return e;}
 return {dir,file,h,cfg,intake,human,close(){fs.rmSync(dir,{recursive:true,force:true});}};
}
test('new completion-bound acceptance is durable, explicit, effect-free and does not convert old work',()=>{
 const f=fixture();try{
  const old={id:'old',status:'budget_exhausted',deadline:1,turns:120,max_turns:135,unknown_receipts:['unknown']};f.h.data.task=structuredClone(old);
  const e=f.human(),args={request_id:e.id,goal:'Complete commissioned shop'};
  const r=f.intake.accept(args),t=f.h.task();assert.equal(r.execution_started,false);assert.equal(t.turns,0);assert.equal(f.h.data.turn.may_mutate,false);
  assert.deepEqual(t.bounds,{version:1,deadline_ms:bounds.unbounded(),max_turns:bounds.unbounded()});assert.ok(!Object.hasOwn(t,'deadline'));assert.ok(!Object.hasOwn(t,'max_turns'));
  assert.deepEqual(f.h.data.task_history[0],old);
  const loaded=new WorkshopState(f.file),i=new TaskIntake(loaded,f.cfg,{completionSupported:()=>true});assert.equal(i.accept(args).duplicate,true);assert.equal(loaded.task().id,t.id);assert.equal(i.runnable(),true);
  assert.equal(i.capabilities().assignment.remaining_ms,null);assert.equal(i.capabilities().defaults.mode,'completion_bound');
 }finally{f.close();}
});
test('unsupported helpers block new completion-bound admission without changing sources or task state',()=>{
 const f=fixture();try{const e=f.human(),i=new TaskIntake(f.h,f.cfg);const before=JSON.stringify(f.h.data);assert.equal(i.capabilities().can_accept,false);assert.equal(i.capabilities().blocked_reason,'completion_bound_helpers_unavailable');assert.throws(()=>i.accept({request_id:e.id,goal:'shop'}),/discovered/);assert.equal(JSON.stringify(f.h.data),before);}finally{f.close();}
});
test('explicit finite dimensions remain binding inside a completion-bound default',()=>{
 for(const limits of [{max_turns:1},{seconds:300},{max_turns:1,seconds:300}]){
  const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop',...limits});const t=f.h.task();
   assert.equal(t.bounds.max_turns.kind,limits.max_turns?'finite':'no_configured_bound');assert.equal(t.bounds.deadline_ms.kind,limits.seconds?'finite':'no_configured_bound');
   f.h.finish();f.h.startTurn();assert.equal(f.intake.runnable(),true);f.h.finish(false,true);
   if(limits.max_turns)assert.equal(f.h.task().status,'budget_exhausted');
   else assert.equal(f.h.task().status,'running');
  }finally{f.close();}
 }
});
test('unknown, null and contradictory bounds never grant work or become unlimited',()=>{
 for(const change of [t=>delete t.bounds,t=>t.bounds=null,t=>delete t.bounds.max_turns,t=>t.bounds.deadline_ms={kind:'unknown'},t=>t.bounds.max_turns={kind:'no_configured_bound',value:999},t=>t.deadline=null,t=>t.max_turns=999,t=>t.turns=null]){
  const t=bounds.set({turns:0},bounds.unbounded(),bounds.unbounded());change(t);assert.equal(bounds.within(t),false);assert.throws(()=>bounds.get(t));
 }
 for(const values of [{max_turns:null},{seconds:null},{max_turns:0}]){const f=fixture();try{const e=f.human();assert.throws(()=>f.intake.accept({request_id:e.id,goal:'shop',...values}));assert.equal(f.h.task(),null);}finally{f.close();}}
});
test('completion-bound leases renew for hours without assignment renewal, and Stop or bound amendment revokes them',()=>{
 let now=1000;const task=bounds.set({id:'same',status:'running',turns:1,authority_revision:1},bounds.unbounded(),bounds.unbounded()),turn={task_id:'same'},lease=new ActionLease({now:()=>now});
 lease.begin(turn,task,true);const original=JSON.stringify(task),r={lease_id:lease.id,task_id:task.id};
 for(let n=0;n<300;n++){now+=30000;const v=lease.renew(r,task,turn);assert.equal(v.expires_at,now+240000);assert.equal(v.assignment_deadline,null);}assert.equal(JSON.stringify(task),original);
 task.status='stopped';assert.throws(()=>lease.renew(r,task,turn));task.status='running';task.authority_revision++;assert.throws(()=>lease.renew(r,task,turn));
});
test('restrictive amendments survive lost replies/reload and keep spent counts, uncertainty and untouched dimension',()=>{
 for(const restriction of [{max_turns:7},{max_turns:0},{deadline:1}])for(const resume of [false,true]){
  const f=fixture();try{const first=f.human();f.intake.accept({request_id:first.id,goal:'shop'});const original=f.h.task();original.turns=8;original.recovery_attempts=2;original.unknown_receipts=['unknown'];
   const next=f.human(),args={request_id:next.id,task_id:original.id,expected_revision:1,...restriction,resume};f.intake.amend(args);
   const h=new WorkshopState(f.file),i=new TaskIntake(h,f.cfg,{completionSupported:()=>true});assert.equal(i.amend(args).duplicate,true);assert.equal(h.task().status,'budget_exhausted');assert.equal(h.task().turns,8);assert.equal(h.task().id,original.id);assert.equal(h.task().recovery_attempts,2);assert.deepEqual(h.task().unknown_receipts,['unknown']);assert.equal(i.runnable(),false);
   assert.equal(h.task().bounds[restriction.deadline?'max_turns':'deadline_ms'].kind,'no_configured_bound');
  }finally{f.close();}
 }
});
test('completion-bound recovery still needs settled effects, preserves attempt ceiling and cannot reopen Stop',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});f.h.finish();f.h.startTurn();f.h.actionStarted('effect');f.h.finish(true);assert.throws(()=>f.h.reconcile({}),/review/);
  f.h.data.last_turn.actions[0].status='succeeded';const before=f.h.task().turns;f.h.reconcile({});assert.equal(f.h.task().turns,before);assert.equal(f.h.task().recovery_attempts,1);
  f.h.task().status='needs_review';f.h.task().recovery_attempts=2;assert.throws(()=>f.h.reconcile({}),/review/);f.h.stop();assert.throws(()=>f.h.resumeReviewed({task_id:f.h.task().id,reason:'No human resume requested'}));
 }finally{f.close();}
});
test('static helper discovery checks exact independent versions/commands and does not pass home or model arguments',async()=>{
 const f=fixture();try{
  const command=path.join(f.dir,'runtime');const manifest={schema_version:1,helpers:{watch:{version:2,command:'watch-v2',bound_kinds:['finite','no_configured_bound'],watch_ttl_seconds:{minimum:30,maximum:1800}},continuation:{version:2,command:'continuation-v2',bound_kinds:['finite','no_configured_bound']}}};
  fs.writeFileSync(command,`#!/usr/bin/env node\nif(process.argv.slice(2).join(' ')!=='helper-capabilities')process.exit(1);process.stdout.write(${JSON.stringify(JSON.stringify(manifest))});`,{mode:0o700});
  assert.equal(helpers.ready(command),false);assert.deepEqual(await helpers.discover(command),manifest);assert.equal(helpers.ready(command),true);
  for(const mutate of [v=>v.schema_version=2,v=>v.helpers.watch.version=1,v=>v.helpers.watch.command='watch',v=>v.helpers.watch.bound_kinds=['finite'],v=>v.helpers.watch.watch_ttl_seconds.maximum=3600]){const v=structuredClone(manifest);mutate(v);assert.equal(helpers.supports(v,'watch'),false);}
  fs.writeFileSync(command,'#!/bin/sh\nexit 1\n',{mode:0o700});assert.equal(helpers.ready(command),false);assert.equal(await helpers.discover(command),null);
  const input={status:'running',remaining_ms:bounds.unbounded(),remaining_turns:bounds.unbounded()};await assert.rejects(()=>bridge.invoke(command,f.dir,input,'continuation'),/unavailable/);
 }finally{f.close();}
});
test('readiness rediscovers an atomically replaced helper without a model/tool call',async()=>{
 const f=fixture();try{
  const command=path.join(f.dir,'runtime'),calls=path.join(f.dir,'discoveries');
  const manifest={schema_version:1,helpers:{watch:{version:2,command:'watch-v2',bound_kinds:['finite','no_configured_bound'],watch_ttl_seconds:{minimum:30,maximum:1800}},continuation:{version:2,command:'continuation-v2',bound_kinds:['finite','no_configured_bound']}}};
  function replace(value){
   const next=command+'.new';
   fs.writeFileSync(next,`#!/usr/bin/env node\nif(process.argv.slice(2).join(' ')!=='helper-capabilities')process.exit(1);require('node:fs').appendFileSync(${JSON.stringify(calls)},'x');process.stdout.write(${JSON.stringify(JSON.stringify(value))});`,{mode:0o700});
   fs.renameSync(next,command);
  }
  replace(manifest);await helpers.discover(command);assert.equal(helpers.ready(command),true);
  replace({...manifest,runtime_version:'next'});
  for(let n=0;n<20;n++)assert.equal(helpers.ready(command),false);
  const until=Date.now()+3000;
  while(!helpers.ready(command)&&Date.now()<until)await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal(helpers.ready(command),true,'state-only readiness must recover after helper replacement');
  assert.equal(fs.readFileSync(calls,'utf8'),'xx','one static discovery per binary identity');
  replace({schema_version:1,helpers:{}});assert.equal(helpers.ready(command),false);
  await helpers.discover(command);assert.equal(helpers.ready(command),false);
  for(let n=0;n<20;n++)assert.equal(helpers.ready(command),false);
  assert.equal(fs.readFileSync(calls,'utf8'),'xxx','unsupported helper must not cause repeated processes');
 }finally{f.close();}
});
test('watch and continuation projections retain exact identity and explicit bounds without mutating assignment',()=>{
 const f=fixture();try{const e=f.human();f.intake.accept({request_id:e.id,goal:'shop',max_turns:8});const before=JSON.stringify(f.h.task());
  const c=bridge.context({username:'Agent'},f.h,{ready:false});assert.equal(c.task.id,f.h.task().id);assert.deepEqual(c.task.deadline_ms,bounds.unbounded());assert.deepEqual(c.task.remaining_turns,bounds.finite(8));assert.deepEqual(f.h.recoveryFacts().remaining_ms,bounds.unbounded());assert.equal(JSON.stringify(f.h.task()),before);
 }finally{f.close();}
});
test('unknown persisted bounds stay unknown and private extra fields cannot escape shared task projection',()=>{
 const f=fixture();try{
  const e=f.human();f.intake.accept({request_id:e.id,goal:'shop'});f.h.finish();f.h.task().bounds.private='private-canary';const before=JSON.stringify(f.h.data.task);
  assert.equal(f.intake.capabilities().work_blocked_reason,'unknown_assignment_bounds');assert.equal(f.intake.capabilities().assignment.bound_status,'unknown');assert.equal(f.h.budgetCheckpoint(),false);assert.throws(()=>f.h.startTurn(),/Unknown assignment/);assert.equal(JSON.stringify(f.h.data.task),before);
  const output=f.h.query({operation:'list',access:{mode:'grant',grant:'shared'}},{username:'Agent',context_grant:'shared'},{});assert.ok(!JSON.stringify(output).includes('private-canary'));const presence=require('../presence.cjs').status({task:f.h.task()},'Test');assert.ok(!JSON.stringify(presence).includes('private-canary'));assert.equal(JSON.stringify(f.h.data.task),before);
 }finally{f.close();}
});
