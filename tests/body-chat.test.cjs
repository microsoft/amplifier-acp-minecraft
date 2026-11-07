// Exercise real chat listeners and durable inboxes without a game or model call.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Readable}=require('node:stream');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(name,semantic=false,extra={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-chat-'));
 const config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:name,token:'fixture',agent_dialogue:true,bot_names:['BuilderOne','BuilderTwo'],conversation_attention:{enabled:semantic},...extra}));
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
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nmodule.exports={history,inbox,operate,mcpServer,activityParticipation,readyFixture(){ready=true;},busyFixture(){ready=true;busy=true;},startFixtureTurn(){ready=true;turnUntil=Date.now()+240000;history.startTurn();}};',context,{filename:'body.cjs'});
 return {bot,...context.module.exports,task,home,async request(url,payload,expectedStatus=200){
  const req=Readable.from(payload===undefined?[]:[JSON.stringify(payload)]);
  Object.assign(req,{url,method:payload===undefined?'GET':'POST',headers:{authorization:'Bearer fixture'}});
  let code,body;await handle(req,{writeHead:c=>{code=c;},end:text=>{body=text;}});
  assert.equal(code,expectedStatus,body);return JSON.parse(body);
 },close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('every advertised game tool has a matching scoped ACP permission',async()=>{
 const {Client}=realRequire('@modelcontextprotocol/sdk/client/index.js');
 const {InMemoryTransport}=realRequire('@modelcontextprotocol/sdk/inMemory.js');
 const {execFileSync}=require('node:child_process');
 const f=fixture('BuilderOne'),server=f.mcpServer(),client=new Client({name:'permission-fixture',version:'1'});
 try{
  const [clientTransport,serverTransport]=InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);await client.connect(clientTransport);
  const tools=(await client.listTools()).tools.map(t=>t.name);
  const allowed=new Set(JSON.parse(execFileSync('python3',['-c','import json; from acp_client import GAME_TOOLS; print(json.dumps(sorted(GAME_TOOLS)))'],{cwd:root,encoding:'utf8'})));
  assert.ok(tools.includes('cancel_movement'));
  assert.deepEqual(tools.filter(t=>!allowed.has(t)),[],'Advertised game tools must not be silently denied by the ACP callback');
 }finally{await client.close();await server.close();f.close();}
});
test('real watch context changes when a nearby crop ripens without a planner turn or game action',async()=>{
 const f=fixture('BuilderOne');try{
  const {Vec3}=realRequire('vec3');let age=0;
  f.bot.entity={position:new Vec3(-2,63,0)};f.bot.health=20;f.bot.inventory={items:()=>[]};
  f.bot.findBlocks=()=>[new Vec3(-2,63,1)];
  f.bot.blockAt=()=>({name:'wheat',getProperties:()=>({age})});
  f.startFixtureTurn();const before=JSON.stringify(f.history.data);
  const initial=await f.request('/watch-context');
  age=7;
  const ripe=await f.request('/watch-context');
  const first=initial.events.find(e=>e.id==='environment:crops'),second=ripe.events.find(e=>e.id==='environment:crops');
  assert.equal(first.content.blocks[0].properties.age,0);
  assert.equal(second.content.blocks[0].properties.age,7);
  assert.equal(second.kind,'environment');assert.equal(second.id,first.id);
  assert.equal(JSON.stringify(f.history.data),before);assert.equal(f.inbox.length,0);
 }finally{f.close();}
});
test('final reply route accepts eight bounded chunks without changing task authority',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=text=>sent.push(text);f.startFixtureTurn();
  const before=JSON.stringify(f.history.task());
  for(let i=0;i<8;i++)await f.request('/reply',{text:`Tour part ${i+1}`,conversation_revision:'empty'});
  assert.equal(sent.length,8);
  const denied=await f.request('/reply',{text:'Ninth chunk',conversation_revision:'empty'},400);
  assert.equal(denied.error,'Reply window is closed');assert.equal(sent.length,8);
  assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});
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
test('automatic final reuses only an exact successful speech receipt from this turn',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=text=>sent.push(text);f.startFixtureTurn();
  const before=JSON.stringify(f.history.task());
  await f.operate('chat',{text:'Supplies checked.',conversation_revision:'empty'});
  const duplicate=await f.request('/reply',{text:'Supplies checked.',conversation_revision:'empty'});
  assert.equal(duplicate.already_sent,true);assert.deepEqual(sent,['Supplies checked.']);
  assert.equal(f.history.data.events.filter(e=>e.kind==='chat_sent').length,1);
  await f.request('/reply',{text:'There are two sticks.',conversation_revision:'empty'});
  assert.equal(sent.length,2);assert.equal(JSON.stringify(f.history.task()),before);
  f.history.data.turn=null;f.startFixtureTurn();
  await f.request('/reply',{text:'Supplies checked.',conversation_revision:'empty'});
  assert.equal(sent.length,3,'a new turn may legitimately repeat a reply');
 }finally{f.close();}
});
test('fresh conversation evidence and different recipients remain separate speech',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=text=>sent.push([null,text]);f.bot.whisper=(who,text)=>sent.push([who,text]);f.startFixtureTurn();
  await f.request('/reply',{text:'Ready.',conversation_revision:'empty'});
  f.bot.emit('chat','VisitorOne','Are you ready now?');
  const fresh=await f.request('/conversation');
  await f.request('/reply',{text:'Ready.',conversation_revision:fresh.revision});
  f.history.data.turn.conversation_only=true;f.history.data.turn.reply_recipient='VisitorOne';
  await f.request('/reply',{text:'Ready.',conversation_revision:fresh.revision});
  assert.deepEqual(sent,[[null,'Ready.'],[null,'Ready.'],['VisitorOne','Ready.']]);
 }finally{f.close();}
});
test('failed or partial tool speech cannot suppress a complete final response',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.startFixtureTurn();f.bot.chat=()=>{throw Error('send failed');};
  await assert.rejects(f.operate('chat',{text:'Ready.',conversation_revision:'empty'}),/send failed/);
  f.bot.chat=text=>sent.push(text);
  await f.request('/reply',{text:'Ready.',conversation_revision:'empty'});
  await f.operate('chat',{text:'Inspected the chest.',conversation_revision:'empty'});
  await f.request('/reply',{text:'Inspected the chest. There are two sticks.',conversation_revision:'empty'});
  assert.deepEqual(sent,['Ready.','Inspected the chest.','Inspected the chest. There are two sticks.']);
 }finally{f.close();}
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
  await f.operate('chat',{text:'The dock framing is ready.',conversation_revision:'empty'});
  await f.operate('tell',{player:'BuilderTwo',intent:'update',text:'Public supplies delivered.',conversation_revision:'empty'});
  await f.request('/reply',{text:'Public reply from the controller.'});
  const canary='PRIVATE_FAILED_SEND_CANARY';
  f.bot.chat=()=>{throw Error(canary);};
  await assert.rejects(f.operate('tell',{player:'BuilderTwo',intent:'request',text:canary,conversation_revision:'empty'}),new RegExp(canary));
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

