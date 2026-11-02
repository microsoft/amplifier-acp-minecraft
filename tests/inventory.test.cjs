const test=require('node:test');const assert=require('node:assert/strict');const {EventEmitter}=require('node:events');
const {refreshInventory}=require('../inventory.cjs');
function fixture(){const bot=new EventEmitter();bot.registry=require('minecraft-data')('1.21.1');bot.supportFeature=()=>true;bot.inventory={id:0,slots:[],type:"minecraft:inventory",selectedItem:null,items:()=>[{name:'oak_planks',count:4}]};return bot;}
test('inventory refresh replaces optimistic counts with the server snapshot',async()=>{
 const bot=fixture();bot._client={write:(name,p)=>{assert.equal(name,'window_click');assert.equal(p.stateId,-1);assert.equal(p.slot,-999);bot.inventory.items=()=>[];bot.emit('setWindowItems:0');}};
 const result=await refreshInventory(bot);assert.deepEqual(result.items,[]);assert.equal(result.source,'server inventory snapshot');assert.equal(bot.listenerCount('setWindowItems:0'),0);
});
test('a failed inventory request removes its acknowledgment listener',async()=>{
 const bot=fixture();bot._client={write:()=>{throw Error('Disconnected');}};
 await assert.rejects(refreshInventory(bot),/Disconnected/);assert.equal(bot.listenerCount('setWindowItems:0'),0);
});
test('an open container snapshot reads its player slots rather than stale closed inventory',async()=>{
 const bot=fixture();bot.currentWindow={id:4,slots:[],type:"minecraft:furnace",selectedItem:null,items:()=>[{name:'iron_ingot',count:2}]};
 bot._client={write:()=>bot.emit('setWindowItems:4')};
 assert.deepEqual((await refreshInventory(bot)).items,[{name:'iron_ingot',count:2}]);
});

 test('inventory reports cursor and crafting-grid materials separately',async()=>{
 const bot=fixture(),Item=require('prismarine-item')(bot.registry);
 bot.inventory.selectedItem=new Item(bot.registry.itemsByName.oak_log.id,5);
 bot.inventory.slots=[null,new Item(bot.registry.itemsByName.birch_log.id,1),null,null,null];
 bot._client={write:()=>bot.emit('setWindowItems:0')};
 const result=await refreshInventory(bot);assert.deepEqual(result.cursor,{name:'oak_log',count:5});
 assert.deepEqual(result.crafting_grid[0],{name:'birch_log',count:1});
 });
