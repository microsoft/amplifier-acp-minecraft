// Actual body admission/receipt path; preparation is controlled to exercise races.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture({prepare,recipe,table=null}={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-craft-')),config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:'Crafter',token:'fixture'}));
 const bot=new EventEmitter(),calls={prepare:0,craft:0,close:0,refresh:0,move:0};
 bot.username='Crafter';bot.entity={position:new Vec3(.5,64,.5)};bot.players={};bot.entities={};
 bot.loadPlugin=()=>{};bot.clearControlStates=()=>{};bot.stopDigging=()=>{};bot.pathfinder={setGoal(){}};
 bot.registry={itemsByName:{stone_pickaxe:{id:1,name:'stone_pickaxe'}}};
 bot.currentWindow=null;bot.inventory={selectedItem:null,slots:Array(46).fill(null),items:()=>[]};
 bot.findBlock=()=>table;bot.recipesFor=(id,meta,count,t)=>recipe?.(bot,t,calls)||[];
 bot.closeWindow=()=>{calls.close++;bot.currentWindow=null;};
 const crafting=realRequire('./crafting.cjs'),spatial=realRequire('./spatial.cjs');
 const context=vm.createContext({require:name=>{
  if(name==='mineflayer')return {createBot:()=>bot};
  if(name==='node:http')return {createServer:()=>({listen(){},close(){}})};
  if(name==='./crafting.cjs')return {...crafting,prepare:async()=>{calls.prepare++;await prepare?.(bot);},craft:async()=>{calls.craft++;return {completed_recipes:1,crafted:1};}};
  if(name==='./inventory.cjs')return {refreshInventory:async()=>{calls.refresh++;}};
  if(name==='./spatial.cjs')return {...spatial,gotoWithProgress:async()=>{calls.move++;}};
  return realRequire(name);
 },structuredClone,module:{exports:{}},console:{log(){}},Buffer,
 process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected exit');}},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+`
 ready=true;
 const request=history.record({kind:'chat',source:'human',accepted:true,username:'Owner',message:'Craft a pickaxe',time:new Date().toISOString()});
 history.begin({request_id:request.id,goal:'Existing crafting task'});history.startTurn();turnUntil=Date.now()+240000;
 module.exports={operate,history};`,context,{filename:'body.cjs'});
 return {...context.module.exports,bot,calls,run:()=>context.module.exports.operate('craft',{item:'stone_pickaxe',count:1}),close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('clean initial no-recipe refusal has no effect admission or preparation and preserves task',async()=>{
 const f=fixture();try{
  const before=JSON.stringify(f.history.task());
  let refusal;await assert.rejects(f.run(),e=>{refusal=e;return true;});
  assert.equal(f.history.data.turn.actions.length,0,'read-only recipe refusal must not admit an uncertain effect');
  assert.match(refusal.message,/observed inventory.*no crafting preparation/);
  assert.deepEqual(f.calls,{prepare:0,craft:0,close:0,refresh:0,move:0});
  assert.equal(f.history.data.turn.actions.length,0);
  assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,0);
  assert.equal(f.history.data.events.at(-1).kind,'action_preflight_refused');
  assert.equal(f.history.data.events.at(-1).effect_attempted,false);
  assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});
for(const dirty of ['cursor','grid','output','open_table','open_container','missing_slots','missing_cursor'])test(`${dirty} cannot establish an initial no-recipe refusal`,async()=>{
 const f=fixture();try{
  if(dirty==='cursor')f.bot.inventory.selectedItem={type:2,count:1};
  if(dirty==='grid')f.bot.inventory.slots[1]={type:2,count:1};
  if(dirty==='output')f.bot.inventory.slots[0]={type:2,count:1};
  if(dirty.startsWith('open_'))f.bot.currentWindow={type:dirty==='open_table'?'minecraft:crafting':'minecraft:chest'};
  if(dirty==='missing_slots')f.bot.inventory.slots=Array(46);
  if(dirty==='missing_cursor')delete f.bot.inventory.selectedItem;
  await assert.rejects(f.run(),/after crafting preparation.*may have changed/);
  assert.equal(f.calls.prepare,1);assert.equal(f.calls.craft,0);assert.equal(f.calls.move,0);
  assert.equal(f.history.data.turn.actions.length,1);assert.equal(f.history.data.turn.actions[0].status,'uncertain');
  assert.equal(f.history.data.events.at(-1).kind,'action_failed');
  assert.equal(f.history.data.events.at(-1).settled_failure,undefined);
 }finally{f.close();}
});
test('recipe lost during preparation stays uncertain, without movement or craft retry',async()=>{
 const f=fixture({recipe:(_bot,_table,c)=>c.prepare===0?[{}]:[]});try{
  await assert.rejects(f.run(),/after crafting preparation/);
  assert.equal(f.calls.prepare,1);assert.equal(f.calls.craft,0);
  assert.equal(f.history.data.turn.actions[0].status,'uncertain');
 }finally{f.close();}
});
test('ingredients returned by preparation can still make a recipe possible',async()=>{
 const f=fixture({prepare:bot=>{bot.inventory.selectedItem=null;},recipe:(_bot,_table,c)=>c.prepare?[{}]:[]});try{
  f.bot.inventory.selectedItem={type:2,count:1};
  const result=await f.run();assert.equal(result.crafted,1);assert.equal(f.calls.craft,1);
  assert.equal(f.history.data.turn.actions[0].status,'succeeded');
 }finally{f.close();}
});
test('unknown item is rejected before admission even with a dirty cursor',async()=>{
 const f=fixture();try{
  f.bot.inventory.selectedItem={type:2,count:1};
  await assert.rejects(f.operate('craft',{item:'not_an_item',count:1}),/Unknown item/);
  assert.equal(f.calls.prepare,0);assert.equal(f.history.data.turn.actions.length,0);
 }finally{f.close();}
});
// Use the pinned production Mineflayer recipe queries, not a fixture recipe classifier.
test('actual Mineflayer recipe lookup admits inventory/table recipes and observes missing ingredients without packets',()=>{
 const registry=require('minecraft-data')('1.21.11'),Item=require('prismarine-item')(registry);
 const windows=require('prismarine-windows')(registry),inventory=windows.createWindow(0,'minecraft:inventory');
 const bot={registry,inventory,currentWindow:null,findBlock:()=>null};
 require('mineflayer/lib/plugins/craft')(bot);
 const preflight=require('../crafting.cjs').preflight;
 const snapshot=()=>JSON.stringify(inventory.slots);
 let before=snapshot();assert.throws(()=>preflight(bot,'stone_pickaxe'),/observed inventory/);assert.equal(snapshot(),before);
 inventory.updateSlot(9,new Item(registry.itemsByName.oak_log.id,1));
 before=snapshot();preflight(bot,'oak_planks');assert.equal(snapshot(),before);
 inventory.updateSlot(10,new Item(registry.itemsByName.cobblestone.id,3));
 inventory.updateSlot(11,new Item(registry.itemsByName.stick.id,2));
 assert.throws(()=>preflight(bot,'stone_pickaxe'),/observed inventory/);
 bot.findBlock=()=>({name:'crafting_table'});before=snapshot();preflight(bot,'stone_pickaxe');assert.equal(snapshot(),before);
});
