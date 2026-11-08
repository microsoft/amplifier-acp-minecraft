const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module'),{Readable}=require('node:stream');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(configOverride={},walkingOverride=null,bridgeOverride=null){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-lease-')),config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:'Builder',token:'fixture',...configOverride}));
 const now=Date.now(),task={id:'accepted',status:'running',deadline:now+3600000,turns:120,max_turns:135,progress:[]};
 fs.writeFileSync(path.join(home,'workshop.json'),JSON.stringify({task,events:[],turn:null,inbox:[]}));
 const bot=new EventEmitter();Object.assign(bot,{username:'Builder',players:{},loadPlugin(){},pathfinder:{setGoal(){}},clearControlStates(){},stopDigging(){},entity:{position:{clone:()=>({x:0,y:64,z:0})}},health:20});
 let handle,current=now;const timers=new Set();
 class Clock extends Date{static now(){return current;}}
 const ctx=vm.createContext({require:n=>n==='./watch-bridge.cjs'&&bridgeOverride?bridgeOverride:n==='./walking.cjs'&&walkingOverride?walkingOverride:n==='mineflayer'?{createBot:()=>bot}:n==='node:http'?{createServer:h=>{handle=h;return {listen(){},close(){}};}}:realRequire(n),
 module:{exports:{}},console:{log(){}},Date:Clock,Buffer,process:{argv:['node','body.cjs',config],on(){},exit(){}},
 setTimeout:(fn,ms)=>{const t={fn,at:current+ms,unref(){}};timers.add(t);return t;},clearTimeout:t=>timers.delete(t)});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nready=true;module.exports={history,operate,actionsRemaining};',ctx);
 return {...ctx.module.exports,home,task,bot,async request(url,payload,code=200,token='fixture'){
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

test('actual reply-only body denies world/task/watch effects and renewal while retaining chat',async()=>{
 const f=fixture();try{
  const h=f.history,before=JSON.stringify(h.data.task);
  const e=h.record({kind:'chat',source:'human',username:'Visitor',message:'How is it going?',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString()});
  h.data.inbox.push({id:e.id,source:'human',message:e.message});h.save();
  const start=await f.request('/turn',{conversation_only:true,message_ids:[e.id]});
  assert.equal(start.action_lease.lease_id,null);assert.equal(start.action_lease.renewable,false);
  assert.equal((await f.request('/status')).conversation_only,true);
  for(const name of ['place','move','gather','container','give','stop','cancel_movement','work_begin','work_report','work_reopen','work_note','attention_watch','attention_cancel','screenshot']){
   await assert.rejects(()=>f.operate(name,{}),/Conversation-only/);
  }
  await f.operate('conversation');
  await f.request('/turn/renew',{lease_id:null,task_id:'accepted'},400);
  await f.request('/finish',{});
  assert.equal(JSON.stringify(h.data.task),before);
  await f.request('/turn',{conversation_only:true,message_ids:[e.id]},400);
 }finally{f.close();}
});

test('reply-only whisper never broadcasts and cannot mix audiences',async()=>{
 const f=fixture();try{
  const sent=[];f.bot.chat=t=>sent.push(['public',t]);f.bot.whisper=(u,t)=>sent.push([u,t]);
  const h=f.history;
  function add(username,whisper){const e=h.record({kind:'chat',source:'human',username,message:'Private question',accepted:true,whisper,provenance:whisper?'minecraft_whisper':'minecraft_public_chat',time:new Date().toISOString()});h.data.inbox.push({id:e.id,source:'human',username,whisper,message:e.message});h.save();return e.id;}
  const one=add('Visitor',true),two=add('Other',false);
  await f.request('/turn',{conversation_only:true,message_ids:[one,two]},400);
  await f.request('/turn',{conversation_only:true,message_ids:[one]});
  await f.request('/reply',{text:'Private reply'});
  assert.deepEqual(sent,[['Visitor','Private reply']]);
  const event=h.data.events.find(e=>e.kind==='chat_sent');assert.equal(event.whisper,true);assert.equal(event.provenance,'minecraft_whisper');
  f.advance(240001);await f.request('/reply',{text:'Late'},400);
 }finally{f.close();}
});

test('incoming-chat-only configuration cannot continue a valid stored task or open ordinary action authority',async()=>{
 const f=fixture({incoming_chat_only:true,automatic_recovery:true});try{
  const before=JSON.stringify(f.history.data.task);
  assert.equal((await f.request('/status')).incoming_chat_only,true);
  assert.equal((await f.request('/continuation',{generation:0})).reason,'incoming_chat_only');
  await f.request('/turn',{renewable_lease:true,continuation:true},400);
  await f.request('/wake',{generation:0,task_id:'accepted'},400);
  await f.request('/watch',{operation:'arm'},400);
  await assert.rejects(()=>f.operate('work_begin',{}),/Conversation-only/);
  const e=f.history.record({kind:'chat',source:'human',username:'Visitor',message:'Hello',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString()});
  f.history.data.inbox.push({id:e.id,source:'human',username:'Visitor',message:'Hello'});f.history.save();
  await f.request('/turn',{message_ids:[e.id]},400);
  await f.request('/turn',{conversation_only:true,message_ids:[e.id]});
  assert.equal((await f.request('/status')).action_lease.lease_id,null);
  await f.request('/finish',{});
  assert.equal(JSON.stringify(f.history.data.task),before);
 }finally{f.close();}
});

test('actual body sequence validates steps, executes ordinary guarded actions, and pauses for fresh human input',async()=>{
 for(const steer of [false,true]){
 const f=fixture();try{
  const {Vec3}=realRequire('vec3');f.bot.entity.position=new Vec3(0,64,0);let effects=0;const opened=new Set();
  f.bot.blockAt=p=>({name:'oak_door',position:p,getProperties:()=>({open:opened.has(p.x)})});
  f.bot.activateBlock=async block=>{effects++;opened.add(block.position.x);if(steer)f.history.record({kind:'chat',source:'human',username:'Visitor',message:'Wait, check the other side',transport:{kind:'server_player_uuid',username:'Visitor',uuid:'human'},time:new Date().toISOString()});};
  await f.request('/turn',{renewable_lease:true,continuation:true});
  const args={plan_id:'door-plan',steps:[{tool:'set_open',arguments:{x:1,y:64,z:0,open:true}},{tool:'set_open',arguments:{x:2,y:64,z:0,open:true}}]};
  const pending=f.request('/action',{name:'action_sequence',arguments:args});
  for(let i=0;i<8;i++){await new Promise(setImmediate);f.advance(350);}
  const r=await pending;
  assert.equal(r.status,steer?'paused':'completed');assert.equal(effects,steer?1:2);
  const duplicate=await f.request('/action',{name:'action_sequence',arguments:args});assert.equal(duplicate.duplicate,true);assert.equal(effects,steer?1:2);
  const invalid=await f.request('/action',{name:'action_sequence',arguments:{plan_id:'bad',steps:[args.steps[0],{tool:'task_amend',arguments:{}}]}},400);
  assert.ok(invalid.error);assert.equal(effects,steer?1:2);
 }finally{f.close();}
 }
});
test('actual async plan returns accepted before physical completion; Stop prevents the second effect',async()=>{
 const f=fixture();try{
  const {Vec3}=realRequire('vec3');f.bot.entity.position=new Vec3(0,64,0);let release,effects=0;const opened=new Set();
  f.bot.blockAt=p=>({name:'oak_door',position:p,getProperties:()=>({open:opened.has(p.x)})});
  f.bot.activateBlock=async block=>{effects++;await new Promise(r=>release=r);opened.add(block.position.x);};
  await f.request('/turn',{renewable_lease:true,continuation:true});
  const args={plan_id:'async-door-plan',steps:[{tool:'set_open',arguments:{x:1,y:64,z:0,open:true}},{tool:'set_open',arguments:{x:2,y:64,z:0,open:true}}]};
  const started=await f.request('/action',{name:'start_sequence',arguments:args});assert.equal(started.accepted,true);assert.equal(started.completed,false);assert.equal(effects,1);
  const running=await f.request('/action',{name:'sequence_status',arguments:{plan_id:args.plan_id}});assert.equal(running.status,'running');assert.equal(running.results.length,0);
  const status=await f.request('/status');assert.equal(status.action_sequence.id,args.plan_id);
  const spoken=[];f.bot.chat=text=>spoken.push(text);f.bot.players.Peer={};
  const conversation=await f.request('/action',{name:'conversation'});
  await f.request('/action',{name:'chat',arguments:{text:'I am on my way.',conversation_revision:conversation.revision}});
  await f.request('/action',{name:'tell',arguments:{player:'Peer',intent:'update',text:'The first step is still running.',conversation_revision:conversation.revision}});
  assert.equal(spoken.length,2);assert.equal((await f.request('/status')).busy,true);assert.equal(effects,1);
  assert.equal(f.history.data.turn.actions.filter(a=>a.status==='pending').length,1);

  await f.request('/stop',{});release();for(let i=0;i<8;i++){await new Promise(setImmediate);f.advance(350);}
  const final=await f.request('/action',{name:'sequence_status',arguments:{plan_id:args.plan_id}});assert.equal(final.status,'paused');assert.equal(effects,1);assert.equal((await f.request('/status')).action_lease.lease_id,null);
 }finally{f.close();}
});

test('actual body helper acceptance is metadata-only, source-bound and opens work only in a later turn',async()=>{
 const f=fixture({incoming_chat_only:true,bot_names:['Lead'],human_engagement:{enabled:true},human_task_intake:{enabled:true,delegation:{enabled:true}}});try{
  f.history.data.task.status='review';
  const base={kind:'chat',time:new Date().toISOString(),whisper:false,provenance:'minecraft_public_chat'};
  const root=f.history.record({...base,source:'human',username:'Human',message:'Lead may recruit helpers, each with an independent normal allowance.',accepted:false,transport:{kind:'server_player_uuid',username:'Human',uuid:'00000000-0000-0000-0000-000000000001'}});
  const peer=f.history.record({...base,source:'agent',username:'Lead',message:'@Builder Please bring timber.',intent:'request',accepted:true,transport:{kind:'server_player_uuid',username:'Lead',uuid:'00000000-0000-0000-0000-000000000002'}});
  f.history.data.inbox.push({id:peer.id,source:'agent',username:'Lead',message:peer.message});f.history.save();
  await f.request('/turn',{conversation_only:true,message_ids:[peer.id]});
  const args={request_id:root.id,peer_request_id:peer.id,authorization_quote:'recruit helpers, each with an independent normal allowance',budget_scope:'independent_per_agent',goal:'Bring timber for the human project'};
  const result=await f.request('/action',{name:'task_accept_help',arguments:args});assert.equal(result.execution_started,false);assert.equal(result.turns,0);
  await f.request('/action',{name:'dig',arguments:{x:1,y:64,z:0}},400);
  assert.equal((await f.request('/status')).peer_proposal,true);
  await f.request('/finish',{});await f.request('/turn',{continuation:true,renewable_lease:true});
  assert.equal(f.history.data.turn.task_id,result.task_id);assert.equal(f.history.data.turn.may_mutate,true);assert.equal(f.history.task().turns,1);
  await f.request('/stop',{});
 }finally{f.close();}
});

test('human-led mode removes local action pacing, while legacy cap and Stop remain enforced',async()=>{
 for(const enabled of [false,true]){
  const f=fixture({human_engagement:{enabled}});try{
   f.bot.chat=()=>{};await f.request('/turn',{renewable_lease:true,continuation:true});
   const before=JSON.stringify(f.history.task());
   for(let i=0;i<25;i++){
    const conversation=await f.request('/action',{name:'conversation'});
    await f.request('/action',{name:'chat',arguments:{text:'Disposable receipt '+i,conversation_revision:conversation.revision}},!enabled&&i===24?400:200);
   }
   assert.equal(f.actionsRemaining(),enabled?null:0);
   assert.equal((await f.request('/status')).task_capabilities.capacity.actions_per_turn,enabled?null:24);
   assert.equal(JSON.stringify(f.history.task()),before);
   await f.request('/stop',{});await f.request('/action',{name:'chat',arguments:{text:'After Stop'}},400);
  }finally{f.close();}
 }
});

test('actual body accepts completion-bound work only after local helper discovery; lease and human reduction stay separate',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'body-helper-capabilities-')),command=path.join(dir,'runtime');
 const capabilities={schema_version:1,helpers:{watch:{version:2,command:'watch-v2',bound_kinds:['finite','no_configured_bound'],watch_ttl_seconds:{minimum:30,maximum:1800}},continuation:{version:2,command:'continuation-v2',bound_kinds:['finite','no_configured_bound']}}};
 fs.writeFileSync(command,`#!/usr/bin/env node\nif(process.argv.slice(2).join(' ')!=='helper-capabilities')process.exit(1);process.stdout.write(${JSON.stringify(JSON.stringify(capabilities))});`,{mode:0o700});
 const f=fixture({incoming_chat_only:true,task_helpers:{command},human_engagement:{enabled:true},human_task_intake:{enabled:true,default_bound_mode:'completion_bound'}});
 try{
  await realRequire('./helper-capabilities.cjs').discover(command);f.history.data.task.status='budget_exhausted';const old=structuredClone(f.history.data.task);
  function human(message){const e=f.history.record({kind:'chat',time:new Date().toISOString(),source:'human',username:'Visitor',message,accepted:true,provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',username:'Visitor',uuid:'human-uuid'}});f.history.data.inbox.push({id:e.id,source:'human',username:'Visitor',message});f.history.save();return e;}
  const e=human('Finish this commission.');await f.request('/turn',{conversation_only:true,message_ids:[e.id]});
  const accepted=await f.request('/action',{name:'task_accept',arguments:{request_id:e.id,goal:'Finish the whole commission'}});
  assert.equal(accepted.execution_started,false);assert.equal(accepted.bounds.deadline_ms.kind,'no_configured_bound');assert.deepEqual(f.history.data.task_history.at(-1),old);
  await f.request('/action',{name:'dig',arguments:{x:1,y:64,z:0}},400);
  await f.request('/finish',{});
  const saved=JSON.stringify(f.history.data),replacement=command+'.new';
  fs.copyFileSync(command,replacement);fs.renameSync(replacement,command);
  assert.equal((await f.request('/status')).task_capabilities.autonomous_work_allowed,false);
  const until=Date.now()+3000;
  while(!(await f.request('/status')).task_capabilities.autonomous_work_allowed&&Date.now()<until)await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal((await f.request('/status')).task_capabilities.autonomous_work_allowed,true);
  assert.equal(JSON.stringify(f.history.data),saved,'helper replacement cannot change assignment or consume input');
  const start=await f.request('/turn',{continuation:true,renewable_lease:true}),taskId=accepted.task_id;
  const before=JSON.stringify(f.history.task());
  for(let i=0;i<90;i++){f.advance(30000);await f.request('/turn/renew',{lease_id:start.action_lease.lease_id,task_id:taskId});}
  assert.equal(JSON.stringify(f.history.task()),before);assert.equal(f.history.task().turns,1);
  await f.operate('work_report',{status:'running',summary:'Progress checkpoint; work remains.'});await f.request('/finish',{});
  const reduce=human('Stop after zero work turns.');await f.request('/turn',{conversation_only:true,message_ids:[reduce.id]});
  await f.request('/action',{name:'task_amend',arguments:{request_id:reduce.id,task_id:taskId,expected_revision:1,max_turns:0}});
  assert.equal(f.history.task().turns,1);assert.equal(f.history.task().status,'budget_exhausted');await f.request('/finish',{});
  await f.request('/turn',{continuation:true,renewable_lease:true},400);
  assert.equal((await f.request('/status')).action_lease.lease_id,null);
 }finally{f.close();fs.rmSync(dir,{recursive:true,force:true});}
});

test('installation gate rejects fresh turns atomically without consuming inputs or renewing authority',async()=>{
 const f=fixture();try{
  const before=JSON.stringify(f.history.data),folder=path.join(f.home,'installation-updates');fs.mkdirSync(folder);
  fs.writeFileSync(path.join(folder,'gate.json'),JSON.stringify({version:1,transaction_id:'fixture-update',closed:true}));
  await f.request('/turn',{renewable_lease:true,continuation:true},400);
  assert.equal(JSON.stringify(f.history.data),before);
  fs.unlinkSync(path.join(folder,'gate.json'));
  await f.request('/turn',{renewable_lease:true,continuation:true});
  assert.equal(f.history.task().turns,121);
 }finally{f.close();}
});
test('installation gate lets an admitted turn settle and does not revoke its existing lease',async()=>{
 const f=fixture();try{
  const start=await f.request('/turn',{renewable_lease:true,continuation:true});
  const folder=path.join(f.home,'installation-updates');fs.mkdirSync(folder);
  fs.writeFileSync(path.join(folder,'gate.json'),JSON.stringify({version:1,transaction_id:'fixture-update',closed:true}));
  f.advance(10000);
  const renewed=await f.request('/turn/renew',{lease_id:start.action_lease.lease_id,task_id:'accepted'});
  assert.equal(renewed.lease_id,start.action_lease.lease_id);
  await f.request('/finish',{});assert.equal((await f.request('/status')).turn_active,false);
  await f.request('/turn',{renewable_lease:true,continuation:true},400);
  assert.equal(f.history.task().turns,121);assert.equal(f.history.task().deadline,f.task.deadline);
 }finally{f.close();}
});
test('malformed installation gate fails closed without changing task state',async()=>{
 const f=fixture();try{
  const before=JSON.stringify(f.history.data),folder=path.join(f.home,'installation-updates');fs.mkdirSync(folder);
  fs.writeFileSync(path.join(folder,'gate.json'),'{}');
  await f.request('/turn',{renewable_lease:true,continuation:true},400);
  assert.equal(JSON.stringify(f.history.data),before);
 }finally{f.close();}
});


test('actual body allows human-requested movement under unchanged assignment, then retains ordinary work accounting',async()=>{
 let moved=0;
 const f=fixture({incoming_chat_only:true,human_engagement:{enabled:true},human_task_intake:{enabled:true}},{async move(bot,p,_range,check){check();moved++;bot.entity.position=p;return {reached:true,position:p};}});
 try{
  const {Vec3}=realRequire('vec3');f.bot.entity.position=new Vec3(0,64,0);
  const task=f.history.task();task.authority={kind:'human_game_request'};task.authority_revision=1;
  const e=f.history.record({kind:'chat',source:'human',username:'Visitor',message:'Go stand by it',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString(),transport:{kind:'server_player_uuid',username:'Visitor',uuid:'verified-human'}});
  f.history.data.inbox.push({id:e.id,source:'human',username:'Visitor',message:e.message});f.history.save();
  await f.request('/turn',{conversation_only:true,message_ids:[e.id]});
  assert.equal((await f.request('/status')).reply_work_allowed,true);assert.equal(f.history.task().turns,120);
  const r=await f.operate('move',{x:1,y:64,z:0,mode:'walk_only'});assert.equal(r.reached,true);assert.equal(moved,1);
  assert.equal(f.history.task().turns,121);const status=await f.request('/status');assert.equal(status.conversation_only,false);assert.equal(status.action_lease.renewable,true);
  await f.operate('work_report',{status:'running',summary:'Reached the requested spot; the existing assignment remains.'});await f.request('/finish',{});
  assert.equal(f.history.task().id,'accepted');assert.equal(f.history.task().deadline,f.task.deadline);assert.equal(f.history.data.last_turn.actions.filter(a=>a.status==='pending').length,0);
 }finally{f.close();}
});


test('recovery inspection stays reachable with effects closed and preserves assignment accounting',async()=>{
 let calls=0;
 const bridge={...realRequire('./watch-bridge.cjs'),invoke:async(_command,_home,facts)=>{calls++;assert.equal(facts.receipts_complete,true);return {action:'inspect_then_continue'};}};
 const f=fixture({incoming_chat_only:true,automatic_recovery:true,task_helpers:{command:'/fixture/helper'},human_task_intake:{enabled:true}},null,bridge);
 try{
  Object.assign(f.history.data.task,{status:'needs_review',authority:{kind:'human_game_request'},authority_revision:1});
  f.history.data.last_turn={task_id:'accepted',interrupted:true,started_at:new Date().toISOString(),actions:[{id:'settled',status:'succeeded'}]};f.history.save();
  const before=structuredClone(f.history.task()),status=await f.request('/status');
  assert.equal(status.task_capabilities.autonomous_work_allowed,false);
  assert.equal(status.task_capabilities.recovery_review_allowed,true);
  await f.request('/action',{name:'dig',arguments:{x:1,y:64,z:0}},400);
  assert.equal((await f.request('/continuation',{generation:0})).action,'inspect_then_continue');
  assert.equal(calls,1);assert.equal(f.history.task().status,'running');
  for(const k of ['id','turns','max_turns','deadline','authority_revision','authority'])assert.deepEqual(f.history.task()[k],before[k]);
  assert.equal(f.history.task().recovery_attempts,1);assert.equal((await f.request('/status')).action_lease.lease_id,null);
  await f.request('/continuation',{generation:0});assert.equal(calls,1);
 }finally{f.close();}
});
test('recovery inspection never bypasses Stop, limits, uncertain effects or installation policy',async()=>{
 for(const scenario of ['stopped','expired','exhausted','pending','uncertain','attempts','disabled','chat_only']){
  let calls=0;const bridge={...realRequire('./watch-bridge.cjs'),invoke:async()=>{calls++;throw Error('Must not invoke');}};
  const f=fixture({incoming_chat_only:true,automatic_recovery:scenario!=='disabled',task_helpers:{command:'/fixture/helper'},human_task_intake:{enabled:scenario!=='chat_only'}},null,bridge);
  try{
   Object.assign(f.history.data.task,{status:scenario==='stopped'?'stopped':'needs_review',authority:{kind:'human_game_request'}});
   if(scenario==='expired')f.history.data.task.deadline=Date.now()-1;
   if(scenario==='exhausted')f.history.data.task.max_turns=f.history.data.task.turns;
   if(scenario==='attempts')f.history.data.task.recovery_attempts=2;
   f.history.data.last_turn={task_id:'accepted',interrupted:true,started_at:new Date().toISOString(),actions:[{id:'effect',status:['pending','uncertain'].includes(scenario)?scenario:'succeeded'}]};f.history.save();
   assert.equal((await f.request('/status')).task_capabilities.recovery_review_allowed,false,scenario);
   const before=JSON.stringify(f.history.data);assert.equal((await f.request('/continuation',{generation:0})).action,'hold');
   assert.equal(calls,0);assert.equal(JSON.stringify(f.history.data),before,scenario);
  }finally{f.close();}
 }
});
test('optional attention cannot reserve a construction turn or poison an existing task on reply failure',async()=>{
 const f=fixture({incoming_chat_only:true,human_engagement:{enabled:true},human_task_intake:{enabled:true}});
 try{
  f.history.data.task.authority={kind:'human_game_request'};
  const e=f.history.record({kind:'chat',source:'human',username:'Visitor',message:'How is it going?',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString()});
  f.history.data.inbox.push({id:e.id,source:'human',username:'Visitor',message:e.message,attention_offer:{id:'offer',ticket:'ticket'}});f.history.save();
  const task=JSON.stringify(f.history.task());
  await f.request('/turn',{message_ids:[e.id],renewable_lease:true},400);
  assert.equal(JSON.stringify(f.history.task()),task);assert.equal(f.history.data.inbox.length,1);
  await f.request('/turn',{conversation_only:true,message_ids:[e.id]});
  await f.request('/finish',{error:true});
  assert.equal(JSON.stringify(f.history.task()),task);assert.equal(f.history.data.last_conversation_turn.interrupted,true);
 }finally{f.close();}
});