test('active conversation projection excludes whispers, private controls and nested local receipts',async()=>{
 const f=fixture('BuilderOne',true);try{
  await f.request('/task',{text:'PRIVATE_CONTROL'});
  f.bot.emit('whisper','VisitorOne','PRIVATE_WHISPER');
  f.history.record({kind:'work_status',progress:{observation:{recent_actions:[{arguments:{text:'PRIVATE_ACTION'}}]}}});
  f.bot.emit('chat','BuilderTwo','Two sticks are in the chest.');
  const queued=f.history.data.participation_pending.slice();f.startFixtureTurn();
  const current=await f.request('/conversation');assert.equal(current.turn_active,true);
  assert.equal(current.messages.length,1);assert.equal(current.messages[0].text,'Two sticks are in the chest.');
  assert.ok(!JSON.stringify(current).includes('PRIVATE_'));
  assert.deepEqual(f.history.data.participation_pending,queued,'reading awareness never consumes an attention opportunity');
  assert.deepEqual(f.history.task(),f.task,'reading evidence never renews authority');
 }finally{f.close();}
});
test('fresh public chat rejects an old transfer before any action reservation',async()=>{
 const f=fixture('BuilderOne');try{
  f.startFixtureTurn();f.bot.emit('chat','BuilderTwo','Please bring sticks.');
  const old=await f.request('/conversation');
  f.bot.emit('chat','BuilderTwo','The sticks arrived; do not send another stack.');
  await assert.rejects(f.operate('give',{player:'BuilderTwo',item:'stick',count:2,conversation_revision:old.revision}),/conversation changed/);
  await assert.rejects(f.operate('container',{operation:'deposit',item:'stick',count:2,contents_revision:'old',conversation_revision:old.revision}),/conversation changed/);
  assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,0);
  assert.equal(f.history.task().turns,12);
 }finally{f.close();}
});
test('late public message fences an automatic final without sending or starting a prompt',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=t=>sent.push(t);f.startFixtureTurn();
  const old=await f.request('/conversation');f.bot.emit('chat','VisitorOne','Wait, that delivery is already done.');
  const result=await f.request('/reply',{text:'I still need that delivery.',conversation_revision:old.revision});
  assert.equal(result.sent,false);assert.equal(result.reason,'conversation_changed');assert.equal(sent.length,0);
  const fresh=await f.request('/conversation');await f.request('/reply',{text:'I see the newer message.',conversation_revision:fresh.revision});
  assert.equal(sent.length,1);assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});
