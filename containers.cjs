// Ordinary storage, through server-confirmed clicks. No movement, item spawning,
// optimistic inventory predictions, dropped leftovers, or automatic retries.
const {once}=require('node:events');
const {refreshInventory}=require('./inventory.cjs');
const {click}=require('./crafting.cjs');
const {translationMetadata}=require('./protocol-compatibility.cjs');
const opened=new WeakMap();
// Keep bridge bookkeeping intact in every snapshot/click. It does not turn
// ordinary supplies into named/enchanted items; all other components still do.
const plain=i=>i&&!i.nbt&&(i.components||[]).every(translationMetadata)&&!i.removedComponents?.length&&!i.metadata;
const item=i=>i?{name:i.name,count:i.count,type:i.type,metadata:i.metadata,nbt:i.nbt,
 components:i.components||[],removedComponents:i.removedComponents||[]}:null;
const snapshot=w=>({slots:w.slots.map(item),cursor:item(w.selectedItem)});
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const total=(w,start,end,name)=>w.slots.slice(start,end).reduce((n,i)=>n+(i?.name===name?i.count:0),0);
const describe=w=>({contents:w.slots.slice(0,w.inventoryStart).flatMap((i,slot)=>i?[{slot,...item(i)}]:[]),
 inventory:w.items().map(item),cursor:item(w.selectedItem),source:'server window snapshot'});
function target(bot,p,expected){
 const block=bot.blockAt(p);
 if(!['chest','barrel'].includes(expected)||block?.name!==expected)throw Error('Expected an ordinary chest or barrel at that position');
 if(p.offset(.5,.5,.5).distanceTo(bot.entity.position)>4)throw Error('Move within four blocks of the container first; no movement performed');
 const eye=bot.entity.position.offset(0,1.62,0),direction=p.offset(.5,.5,.5).minus(eye),distance=direction.norm();
 const hit=distance?bot.world.raycast(eye,direction.scaled(1/distance),distance):null;
 if(hit&&!hit.position.equals(p))throw Error('Container is obstructed; move to a clear reachable position');
 return block;
}
async function open(bot,p,expected,check){
 const block=target(bot,p,expected),known=opened.get(bot);
 if(bot.currentWindow){
  if(known?.window===bot.currentWindow&&known.position.equals(p))return known;
  throw Error('Another window is open; resolve its inventory/cursor before opening storage');
 }
 await refreshInventory(bot);check();
 if(bot.inventory.selectedItem)throw Error('Inventory cursor is occupied; resolve it before opening storage');
 const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),5000);
 const pending=once(bot,'windowOpen',{signal:abort.signal});
 try{
  await bot.activateBlock(block);
  const [window]=await pending;
  const binding={window,position:p.clone(),sourceSlot:null};opened.set(bot,binding);
  check();
  if(!['minecraft:generic_9x3','minecraft:generic_9x6'].includes(window.type)||
     ![27,54].includes(window.inventoryStart)||window.inventoryEnd-window.inventoryStart!==36)
   throw Error('Unsupported storage window; no transfer attempted');
  return binding;
 }finally{clearTimeout(timer);abort.abort();await pending.catch(()=>{});}
}
function ranges(w,operation){return operation==='deposit'?
 {src:[w.inventoryStart,w.inventoryEnd],dst:[0,w.inventoryStart]}:
 {src:[0,w.inventoryStart],dst:[w.inventoryStart,w.inventoryEnd]};}
