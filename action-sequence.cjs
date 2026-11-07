// Execute an agent-selected plan through the existing guarded operations.
// A recorded plan ID is never replayed, even after a lost reply or restart.
const {createHash}=require('node:crypto');
const {digest}=require('./task-intake.cjs');
const SEQUENCE_TOOLS=['move','place','build','craft','dig','set_open','till'];
class ActionSequence {
 constructor(history){this.history=history;this.active=null;this.pending=null;}
 status(){return this.active?{id:this.active.id,status:'running',completed:this.active.results.length,cancel_requested:!!this.active.cancel_reason}:null;}
 cancel(reason='planner_cancelled'){if(!this.active)return {cancel_requested:false};this.active.cancel_reason=reason;return {cancel_requested:true,id:this.active.id,current_step_may_still_be_running:true};}
 inspect(id){
  const record=(this.history.data.action_sequences||[]).find(r=>r.id===id);
  if(!record)return {id,status:'unknown',replayed:false};
  return structuredClone({...record,status:record.status==='running'&&this.active?.id!==id?'interrupted':record.status,replayed:false});
 }
 async start(plan,options){
  const previous=(this.history.data.action_sequences||[]).find(r=>r.id===plan.plan_id);
  if(previous)return {...await this.run(plan,options),accepted:false};
  const pending=this.run(plan,options),record=this.active;
  // run reserves its durable ID before its first asynchronous operation.
  // If admission failed, propagate that failure instead of claiming acceptance.
  if(!record||record.id!==plan.plan_id)return await pending;
  this.pending=pending;
  pending.catch(error=>{
   record.status='interrupted';record.reason=error.message;record.finished_at=new Date().toISOString();
   try{this.history.save();}catch{}
  }).finally(()=>{if(this.pending===pending)this.pending=null;});
  return {id:record.id,accepted:true,status:'running',completed:false,completed_steps:record.results.length,
   next:'Planning may continue. Use sequence_status for actual results before claiming completion; cancel_sequence stops pending steps.'};
 }
 async wait(id,ms=0){
  if(this.active?.id===id&&this.pending&&ms>0){
   let timer;try{await Promise.race([this.pending.catch(()=>{}),new Promise(resolve=>{timer=setTimeout(resolve,ms);})]);}finally{clearTimeout(timer);}
  }
  return this.inspect(id);
 }
 async run({plan_id,steps}, {guard,execute}){
  const hash=digest(steps),records=this.history.data.action_sequences||[];
  const previous=records.find(r=>r.id===plan_id);
  if(previous){if(previous.hash!==hash)throw Error('Plan ID already binds a different sequence');return {...previous,status:previous.status==='running'&&this.active?.id!==previous.id?'interrupted':previous.status,duplicate:true,replayed:false};}
  if(this.active)throw Error('Another action sequence is running');
  guard();
  const record={id:plan_id,hash,task_id:this.history.data.turn?.task_id,started_at:new Date().toISOString(),status:'running',results:[]};
  // Bound owner storage, but retain consumed IDs independently so eviction
  // cannot make an old possibly accepted sequence executable again.
  const key=createHash('sha256').update(plan_id).digest('hex');
  if((this.history.data.consumed_sequence_ids||[]).includes(key))throw Error('Plan already consumed; detailed receipt no longer retained. Inspect effects; do not replay.');
  this.history.data.consumed_sequence_ids=[...(this.history.data.consumed_sequence_ids||[]),key];
  this.history.data.action_sequences=[...records,record].slice(-32);this.history.save();
  this.active=record;
  try{
   for(let i=0;i<steps.length;i++){
    if(record.cancel_reason){record.status='paused';record.reason=record.cancel_reason;break;}
    try{guard();}catch(e){record.status='paused';record.reason=e.message;break;}
    record.next_step=i;this.history.save();
    try{
     const result=await execute(steps[i],record.id);
     record.results.push({index:i,tool:steps[i].tool,result});
     if(result?.error||result?.blocked||result?.verified===false){record.status='paused';record.reason='Step reported partial, blocked or unverified results; inspect before making a new plan';}
    }catch(e){record.status='paused';record.reason=e.message;record.failed_step=i;}
    this.history.save();
    if(record.status!=='running')break;
   }
   if(record.status==='running')record.status='completed';
   record.finished_at=new Date().toISOString();this.history.save();return {...record,replayed:false};
  }finally{this.active=null;}
 }
}
module.exports={ActionSequence,SEQUENCE_TOOLS};
