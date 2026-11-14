const {inventoryClient}=require('./inventory-client-fixture.cjs');
const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');const {Vec3}=require('vec3');
const {entities,sheepTarget,furnace,validLoad,furnacePreflight}=require('../survival.cjs');
function fixture(){
 const bot=new EventEmitter();bot.registry=require('minecraft-data')('1.21.1');
 bot.entity={position:new Vec3(0,0,0)};bot.world={raycast:()=>null};bot.entities={};
 bot.supportFeature=()=>true;bot.inventory={id:0,slots:[],type:"minecraft:inventory",selectedItem:null,items:()=>[{name:'raw_iron',count:2}]};
 bot._client=inventoryClient(()=>bot.emit('setWindowItems:0'));
 const sheep={id:1,uuid:'stable-id',name:'sheep',position:new Vec3(2,0,0),metadata:[]};
 const keys=bot.registry.entitiesByName.sheep.metadataKeys;
 sheep.metadata[keys.indexOf('wool')]=0;sheep.metadata[keys.indexOf('baby')]=false;bot.entities[1]=sheep;
 return {bot,sheep,keys};
}
test('animal discovery is scoped to loaded radius and shearing fails closed on unknown metadata',()=>{
 const {bot,sheep,keys}=fixture();assert.equal(entities(bot,{radius:1}).entities.length,0);
 assert.equal(entities(bot,{name:'sheep',radius:4}).entities.length,1);
 assert.throws(()=>sheepTarget(bot,{id:1,uuid:'reused-id'}),/identity changed/);
 sheep.metadata=[];assert.throws(()=>sheepTarget(bot,{id:1,uuid:'stable-id'}),/confirmed adult/);
});
test('animal interactions reject out-of-reach and obstructed targets',()=>{
 const {bot,sheep}=fixture();sheep.position=new Vec3(5,0,0);
 assert.throws(()=>sheepTarget(bot,{id:1,uuid:'stable-id'}),/within three/);
 sheep.position=new Vec3(2,0,0);bot.world.raycast=()=>({});assert.throws(()=>sheepTarget(bot,{id:1,uuid:'stable-id'}),/behind a block/);
});
test('cancellation after opening a furnace closes its window before any transfer',async()=>{
 const {bot}=fixture();let opened=false,closed=false;
 bot.blockAt=()=>({name:'furnace'});bot.openFurnace=async()=>{opened=true;return {selectedItem:null,close:()=>{closed=true;}};};
 await assert.rejects(furnace(bot,new Vec3(1,0,0),{operation:'inspect'},()=>{if(opened)throw Error('Stopped');}),/Stopped/);
 assert.equal(closed,true);
});
test('registered furnace choices are not restricted by a client recipe or fuel table',()=>{
 const {bot}=fixture();
 for(const [item,fuel] of [['cobblestone','oak_slab'],['raw_iron','coal_block'],['potato','bamboo'],['beef','stick']]){
  assert.doesNotThrow(()=>validLoad({operation:'load',item,count:1,fuel,fuel_count:1},bot.registry));
 }
 // Registration is not smelting proof: eligibility remains server-owned.
 assert.doesNotThrow(()=>validLoad({item:'cobblestone',count:1,fuel:'stone',fuel_count:1},bot.registry));
});
test('unknown items and malformed counts refuse before opening or inventory effects',async()=>{
 const {bot}=fixture();let effects=0;bot.blockAt=()=>({name:'furnace'});
 bot.openFurnace=async()=>{effects++;throw Error('must not open');};bot._client.write=()=>{effects++;};
 for(const a of [{item:'no_such_item',count:1},{item:'__proto__',count:1},{item:'cobblestone',count:0},
                  {item:'cobblestone',count:9},{item:'cobblestone',count:1,fuel:'oak_slab'},
                  {item:'cobblestone',count:1,fuel_count:1},{item:'cobblestone',count:1,fuel:'oak_slab',fuel_count:0}]){
  await assert.rejects(furnace(bot,new Vec3(1,0,0),{operation:'load',...a},()=>{}));
 }
 assert.equal(effects,0);
});
test('furnace target and reach are observable preflight facts',()=>{
 const {bot}=fixture();bot.blockAt=()=>({name:'air'});
 assert.throws(()=>furnacePreflight(bot,new Vec3(1,0,0),{operation:'inspect'}),/ordinary furnace/);
 bot.blockAt=()=>({name:'furnace'});
 assert.throws(()=>furnacePreflight(bot,new Vec3(8,0,0),{operation:'inspect'}),/within reach/);
});
test('fuel transfer failure after input is retained as a possible partial load',async()=>{
 const {bot}=fixture();const calls=[];bot.blockAt=()=>({name:'furnace'});
 bot.openFurnace=async()=>({selectedItem:null,inputItem:()=>null,outputItem:()=>null,fuelItem:()=>null,
  items:()=>[{name:'raw_iron',count:2},{name:'stone',count:1}],
  putInput:async()=>calls.push('input'),putFuel:async()=>{calls.push('fuel');throw Error('Server rejected fuel');},
  close:()=>calls.push('close')});
 await assert.rejects(furnace(bot,new Vec3(1,0,0),{operation:'load',item:'raw_iron',count:1,fuel:'stone',fuel_count:1},()=>{}),/Server rejected fuel/);
 assert.deepEqual(calls,['input','fuel','close']);
});
for(const mode of ['confirmed','full','cursor','pickup_error','deposit_error','stopped'])test('furnace collection uses confirmed clicks: '+mode,async()=>{
 const {bot}=fixture(),windows=require('prismarine-windows')(bot.registry),Item=require('prismarine-item')(bot.registry);
 const f=windows.createWindow(1,'minecraft:furnace','Furnace'),calls=[];let closed=false;
 const iron=new Item(bot.registry.itemsByName.iron_ingot.id,1);f.updateSlot(2,iron);
 f.inputItem=()=>f.slots[0];f.fuelItem=()=>f.slots[1];f.outputItem=()=>f.slots[2];f.fuel=0;f.progress=0;
 if(mode==='full')for(let i=f.inventoryStart;i<f.inventoryEnd;i++)f.updateSlot(i,new Item(bot.registry.itemsByName.cobblestone.id,64));
 if(mode==='cursor')f.selectedItem=new Item(bot.registry.itemsByName.dirt.id,1);
 f.close=()=>{closed=true;bot.currentWindow=null;};f.takeOutput=async()=>{throw Error('optimistic takeOutput must not be used');};
 bot.currentWindow=null;bot.blockAt=()=>({name:'furnace'});bot.openFurnace=async()=>{bot.currentWindow=f;return f;};
 bot._client=inventoryClient((name,p)=>{
  if(p.mode===0){
   calls.push(p.slot);
   if(mode==='pickup_error'&&p.slot===2||mode==='deposit_error'&&p.slot!==2)throw Error('unknown click reply');
   if(p.slot===2){f.selectedItem=f.slots[2];f.updateSlot(2,null);}
   else{f.updateSlot(p.slot,f.selectedItem);f.selectedItem=null;}
  }
  bot.emit('setWindowItems:'+p.windowId);
 });
 const check=()=>{if(mode==='stopped'&&calls.length)throw Error('Stopped');};
 if(mode==='confirmed'){
  const result=await furnace(bot,new Vec3(1,0,0),{operation:'collect'},check);
  assert.deepEqual(result.collected,{name:'iron_ingot',count:1});assert.equal(result.inventory.find(i=>i.name==='iron_ingot').count,1);assert.deepEqual(calls,[2,3]);assert.equal(f.selectedItem,null);assert.equal(closed,true);
 }else{
  await assert.rejects(furnace(bot,new Vec3(1,0,0),{operation:'collect'},check));
  assert.ok(calls.filter(s=>s===2).length<=1,'never repeat output pickup');
  if(['full','cursor','pickup_error','deposit_error','stopped'].includes(mode))assert.equal(closed,false,'do not close a held cursor');
 }
});
