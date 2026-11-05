// Real placement/receipt path, with a simulated server block update. No game calls.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Vec3}=require('vec3');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(item,result){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-planting-'));
 const config=path.join(home,'config.json');fs.writeFileSync(config,JSON.stringify({username:'Farmer',token:'fixture'}));
 const p=new Vec3(0,64,0),bot=new EventEmitter();let placed='air',sends=0;
 bot.username='Farmer';bot.entity={position:new Vec3(.5,64,.5)};bot.players={};
 bot.loadPlugin=()=>{};bot.setControlState=()=>{};bot.clearControlStates=()=>{};bot.stopDigging=()=>{};
 bot.pathfinder={setGoal(){}};bot.inventory={items:()=>[{name:item,count:1}]};
 bot.equip=async i=>{bot.heldItem=i;};
 bot.blockAt=v=>({name:v.equals(p)?placed:'farmland',position:v,boundingBox:v.equals(p)?'empty':'block',getProperties:()=>v.equals(p)?{age:0}:{moisture:7}});
 bot.placeBlock=async()=>{sends++;placed=result;bot.emit('blockUpdate',null,bot.blockAt(p));};
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
 const request=history.record({kind:'chat',source:'human',accepted:true,username:'Owner',message:'Plant the existing garden',time:new Date().toISOString()});
 history.begin({request_id:request.id,goal:'Existing garden task'});history.startTurn();turnUntil=Date.now()+240000;
 module.exports={operate,history};`,context,{filename:'body.cjs'});
 return {...context.module.exports,run:()=>context.module.exports.operate('place',{x:0,y:64,z:0,item,support_face:'up'}),
  sends:()=>sends,close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('server crop results produce one successful action receipt without replay or task renewal',async()=>{
 for(const [item,block] of Object.entries({wheat_seeds:'wheat',beetroot_seeds:'beetroots',melon_seeds:'melon_stem',pumpkin_seeds:'pumpkin_stem',carrot:'carrots',potato:'potatoes'})){
  const f=fixture(item,block);try{
   const before={...f.history.task()},r=await f.run();assert.equal(r.verified,true);assert.equal(r.actual,block);
   assert.equal(r.properties.age,0);assert.equal(f.sends(),1);
   assert.equal(f.history.data.events.filter(e=>e.kind==='action_result').length,1);
   assert.equal(f.history.data.events.filter(e=>e.kind==='action_failed').length,0);
   assert.equal(f.history.task().deadline,before.deadline);assert.equal(f.history.task().turns,before.turns);
  }finally{f.close();}
 }
});
test('absent or wrong crop remains unconfirmed without automatically retrying placement',async()=>{
 for(const actual of ['air','beetroots','stone']){
  const f=fixture('wheat_seeds',actual);try{
   await assert.rejects(f.run(),/Placement mismatch/);assert.equal(f.sends(),1);
   assert.equal(f.history.data.events.filter(e=>e.kind==='action_result').length,0);
   assert.equal(f.history.data.events.filter(e=>e.kind==='action_failed').length,1);
  }finally{f.close();}
 }
});