test('stick deposit prevents a cancellation composed against older conversation evidence',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=t=>sent.push(t);f.startFixtureTurn();
  f.bot.emit('chat','BuilderTwo','I will bring the sticks.');
  const old=await f.request('/conversation');
  f.bot.emit('chat','BuilderTwo','The sticks are now in the chest.');
  await assert.rejects(f.operate('tell',{player:'BuilderTwo',intent:'request',text:'Cancel those sticks.',conversation_revision:old.revision}),/conversation changed/);
  await assert.rejects(f.operate('chat',{text:'Still waiting for sticks.'}),/conversation changed/);
  assert.equal(sent.length,0);assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,0);
  const fresh=await f.request('/conversation');
  await f.operate('tell',{player:'BuilderTwo',intent:'update',text:'Checking the chest before using the delivery.',conversation_revision:fresh.revision});
  assert.equal(sent.length,1);assert.ok(sent[0].includes('Checking the chest'));
 }finally{f.close();}
});

test('operator stopped-task recovery uses the real idle generation gate and explicit authorization',async()=>{
 const f=fixture('BuilderOne');try{
  f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};
  Object.assign(f.history.data.task,{status:'running',deadline:Date.now()+3600000,turns:7,max_turns:45});
  f.startFixtureTurn();await f.operate('stop');
  const before=JSON.parse(JSON.stringify(f.history.task())),generation=(await f.request('/conversation')).generation;
  const args={task_id:before.id,reason:'Operator inspected an accidental route stop; original human allowance remains valid.',generation,resume_stopped:true};
  await f.request('/resume-reviewed',{...args,resume_stopped:false},400);
  await f.request('/resume-reviewed',{...args,generation:generation-1},400);
  const recovered=await f.request('/resume-reviewed',args);
  assert.equal(recovered.status,'running');
  for(const field of ['id','deadline','turns','max_turns'])assert.equal(recovered[field],before[field]);
  assert.equal(f.history.data.turn,null);assert.equal((await f.request('/conversation')).turn_active,false);
  await assert.rejects(f.operate('resume-reviewed',args),/No active action lease/);
 }finally{f.close();}
});
test('reply reserve filters triggers but retains peer context and respects the host hold',async()=>{
 const f=fixture('BuilderOne',true);try{
  f.bot.emit('chat','BuilderTwo','The roof needs a check.');
  f.bot.emit('chat','VisitorOne','What are you all working on?');
  const proposal=await f.request('/participation?human_only=1');
  assert.equal(proposal.ids.length,1);
  assert.equal(proposal.context.messages.find(m=>m.id===proposal.context.trigger_id).sender,'VisitorOne');
  assert.ok(proposal.context.messages.some(m=>m.sender==='BuilderTwo'));
  const task=JSON.stringify(f.history.data.task);
  const result=await f.request('/participation',{signature:proposal.signature,action:'hold',human_only:true});
  assert.equal(result.queued,false);assert.equal(f.inbox.length,0);
  assert.deepEqual((await f.request('/conversation/admission')).eligible_ids,[]);
  assert.equal(await f.request('/participation?human_only=1'),null);
  assert.equal(JSON.stringify(f.history.data.task),task);
  assert.ok(f.history.data.events.some(e=>e.username==='BuilderTwo'&&e.accepted!==true));
 }finally{f.close();}
});
test('actual body separates human task acceptance from reply effects and preserves expired history',async()=>{
 const f=fixture('BuilderOne',false,{incoming_chat_only:true,human_task_intake:{enabled:true,max_turns:45,max_seconds:10800}});
 try{
  const {Vec3}=realRequire('vec3');f.bot.entity={position:new Vec3(0,64,0)};f.bot.inventory={items:()=>[]};f.bot.findBlocks=()=>[];f.bot.blockAt=()=>null;f.bot.time={timeOfDay:0};f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};f.readyFixture();
  const raw={},uuid='00000000-0000-0000-0000-000000000123';f.bot.players.Visitor={uuid};
  f.bot.emit('message',raw,'chat',uuid,false);f.bot.emit('chat','Visitor','BuilderOne, please build a shop.',null,raw);
  const source=f.history.data.events.find(e=>e.kind==='chat'&&e.username==='Visitor');assert.equal(source.transport.uuid,uuid);
  const cap=(await f.request('/status')).task_capabilities;assert.equal(cap.autonomous_work_allowed,false);assert.equal(cap.can_accept,true);
  await f.request('/turn',{conversation_only:true,message_ids:[source.id]});
  const first=await f.request('/action',{name:'task_accept',arguments:{request_id:source.id,goal:'shop'}});
  assert.equal(first.accepted,true);assert.equal(first.turns,0);assert.deepEqual(f.history.data.task_history[0],f.task);
  assert.equal((await f.request('/status')).action_lease.lease_id,null);
  const rejected=await f.request('/action',{name:'move',arguments:{x:1,y:64,z:1}},400);assert.match(rejected.error,/World effects/);
  await f.request('/finish',{});assert.equal(f.history.task().turns,0);
  await f.request('/turn',{continuation:true,renewable_lease:true,message_ids:[]});assert.equal(f.history.task().turns,1);assert.ok((await f.request('/status')).action_lease.lease_id);
  await f.request('/action',{name:'stop',arguments:{}});assert.equal(f.history.task().status,'stopped');assert.equal((await f.request('/status')).action_lease.lease_id,null);
  await f.request('/finish',{});
 }finally{f.close();}
});
test('actual body does not trust a parsed human-looking name or a configured agent as human authority',async()=>{
 const f=fixture('BuilderOne',false,{incoming_chat_only:true,human_task_intake:{enabled:true}});
 try{
  f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};f.readyFixture();
  f.bot.emit('chat','Visitor','BuilderOne, please build a shop.');const source=f.history.data.events.find(e=>e.kind==='chat');
  await f.request('/turn',{conversation_only:true,message_ids:[source.id]});
  const rejected=await f.request('/action',{name:'task_accept',arguments:{request_id:source.id,goal:'shop'}},400);assert.match(rejected.error,/attributed by the game transport/);assert.deepEqual(f.history.task(),f.task);
  // Finish before fixture cleanup, without requiring world observation stubs.
  await f.operate('task_capabilities',{});f.history.finish();
 }finally{f.close();}
});

