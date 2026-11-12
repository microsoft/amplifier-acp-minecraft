// Exercise real chat listeners and durable inboxes without a game or model call.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {Readable}=require('node:stream');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
async function huddleFixture(t,automatic=false){
 const nativeHttp=require('node:http'),crypto=require('node:crypto'),sha=v=>crypto.createHash('sha256').update(v).digest('hex');
 const event={id:'original-public-human',time:'2026-11-10T12:00:00.000Z',kind:'chat',source:'human',accepted:true,username:'Human',message:'Check together',provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',uuid:'human-uuid',username:'Human'}};
 const origin={kind:'external',service:'minecraft',connection_id:'game',conversation_id:'public-game',request_id:'original',source_id:event.id,source_revision:require('../source-revision.cjs').publicSource(event).revision,occurred_at:Date.parse(event.time),actor:{id:'human-uuid',kind:'human'}};
 const state={room:'open',posts:0,requests:0,unavailable:false,messages:[],saved:new Map()},caps={version:1,external_participants:true,read:true,post:true,post_status:true,outcomes:true,quiet_follow:true,max_text_bytes:6000,max_evidence_items:8,max_metadata_bytes:8000,max_page_items:100};let url;
 const server=nativeHttp.createServer(async(req,res)=>{state.requests++;res.setHeader('Content-Type','application/json');if(state.unavailable){res.statusCode=503;res.end('{}');return;}
  const descriptor={version:1,id:'room',conversation_id:'room',participant:{agent_id:'agent',connection_id:'game'},state:state.room,revision:state.revision||1,origin:state.origin||origin,inspect_url:url+'/?conversation=room',capabilities:caps,participants:[{id:'agent'},{id:'peer'}],purpose:'Shared check'};
  if(automatic&&req.url==='/api/v1/huddles/roster'){res.end(JSON.stringify({version:1,installation:{id:'installation',agent_id:'agent',connection_id:'game',conversation_id:'public-game',namespace:'world',service:'minecraft'},items:[{id:'peer-installation',agent_id:'peer',connection_id:'peer-game',conversation_id:'public-game',namespace:'world',enabled:true,availability:'unknown'}],capabilities:{automatic:1}}));return;}
  if(automatic&&req.url.startsWith('/api/v1/huddles/discovery')){res.end(JSON.stringify({version:1,items:state.origin?[{...descriptor,membership:'active'}]:[],cursor:state.origin?1:0,has_more:false,coverage:'current_memberships'}));return;}
  if(automatic&&req.url==='/api/v1/huddles/ensure'){let raw='';for await(const c of req)raw+=c;const p=JSON.parse(raw);state.origin=p.origin;res.end(JSON.stringify({...descriptor,origin:p.origin,request_id:p.request_id,status:'saved',reused:false,membership:'active'}));return;}
  if(req.method==='POST'){
   let raw='';for await(const c of req)raw+=c;const p=JSON.parse(raw);state.posts++;
   const receipt={version:1,status:'saved',message_id:p.request_id,request_id:p.request_id,room_id:'room',sequence:1,kind:p.kind,created_at:1,agent_id:'agent',connection_id:'game',origin:state.origin||origin,return:p.kind==='outcome'?{state:'available',delivery:'domain_owned'}:{state:'not_requested'},revision:sha(JSON.stringify(p)),text_sha256:sha(p.text),source:p.source,outcome:p.outcome,target_agent_ids:p.target_agent_ids,inspect_url:descriptor.inspect_url};state.saved.set(p.request_id,receipt);res.end(JSON.stringify(receipt));
  }else if(req.url.includes('/posts/')){res.end(JSON.stringify(state.saved.get(req.url.split('/').at(-1))));}
  else if(req.url.includes('/messages')){const after=Number(new URL(req.url,url).searchParams.get('after')||0),items=state.messages.filter(m=>m.seq>after),through=items.at(-1)?.seq||after;res.end(JSON.stringify({version:1,items,next_cursor:through,has_more:false,coverage:{after,through,complete_through_cursor:true},state:state.room,revision:state.revision||1}));}
  else res.end(JSON.stringify(descriptor));
 });await new Promise(r=>server.listen(0,'127.0.0.1',r));url=`http://127.0.0.1:${server.address().port}`;t.after(()=>{server.closeAllConnections();server.close();});
 const enrollment={url,room_id:'room',agent_id:'agent',connection_id:'game',conversation_id:'public-game',origin,token:'participant-secret-'.repeat(3)};
 const f=fixture('BuilderOne',false,automatic?{huddles:{...enrollment,installation_id:'installation',namespace:'world'},human_engagement:{enabled:true}}:{huddle:enrollment});t.after(f.close);f.history.data.events.push(event);f.history.save();return {f,state,event};
}
test('actual body keeps huddle coordination quiet and public outcome uses original speech once',async t=>{
 const {f,state}=await huddleFixture(t),sent=[];f.bot.chat=text=>sent.push(text);f.startFixtureTurn();
 const before=JSON.stringify(f.history.task()),binding=fs.existsSync(path.join(f.home,'session.json'));
 const id='01000000-0000-4000-8000-000000000001';
 await f.operate('huddle',{operation:'read'});await f.operate('huddle',{operation:'post',request_id:id,text:'Meet in the work room.',kind:'message'});assert.deepEqual(sent,[]);
 const privateFinal=await f.request('/reply',{text:'Private coordination wrap-up',conversation_revision:'original-public-human'});assert.equal(privateFinal.sent,false);assert.deepEqual(sent,[]);
 const outcome='02000000-0000-4000-8000-000000000002';
 await f.operate('huddle',{operation:'post',request_id:outcome,text:'Checked.',kind:'outcome',outcome:{kind:'result',evidence:[]}});
 await assert.rejects(f.operate('huddle',{operation:'return',request_id:outcome}),/conversation_revision/);
 await assert.rejects(f.operate('huddle',{operation:'return',request_id:outcome,conversation_revision:'stale'}),/changed/);
 assert.equal(sent.length,0);assert.ok(Object.values(f.history.data.huddle_operations).every(group=>!group[outcome].public_return));
 const revision=await f.request('/conversation');
 const result=await f.operate('huddle',{operation:'return',request_id:outcome,conversation_revision:revision.revision});assert.equal(result.transport_submitted,true);assert.equal(sent.length,1);
 await f.operate('huddle',{operation:'return',request_id:outcome,conversation_revision:revision.revision});assert.equal(sent.length,1);assert.equal(state.posts,2);
 assert.equal(JSON.stringify(f.history.task()),before);assert.equal(fs.existsSync(path.join(f.home,'session.json')),binding);assert.equal(f.history.data.input_outcomes?.length||0,0);
 assert.ok(f.history.data.turn.speech_operations[0].huddle_return);assert.equal(f.history.data.turn.speech_operations[0].reply_to,undefined);
});
test('actual body room Stop affects matching work only and preserves later human chat availability',async t=>{
 const {f,state,event}=await huddleFixture(t);f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.startFixtureTurn();state.room='stopped';
 const before=JSON.stringify(f.history.data.task);await f.request('/huddle/context');assert.equal(JSON.stringify(f.history.data.task),before);assert.ok(f.history.data.turn);
 f.history.data.task={...f.history.data.task,status:'running',authority:{source:{id:event.id}}};f.history.data.turn.task_id=f.history.data.task.id;f.history.data.turn.activity=false;
 await f.request('/huddle/context');assert.equal(f.history.data.task.status,'stopped');assert.equal(f.history.data.turn,null);assert.equal(f.history.data.activity_stop,undefined);
 f.bot.emit('chat','Human','Hello BuilderOne');assert.equal(f.inbox.at(-1).source,'human');assert.equal(f.history.data.task.status,'stopped');
});
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
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nmodule.exports={history,inbox,operate,mcpServer,activityParticipation,readyFixture(){ready=true;},busyFixture(){ready=true;busy=true;},endFixtureTurn(){turnUntil=0;history.data.turn=null;},startFixtureTurn(){ready=true;turnUntil=Date.now()+240000;history.startTurn();}};',context,{filename:'body.cjs'});
 return {bot,...context.module.exports,task,home,async request(url,payload,expectedStatus=200,token='fixture'){
  const req=Readable.from(payload===undefined?[]:[JSON.stringify(payload)]);
  Object.assign(req,{url,method:payload===undefined?'GET':'POST',headers:{authorization:'Bearer '+token}});
  let code,body;await handle(req,{writeHead:c=>{code=c;},end:text=>{body=text;}});
  assert.equal(code,expectedStatus,body);return body===undefined?null:JSON.parse(body);
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
  const allowed=new Set(JSON.parse(execFileSync(process.env.WORKSHOP_TEST_PYTHON||'python3',['-c','import json; from acp_client import GAME_TOOLS; print(json.dumps(sorted(GAME_TOOLS)))'],{cwd:root,encoding:'utf8'})));
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
test('explicit speech owns public delivery for the turn; further utterances use tools',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.bot.chat=text=>sent.push(text);f.startFixtureTurn();
  const before=JSON.stringify(f.history.task());
  await f.operate('chat',{text:'Supplies checked.',conversation_revision:'empty'});
  const duplicate=await f.request('/reply',{text:'Supplies checked.',conversation_revision:'empty'});
  assert.equal(duplicate.sent,false);assert.equal(duplicate.reason,'explicit_speech_turn');assert.deepEqual(sent,['Supplies checked.']);
  assert.equal(f.history.data.events.filter(e=>e.kind==='chat_sent').length,1);
  await f.request('/reply',{text:'There are two sticks.',conversation_revision:'empty'});
  assert.equal(sent.length,1);
  await f.operate('chat',{text:'There are two sticks.',conversation_revision:'empty'});
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
test('failed tool speech is not delivery and does not make a later final another public attempt',async()=>{
 const f=fixture('BuilderOne');try{
  const sent=[];f.startFixtureTurn();f.bot.chat=()=>{throw Error('send failed');};
  await assert.rejects(f.operate('chat',{text:'Ready.',conversation_revision:'empty'}),/send failed/);
  f.bot.chat=text=>sent.push(text);
  const final=await f.request('/reply',{text:'Ready.',conversation_revision:'empty'});
  assert.equal(final.sent,false);assert.equal(f.history.data.events.filter(e=>e.kind==='chat_sent').length,0);
  await assert.rejects(f.operate('chat',{text:'Ready.',conversation_revision:'empty'}),/unresolved or partial/);
  await f.operate('chat',{text:'Inspected the chest.',conversation_revision:'empty'});
  await f.request('/reply',{text:'Inspected the chest. There are two sticks.',conversation_revision:'empty'});
  assert.deepEqual(sent,['Inspected the chest.']);
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
test('actual private input outcome route records task-optional queue, admission, speech and terminal without exposing public context',async()=>{
 const f=fixture('BuilderOne',false,{human_engagement:{enabled:true,task_optional:true}});try{
  const {Vec3}=realRequire('vec3');f.bot.entity={position:new Vec3(0,64,0)};f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};f.bot.chat=()=>{};f.readyFixture();
  const before=JSON.stringify(f.history.data.task),q=await f.request('/task',{text:'Private instruction only'}),id=q.request_id;
  const capability=(await f.request('/status')).input_outcomes;assert.equal(capability.version,1);assert.equal(capability.path,'/input-outcomes');
  const query=()=>f.request('/input-outcomes?ids='+id);
  assert.equal((await query()).outcomes[0].delivery,'queued');
  await f.request('/turn',{message_ids:[id],activity:true});assert.equal((await query()).outcomes[0].delivery,'admitted');
  await f.operate('chat',{text:'A public observation.',conversation_revision:'empty'});
  await f.request('/finish',{});const r=(await query()).outcomes[0];
  assert.equal(r.delivery,'terminal');assert.equal(r.turn_task_id,null);assert.equal(r.responses[0].text,'A public observation.');assert.equal(r.completion,'not_established');
  assert.equal(JSON.stringify(f.history.data.task),before);assert.ok(!JSON.stringify(r).includes('Private instruction only'));
  const bytes=fs.readFileSync(path.join(f.home,'workshop.json'),'utf8');await query();assert.equal(fs.readFileSync(path.join(f.home,'workshop.json'),'utf8'),bytes);
  await f.request('/input-outcomes?ids='+id,undefined,401,'public-presence-token');
  await f.request('/input-outcomes?ids=not-an-id',undefined,400);await f.request('/input-outcomes',{ids:[id]},404);
 }finally{f.close();}
});

test('scoped installation token reaches only idempotent original input and exact private outcome boundary',async()=>{
 const caller={id:'fixture-voice',label:'Fixture voice',token:'v'.repeat(40)},f=fixture('BuilderOne',false,{installation_callers:[caller]});
 const body={text:'Original human words',source:{version:1,request_id:'87ca622b-3360-4694-a8c6-f0ebd4c522e7',call_id:'call1',intent_id:'intent1',revision:'1',occurred_at:new Date().toISOString(),actor:{id:'fixture-user',label:'Fixture user'},audience:{kind:'private',experience:'companion',id:'fixture-audience'}}};
 try{
  const baseline=JSON.stringify(f.history.task());await f.request('/source-capabilities',undefined,401,'é'.repeat(7));const caps=await f.request('/source-capabilities',undefined,200,caller.token);assert.equal(caps.version,1);assert.equal(caps.outcomes.method,'POST');
  const first=await f.request('/task',body,200,caller.token),again=await f.request('/task',body,200,caller.token);assert.equal(first.request_id,again.request_id);assert.equal(again.duplicate,true);assert.equal(f.inbox.length,1);
  const read=await f.request('/source-outcomes',{version:1,requests:[{request_id:first.request_id,source:body.source}]},200,caller.token);assert.equal(read.outcomes[0].delivery,'queued');assert.equal(read.outcomes[0].source.actor.id,'fixture-user');
  for(const route of ['/action','/stop','/inbox/drain','/mcp'])await f.request(route,{},403,caller.token);
  for(const route of ['/state','/operator-inputs','/input-outcomes?ids='+first.request_id])await f.request(route,undefined,403,caller.token);
  await f.request('/task',body,400);assert.equal(f.inbox.length,1);assert.equal(JSON.stringify(f.history.task()),baseline);
  const legacy=await f.request('/task',{text:'Legacy owner instruction'});assert.ok(legacy.request_id);assert.equal(f.inbox.length,2);
  const operator=await f.request('/operator-inputs');const e=operator.messages.find(e=>e.id===first.request_id);assert.equal(e.text,body.text);assert.equal(e.installation_source.call_id,'call1');
 }finally{f.close();}
});

test('associated valid work does not consult an unavailable room for each action; observed Stop still blocks',async t=>{
 const {f,state,event}=await huddleFixture(t);f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};
 Object.assign(f.history.data.task,{status:'running',deadline:Date.now()+600000,turns:1,authority:{source:{id:event.id}}});
 f.startFixtureTurn();f.history.data.turn.task_id=f.history.data.task.id;f.history.data.turn.activity=false;
 await f.request('/huddle/context');state.unavailable=true;const requests=state.requests;
 await f.operate('work_report',{status:'running',summary:'Existing authorized work continues.'});
 assert.equal(state.requests,requests);
 await assert.rejects(f.operate('huddle',{operation:'post',request_id:'03000000-0000-4000-8000-000000000003',text:'Unavailable room'}));
 assert.equal(state.posts,0);assert.equal(f.history.data.task.status,'running');
 state.unavailable=false;state.room='stopped';await f.request('/huddle/context');state.unavailable=true;const afterStop=state.requests;
 await assert.rejects(f.operate('work_report',{status:'running',summary:'Must not resume stopped work.'}),/stopped/);
 assert.equal(state.requests,afterStop);assert.equal(f.history.data.task.status,'stopped');assert.equal(f.history.data.turn,null);
});

for(const webHuman of [false,true])test(`actual body automatic discovered idle ${webHuman?'web human':'peer'} input can receive a private room reply`,async t=>{
 const {f,state,event}=await huddleFixture(t,true),sent=[];f.bot.chat=v=>sent.push(v);f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};
 const originalTask=JSON.stringify(f.history.data.task);f.startFixtureTurn();f.history.data.turn.request_ids=[event.id];
 const created=await f.operate('huddle',{operation:'ensure',request_id:'04000000-0000-4000-8000-000000000004',source_id:event.id,title:'Compare',purpose:'Compare current observations',peer_installation_ids:['peer-installation']});assert.equal(created.state,'saved');assert.equal(sent.length,0);
 f.endFixtureTurn();
 state.messages.push({id:'05000000-0000-4000-8000-000000000005',seq:2,role:webHuman?'user':'assistant',actor:webHuman?'browser-member-17':'Peer',agent_id:webHuman?null:'peer',text:'What do you observe?',status:'complete',created_at:Date.now(),target_agent_ids:['agent'],source:null,kind:'message',outcome:null});
 await f.request('/huddle/context');const proposal=await f.request('/huddle/participation');assert.equal(proposal.context.conversation_id,'room');assert.equal(proposal.context.participants[1].is_agent,!webHuman);assert.equal(proposal.occurred_at,state.messages[0].created_at);
 await f.request('/huddle/participation',{signature:proposal.signature,source_id:proposal.ids[0],action:'engage'});assert.equal(f.inbox[0].source,'huddle');assert.equal(f.history.data.events.some(e=>e.message==='What do you observe?'),false);
 const admission=await f.request('/conversation/admission');assert.deepEqual(admission.eligible_ids,proposal.ids);
 await f.request('/turn',{conversation_only:true,message_ids:proposal.ids});assert.equal(f.history.data.turn.huddle_room_id,'room');assert.equal(f.history.data.turn.explicit_speech,true);
 const receipt=await f.operate('huddle',{operation:'post',request_id:'06000000-0000-4000-8000-000000000006',text:'My observation is recorded here.',kind:'message'});assert.equal(receipt.state,'saved');assert.equal(receipt.receipt.status,'saved');assert.equal(state.posts,1);assert.deepEqual(sent,[]);
 const final=await f.request('/reply',{text:'Room-only wrap-up',conversation_revision:event.id});assert.equal(final.sent,false);assert.deepEqual(sent,[]);
 state.room='stopped';state.revision=2;await f.request('/huddle/context');assert.equal(f.history.data.turn,null);assert.equal(JSON.stringify(f.history.data.task),originalTask);
});
test('actual body keeps installation final/tool replies private while explicit game publication stays separate',async t=>{
 const caller={id:'voice',label:'Companion',token:'q'.repeat(40)},f=fixture('BuilderOne',false,{installation_callers:[caller],human_engagement:{enabled:true,task_optional:true}});t.after(f.close);
 const {Vec3}=realRequire('vec3');f.bot.entity={position:new Vec3(-313.1567,73,68.52)};f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};f.bot.stopDigging=()=>{};const sent=[];f.bot.chat=text=>sent.push(text);f.bot.whisper=()=>assert.fail('External caller is not a game whisper recipient');f.readyFixture();
 const source={version:1,request_id:'93000000-0000-4000-8000-000000000001',call_id:'private-call',intent_id:'original',revision:'r1',occurred_at:new Date().toISOString(),actor:{id:'human',label:'Human'},audience:{kind:'private',experience:'companion',id:'private-audience'}};
 const q=await f.request('/task',{text:'Check privately',source},200,caller.token),baseline=JSON.stringify(f.history.data.task);
 const input=(await f.request('/inbox/peek'))[0];assert.equal(input.installation_source.actor.id,'human');assert.equal(input.reply_scope,'installation:'+q.request_id);
 await f.request('/turn',{message_ids:[q.request_id],activity:true});assert.equal((await f.request('/status')).reply_route.source.audience.id,'private-audience');
 const first=await f.request('/reply',{text:'PRIVATE_FINAL_SENTINEL',conversation_revision:'unrelated-public-revision'});assert.equal(first.delivery,'recorded');assert.equal(first.transport_submitted,false);assert.deepEqual(sent,[]);
 const dup=await f.request('/reply',{text:'PRIVATE_FINAL_SENTINEL',conversation_revision:'another-public-revision'});assert.equal(dup.reply_id,first.reply_id);assert.equal(dup.at,first.at);
 const priorActions=JSON.stringify(f.history.data.turn.actions);
 await assert.rejects(f.operate('tell',{player:'Companion',text:'PRIVATE_FAILED_TELL',conversation_revision:'empty'}),/private installation caller/);assert.deepEqual(sent,[]);
 await assert.rejects(f.operate('chat',{text:'NOT_SENT',audience:'invalid'}),/Unknown speech audience/);
 assert.equal(JSON.stringify(f.history.data.turn.actions),priorActions,'audience validation does not create uncertain effects');
 const tool=await f.operate('chat',{text:'PRIVATE_TOOL_SENTINEL',conversation_revision:'irrelevant'});assert.equal(tool.delivery,'recorded');assert.deepEqual(sent,[]);
 await f.operate('chat',{text:'Explicitly requested public announcement',audience:'game',conversation_revision:'empty'});assert.deepEqual(sent,['Explicitly requested public announcement']);
 await f.request('/finish',{});
 const result=(await f.request('/source-outcomes',{version:1,requests:[{request_id:q.request_id,source}]},200,caller.token)).outcomes[0];assert.equal(result.delivery,'terminal');assert.equal(result.completion,'not_established');assert.equal(result.source_replies.length,2);assert.equal(result.source_replies[1].text,'PRIVATE_TOOL_SENTINEL');
 const owner=await f.request('/input-outcomes?ids='+q.request_id);assert.ok(!JSON.stringify(owner).includes('PRIVATE_'));assert.equal(owner.outcomes[0].responses[0].text,'Explicitly requested public announcement');
 assert.ok(!JSON.stringify(await f.request('/conversation')).includes('PRIVATE_'));assert.equal(JSON.stringify(f.history.data.task),baseline);
});
test('invalid movement and blocked storage preflight never poison future activity',async t=>{
 const {Vec3}=realRequire('vec3'),f=fixture('BuilderOne',false,{human_engagement:{enabled:true,task_optional:true}});t.after(()=>f.close());
 f.bot.entity={position:new Vec3(0,64,0)};f.bot.pathfinder={setGoal(){}};f.bot.clearControlStates=()=>{};
 f.bot.blockAt=p=>({name:'barrel',position:p});f.bot.world={raycast:()=>({name:'stone',position:new Vec3(0,65,0)})};
 f.startFixtureTurn();f.history.data.turn.activity=true;f.history.data.turn.task_id=null;f.history.data.turn.may_mutate=true;
 const before=JSON.stringify(f.history.data.turn.actions);
 await assert.rejects(f.operate('move',{x:1000,y:64,z:0,mode:'normal'}),/Coordinates must/);
 await assert.rejects(f.operate('container',{x:1,y:64,z:0,operation:'inspect',expected:'barrel'}),/obstructed/);
 await assert.rejects(f.operate('container',{x:8,y:64,z:0,operation:'inspect',expected:'barrel'}),/within four/);
 assert.equal(JSON.stringify(f.history.data.turn.actions),before);
 assert.equal(f.history.data.events.filter(e=>e.kind==='action_started').length,0);
});
