// Experience-owned history and bounded work; independent of any agent runtime.
const fs=require('node:fs');
const crypto=require('node:crypto');
const bounds=require('./task-bounds.cjs');
const inputOutcomes=require('./input-outcomes.cjs');
const {isPublicChatEvent}=require('./public-chat.cjs');
const sharedActions=new Set(['chat','tell','move','follow','dig','place','build','gather','craft','give','shear','furnace','container','write_sign','set_open','activate_control']);
const text=(value,limit)=>typeof value==='string'?value.slice(0,limit):undefined;
function sharedProgress(progress){return {at:text(progress?.at,64),summary:text(progress?.summary,2000)||''};}
function sharedEvent(event){
 // This is an export projection, not a redaction of the durable owner record.
 // New event types and new fields remain local until explicitly projected here.
 if(!event||event.whisper||(event.provenance!==undefined&&event.provenance!=='minecraft_public_chat'))return null;
 const base={id:text(event.id,160),time:text(event.time,64),kind:event.kind};
 if(isPublicChatEvent(event))return {...base,username:text(event.username,160),
  message:text(event.message,4000)??text(event.sent,4000)??''};
 if(event.kind==='work_status')return {...base,task_id:text(event.task_id,160),
  status:text(event.status,64),goal:text(event.goal,2000),
  ...(event.progress?{progress:sharedProgress(event.progress)}:{})};
 if(['action_started','action_result','action_failed'].includes(event.kind)&&sharedActions.has(event.action)){
  // Inputs, returned payloads and exception strings may contain private text,
  // even for a public-chat tool which never actually sent its attempted message.
  const receipt={...base,action_id:text(event.action_id,160),action:event.action};
  if(event.kind==='action_result')receipt.reported_error=!!event.result?.error;
  for(const key of ['timeout','operation_settled','turn_preserved'])if(typeof event[key]==='boolean')receipt[key]=event[key];
  return receipt;
 }
 return null;
}
class WorkshopState {
 constructor(file,{maxTurns=12,maxSeconds=2400}={}){
  this.file=file;this.maxTurns=maxTurns;this.maxSeconds=maxSeconds;
  this.data=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{events:[],task:null,turn:null};
  this.recover();
 }
 recover(){
  inputOutcomes.settle(this.data,{interrupted:true,reason:'body_restarted'});
  if(this.data.turn?.conversation_only){this.data.last_conversation_turn={...this.data.turn,interrupted:true};this.data.turn=null;this.save();return;}
  if(this.data.turn){
   if(this.data.turn.task_id===this.data.task?.id&&['running','waiting','review'].includes(this.data.task?.status))this.data.task.status='needs_review';
   this.data.last_turn={...this.data.turn,interrupted:true};this.data.turn=null;this.save();
  }
 }
 save(){fs.writeFileSync(this.file+'.tmp',JSON.stringify(this.data),{mode:0o600});fs.renameSync(this.file+'.tmp',this.file);}
 record(event){
  const saved={...event,id:crypto.randomUUID()};this.data.events.push(saved);
  inputOutcomes.response(this.data,saved);
  // Keep public conversation independent of high-volume physical receipts.
  // This is retrieval evidence, never an input queue or a replayable grant.
  const publicEvents=new Map([...(this.data.public_conversation_history||[]),...this.data.events.filter(isPublicChatEvent)].map(e=>[e.id,e]));
  this.data.public_conversation_history=[...publicEvents.values()].slice(-2000);
  // Pending input retains its original authority evidence independently of
  // the rolling observation journal, only for the existing input lifetime.
  const pinned=new Set([...(this.data.participation_pending||[]),...(this.data.inbox||[]).map(m=>m.id)]),recent=this.data.events.slice(-1000),ids=new Set(recent.map(e=>e.id)),now=Date.now();
  this.data.events=[...this.data.events.filter(e=>!ids.has(e.id)&&pinned.has(e.id)&&now-Date.parse(e.time)<600000),...recent];
  this.save();return saved;
 }
 task(){const task=this.data.task;if(['running','waiting','review','blocked','needs_review'].includes(task?.status)&&bounds.valid(task)&&bounds.timeLow(task)){task.status='budget_exhausted';this.save();}return task;}
 begin({request_id,goal}){
  if(['running','waiting'].includes(this.task()?.status))throw Error('An accepted task is already running');
  if((this.data.accepted_requests||[]).includes(request_id))throw Error('This request has already authorized a task; ask the human for a new request');
  const source=this.data.events.find(e=>e.id===request_id&&e.kind==='chat'&&e.source==='human'&&e.accepted&&!e.whisper);
  if(!source||Date.now()-Date.parse(source.time)>600000)throw Error('Choose a recent routed human request from this game');
  const task={id:crypto.randomUUID(),goal,request_id,requested_by:source.username,request:source.message,status:'running',turns:1,max_turns:this.maxTurns,deadline:Date.now()+this.maxSeconds*1000,progress:[],started_at:new Date().toISOString()};
  // Only the operator's routed request can grant review authority. Models cannot
  // nominate reviewers through work_begin or infer grants from chat prose.
  task.reviewers=source.reviewers||[];task.rework_requests=[];
  this.data.accepted_requests=[...(this.data.accepted_requests||[]),request_id].slice(-1000);
  if(this.data.task)this.data.task_history=[...(this.data.task_history||[]),this.data.task].slice(-10);
  this.data.task=task;if(this.data.turn)this.data.turn.task_id=task.id;this.save();return task;
 }
 startTurn({peerOnly=false,requestIds=[],activity=false,continuation=false}={}){
  const input=require('./installation-inputs.cjs'),task=activity?null:this.task(),last=this.data.last_turn;
  const sameWork=activity?last?.activity===true:last?.activity!==true&&!!task&&last?.task_id===task.id;
  const taskSource=task?.authority?.source?.id||task?.request_id;
  const replyRoute=requestIds.length?input.replyRoute(this.data,requestIds):continuation?
   (sameWork&&last?.reply_route||taskSource&&input.replyRoute(this.data,[taskSource])):null;
  if(replyRoute)input.replyRecord(this.data,replyRoute);
  if(task&&!bounds.valid(task))throw Error('Unknown assignment bounds require inspection');
  if(['running','waiting'].includes(task?.status)){
   if(bounds.timeLow(task,120000)){this.budgetCheckpoint();throw Error('Insufficient time for another useful turn; progress saved');}
   task.status='running';
   if(bounds.turnsLow(task)){task.status='budget_exhausted';this.save();throw Error('Task turn budget exhausted');}
   task.turns++;
  }
  this.data.turn={...(activity?{activity:true}:{}),...(replyRoute?{reply_route:structuredClone(replyRoute)}:{}),started_at:new Date().toISOString(),task_id:task?.id||null,progress_revision:task?.progress_revision||0,actions:[],request_ids:requestIds,may_mutate:!peerOnly||['running','waiting'].includes(task?.status)};inputOutcomes.admit(this.data);this.save();
 }
 actionStarted(id){if(this.data.turn){this.data.turn.actions.push({id,status:'pending'});this.save();}}
 actionSettled(id,success){const a=this.data.turn?.actions?.find(a=>a.id===id);if(a){a.status=success?'succeeded':'uncertain';this.save();}}
 actionFailedSettled(id,evidence){const a=this.data.turn?.actions?.find(a=>a.id===id);if(a){a.status='failed_settled';a.outcome=structuredClone(evidence);this.save();}}
 recoveryFacts(){
  const task=this.task(),turn=this.data.last_turn;
  return {status:task?.status||'none',...(task?.bounds?bounds.remaining(task):{remaining_ms:Math.max(0,(task?.deadline||0)-Date.now()),remaining_turns:Math.max(0,(task?.max_turns||0)-(task?.turns||0))}),minimum_turn_ms:120000,
   receipts_complete:!!(turn?.interrupted&&turn.task_id===task?.id&&Array.isArray(turn.actions)&&turn.actions.every(a=>a.status!=='pending')),
   actions_succeeded:!!turn?.actions?.every(a=>a.status==='succeeded'),recovery_attempts:task?.recovery_attempts||0};
 }
 budgetCheckpoint(){
  const task=this.task();if(task&&bounds.valid(task)&&['running','waiting','needs_review'].includes(task.status)&&bounds.timeLow(task,120000)){
   this.appendProgress(task,{at:new Date().toISOString(),kind:'budget_checkpoint',summary:'Progress saved: less than two minutes remain, so no new work turn will start. A fresh authorization is required to continue.'});
   task.status='budget_exhausted';task.wait_for=null;this.save();return true;
  }return false;
 }
 reconcile(observation){
  const f=this.recoveryFacts();const task=this.task();
  if(this.data.turn||f.status!=='needs_review'||!bounds.within(task,{minimumMs:120000})||!f.receipts_complete||!f.actions_succeeded||f.recovery_attempts>=2)throw Error('Interrupted work requires operator review');
  task.recovery_attempts=f.recovery_attempts+1;
  this.appendProgress(task,{at:new Date().toISOString(),kind:'receipt_reconciliation',summary:'Controller inspected settled successful action receipts and current world state. Continue by observing; do not replay prior actions.',observation});
  task.status='running';task.wait_for=null;task.wait_started_at=null;this.save();return task;
 }
 appendProgress(task,entry){
  task.progress.push(entry);task.progress=task.progress.slice(-30);
  // A bounded history's length stops changing; revisions still identify new work.
  task.progress_revision=(task.progress_revision||0)+1;
 }
 report({status,summary,wait_for}){
  if(this.data.turn?.activity){
   if(status==='waiting'&&(!wait_for||!wait_for.trim()))throw Error('Waiting requires a concrete observable wait_for condition');
   this.data.turn.activity_report={status,summary,...(status==='waiting'?{wait_for}:{})};this.save();
   return {id:null,status,progress:[{summary}],activity:true};
  }
  const task=this.task();if(!task||task.status!=='running')throw Error('No running task');
  if(status==='waiting'&&(!wait_for||!wait_for.trim()))throw Error('Waiting requires a concrete observable wait_for condition');
  task.wait_for=status==='waiting'?wait_for:null;
  task.wait_started_at=status==='waiting'?new Date().toISOString():null;
  this.appendProgress(task,{at:new Date().toISOString(),summary});
  if(status==='review')task.reviewed_at=new Date().toISOString();
  task.status=status;this.save();return task;
 }
 reopen({task_id,request_id,reason}){
  const task=this.task(),turn=this.data.turn;
  if(!task||task.id!==task_id||task.status!=='review'||!turn||turn.task_id!==task.id)throw Error('Only a reviewed task in its current conversation turn can return to work');
  if(bounds.timeLow(task,120000)||bounds.turnsLow(task))throw Error('The original task budget cannot be extended');
  const source=this.data.events.find(e=>e.id===request_id);
  if(!turn.request_ids?.includes(request_id)||!source||source.kind!=='chat'||source.source!=='agent'||!source.accepted||source.whisper||source.intent!=='request'||!task.reviewers?.includes(source.username)||!task.reviewed_at||Date.parse(source.time)<Date.parse(task.reviewed_at)||Date.now()-Date.parse(source.time)>600000)throw Error('A fresh public request from an operator-authorized reviewer is required');
  if((task.rework_requests||[]).includes(request_id)||(task.rework_requests||[]).length>=3)throw Error('Review request already used or rework limit reached');
  if(typeof reason!=='string'||!reason.trim()||reason.length>2000)throw Error('Explain how this correction fits the existing task');
  task.rework_requests=[...(task.rework_requests||[]),request_id];task.turns++;
  this.appendProgress(task,{at:new Date().toISOString(),kind:'review_rework',summary:reason,reviewer:source.username,request_id,previous_status:task.status});
  task.status='running';task.wait_for=null;task.wait_started_at=null;turn.may_mutate=true;this.save();return task;
 }
 note({task_id,summary,blocker_resolved=false,status},observation){
  if(status!==undefined&&!['blocked','needs_review','review'].includes(status))throw Error('Notes cannot start or resume work');
  const task=this.task();if(!task||task.id!==task_id)throw Error('Task changed; inspect the current task before updating it');
  if(status&&['stopped','budget_exhausted'].includes(task.status))throw Error('Notes cannot reopen stopped or exhausted work');
  this.appendProgress(task,{at:new Date().toISOString(),summary,kind:'reassessment',blocker_resolved,observation});
  if(status){task.status=status;if(status==='review')task.reviewed_at=new Date().toISOString();}
  else if(blocker_resolved&&task.status==='blocked')task.status='needs_review';
  this.save();return task;
 }
 checkpoint(observation){if(this.data.turn&&!this.data.turn.conversation_only&&!this.data.turn.activity&&this.data.turn.task_id===this.data.task?.id&&this.data.task){this.data.task.last_observed={at:new Date().toISOString(),...observation};this.save();}}
 finish(error=false,budgetLimited=false){
  if(this.data.turn?.conversation_only){inputOutcomes.settle(this.data,{interrupted:!!error,reason:error?'turn_interrupted':budgetLimited?'planner_turn_limited':null});require('./speech.cjs').settleReplies(this.data,{error,budgetLimited});this.data.last_conversation_turn={...this.data.turn,interrupted:!!error};this.data.turn=null;this.save();return;}
  const turn=this.data.turn,task=turn?.activity?null:this.task();
  if(error&&turn&&['waiting','review'].includes(task?.status))task.status='needs_review';
  if(task?.status==='running'){
   if(error&&turn)task.status='needs_review';
   else if(budgetLimited){
    this.appendProgress(task,{at:new Date().toISOString(),kind:'controller_checkpoint',summary:'The model reached a turn limit after its reported tool calls settled. Inspect current observations and receipts before continuing the existing responsibility.'});
    if(bounds.turnsLow(task))task.status='budget_exhausted';
   }
   else if(turn?.task_id===task.id&&turn.progress_revision===(task.progress_revision||0)){
    const succeeded=Array.isArray(turn.actions)&&turn.actions.length>0&&turn.actions.every(a=>a.status==='succeeded');
    const prior=this.data.last_turn;
    // A successful terminal with settled effects can omit work_report. Save
    // a truthful checkpoint and allow one reassessment; never replay effects,
    // infer completion, or spin indefinitely on missing reports/no-op tools.
    const alreadyMissing=prior?.task_id===task.id&&prior.missing_report===true;
    if(succeeded&&!alreadyMissing){
     this.appendProgress(task,{at:new Date().toISOString(),kind:'missing_report_checkpoint',summary:'The planner ended without a progress report after all recorded actions settled successfully. Inspect current state and receipts, report the actual remaining work or blocker, and do not replay these actions.'});
     turn.missing_report=true;
    }else task.status='blocked';
    if(bounds.turnsLow(task))task.status='budget_exhausted';
   }
   else if(bounds.turnsLow(task))task.status='budget_exhausted';
  }
  inputOutcomes.settle(this.data,{interrupted:!!error,reason:error?'turn_interrupted':budgetLimited?'planner_turn_limited':turn?.activity_report?.status==='blocked'?'activity_blocked':task?.status==='blocked'?'assignment_blocked':null});
  require('./speech.cjs').settleReplies(this.data,{error,budgetLimited});
  if(turn)this.data.last_turn={...turn,interrupted:!!error,...(budgetLimited&&!error?{budget_limited:true}:{})};
  this.data.turn=null;this.save();
 }
 wake(task_id){
  const task=this.task();
  if(!task||task.id!==task_id||task.status!=='waiting'||bounds.turnsLow(task))throw Error('No authorized waiting task with remaining budget');
  task.status='running';this.save();return task;
 }
 resumeReviewed({task_id,reason,resume_stopped=false,effects_review_id}){
  const task=this.task();
  if(this.data.turn||!task||task.id!==task_id||(!['blocked','needs_review'].includes(task.status)&&!(task.status==='stopped'&&resume_stopped===true)))throw Error('Only an idle blocked or interrupted task can be resumed after review; stopped work requires explicit operator authorization');
  if(bounds.timeLow(task)||bounds.turnsLow(task))throw Error('Existing task budget exhausted; review cannot extend it');
  if(typeof reason!=='string'||!reason.trim()||reason.length>2000)throw Error('A concrete recovery review is required');
  const review=this.data.last_turn?.effect_review;
  if(effects_review_id!==undefined){
   const digest=value=>require('node:crypto').createHash('sha256').update(JSON.stringify(value)).digest('hex');
   if(review?.scope!=='task_effects'||review.task_id!==task.id||review.request_id!==effects_review_id||review.expected_task_sha256!==digest(task)||review.resumed_task_id)throw Error('Exact unconsumed task-effects review required');
  }else if(review?.scope==='task_effects'&&review.task_id===task.id)throw Error('Name the exact task-effects review before resuming');
  const original=structuredClone(this.data);
  this.appendProgress(task,{at:new Date().toISOString(),kind:'operator_recovery',summary:reason,previous_status:task.status,...(effects_review_id?{effects_review_id}:{})});
  if(effects_review_id)review.resumed_task_id=task.id;

  task.status='running';task.wait_for=null;task.wait_started_at=null;try{this.save();}catch(error){this.data=original;throw error;}return task;
 }
 stop({activity=false}={}){inputOutcomes.settle(this.data,{interrupted:true,reason:'explicit_stop'});if(activity)this.data.activity_stop={at:Date.now()};if(this.data.turn)this.data[this.data.turn.conversation_only?'last_conversation_turn':'last_turn']={...this.data.turn,interrupted:!!this.data.turn.actions?.some(a=>a.status==='pending'||a.status==='uncertain')};if(['running','waiting','blocked','needs_review','review'].includes(this.data.task?.status))this.data.task.status='stopped';this.data.turn=null;this.save();}
 query(q,cfg,live){
  const owner=q.access?.mode==='owner';
  if(!owner&&(q.access?.mode!=='grant'||!cfg.context_grant||q.access.grant!==cfg.context_grant))throw Error('Invalid conversation grant');
  const id=cfg.conversation_id||'minecraft:workshop';
  if(q.conversation_id&&q.conversation_id!==id)throw Error('Conversation is not available');
  const observed_at=new Date().toISOString();
  if(q.operation==='list'){
   // Discovery is not a detailed observation of every connected world. Keep
   // canonical tasks untouched, including recorded status after a deadline.
   const recorded=this.data.task;
   const activity=Object.fromEntries(['connected','busy','turn_active'].map(k=>[k,typeof live[k]==='boolean'?live[k]:null]));
   activity.task=recorded?{id:recorded.id,status:recorded.status,
    limit_state:bounds.limitState(recorded,Date.parse(observed_at))}:null;
   return {items:[{id,conversation_id:id,label:`Minecraft — ${cfg.username}`,surface:'minecraft',
    updated_at:this.data.events.at(-1)?.time,observed_at,activity,
    coverage:'Discovery/status only; task status is recorded, not proof of completion. Read this conversation for details and evidence under the same access rules.',
    read:{operation:'read',conversation_id:id}}],complete:true,observed_at};
  }
  const original=this.task();
  const task=original?{...(owner?original:Object.fromEntries(
   ['id','goal','status','turns','max_turns','deadline','wait_for'].filter(k=>original[k]!==undefined).map(k=>[k,original[k]]))),
   ...(!owner&&original.bounds!==undefined?{bounds:bounds.valid(original)?bounds.get(original):{status:'unknown'}}:{}),
   limit_state:bounds.limitState(original,Date.parse(observed_at)),
   progress:original.progress.slice(-8).map(p=>owner?p:sharedProgress(p))}:null;
  const coverage=owner?'Recent game chat and actual action receipts; task completion is agent-reported':
   'Recent public chat, task summaries and action receipt metadata; raw inputs/results are owner-local and task completion is agent-reported';
  const current={id,conversation_id:id,label:`Minecraft — ${cfg.username}`,surface:'minecraft',updated_at:this.data.events.at(-1)?.time,coverage,activity:{...live,task},observed_at};
  if(q.operation==='authorize')return {owner:false,conversation_id:id,actor_id:`minecraft:${cfg.username}`,surface:'minecraft',label:current.label,observed_at};
  const limit=Math.max(1,Math.min(40,Number(q.limit)||20));
  const events=owner?this.data.events:this.data.events.map(sharedEvent).filter(Boolean);
  const messages=events.slice(-limit).map(e=>({id:e.id,at:e.time,actor:e.username||cfg.username,
   text:(owner?(e.message||e.sent||JSON.stringify(e)):(e.message??JSON.stringify(e))).slice(0,4000),label:e.kind}));
  if(q.operation==='read'||q.operation==='orientation')return {conversation_id:id,current,messages,complete:events.length<=limit,observed_at};
  throw Error('Unsupported context operation');
 }
}
module.exports={WorkshopState};
