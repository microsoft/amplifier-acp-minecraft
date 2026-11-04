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
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nmodule.exports={history,inbox,operate,startFixtureTurn(){ready=true;turnUntil=Date.now()+240000;history.startTurn();}};',context,{filename:'body.cjs'});
 return {bot,...context.module.exports,task,home,async request(url,payload,expectedStatus=200){
  const req=Readable.from(payload===undefined?[]:[JSON.stringify(payload)]);
  Object.assign(req,{url,method:payload===undefined?'GET':'POST',headers:{authorization:'Bearer fixture'}});
  let code,body;await handle(req,{writeHead:c=>{code=c;},end:text=>{body=text;}});
  assert.equal(code,expectedStatus,body);return JSON.parse(body);
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

test('shared history includes separately recorded public sends, never failed tool inputs',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=text=>sent.push(text);f.startFixtureTurn();
  await f.operate('chat',{text:'The dock framing is ready.'});
  await f.operate('tell',{player:'BuilderTwo',intent:'update',text:'Public supplies delivered.'});
  await f.request('/reply',{text:'Public reply from the controller.'});
  const canary='PRIVATE_FAILED_SEND_CANARY';
  f.bot.chat=()=>{throw Error(canary);};
  await assert.rejects(f.operate('tell',{player:'BuilderTwo',intent:'request',text:canary}),new RegExp(canary));
  const publicEvents=f.history.data.events.filter(e=>e.kind==='chat_sent');
  assert.deepEqual(publicEvents.map(e=>e.sent),sent,'each successful public send has exactly one receipt');
  assert.ok(publicEvents.every(e=>e.provenance==='minecraft_public_chat'));
  const cfg={username:'BuilderOne',context_grant:'fixture-grant'};
  const shared=f.history.query({operation:'read',limit:40,access:{mode:'grant',grant:'fixture-grant'}},cfg,{});
  assert.deepEqual(shared.messages.filter(e=>e.label==='chat_sent').map(e=>e.text),sent);
  assert.ok(!JSON.stringify(shared).includes(canary));
  const owner=f.history.query({operation:'read',limit:40,access:{mode:'owner'}},cfg,{});
  assert.ok(JSON.stringify(owner).includes(canary));
 }finally{f.close();}
});

test('real participation route reports stable rejections and rechecks capacity after preflight',async()=>{
 const f=fixture('BuilderOne',true);try{
  f.bot.emit('chat','VisitorOne','How is it going?');
  const proposal=await f.request('/participation');
  assert.equal(proposal.delivery.eligible,true);
  // Capacity changes after GET; the POST must reject instead of trusting preflight.
  for(let i=0;i<8;i++)f.inbox.push({id:'existing-'+i});
  const failure=await f.request('/participation',{signature:proposal.signature,action:'engage'},429);
  assert.equal(failure.code,'inbox_full');assert.equal(f.inbox.length,8);
  assert.equal((await f.request('/participation')).delivery.reason_code,'inbox_full');
  assert.equal(f.history.data.participation_pending.length,1);
  const stale=await f.request('/participation',{signature:'old',action:'engage'},409);
  assert.equal(stale.code,'source_changed');
  f.inbox.length=0;
  const fresh=await f.request('/participation');assert.equal(fresh.delivery.eligible,true);
  const applied=await f.request('/participation',{signature:fresh.signature,action:'engage'});
  assert.equal(applied.queued,true);assert.equal(f.inbox.length,1);
  assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});
test('delayed duplicate POST after a lost reply does not enqueue accepted work twice',async()=>{
 const f=fixture('BuilderOne',true);try{
  const task=JSON.stringify(f.history.task());
  f.bot.emit('chat','VisitorOne','Could you show me around?');
  const original=await f.request('/participation');
  const payload={signature:original.signature,action:'engage',offer:{id:'one',ticket:'one'}};
  await f.request('/participation',payload); // Reply discarded by the controller.
  assert.equal(await f.request('/participation'),null);
  assert.equal((await f.request('/participation',payload,409)).code,'source_changed');
  f.bot.emit('chat','VisitorOne','And what materials do you need?');
  const fresh=await f.request('/participation');
  assert.equal((await f.request('/participation',payload,409)).code,'source_changed');
  await f.request('/participation',{signature:fresh.signature,action:'engage',offer:{id:'two',ticket:'two'}});
  assert.equal(f.inbox.length,2);assert.equal(new Set(f.inbox.map(m=>m.id)).size,2);
  assert.equal(f.inbox.filter(m=>m.attention_offer.id==='one').length,1);
  assert.equal(JSON.stringify(f.history.task()),task);assert.equal(f.history.data.turn,null);
 }finally{f.close();}
});
