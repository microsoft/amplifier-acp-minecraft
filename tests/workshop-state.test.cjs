const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const os=require('node:os');const path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
function fixture(t,options){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'minecraft-state-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return new WorkshopState(path.join(dir,'state.json'),options);}
function request(s,changes={}){s.record({kind:'chat',username:'VisitorOne',source:'human',accepted:true,whisper:false,message:'Build the inn while I am away',time:new Date().toISOString(),...changes});return s.data.events.at(-1).id;}
const cfg={username:'BuilderOne',context_grant:'secret-grant',conversation_id:'world-one'};
test('context persists, reports activity, and excludes private whispers from the room',t=>{
 const s=fixture(t);request(s);request(s,{whisper:true,message:'private-whisper'});
 const fresh=new WorkshopState(s.file);assert.equal(fresh.data.events.length,2);
 const shared=fresh.query({operation:'read',conversation_id:'world-one',access:{mode:'grant',grant:'secret-grant'}},cfg,{connected:true});
 assert.equal(shared.messages.length,1);assert.equal(shared.current.activity.connected,true);assert.ok(!JSON.stringify(shared).includes('private-whisper'));
 assert.equal(fresh.query({operation:'read',access:{mode:'owner'}},cfg,{}).messages.length,2);
 assert.throws(()=>fresh.query({operation:'list',access:{mode:'grant',grant:'wrong'}},cfg,{}));
 assert.throws(()=>fresh.query({operation:'read',conversation_id:'private-slack',access:{mode:'owner'}},cfg,{}));
 assert.equal(fresh.query({operation:'authorize',access:{mode:'grant',grant:'secret-grant'}},cfg,{}).owner,false);
});
test('task continues with progress and stops at its persisted turn budget',t=>{
 const s=fixture(t,{maxTurns:2});const id=request(s);s.startTurn();s.begin({request_id:id,goal:'inn'});s.report({status:'running',summary:'floor laid'});s.finish();
 s.startTurn();s.report({status:'running',summary:'wall laid'});s.finish();assert.equal(s.task().status,'budget_exhausted');
 assert.throws(()=>s.begin({request_id:id,goal:'reset budget'}));
 assert.equal(new WorkshopState(s.file).task().status,'budget_exhausted');
});
test('only routed, recent human requests can authorize ongoing work',t=>{
 const s=fixture(t);
 for(const changes of [{source:'agent'},{accepted:false},{whisper:true},{time:'2000-01-01T00:00:00Z'}]){
  assert.throws(()=>s.begin({request_id:request(s,changes),goal:'inn'}));
 }
});
test('stop, interrupted execution, no progress, and explicit review do not continue',t=>{
 for(const mode of ['stop','crash','no-progress','review']){
  const s=fixture(t);const id=request(s);s.startTurn();s.begin({request_id:id,goal:'inn'});s.report({status:'running',summary:'floor laid'});s.finish();s.startTurn();
  if(mode==='stop')s.stop();
  if(mode==='review')s.report({status:'review',summary:'inspect completed shell'});
  if(mode==='no-progress'||mode==='review')s.finish();
  const status=new WorkshopState(s.file).task().status;
  assert.equal(status,{stop:'stopped',crash:'needs_review','no-progress':'blocked',review:'review'}[mode]);
 }
});
test('elapsed task budget expires without another model call',t=>{
 const s=fixture(t);s.begin({request_id:request(s),goal:'inn'});s.data.task.deadline=Date.now()-1;
 assert.equal(s.task().status,'budget_exhausted');
});
test('a completed checkpoint can resume after restart, while an interrupted controller cannot',t=>{
 const s=fixture(t);s.startTurn();s.begin({request_id:request(s),goal:'inn'});s.report({status:'running',summary:'floor verified'});s.finish();
 const fresh=new WorkshopState(s.file);assert.equal(fresh.task().status,'running');fresh.startTurn();fresh.recover();assert.equal(fresh.task().status,'needs_review');
});

test('recovery notes reconcile a blocked task without renewing its authority or budget',t=>{
 const s=fixture(t);s.startTurn();const task=s.begin({request_id:request(s),goal:'inn'});
 s.report({status:'blocked',summary:'stuck in pit'});s.finish();const deadline=task.deadline,turns=task.turns;
 s.startTurn();s.note({task_id:task.id,summary:'escaped, inn unfinished',blocker_resolved:true},{position:{x:20,y:64,z:66}});
 assert.equal(s.task().status,'needs_review');
 assert.throws(()=>s.note({task_id:task.id,summary:'resume',status:'running'},{}),/cannot start/);
 s.note({task_id:task.id,summary:'new blocker',status:'blocked'},{});assert.equal(s.task().status,'blocked');
 s.note({task_id:task.id,summary:'resolved, needs review',status:'needs_review'},{});
 assert.equal(s.task().deadline,deadline);assert.equal(s.task().turns,turns);
 assert.throws(()=>s.note({task_id:'stale',summary:'done'},{}),/Task changed/);
 s.checkpoint({position:{x:20,y:64,z:66}});s.finish();
 const fresh=new WorkshopState(s.file);assert.equal(fresh.task().last_observed.position.y,64);assert.equal(fresh.task().status,'needs_review');
 fresh.startTurn();fresh.begin({request_id:request(fresh),goal:'resume inn'});assert.equal(fresh.data.task_history.at(-1).id,task.id);
});

test('waiting preserves authority, wakes without renewed budgets, and stop revokes it',t=>{
 const s=fixture(t);s.startTurn();const task=s.begin({request_id:request(s),goal:'assist lead'});
 assert.throws(()=>s.report({status:'waiting',summary:'waiting'}),/wait_for/);
 s.report({status:'waiting',summary:'awaiting wood',wait_for:'peer confirms wood delivered'});s.finish();
 const deadline=task.deadline,turns=task.turns;
 assert.throws(()=>s.begin({request_id:request(s),goal:'replace'}));
 assert.throws(()=>s.wake('wrong'));
 s.wake(task.id);assert.equal(task.deadline,deadline);assert.equal(task.turns,turns);
 s.startTurn();assert.equal(task.turns,turns+1);
 s.report({status:'waiting',summary:'awaiting wood',wait_for:'wood arrives'});s.finish();s.stop();
 assert.equal(task.status,'stopped');assert.throws(()=>s.wake(task.id));
});
test('waiting expires and cannot wake past the turn budget',t=>{
 const s=fixture(t,{maxTurns:1});const task=s.begin({request_id:request(s),goal:'assist lead'});
 s.report({status:'waiting',summary:'awaiting wood',wait_for:'wood arrives'});s.finish();
 assert.throws(()=>s.wake(task.id));task.deadline=Date.now()-1;
 assert.equal(s.task().status,'budget_exhausted');assert.throws(()=>s.wake(task.id));
});

test('interruption after declaring a wait does not authorize a decision wake',t=>{
 for(const crash of [false,true]){
  const s=fixture(t);s.startTurn();const task=s.begin({request_id:request(s),goal:'assist'});
  s.report({status:'waiting',summary:'pending',wait_for:'wood delivered'});
  if(crash)s.recover();else s.finish(true);
  assert.equal(task.status,'needs_review');assert.throws(()=>s.wake(task.id));
 }
});

test('clean turn budget exhaustion checkpoints without renewing task authority',t=>{
 const s=fixture(t,{maxTurns:2});s.startTurn();const task=s.begin({request_id:request(s),goal:'creative task'});
 const deadline=task.deadline;s.finish(false,true);
 assert.equal(task.status,'running');assert.equal(task.progress.at(-1).kind,'controller_checkpoint');
 assert.equal(task.deadline,deadline);assert.equal(task.turns,1);
 const fresh=new WorkshopState(s.file);fresh.startTurn();fresh.finish(false,true);
 assert.equal(fresh.task().status,'budget_exhausted');assert.equal(fresh.task().deadline,deadline);
});

test('clean budget boundary preserves waits and never restarts stopped or reviewed work',t=>{
 for(const status of ['waiting','stopped','review']){
  const s=fixture(t);s.startTurn();s.begin({request_id:request(s),goal:'creative task'});
  if(status==='stopped')s.stop();else s.report({status,summary:'recorded',wait_for:'peer result'});
  s.finish(false,true);assert.equal(s.task().status,status);
 }
 const s=fixture(t);s.startTurn();s.begin({request_id:request(s),goal:'creative task'});s.finish(true,true);
 assert.equal(s.task().status,'needs_review');
});

test('progress continues after the retained history fills, including after restart',t=>{
 let s=fixture(t,{maxTurns:60});s.startTurn();const task=s.begin({request_id:request(s),goal:'large library'});
 const deadline=task.deadline;
 for(let i=1;i<=40;i++){
  if(i>1)s.startTurn();
  s.report({status:'running',summary:`section ${i}`});s.finish();
  assert.equal(s.task().status,'running');
  if(i===30)s=new WorkshopState(s.file,{maxTurns:60});
 }
 assert.equal(s.task().progress.length,30);assert.equal(s.task().turns,40);assert.equal(s.task().deadline,deadline);
 s.startTurn();s.finish();assert.equal(s.task().status,'blocked','a full log must still detect a genuinely missing report');
});

test('legacy full histories acquire revisions without changing authority or limits',t=>{
 const s=fixture(t,{maxTurns:90});const task=s.begin({request_id:request(s),goal:'library'});
 task.progress=Array.from({length:30},()=>({at:'earlier',summary:'saved progress'}));s.save();
 const fresh=new WorkshopState(s.file);fresh.startTurn();fresh.report({status:'running',summary:'new verified progress'});fresh.finish();
 assert.equal(fresh.task().status,'running');assert.equal(fresh.task().progress.length,30);assert.equal(fresh.task().progress_revision,1);
 assert.equal(fresh.task().deadline,task.deadline);assert.equal(fresh.task().max_turns,90);
});

test('operator recovery resumes only a reviewed idle task within its original budget',t=>{
 for(const status of ['blocked','needs_review']){
  const s=fixture(t);const task=s.begin({request_id:request(s),goal:'library'});task.status=status;s.save();
  const {id,deadline,turns,max_turns,request_id}=task;
  assert.throws(()=>s.resumeReviewed({task_id:'stale',reason:'checked'}));
  assert.throws(()=>s.resumeReviewed({task_id:id,reason:' '}));
  s.resumeReviewed({task_id:id,reason:'Receipts settled and current work inspected; original work remains unfinished.'});
  assert.equal(task.status,'running');assert.equal(task.deadline,deadline);assert.equal(task.turns,turns);assert.equal(task.max_turns,max_turns);assert.equal(task.request_id,request_id);
  assert.equal(task.progress.at(-1).kind,'operator_recovery');assert.equal(task.progress.at(-1).previous_status,status);
  assert.equal(new WorkshopState(s.file).task().status,'running');
 }
});

test('recovery rejects active, stopped, reviewed, expired, or exhausted work',t=>{
 for(const status of ['running','waiting','stopped','review','budget_exhausted']){
  const s=fixture(t);const task=s.begin({request_id:request(s),goal:'library'});task.status=status;
  assert.throws(()=>s.resumeReviewed({task_id:task.id,reason:'checked'}));assert.equal(task.status,status);
 }
 for(const condition of ['active','deadline','turns']){
  const s=fixture(t);const task=s.begin({request_id:request(s),goal:'library'});task.status='needs_review';
  if(condition==='active')s.data.turn={task_id:task.id};
  if(condition==='deadline')task.deadline=Date.now()-1;
  if(condition==='turns')task.turns=task.max_turns;
  assert.throws(()=>s.resumeReviewed({task_id:task.id,reason:'checked'}));assert.equal(task.status,'needs_review');
 }
});

test('deadline checkpoint prevents empty turns and preserves original authorization',t=>{
 const s=fixture(t);const task=s.begin({request_id:request(s),goal:'library'});task.deadline=Date.now()+100000;
 const {id,deadline,turns,max_turns}=task;assert.throws(()=>s.startTurn(),/Insufficient time/);
 assert.equal(task.status,'budget_exhausted');assert.equal(task.id,id);assert.equal(task.deadline,deadline);assert.equal(task.turns,turns);assert.equal(task.max_turns,max_turns);
 assert.equal(s.budgetCheckpoint(),false);assert.equal(task.progress.filter(p=>p.kind==='budget_checkpoint').length,1);
});
test('bounded receipt recovery never replays or extends uncertain work',t=>{
 for(const result of ['succeeded','uncertain','pending']){
  const s=fixture(t);const task=s.begin({request_id:request(s),goal:'library'});s.startTurn();s.actionStarted('a');
  if(result!=='pending')s.actionSettled('a',result==='succeeded');s.finish(true);
  const {id,deadline,turns}=task;
  if(result==='succeeded'){
   s.reconcile({position:{x:1,y:65,z:1}});assert.equal(task.status,'running');assert.equal(task.recovery_attempts,1);
   assert.equal(task.id,id);assert.equal(task.deadline,deadline);assert.equal(task.turns,turns);
   s.startTurn();s.finish(true);s.reconcile({});s.startTurn();s.finish(true);assert.throws(()=>s.reconcile({}),/review/);
  }else {assert.throws(()=>s.reconcile({}),/review/);assert.equal(task.status,'needs_review');}
 }
});
test('stop revokes paused recovery and legacy receipts do not justify automatic continuation',t=>{
 const s=fixture(t);s.begin({request_id:request(s),goal:'library'});s.startTurn();delete s.data.turn.actions;s.finish(true);
 assert.equal(s.recoveryFacts().receipts_complete,false);assert.throws(()=>s.reconcile({}));
 s.stop();assert.equal(s.task().status,'stopped');assert.throws(()=>s.resumeReviewed({task_id:s.task().id,reason:'previous receipts'}));
});

test('peer replies cannot authorize mutations after work stops or expires',t=>{
 for(const status of ['stopped','blocked','needs_review','review','budget_exhausted']){
  const s=fixture(t);const task=s.begin({request_id:request(s),goal:'library'});task.status=status;
  s.startTurn({peerOnly:true});assert.equal(s.data.turn.may_mutate,false);assert.equal(task.status,status);
 }
 const s=fixture(t);s.startTurn({peerOnly:true});assert.equal(s.data.turn.may_mutate,false);s.finish();
 s.startTurn();assert.equal(s.data.turn.may_mutate,true);
 s.begin({request_id:request(s),goal:'library'});s.report({status:'running',summary:'progress'});s.finish();s.startTurn({peerOnly:true});assert.equal(s.data.turn.may_mutate,true);
});
