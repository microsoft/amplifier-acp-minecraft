const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {fixture,uuid}=require('./world-body-fixture.cjs');

test('MCP lists world tools outside a turn and publishes one durable utterance',async t=>{
  const f=await fixture(t);
  const names=(await f.rpc('tools/list',{})).tools.map(t=>t.name);
  for(const n of ['chat','move','dig','inspect','operation_status','conversation'])assert.ok(names.includes(n));
  for(const n of ['work_begin','task_accept','start_sequence','work_report','follow_up','attention_watch'])assert.ok(!names.includes(n));
  const args={text:'At the workshop',operation_id:'chat-public-1'};
  assert.ok(!(await f.call('chat',args)).isError);
  assert.ok(!(await f.call('chat',args)).isError);assert.deepEqual(f.sends,['At the workshop']);
  assert.ok((await f.call('chat',{...args,text:'Modified'})).isError);
  assert.equal((await f.request('/turn',{})).status,404);
  assert.equal((await f.request('/mcp',{},'invalid')).status,401);
  assert.equal((await f.request('/stop',{},'owner',{origin:'https://foreign.example'})).status,403);
  assert.equal((await f.request('/stop',{})).status,200);
  assert.ok((await f.call('chat',{text:'stopped',operation_id:'chat-public-2'})).isError);
  assert.equal((await f.call('operation_status',{operation_id:'chat-public-1'})).isError,undefined);
});
test('private requests never enter public history or public dispatch',async t=>{
  const f=await fixture(t,{}, {inbox:[{id:'old',message:'no replay'}]});
  f.bot.emit('whisper','Sam','private words');
  f.bot.emit('chat','Sam','public words');
  const e=(await f.request('/inbox/peek')).value.event;
  assert.equal(e.message,'public words');assert.equal(e.source_fact.id,e.id);
  assert.equal((await f.request('/inbox/ack',{id:'old'})).status,400);
  assert.deepEqual((await f.request('/inbox/ack',{id:e.id})).value,{acknowledged:true,id:e.id});
  assert.equal((await f.request('/inbox/peek')).value.event,null);
  const grant=await f.request('/context/v1/query',{operation:'read',access:{mode:'grant',grant:'grant'}},'context');
  assert.match(JSON.stringify(grant),/public words/);assert.doesNotMatch(JSON.stringify(grant),/private words/);
  const raw=JSON.parse(fs.readFileSync(path.join(f.home,'world-tools/state.json')));
  const id=raw.events.find(e=>e.whisper).id,reply={request_id:id,operation_id:'private-reply-1',text:'private answer'};
  assert.equal((await f.request('/private/reply',reply)).status,200);
  assert.equal((await f.request('/private/reply',reply)).status,200);
  assert.deepEqual(f.whispers,[['Sam','private answer']]);assert.deepEqual(f.sends,[]);
  assert.doesNotMatch(JSON.stringify(await f.call('conversation',{})),/private words|private answer/);
});
test('existing chat-only enrollment and updater gate still restrict effects',async t=>{
  const f=await fixture(t,{incoming_chat_only:true});
  const denied=await f.call('attack',{entity_id:1,uuid,expected:'zombie',operation_id:'attack-001'});
  assert.ok(denied.isError);
  fs.mkdirSync(path.join(f.home,'installation-updates'));
  fs.writeFileSync(path.join(f.home,'installation-updates','gate.json'),JSON.stringify({version:1,transaction_id:'tx',closed:true}));
  assert.ok((await f.call('chat',{text:'held',operation_id:'blocked-001'})).isError);
  assert.deepEqual(f.sends,[]);
});
test('private caller replies and historical outcomes are available within their original scopes',async t=>{
  const caller={id:'source-one',label:'Caller',token:'s'.repeat(40)};
  const original='00000000-0000-4000-8000-000000000010';
  const f=await fixture(t,{installation_callers:[caller]},{
    input_outcomes:[{request_id:original,delivery:'admitted',responses:[],terminal_at:'retained'}]});
  const p={text:'Private source words',source:{version:1,request_id:'00000000-0000-4000-8000-000000000011',call_id:'call',intent_id:'intent',revision:'1',occurred_at:new Date().toISOString(),actor:{id:'human',label:'Owner'},audience:{kind:'private',experience:'voice',id:'room'}}};
  const received=await f.request('/task',p,caller.token);
  assert.equal(received.status,200);const id=received.value.request_id;
  assert.equal((await f.request('/task',p,caller.token)).value.request_id,id);
  assert.equal((await f.request('/private/inbox',undefined,caller.token)).status,403);
  assert.equal((await f.request('/inbox/peek')).value.event,null);
  assert.equal((await f.request('/private/inbox')).value.messages[0].id,id);
  const sent=await f.request('/private/reply',{request_id:id,text:'private response',operation_id:'private-caller-reply'});
  assert.equal(sent.status,200);
  const outcome=await f.request('/source-outcomes',{version:1,requests:[{request_id:id,source:p.source}]},caller.token);
  assert.equal(outcome.value.outcomes[0].source_replies[0].text,'private response');assert.deepEqual(f.sends,[]);
  assert.equal((await f.request('/input-outcomes?ids='+original)).value.outcomes[0].terminal_at,'retained');
});
test('public chat is data, including messages that mention Stop',async t=>{
  const f=await fixture(t);f.bot.emit('chat','Sam',"Body, don't stop building yet");
  const response=await f.call('chat',{operation_id:'chat-intent-2',text:'Heard'});
  assert.ok(!response.isError);assert.deepEqual(f.sends,['Heard']);
});
