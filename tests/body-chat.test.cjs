// Exercise real chat listeners and durable inboxes without a game or model call.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Readable}=require('node:stream');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(name,semantic=false){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-chat-'));
 const config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:name,token:'fixture',agent_dialogue:true,bot_names:['BuilderOne','BuilderTwo'],conversation_attention:{enabled:semantic}}));
 const task={id:'expired-task',status:'budget_exhausted',deadline:1,turns:12,max_turns:12,progress:[]};
 fs.writeFileSync(path.join(home,'workshop.json'),JSON.stringify({events:[],task,turn:null,inbox:[]}));
 const bot=new EventEmitter();bot.username=name;bot.players={BuilderOne:{},BuilderTwo:{}};bot.loadPlugin=()=>{};
 let handle;
 const context=vm.createContext({require:n=>{
  if(n==='mineflayer')return {createBot:()=>bot};
  if(n==='node:http')return {createServer:handler=>{handle=handler;return {listen(){},close(){}};}};
  return realRequire(n);
 },module:{exports:{}},console:{log(){}},Buffer,
 process:{argv:['node','body.cjs',config],on(){},exit(){assert.fail('Unexpected process exit');}},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nmodule.exports={history,inbox};',context,{filename:'body.cjs'});
 return {bot,...context.module.exports,task,home,async request(url,payload){
  const req=Readable.from(payload===undefined?[]:[JSON.stringify(payload)]);
  Object.assign(req,{url,method:payload===undefined?'GET':'POST',headers:{authorization:'Bearer fixture'}});
  let code,body;await handle(req,{writeHead:c=>{code=c;},end:text=>{body=text;}});
  assert.equal(code,200,body);return JSON.parse(body);
 },close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('real chat listeners queue sentence-end addresses and keep expired work unchanged',()=>{
 const one=fixture('BuilderOne'),two=fixture('BuilderTwo');
 try{
  const say=message=>{one.bot.emit('chat','VisitorOne',message);two.bot.emit('chat','VisitorOne',message);};
  say('hi');assert.equal(one.inbox.length,0);assert.equal(two.inbox.length,0);
  say('what are you working on, builderone');
  assert.equal(one.inbox.length,1);assert.equal(two.inbox.length,0);
  say('how about you, buildertwo?');
  assert.equal(one.inbox.length,1);assert.equal(two.inbox.length,1);
  say('Can you show me?');
  assert.equal(one.inbox.length,1);assert.equal(two.inbox.length,2);
  for(const f of [one,two]){
   const saved=JSON.parse(fs.readFileSync(path.join(f.home,'workshop.json'),'utf8'));
   assert.deepEqual(saved.task,f.task);assert.equal(saved.turn,null);
   assert.equal(saved.inbox.length,f.inbox.length);
   for(const item of saved.inbox){
    const source=saved.events.find(e=>e.id===item.id);
    assert.equal(source.source,'human');assert.equal(source.accepted,true);
    assert.equal(source.message,item.message);
   }
  }
 }finally{one.close();two.close();}
});
test('own messages, incidental peer mentions and FYI updates do not start exchanges',()=>{
 const f=fixture('BuilderOne');try{
  f.bot.emit('chat','BuilderOne','How is it going, BuilderOne?');
  f.bot.emit('chat','VisitorOne','BuilderTwo, ask BuilderOne to help.');
  f.bot.emit('chat','BuilderTwo','@BuilderOne [FYI] Supplies delivered.');
  assert.equal(f.inbox.length,0);assert.equal(f.history.data.turn,null);
  assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});

test('semantic mode captures unnamed chat without immediately waking either agent',()=>{
 const f=fixture('BuilderOne',true);try{
  f.bot.emit('chat','VisitorOne',"hey, what are y'all working on?");
  assert.equal(f.inbox.length,0);
  assert.equal(f.history.data.participation_pending.length,1);
  assert.equal(f.history.data.events.find(e=>e.kind==='chat').accepted,false);
  assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});

test('host mode presents peer chatter as evidence without a name or intent classifier',()=>{
 const f=fixture('BuilderOne',true);try{
  f.bot.emit('chat','VisitorOne','Hello everyone');
  f.bot.emit('chat','BuilderTwo','I finished the roof. Does anyone need materials?');
  f.bot.emit('chat','BuilderTwo','[FYI] Waiting here.');
  assert.equal(f.history.data.participation_pending.length,3);
  assert.equal(f.inbox.length,0);
  assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});
test('private task endpoint preserves authorization without becoming public attention',async()=>{
 const f=fixture('BuilderOne',true);try{
  const reply=await f.request('/task',{text:'Private operator-only brief',reviewers:['BuilderTwo']});
  const control=f.history.data.events.find(e=>e.id===reply.request_id);
  assert.equal(control.provenance,'operator_control');assert.equal(control.source,'human');
  assert.equal(control.accepted,true);assert.equal(f.inbox[0].id,control.id);
  assert.equal(await f.request('/participation'),null);
  f.bot.emit('chat','VisitorOne','What are you building?');
  const proposal=await f.request('/participation');
  assert.equal(proposal.context.messages.length,1);
  assert.equal(proposal.context.messages[0].text,'What are you building?');
  assert.ok(!proposal.context.participants.some(p=>p.id==='Operator'));
  assert.ok(!JSON.stringify(proposal).includes('Private operator-only brief'));
  assert.equal(f.history.begin({request_id:control.id,goal:'Accepted private commission'}).request,control.message);
 }finally{f.close();}
});
