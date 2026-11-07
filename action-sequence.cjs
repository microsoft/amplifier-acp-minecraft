// Execute an agent-selected plan through the existing guarded operations.
// A recorded plan ID is never replayed, even after a lost reply or restart.
const {createHash}=require('node:crypto');
const {digest}=require('./task-intake.cjs');
const SEQUENCE_TOOLS=['move','place','build','craft','dig','set_open','till'];
class ActionSequence {
 constructor(history){this.history=history;this.active=null;}
 status(){return this.active?{id:this.active.id,status:'running',completed:this.active.results.length,cancel_requested:!!this.active.cancel_reason}:null;}
 cancel(reason='planner_cancelled'){if(!this.active)return {cancel_requested:false};this.active.cancel_reason=reason;return {cancel_requested:true,id:this.active.id,current_step_may_still_be_running:true};}
 async run({plan_id,steps}, {guard,execute}){
  const hash=digest(steps),records=this.history.data.action_sequences||[];
  const previous=records.find(r=>r.id===plan_id);
  if(previous){if(previous.hash!==hash)throw Error('Plan ID already binds a different sequence');return {...previous,status:previous.status==='running'?'interrupted':previous.status,duplicate:true,replayed:false};}
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
