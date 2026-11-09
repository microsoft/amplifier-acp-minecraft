// Exercise the actual body placement path against simulated server observations.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(item,properties={facing:'south'},actual=item,refusal=null){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-facing-'));
 const config=path.join(home,'config.json');fs.writeFileSync(config,JSON.stringify({username:'Builder',token:'fixture'}));
 const target=new Vec3(0,64,0),bot=new EventEmitter();let placed='air',sends=0,options=null,look=null,ordinary=0;
 bot.username='Builder';bot.entity={position:new Vec3(.5,64,1.5)};bot.players={};
 bot.loadPlugin=()=>{};bot.setControlState=()=>{};bot.clearControlStates=()=>{};bot.stopDigging=()=>{};
 bot.pathfinder={setGoal(){}};bot.inventory={items:()=>[{name:item,count:1}]};
 bot.equip=async i=>{bot.heldItem=i;};bot.lookAt=async p=>{look=p.minus(bot.entity.position);};
 bot.blockAt=p=>({name:p.equals(target)?placed:'stone',position:p,boundingBox:p.equals(target)?'empty':'block',getProperties:()=>p.equals(target)?properties:{}});
 const send=()=>{sends++;if(refusal)throw Error(refusal);placed=actual;bot.emit('blockUpdate',null,bot.blockAt(target));};
 bot._placeBlockWithOptions=async(block,normal,o)=>{assert.ok(block.position.plus(normal).equals(target));options=o;send();};
 bot.placeBlock=async()=>{ordinary++;send();};
 const spatial=realRequire('./spatial.cjs');
 const context=vm.createContext({require:name=>{
  if(name==='mineflayer')return {createBot:()=>bot};
  if(name==='node:http')return {createServer:()=>({listen(){},close(){}})};
  if(name==='./spatial.cjs')return {...spatial,gotoWithProgress:async()=>{}};
  if(name==='./inventory.cjs')return {refreshInventory:async()=>{}};
  return realRequire(name);
 },module:{exports:{}},console:{log(){}},Buffer,
 process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected exit');}},
 setTimeout:(fn,ms)=>setTimeout(fn,[100,180,250].includes(ms)?1:ms),clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+`
 ready=true;
 const request=history.record({kind:'chat',source:'human',accepted:true,username:'Owner',message:'Build the accepted project',time:new Date().toISOString()});
 history.begin({request_id:request.id,goal:'Existing construction task'});history.startTurn();turnUntil=Date.now()+240000;
 module.exports={operate,history};`,context,{filename:'body.cjs'});
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
