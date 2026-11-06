const test=require('node:test'),assert=require('node:assert/strict');
const {publicSource}=require('../source-revision.cjs');
const {Conversation}=require('../conversation.cjs');
const {Participation}=require('../participation.cjs');
function event(){return {id:'immutable-event',time:new Date().toISOString(),kind:'chat',username:'Peer',source:'agent',message:'A'.repeat(1000),provenance:'minecraft_public_chat'};}
test('attention and active awareness share source revision despite truncation/context changes',()=>{
 const e=event(),history={data:{events:[e],participation_pending:[e.id]},save(){}};
 const p=new Participation(history,{username:'Builder',bot_names:['Peer'],conversation_attention:{enabled:true}});
 const first=p.proposal([]),c=new Conversation(history,'Builder').snapshot();
 assert.deepEqual(first.sources[0],c.messages[0].source_fact);
 assert.equal(first.context.messages[0].text.length,700);assert.equal(c.messages[0].text.length,800);
 assert.equal(first.sources[0].occurredAt,Date.parse(e.time));
 history.data.task={goal:'Changed surrounding task'};
 assert.notEqual(p.proposal(['Other']).signature,first.signature);
 assert.deepEqual(p.proposal(['Other']).sources[0],first.sources[0]);
 assert.notEqual(publicSource({...e,message:e.message+'edit'}).revision,first.sources[0].revision);
});
test('private controls, whispers and missing original time do not get public provenance',()=>{
 const e=event();
 for(const value of [{...e,whisper:true},{...e,provenance:'operator_control'},{...e,provenance:undefined,username:'Operator'},{...e,time:undefined}])
  assert.equal(publicSource(value),null);
});
