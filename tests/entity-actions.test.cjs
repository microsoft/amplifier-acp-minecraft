const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {Vec3}=require('vec3'),{inventoryClient}=require('./inventory-client-fixture.cjs');
const {attackTarget,attack,consumePreflight,equipmentPreflight}=require('../entity-actions.cjs');
function fixture(){
 const bot=new EventEmitter();bot.registry=require('minecraft-data')('1.21.1');bot.entity={id:99,position:new Vec3(0,64,0)};bot.entities={};bot.world={raycast:()=>null};
 const e={id:1,uuid:'exact',name:'pig',position:new Vec3(2,64,0),metadata:[],height:.8};e.metadata[0]=0;bot.entities[1]=e;
 bot._client=inventoryClient(()=>{});let sends=0;bot.attack=target=>{sends++;bot.emit('entityHurt',target,bot.entity);};
 return {bot,e,get sends(){return sends;}};
}
for(const mode of ['player','named','baby','far','obstructed','identity','unknown_metadata','armor_stand','owned'])test('attack preflight refuses '+mode+' without dispatch',()=>{
 const f=fixture(),{bot,e}=f;const set=(key,value)=>{e.metadata[bot.registry.entitiesByName[e.name].metadataKeys.indexOf(key)]=value;};
 if(mode==='player')e.name='player';if(mode==='armor_stand')e.name='armor_stand';
 if(mode==='named')set('custom_name',{text:'Pet'});if(mode==='baby')set('baby',true);
 if(mode==='far')e.position=new Vec3(5,64,0);if(mode==='obstructed')bot.world.raycast=()=>({});
 if(mode==='identity')e.uuid='replacement';if(mode==='unknown_metadata')e.metadata=[];
 if(mode==='owned'){e.name='wolf';set('owneruuid','owner');}
 assert.throws(()=>attackTarget(bot,{id:1,uuid:'exact'}));assert.equal(f.sends,0);
});
test('one attack observes exact self damage, cleans listeners and does not claim food or kill',async()=>{
 const f=fixture(),r=await attack(f.bot,{id:1,uuid:'exact'},()=>{});
 assert.equal(f.sends,1);assert.equal(r.hurt_observed,true);assert.equal(r.death_observed,false);assert.equal(r.drops_collected,false);assert.equal(f.bot.listenerCount('entityHurt'),0);assert.equal(f.bot.listenerCount('entityDead'),0);
});
test('other damage and reused identity do not confirm our attack; disconnect stays unknown without resend',async()=>{
 const f=fixture();let calls=0;
 f.bot.attack=()=>{calls++;f.bot.emit('entityHurt',f.e,{id:2});f.bot.emit('entityDead',{...f.e,uuid:'replacement'});f.bot.emit('end');};
 await assert.rejects(attack(f.bot,{id:1,uuid:'exact'},()=>{}),/Connection ended/);assert.equal(calls,1);assert.equal(f.bot.listenerCount('entityHurt'),0);
});
test('Stop at dispatch prevents the attack and leaves no observation waiter',async()=>{
 const f=fixture();let checks=0;
 await assert.rejects(attack(f.bot,{id:1,uuid:'exact'},()=>{if(++checks===2)throw Error('Stopped');}),/Stopped/);
 assert.equal(f.sends,0);assert.equal(f.bot.listenerCount('entityHurt'),0);
});
test('food/equipment use registry and actual inventory, without a weapon whitelist',()=>{
 const {bot}=fixture();bot.currentWindow=null;bot.food=10;bot.inventory={selectedItem:null,items:()=>[{name:'bread',count:2},{name:'wooden_sword',count:1}]};
 assert.doesNotThrow(()=>equipmentPreflight(bot,{item:'wooden_sword'}));assert.doesNotThrow(()=>consumePreflight(bot,{item:'bread'}));
 assert.throws(()=>consumePreflight(bot,{item:'wooden_sword'}),/food/);bot.food=20;assert.throws(()=>consumePreflight(bot,{item:'bread'}),/full/);
 bot.inventory.selectedItem=undefined;assert.throws(()=>equipmentPreflight(bot,{item:'bread'}),/cursor/);
});