test('actual body applies a human exhausted reduction and rejects the next work lease',async()=>{
 const f=fixture('BuilderOne',false,{incoming_chat_only:true,human_task_intake:{enabled:true}});
 try{
  const {Vec3}=realRequire('vec3');f.bot.entity={position:new Vec3(0,64,0)};f.bot.inventory={items:()=>[]};f.bot.findBlocks=()=>[];f.bot.blockAt=()=>null;f.bot.time={timeOfDay:0};f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};f.readyFixture();
  const uuid='00000000-0000-0000-0000-000000000123';f.bot.players.Visitor={uuid};
  const say=text=>{const raw={};f.bot.emit('message',raw,'chat',uuid,false);f.bot.emit('chat','Visitor',text,null,raw);return f.history.data.events.filter(e=>e.kind==='chat').at(-1);};
  const source=say('BuilderOne, please build a shop.');await f.request('/turn',{conversation_only:true,message_ids:[source.id]});
  const accepted=await f.request('/action',{name:'task_accept',arguments:{request_id:source.id,goal:'shop'}});await f.request('/finish',{});
  await f.request('/turn',{continuation:true,renewable_lease:true,message_ids:[]});await f.request('/action',{name:'work_report',arguments:{status:'running',summary:'Inspected initial work area.'}});await f.request('/finish',{});
  const amendment=say('BuilderOne, reduce the cumulative allowance to zero.');await f.request('/turn',{conversation_only:true,message_ids:[amendment.id]});
  const result=await f.request('/action',{name:'task_amend',arguments:{request_id:amendment.id,task_id:accepted.task_id,expected_revision:1,max_turns:0}});
  assert.equal(result.status,'budget_exhausted');assert.equal(result.turns,1);assert.equal(result.max_turns,0);assert.equal(result.task_id,accepted.task_id);assert.equal((await f.request('/status')).action_lease.lease_id,null);
  await f.request('/finish',{});await f.request('/turn',{continuation:true,renewable_lease:true,message_ids:[]},400);assert.equal((await f.request('/status')).action_lease.lease_id,null);assert.equal(f.history.task().turns,1);
 }finally{f.close();}
});

