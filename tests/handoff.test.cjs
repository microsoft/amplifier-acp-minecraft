const test=require('node:test'),assert=require('node:assert/strict');const {Vec3}=require('vec3');
const {pickupTracker}=require('../handoff.cjs');
const {give}=require('../handoff.cjs');const {EventEmitter}=require('node:events');
function fixture(){const bot={entities:{}};const t=pickupTracker({item:'oak_planks',count:4,origin:new Vec3(0,1,0),existing:new Set([1]),recipient:20,sender:10});
 const drop=(id,count=4)=>{const e={id,uuid:'uuid'+id,name:'item',position:new Vec3(0,1,0)};bot.entities[id]=e;t.drop(e,{name:'oak_planks',count});};return {t,bot,drop};}
test('handoff requires matching new drops and pickup by the intended recipient',()=>{
 const {t,bot,drop}=fixture();drop(1);t.collect({collectedEntityId:1,collectorEntityId:20,pickupItemCount:4});assert.equal(t.result(bot).status,'unconfirmed');
 drop(2);t.collect({collectedEntityId:2,collectorEntityId:30,pickupItemCount:4});assert.equal(t.result(bot).status,'unconfirmed');
});
test('partial or ambiguous pickup cannot claim a delivered handoff',()=>{
 const {t,bot,drop}=fixture();drop(2);t.collect({collectedEntityId:2,collectorEntityId:20,pickupItemCount:2});assert.equal(t.result(bot).status,'unconfirmed');
 t.collect({collectedEntityId:2,collectorEntityId:20,pickupItemCount:2});assert.equal(t.result(bot).status,'pickup_observed');
 drop(3);assert.equal(t.result(bot).status,'unconfirmed');assert.equal(t.result(bot).ambiguous,true);
});
test('a sender recovering the drop is not delivery, and old entity positions are not reused',()=>{
 const {t,bot,drop}=fixture();drop(2);t.collect({collectedEntityId:2,collectorEntityId:10,pickupItemCount:4});
 bot.entities[2].uuid='reused-id';const result=t.result(bot);assert.equal(result.status,'recovered_by_sender');assert.equal(result.drops[0].position,null);
});
test('cancelled handoff removes packet listeners and never retries a tossed stack',async()=>{
 const bot=new EventEmitter(),client=new EventEmitter();bot._client=client;bot.username='Sender';bot.registry=require('minecraft-data')('1.21.1');
 bot.entity={id:10,position:new Vec3(0,0,0)};bot.entities={};bot.players={Taker:{entity:{id:20,position:new Vec3(2,0,0)}}};
 bot.inventory={id:0,slots:[],type:"minecraft:inventory",selectedItem:null,items:()=>[{name:'oak_planks',count:4,type:1}]};bot.supportFeature=()=>true;
 client.write=()=>bot.emit('setWindowItems:0');bot.world={raycast:()=>null};bot.lookAt=async()=>{};let tosses=0;
 bot.tossStack=async()=>{tosses++;};
 await assert.rejects(give(bot,{player:'Taker',item:'oak_planks',count:4},()=>{if(tosses)throw Error('Stopped');}),/Stopped/);
 assert.equal(tosses,1);assert.equal(bot.listenerCount('itemDrop'),0);assert.equal(client.listenerCount('collect'),0);
});