function equipmentFixture({consumeChanges=true,equipChanges=true,onRefresh}={}){
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{createRequire}=require('node:module');
 const file=path.resolve(__dirname,'../entity-actions.cjs'),load=createRequire(file),items=[{name:'bread',count:2},{name:'wooden_sword',count:1}];
 let refreshes=0,equips=0,consumes=0;
 const {bot}=fixture();bot.currentWindow=null;bot.food=10;bot.health=18;bot.inventory={selectedItem:null,items:()=>items};
 bot.equip=async item=>{equips++;if(equipChanges)bot.heldItem=item;};
 bot.consume=async()=>{consumes++;if(consumeChanges){items[0].count--;bot.food=15;}};
 const context={module:{exports:{}},require:name=>name==='./inventory.cjs'?{refreshInventory:async()=>{refreshes++;onRefresh?.(bot,refreshes);return {items};}}:load(name),setTimeout,clearTimeout};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),context,{filename:file});
 return {bot,actions:context.module.exports,counts:()=>({refreshes,equips,consumes})};
}
test('equipment and eating verify actual held item/count without an automatic second attempt',async()=>{
 const f=equipmentFixture();const held=await f.actions.equip(f.bot,{item:'wooden_sword'},()=>{});assert.equal(held.held_item,'wooden_sword');
 const eaten=await f.actions.consume(f.bot,{item:'bread'},()=>{});assert.equal(eaten.consumed,1);assert.equal(eaten.after,1);assert.equal(f.counts().consumes,1);
});
for(const mode of ['unconfirmed_equip','unconfirmed_consume','stop'])test('equipment/food '+mode+' never repeats',async()=>{
 const f=equipmentFixture({equipChanges:mode!=='unconfirmed_equip',consumeChanges:mode!=='unconfirmed_consume'});let checks=0;
 await assert.rejects(f.actions.consume(f.bot,{item:'bread'},()=>{if(mode==='stop'&&++checks===1)throw Error('Stopped');}));
 assert.equal(f.counts().consumes,mode==='unconfirmed_consume'?1:0);assert.ok(f.counts().equips<=1);
});

test('sword sweep cannot hit an unselected nearby player or animal',()=>{
 const {bot,e}=fixture();bot.heldItem={name:'wooden_sword'};bot.entities[2]={id:2,name:'player',position:e.position.offset(.5,0,0)};
 assert.throws(()=>attackTarget(bot,{id:1,uuid:'exact'}),/sweep/);
 bot.entities[2].name='cow';assert.throws(()=>attackTarget(bot,{id:1,uuid:'exact'}),/sweep/);
 bot.heldItem={name:'wooden_axe'};assert.equal(attackTarget(bot,{id:1,uuid:'exact'}),e);
});

test('completed equipment/consumption mismatches preserve observations, not fabricated deltas',async()=>{
 for(const mode of ['equip','consume']){
  const f=equipmentFixture({equipChanges:mode!=='equip',consumeChanges:mode!=='consume'}),outcomes=require('../effect-outcome.cjs').create();let error;
  await assert.rejects(f.actions.consume(f.bot,{item:'bread'},()=>{},{settled:outcomes.settled}),e=>{error=e;return true;});
  const result=outcomes.get(error);assert.equal(result.kind,mode==='equip'?'settled_failed_equipment':'settled_failed_consumption');
  if(mode==='consume')assert.equal(result.consumed_count,null);
  assert.ok(f.counts().equips<=1&&f.counts().consumes<=1);
 }
});
test('food becoming full during confirmed equipment is a settled pre-consumption refusal',async()=>{
 const f=equipmentFixture({onRefresh:(bot,n)=>{if(n===2)bot.food=20;}}),outcomes=require('../effect-outcome.cjs').create();let error;
 await assert.rejects(f.actions.consume(f.bot,{item:'bread'},()=>{},{settled:outcomes.settled}),e=>{error=e;return true;});
 assert.equal(outcomes.get(error).stage,'before_consume');assert.equal(f.counts().consumes,0);assert.equal(f.counts().equips,1);
});
