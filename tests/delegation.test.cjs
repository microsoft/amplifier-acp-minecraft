const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs'),{TaskIntake}=require('../task-intake.cjs'),{ConversationAdmission}=require('../conversation-admission.cjs');
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'helper-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(dir,'state.json')),cfg={incoming_chat_only:true,human_engagement:{enabled:true},bot_names:['Lead'],task_max_turns:12,task_max_seconds:2400,human_task_intake:{enabled:true,max_turns:45,max_seconds:10800,delegation:{enabled:true}}};
 let now=Date.now();const intake=new TaskIntake(h,cfg,{now:()=>now}),admit=new ConversationAdmission(h,cfg,{now:()=>now});
 function event(source,username,message,extra={}){return h.record({time:new Date(now).toISOString(),kind:'chat',source,username,message,whisper:false,provenance:'minecraft_public_chat',accepted:source==='agent',intent:source==='agent'?'request':undefined,transport:{kind:'server_player_uuid',username,uuid:source==='human'?'00000000-0000-0000-0000-000000000001':'00000000-0000-0000-0000-000000000002'},...extra});}
 const root=event('human','Human','Lead, recruit helpers to build the shop; each may use its own normal allowance.');
 const peer=event('agent','Lead','@Helper Please supply timber for the human-authorized shop.');
 const message={id:peer.id,source:'agent',username:'Lead',message:peer.message};h.data.inbox=[message];h.save();
 const args={request_id:root.id,peer_request_id:peer.id,authorization_quote:'recruit helpers to build the shop; each may use its own normal allowance',budget_scope:'independent_per_agent',goal:'Supply timber for the shop'};
 return {h,cfg,intake,admit,root,peer,message,args,event,advance(ms){now+=ms;},start(){return admit.start([peer.id],h.data.inbox);}};
}
test('helper independently accepts local human provenance and peer proposal; no effects or shared budget grant',t=>{
 const f=fixture(t);f.advance(60000);f.start();const result=f.intake.acceptHelp(f.args);
 assert.equal(result.execution_started,false);assert.equal(result.turns,0);assert.equal(result.max_turns,12);
 assert.equal(result.deadline,Date.parse(f.root.time)+2400000);assert.equal(f.h.data.turn.may_mutate,false);
 assert.equal(f.h.task().authority.source.id,f.root.id);assert.equal(f.h.task().authority.delegation.peer.id,f.peer.id);assert.equal(f.h.task().authority.delegation.may_delegate_further,false);
 assert.equal(f.h.task().requested_by,'Human');assert.equal(f.intake.capabilities().can_delegate_execution,false);
});
test('lost acknowledgement/reload preserves helper task and consumed source; edited retry is rejected',t=>{
 const f=fixture(t);f.start();const first=f.intake.acceptHelp(f.args),loaded=new WorkshopState(f.h.file),intake=new TaskIntake(loaded,f.cfg);
 const duplicate=intake.acceptHelp(f.args);assert.equal(duplicate.task_id,first.task_id);assert.equal(duplicate.duplicate,true);assert.equal(loaded.data.task_authorizations.length,1);
 assert.throws(()=>intake.acceptHelp({...f.args,goal:'Something else'}),/different transition/);assert.equal(loaded.task().turns,0);
});
test('peer copies, unknown transport, private/root stale/retracted sources and unsupported budgets cannot grant helper authority',t=>{
 const cases=[f=>f.root.source='agent',f=>f.root.transport=null,f=>f.peer.transport=null,f=>f.root.whisper=true,f=>f.peer.whisper=true,f=>f.root.transport.username='Other',f=>f.peer.username='Stranger',f=>f.root.time=new Date(Date.now()-700000).toISOString(),f=>f.root.time=new Date(Date.now()+60000).toISOString(),f=>f.h.data.task_source_cutoff=Date.now()+1,f=>f.args.authorization_quote='made up authorization',f=>f.args.budget_scope='aggregate',f=>f.cfg.human_task_intake.delegation.enabled=false,f=>f.args.max_turns=100];
 for(const change of cases){const f=fixture(t);f.start();change(f);assert.throws(()=>f.intake.acceptHelp(f.args));assert.equal(f.h.task(),null);}
});
test('helper acceptance rejects unbound peer, active work and unresolved effects; preserves previous expired records',t=>{
 for(const kind of ['unbound','running','unknown','expired']){const f=fixture(t);f.start();const old={id:'old',status:kind==='unknown'?'needs_review':kind==='running'?'running':'budget_exhausted',turns:8,max_turns:12,deadline:kind==='expired'?1:Date.now()+600000,progress:[],unknown:['retain']};
  if(kind==='unbound')f.h.data.turn.request_ids=[];else f.h.data.task=old;
  if(kind!=='expired'){assert.throws(()=>f.intake.acceptHelp(f.args));if(kind!=='unbound')assert.deepEqual(f.h.data.task,old);}
  else{f.intake.acceptHelp(f.args);assert.deepEqual(f.h.data.task_history[0],old);}
 }
});
test('helper allowance is anchored to original human time and cannot be refreshed by a later proposal',t=>{
 const f=fixture(t);f.start();f.advance(300000);assert.throws(()=>f.intake.acceptHelp({...f.args,seconds:300}),/Original helper allowance/);assert.equal(f.h.task(),null);
});
test('peer proposal replies retain their own bound and cannot consume the unmetered human lane',t=>{
 const f=fixture(t);f.h.data.conversation_admissions=Array.from({length:4},(_,i)=>({at:Date.now(),ids:['prior'+i],kind:'peer_proposal'}));
 assert.equal(f.admit.limit(),null);assert.equal(f.admit.eligible(f.message),false);assert.throws(()=>f.start(),/No fresh/);
 const human=f.event('human','Human','Hello Helper',{accepted:true});assert.equal(f.admit.eligible({id:human.id,source:'human'}),true);
});
test('saving helper admission failure does not leave a live assignment in memory',t=>{
 const f=fixture(t);f.start();f.h.save=()=>{throw Error('disk failed');};assert.throws(()=>f.intake.acceptHelp(f.args),/disk failed/);assert.equal(f.h.data.task,null);assert.equal(f.h.data.accepted_delegation_sources,undefined);
});
test('host-engaged peer report can be answered after human source ages out, without helper authority',t=>{
 const f=fixture(t);f.cfg.agent_dialogue=true;f.advance(700000);
 const e=f.event('agent','Lead','The timber is in the marked chest',{intent:'update'});
 const message={id:e.id,source:'agent',username:'Lead',message:e.message,attention_offer:{id:'offered',ticket:'unchanged-ticket'}};
 f.h.data.inbox=[message];f.h.data.conversation_admissions=Array.from({length:20},(_,i)=>({at:Date.now(),ids:['old'+i],kind:'peer_proposal'}));
 assert.equal(f.admit.eligible(message),true);
 f.admit.start([e.id],f.h.data.inbox);assert.equal(f.h.data.turn.conversation_only,true);assert.equal(f.h.data.turn.may_mutate,false);
 assert.throws(()=>f.intake.acceptHelp({...f.args,peer_request_id:e.id}));assert.equal(f.h.task(),null);
 f.h.finish();const restored=new WorkshopState(f.h.file);assert.equal(new ConversationAdmission(restored,f.cfg).eligible(message),false);
});
test('peer conversation still requires attributed current accepted evidence and explicit dialogue policy',t=>{
 for(const mutate of [f=>f.cfg.agent_dialogue=false,f=>f.peer.transport=null,f=>f.peer.accepted=false,f=>f.peer.username='Unknown',f=>f.peer.time='2000-01-01T00:00:00Z']){
  const f=fixture(t);f.cfg.agent_dialogue=true;f.cfg.human_task_intake.delegation.enabled=false;mutate(f);
  assert.equal(f.admit.eligible(f.message),false);assert.equal(f.h.task(),null);
 }
});
