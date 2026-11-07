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
 const clone=i=>{if(!i)return null;const n=new Item(i.type,i.count,i.metadata,i.nbt);n.components=structuredClone(i.components);n.removedComponents=structuredClone(i.removedComponents||[]);return n;};
 const sync=()=>{for(let i=0;i<server.slots.length;i++)client.updateSlot(i,clone(server.slots[i]));client.selectedItem=clone(server.selectedItem);};
 let writes=0,closes=0,mode='normal';
 bot.activateBlock=async()=>{sync();bot.currentWindow=client;bot.emit('windowOpen',client);};
 bot.closeWindow=w=>{assert.equal(w.selectedItem,null,'must never close a held cursor');closes++;bot.currentWindow=null;};
 bot._client=inventoryClient((packet,a)=>{
  assert.equal(packet,'window_click');assert.equal(a.stateId,-1);
  if(a.mode===0){
   writes++;assert.ok(a.slot>=0,'must never click outside/drop');
   if(mode!=='ignore'){
    const held=clone(server.selectedItem),empty=!server.slots[a.slot];
    server.acceptClick({...a,item:server.slots[a.slot]});
    // The real server preserves components when right-click splits a stack;
    // prismarine-windows' local prediction constructs a fresh bare Item.
    if(empty&&held&&server.slots[a.slot]?.type===held.type){
     Object.assign(server.slots[a.slot],{nbt:held.nbt,components:structuredClone(held.components),removedComponents:structuredClone(held.removedComponents)});
    }
   }
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

test('a stick delivery between inspection and a competing transfer rejects the stale contents revision',async()=>{
 const f=fixture();f.set(27,'stick',4);const inspected=await f.run('inspect');
 f.set(0,'stick',2);const before=f.writes;
 await assert.rejects(f.run('deposit',{item:'stick',count:2,contents_revision:inspected.contents_revision}),/contents changed/);
 assert.equal(f.writes,before);assert.equal(f.server.slots[0].count,2);assert.equal(f.server.slots[27].count,4);
});
test('fresh torch handoff retains confirmed counts with a matching contents revision',async()=>{
 const f=fixture();f.set(0,'torch',8);
 const inspected=await f.run('inspect'),result=await f.run('withdraw',{item:'torch',count:8,contents_revision:inspected.contents_revision});
 assert.equal(result.verified,true);assert.equal(result.after.destination,8);assert.notEqual(result.contents_revision,inspected.contents_revision);
});
test('public cancellation during window opening is rechecked before the first item click',async()=>{
 const f=fixture();f.set(27,'stick',4);
 const before=f.writes;let checked=false;
 await assert.rejects(container(f.bot,f.p,{operation:'deposit',expected:'chest',item:'stick',count:2},()=>{},
  {beforeTransfer:()=>{checked=true;throw Error('New public cancellation');}}),/cancellation/);
 assert.equal(checked,true);assert.equal(f.writes,before);assert.equal(f.server.slots[27].count,4);
});

async function selection(f,operation,slot){
 const view=await f.run('inspect'),source=(operation==='deposit'?view.inventory:view.contents).find(i=>i.slot===slot);
 assert.ok(source,'inspection must expose exact window-relative source slot');
 return {item:source.name,count:1,contents_revision:view.contents_revision,source_slot:slot,source_item_revision:source.item_revision};
}
function special(f,slot,name='wooden_hoe',count=1,damage=7){
 f.set(slot,name,count);const i=f.server.slots[slot];
 i.components=[{type:'damage',data:damage},{type:'custom_name',data:'Loan tool'}];
 return structuredClone(i.components);
}
test('inspection identifies different tools and exact selected deposit/withdraw preserves components',async()=>{
 const f=fixture(),original=special(f,27);special(f,28,'wooden_hoe',1,2);
 const view=await f.run('inspect');assert.notEqual(view.inventory[0].item_revision,view.inventory[1].item_revision);
 const chosen=await selection(f,'deposit',27),r=await f.run('deposit',chosen);
 assert.equal(r.verified,true);assert.equal(f.server.slots[27],null);assert.deepEqual(f.server.slots[0].components,original);
 assert.equal(f.server.slots[28].components[0].data,2);
 const withdrawal=await f.run('withdraw',await selection(f,'withdraw',0));
 assert.equal(withdrawal.verified,true);assert.deepEqual(f.server.slots[27].components,original);assert.equal(f.server.slots[0],null);
});
test('selected metadata stack transfers a bounded partial count and returns its unchanged remainder',async()=>{
 const f=fixture(),components=special(f,27,'oak_planks',20);
 const a=await selection(f,'deposit',27);a.count=5;
 const r=await f.run('deposit',a);assert.equal(r.verified,true,JSON.stringify(r));assert.equal(r.transferred,5);
 assert.equal(f.server.slots[0].count,5);assert.equal(f.server.slots[1],null);assert.equal(f.server.slots[27].count,15);
 assert.deepEqual(f.server.slots[0].components,components);assert.deepEqual(f.server.slots[27].components,components);
});
test('selected item cannot silently change wear, count, NBT or removed components after inspection',async()=>{
 for(const change of [i=>i.components[0].data++,i=>i.count++,i=>{i.nbt={type:'compound',name:'',value:{note:{type:'string',value:'changed'}}};},i=>i.removedComponents=['custom_name']]){
  const f=fixture();special(f,27);const a=await selection(f,'deposit',27);change(f.server.slots[27]);
  await assert.rejects(f.run('deposit',a),/Selected source item changed/);assert.equal(f.writes,0);
 }
});
test('selection requires paired fresh fingerprints, correct direction and enough of that one stack',async()=>{
 const f=fixture();special(f,27);special(f,28);const a=await selection(f,'deposit',27);
 await assert.rejects(f.run('deposit',{...a,source_item_revision:undefined}),/Explicit selection/);
 await assert.rejects(f.run('deposit',{...a,source_slot:undefined}),/Explicit selection/);
 await assert.rejects(f.run('deposit',{...a,contents_revision:undefined}),/contents_revision/);
 await assert.rejects(f.run('withdraw',a),/outside the source/);
 await assert.rejects(f.run('deposit',{...a,count:2}),/Insufficient source/);
 assert.equal(f.writes,0);
});
test('selected transfers never merge into pre-existing same-name or same-component stacks',async()=>{
 const f=fixture();special(f,27,'oak_planks',10);special(f,0,'oak_planks',10);
 for(let i=1;i<27;i++)f.set(i,'dirt',64);
 await assert.rejects(f.run('deposit',await selection(f,'deposit',27)),/destination space/);
 assert.equal(f.writes,0);assert.equal(f.server.slots[0].count,10);
});
test('selected legacy NBT and removed components survive complete server-confirmed clicks',async()=>{
 const f=fixture();special(f,27);
 const nbt={type:'compound',name:'',value:{note:{type:'string',value:'Keep this'}}};
 f.server.slots[27].nbt=nbt;f.server.slots[27].removedComponents=['repair_cost'];
 const result=await f.run('deposit',await selection(f,'deposit',27));
 assert.equal(result.verified,true);assert.deepEqual(f.server.slots[0].nbt,nbt);assert.deepEqual(f.server.slots[0].removedComponents,['repair_cost']);
});
test('selected cursor recovery preserves metadata after interruption and never resends the transfer',async()=>{
 const f=fixture(),components=special(f,27,'oak_planks',12);const a=await selection(f,'deposit',27);a.count=4;
 f.setMode('concurrent');const result=await f.run('deposit',a);
 assert.equal(result.verified,false);assert.equal(f.writes,2);assert.equal(f.closes,1);
 f.setMode('normal');assert.deepEqual((await f.run('inspect')).cursor.components,components);
 const recovered=await f.run('recover');assert.equal(recovered.recovered,true);
 assert.equal(f.server.slots[27].count,11);assert.deepEqual(f.server.slots[27].components,components);
 assert.equal(f.server.slots[0].count,1);assert.equal(f.server.selectedItem,null);
});
test('lost selected pickup acknowledgement retains unknown state and permits reviewed cursor return only',async()=>{
 const f=fixture(),components=special(f,27);const a=await selection(f,'deposit',27);
 f.setMode('disconnect_first');const result=await f.run('deposit',a);
 assert.equal(result.verified,false);assert.equal(f.writes,1);assert.equal(f.closes,1);
 f.setMode('normal');const observed=await f.run('inspect');assert.deepEqual(observed.cursor.components,components);
 assert.equal((await f.run('recover')).recovered,true);assert.deepEqual(f.server.slots[27].components,components);
 assert.equal(f.server.slots[0],null);assert.equal(f.writes,2);
});
test('selected cursor whose identity changed cannot be returned as the original item',async()=>{
 const f=fixture();special(f,27);const a=await selection(f,'deposit',27);
 await f.run('deposit',a,()=>{if(f.writes)throw Error('Stopped');});
 f.server.selectedItem.components[0].data++;
 await assert.rejects(f.run('recover'),/Cannot safely return/);
 assert.equal(f.writes,1);assert.equal(f.closes,1);
});
test('obstruction failure returns exact current blocker geometry without opening or moving',async()=>{
 const f=fixture();let opens=0;f.bot.activateBlock=()=>{opens++;};
 f.bot.world.raycast=()=>({name:'oak_fence',position:new Vec3(0,1,0)});
 await assert.rejects(f.run('inspect'),error=>{
  assert.equal(error.details.code,'container_obstructed');assert.equal(error.details.blocker.name,'oak_fence');
  assert.deepEqual(error.details.blocker.position,new Vec3(0,1,0));assert.deepEqual(error.details.target.position,f.p);
  assert.deepEqual(error.details.eye,new Vec3(0,1.62,0));return true;
 });
 assert.equal(opens,0);assert.equal(f.writes,0);assert.deepEqual(f.bot.entity.position,new Vec3(0,0,0));
});
