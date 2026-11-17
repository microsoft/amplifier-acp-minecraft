// Small composable survival primitives. No pursuit, target substitution, combat
// loop or automatic retry. Body admission owns authority, deadlines and budgets.
const {refreshInventory}=require('./inventory.cjs');
const {inventoryBarrier}=require('./inventory-barrier.cjs');
function metadata(bot,e,key){const i=bot.registry.entitiesByName[e.name]?.metadataKeys?.indexOf(key);return i>=0?e.metadata?.[i]:undefined;}
function attackTarget(bot,a){
 const e=bot.entities[a.id],definition=e&&bot.registry.entitiesByName[e.name];
 if(!e||e.uuid!==a.uuid)throw Error('Entity identity changed; inspect entities again');
 if(e===bot.entity||e.type==='player'||e.username||definition?.type==='player'||e.name==='armor_stand'||!definition?.metadataKeys?.includes('health'))throw Error('Attack requires a living non-player mob');
 if(!Object.keys(e.metadata||{}).length)throw Error('Entity metadata is not available yet');
 if(metadata(bot,e,'custom_name')||metadata(bot,e,'owneruuid')||metadata(bot,e,'owner_uuid')||((definition.metadataKeys.includes('owneruuid')||definition.metadataKeys.includes('owner_uuid'))&&(metadata(bot,e,'flags')&4)))throw Error('Do not attack named or owned animals');
 if(metadata(bot,e,'baby')===true)throw Error('Do not attack baby animals');
 if(e.position.distanceTo(bot.entity.position)>3)throw Error('Move within three blocks before attacking; attack never chases');
 // A sword may sweep nearby entities, even though the packet names one target.
 if(bot.heldItem?.name?.endsWith('_sword')&&Object.values(bot.entities).some(other=>other!==e&&other!==bot.entity&&other.position&&bot.registry.entitiesByName[other.name]?.metadataKeys?.includes('health')&&other.position.distanceTo(e.position)<3))throw Error('A sword sweep could hit another nearby entity; choose a non-sweeping tool or an isolated target');
 const eye=bot.entity.position.offset(0,1.62,0),aim=e.position.offset(0,Math.min(1,e.height||.5),0),delta=aim.minus(eye),distance=delta.norm();
 if(distance&&bot.world.raycast(eye,delta.scaled(1/distance),distance))throw Error('Target is behind a block');
 return e;
}
async function attack(bot,a,check){
 check();const e=attackTarget(bot,a),identity={id:e.id,uuid:e.uuid,name:e.name};
 // A packet write is not a confirmed hit. Only matching server damage attributed
 // to this player, or an observed death of this exact entity, ends the wait.
 let timer,clean;
 const observed=new Promise((resolve,reject)=>{
  const hurt=(target,source)=>{if(target===e&&target.uuid===identity.uuid&&source===bot.entity)resolve({hurt_observed:true,damage_source:'self',death_observed:false});};
  const dead=target=>{if(target===e&&target.uuid===identity.uuid)resolve({hurt_observed:false,damage_source:null,death_observed:true});};
  const ended=()=>reject(Error('Connection ended after attack; inspect before any further attack'));
  clean=()=>{clearTimeout(timer);bot.off('entityHurt',hurt);bot.off('entityDead',dead);bot.off('end',ended);};
  bot.on('entityHurt',hurt);bot.on('entityDead',dead);bot.on('end',ended);
  timer=setTimeout(()=>reject(Error('Attack result unconfirmed; inspect this exact entity and do not replay')),5000);
 });
 // Handle a synchronous send/check failure without leaving an unhandled waiter.
 observed.catch(()=>{});
 try{
  check();if(attackTarget(bot,a)!==e)throw Error('Target changed before attack');
  bot.attack(e);const result=await observed;check();await inventoryBarrier(bot);check();
  return {target:identity,attacks_sent:1,...result,drops_collected:false,
   scope:'One attack and subsequent server observations. Death does not identify the killer; drops and inventory must be inspected separately.'};
 }finally{clean();}
}
function selectedItem(bot,a){
 if(!Object.hasOwn(bot.registry.itemsByName,a.item))throw Error('Unknown registered item');
 const item=bot.inventory.items().find(i=>i.name===a.item);
 if(!item)throw Error('Item is not in inventory');return item;
}
function equipmentPreflight(bot,a){selectedItem(bot,a);if(bot.currentWindow!==null||bot.inventory.selectedItem!==null)throw Error('Resolve the open window/cursor before equipment or eating');}
function prepared(bot,validate,settled,stage){
 try{validate();}catch(error){
  if(bot.currentWindow===null&&bot.inventory.selectedItem===null)settled(error,{kind:'settled_failed_preparation',stage});
  throw error;
 }
}
async function equip(bot,a,check,{settled=()=>{}}={}){
 equipmentPreflight(bot,a);await refreshInventory(bot);check();prepared(bot,()=>equipmentPreflight(bot,a),settled,'before_equip');
 const item=selectedItem(bot,a);await bot.equip(item,'hand');await refreshInventory(bot);check();
 if(bot.heldItem?.name!==a.item){const error=Error('Server did not confirm held item; inspect inventory');settled(error,{kind:'settled_failed_equipment',requested:a.item,observed:bot.heldItem?.name||null});throw error;}
 return {held_item:a.item,verified:true};
}
function consumePreflight(bot,a){
 equipmentPreflight(bot,a);
 if(!Object.hasOwn(bot.registry.foodsByName||{},a.item))throw Error('Select a registered food item; arbitrary item use is not eating');
 if(bot.food>=20)throw Error('Food is already full; no consumption needed');
}
async function consume(bot,a,check,{settled=()=>{}}={}){
 consumePreflight(bot,a);await equip(bot,a,check,{settled});check();prepared(bot,()=>consumePreflight(bot,a),settled,'before_consume');
 const count=()=>bot.inventory.items().filter(i=>i.name===a.item).reduce((n,i)=>n+i.count,0),before=count();
 await bot.consume();await refreshInventory(bot);check();const after=count();
 if(before-after!==1){const error=Error('Consumption count unconfirmed; inspect inventory and food before continuing');settled(error,{kind:'settled_failed_consumption',completion_observed:true,before,after,consumed_count:null});throw error;}
 return {item:a.item,consumed:1,before,after,food:bot.food,health:bot.health,verified:true};
}
module.exports={attackTarget,attack,equipmentPreflight,equip,consumePreflight,consume};
