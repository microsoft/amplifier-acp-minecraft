// Exercise the real body/turn wiring with a controllable movement worker.
// No sockets, model requests, or game world are involved in this fixture.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const {boundedAction}=require('../action-deadline.cjs');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function fixture({ignoreCancel=false,cleanupMs=0,timeoutMs=10}={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-timeout-'));
 const config=path.join(home,'config.json');fs.writeFileSync(config,JSON.stringify({username:'Fixture',token:'fixture'}));
 const bot=new EventEmitter();bot.username='Fixture';bot.entity={position:new Vec3(.5,64,.5)};bot.players={};bot.entities={1:{id:1,uuid:'fixture-target',position:new Vec3(2,64,0)}};
 bot.loadPlugin=()=>{};bot.blockAt=()=>null;bot.clearControlStates=()=>{};bot.stopDigging=()=>{};
 let rejectMovement,releaseMovement,starts=0;
 bot.pathfinder={setGoal(goal){if(goal===null&&!ignoreCancel&&rejectMovement)setTimeout(()=>rejectMovement(Error('Movement cancelled')),cleanupMs);}};
 const actualSpatial=realRequire('./spatial.cjs');
 const spatial={...actualSpatial,gotoWithProgress(){starts++;return new Promise((resolve,reject)=>{rejectMovement=reject;releaseMovement=resolve;});}};
 const requireMock=name=>{
  if(name==='mineflayer')return {createBot:()=>bot};
  if(name==='node:http')return {createServer:()=>({listen(_port,_host,start){start()},close(){}})};
  if(name==='./spatial.cjs')return spatial;
  if(name==='./containers.cjs')return {preflight(){},container:()=>spatial.gotoWithProgress()};
  if(name==='./action-deadline.cjs')return {boundedAction:(work,options)=>boundedAction(work,{...options,timeoutMs,settleMs:40})};
  return realRequire(name);
 };
 const context=vm.createContext({require:requireMock,module:{exports:{}},console:{log(){}},Buffer,
  process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected process exit');}},
  setTimeout:(fn,ms)=>setTimeout(fn,ms===250?1:ms),clearTimeout});
 const source=fs.readFileSync(process.env.WORKSHOP_TEST_BODY_PATH||path.join(root,'body.cjs'),'utf8');
 vm.runInContext(source+`
   ready=true;
   module.exports={operate,history,state:()=>({busy,generation,activeId})};
 `,context,{filename:'body.cjs'});
 return {...context.module.exports,starts:()=>starts,release:()=>releaseMovement?.(),fail:(settled=true)=>rejectMovement?.(Object.assign(Error('Fixture route failed'),{movementOperationSettled:settled})),
  bot,
  close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
const move={x:2,y:64,z:0,mode:'normal',operation_id:'movement-1'};
test('uncertain movement remains exclusive through cancellation and cannot be replayed',async()=>{
 const f=fixture({ignoreCancel:true});try{
  await assert.rejects(f.operate('move',move),/cancellation has not settled/);
  assert.equal(f.state().busy,true);
  await assert.rejects(f.operate('move',{...move,operation_id:'movement-2'}),/in progress/);
  f.release();await wait(20);assert.equal(f.state().busy,false);
  await assert.rejects(f.operate('move',move),/unknown/);
  await assert.rejects(f.operate('move',{...move,x:3,operation_id:'movement-2'}),/uncertain receipt/);
  assert.equal(f.starts(),1);
 }finally{f.close();}
});
test('Stop during movement cancels and persists through timeout',async()=>{
 const f=fixture({cleanupMs:25});try{
  const original=assert.rejects(f.operate('move',move));
  await wait(2);await f.operate('stop');await original;
  assert.ok(f.history.data.stopped);
  await assert.rejects(f.operate('move',{...move,operation_id:'movement-2'}),/stopped/);
 }finally{f.close();}
});
test('movement cancellation must address the original active operation',async()=>{
 const f=fixture({ignoreCancel:true,timeoutMs:1000});try{
  const original=assert.rejects(f.operate('move',move));
  await wait(5);
  await assert.rejects(f.operate('cancel_movement',{target_operation_id:'another-id'}),/not active/);
  assert.equal((await f.operate('cancel_movement',{target_operation_id:move.operation_id})).cancellation_requested,true);
  f.release();await original;assert.equal(f.starts(),1);
 }finally{f.close();}
});
