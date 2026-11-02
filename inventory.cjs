// A read-only inventory resync for the pinned state-ID Minecraft protocol.
// Use the same no-op stale-state click as Mineflayer's window sync, with a
// bounded wait and cleanup. Never infer inventory from local click predictions.
const {once}=require('node:events');
async function refreshInventory(bot){
 if(!bot.supportFeature('stateIdUsed'))throw Error('Inventory verification needs a state-ID Minecraft protocol');
 const window=bot.currentWindow||bot.inventory,Item=require('prismarine-item')(bot.registry);
 const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),5000);
 const ack=once(bot,`setWindowItems:${window.id}`,{signal:abort.signal});
 try{
  bot._client.write('window_click',{windowId:window.id,stateId:-1,slot:-999,mouseButton:2,mode:5,changedSlots:[],cursorItem:Item.toNotch(window.selectedItem)});
  await ack;
  return {cursor:window.selectedItem?{name:window.selectedItem.name,count:window.selectedItem.count}:null,crafting_grid:window.slots.slice(1,window===bot.inventory?5:window.type.startsWith('minecraft:crafting')?10:1).map(i=>i?{name:i.name,count:i.count}:null),items:window.items().map(i=>({name:i.name,count:i.count})),verified_at:new Date().toISOString(),source:'server inventory snapshot'};
 }finally{clearTimeout(timer);abort.abort();await ack.catch(()=>{});}
}
module.exports={refreshInventory};
