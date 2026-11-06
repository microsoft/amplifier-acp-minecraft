const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module'),{Readable}=require('node:stream');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-lease-')),config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:'Builder',token:'fixture'}));
 const now=Date.now(),task={id:'accepted',status:'running',deadline:now+3600000,turns:120,max_turns:135,progress:[]};
 fs.writeFileSync(path.join(home,'workshop.json'),JSON.stringify({task,events:[],turn:null,inbox:[]}));
 const bot=new EventEmitter();Object.assign(bot,{username:'Builder',players:{},loadPlugin(){},pathfinder:{setGoal(){}},clearControlStates(){},stopDigging(){},entity:{position:{clone:()=>({x:0,y:64,z:0})}},health:20});
 let handle,current=now;const timers=new Set();
 class Clock extends Date{static now(){return current;}}
 const ctx=vm.createContext({require:n=>n==='mineflayer'?{createBot:()=>bot}:n==='node:http'?{createServer:h=>{handle=h;return {listen(){},close(){}};}}:realRequire(n),
 module:{exports:{}},console:{log(){}},Date:Clock,Buffer,process:{argv:['node','body.cjs',config],on(){},exit(){}},
 setTimeout:(fn,ms)=>{const t={fn,at:current+ms,unref(){}};timers.add(t);return t;},clearTimeout:t=>timers.delete(t)});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nready=true;module.exports={history,operate};',ctx);
 return {...ctx.module.exports,task,async request(url,payload,code=200,token='fixture'){
  const req=Readable.from(payload===undefined?[]:[JSON.stringify(payload)]);Object.assign(req,{url,method:payload===undefined?'GET':'POST',headers:{authorization:'Bearer '+token}});
  let status,text;await handle(req,{writeHead:x=>status=x,end:x=>text=x});assert.equal(status,code,text);return text?JSON.parse(text):null;
 },advance(ms){current+=ms;for(const t of [...timers])if(t.at<=current){timers.delete(t);t.fn();}},close(){fs.rmSync(home,{recursive:true,force:true});}};
}
test('actual body renews same turn without budget changes; authenticates control, denies stale replay and Stop',async()=>{
 const f=fixture();try{
  const start=await f.request('/turn',{renewable_lease:true,continuation:true});const r={lease_id:start.action_lease.lease_id,task_id:'accepted'};
  const before=JSON.stringify(f.history.data);
  f.advance(200000);const renewed=await f.request('/turn/renew',r);
  assert.ok(renewed.expires_at>start.action_lease.expires_at);assert.equal(JSON.stringify(f.history.data),before);
  await f.request('/turn/renew',r,401,'wrong');
  await f.request('/turn',{renewable_lease:true},400);
  await f.request('/stop',{});await f.request('/turn/renew',r,400);
  assert.equal((await f.request('/status')).turn_active,false);assert.equal(f.history.task().status,'stopped');
 }finally{f.close();}
});
test('actual body expires abandoned controller permission without polling and cannot resurrect it',async()=>{
 const f=fixture();try{
  const start=await f.request('/turn',{renewable_lease:true,continuation:true});
  f.advance(240001);assert.equal((await f.request('/status')).turn_active,false);
  await f.request('/turn/renew',{lease_id:start.action_lease.lease_id,task_id:'accepted'},400);
  await assert.rejects(()=>f.operate('chat',{text:'Late effect'}),/No active action lease/);
  assert.equal(f.history.task().turns,121);assert.equal(f.history.task().deadline,f.task.deadline);
 }finally{f.close();}
});
