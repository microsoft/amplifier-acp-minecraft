// Actual body admission and follow path; disposable observations, no server.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs')),{Vec3}=realRequire('vec3');
const UUID='00000000-0000-4000-8000-000000000001';
function fixture({followDelay=1}={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-follow-')),config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:'Follower',token:'fixture'}));
 const target={id:42,uuid:UUID,name:'pig',position:new Vec3(2,64,0)},bot=new EventEmitter(),goals=[];let clears=0;
 Object.assign(bot,{username:'Follower',entity:{position:new Vec3(0,64,0)},players:{},entities:{42:target},loadPlugin(){},blockAt(){return null;},inventory:{items:()=>[],selectedItem:null},stopDigging(){},clearControlStates(){clears++;}});
 bot.pathfinder={setGoal(goal){goals.push(goal);}};
 const context=vm.createContext({require:n=>n==='mineflayer'?{createBot:()=>bot}:n==='node:http'?{createServer:()=>({listen(_port,_host,start){start()},close(){}})}:realRequire(n),module:{exports:{}},console:{log(){}},Buffer,
 process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected exit');}},setTimeout:(f,ms)=>setTimeout(f,ms===1000?followDelay:ms),clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+`
 ready=true;
 module.exports={operate:(name,args={})=>operate(name,{operation_id:crypto.randomUUID(),...args}),history};`,context,{filename:'body.cjs'});
 return {...context.module.exports,bot,target,goals,clears:()=>clears,run:(args={entity_id:42,uuid:UUID,seconds:1})=>context.module.exports.operate('follow',args),close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
for(const mode of ['missing','different_uuid','missing_player','ambiguous'])test('follow initial '+mode+' refuses before action admission or movement',async()=>{
 const f=fixture();try{
  let args={entity_id:42,uuid:UUID,seconds:1};
  if(mode==='missing')delete f.bot.entities[42];
  if(mode==='different_uuid')f.target.uuid='00000000-0000-4000-8000-000000000002';
  if(mode==='missing_player')args={player:'Absent',seconds:1};
  if(mode==='ambiguous')args={player:'Absent',entity_id:42,uuid:UUID,seconds:1};
  const before=JSON.stringify(f.history.task());
  await assert.rejects(f.run(args),mode==='ambiguous'?/Choose a player/:/identity changed/);
  assert.equal(Object.values(f.history.data.operations).length,0);assert.equal(f.goals.length,0);assert.equal(f.clears(),0);
  assert.equal(f.history.data.events.at(-1).kind,'action_preflight_refused');assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});
test('a fresh entity observation can be chosen after a stale refusal, once',async()=>{
 const f=fixture();try{
  delete f.bot.entities[42];await assert.rejects(f.run(),/identity changed/);
  f.bot.entities[42]=f.target;const result=await f.run();
  assert.equal(result.target.uuid,UUID);assert.equal(result.within_three_blocks,true);
  assert.equal(f.goals.filter(Boolean).length,1);assert.equal(f.goals.at(-1),null);
  assert.equal(Object.values(f.history.data.operations).length,1);assert.equal(Object.values(f.history.data.operations)[0].status,'completed');
 }finally{f.close();}
});
for(const mode of ['known_refusal','same_text_read_error','different_read_error'])test('follow recheck distinguishes '+mode+' before goal dispatch',async()=>{
 const f=fixture();try{
  let reads=0;const original=JSON.stringify(f.history.task());
  Object.defineProperty(f.bot,'entities',{get(){reads++;if(reads===1)return {42:f.target};if(mode==='known_refusal')return {};throw Error(mode==='same_text_read_error'?'Target identity changed or is not visible; inspect entities again':'Unknown read failure');}});
  await assert.rejects(f.run());assert.equal(f.goals.length,0);
  const action=Object.values(f.history.data.operations)[0];assert.ok(action);
  assert.equal(action.status,mode==='known_refusal'?'failed_settled':'unknown');
  if(mode==='known_refusal'){assert.equal(action.result.settled_failure.kind,'settled_follow_preflight');assert.equal(action.result.settled_failure.effect_attempted,false);}
  assert.equal(JSON.stringify(f.history.task()),original);
 }finally{f.close();}
});
test('loss after movement begins remains uncertain and is never redispatched',async()=>{
 const f=fixture();try{
  f.bot.pathfinder.setGoal=goal=>{f.goals.push(goal);if(goal)delete f.bot.entities[42];};
  await assert.rejects(f.run(),/no longer loaded/);
  assert.equal(f.goals.filter(Boolean).length,1);assert.equal(f.goals.at(-1),null);assert.equal(f.clears(),1);
  assert.equal(Object.values(f.history.data.operations)[0].status,'unknown');
 }finally{f.close();}
});
test('a goal-dispatch exception with preflight wording is not settlement proof',async()=>{
 const f=fixture();try{
  f.bot.pathfinder.setGoal=goal=>{f.goals.push(goal);throw Error('Target identity changed or is not visible; inspect entities again');};
  await assert.rejects(f.run());assert.equal(f.goals.filter(Boolean).length,1);assert.equal(Object.values(f.history.data.operations)[0].status,'unknown');
 }finally{f.close();}
});
test('named-player follow retains its original single movement and cleanup',async()=>{
 const f=fixture();try{
  f.bot.players.Friend={entity:f.target};const before=JSON.stringify(f.history.task());
  const r=await f.run({player:'Friend',seconds:1});assert.equal(r.target.uuid,UUID);assert.equal(f.goals.filter(Boolean).length,1);assert.equal(f.goals.at(-1),null);assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});
