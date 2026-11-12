// Real body path with disposable terrain; no server, player or model calls.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
const xyz=p=>({x:p.x,y:p.y,z:p.z});
function fixture({far=false,onMove,onEquip,onDig,onDigGuard}={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-gather-'));
 const config=path.join(home,'config.json');fs.writeFileSync(config,JSON.stringify({username:'Builder',token:'fixture'}));
 const bot=new EventEmitter(),paver=new Vec3(1,63,0),quarry=new Vec3(3,64,0),second=new Vec3(4,64,0);
 const blocks=new Map([paver,quarry,second].map(p=>[p.toString(),'stone']));
 const dug=[],moves=[],items=[{name:'cobblestone',count:2},{name:'cobblestone',count:3}];let near=!far;
 bot.username='Builder';bot.entity={position:new Vec3(.5,64,2.5)};bot.players={};bot.entities={};bot.time={timeOfDay:0};
 bot.loadPlugin=()=>{};bot.clearControlStates=()=>{};bot.stopDigging=()=>{};bot.pathfinder={setGoal(){}};
 bot.inventory={items:()=>items};bot.equip=async()=>{onEquip?.(blocks,quarry);};
 bot.blockAt=p=>blocks.has(p.toString())&&blocks.get(p.toString())===null?null:({name:blocks.get(p.toString())||'air',position:p,boundingBox:'block',getProperties:()=>({})});
 // The old implementation selects this nearby player-made paver first.
 bot.findBlocks=({count})=>count===12?[paver,quarry,second]:[];
 bot.canDigBlock=()=>near;
 bot.dig=async b=>{dug.push(xyz(b.position));if(onDig)onDig(blocks,b.position);else{blocks.set(b.position.toString(),'air');items[0].count++;}};
 const spatial=realRequire('./spatial.cjs');
 const context=vm.createContext({require:name=>{
  if(name==='mineflayer')return {createBot:()=>bot};
  if(name==='node:http')return {createServer:()=>({listen(){},close(){}})};
  if(name==='./spatial.cjs')return {...spatial,digGuard(){onDigGuard?.();},harvestTool:()=>({name:'pickaxe'}),supported:()=>true,route:()=>({reachable:true}),localMap:()=>({}),
   gotoWithProgress:async(_bot,goal)=>{moves.push(goal);bot.entity.position=new Vec3(goal.x,goal.y,goal.z);near=true;onMove?.(blocks,quarry);}};
  return realRequire(name);
 },structuredClone,module:{exports:{}},console:{log(){}},Buffer,
 process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected exit');}},
 setTimeout:(fn,ms)=>setTimeout(fn,[200,250,350,700].includes(ms)?1:ms),clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+`
 ready=true;
 const request=history.record({kind:'chat',source:'human',accepted:true,username:'Owner',message:'Gather for the accepted project',time:new Date().toISOString()});
 history.begin({request_id:request.id,goal:'Existing construction task'});history.startTurn();turnUntil=Date.now()+240000;
 module.exports={operate,history,mcpServer};`,context,{filename:'body.cjs'});
 return {...context.module.exports,bot,blocks,dug,moves,paver,quarry,second,
  run:a=>context.module.exports.operate('gather',{block:'stone',count:1,...a}),
  close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('unselected nearby paver is never substituted for a selected quarry block',async()=>{
 const f=fixture();try{
  const before=JSON.stringify(f.history.task()),r=await f.run({targets:[xyz(f.quarry)]});
  assert.deepEqual(f.dug,[xyz(f.quarry)]);assert.equal(f.blocks.get(f.paver.toString()),'stone');
  assert.equal(r.mined,1);assert.equal(r.removed[0].position.x,3);assert.equal(r.removed[0].after,'air');
  assert.equal(r.collected.find(i=>i.name==='cobblestone').count,1,'inventory deltas sum multiple stacks');
  assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});
test('missing, invalid or duplicate selection is refused before any movement or digging',async()=>{
 for(const input of [{},{targets:[]},{targets:[{x:NaN,y:64,z:0}]},{targets:[{x:1.5,y:64,z:0}]},
  {targets:[{x:30,y:64,z:0}]},{targets:Array(9).fill({x:3,y:64,z:0})},{targets:[{x:3,y:64,z:0},{x:3,y:64,z:0}]},
  {count:2,targets:[{x:3,y:64,z:0}]}]){
  const f=fixture();try{await assert.rejects(f.run(input),/target|selection|count/i);assert.equal(f.dug.length,0);assert.equal(f.moves.length,0);assert.equal(f.history.data.turn.actions.length,0);assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,0);}finally{f.close();}
 }
});
test('a changed or unloaded selected block stops the batch without finding replacements',async()=>{
 for(const replacement of ['oak_planks','air',null]){
  const f=fixture();try{
   f.blocks.set(f.quarry.toString(),replacement);
   const r=await f.run({count:2,targets:[xyz(f.quarry),xyz(f.second)]});
   assert.equal(r.mined,0);assert.equal(f.dug.length,0);assert.match(r.blocked,/changed|unloaded/i);
   assert.equal(f.blocks.get(f.paver.toString()),'stone');
  }finally{f.close();}
 }
});
test('terrain is rechecked after movement and asynchronous tool equip',async()=>{
 for(const opts of [{far:true,onMove:(b,p)=>b.set(p.toString(),'oak_planks')},{onEquip:(b,p)=>b.set(p.toString(),'oak_planks')}]){
  const f=fixture(opts);try{
   const r=await f.run({targets:[xyz(f.quarry)]});assert.equal(f.dug.length,0);assert.equal(r.mined,0);assert.match(r.blocked,/changed/i);
  }finally{f.close();}
 }
});
test('partial batch reports exactly removed targets and leaves a changed next target alone',async()=>{
 const f=fixture({onDig:(b,p)=>{b.set(p.toString(),'air');b.set('(4, 64, 0)','oak_planks');}});try{
  const r=await f.run({count:2,targets:[xyz(f.quarry),xyz(f.second)]});
  assert.equal(r.mined,1);assert.equal(r.removed.length,1);assert.deepEqual(f.dug,[xyz(f.quarry)]);assert.match(r.blocked,/changed/i);
 }finally{f.close();}
});
test('unconfirmed removal is not counted or retried and prevents further batch effects',async()=>{
 const f=fixture({onDig(){}});try{
  const r=await f.run({count:2,targets:[xyz(f.quarry),xyz(f.second)]});
  assert.equal(r.mined,0);assert.equal(r.removed.length,0);assert.equal(f.dug.length,1);assert.match(r.error,/confirm/i);
  assert.equal(f.history.data.events.at(-1).kind,'action_result');
  assert.equal(f.history.data.turn.actions.at(-1).status,'uncertain');
 }finally{f.close();}
});
test('explicit order and count bound the batch without inferring that targets are natural',async()=>{
 const f=fixture();try{
  const r=await f.run({targets:[xyz(f.second),xyz(f.quarry)],count:1});
  assert.deepEqual(f.dug,[xyz(f.second)]);assert.equal(r.mined,1);assert.equal(f.blocks.get(f.quarry.toString()),'stone');
  assert.match(r.warning,/cannot prove natural origin/);
 }finally{f.close();}
});
test('Stop during asynchronous equip prevents mining and remains stopped',async()=>{
 let f;f=fixture({onEquip:()=>{f.operate('stop');}});try{
  await assert.rejects(f.run({targets:[xyz(f.quarry)]}),/cancelled/);
  assert.equal(f.dug.length,0);assert.equal(f.history.task().status,'stopped');
 }finally{f.close();}
});

test('actual body blocks repeated unchanged occupied placement before another action admission',async()=>{
 const f=fixture();try{
  const a={...xyz(f.quarry),item:'oak_planks'},before=JSON.stringify(f.history.task());
  for(let i=0;i<2;i++)await assert.rejects(f.operate('place',a),/Target is not empty/);
  await assert.rejects(f.operate('place',a),e=>e.details.retry_guard.effect_attempted===false);
  assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,2);
  assert.equal(f.history.data.events.at(-1).kind,'action_retry_blocked');
  assert.equal(f.dug.length,0);assert.equal(f.moves.length,0);assert.equal(JSON.stringify(f.history.task()),before);
  await f.operate('inspect',xyz(f.quarry));
  await assert.rejects(f.operate('place',a),/Unchanged failed action/,'inspection alone must not clear the known condition');
  f.blocks.set(f.quarry.toString(),'air');
  await assert.rejects(f.operate('place',a),e=>!e.details?.retry_guard);
  assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,3,'changed terrain reaches original live checks');
 }finally{f.close();}
});

test('settled pickup-route failure retains confirmed harvest and permits fresh planning without claiming success',async()=>{
 const f=fixture({onMove(){throw Object.assign(Error('Fixture route refused after partial movement'),{movementOperationSettled:true});}});try{
  f.bot.entities={1:{name:'item',position:f.quarry.offset(1,0,0)}};
  const r=await f.run({targets:[xyz(f.quarry),xyz(f.second)],count:2});
  assert.equal(r.mined,1);assert.deepEqual(f.dug,[xyz(f.quarry)]);assert.equal(f.blocks.get(f.second.toString()),'stone');
  assert.equal(r.settled_failure.kind,'settled_partial_gather');assert.equal(r.settled_failure.reached,false);
  assert.match(r.blocked,/partial movement/);assert.equal(r.error,undefined);
  assert.equal(f.history.data.turn.actions[0].status,'failed_settled');
  f.history.data.turn.activity=true;f.history.data.turn.task_id=null;
  f.history.data.turn.activity_report={status:'running'};f.history.finish();
  const policy=require('../activity-policy.cjs'),cfg={human_engagement:{enabled:true,task_optional:true}};
  assert.equal(policy.allowed(f.history,cfg),true);assert.equal(policy.canContinue(f.history,cfg),true);
  assert.equal(f.dug.length,1,'settlement never retries the remaining targets');
 }finally{f.close();}
});
test('unconfirmed block removal is still uncertain and cannot become a settled movement failure',async()=>{
 const f=fixture({onDig(){}});try{
  const r=await f.run({targets:[xyz(f.quarry)]});assert.match(r.error,/did not confirm/);
  assert.equal(r.settled_failure,undefined);assert.equal(f.history.data.turn.actions[0].status,'uncertain');
 }finally{f.close();}
});

test('supporting-player dig refusal happens before any admitted effect',async()=>{
 const f=fixture({onDigGuard(){throw Error('Refusing to remove a block supporting a player; move to safe footing first');}});try{
  await assert.rejects(f.operate('dig',{...xyz(f.quarry),expected:'stone'}),/supporting a player/);
  assert.equal(f.dug.length,0);assert.equal(f.history.data.turn.actions.length,0);
  assert.equal(f.history.data.events.at(-1).kind,'action_preflight_refused');assert.equal(f.history.data.events.at(-1).effect_attempted,false);
 }finally{f.close();}
});
