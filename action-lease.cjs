// Controller liveness is not model/provider liveness. This lease only bounds
// the current body's effects; it never creates/renews assignment authority.
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
  if(this.binding||!task||task.status!=='running'||task.id!==this.turn?.task_id)return;
  this.binding={task_id:task.id,deadline:task.deadline,max_turns:task.max_turns,turns:task.turns};
  this.until=Math.min(this.until,task.deadline);
 }
 eligible(task,turn=this.turn){
  const b=this.binding;
  return !!(this.enabled&&this.id&&this.until>this.now()&&turn===this.turn&&b&&
   task?.id===b.task_id&&task.status==='running'&&task.deadline===b.deadline&&
   task.max_turns===b.max_turns&&task.turns===b.turns&&task.turns<=b.max_turns&&b.deadline>this.now());
 }
 renew(request,task,turn){
  if(request.lease_id!==this.id||request.task_id!==this.binding?.task_id||!this.eligible(task,turn))
   throw Error('Action lease changed, expired, or no longer authorized; inspect without replay');
  this.until=Math.min(this.now()+this.windowMs,this.binding.deadline);
  return this.view(task);
 }
 view(task){return {version:1,lease_id:this.id,task_id:this.binding?.task_id||null,
  expires_at:this.until,assignment_deadline:this.binding?.deadline||null,
  renewable:this.eligible(task),window_ms:this.windowMs};}
}
module.exports={ActionLease};
