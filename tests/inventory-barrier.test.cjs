const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {inventoryBarrier}=require('../inventory-barrier.cjs');
const {refreshInventory}=require('../inventory.cjs');
test('refresh waits for late inventory updates and ignores an unrelated pong',async()=>{
 const bot=new EventEmitter();bot.registry=require('minecraft-data')('1.21.1');bot.supportFeature=()=>true;
 const w=bot.inventory={id:0,slots:[],selectedItem:null,items:()=>[{name:'oak_log',count:2}]};
 const c=bot._client=new EventEmitter();let request,finished=false;
 c.write=(name,p)=>{if(name==='window_click')bot.emit('setWindowItems:0');else request=p;};
 const pending=refreshInventory(bot).then(r=>{finished=true;return r;});
 await new Promise(setImmediate);assert.ok(request);assert.equal(finished,false);
 c.emit('ping_response',{id:request.id+1n});await new Promise(setImmediate);assert.equal(finished,false);
 w.items=()=>[{name:'oak_planks',count:8}];bot.emit('setWindowItems:0');
 c.emit('ping_response',{id:[0,Number(request.id)]});
 assert.deepEqual((await pending).items,[{name:'oak_planks',count:8}]);
 assert.equal(c.listenerCount('ping_response'),0);assert.equal(c.listenerCount('end'),0);
});
test('missing confirmation and disconnect fail closed and remove listeners',async()=>{
 for(const scenario of ['timeout','disconnect','write']){
  const c=new EventEmitter();c.write=()=>{if(scenario==='write')throw Error('Write failed');};
  const p=inventoryBarrier({_client:c},{timeout:15});if(scenario==='disconnect')c.emit('end');
  await assert.rejects(p);assert.equal(c.listenerCount('ping_response'),0);assert.equal(c.listenerCount('end'),0);
 }
});
