// The real loopback body HTTP and MCP transports, with the game socket replaced
// by a disposable player. No model call or external Minecraft server.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter,once}=require('node:events'),{createRequire}=require('node:module');
const bodyFile=path.resolve(__dirname,'../body.cjs'), load=createRequire(bodyFile);
const {Vec3}=load('vec3');
const uuid='11111111-1111-4111-8111-111111111111';
async function fixture(t,extra={},legacy={}) {
  const home=fs.mkdtempSync(path.join(os.tmpdir(),'mc-direct-'));
  const file=path.join(home,'config.json');
  fs.writeFileSync(file,JSON.stringify({username:'Body',token:'owner',context_token:'context',context_grant:'grant',control_port:0,...extra}));
  const archive=JSON.stringify(legacy);fs.writeFileSync(path.join(home,'workshop.json'),archive);
  const bot=new EventEmitter(),sends=[],whispers=[];
  Object.assign(bot,{username:'Body',entity:{position:new Vec3(0,64,0)},players:{Sam:{username:'Sam',uuid}},
    inventory:{slots:[],selectedItem:null,items:()=>[]},loadPlugin(){},pathfinder:{setGoal(){}},clearControlStates(){},stopDigging(){},chat:s=>sends.push(s),whisper:(name,s)=>whispers.push([name,s])});
  const ctx=vm.createContext({require:n=>n==='mineflayer'?{createBot:()=>bot}:load(n),
    process:{argv:['node',bodyFile,file],on(){}},module:{exports:{}},console,Buffer,setTimeout,clearTimeout,structuredClone});
  vm.runInContext(fs.readFileSync(bodyFile,'utf8')+'\nmodule.exports={server,setReady(){ready=true;}};',ctx);
  const {server,setReady}=ctx.module.exports;
  if(!server.listening)await once(server,'listening');
  setReady(); const url='http://127.0.0.1:'+server.address().port;
  t.after(async()=>{await new Promise(r=>server.close(r));assert.equal(fs.readFileSync(path.join(home,'workshop.json'),'utf8'),archive);fs.rmSync(home,{recursive:true,force:true});});
  async function request(route,value,token='owner',headers={}) {
    const response=await fetch(url+route,{method:value===undefined?'GET':'POST',headers:{
      authorization:'Bearer '+token,'content-type':'application/json',accept:'application/json, text/event-stream',...headers},
      ...(value===undefined?{}:{body:JSON.stringify(value)})});
    const text=await response.text();return {status:response.status,value:text?JSON.parse(text):null};
  }
  const rpc=async(method,params)=>{const r=await request('/mcp',{id:1,jsonrpc:'2.0',method,params});assert.equal(r.status,200);return r.value.result;};
  const call=(name,args)=>rpc('tools/call',{name,arguments:args});
  return {home,bot,request,call,rpc,sends,whispers};
}
module.exports = {fixture,uuid};
