// Exercise the actual body placement path against simulated server observations.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(item,properties={facing:'south'},actual=item,refusal=null,onMove=null){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-facing-'));
 const config=path.join(home,'config.json');fs.writeFileSync(config,JSON.stringify({username:'Builder',token:'fixture'}));
 const target=new Vec3(0,64,0),bot=new EventEmitter();let placed='air',sends=0,options=null,look=null,ordinary=0;
 bot.username='Builder';bot.entity={position:new Vec3(.5,64,1.5)};bot.players={};
 bot.loadPlugin=()=>{};bot.setControlState=()=>{};bot.clearControlStates=()=>{};bot.stopDigging=()=>{};
 bot.pathfinder={setGoal(){}};bot.inventory={items:()=>[{name:item,count:1}]};
 bot.equip=async i=>{bot.heldItem=i;};bot.lookAt=async p=>{look=p.minus(bot.entity.position);};
 bot.blockAt=p=>({name:p.equals(target)?placed:'stone',position:p,boundingBox:p.equals(target)?'empty':'block',getProperties:()=>p.equals(target)?properties:{}});
 const send=()=>{sends++;if(typeof refusal==='function')return refusal(bot,target);if(refusal)throw Error(refusal);placed=actual;bot.emit('blockUpdate',null,bot.blockAt(target));};
 bot._placeBlockWithOptions=async(block,normal,o)=>{assert.ok(block.position.plus(normal).equals(target));options=o;return send();};
 bot.placeBlock=async()=>{ordinary++;return send();};
 const spatial=realRequire('./spatial.cjs');
 const context=vm.createContext({require:name=>{
  if(name==='mineflayer')return {createBot:()=>bot};
  if(name==='node:http')return {createServer:()=>({listen(_port,_host,start){start()},close(){}})};
  if(name==='./spatial.cjs')return {...spatial,gotoWithProgress:async()=>{if(onMove)await onMove(bot);}};
  if(name==='./inventory.cjs')return {refreshInventory:async()=>{}};
  return realRequire(name);
 },module:{exports:{}},console:{log(){}},Buffer,
 process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected exit');}},
 setTimeout:(fn,ms)=>setTimeout(fn,[100,180,250].includes(ms)?1:ms),clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+`
 ready=true;

 module.exports={operate:(name,args={})=>operate(name,{operation_id:crypto.randomUUID(),...args}),history};`,context,{filename:'body.cjs'});
 return {...context.module.exports,bot,run:facing=>context.module.exports.operate('place',{x:0,y:64,z:0,item,support_face:'up',...(facing?{facing}:{})}),
  observation:()=>({sends,options,look,ordinary}),close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
const furnaceLook={north:[0,1],south:[0,-1],east:[-1,0],west:[1,0]};
const stairsLook={north:[0,-1],south:[0,1],east:[1,0],west:[-1,0]};
for(const item of ['furnace','blast_furnace','smoker','repeater','comparator','oak_stairs','stone_brick_stairs']){
 test(`${item} places and verifies each requested horizontal facing`,async()=>{
  for(const facing of ['north','south','east','west']){
   const f=fixture(item,{facing,lit:false});try{
    const before=JSON.stringify(f.history.task()),result=await f.run(facing),o=f.observation();
    assert.equal(result.verified,true);assert.equal(result.actual,item);assert.equal(result.properties.facing,facing);
    assert.deepEqual([o.look.x===0?0:o.look.x,o.look.z===0?0:o.look.z],(item.endsWith('_stairs')?stairsLook:furnaceLook)[facing]);
    assert.equal(o.options.forceLook,'ignore');assert.equal(o.sends,1);assert.equal(o.ordinary,0);
    assert.equal(f.history.data.events.filter(e=>e.kind==='action_result').length,1);
    assert.equal(f.history.data.events.filter(e=>e.kind==='action_failed').length,0);
    assert.equal(JSON.stringify(f.history.task()),before,'placement must not modify work authority');
   }finally{f.close();}
  }
 });
}
test('wrong or absent server facing is reported without repairing or repeating the effect',async()=>{
 for(const item of ['furnace','oak_stairs','repeater','comparator'])for(const properties of [{facing:'west'},{}]){
  const f=fixture(item,properties);try{
   await assert.rejects(f.run('south'),/placed but.*facing.*inspect/i);assert.equal(f.observation().sends,1);
   assert.equal(f.history.data.events.filter(e=>e.kind==='action_result').length,0);
   assert.equal(f.history.data.events.filter(e=>e.kind==='action_failed').length,1);
  }finally{f.close();}
 }
});
test('a missing block cannot pass orientation verification',async()=>{
 const f=fixture('furnace',{facing:'south'},'air');try{
  await assert.rejects(f.run('south'),/Placement mismatch/);assert.equal(f.observation().sends,1);
 }finally{f.close();}
});
test('ordinary placement keeps its default behavior without an explicit facing',async()=>{
 const f=fixture('furnace',{facing:'west'});try{
  const r=await f.run();assert.equal(r.properties.facing,'west');assert.equal(f.observation().ordinary,1);assert.equal(f.observation().look,null);
 }finally{f.close();}
});
for(const race of ['target','support'])test('placement '+race+' changing during preparation is not a legacy no-effect refusal',async()=>{
 const f=fixture('cobblestone',{});try{
  const read=f.bot.blockAt,equip=f.bot.equip;let prepared=false;
  f.bot.equip=async item=>{await equip(item);prepared=true;};
  f.bot.blockAt=p=>prepared&&((race==='target'&&p.equals(new Vec3(0,64,0)))||(race==='support'&&p.equals(new Vec3(0,63,0))))?
   {position:p,name:race==='target'?'stone':'air',boundingBox:race==='target'?'block':'empty',getProperties:()=>({})}:read(p);
  await assert.rejects(f.run(),race==='target'?/changed during preparation/:/supporting block/);
  assert.equal(f.observation().sends,0);assert.equal(Object.values(f.history.data.operations)[0].status,'unknown');
  assert.notEqual(f.history.data.events.at(-1).error,'Target is not empty');
 }finally{f.close();}
});
test('initial occupied placement leaves no effect receipt and a changed empty target can be placed once',async()=>{
 const f=fixture('cobblestone',{});try{
  const read=f.bot.blockAt;let occupied=true;
  f.bot.blockAt=p=>occupied&&p.equals(new Vec3(0,64,0))?{position:p,name:'stone',boundingBox:'block',getProperties:()=>({})}:read(p);
  await assert.rejects(f.run(),/Target is not empty/);assert.equal(f.observation().sends,0);assert.equal(Object.values(f.history.data.operations).length,0);
  occupied=false;const result=await f.run();assert.equal(result.verified,true);assert.equal(f.observation().sends,1);
 }finally{f.close();}
});
test('unsupported explicit facing is rejected before inventory effects or movement',async()=>{
 for(const item of ['stone','oak_hanging_sign']){
  const f=fixture(item);try{
   await assert.rejects(f.run('south'),/facing.*supported/i);assert.equal(f.observation().sends,0);assert.equal(f.observation().look,null);
  }finally{f.close();}
 }
});
test('partial build retains failed coordinates, occupancy hints and authority without replay',async()=>{
 const f=fixture('oak_planks',{},'air','Server refused to place oak_planks: the block is still air');
 try{
  f.bot.entity.position=new Vec3(.5,64,.5);const before=JSON.stringify(f.history.task());
  const r=await f.operate('build',{item:'oak_planks',support_face:'up',blocks:[{x:0,y:64,z:0},{x:1,y:64,z:0}]});
  assert.equal(r.placed.length,0);assert.equal(r.failed_at.x,0);assert.equal(r.repair.code,'placement_unconfirmed');
  assert.equal(r.repair.observed.target_player_overlaps[0].self,true);assert.match(r.repair.next_steps.join(' '),/outside the placement cell/);
  assert.equal(f.observation().sends,1);assert.equal(JSON.stringify(f.history.task()),before);
  assert.equal(f.history.data.events.at(-1).result.repair.code,'placement_unconfirmed');
 }finally{f.close();}
});


test('redstone item verifies its placed wire block without accepting missing or different blocks',async()=>{
 for(const actual of ['redstone_wire','air','stone']){
  const f=fixture('redstone',{power:0},actual);try{
   if(actual==='redstone_wire'){
    const r=await f.run();assert.equal(r.verified,true);assert.equal(r.actual,'redstone_wire');assert.equal(r.properties.power,0);
    assert.equal(Object.values(f.history.data.operations)[0].status,'completed');
   }else await assert.rejects(f.run(),/Placement mismatch/);
   assert.equal(f.observation().sends,1);
  }finally{f.close();}
 }
});
for(const confirmed of [true,false])test('actual partial build '+(confirmed?'retains verified prefix and settled refusal':'retains unknown missing acknowledgment'),async()=>{
 const f=fixture('cobblestone',{});try{
  const placed=new Map(),first=new Vec3(0,64,0),second=new Vec3(1,64,0);
  f.bot.blockAt=p=>({position:p,type:p.y===63||placed.has(p.toString())?1:0,name:p.y===63||placed.has(p.toString())?'cobblestone':'air',boundingBox:p.y===63?'block':'empty',getProperties:()=>({})});
  let attempts=0;
  f.bot.placeBlock=async(support,normal)=>{attempts++;const dest=support.position.plus(normal);if(dest.equals(first)){placed.set(dest.toString(),true);return;}if(confirmed){f.bot.emit(`blockUpdate:${support.position}`,null,support);f.bot.emit(`blockUpdate:${dest}`,null,f.bot.blockAt(dest));}throw Error(`Server refused to place cobblestone at ${dest}: the block is still air`);};
  const before=JSON.stringify(f.history.task());
  const result=await f.operate('build',{item:'cobblestone',support_face:'up',blocks:[first,second,{x:2,y:64,z:0}]});
  assert.equal(attempts,2);assert.equal(result.placed.length,1);assert.equal(result.placed[0].verified,true);assert.equal(result.failed_at.x,1);assert.match(result.error,/Server refused/);
  assert.equal(Object.values(f.history.data.operations)[0].status,confirmed?'failed_settled':'unknown');
  assert.equal(!!result.settled_failure,confirmed);assert.equal(JSON.stringify(f.history.task()),before);
  assert.equal(f.bot.eventNames().filter(n=>String(n).startsWith('blockUpdate:')).length,0);
 }finally{f.close();}
});

for(const obstacle of ['cornflower',null,Error('Target is not empty'),Error('Read failed')])test('partial build distinguishes target refusal from an unclassified read error: '+obstacle,async()=>{
 const f=fixture('diorite',{});try{
  const placed=new Set();let sends=0,equips=0;
  f.bot.entity.position=new Vec3(2.5,64,.5);
  const equip=f.bot.equip;f.bot.equip=async item=>{equips++;await equip(item);};
  f.bot.blockAt=p=>{
   if(p.y===64&&p.x===4&&p.z===0&&obstacle instanceof Error)throw obstacle;
   if(p.y===64&&p.x===4&&p.z===0&&obstacle===null)return null;
   const name=p.y===63?'stone':placed.has(p.toString())?'diorite':p.y===64&&p.x===4&&p.z===0?obstacle:'air';
   return {position:p,name,boundingBox:name==='stone'||name==='diorite'?'block':'empty',getProperties:()=>({})};
  };
  f.bot.placeBlock=async(support,normal)=>{sends++;placed.add(support.position.plus(normal).toString());};
  const before=JSON.stringify(f.history.task());
  const result=await f.operate('build',{item:'diorite',support_face:'up',blocks:Array.from({length:6},(_,x)=>({x,y:64,z:0}))});
  assert.equal(sends,4);assert.equal(equips,4,'no preparation or placement for the refused fifth target');
  assert.equal(result.placed.length,4);assert.ok(result.placed.every(v=>v.verified&&v.actual==='diorite'));
  assert.equal(result.failed_at.x,4);
  if(obstacle instanceof Error){
   assert.equal(result.error,obstacle.message);assert.equal(Object.values(f.history.data.operations)[0].status,'unknown');
   assert.equal(result.settled_failure,undefined,'an error string is not internal refusal evidence');
   assert.equal(JSON.stringify(f.history.task()),before);return;
  }
  assert.equal(result.error,'Target is not empty');
  assert.equal(Object.values(f.history.data.operations)[0].status,'failed_settled');
  assert.equal(result.settled_failure.kind,'settled_partial_build');
  assert.equal(result.settled_failure.placement.phase,'target_preflight');
  assert.equal(result.settled_failure.placement.effect_attempted,false,'only the refused placement had no effect');
  assert.equal(result.settled_failure.placed.length,4,'the aggregate retains every verified effect');
  assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});

test('geometry clarity accompanies a verified production placement without another effect or authority change',async()=>{
 const f=fixture('cobblestone',{});try{
  const read=f.bot.blockAt;
  f.bot.blockAt=p=>{const b=read(p);return {...b,shapes:b.name!=='air'?[[0,0,0,1,1,1]]:[]};};
  const before=JSON.stringify(f.history.task()),result=await f.run();
  assert.equal(result.verified,true);assert.equal(result.position.y,64);
  assert.equal(result.placement_geometry.block.name,'cobblestone');
  assert.equal(result.placement_geometry.stance_above_full_block.feet.position.y,65);
  assert.equal(result.placement_geometry.stance_above_full_block.exact_target_obstructed,true,'fixture overhead is stone, not a safe destination');
  assert.equal(f.observation().sends,1);assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});

for(const mode of ['settled','unknown','timeout'])test('place carries approach outcome without placing: '+mode,async()=>{
 const f=fixture('cobblestone',{},'cobblestone',null,async bot=>{
  bot.entity.position=new Vec3(12,64,12);
  if(mode!=='settled'){const e=Error('unconfirmed movement');if(mode==='timeout')e.actionTimeout=true;throw e;}
 });try{
  await assert.rejects(f.run(),mode==='settled'?/Movement ended/:/unconfirmed/);
  assert.equal(f.observation().sends,0);
  assert.equal(Object.values(f.history.data.operations)[0].status,mode==='settled'?'failed_settled':'unknown');
  if(mode==='settled')assert.equal(f.history.data.events.at(-1).settled_failure.kind,'settled_failed_movement');
 }finally{f.close();}
});
