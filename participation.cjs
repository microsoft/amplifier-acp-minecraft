// Map this player's public conversation to the shared agent participation policy.
// Private messages, world geometry and provider-specific questions stay out.
const crypto=require('node:crypto');
const {isPublicChatEvent}=require('./public-chat.cjs');
const {publicSource}=require('./source-revision.cjs');
const {messageEnvelope}=require('./watch-bridge.cjs');
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
  data.participation_pending=[...new Set([...(data.participation_pending||[]),event.id])];
  this.history.save();
 }
 proposal(players,{humanOnly=false,sourceId=null}={}){
  const data=this.history.data;
  const now=Date.now(),byId=new Map(data.events.map(e=>[e.id,e]));
  const pending=(data.participation_pending||[]).filter(id=>{
   const e=byId.get(id),at=Date.parse(e?.time);
   return e&&!e.accepted&&isPublicChatEvent(e)&&Number.isFinite(at)&&at<=now+5000&&now-at<600000;
  });
  if(pending.length!==(data.participation_pending||[]).length){
   const removed=(data.participation_pending||[]).filter(id=>!pending.includes(id));
   data.participation_outcomes=[...(data.participation_outcomes||[]),...removed.map(id=>({id,at:now,outcome:'expired_or_unavailable'}))].slice(-1000);
   data.participation_pending=pending;
   for(const id of removed)if(data.participation_proposals)delete data.participation_proposals[id];
   this.history.save();
  }
  const fresh=pending.map(id=>byId.get(id)).filter(e=>(!humanOnly||e.source==='human')&&(!sourceId||e.id===sourceId));
  // Each input owns its own outcome. A peer or a newer human input cannot
  // consume another human source merely by sharing its contextual snapshot.
  const trigger=fresh.find(e=>e.source==='human')||fresh[0];
  if(!trigger)return null;
  const sourceKey=crypto.createHash('sha256').update(JSON.stringify([publicSource(trigger),trigger.transport])).digest('hex');
  const cached=data.participation_proposals?.[trigger.id];
  if(cached?.source_key===sourceKey)return structuredClone(cached);
  const publicEvents=data.events.filter(isPublicChatEvent);
  const selected=new Set([...publicEvents.slice(-23).map(e=>e.id),trigger.id]);
  // Retain recorded source order, including newer evidence after an old trigger.
  // trigger_id identifies the evaluated source; list position does not.
  const chat=publicEvents.filter(e=>selected.has(e.id));
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
   // Only the visible first-address convention is projected. The watch bridge's
   // default request intent is not evidence of intent, authority or completion.
   messages:chat.map(e=>({id:e.id,sender:e.username||this.cfg.username,text:(e.message||e.sent||'').slice(0,700),
    recipients:messageEnvelope(this.cfg,e).recipients})),
   trigger_id:trigger.id,
   responsibilities:JSON.stringify({goal:data.task?.goal,status:data.task?.status,progress:data.task?.progress?.at(-1)?.summary}).slice(0,1500)};
  const ids=[trigger.id];
  const sources=chat.map(publicSource).filter(Boolean);
  const signature=crypto.createHash('sha256').update(JSON.stringify({context,ids,sources})).digest('hex');
  const proposal={context,ids,signature,occurred_at:Date.parse(trigger.time),sources,source_key:sourceKey};
  data.participation_proposals={...(data.participation_proposals||{}),[trigger.id]:proposal};this.history.save();
  return structuredClone(proposal);
 }
 // These are existing local delivery constraints, not social/model policy.
 // Recompute on both GET and POST; a preflight result never grants admission.
 deliveryStatus(proposal,inbox,{lastHumanAt=0,agentWakeTimes=[]}={},now=Date.now()){
  if(!proposal)return {eligible:false,reason_code:'source_changed'};
  const ids=new Set(proposal.ids),data=this.history.data;
  const peerCount=data.events.filter(e=>ids.has(e.id)&&e.source==='agent').length;
  if(peerCount&&this.cfg.human_engagement?.enabled!==true){
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
  if(data.participation_proposals)for(const id of ids)delete data.participation_proposals[id];
  data.participation_outcomes=[...(data.participation_outcomes||[]),...Array.from(ids,id=>({id,at:Date.now(),outcome:result.action}))].slice(-1000);
  this.history.save();
  return {queued:result.action==='engage',action:result.action,acp_admitted:false,message_ids:[...ids],trigger_id:proposal.context.trigger_id,signature:proposal.signature};
 }
}
module.exports={Participation,ParticipationRejection};
