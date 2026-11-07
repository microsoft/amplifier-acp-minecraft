// Local transcript evidence, never authority copied from a peer's payload.
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function enabled(cfg){return cfg.human_task_intake?.enabled===true&&cfg.human_task_intake?.delegation?.enabled===true;}
function publicSource(e,now,cutoff=0){
 const at=Date.parse(e?.time);
 return e?.kind==='chat'&&!e.whisper&&e.provenance==='minecraft_public_chat'&&e.transport?.kind==='server_player_uuid'&&e.transport.username===e.username&&uuid.test(e.transport.uuid||'')&&Number.isFinite(at)&&at>cutoff&&at<=now+5000&&at>now-600000;
}
function humans(history,cfg,now){return enabled(cfg)?history.data.events.filter(e=>e.source==='human'&&publicSource(e,now,history.data.task_source_cutoff||0)).slice(-16):[];}
function peer(history,cfg,message,now){
 const e=history.data.events.find(e=>e.id===message.id);
 return enabled(cfg)&&message.source==='agent'&&e?.source==='agent'&&e.accepted===true&&e.intent==='request'&&publicSource(e,now,history.data.task_source_cutoff||0)&&(cfg.bot_names||[]).some(n=>n.toLowerCase()===e.username.toLowerCase())&&humans(history,cfg,now).length>0?e:null;
}
module.exports={enabled,publicSource,humans,peer};
