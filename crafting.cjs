// Server-confirmed crafting clicks; never synthesize output or trust local predictions.
const {once}=require('node:events');
const {refreshInventory}=require('./inventory.cjs');
const {inventoryBarrier}=require('./inventory-barrier.cjs');
const counts=items=>{const n={};for(const i of items)n[i.name]=(n[i.name]||0)+i.count;return n;};
async function click(bot,slot,button,check){
 check();const window=bot.currentWindow||bot.inventory,Item=require('prismarine-item')(bot.registry);
 if(!bot.supportFeature('stateIdUsed'))throw Error('Confirmed crafting needs a state-ID protocol');
 const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),5000);
 const ack=once(bot,`setWindowItems:${window.id}`,{signal:abort.signal});
 try{
  // An ordinary click with an intentionally stale state ID requests authoritative
  // resync after the server applies it. No client-side slot/output prediction.
  bot._client.write('window_click',{windowId:window.id,stateId:-1,slot,mouseButton:button,mode:0,changedSlots:[],cursorItem:Item.toNotch(window.selectedItem)});
  await ack;await inventoryBarrier(bot);check();
 }finally{clearTimeout(timer);abort.abort();await ack.catch(()=>{});}
}
async function parkCursor(bot,window,check){
 for(let n=0;window.selectedItem&&n<40;n++){
  const held=window.selectedItem;
  const partial=window.items().find(i=>i.type===held.type&&i.count<i.stackSize&&i.metadata===held.metadata);
  const slot=partial?.slot??window.firstEmptySlotRange(window.inventoryStart,window.inventoryEnd);
  if(slot===null||slot===undefined)throw Error('No inventory space to return crafting cursor; no items dropped');
  const before=held.count;await click(bot,slot,0,check);
  if(window.selectedItem&&window.selectedItem.count>=before)throw Error('Server did not confirm returning crafting cursor; inspect before retrying');
 }
 if(window.selectedItem)throw Error('Crafting cursor recovery exceeded its bound');
}
async function prepare(bot,check){
 await refreshInventory(bot);check();const window=bot.currentWindow||bot.inventory;
 if(window!==bot.inventory&&!window.type.startsWith('minecraft:crafting'))throw Error('Close the other container before crafting');
 await parkCursor(bot,window,check);
 const size=window===bot.inventory?4:9;
 for(let slot=1;slot<=size;slot++)if(window.slots[slot]){await click(bot,slot,0,check);await parkCursor(bot,window,check);}
 return window;
}
async function craft(bot,item,count,table,check){
 let window=await prepare(bot,check),completed=0,produced=0;
 const before=counts(window.items());
 try{
  for(let n=0;n<count;n++){
   check();await refreshInventory(bot);check();
   let recipe=bot.recipesFor(item.id,null,1,window===bot.inventory?null:table)[0];
   if(!recipe&&table&&window===bot.inventory){
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),5000);
    const opened=once(bot,'windowOpen',{signal:abort.signal});
    try{await bot.activateBlock(table);[window]=await opened;}
    finally{clearTimeout(timer);abort.abort();await opened.catch(()=>{});}
    if(!window.type.startsWith('minecraft:crafting'))throw Error('Expected a crafting table');
    await prepare(bot,check);recipe=bot.recipesFor(item.id,null,1,table)[0];
   }
   if(!recipe)throw Error(`Insufficient ingredients after ${completed} completed recipe executions`);
   const width=window===bot.inventory?2:3,ingredients=[];
   if(recipe.inShape)for(let y=0;y<recipe.inShape.length;y++)for(let x=0;x<recipe.inShape[y].length;x++){
    const i=recipe.inShape[y][x];if(i.id!==-1)ingredients.push({slot:1+x+width*y,...i});
   }
   if(recipe.ingredients){
    const used=new Set(ingredients.map(i=>i.slot));let slot=1;
    for(const i of recipe.ingredients){while(used.has(slot))slot++;ingredients.push({slot:slot++,...i});}
   }
   for(const i of ingredients){
    if(i.slot>width*width)throw Error('Recipe does not fit crafting grid');
    const source=window.findInventoryItem(i.id,i.metadata);
    if(!source)throw Error('Server inventory no longer has the required ingredient');
    await click(bot,source.slot,0,check);
    for(let k=0;k<Math.abs(i.count||1);k++)await click(bot,i.slot,1,check);
    await parkCursor(bot,window,check);
   }
   const result=window.slots[0];
   if(result?.type!==item.id||result.count!==recipe.result.count)throw Error('Server crafting output differs from requested recipe; no output taken');
   await click(bot,0,0,check);await parkCursor(bot,window,check);completed++;produced+=recipe.result.count;
   await prepare(bot,check); // Return any recipe remainders; never drop leftovers.
  }
  const after=counts(window.items()),crafted=(after[item.name]||0)-(before[item.name]||0);
  return {completed_recipes:completed,crafted:produced,inventory_delta:crafted,inventory:window.items().map(i=>({name:i.name,count:i.count})),verified_at:new Date().toISOString(),source:'server-confirmed recipe grid and every click'};
 }catch(e){throw Error(`${e.message}; ${completed} recipe executions completed. Inventory/crafting grid may contain partial work; inspect before retrying.`);}
 finally{
  if(bot.currentWindow?.type.startsWith('minecraft:crafting')&&!bot.currentWindow.selectedItem)bot.closeWindow(bot.currentWindow);
 }
}
// The same authoritative click is useful for ordinary storage transfers.
module.exports={craft,prepare,parkCursor,click};
