// Observe Mineflayer's normal placement settlement; never send or retry packets.
const refusals=new WeakMap();
async function attempt(bot,support,target,item,send){
 const before=bot.blockAt(target);let acknowledged=false,unchanged=null;
 const referenceEvent=`blockUpdate:${support.position}`,targetEvent=`blockUpdate:${target}`;
 const reference=()=>{acknowledged=true;};
 const update=(_old,next)=>{if(acknowledged&&before&&next&&Number.isInteger(before.type)&&next.type===before.type&&next.name===before.name)unchanged={name:next.name,type:next.type};else unchanged=null;};
 bot.on(referenceEvent,reference);bot.on(targetEvent,update);
 try{return await send();}catch(error){
  // Exact upstream terminal refusal plus ordered server observations. A timeout,
  // unloaded block, bare matching text or a later differing update stays unknown.
  if(unchanged&&error.message===`Server refused to place ${item} at ${target}: the block is still ${unchanged.name}`)
   refusals.set(error,{kind:'server_refused_placement',target:{x:target.x,y:target.y,z:target.z},observed:unchanged,reference_acknowledged:true,target_acknowledged:true});
  throw error;
 }finally{bot.removeListener(referenceEvent,reference);bot.removeListener(targetEvent,update);}
}
module.exports={attempt,refusal:error=>refusals.get(error)};