test('verified addressed human bypasses optional attention budget; other-agent speech remains context',async()=>{
 const f=fixture('BuilderOne',true,{human_engagement:{enabled:true}});try{
  const uuid='00000000-0000-0000-0000-000000000123';f.bot.players.Visitor={uuid};
  const say=text=>{const raw={};f.bot.emit('message',raw,'chat',uuid,false);f.bot.emit('chat','Visitor',text,null,raw);};
  say('BuilderOne, can you answer me?');assert.equal(f.inbox.length,1);assert.equal(f.inbox[0].source,'human');
  assert.equal(f.history.data.events.filter(e=>e.kind==='chat').at(-1).accepted,true);
  assert.equal(f.history.data.participation_pending?.length||0,0);
  say('BuilderTwo, please look here.');assert.equal(f.inbox.length,1);assert.equal(f.history.data.participation_pending.length,1);
  assert.equal(f.history.data.task.status,'budget_exhausted');
 }finally{f.close();}
});
test('human priority retains a burst beyond one turn batch without dropping or promoting peers',async()=>{
 const f=fixture('BuilderOne',true,{human_engagement:{enabled:true}});try{
  const uuid='00000000-0000-0000-0000-000000000123';f.bot.players.Visitor={uuid};
  for(let i=0;i<12;i++){const raw={};f.bot.emit('message',raw,'chat',uuid,false);f.bot.emit('chat','Visitor','BuilderOne, message '+i,null,raw);}
  assert.equal(f.inbox.length,12);assert.equal((await f.request('/inbox/peek')).length,8);
  assert.equal(new Set(f.inbox.map(m=>m.id)).size,12);
 }finally{f.close();}
});
test('real participation delivery targets one source despite later human arrivals and lost replies',async()=>{
 const f=fixture('BuilderOne',true);try{
  f.bot.emit('chat','VisitorOne','First question');const first=await f.request('/participation');
  f.bot.emit('chat','VisitorOne','Second question');
  assert.equal((await f.request('/participation')).signature,first.signature);
  const payload={source_id:first.context.trigger_id,signature:first.signature,action:'hold'};
  await f.request('/participation',payload);
  assert.equal(f.history.data.participation_pending.length,1);const second=await f.request('/participation');
  assert.notEqual(second.context.trigger_id,first.context.trigger_id);
  await f.request('/participation',payload,409);
  assert.equal(f.history.data.participation_pending.length,1);
  await f.request('/participation',{source_id:second.context.trigger_id,signature:second.signature,action:'engage'});
  assert.equal(f.inbox.length,1);assert.equal(f.inbox[0].message,'Second question');assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});

test('actual activity reply turn cannot accept/amend tasks or perform world effects',async()=>{
 const f=fixture('BuilderOne',true,{human_engagement:{enabled:true,activity_scope:'conversation_only'},human_task_intake:{enabled:true}});try{
  f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};f.readyFixture();f.activityParticipation.observe({uuid:'12345678-1234-1234-1234-123456789abc',name:'Visitor',from:{x:0,y:64,z:0},to:{x:1,y:64,z:0},at:Date.now()});
  const proposal=await f.request('/activity/participation');assert.equal(proposal.context.messages.length,0);
  await f.request('/activity/participation',{source_id:proposal.context.trigger_id,signature:proposal.signature,action:'engage',offer:{id:'decision',ticket:'ticket'}});
  const before=JSON.stringify(f.history.task());
  await f.request('/turn',{conversation_only:true,message_ids:[proposal.context.trigger_id]});
  assert.equal(f.history.data.turn.ambient_activity,true);
  for(const name of ['task_accept','task_amend','move','work_begin','attention_watch'])await assert.rejects(f.operate(name,{}),/Task intake|Conversation-only/);
  assert.equal(JSON.stringify(f.history.task()),before);
  await f.request('/stop',{});assert.equal(await f.request('/activity/participation'),null);
 }finally{f.close();}
});

