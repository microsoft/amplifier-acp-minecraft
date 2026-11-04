// Ordinary survival interactions. Loaded entities and server state are evidence;
// neither a successful packet write nor a dropped item proves collection.
const {refreshInventory}=require('./inventory.cjs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const colors=['white','orange','magenta','light_blue','yellow','lime','pink','gray','light_gray','cyan','purple','blue','brown','green','red','black'];
function metadata(bot,e,key){const index=bot.registry.entitiesByName[e.name]?.metadataKeys?.indexOf(key);return index>=0?e.metadata?.[index]:undefined;}
function describe(bot,e){
 const result={id:e.id,uuid:e.uuid,name:e.name,position:e.position.clone(),distance:Math.round(e.position.distanceTo(bot.entity.position)*10)/10};
 if(e.name==='sheep'){
  // Java 1.21.1 sends non-default metadata only: wool=0 (white,
  // unsheared), baby=false. Wait for an initial metadata snapshot first.
  const initialized=Object.keys(e.metadata||{}).length>0;
  const wool=metadata(bot,e,'wool')??(initialized?0:undefined),baby=metadata(bot,e,'baby')??(initialized?false:undefined);
  result.sheep={color:Number.isInteger(wool)?colors[wool&15]:null,sheared:Number.isInteger(wool)?!!(wool&16):null,baby:typeof baby==='boolean'?baby:null};
 }
 if(e.name==='item'){
  const raw=metadata(bot,e,'item');
  try{const item=require('prismarine-item')(bot.registry).fromNotch(raw);if(item)result.item={name:item.name,count:item.count};}catch{}
 }
 return result;
}
function entities(bot,{name,radius=32}){
 const found=Object.values(bot.entities).filter(e=>e!==bot.entity&&(!name||e.name===name)&&e.position.distanceTo(bot.entity.position)<=radius).sort((a,b)=>a.position.distanceTo(bot.entity.position)-b.position.distanceTo(bot.entity.position));
 return {entities:found.slice(0,24).map(e=>describe(bot,e)),truncated:found.length>24,scope:'Currently loaded entities only; an empty result does not prove none exist elsewhere.'};
}
function sheepTarget(bot,a){
 const e=bot.entities[a.id];
 if(!e||e.uuid!==a.uuid||e.name!=='sheep')throw Error('Sheep identity changed or is no longer loaded; inspect entities again');
 const s=describe(bot,e).sheep;
 if(s.baby!==false||s.sheared!==false)throw Error('Shearing requires a confirmed adult sheep with unsheared wool');
 if(e.position.distanceTo(bot.entity.position)>3)throw Error('Move safely within three blocks of this sheep first');
 const eye=bot.entity.position.offset(0,1.62,0),target=e.position.offset(0,.8,0),direction=target.minus(eye),distance=direction.norm();
 const hit=bot.world.raycast(eye,direction.scaled(1/distance),distance);
 if(hit)throw Error('Sheep is behind a block; move to a clear reachable position');
 return e;
}
async function shear(bot,a,check){
 sheepTarget(bot,a);await refreshInventory(bot);check();
 const tool=bot.inventory.items().find(i=>i.name==='shears');if(!tool)throw Error('Shears are required; craft them from two iron ingots');
 await bot.equip(tool,'hand');await refreshInventory(bot);check();
 if(bot.heldItem?.name!=='shears')throw Error('Server did not confirm held shears');
 const e=sheepTarget(bot,a),before=bot.inventory.items().filter(i=>i.name.endsWith('_wool')).reduce((n,i)=>n+i.count,0);
 // Java clients try a precise hit before the general interaction. Older sheep
 // implementations ignore the precise hit; newer translated servers need it.
 await bot.activateEntityAt(e,e.position.offset(0,.8,0));
 await require('./inventory-barrier.cjs').inventoryBarrier(bot);check();
 if(describe(bot,e).sheep.sheared!==true){sheepTarget(bot,a);await bot.activateEntity(e);}
 for(let i=0;i<20;i++){await delay(100);check();if(describe(bot,e).sheep.sheared===true)break;}
 if(describe(bot,e).sheep.sheared!==true)throw Error('Server did not confirm shearing; inspect before retrying');
 const inventory=await refreshInventory(bot);check();
 const after=inventory.items.filter(i=>i.name.endsWith('_wool')).reduce((n,i)=>n+i.count,0);
 return {sheep:describe(bot,e),verified:true,collected_wool:Math.max(0,after-before),inventory:inventory.items,nearby_drops:entities(bot,{name:'item',radius:8}),guidance:'Wool drops may still be on the ground. Inspect, plan a safe route, and verify inventory after pickup.'};
}
const stack=i=>i?{name:i.name,count:i.count}:null;
function furnaceState(f){return {input:stack(f.inputItem()),fuel:stack(f.fuelItem()),output:stack(f.outputItem()),burning:f.fuel===null?null:f.fuel>0,progress:f.progress};}
function validLoad(a){
 if(!a.item||!a.count)throw Error('Loading requires item and count');
 if(!['raw_iron','raw_gold','raw_copper','iron_ore','gold_ore','copper_ore','sand','cobblestone'].includes(a.item)&&!a.item.endsWith('_log'))throw Error('Supported inputs: raw metals, ores, sand, cobblestone or logs');
 if(a.fuel&&!['coal','charcoal','stick'].includes(a.fuel)&&!a.fuel.endsWith('_planks')&&!a.fuel.endsWith('_log'))throw Error('Supported fuels: coal, charcoal, sticks, planks or logs');
 if(!!a.fuel!==!!a.fuel_count)throw Error('Provide fuel and fuel_count together');
}
async function furnace(bot,p,a,check){
 if(a.operation==='load')validLoad(a);
 const block=bot.blockAt(p);if(block?.name!=='furnace')throw Error('Target must be an ordinary furnace');
 if(p.offset(.5,.5,.5).distanceTo(bot.entity.position)>4)throw Error('Move within reach of the furnace first');
 await refreshInventory(bot);check();
 let f;
 try{
  f=await bot.openFurnace(block);check();await refreshInventory(bot);check();
  if(a.operation==='load'){
   if(f.inputItem()||f.outputItem())throw Error('Furnace input/output must be empty before loading; inspect or collect first');
   if(a.fuel&&f.fuelItem())throw Error('Fuel slot already has items; omit fuel to use the existing supply');
   const counts={};for(const i of f.items())counts[i.name]=(counts[i.name]||0)+i.count;
   const needed={[a.item]:a.count};if(a.fuel)needed[a.fuel]=(needed[a.fuel]||0)+a.fuel_count;
   for(const [name,count]of Object.entries(needed))if((counts[name]||0)<count)throw Error('Insufficient inventory: '+name);
   // No unbounded wait for smelting. Load once, inspect/collect in a later call.
   await f.putInput(bot.registry.itemsByName[a.item].id,null,a.count);check();
   if(a.fuel){await f.putFuel(bot.registry.itemsByName[a.fuel].id,null,a.fuel_count);check();}
  }
  let collected=null;
  if(a.operation==='collect'&&f.outputItem()){
   collected=stack(f.outputItem());
   const before=f.items().filter(i=>i.name===collected.name).reduce((n,i)=>n+i.count,0);
   await f.takeOutput();check();await refreshInventory(bot);check();
   const after=f.items().filter(i=>i.name===collected.name).reduce((n,i)=>n+i.count,0);
   if(after-before<collected.count)throw Error('Output pickup not confirmed; inspect inventory before retrying');
  }
  const inventory=await refreshInventory(bot);check();
  return {position:p,operation:a.operation,...furnaceState(f),collected,inventory:inventory.items,guidance:'Smelting continues in the world after closing. Inspect later; collect only reports items verified in inventory. Coordinate furnace ownership through game chat.'};
 }finally{if(f)f.close();}
}
module.exports={entities,describe,sheepTarget,shear,furnace,validLoad};
