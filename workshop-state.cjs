// Experience-owned history and bounded work; independent of any agent runtime.
const fs=require('node:fs');
const crypto=require('node:crypto');
class WorkshopState {
 constructor(file,{maxTurns=12,maxSeconds=2400}={}){
  this.file=file;this.maxTurns=maxTurns;this.maxSeconds=maxSeconds;
  this.data=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{events:[],task:null,turn:null};
  this.recover();
 }
 recover(){
  if(this.data.turn){
   if(['running','waiting'].includes(this.data.task?.status))this.data.task.status='needs_review';
   this.data.turn=null;this.save();
  }
 }
 save(){fs.writeFileSync(this.file+'.tmp',JSON.stringify(this.data),{mode:0o600});fs.renameSync(this.file+'.tmp',this.file);}
 record(event){this.data.events.push({...event,id:crypto.randomUUID()});this.data.events=this.data.events.slice(-1000);this.save();}
 task(){const task=this.data.task;if(['running','waiting'].includes(task?.status)&&Date.now()>task.deadline){task.status='budget_exhausted';this.save();}return task;}
 begin({request_id,goal}){
  if(['running','waiting'].includes(this.task()?.status))throw Error('An accepted task is already running');
  if((this.data.accepted_requests||[]).includes(request_id))throw Error('This request has already authorized a task; ask the human for a new request');
  const source=this.data.events.find(e=>e.id===request_id&&e.kind==='chat'&&e.source==='human'&&e.accepted&&!e.whisper);
  if(!source||Date.now()-Date.parse(source.time)>600000)throw Error('Choose a recent routed human request from this game');
  const task={id:crypto.randomUUID(),goal,request_id,requested_by:source.username,request:source.message,status:'running',turns:1,max_turns:this.maxTurns,deadline:Date.now()+this.maxSeconds*1000,progress:[],started_at:new Date().toISOString()};
  this.data.accepted_requests=[...(this.data.accepted_requests||[]),request_id].slice(-1000);
  if(this.data.task)this.data.task_history=[...(this.data.task_history||[]),this.data.task].slice(-10);
  this.data.task=task;this.save();return task;
 }
 startTurn(){
  const task=this.task();
  if(['running','waiting'].includes(task?.status)){
   task.status='running';
   if(task.turns>=task.max_turns){task.status='budget_exhausted';this.save();throw Error('Task turn budget exhausted');}
   task.turns++;
  }
  this.data.turn={started_at:new Date().toISOString(),task_id:task?.id||null,progress_revision:task?.progress_revision||0};this.save();
 }
 appendProgress(task,entry){
  task.progress.push(entry);task.progress=task.progress.slice(-30);
  // A bounded history's length stops changing; revisions still identify new work.
  task.progress_revision=(task.progress_revision||0)+1;
 }
 report({status,summary,wait_for}){
  const task=this.task();if(!task||task.status!=='running')throw Error('No running task');
  if(status==='waiting'&&(!wait_for||!wait_for.trim()))throw Error('Waiting requires a concrete observable wait_for condition');
  task.wait_for=status==='waiting'?wait_for:null;
  task.wait_started_at=status==='waiting'?new Date().toISOString():null;
  this.appendProgress(task,{at:new Date().toISOString(),summary});
  task.status=status;this.save();return task;
 }
 note({task_id,summary,blocker_resolved=false,status},observation){
  if(status!==undefined&&!['blocked','needs_review','review'].includes(status))throw Error('Notes cannot start or resume work');
  const task=this.task();if(!task||task.id!==task_id)throw Error('Task changed; inspect the current task before updating it');
  this.appendProgress(task,{at:new Date().toISOString(),summary,kind:'reassessment',blocker_resolved,observation});
  if(status)task.status=status;
  else if(blocker_resolved&&task.status==='blocked')task.status='needs_review';
  this.save();return task;
 }
 checkpoint(observation){if(this.data.task){this.data.task.last_observed={at:new Date().toISOString(),...observation};this.save();}}
 finish(error=false,budgetLimited=false){
  const task=this.task(),turn=this.data.turn;
  if(error&&task?.status==='waiting')task.status='needs_review';
  if(task?.status==='running'){
   if(error)task.status='needs_review';
   else if(budgetLimited){
    this.appendProgress(task,{at:new Date().toISOString(),kind:'controller_checkpoint',summary:'The model reached a turn limit after its reported tool calls settled. Inspect current observations and receipts before continuing the existing responsibility.'});
    if(task.turns>=task.max_turns)task.status='budget_exhausted';
   }
   else if(turn?.task_id===task.id&&turn.progress_revision===(task.progress_revision||0))task.status='blocked';
   else if(task.turns>=task.max_turns)task.status='budget_exhausted';
  }
  this.data.turn=null;this.save();
 }
 wake(task_id){
  const task=this.task();
  if(!task||task.id!==task_id||task.status!=='waiting'||task.turns>=task.max_turns)throw Error('No authorized waiting task with remaining budget');
  task.status='running';this.save();return task;
 }
 resumeReviewed({task_id,reason}){
  const task=this.task();
  if(this.data.turn||!task||task.id!==task_id||!['blocked','needs_review'].includes(task.status))throw Error('Only an idle blocked or interrupted task can be resumed after review');
  if(Date.now()>=task.deadline||task.turns>=task.max_turns)throw Error('Existing task budget exhausted; review cannot extend it');
  if(typeof reason!=='string'||!reason.trim()||reason.length>2000)throw Error('A concrete recovery review is required');
  this.appendProgress(task,{at:new Date().toISOString(),kind:'operator_recovery',summary:reason,previous_status:task.status});
  task.status='running';task.wait_for=null;task.wait_started_at=null;this.save();return task;
 }
 stop(){if(['running','waiting'].includes(this.data.task?.status))this.data.task.status='stopped';this.data.turn=null;this.save();}
 query(q,cfg,live){
  const owner=q.access?.mode==='owner';
  if(!owner&&(q.access?.mode!=='grant'||!cfg.context_grant||q.access.grant!==cfg.context_grant))throw Error('Invalid conversation grant');
  const id=cfg.conversation_id||'minecraft:workshop';
  if(q.conversation_id&&q.conversation_id!==id)throw Error('Conversation is not available');
  const observed_at=new Date().toISOString();
  const original=this.task();const task=original?{...original,progress:original.progress.slice(-8)}:null;
  const current={id,conversation_id:id,label:`Minecraft — ${cfg.username}`,surface:'minecraft',updated_at:this.data.events.at(-1)?.time,coverage:'Recent game chat and actual action receipts; task completion is agent-reported',activity:{...live,task},observed_at};
  if(q.operation==='authorize')return {owner:false,conversation_id:id,actor_id:`minecraft:${cfg.username}`,surface:'minecraft',label:current.label,observed_at};
  if(q.operation==='list')return {items:[current],complete:true,observed_at};
  const limit=Math.max(1,Math.min(40,Number(q.limit)||20));
  const events=this.data.events.filter(e=>owner||!e.whisper);
  const messages=events.slice(-limit).map(e=>({id:e.id,at:e.time,actor:e.username||cfg.username,text:(e.message||e.sent||JSON.stringify(e)).slice(0,4000),label:e.kind}));
  if(q.operation==='read'||q.operation==='orientation')return {conversation_id:id,current,messages,complete:events.length<=limit,observed_at};
  throw Error('Unsupported context operation');
 }
}
module.exports={WorkshopState};
