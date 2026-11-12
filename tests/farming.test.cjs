const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events'),{Vec3}=require('vec3');
const {till,observeCrops}=require('../farming.cjs');
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

test('passive crop observations expose growth and hydration without unstable ordering or effects',()=>{
 const crops=[{name:'wheat',position:new Vec3(-2,63,1),age:0},{name:'farmland',position:new Vec3(-2,62,1),moisture:7}];
 let reverse=false;
 const bot={findBlocks:options=>{
  assert.equal(options.maxDistance,16);assert.equal(options.count,65);
  assert.equal(options.matching({name:'oak_sign'}),false);
  assert.equal(options.matching({name:'wheat'}),true);
  return (reverse?[...crops].reverse():crops).map(b=>b.position);
 },blockAt:p=>{const b=crops.find(b=>b.position.equals(p));return {...b,getProperties:()=>({...b,private_text:'excluded'})};}};
 const first=observeCrops(bot);reverse=true;
 assert.deepEqual(observeCrops(bot),first);
 assert.equal(first.blocks[0].properties.moisture,7);assert.equal(first.blocks[1].properties.age,0);
 assert.ok(!JSON.stringify(first).includes('private_text'));
 crops[0].age=7;
 assert.equal(observeCrops(bot).blocks[1].properties.age,7);
 assert.equal(first.coverage,'loaded_nearby_blocks');assert.equal(first.truncated,false);
});

test('crop observations bound their size and retain unavailable coverage instead of inventing growth',()=>{
 const positions=Array.from({length:65},(_,i)=>new Vec3(i%8,63,Math.floor(i/8)));
 let reads=0;
 const bot={findBlocks:()=>positions,blockAt:p=>{reads++;return reads===1?null:{name:'wheat',getProperties:()=>({age:3})};}};
 const result=observeCrops(bot);
 assert.equal(reads,64);assert.equal(result.blocks.length,63);assert.equal(result.unavailable,1);assert.equal(result.truncated,true);
 assert.ok(result.blocks.every(b=>b.properties.age===3));
});

test('crop scan uses registry block IDs for loaded chunk palette filtering',()=>{
 const bot={registry:{blocksByName:{wheat:{id:59},farmland:{id:60}}},findBlocks:options=>{
  assert.deepEqual(options.matching,[59,60]);return [];
 },blockAt:()=>assert.fail('No candidate blocks to read')};
 assert.deepEqual(observeCrops(bot).blocks,[]);
});

test('string-valued protocol block properties retain age and moisture without coercing invalid values',()=>{
 const bot={findBlocks:()=>[new Vec3(0,63,0)],blockAt:()=>({name:'wheat',getProperties:()=>({age:'6',moisture:'7',stage:'0'})})};
 assert.deepEqual(observeCrops(bot).blocks[0].properties,{age:6,moisture:7,stage:0});
 for(const bad of ['',null,true,[],{},'NaN','1.5','-1',-1]){
  bot.blockAt=()=>({name:'wheat',getProperties:()=>({age:bad})});
  assert.deepEqual(observeCrops(bot).blocks[0].properties,{});
 }
});

test('mushroom evidence changes only with observed block changes and retains bounded coverage',()=>{
 let blocks=[{name:'red_mushroom',position:new Vec3(1,64,0)},{name:'brown_mushroom',position:new Vec3(2,64,0)}];
 const bot={registry:{blocksByName:{red_mushroom:{id:39},brown_mushroom:{id:40}}},findBlocks:options=>{
  assert.deepEqual(options.matching,[39,40]);assert.equal(options.maxDistance,16);assert.equal(options.count,65);return blocks.map(b=>b.position);
 },blockAt:p=>{const b=blocks.find(b=>b.position.equals(p));return b?{...b,getProperties:()=>({})}:null;}};
 const before=observeCrops(bot);assert.equal(before.blocks.length,2);assert.deepEqual(observeCrops(bot),before);
 blocks.push({name:'red_mushroom',position:new Vec3(3,64,0)});const grown=observeCrops(bot);assert.equal(grown.blocks.length,3);assert.notDeepEqual(grown,before);assert.ok(grown.blocks.every(b=>Object.keys(b.properties).length===0));
 blocks=blocks.slice(1);assert.equal(observeCrops(bot).blocks.some(b=>b.position.x===1),false);
 assert.equal(grown.radius_blocks,16);assert.equal(grown.truncated,false);
});
