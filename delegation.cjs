// Local transcript evidence, never authority copied from a peer's payload.
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function enabled(cfg){return cfg.human_task_intake?.enabled===true&&cfg.human_task_intake?.delegation?.enabled===true;}
function publicSource(e,now,cutoff=0,maxAge=600000){
 const at=Date.parse(e?.time);
 return e?.kind==='chat'&&!e.whisper&&e.provenance==='minecraft_public_chat'&&e.transport?.kind==='server_player_uuid'&&e.transport.username===e.username&&uuid.test(e.transport.uuid||'')&&Number.isFinite(at)&&at>cutoff&&at<=now+5000&&(maxAge===null||at>now-maxAge);
}
function humans(history,cfg,now,{existing=false}={}){
 if(!enabled(cfg))return [];
 const task=history.task(),start=Date.parse(task?.started_at);
 const retained=existing&&task?.authority?.kind==='human_game_request'&&['running','waiting'].includes(task.status)&&Number.isFinite(start);
 const events=[...new Map([...(retained?history.data.public_conversation_history||[]:[]),...history.data.events].map(e=>[e.id,e])).values()];
 const result=events.filter(e=>e.source==='human'&&publicSource(e,now,history.data.task_source_cutoff||0,retained?null:600000)&&(!retained||Date.parse(e.time)>=start)).slice(-16);
 // Acceptance follows its original request. Retain that exact authority even
 // when its public event has aged out; unrelated pre-assignment chat is not a grant.
 const s=task?.authority?.source;
 if(retained&&s?.actor?.kind==='human'&&s.audience?.kind==='public'&&s.audience.experience==='minecraft'&&s.evidence_origin==='server_player_uuid'){
  const original={id:s.id,kind:'chat',source:'human',username:s.username,message:s.message,time:s.time,transport:s.transport,provenance:'minecraft_public_chat',accepted:true,accepted_task_source:s};
  if(publicSource(original,now,history.data.task_source_cutoff||0,null)&&!result.some(e=>e.id===s.id))result.unshift(original);
 }
 return result;
}
function peer(history,cfg,message,now){
 const e=history.data.events.find(e=>e.id===message.id);
 return enabled(cfg)&&message.source==='agent'&&e?.source==='agent'&&e.accepted===true&&e.intent==='request'&&publicSource(e,now,history.data.task_source_cutoff||0)&&(cfg.bot_names||[]).some(n=>n.toLowerCase()===e.username.toLowerCase())&&humans(history,cfg,now).length>0?e:null;
}
// Conversational delivery is not helper-task admission. A peer can report a
// dependency after the original human request has aged out of intake evidence.
function conversation(history,cfg,message,now){
 const e=history.data.events.find(e=>e.id===message.id);
 return cfg.human_engagement?.enabled===true&&cfg.agent_dialogue===true&&message.source==='agent'&&e?.source==='agent'&&e.accepted===true&&
  publicSource(e,now,history.data.task_source_cutoff||0)&&(cfg.bot_names||[]).some(n=>n.toLowerCase()===e.username.toLowerCase())&&
  (message.attention_offer?.ticket||e.intent==='request')?e:null;
}
module.exports={enabled,publicSource,humans,peer,conversation};
