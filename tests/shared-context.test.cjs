// Shared reads project public evidence; owner-local records stay unchanged.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const cfg={username:'Builder',conversation_id:'fixture-world',context_grant:'fixture-grant'};
const canary='PRIVATE_EVENT_CANARY';
function fixture(t){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'shared-context-'));
 t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 return new WorkshopState(path.join(home,'state.json'));
}
function read(s,operation='read',limit=40){
 return s.query({operation,limit,access:{mode:'grant',grant:cfg.context_grant}},cfg,{connected:true});
}
function owner(s){return s.query({operation:'read',limit:40,access:{mode:'owner'}},cfg,{});}

test('shared work-status receipts omit nested observations while preserving summaries and local evidence',t=>{
 const s=fixture(t),at=new Date().toISOString();
 const request=s.record({kind:'chat',source:'human',username:'Operator',accepted:true,whisper:false,
  provenance:'operator_control',message:canary,time:at});
 const task=s.begin({request_id:request.id,goal:'Build a public dock'});
 const observation={position:{x:1,y:64,z:2},recent_actions:[{action:'tell',
  arguments:{player:'Owner',text:canary},result:{sent:canary}}],private_snapshot:{nested:[canary]}};
 s.note({task_id:task.id,summary:'Dock framing inspected'},observation);
 s.record({kind:'work_status',time:at,task_id:task.id,status:task.status,goal:task.goal,
  progress:task.progress.at(-1),debug:{private_brief:canary}});
 const fresh=new WorkshopState(s.file),before=fs.readFileSync(s.file,'utf8');
 for(const operation of ['read','orientation']){
  const result=read(fresh,operation);
  assert.ok(!JSON.stringify(result).includes(canary),'nested action evidence is owner-local');
  assert.equal(result.current.activity.task.progress[0].summary,'Dock framing inspected');
  assert.equal(result.messages.length,1);
  const event=JSON.parse(result.messages[0].text);
  assert.deepEqual(event.progress,{at:task.progress.at(-1).at,summary:'Dock framing inspected'});
  assert.equal(event.task_id,task.id);assert.equal(event.status,'running');
  assert.equal(event.goal,'Build a public dock');
 }
 assert.ok(JSON.stringify(owner(fresh)).includes(canary));
 assert.deepEqual(fresh.data.events.at(-1).progress.observation,observation);
 assert.equal(fs.readFileSync(s.file,'utf8'),before,'projection never rewrites local records');
});

test('shared action lifecycle receipts omit tell arguments, returned payloads and error text',t=>{
 const s=fixture(t),at=new Date().toISOString();
 for(const kind of ['action_started','action_result','action_failed']){
  s.record({kind,time:at,action_id:'attempt-'+kind,action:'tell',
   arguments:{player:canary,text:canary},result:{sent:canary,error:canary},error:canary,
   message:canary,sent:canary,metadata:{nested:canary}});
 }
 const before=fs.readFileSync(s.file,'utf8');
 const result=read(new WorkshopState(s.file));
 assert.ok(!JSON.stringify(result).includes(canary));
 assert.equal(result.messages.length,3);
 for(const row of result.messages){
  const event=JSON.parse(row.text);
  assert.equal(event.action,'tell');assert.equal(event.action_id,'attempt-'+row.label);
  for(const field of ['arguments','result','error','message','sent','metadata'])assert.ok(!(field in event));
 }
 assert.equal(JSON.parse(result.messages[1].text).reported_error,true);
 assert.ok(JSON.stringify(owner(s)).includes(canary));
 assert.equal(fs.readFileSync(s.file,'utf8'),before);
});

test('unknown and private event types cannot bypass shared projection or crowd out public chat',t=>{
 const s=fixture(t);
 const publicChat=s.record({kind:'chat',time:new Date().toISOString(),username:'Visitor',
  provenance:'minecraft_public_chat',message:'How is the dock going?',debug:canary});
 for(const kind of ['future_internal_event','attention_watch_tool','operator_recovery']){
  s.record({kind,result:{secret:canary},message:canary});
 }
 s.record({kind:'work_status',provenance:'operator_control',progress:{summary:canary}});
 s.record({kind:'action_result',action:'tell',whisper:true,result:{sent:canary}});
 const result=read(s,'read',1);
 assert.ok(!JSON.stringify(result).includes(canary));
 assert.equal(result.messages.length,1);assert.equal(result.messages[0].id,publicChat.id);
 assert.equal(result.messages[0].text,'How is the dock going?');assert.equal(result.complete,true);
 assert.ok(JSON.stringify(owner(s)).includes(canary));
});

test('empty public chat never falls back to raw event serialization',t=>{
 const s=fixture(t);
 s.record({kind:'chat_sent',time:new Date().toISOString(),provenance:'minecraft_public_chat',sent:'',extra:canary});
 const result=read(s);
 assert.equal(result.messages.length,1);assert.equal(result.messages[0].text,'');
 assert.ok(!JSON.stringify(result).includes(canary));
 assert.ok(JSON.stringify(owner(s)).includes(canary));
});

test('shared receipts preserve bounded action outcomes without claiming independently verified completion',t=>{
 const s=fixture(t);
 s.record({kind:'action_result',action_id:'move-1',action:'move',arguments:{x:12,y:64,z:20},
  result:{reached:true,debug:canary},private_trace:canary});
 s.record({kind:'action_failed',action_id:'move-2',action:'move',error:canary,
  timeout:true,operation_settled:true,turn_preserved:true});
 const result=read(s);
 assert.ok(!JSON.stringify(result).includes(canary));
 const [returned,failed]=result.messages.map(row=>JSON.parse(row.text));
 assert.equal(returned.kind,'action_result');assert.equal(returned.action,'move');
 assert.equal(returned.action_id,'move-1');assert.equal(returned.reported_error,false);
 assert.ok(!('verified' in returned));assert.ok(!('result' in returned));
 assert.equal(failed.kind,'action_failed');assert.equal(failed.action_id,'move-2');
 assert.equal(failed.timeout,true);assert.equal(failed.operation_settled,true);assert.equal(failed.turn_preserved,true);
 assert.match(result.current.coverage,/metadata/);
});
