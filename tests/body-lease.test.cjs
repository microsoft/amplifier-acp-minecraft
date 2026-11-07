const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),{createRequire}=require('node:module'),{Readable}=require('node:stream');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
function fixture(configOverride={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-lease-')),config=path.join(home,'config.json');
 fs.writeFileSync(config,JSON.stringify({username:'Builder',token:'fixture',...configOverride}));
 const now=Date.now(),task={id:'accepted',status:'running',deadline:now+3600000,turns:120,max_turns:135,progress:[]};
 fs.writeFileSync(path.join(home,'workshop.json'),JSON.stringify({task,events:[],turn:null,inbox:[]}));
 const bot=new EventEmitter();Object.assign(bot,{username:'Builder',players:{},loadPlugin(){},pathfinder:{setGoal(){}},clearControlStates(){},stopDigging(){},entity:{position:{clone:()=>({x:0,y:64,z:0})}},health:20});
 let handle,current=now;const timers=new Set();
 class Clock extends Date{static now(){return current;}}
 const ctx=vm.createContext({require:n=>n==='mineflayer'?{createBot:()=>bot}:n==='node:http'?{createServer:h=>{handle=h;return {listen(){},close(){}};}}:realRequire(n),
 module:{exports:{}},console:{log(){}},Date:Clock,Buffer,process:{argv:['node','body.cjs',config],on(){},exit(){}},
 setTimeout:(fn,ms)=>{const t={fn,at:current+ms,unref(){}};timers.add(t);return t;},clearTimeout:t=>timers.delete(t)});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nready=true;module.exports={history,operate};',ctx);
 return {...ctx.module.exports,task,bot,async request(url,payload,code=200,token='fixture'){
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
