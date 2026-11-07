// Map this player's public conversation to the shared agent participation policy.
// Private messages, world geometry and provider-specific questions stay out.
const crypto=require('node:crypto');
const {isPublicChatEvent}=require('./public-chat.cjs');
const {publicSource}=require('./source-revision.cjs');
const REJECTIONS={
 source_changed:[409,'Conversation changed during participation assessment'],
 invalid_action:[400,'Invalid participation action'],
 non_public_evidence:[409,'Participation evidence is not public game chat'],
 inbox_full:[429,'Conversation inbox is full; retry after processing queued messages'],
 disabled:[409,'Conversation attention is not enabled'],
 peer_window_expired:[409,'Peer participation human-activity window expired'],
 peer_budget_exhausted:[429,'Peer participation budget exhausted']
};
class ParticipationRejection extends Error {
 constructor(code){const [status,message]=REJECTIONS[code];super(message);this.code=code;this.status=status;}
}
class Participation {
 constructor(history,cfg){this.history=history;this.cfg=cfg;}
 get enabled(){return this.cfg.conversation_attention?.enabled===true;}
 queue(event){
  if(!isPublicChatEvent(event))return;
  const data=this.history.data;
  data.participation_pending=[...(data.participation_pending||[]),event.id].slice(-8);
  this.history.save();
 }
 proposal(players,{humanOnly=false}={}){
  const data=this.history.data;
  const pending=new Set(data.participation_pending||[]);
  const fresh=data.events.filter(e=>pending.has(e.id)&&(!humanOnly||e.source==='human')&&isPublicChatEvent(e)&&Date.now()-Date.parse(e.time)<600000);
  if(!fresh.length)return null;
  const chat=data.events.filter(isPublicChatEvent).slice(-24);
  const names=[...new Set([this.cfg.username,...chat.map(e=>e.username||this.cfg.username),...players])].slice(0,64);
  const agents=new Set([this.cfg.username,...(this.cfg.bot_names||[])].map(name=>name.toLowerCase()));
  const participants=names.map(name=>{
   if(agents.has(name.toLowerCase()))return {id:name,name,is_agent:true,role:''};
   const messages=chat.filter(e=>e.username===name);
   // Participant kind applies to every message under this actor ID. Never let
   // a verified message upgrade unattributed history from the same display name.
   const human=messages.length>0&&messages.every(e=>e.kind==='chat'&&e.source==='human'
    &&e.transport?.kind==='server_player_uuid'&&e.transport.username===name
    &&typeof e.transport.uuid==='string'
    &&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(e.transport.uuid));
   return {id:name,name,...(human?{is_agent:false}:{}),role:''};
  });
  const context={conversation_id:this.cfg.conversation_id||'minecraft:workshop',
   agent:participants.find(p=>p.id===this.cfg.username),participants,
   messages:chat.map(e=>({id:e.id,sender:e.username||this.cfg.username,text:(e.message||e.sent||'').slice(0,700)})),
   trigger_id:fresh.at(-1).id,
   responsibilities:JSON.stringify({goal:data.task?.goal,status:data.task?.status,progress:data.task?.progress?.at(-1)?.summary}).slice(0,1500)};
  // The trigger may fall outside bounded context after a long burst. Leave the
  // newest visible candidate only; old public chat remains recorded, not replayed.
  if(!context.messages.some(m=>m.id===context.trigger_id))return null;
  const ids=fresh.filter(e=>context.messages.some(m=>m.id===e.id)).map(e=>e.id);
  const sources=chat.map(publicSource).filter(Boolean);
  const signature=crypto.createHash('sha256').update(JSON.stringify({context,ids,sources})).digest('hex');
  return {context,ids,signature,occurred_at:Date.parse(fresh.at(-1).time),sources};
 }
 // These are existing local delivery constraints, not social/model policy.
 // Recompute on both GET and POST; a preflight result never grants admission.
 deliveryStatus(proposal,inbox,{lastHumanAt=0,agentWakeTimes=[]}={},now=Date.now()){
  if(!proposal)return {eligible:false,reason_code:'source_changed'};
  const ids=new Set(proposal.ids),data=this.history.data;
  const peerCount=data.events.filter(e=>ids.has(e.id)&&e.source==='agent').length;
  if(peerCount){
   if(now-lastHumanAt>=(this.cfg.agent_dialogue_window_seconds||2400)*1000)return {eligible:false,reason_code:'peer_window_expired'};
   const recent=agentWakeTimes.filter(t=>t>now-3600000).length;
   if(recent+peerCount>Math.min(60,Math.max(1,this.cfg.peer_wakes_per_hour||4)))return {eligible:false,reason_code:'peer_budget_exhausted'};
  }
  if(inbox.length+ids.size>8)return {eligible:false,reason_code:'inbox_full'};
  return {eligible:true};
 }
 validate(proposal,result){
  if(!proposal||result.signature!==proposal.signature)throw new ParticipationRejection('source_changed');
  if(!['engage','hold'].includes(result.action))throw new ParticipationRejection('invalid_action');
  const ids=new Set(proposal.ids),data=this.history.data;
  if([...ids].some(id=>!data.events.some(e=>e.id===id&&isPublicChatEvent(e))))throw new ParticipationRejection('non_public_evidence');
  // Source consumption and inbox persistence share one synchronous save. A
  // lost HTTP reply never makes the same source eligible for another delivery,
  // even if a caller retained the pre-acceptance proposal or the body reloaded.
  const pending=new Set(data.participation_pending||[]);
  if(!ids.size||[...ids].some(id=>!pending.has(id)||data.events.find(e=>e.id===id)?.accepted))throw new ParticipationRejection('source_changed');
 }
 apply(proposal,result,inbox){
  this.validate(proposal,result);
  const ids=new Set(proposal.ids),data=this.history.data;
  if(result.action==='engage'){
   if(inbox.length+ids.size>8)throw new ParticipationRejection('inbox_full');
   for(const e of data.events.filter(e=>ids.has(e.id))){
    e.accepted=true;
    inbox.push({id:e.id,username:e.username,message:e.message,source:e.source,whisper:false,...(result.offer?{attention_offer:result.offer}:{})});
   }
  }
  data.participation_pending=(data.participation_pending||[]).filter(id=>!ids.has(id));
  this.history.save();
  return {queued:result.action==='engage',action:result.action,acp_admitted:false,message_ids:[...ids],trigger_id:proposal.context.trigger_id,signature:proposal.signature};
 }
}
module.exports={Participation,ParticipationRejection};
