// A context token authorizes queries, never game commands. The grant view only
// contains public game messages, including after migration from WorkshopState.
const {isPublicChatEvent}=require('./public-chat.cjs');
const {publicSource}=require('./source-revision.cjs');
function query(request,cfg,history,activity) {
  const owner=request.access?.mode==='owner';
  if (!owner && (request.access?.mode!=='grant'||!cfg.context_grant||request.access.grant!==cfg.context_grant))
    throw Error('Invalid conversation grant');
  const id=cfg.conversation_id||'minecraft:workshop';
  if(request.conversation_id && request.conversation_id!==id) throw Error('Unknown conversation');
  const observed_at=new Date().toISOString();
  const events=[...(history.legacy.events||[]),...history.data.events].filter(isPublicChatEvent);
  const current={id,conversation_id:id,label:'Minecraft — '+cfg.username,surface:'minecraft',observed_at,activity,
    updated_at:events.at(-1)?.time,coverage:'Retained public Minecraft messages.'};
  if(request.operation==='list') return {items:[{...current,read:{operation:'read',conversation_id:id}}],complete:true,observed_at};
  if(request.operation==='authorize') return {owner:false,conversation_id:id,actor_id:'minecraft:'+cfg.username,surface:'minecraft',label:current.label,observed_at};
  if(!['read','orientation'].includes(request.operation))throw Error('Unsupported context operation');
  const limit=Math.max(1,Math.min(40,Number(request.limit)||20));
  const messages=events.slice(-limit).map(e=>({id:e.id,at:e.time,actor:e.username||cfg.username,text:e.message||e.sent||'',label:e.kind,source_fact:publicSource(e)}));
  return {conversation_id:id,current,messages,complete:events.length<=limit,observed_at};
}
module.exports={query};
