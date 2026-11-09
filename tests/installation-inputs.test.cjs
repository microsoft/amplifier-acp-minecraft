const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const api=require('../installation-inputs.cjs'),{WorkshopState}=require('../workshop-state.cjs'),outcomes=require('../input-outcomes.cjs');
const caller={id:'voice-test',label:'Test voice connection',token:'a'.repeat(40)};
function payload(now=Date.now()){return {text:'Original human wording.\nLeave the finished work alone.',source:{version:1,request_id:'ba3a420b-54b9-4004-902b-b22ad783df86',call_id:'test-call',intent_id:'test-intent',revision:'1',occurred_at:new Date(now).toISOString(),actor:{id:'test-user',label:'Test person'},audience:{kind:'private',experience:'companion',id:'test-call-audience'}}};}
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'installation-source-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const h=new WorkshopState(path.join(root,'workshop.json'));h.data.task={id:'old',status:'budget_exhausted',turns:12,deadline:1};h.data.activity_stop={at:1};h.save();return h;}
function read(h,p,r,c=caller){return api.query(h,c,{version:1,requests:[{request_id:r.request_id,source:p.source}]}).outcomes[0];}
test('dedicated caller credentials cannot reuse owner secrets or duplicate identity',()=>{
 assert.deepEqual(api.callers({}),[]);const list=api.callers({token:'owner',installation_callers:[caller]});assert.equal(api.authenticate(list,'Bearer '+caller.token),caller);assert.equal(api.authenticate(list,'Bearer wrong'),null);
 for(const cfg of [{token:caller.token,installation_callers:[caller]},{installation_callers:[caller,caller]},{installation_callers:[{...caller,token:'short'}]}])assert.throws(()=>api.callers(cfg));
 for(const [method,url] of [['POST','/action'],['POST','/stop'],['GET','/state'],['GET','/operator-inputs'],['GET','/input-outcomes?ids=x'],['POST','/inbox/drain'],['POST','/mcp']])assert.equal(api.allowed(method,url),false);
});
test('atomic admission preserves exact wording/source and no work state changes',t=>{
 const h=fixture(t),p=payload(),before=JSON.stringify(h.data.task),stop=JSON.stringify(h.data.activity_stop);const {receipt:r,event:e}=api.enqueue(h,caller,p);
 assert.equal(e.message,p.text);assert.equal(e.time,p.source.occurred_at);assert.equal(e.transport.uuid,undefined);assert.equal(e.username,caller.label);assert.equal(e.installation_source.actor.id,'test-user');assert.equal(e.provenance,'operator_control');assert.equal(e.installation_source.audience.kind,'private');assert.equal(h.data.inbox[0].id,r.request_id);assert.equal(JSON.stringify(h.data.task),before);assert.equal(JSON.stringify(h.data.activity_stop),stop);assert.equal(read(h,p,r).delivery,'queued');
});
test('lost acknowledgement/restart/credential rotation returns same receipt without requeue',t=>{
 const h=fixture(t),p=payload(),r=api.enqueue(h,caller,p).receipt;h.data.inbox=[];h.save();const reloaded=new WorkshopState(h.file);const before=JSON.stringify(reloaded.data);
 const dup=api.enqueue(reloaded,{...caller,token:'b'.repeat(40)},p,{now:Date.now()+86400000});assert.equal(dup.receipt.request_id,r.request_id);assert.equal(dup.receipt.duplicate,true);assert.equal(dup.event,null);assert.equal(JSON.stringify(reloaded.data),before);
 for(const q of [{...p,text:p.text+' changed'},{...p,source:{...p.source,revision:'2'}}])assert.throws(()=>api.enqueue(reloaded,caller,q),/different payload/);
});
test('failed disk admission rolls back inbox, source journal and original state',t=>{
 const h=fixture(t),before=JSON.stringify(h.data);h.save=()=>{throw Error('disk failure');};assert.throws(()=>api.enqueue(h,caller,payload()),/disk failure/);assert.equal(JSON.stringify(h.data),before);
});
test('queue capacity, stale/future/revoked source fail without durable receipt',t=>{
 const h=fixture(t),now=Date.now();
 for(const time of [now-600000,now+5001])assert.throws(()=>api.enqueue(h,caller,payload(time),{now}));
 h.data.task_source_cutoff=now;assert.throws(()=>api.enqueue(h,caller,payload(now),{now}));delete h.data.task_source_cutoff;
 h.data.inbox=Array.from({length:8},(_,id)=>({id}));const before=JSON.stringify(h.data);assert.throws(()=>api.enqueue(h,caller,payload(now),{now}),/queue/);assert.equal(JSON.stringify(h.data),before);
});
test('caller and exact original actor/audience/call/revision bind outcome access',t=>{
 const h=fixture(t),p=payload(),r=api.enqueue(h,caller,p).receipt;const unknown=read(h,p,r,{...caller,id:'other'});assert.equal(unknown.delivery,'unknown');assert.equal(unknown.source,undefined);
 for(const change of [{actor:{...p.source.actor,id:'other'}},{audience:{...p.source.audience,id:'other'}},{revision:'2'},{call_id:'other'},{intent_id:'other'},{occurred_at:new Date(Date.now()+1000).toISOString()}])assert.deepEqual(read(h,{...p,source:{...p.source,...change}},r),unknown);
 assert.equal(read(h,p,r).source.caller.id,caller.id);
});
test('outcome distinguishes grouped public speech, hides private replies and never claims completion',t=>{
 const h=fixture(t),p=payload(),r=api.enqueue(h,caller,p).receipt;
 h.data.turn={request_ids:[r.request_id,'another-source'],started_at:new Date().toISOString(),conversation_only:true};outcomes.admit(h.data);
 outcomes.response(h.data,{kind:'chat_sent',id:'public',time:new Date().toISOString(),provenance:'minecraft_public_chat',sent:'Public progress'});
 outcomes.response(h.data,{kind:'chat_sent',id:'private',time:new Date().toISOString(),provenance:'minecraft_public_chat',whisper:true,sent:'PRIVATE_SENTINEL'});outcomes.settle(h.data);
 const result=read(h,p,r);assert.equal(result.delivery,'terminal');assert.equal(result.response_association,'shared_turn');assert.equal(result.source_ids,undefined);assert.equal(result.private_responses_withheld,true);assert.equal(result.completion,'not_established');assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'));assert.equal(result.responses[0].text,'Public progress');
});
test('schemas refuse caller spoof, unknown fields, malformed source and duplicate query IDs',t=>{
 const h=fixture(t),p=payload();for(const q of [{...p,caller:'owner'},{...p,source:{...p.source,caller:'owner'}},{...p,source:{...p.source,audience:{kind:'public',experience:'minecraft',id:'x'}}},{...p,source:{...p.source,occurred_at:'yesterday'}}])assert.throws(()=>api.enqueue(h,caller,q));
 const r=api.enqueue(h,caller,p).receipt;assert.throws(()=>api.query(h,caller,{version:1,requests:[{request_id:r.request_id,source:p.source},{request_id:r.request_id,source:p.source}]}));
});
