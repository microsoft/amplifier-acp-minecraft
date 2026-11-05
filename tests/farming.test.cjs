const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events'),{Vec3}=require('vec3');
const {till}=require('../farming.cjs');
const {inventoryClient}=require('./inventory-client-fixture.cjs');
function fixture(){
 const bot=new EventEmitter(),p=new Vec3(1,0,0),items=[{name:'wooden_hoe',count:1}];
 bot.registry=require('minecraft-data')('1.21.1');bot.supportFeature=()=>true;
 let soil={name:'grass_block',position:p,getProperties:()=>({})},above='air',activations=0,mode='normal';
 bot.entity={position:new Vec3(.5,1,.5)};bot.world={raycast:()=>({position:p})};
 bot.blockAt=v=>v.equals(p)?soil:{name:above,position:v};
 bot.inventory={id:0,slots:[],type:'minecraft:inventory',selectedItem:null,items:()=>items};
 bot.lookAt=async()=>{};bot.swingArm=()=>{};
 bot.equip=async i=>{bot.heldItem=i;};
 bot._client=inventoryClient((packet,a)=>{
  if(packet==='window_click'){bot.emit('setWindowItems:0');return;}
  assert.equal(packet,'block_place');assert.equal(a.direction,1);assert.equal(a.hand,0);assert.equal(a.cursorY,1);assert.deepEqual(a.location,p);activations++;
  if(mode==='disconnect')throw Error('Connection closed after send');
  if(mode==='ignore')return;
  if(mode==='other'){bot.emit('blockUpdate',null,{name:'farmland',position:p.offset(1,0,0)});return;}
  soil={name:'farmland',position:p,getProperties:()=>({moisture:0})};bot.emit('blockUpdate',null,soil);
 });
 return {bot,p,items,setAbove:v=>{above=v;},setSoil:v=>{soil={...soil,name:v};},setMode:v=>{mode=v;},
  get activations(){return activations;},run:(check=()=>{})=>till(bot,p,{expected:'grass_block'},check,{timeoutMs:10})};
}
test('one hoe interaction requires server farmland at the exact position',async()=>{
 const f=fixture(),r=await f.run();assert.equal(r.verified,true);assert.equal(r.properties.moisture,0);
 assert.equal(f.activations,1);assert.equal(f.bot.listenerCount('blockUpdate'),0);
 assert.match(r.guidance,/Hydration and planting are separate/);
});
test('missing hoe, wrong block, overhead obstacle, reach and occlusion perform no till',async()=>{
 for(const mode of ['hoe','block','above','reach','occluded']){
  const f=fixture();if(mode==='hoe')f.items.length=0;
  if(mode==='block')f.setSoil('coarse_dirt');if(mode==='above')f.setAbove('short_grass');
  if(mode==='reach')f.bot.entity.position=new Vec3(9,1,0);
  if(mode==='occluded')f.bot.world.raycast=()=>({position:new Vec3(0,1,0)});
  await assert.rejects(f.run());assert.equal(f.activations,0);assert.equal(f.bot.listenerCount('blockUpdate'),0);
 }
});
test('soil or authorization changing while equipping is rechecked before interaction',async()=>{
 for(const mode of ['block','stop','held']){
  const f=fixture();let stopped=false;
  f.bot.equip=async i=>{f.bot.heldItem=mode==='held'?{name:'stick'}:i;if(mode==='block')f.setSoil('stone');if(mode==='stop')stopped=true;};
  await assert.rejects(f.run(()=>{if(stopped)throw Error('Action cancelled');}));assert.equal(f.activations,0);
 }
});
test('ignored, unrelated and lost acknowledgments stay unconfirmed without retry',async()=>{
 for(const mode of ['ignore','other','disconnect']){
  const f=fixture();f.setMode(mode);const r=await f.run();assert.equal(r.verified,false);assert.equal(r.status,'unconfirmed');
  assert.equal(f.activations,1);assert.equal(f.bot.listenerCount('blockUpdate'),0);assert.match(r.guidance,/[Ii]nspect/);
 }
});

test('Stop or target change during aiming never sends a hoe interaction',async()=>{
 for(const change of ['stop','soil']){
  const f=fixture();let stopped=false;
  f.bot.lookAt=async()=>{if(change==='stop')stopped=true;else f.setSoil('stone');};
  await assert.rejects(f.run(()=>{if(stopped)throw Error('Action cancelled');}));
  assert.equal(f.activations,0);assert.equal(f.bot.listenerCount('blockUpdate'),0);
 }
});
