// One self-authored conversation input. It is neither human evidence nor work
// authority. Admission consumes it durably before the controller calls ACP.
const crypto=require('node:crypto');
class ConversationFollowUp {
 constructor(history,{now=Date.now,blocked=()=>null,conversationAllowed=()=>true}={}){
  this.history=history;this.now=now;this.blocked=blocked;this.conversationAllowed=conversationAllowed;
 }
 reason(){
  const d=this.history.data;
  if(d.activity_stop||d.task?.status==='stopped')return 'explicit_stop';
  if(!this.conversationAllowed())return 'conversation_disabled';
  if((d.last_conversation_turn?.actions||[]).some(a=>['pending','uncertain'].includes(a.status)&&a.review?.outcome!=='no_effect'))return 'unresolved_conversation_effects';
  return this.blocked();
 }
 view(){const r=this.history.data.conversation_follow_up;return r?{...r}:{status:'none'};}
 commit(change){
  // Keep the body's shared inbox array identity on both success and failure.
  const d=this.history.data,old=d.conversation_follow_up,inbox=d.inbox||(d.inbox=[]),messages=[...inbox];
  try{change(d,inbox);this.history.save();}catch(error){d.conversation_follow_up=old;inbox.splice(0,inbox.length,...messages);throw error;}
  return this.view();
 }
 set({after_seconds,goal}){
  if(!Number.isInteger(after_seconds)||after_seconds<0||after_seconds>3600)throw Error('after_seconds must be an integer from 0 through 3600');
  if(after_seconds===0){
   if(!['scheduled','queued'].includes(this.view().status))return this.view();
   return this.commit(d=>cancel(d,'cancelled',this.now()));
  }
  if(typeof goal!=='string'||!goal.trim()||goal.length>2000)throw Error('A nonempty follow-up goal of at most 2000 characters is required');
  const reason=this.reason();if(reason)throw Error('Follow-up unavailable: '+reason);
  const turn=this.history.data.turn;
  if(turn?.reply_route||turn?.reply_recipient||turn?.huddle_room_id)throw Error('Follow-up is scoped to this public game conversation');
  return this.commit((d,inbox)=>{
   const prior=d.conversation_follow_up;
   if(prior?.status==='queued')for(let i=inbox.length-1;i>=0;i--)if(inbox[i].id===prior.id&&inbox[i].source==='follow_up')inbox.splice(i,1);
   d.conversation_follow_up={id:crypto.randomUUID(),status:'scheduled',goal,created_at:this.now(),due_at:this.now()+after_seconds*1000};
  });
 }
 poll(){
  const r=this.view();
  if(r.status!=='scheduled'||this.now()<r.due_at)return r;
  const blocked=this.reason();if(blocked)return {...r,blocked_reason:blocked};
  return this.commit((d,inbox)=>{
   d.conversation_follow_up={...r,status:'queued'};
   inbox.push({id:r.id,source:'follow_up',message:r.goal,reply_scope:'follow_up:'+r.id});
  });
 }
 eligible(message){
  const r=this.view();
  return !this.reason()&&r.status==='queued'&&this.now()>=r.due_at&&message.id===r.id&&message.source==='follow_up'&&message.message===r.goal&&message.reply_scope==='follow_up:'+r.id&&!message.whisper&&!message.attention_offer&&!message.source_fact;
 }
}
function cancel(data,reason='explicit_stop',now=Date.now()){
 const r=data.conversation_follow_up;if(!r||!['scheduled','queued'].includes(r.status))return;
 const inbox=data.inbox||[];for(let i=inbox.length-1;i>=0;i--)if(inbox[i].source==='follow_up'&&inbox[i].id===r.id)inbox.splice(i,1);
 data.conversation_follow_up={...r,status:'cancelled',reason,cancelled_at:now};
}
module.exports={ConversationFollowUp,cancel};
