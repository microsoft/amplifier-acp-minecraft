const {inventoryClient}=require('./inventory-client-fixture.cjs');
const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');const {Vec3}=require('vec3');
const {entities,sheepTarget,furnace}=require('../survival.cjs');
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
 bot.blockAt=()=>({name:'furnace'});bot.openFurnace=async()=>{opened=true;return {close:()=>{closed=true;}};};
 await assert.rejects(furnace(bot,new Vec3(1,0,0),{operation:'inspect'},()=>{if(opened)throw Error('Stopped');}),/Stopped/);
 assert.equal(closed,true);
});
