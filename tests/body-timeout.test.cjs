// Exercise the real body/turn wiring with a controllable movement worker.
// No sockets, model requests, or game world are involved in this fixture.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const {boundedAction}=require('../action-deadline.cjs');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function fixture({ignoreCancel=false,cleanupMs=0}={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-timeout-'));
 const config=path.join(home,'config.json');fs.writeFileSync(config,JSON.stringify({username:'Fixture',token:'fixture'}));
 const bot=new EventEmitter();bot.username='Fixture';bot.entity={position:new Vec3(.5,64,.5)};bot.players={};
 bot.loadPlugin=()=>{};bot.clearControlStates=()=>{};bot.stopDigging=()=>{};
 let rejectMovement,releaseMovement,starts=0;
 bot.pathfinder={setGoal(goal){if(goal===null&&!ignoreCancel&&rejectMovement)setTimeout(()=>rejectMovement(Error('Movement cancelled')),cleanupMs);}};
 const actualSpatial=realRequire('./spatial.cjs');
 const spatial={...actualSpatial,gotoWithProgress(){starts++;return new Promise((resolve,reject)=>{rejectMovement=reject;releaseMovement=resolve;});}};
 const requireMock=name=>{
  if(name==='mineflayer')return {createBot:()=>bot};
  if(name==='node:http')return {createServer:()=>({listen(){},close(){}})};
  if(name==='./spatial.cjs')return spatial;
  if(name==='./containers.cjs')return {container:()=>spatial.gotoWithProgress()};
  if(name==='./action-deadline.cjs')return {boundedAction:(work,options)=>boundedAction(work,{...options,timeoutMs:10,settleMs:40})};
  return realRequire(name);
 };
 const context=vm.createContext({require:requireMock,module:{exports:{}},console:{log(){}},Buffer,
  process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected process exit');}},
  setTimeout:(fn,ms)=>setTimeout(fn,ms===60000?10:ms===250?1:ms),clearTimeout});
 const source=fs.readFileSync(process.env.WORKSHOP_TEST_BODY_PATH||path.join(root,'body.cjs'),'utf8');
 vm.runInContext(source+`
   ready=true;
   const fixtureRequest=history.record({kind:'chat',source:'human',accepted:true,whisper:false,username:'Fixture owner',message:'Existing task',time:new Date().toISOString()});
   history.begin({request_id:fixtureRequest.id,goal:'Existing bounded fixture responsibility'});
   history.startTurn();turnUntil=Date.now()+240000;
   module.exports={operate,history,state:()=>({busy,generation,turnUntil,task:history.task()})};
 `,context,{filename:'body.cjs'});
 return {...context.module.exports,starts:()=>starts,release:()=>releaseMovement?.(),
  close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('a settled move timeout preserves the turn for observation/reporting, without replay or budget renewal',async()=>{
 const f=fixture();try{
  const initial=f.state();const deadline=initial.task.deadline,turns=initial.task.turns;
  await assert.rejects(f.operate('move',{x:2,y:64,z:0,mode:'normal'}),/timed out/);
  assert.equal(f.state().turnUntil,initial.turnUntil);
  assert.equal(f.state().busy,false);assert.equal(f.state().task.status,'running');assert.equal(f.starts(),1);
  const receipt=f.history.data.events.at(-1);assert.equal(receipt.kind,'action_failed');
  assert.equal(receipt.operation_settled,true);assert.equal(receipt.turn_preserved,true);
  assert.equal(f.history.data.turn.actions[0].status,'uncertain');
  await f.operate('work_report',{status:'waiting',summary:'Timed-out move inspected; no arrival claimed.',wait_for:'A verified route change'});
  assert.equal(f.state().task.status,'waiting');assert.equal(f.state().task.deadline,deadline);assert.equal(f.state().task.turns,turns);
 }finally{f.close();}
});
test('human Stop wins both before timeout and during cancellation cleanup',async()=>{
 for(const stopAfterMs of [2,20]){
  const f=fixture({cleanupMs:25});try{
   const move=f.operate('move',{x:2,y:64,z:0,mode:'normal'});
   const failed=assert.rejects(move,/cancelled|timed out/);
   await wait(stopAfterMs);await f.operate('stop',{});await failed;
   assert.equal(f.state().turnUntil,0);assert.equal(f.state().task.status,'stopped');
   await assert.rejects(f.operate('work_report',{status:'running',summary:'Do not revive'}),/No active agent turn/);
  }finally{f.close();}
 }
});
test('an unsettled move closes the turn and holds busy until cleanup actually finishes',async()=>{
 const f=fixture({ignoreCancel:true});try{
  await assert.rejects(f.operate('move',{x:2,y:64,z:0,mode:'normal'}),/cancellation has not settled/);
  assert.equal(f.state().turnUntil,0);assert.equal(f.state().busy,true);
  assert.equal(f.history.data.events.at(-1).operation_settled,false);
  await assert.rejects(f.operate('move',{x:3,y:64,z:0,mode:'normal'}),/No active agent turn/);
  f.release();await wait(10);assert.equal(f.state().busy,false);assert.equal(f.starts(),1);
 }finally{f.close();}
});
test('a non-movement timeout retains the conservative closed-turn behavior',async()=>{
 const f=fixture();try{
  await assert.rejects(f.operate('container',{conversation_revision:(await f.operate('conversation')).revision,contents_revision:'fixture',x:2,y:64,z:0,operation:'deposit',item:'oak_planks',count:1}),/timed out/);
  assert.equal(f.state().turnUntil,0);assert.equal(f.state().busy,false);
  assert.equal(f.history.data.events.at(-1).operation_settled,true);
  assert.equal(f.history.data.events.at(-1).turn_preserved,false);
 }finally{f.close();}
});
