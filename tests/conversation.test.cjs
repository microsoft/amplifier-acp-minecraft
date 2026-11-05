const test=require('node:test'),assert=require('node:assert/strict');
const {Conversation}=require('../conversation.cjs');
test('tool results carry only new public context, without repeatedly appending old messages',()=>{
 const history={data:{events:[]}},c=new Conversation(history,'Self');c.expose();
 const add=(id,text)=>history.data.events.push({id,kind:'chat',username:'Peer',message:text,provenance:'minecraft_public_chat',source:'agent'});
 add('1','Supplies arrived');const first=c.updates();assert.equal(first.messages.length,1);assert.equal(c.updates(),null);
 add('2','Please collect them');const second=c.updates();assert.deepEqual(second.messages.map(v=>v.id),['2']);assert.equal(c.updates(),null);
 for(let i=3;i<24;i++)add(String(i),'Bounded public update');
 const limited=c.updates();assert.equal(limited.messages.length,16);assert.equal(limited.earlier_context_may_be_omitted,true);
 assert.equal(c.snapshot().exposed_revision,'23');
});
