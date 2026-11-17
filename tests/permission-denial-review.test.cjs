const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {WorkshopState}=require('../workshop-state.cjs'),policy=require('../activity-policy.cjs'),{review}=require('../activity-settlement.cjs');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
function fixture(t){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'denied-activity-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(home,'workshop.json')),cfg={human_engagement:{enabled:true,task_optional:true}};
 h.data.task={id:'original-task',status:'waiting',turns:28,bounds:{deadline_ms:{kind:'no_configured_bound'},max_turns:{kind:'no_configured_bound'}},authority:{revision:5},progress:[{summary:'Completed transfer must not be repeated'}]};
 h.data.last_turn={activity:true,started_at:'2026-11-17T19:21:02.056Z',task_id:null,progress_revision:0,actions:[],request_ids:[],may_mutate:true,interrupted:true};
 h.data.inbox=[{id:'retained-input'}];h.data.input_outcomes=[{id:'unknown-input',status:'unknown'}];
 const observation={position:{x:1,y:64,z:2},inventory:{slots:[],cursor:null},session:{session:crypto.randomUUID(),binding:'b'.repeat(64)}};
 const denial={version:1,session:{...observation.session},turn_started_at:h.data.last_turn.started_at,prompt_id:'prompt-original',complete_tool_ledger:true,calls:[{id:'call-original',permission:'cancelled',reason:'unverified_tool_identity',status:'failed',dispatch:'not_dispatched'}],terminal:{stop_reason:'cancelled',unsettled_tool_count:0},sources:{client_sha256:'c'.repeat(64),instance_sha256:'d'.repeat(64),engine_sha256:'e'.repeat(64)}};
 const input={generation:1,request_id:crypto.randomUUID(),expected_turn_sha256:digest(h.data.last_turn),expected_task_sha256:digest(h.data.task),expected_position:{...observation.position},expected_inventory_sha256:digest(observation.inventory),evidence_sha256:'a'.repeat(64),reason:'Owner reviewed the complete original prompt ledger and correlated every denied call with the producer pre-dispatch terminal. All external evidence is retained.',receipts:[],permission_denial:denial};
 h.save();return {h,cfg,input,observation};
}
test('exact owner-reviewed denied prompt permits only fresh activity and preserves original records',t=>{
 const {h,cfg,input,observation}=fixture(t),before=structuredClone(h.data);
 assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
 const result=review(h,cfg,input,observation);assert.equal(result.activity_allowed,true);assert.equal(result.future_work_only,true);assert.equal(result.replayed,false);
 assert.equal(policy.canContinue(h,cfg),false);assert.equal(h.data.last_turn.interrupted,true);
 const saved=structuredClone(h.data);delete saved.last_turn.effect_review;assert.deepEqual(saved,before);
 assert.deepEqual(h.data.last_turn.effect_review.permission_denial,input.permission_denial);
 const reload=new WorkshopState(h.file),bytes=fs.readFileSync(h.file);
 assert.equal(review(reload,cfg,input,observation).duplicate,true);assert.deepEqual(fs.readFileSync(h.file),bytes);
 assert.throws(()=>review(reload,cfg,{...input,request_id:crypto.randomUUID()},observation),/reviewed/);
 reload.data.last_turn.request_ids.push('new-input');assert.equal(policy.allowed(reload,cfg),false);
});
const mutations={
 missing_evidence:f=>delete f.input.permission_denial,
 incomplete_ledger:f=>f.input.permission_denial.complete_tool_ledger=false,
 missing_call:f=>f.input.permission_denial.calls=[],
 duplicate_call:f=>f.input.permission_denial.calls.push({...f.input.permission_denial.calls[0]}),
 no_call_identity:f=>delete f.input.permission_denial.calls[0].id,
 allowed_call:f=>f.input.permission_denial.calls[0].permission='allow_once',
 unknown_dispatch:f=>f.input.permission_denial.calls[0].dispatch='unknown',
 dispatched_call:f=>f.input.permission_denial.calls[0].dispatch='dispatched',
 unfinished_call:f=>f.input.permission_denial.calls[0].status='pending',
 wrong_denial:f=>f.input.permission_denial.calls[0].reason='timeout',
 missing_engine_evidence:f=>delete f.input.permission_denial.sources.engine_sha256,
 malformed_hash:f=>f.input.permission_denial.sources.client_sha256='missing',
 boolean_version:f=>f.input.permission_denial.version=true,
 boolean_unsettled:f=>f.input.permission_denial.terminal.unsettled_tool_count=false,
 unsettled_tool:f=>f.input.permission_denial.terminal.unsettled_tool_count=1,
 ambiguous_terminal:f=>f.input.permission_denial.terminal.stop_reason='unknown',
 empty_prompt:f=>f.input.permission_denial.prompt_id='',
 different_turn:f=>f.input.permission_denial.turn_started_at='2026-11-17T19:20:00Z',
 different_session:f=>f.observation.session.session=crypto.randomUUID(),
 different_binding:f=>f.observation.session.binding='f'.repeat(64),
 absent_session:f=>delete f.observation.session,
 nonempty_action:f=>f.h.data.last_turn.actions=[{id:'extra',status:'succeeded'}],
 uncertain_action:f=>f.h.data.last_turn.actions=[{id:'extra',status:'uncertain'}],
 absent_actions:f=>delete f.h.data.last_turn.actions,
 input_bound:f=>f.h.data.last_turn.request_ids=['old-input'],
 absent_request_ids:f=>delete f.h.data.last_turn.request_ids,
 speech:f=>f.h.data.last_turn.speech_operations=[{status:'submitted'}],
 malformed_speech:f=>f.h.data.last_turn.speech_operations={},
 domain_report:f=>f.h.data.last_turn.activity_report={status:'waiting'},
 stopped:f=>f.h.data.activity_stop={at:1},
 active:f=>f.h.data.turn={activity:true},
 task_turn:f=>f.h.data.last_turn.task_id='original-task',
 not_interrupted:f=>f.h.data.last_turn.interrupted=false,
 disabled:f=>f.cfg.human_engagement.task_optional=false,
 same_turn_action_event:f=>f.h.data.events.push({kind:'action_started',time:'2026-11-17T19:21:03Z'}),
 malformed_action_time:f=>f.h.data.events.push({kind:'action_result',time:'unknown'}),
 overlapping_sequence:f=>f.h.data.action_sequences=[{status:'completed',started_at:'2026-11-17T19:21:03Z'}],
 unresolved_old_sequence:f=>f.h.data.action_sequences=[{status:'interrupted',started_at:'2026-11-16T00:00:00Z'}],
 changed_task:f=>f.h.data.task.turns++,
 changed_position:f=>f.observation.position.x++,
 changed_inventory:f=>f.observation.inventory.slots.push({name:'stone'}),
 unknown_cursor:f=>delete f.observation.inventory.cursor,
 cursor:f=>f.observation.inventory.cursor={name:'stone'},
 extra_action_receipt:f=>f.input.receipts=[{action_id:'extra',receipt_sha256:'a'.repeat(64)}],
};
for(const [name,mutate] of Object.entries(mutations))test('denied empty activity refuses '+name+' unchanged',t=>{
 const f=fixture(t);mutate(f);
 // Rehash semantic counterexamples: a matching hash does not validate content.
 f.input.expected_turn_sha256=digest(f.h.data.last_turn);
 if(['unknown_cursor','cursor'].includes(name))f.input.expected_inventory_sha256=digest(f.observation.inventory);
 const before=JSON.stringify(f.h.data),disk=fs.readFileSync(f.h.file);
 assert.throws(()=>review(f.h,f.cfg,f.input,f.observation));assert.equal(JSON.stringify(f.h.data),before);assert.deepEqual(fs.readFileSync(f.h.file),disk);
});
test('failed denial-review persistence restores memory and leaves admission blocked',t=>{
 const {h,cfg,input,observation}=fixture(t),before=JSON.stringify(h.data);h.save=()=>{throw Error('disk full');};
 assert.throws(()=>review(h,cfg,input,observation),/disk full/);assert.equal(JSON.stringify(h.data),before);assert.equal(policy.allowed(new WorkshopState(h.file),cfg),false);
});
