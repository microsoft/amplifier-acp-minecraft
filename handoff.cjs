// A physical handoff observed through Minecraft packets, not another agent's
// private state. Merges or ambiguous drops remain unconfirmed, never retried.
const {refreshInventory}=require('./inventory.cjs');
const {describe}=require('./survival.cjs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function pickupTracker({item,count,origin,existing,recipient,sender}){
 const drops=new Map();const collected=new Map();let ambiguous=false;
 return {
  drop(e,stack){
   if(existing.has(e.id)||e.name!=='item'||stack?.name!==item||e.position.distanceTo(origin)>.8||drops.has(e.id))return;
   drops.set(e.id,{id:e.id,uuid:e.uuid,count:stack.count});
   if([...drops.values()].reduce((n,d)=>n+d.count,0)>count)ambiguous=true;
  },
  collect(p){
   const d=drops.get(p.collectedEntityId);if(!d||!Number.isInteger(p.pickupItemCount)||p.pickupItemCount<1)return;
   const prior=collected.get(d.id)||{total:0,by:{}};
   const amount=Math.min(p.pickupItemCount,d.count-prior.total);
   prior.total+=amount;prior.by[p.collectorEntityId]=(prior.by[p.collectorEntityId]||0)+amount;collected.set(d.id,prior);
  },
  result(bot){
   const total=who=>[...collected.values()].reduce((n,d)=>n+(d.by[who]||0),0);
   const received=total(recipient),recovered=total(sender);
   return {status:!ambiguous&&received===count?'pickup_observed':recovered===count?'recovered_by_sender':'unconfirmed',recipient_pickup_observed:received,sender_recovered:recovered,ambiguous,
    drops:[...drops.values()].map(d=>({...d,collected:collected.get(d.id)?.total||0,position:bot.entities[d.id]?.uuid===d.uuid?bot.entities[d.id].position.clone():null}))};
  }
 };
}
function preflight(bot,a){
 if(a.player===bot.username)throw Error('Choose another player');
 const target=bot.players[a.player]?.entity;
 const near=()=>bot.players[a.player]?.entity===target&&target&&target.position.distanceTo(bot.entity.position)<=2.5;
 if(!near())throw Error('Meet the recipient within 2.5 blocks first; give does not chase players');
 const spacing=()=>Math.hypot(target.position.x-bot.entity.position.x,target.position.z-bot.entity.position.z)>=1.8&&Math.abs(target.position.y-bot.entity.position.y)<=.5;
 if(!spacing())throw Error('Stand about two blocks apart on the same level (1.8–2.5 blocks); closer drops can be picked back up by the sender');
 return {target,near,spacing};
}
async function give(bot,a,check,{beforeTransfer=()=>{}}={}){
 const {target,near,spacing}=preflight(bot,a);
 const initial=target.position.clone();await delay(500);check();
 if(!near()||target.position.distanceTo(initial)>.15)throw Error('Recipient is moving; agree on a meeting spot and wait until they stand still');
 await refreshInventory(bot);check();
 const items=bot.inventory.items();let item=items.find(i=>i.name===a.item&&i.count===a.count)||items.find(i=>i.name===a.item&&i.count>=a.count);const before=items.filter(i=>i.name===a.item).reduce((n,i)=>n+i.count,0);
 if(before<a.count)throw Error('Insufficient server-confirmed inventory');
 if(!item)throw Error('Choose a count available in one stack; this handoff does not consolidate separate stacks');
 // Mineflayer toss(count) drops partial stacks one item at a time. Prepare
 // one exact stack using ordinary inventory clicks, then drop it once.
 beforeTransfer();
 if(item.count!==a.count){
  const slot=bot.inventory.firstEmptyInventorySlot();if(slot===null)throw Error('An empty inventory slot is needed to prepare this exact handoff');
  await bot.transfer({window:bot.inventory,itemType:item.type,metadata:item.metadata,count:a.count,sourceStart:item.slot,sourceEnd:item.slot+1,destStart:slot,destEnd:slot+1});check();
  await refreshInventory(bot);check();item=bot.inventory.slots[slot];
  if(item?.name!==a.item||item.count!==a.count)throw Error('Server did not confirm the prepared stack; nothing was intentionally dropped');
 }
 const eye=bot.entity.position.offset(0,1.62,0),delta=target.position.offset(0,.5,0).minus(eye);
 if(bot.world.raycast(eye,delta.scaled(1/delta.norm()),delta.norm()))throw Error('Recipient is behind a block; meet in a clear space');
 await bot.lookAt(target.position.offset(0,.2,0),false);check();
 if(!near()||!spacing()||target.position.distanceTo(initial)>.15)throw Error('Recipient moved before the handoff; nothing was dropped');
 beforeTransfer(); // Recheck after asynchronous inventory, aim and recipient checks.
 const tracker=pickupTracker({item:a.item,count:a.count,origin:bot.entity.position.offset(0,1.32,0),existing:new Set(Object.values(bot.entities).map(e=>e.id)),recipient:target.id,sender:bot.entity.id});
 const onDrop=e=>tracker.drop(e,describe(bot,e).item),onCollect=p=>tracker.collect(p);
 bot.on('itemDrop',onDrop);bot._client.on('collect',onCollect);
 try{
  await bot.tossStack(item);check();
  for(let i=0;i<35;i++){await delay(100);check();if(tracker.result(bot).status==='pickup_observed')break;}
  const inventory=await refreshInventory(bot);check();
  const after=inventory.items.filter(i=>i.name===a.item).reduce((n,i)=>n+i.count,0),result=tracker.result(bot);
  if(before-after!==a.count&&result.status==='pickup_observed')result.status='unconfirmed';
  return {...result,item:a.item,requested:a.count,recipient:a.player,sender_inventory_change:after-before,inventory:inventory.items,position:bot.entity.position.clone(),evidence:'Nearby new item entities and server pickup packets, plus sender inventory snapshot',guidance:result.status==='pickup_observed'?'Pickup observed for the intended recipient. Send an update only if useful; no acknowledgment loop is needed.':'Do not repeat give automatically. Inspect drop positions and ask the recipient to collect or verify inventory. Drops can merge or be collected by someone else.'};
 }finally{bot.removeListener('itemDrop',onDrop);bot._client.removeListener('collect',onCollect);}
}
module.exports={give,preflight,pickupTracker};
