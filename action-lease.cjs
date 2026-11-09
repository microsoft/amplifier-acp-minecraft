// Controller liveness is not model/provider liveness. This lease only bounds
// the current body's effects; it never creates/renews assignment authority.
const bounds=require('./task-bounds.cjs');
const {randomUUID}=require('node:crypto');
class ActionLease {
 constructor({windowMs=240000,now=Date.now}={}){this.windowMs=windowMs;this.now=now;this.clear();}
 clear(){this.id=null;this.turn=null;this.binding=null;this.until=0;}
 begin(turn,task,renewable){
  this.clear();this.id=randomUUID();this.turn=turn;
  this.enabled=renewable===true;
  this.until=this.now()+this.windowMs;
  this.bind(task);return this.view(task);
 }
 bind(task){
  if(this.turn?.activity||this.binding||!task||!bounds.valid(task)||task.status!=='running'||task.id!==this.turn?.task_id)return;
  this.binding={task_id:task.id,deadline:task.deadline,max_turns:task.max_turns,turns:task.turns,bounds_key:JSON.stringify(bounds.get(task)),authority_revision:task.authority_revision};
  this.until=bounds.clamp(task,this.until);
 }
 eligible(task,turn=this.turn){
  const b=this.binding;
  if(this.turn?.activity)return !!(this.enabled&&this.id&&this.until>this.now()&&turn===this.turn);
  return !!(this.enabled&&this.id&&this.until>this.now()&&turn===this.turn&&b&&
   task?.id===b.task_id&&task.status==='running'&&task.deadline===b.deadline&&
   task.max_turns===b.max_turns&&task.turns===b.turns&&bounds.within(task,{now:this.now(),currentTurn:true})&&JSON.stringify(bounds.get(task))===b.bounds_key&&task.authority_revision===b.authority_revision);
 }
 renew(request,task,turn){
  if(request.lease_id!==this.id||request.task_id!==(this.binding?.task_id??null)||!this.eligible(task,turn))
   throw Error('Action lease changed, expired, or no longer authorized; inspect without replay');
  this.until=this.turn?.activity?this.now()+this.windowMs:bounds.clamp(task,this.now()+this.windowMs);
  return this.view(task);
 }
 view(task){return {version:1,lease_id:this.id,task_id:this.binding?.task_id||null,
  expires_at:this.until,assignment_deadline:this.binding?.deadline??null,assignment_bounds:this.binding?JSON.parse(this.binding.bounds_key):null,
  renewable:this.eligible(task),window_ms:this.windowMs};}
}
module.exports={ActionLease};
