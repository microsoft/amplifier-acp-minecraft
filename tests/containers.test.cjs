const {inventoryClient}=require('./inventory-client-fixture.cjs');
const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');const {Vec3}=require('vec3');
const {container}=require('../containers.cjs');
function fixture({size=27}={}){
 const bot=new EventEmitter();bot.registry=require('minecraft-data')('1.21.1');
 const Item=require('prismarine-item')(bot.registry),windows=require('prismarine-windows')('1.21.1');
 const type=size===27?'minecraft:generic_9x3':'minecraft:generic_9x6';
 const server=windows.createWindow(1,type,'Storage'),client=windows.createWindow(1,type,'Storage');
 bot.inventory=windows.createWindow(0,'minecraft:inventory','Inventory');bot.currentWindow=null;
 bot.supportFeature=()=>true;bot.entity={position:new Vec3(0,0,0)};bot.world={raycast:()=>null};
 const p=new Vec3(1,0,0);bot.blockAt=()=>({name:'chest',position:p});
 const clone=i=>{if(!i)return null;const n=new Item(i.type,i.count,i.metadata,i.nbt);n.components=i.components.slice();return n;};
 const sync=()=>{for(let i=0;i<server.slots.length;i++)client.updateSlot(i,clone(server.slots[i]));client.selectedItem=clone(server.selectedItem);};
 let writes=0,closes=0,mode='normal';
 bot.activateBlock=async()=>{sync();bot.currentWindow=client;bot.emit('windowOpen',client);};
 bot.closeWindow=w=>{assert.equal(w.selectedItem,null,'must never close a held cursor');closes++;bot.currentWindow=null;};
 bot._client=inventoryClient((packet,a)=>{
  assert.equal(packet,'window_click');assert.equal(a.stateId,-1);
  if(a.mode===0){
   writes++;assert.ok(a.slot>=0,'must never click outside/drop');
   if(mode!=='ignore')server.acceptClick({...a,item:server.slots[a.slot]});
   if(mode==='concurrent'&&writes===2)server.updateSlot(5,new Item(bot.registry.itemsByName.dirt.id,2));
   if(mode==='disconnect'&&writes===2)throw Error('Disconnected after packet send');
   if(mode==='disconnect_first'&&writes===1)throw Error('Disconnected after picking up source');
   if(mode==='timeout'&&writes===1)return;
  }
  sync();bot.emit(`setWindowItems:${a.windowId}`);
 });
 const set=(slot,name,count)=>server.updateSlot(slot,new Item(bot.registry.itemsByName[name].id,count));
 return {bot,p,server,client,set,setMode:m=>{mode=m;},get writes(){return writes;},get closes(){return closes;},
  run:(operation,extra={},check=()=>{})=>container(bot,p,{expected:'chest',operation,...extra},check)};
}
test('partial deposit and withdrawal verify exact server deltas, preserve other supplies and close',async()=>{
 const f=fixture();f.set(27,'oak_planks',20);f.set(28,'coal',8);f.set(0,'oak_planks',62);
 const r=await f.run('deposit',{item:'oak_planks',count:7});
 assert.equal(r.verified,true);assert.deepEqual(r.before,{source:20,destination:62});assert.deepEqual(r.after,{source:13,destination:69});
 assert.equal(f.server.slots[0].count,64);assert.equal(f.server.slots[1].count,5);assert.equal(f.server.slots[28].count,8);
 const w=await f.run('withdraw',{item:'oak_planks',count:4});assert.equal(w.transferred,4);assert.equal(w.after.source,65);assert.equal(w.after.destination,17);assert.equal(f.closes,2);
});
test('64 items across source stacks and a double chest stay bounded',async()=>{
 const f=fixture({size:54});f.set(54,'dirt',33);f.set(55,'dirt',31);
 const r=await f.run('deposit',{item:'dirt',count:64});assert.equal(r.transferred,64);assert.equal(r.after.source,0);assert.ok(r.clicks<=6);assert.equal(f.server.slots[0].count,64);
});
test('source/capacity/count/type/reach/visibility failures perform no transfer',async()=>{
 const f=fixture();f.set(27,'oak_planks',10);
 for(let i=0;i<27;i++)f.set(i,'dirt',64);
 await assert.rejects(f.run('deposit',{item:'oak_planks',count:1}),/destination space/);
 await assert.rejects(f.run('withdraw',{item:'coal',count:1}),/Insufficient source/);
 await assert.rejects(f.run('deposit',{item:'oak_planks',count:65}),/1 to 64/);
 f.bot.blockAt=()=>({name:'trapped_chest'});await assert.rejects(f.run('inspect'),/ordinary chest/);
 f.bot.blockAt=()=>({name:'chest'});f.bot.entity.position=new Vec3(9,0,0);await assert.rejects(f.run('inspect'),/four blocks/);
 f.bot.entity.position=new Vec3(0,0,0);f.bot.world.raycast=()=>({position:new Vec3(0,0,0)});await assert.rejects(f.run('inspect'),/obstructed/);
 assert.equal(f.writes,0);
});
test('custom components are not mistaken for plain supplies with the same item name',async()=>{
 const f=fixture();f.set(27,'oak_planks',10);f.server.slots[27].components=[{type:'custom_name',data:'Special'}];
 await assert.rejects(f.run('deposit',{item:'oak_planks',count:1}),/component-bearing/);assert.equal(f.writes,0);
});
test('an ignored click fails without claiming a transfer or retrying',async()=>{
 const f=fixture();f.set(27,'oak_planks',10);f.setMode('ignore');
 const r=await f.run('deposit',{item:'oak_planks',count:4});assert.equal(r.verified,false);assert.equal(r.status,'unconfirmed');assert.equal(f.writes,1);assert.equal(f.closes,1);
});
test('concurrent storage changes stop the batch and keep its cursor inspectable/recoverable',async()=>{
 const f=fixture();f.set(27,'oak_planks',10);f.setMode('concurrent');
 const r=await f.run('deposit',{item:'oak_planks',count:4});assert.equal(r.verified,false);assert.equal(f.writes,2);assert.equal(f.closes,0);
 const observed=await f.run('inspect');assert.equal(observed.cursor.count,9);assert.equal(observed.contents.find(i=>i.name==='oak_planks').count,1);
 await assert.rejects(f.run('deposit',{item:'oak_planks',count:4}),/previous transfer/);
 f.setMode('normal');const recovered=await f.run('recover');assert.equal(recovered.recovered,true);assert.equal(f.server.slots[27].count,9);assert.equal(f.server.selectedItem,null);assert.equal(f.closes,1);
});
test('Stop after picking up a source stack sends no cleanup mutation and does not drop the cursor',async()=>{
 const f=fixture();f.set(27,'coal',64);
 const r=await f.run('deposit',{item:'coal',count:8},()=>{if(f.writes)throw Error('Stopped');});
 assert.equal(r.verified,false);assert.match(r.error,/Stopped/);assert.equal(f.writes,1);assert.equal(f.closes,0);
 assert.equal(f.server.selectedItem.count,64);
});
test('unknown outcome after a sent packet removes listeners and never repeats it',async()=>{
 const f=fixture();f.set(27,'coal',12);f.setMode('disconnect');
 const r=await f.run('deposit',{item:'coal',count:3});assert.equal(r.verified,false);assert.match(r.error,/Disconnected/);assert.equal(f.writes,2);
 assert.equal(f.bot.listenerCount('setWindowItems:1'),0);assert.equal(f.bot.listenerCount('windowOpen'),0);
});
test('Stop immediately after opening closes the empty-cursor window without clicks',async()=>{
 const f=fixture();await assert.rejects(f.run('inspect',{},()=>{if(f.bot.currentWindow)throw Error('Stopped');}),/Stopped/);
 assert.equal(f.closes,1);assert.equal(f.writes,0);assert.equal(f.bot.listenerCount('windowOpen'),0);
});
test('missing first-click acknowledgment cannot close a cursor that looks locally empty',async()=>{
 const f=fixture();f.set(27,'coal',64);f.setMode('disconnect_first');
 const r=await f.run('deposit',{item:'coal',count:1});assert.equal(r.verified,false);assert.equal(f.client.selectedItem,null);assert.equal(f.server.selectedItem.count,64);assert.equal(f.closes,0);
 f.setMode('normal');const inspected=await f.run('inspect');assert.equal(inspected.cursor.count,64);
 assert.equal((await f.run('recover')).recovered,true);assert.equal(f.server.slots[27].count,64);
});
test('acknowledgement timeout ends the batch with no retry or leaked listener',async()=>{
 const f=fixture();f.set(27,'coal',64);f.setMode('timeout');
 const r=await f.run('deposit',{item:'coal',count:1});assert.equal(r.verified,false);assert.equal(f.writes,1);assert.equal(f.closes,0);assert.equal(f.bot.listenerCount('setWindowItems:1'),0);
});