test('authenticated operator updates have their own bounded view, never public chat or authority',async()=>{
 const f=fixture('BuilderOne');try{
  const before=JSON.stringify(f.history.task());
  const r=await f.request('/task',{text:'Do not place the lamp. Keep it in inventory.'});
  const control=await f.request('/operator-inputs'),room=await f.request('/conversation');
  assert.equal(control.revision,r.request_id);assert.equal(control.messages[0].author,'Operator');
  assert.match(control.messages[0].text,/Do not place/);assert.match(control.scope,/not public/);
  assert.equal(room.messages.length,0);assert.equal(room.revision,'empty');
  assert.equal(f.inbox.length,1,'delivery facts never consume a request or grant authority');
  assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});

test('actual body can plan ahead during an operation without changing live movement or authority',async()=>{
 const f=fixture('BuilderOne');try{
  const {Vec3}=realRequire('vec3');f.bot.entity={position:new Vec3(.5,64,.5)};
  f.bot.blockAt=p=>({name:p.y===63?'stone':'air',boundingBox:p.y===63?'block':'empty',shapes:p.y===63?[[0,0,0,1,1,1]]:[]});
  f.bot.pathfinder={getPathTo(){assert.fail('Do not alter live pathfinder');}};
  f.busyFixture();const before=JSON.stringify(f.history.data);
  const result=await f.operate('plan_route',{x:5,y:64,z:0,mode:'walk_only',range:0,start:{x:3,y:64,z:0}});
  assert.equal(result.reachable,true);assert.equal(result.hypothetical_start,true);assert.equal(result.steps[0].x,3);
  assert.equal(f.bot.entity.position.x,.5);assert.equal(JSON.stringify(f.history.data),before);
  await assert.rejects(f.operate('plan_route',{x:5,y:64,z:0,mode:'normal',range:0}),/live pathfinder/);
  await assert.rejects(f.operate('plan_route',{x:5,y:64,z:0,mode:'normal',start:{x:3,y:64,z:0}}),/requires walk_only/);
 }finally{f.close();}
});
test('actual server animation listener captures stationary human interaction without a task or fake chat',()=>{
 const f=fixture('BuilderOne',true,{human_engagement:{enabled:true,activity_scope:'conversation_only'}});try{
  const {Vec3}=realRequire('vec3');const entity={position:new Vec3(0,64,0)};
  f.bot.players.Human={username:'Human',uuid:'12345678-1234-1234-1234-123456789abc',entity};
  const before=JSON.stringify(f.history.data.task);f.bot.emit('entitySwingArm',entity);
  const p=f.activityParticipation.proposal();assert.equal(p.context.activities[0].kind,'interaction');
  assert.equal(p.context.messages.length,0);assert.equal(f.inbox.length,0);assert.equal(JSON.stringify(f.history.data.task),before);
 }finally{f.close();}
});
test('public peer evidence survives a full inbox and old human activity for human-led play',async()=>{
 const f=fixture('BuilderOne',true,{human_engagement:{enabled:true}});try{
  for(let i=0;i<8;i++)f.inbox.push({id:'queued-'+i,source:'human'});
  f.bot.emit('chat','BuilderTwo','@BuilderOne [FYI] Your materials are ready.');
  const e=f.history.data.events.find(e=>e.kind==='chat');
  assert.equal(e.accepted,false);assert.ok(f.history.data.participation_pending.includes(e.id));
  const waiting=await f.request('/participation');assert.equal(waiting.delivery.reason_code,'inbox_full');
  f.inbox.length=0;const ready=await f.request('/participation');
  assert.equal(ready.signature,waiting.signature);assert.equal(ready.delivery.eligible,true);
  await f.request('/participation',{signature:ready.signature,source_id:e.id,action:'engage',offer:{id:'host',ticket:'original'}});
  assert.equal(f.inbox[0].id,e.id);assert.deepEqual(f.history.task(),f.task);
 }finally{f.close();}
});
test('installation observation reports fresh human engagement without a turn or authority change',async()=>{
 const f=fixture('BuilderOne');try{
  const before=JSON.stringify(f.history.task());
  assert.equal((await f.request('/installation-state')).human_engagement.active,false);
  f.history.record({kind:'chat',source:'human',username:'Visitor',message:'Hello',time:new Date().toISOString(),provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',username:'Visitor',uuid:'00000000-0000-0000-0000-000000000001'}});
  assert.equal((await f.request('/installation-state')).human_engagement.active,true);
  assert.equal(f.history.data.turn,null);assert.equal(JSON.stringify(f.history.task()),before);
 }finally{f.close();}
});