function validate(a){
 if(!['inspect','deposit','withdraw','recover'].includes(a.operation))throw Error('Unknown container operation');
 if(['deposit','withdraw'].includes(a.operation)&&(!a.item||!Number.isInteger(a.count)||a.count<1||a.count>64))
  throw Error('Transfer needs an exact item name and count from 1 to 64');
}
async function container(bot,p,a,check){
 validate(a);let binding,before,confirmed=0,clicks=0,lastConfirmed,unacknowledged=false;
 const deadline=Date.now()+25000;
 const guard=()=>{check();if(Date.now()>deadline)throw Error('Container operation reached its time bound');
  if(binding&&bot.currentWindow!==binding.window)throw Error('Storage window changed');target(bot,p,a.expected);};
 // Verify the complete server snapshot after each click, including the cursor.
 // A concurrent edit, ignored click, or missing acknowledgement halts the batch.
 async function confirmedClick(slot,button,expected){
  guard();if(++clicks>140)throw Error('Container click bound reached');
  unacknowledged=true;await click(bot,slot,button,guard);unacknowledged=false;
  if(!same(snapshot(binding.window),expected))throw Error('Storage changed or the server did not confirm the exact click');
  lastConfirmed=describe(binding.window);
 }
 try{
  binding=await open(bot,p,a.expected,check);guard();
  const w=binding.window;await refreshInventory(bot);guard();lastConfirmed=describe(w);
  if(a.operation==='inspect')return {position:p,operation:a.operation,...lastConfirmed};
  if(a.operation==='recover'){
   if(!w.selectedItem)return {position:p,operation:a.operation,recovered:true,...lastConfirmed};
   const slot=binding.sourceSlot,held=w.selectedItem,existing=w.slots[slot];
   if(slot===null||!plain(held)||(existing&&(!plain(existing)||existing.type!==held.type||existing.count+held.count>existing.stackSize)))
    throw Error('Cannot safely return the cursor to its original source slot; inspect and coordinate before recovery');
   const expected=snapshot(w);expected.slots[slot]={...item(held),count:held.count+(existing?.count||0)};expected.cursor=null;
   await confirmedClick(slot,0,expected);binding.sourceSlot=null;
   return {position:p,operation:a.operation,recovered:true,...describe(w)};
  }
  if(w.selectedItem)throw Error('A previous transfer left items on the cursor; inspect then use recover before another transfer');
  const {src,dst}=ranges(w,a.operation),source=w.slots.slice(...src).filter(i=>i?.name===a.item);
  if(source.some(i=>!plain(i)))throw Error('Named, enchanted, or component-bearing items need explicit selection; this tool transfers ordinary supplies only');
  if(source.reduce((n,i)=>n+i.count,0)<a.count)throw Error('Insufficient source items; nothing transferred');
  const sample=source[0];
  const capacity=w.slots.slice(...dst).reduce((n,i)=>n+(!i?sample.stackSize:plain(i)&&i.type===sample.type?i.stackSize-i.count:0),0);
  if(capacity<a.count)throw Error('Insufficient destination space; nothing transferred');
  before={source:total(w,...src,a.item),destination:total(w,...dst,a.item)};
  while(confirmed<a.count){
   guard();const sourceSlot=w.slots.findIndex((i,s)=>s>=src[0]&&s<src[1]&&i?.name===a.item&&plain(i));
   if(sourceSlot<0)throw Error('Source changed during transfer');
   binding.sourceSlot=sourceSlot;
   let expected=snapshot(w);expected.cursor=expected.slots[sourceSlot];expected.slots[sourceSlot]=null;
   await confirmedClick(sourceSlot,0,expected);
   let batch=0;
   while(w.selectedItem&&confirmed+batch<a.count){
    guard();const h=w.selectedItem;
    const dest=w.slots.findIndex((i,s)=>s>=dst[0]&&s<dst[1]&&(!i||(plain(i)&&i.type===h.type&&i.count<i.stackSize)));
    if(dest<0)throw Error('Destination changed during transfer');
    const room=w.slots[dest]?w.slots[dest].stackSize-w.slots[dest].count:h.stackSize;
    const amount=Math.min(h.count,room,a.count-confirmed-batch);
    const button=amount===Math.min(h.count,room)?0:1,n=button===0?amount:1;
    expected=snapshot(w);expected.slots[dest]={...item(h),count:(w.slots[dest]?.count||0)+n};
    expected.cursor=h.count===n?null:{...item(h),count:h.count-n};
    await confirmedClick(dest,button,expected);batch+=n;
   }
   if(w.selectedItem){
    expected=snapshot(w);expected.slots[sourceSlot]=expected.cursor;expected.cursor=null;
    await confirmedClick(sourceSlot,0,expected);
   }
   binding.sourceSlot=null;confirmed+=batch;
  }
  await refreshInventory(bot);guard();
  const after={source:total(w,...src,a.item),destination:total(w,...dst,a.item)};
  if(w.selectedItem||before.source-after.source!==a.count||after.destination-before.destination!==a.count)
   throw Error('Final source/destination totals differ; inspect before retrying');
  return {position:p,operation:a.operation,item:a.item,requested_count:a.count,transferred:a.count,
   verified:true,before,after,clicks,...describe(w),guidance:'Coordinate shared storage in game chat. This verifies this transfer, not exclusive ownership or future contents.'};
 }catch(e){
  if(!clicks)throw e;
  return {position:p,operation:a.operation,item:a.item,requested_count:a.count,status:'unconfirmed',verified:false,
   error:e.message,completed_batches_count:confirmed,clicks,last_confirmed:lastConfirmed,
   guidance:'Partial changes may exist. Do not repeat the transfer blindly. Inspect this container and your inventory; recover any cursor to its original source before continuing.'};
 }finally{
  // Closing a full inventory with a held cursor can drop items. Preserve that
  // window for inspection/recovery instead. Never perform cleanup mutations
  // after Stop or a timeout.
  const b=binding||opened.get(bot);
  if(b&&bot.currentWindow===b.window&&!b.window.selectedItem&&!unacknowledged){bot.closeWindow(b.window);opened.delete(bot);}
 }
}
module.exports={container,validate};
