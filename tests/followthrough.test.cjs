const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs'),{TaskIntake}=require('../task-intake.cjs'),{Conversation}=require('../conversation.cjs');
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'followthrough-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(dir,'workshop.json')),cfg={human_engagement:{enabled:true},human_task_intake:{enabled:true,delegation:{enabled:true}},bot_names:['Lead']};
 const now=Date.now(),i=new TaskIntake(h,cfg,{now:()=>now});
 h.data.task={id:'original',goal:'Finish the shop',status:'waiting',wait_for:'Lead installs the glass or approves signs',started_at:new Date(now-3600000).toISOString(),turns:8,max_turns:12,deadline:now+1800000,progress:[],authority_revision:1,authority:{kind:'human_game_request'}};
 function event(source,message,time=now){return h.record({kind:'chat',source,username:source==='human'?'Visitor':'Lead',message,time:new Date(time).toISOString(),accepted:true,intent:'request',provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',username:source==='human'?'Visitor':'Lead',uuid:'00000000-0000-0000-0000-000000000001'}});}
 const root=event('human','Lead is in charge. Use the crew.',now-1200000),peer=event('agent','The glass is installed. Finish your signs.');
 h.data.turn={conversation_only:true,peer_proposal:true,request_ids:[peer.id],actions:[],may_mutate:false};h.save();
 return {h,cfg,i,event,root,peer,args:{task_id:'original',expected_revision:1,request_id:peer.id,reason:'Glass is installed and the remaining approved signs can proceed.'},help:{expected_task_id:'original',expected_revision:1,request_id:root.id,peer_request_id:peer.id,authorization_quote:'Lead is in charge. Use the crew.',budget_scope:'independent_per_agent',goal:'Finish the approved signs'}};
}
test('dependency resolution schedules same waiting task without effects or changing spent/bounds; lost ack is idempotent',t=>{
 const f=fixture(t),before=structuredClone(f.h.task()),r=f.i.resume(f.args);
 assert.equal(r.execution_started,false);assert.equal(f.h.task().status,'running');assert.equal(f.h.data.turn.may_mutate,false);
 for(const key of ['id','goal','turns','max_turns','deadline','authority_revision','authority'])assert.deepEqual(f.h.task()[key],before[key]);
 const loaded=new WorkshopState(f.h.file),i=new TaskIntake(loaded,f.cfg);assert.equal(i.resume(f.args).duplicate,true);assert.equal(loaded.data.work_resumptions.length,1);
 assert.throws(()=>i.resume({...f.args,reason:'different'}),/used differently/);
});
test('resume cannot reopen Stop/expiry/review/uncertain effects or use ambient/unbound/private sources',t=>{
 for(const change of [f=>f.h.task().status='stopped',f=>f.h.task().deadline=1,f=>f.h.task().turns=12,f=>f.h.task().status='review',f=>f.h.task().status='needs_review',f=>f.h.data.turn.ambient_activity=true,f=>f.h.data.turn.request_ids=[],f=>f.peer.whisper=true,f=>f.peer.transport=null,f=>f.h.task().authority_revision=2,f=>f.h.data.last_turn={task_id:'original',interrupted:true,started_at:new Date().toISOString(),actions:[{status:'pending'}]}]){
  const f=fixture(t);change(f);f.h.task();const before=JSON.stringify(f.h.data);assert.throws(()=>f.i.resume(f.args));assert.equal(JSON.stringify(f.h.data),before);
 }
});
test('existing helper coordination retains human provenance, original goal and spent bounds across reload; does not require a new assignment',t=>{
 const f=fixture(t),before=structuredClone(f.h.task());assert.equal(f.i.capabilities().can_accept_help,true);
 const r=f.i.acceptHelp(f.help);assert.equal(r.task_id,'original');assert.equal(r.execution_started,false);
 for(const key of ['id','goal','turns','max_turns','deadline','authority'])assert.deepEqual(f.h.task()[key],before[key]);
 assert.equal(f.h.task().coordination[0].source.id,f.root.id);assert.equal(f.h.task().coordination[0].peer.id,f.peer.id);assert.equal(f.h.data.turn.may_mutate,false);
 const loaded=new WorkshopState(f.h.file),i=new TaskIntake(loaded,f.cfg);assert.equal(i.acceptHelp(f.help).duplicate,true);assert.equal(loaded.task().authority_revision,2);
 assert.throws(()=>i.acceptHelp({...f.help,goal:'changed'}),/different transition/);
});
test('retained human authority supports only same active assignment; no source forgery, changed revision, renewal or expired task',t=>{
 for(const change of [f=>delete f.help.expected_task_id,f=>f.help.expected_revision=2,f=>f.help.seconds=300,f=>f.help.max_turns=40,f=>f.h.task().deadline=1,f=>f.h.task().status='stopped',f=>f.root.source='agent',f=>f.root.transport=null,f=>f.h.data.task_source_cutoff=Date.now()+1,f=>f.root.time=new Date(Date.now()-7200000).toISOString(),f=>f.help.authorization_quote='made up instruction']){
  const f=fixture(t);change(f);f.h.task();const before=JSON.stringify(f.h.data);assert.throws(()=>f.i.acceptHelp(f.help));assert.equal(JSON.stringify(f.h.data),before);
 }
});
test('public requirements survive physical-event churn and search excludes whispers/operator evidence',t=>{
 const f=fixture(t),c=new Conversation(f.h,'Self');f.event('human','A piston entrance with a Doom theme');
 f.h.record({kind:'chat',username:'Visitor',message:'PRIVATE piston password',whisper:true,provenance:'minecraft_whisper'});
 f.h.record({kind:'chat',username:'Operator',message:'PRIVATE piston admin',provenance:'operator_control'});
 for(let n=0;n<1010;n++)f.h.record({kind:'action_result',action:'move',result:{position:n}});
 assert.equal(f.h.data.events.some(e=>e.message?.includes('Doom')),false);
 const result=c.search({query:'piston',limit:10});assert.deepEqual(result.messages.map(m=>m.text),['A piston entrance with a Doom theme']);assert.equal(result.history_may_be_incomplete,true);
 assert.equal(f.i.capabilities().delegation_sources.some(e=>e.id===f.root.id),true);
});
test('failed durable resume/coordination write cannot leave changed task in memory',t=>{
 for(const method of ['resume','acceptHelp']){const f=fixture(t),before=JSON.stringify(f.h.data);f.h.save=()=>{throw Error('disk failure');};assert.throws(()=>f.i[method](method==='resume'?f.args:f.help),/disk failure/);assert.equal(JSON.stringify(f.h.data),before);}
});
test('a fresh human can amend scope without resetting spent work or replacing original authority',t=>{
 const f=fixture(t),e=f.event('human','Keep the shop and add the piston entrance'),old=structuredClone(f.h.task());
 f.h.data.turn.request_ids=[e.id];f.h.data.turn.peer_proposal=false;
 const args={request_id:e.id,task_id:old.id,expected_revision:1,goal:'Finish the shop including its piston entrance',resume:true};
 f.i.amend(args);for(const key of ['id','turns','max_turns','deadline','authority'])assert.deepEqual(f.h.task()[key],old[key]);
 assert.equal(f.h.task().status,'running');assert.equal(f.h.task().goal,args.goal);
 const loaded=new WorkshopState(f.h.file),i=new TaskIntake(loaded,f.cfg);assert.equal(i.amend(args).duplicate,true);assert.equal(loaded.task().authority_revision,2);
});
