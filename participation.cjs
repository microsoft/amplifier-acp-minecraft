// Map this player's public conversation to the shared agent participation policy.
// Private messages, world geometry and provider-specific questions stay out.
const crypto=require('node:crypto');
class Participation {
 constructor(history,cfg){this.history=history;this.cfg=cfg;}
 get enabled(){return this.cfg.conversation_attention?.enabled===true;}
 queue(event){
  const data=this.history.data;
  data.participation_pending=[...(data.participation_pending||[]),event.id].slice(-8);
  this.history.save();
 }
 proposal(players){
  const data=this.history.data;
  const pending=new Set(data.participation_pending||[]);
  const fresh=data.events.filter(e=>pending.has(e.id)&&!e.whisper&&Date.now()-Date.parse(e.time)<600000);
  if(!fresh.length)return null;
  const chat=data.events.filter(e=>!e.whisper&&['chat','chat_sent'].includes(e.kind)).slice(-24);
  const names=[...new Set([this.cfg.username,...chat.map(e=>e.username||this.cfg.username),...players])].slice(0,64);
  const participants=names.map(name=>({id:name,name,is_agent:name===this.cfg.username||(this.cfg.bot_names||[]).includes(name),role:name===this.cfg.username?(this.cfg.conversation_attention?.role||''):''}));
  const context={conversation_id:this.cfg.conversation_id||'minecraft:workshop',
   agent:participants.find(p=>p.id===this.cfg.username),participants,
   messages:chat.map(e=>({id:e.id,sender:e.username||this.cfg.username,text:(e.message||e.sent||'').slice(0,700)})),
   trigger_id:fresh.at(-1).id,
   responsibilities:JSON.stringify({goal:data.task?.goal,status:data.task?.status,progress:data.task?.progress?.at(-1)?.summary}).slice(0,1500)};
  // The trigger may fall outside bounded context after a long burst. Leave the
  // newest visible candidate only; old public chat remains recorded, not replayed.
  if(!context.messages.some(m=>m.id===context.trigger_id))return null;
  const ids=fresh.filter(e=>context.messages.some(m=>m.id===e.id)).map(e=>e.id);
  const signature=crypto.createHash('sha256').update(JSON.stringify({context,ids})).digest('hex');
  return {context,ids,signature};
 }
 apply(proposal,result,inbox){
  if(!proposal||result.signature!==proposal.signature)throw Error('Conversation changed during participation assessment');
  if(!['engage','hold'].includes(result.action))throw Error('Invalid participation action');
  const ids=new Set(proposal.ids),data=this.history.data;
  if(result.action==='engage'){
   if(inbox.length+ids.size>8)throw Error('Conversation inbox is full; retry after processing queued messages');
   for(const e of data.events.filter(e=>ids.has(e.id))){
    e.accepted=true;
    inbox.push({id:e.id,username:e.username,message:e.message,source:e.source,whisper:false});
   }
  }
  data.participation_pending=(data.participation_pending||[]).filter(id=>!ids.has(id));
  this.history.save();
  return {admitted:result.action==='engage',message_ids:[...ids],trigger_id:proposal.context.trigger_id,signature:proposal.signature};
 }
}
module.exports={Participation};
