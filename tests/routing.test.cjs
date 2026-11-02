const test=require('node:test');const assert=require('node:assert/strict');const {addressed}=require('../routing.cjs');
test('a mention of a third party is not an instruction to them',()=>{
 assert.equal(addressed('BuilderOne, ask BuilderTwo to introduce themselves','BuilderTwo'),false);
 assert.equal(addressed('BuilderOne, ask BuilderTwo to introduce themselves','BuilderOne'),true);
});
test('direct greeting, explicit mention and group addresses',()=>{
 for(const text of ['Hey BuilderOne, help me','BuilderOne','Could you help @BuilderOne?','Team, gather wood'])assert.equal(addressed(text,'BuilderOne'),true);
 assert.equal(addressed('Team, gather wood','BuilderOne',false),false);
 assert.equal(addressed('BuilderOne2, help me','BuilderOne'),false);
});
const {conversationRouter}=require('../routing.cjs');
const {peerIntent}=require('../routing.cjs');
test('public FYI and ACK are context, while unmarked requests remain actionable',()=>{
 assert.equal(peerIntent('@BuilderOne [FYI] Furnace is ready.','BuilderOne'),'update');
 assert.equal(peerIntent('@BuilderOne [ACK] Got it.','BuilderOne'),'ack');
 assert.equal(peerIntent('@BuilderOne Please meet here.','BuilderOne'),'request');
 assert.equal(peerIntent('@BuilderOne2 [FYI] Hello.','BuilderOne'),'request');
 assert.equal(peerIntent('@Someone [FYI] @BuilderOne help.','BuilderOne'),'request');
});
test('question marks and punctuation address the player without matching name prefixes',()=>{
 for(const text of ['BuilderOne?','BuilderOne…','BuilderOne. Are you there?'])assert.equal(addressed(text,'BuilderOne'),true);
 for(const text of ['BuilderOne2?','BuilderOne_helper?'])assert.equal(addressed(text,'BuilderOne'),false);
});
test('synthetic workshop dialogue keeps follow-ups with the addressed agent',()=>{
 const pony=conversationRouter('BuilderOne'),alpha=conversationRouter('BuilderTwo');
 const messages=["BuilderOne, help design a bridge.", 'Start with a materials list.',
 "Please coordinate with the other builders and complete the bridge within this task.",
 'Are you working on it?', 'BuilderOne?'];
 for(const [i,message] of messages.entries()){
  const event={username:'VisitorOne',message,participants:['BuilderOne','BuilderTwo','VisitorOne'],now:1000+i*120000};
  assert.equal(pony(event),i===0||i===4?'direct':'followup');assert.equal(alpha(event),null);
 }
});
test('focus expires, is per human and hands off when someone else is addressed',()=>{
 const route=conversationRouter('BuilderOne',{windowMs:100});
 const send=(username,message,now)=>route({username,message,now,participants:['BuilderOne','BuilderTwo','VisitorTwo']});
 assert.equal(send('VisitorOne','BuilderOne, help',0),'direct');
 assert.equal(send('VisitorTwo','Are you working?',1),null);
 assert.equal(send('VisitorOne','BuilderTwo, help',2),null);
 assert.equal(send('VisitorOne','What now?',3),null);
 assert.equal(send('VisitorOne','BuilderOne?',4),'direct');
 assert.equal(send('VisitorOne','What now?',105),null);
 assert.equal(send('VisitorOne','Team, hello',106),'group');
 assert.equal(send('VisitorOne','What now?',107),null);
});

test('configured aliases route humans and hand off focus without prefix matches',()=>{
 const aliases={BuilderTwo:['Codex']},pony=conversationRouter('BuilderOne',{aliases}),alpha=conversationRouter('BuilderTwo',{aliases});
 const e={username:'VisitorOne',participants:['BuilderOne','BuilderTwo'],now:1};
 assert.equal(pony({...e,message:'BuilderOne, hello'}),'direct');
 assert.equal(alpha({...e,message:'Codex, carve steps'}),'direct');
 assert.equal(pony({...e,message:'Codex, carve steps'}),null);
 assert.equal(pony({...e,message:'How is it going?'}),null);
 assert.equal(alpha({...e,username:'VisitorTwo',message:'BuilderThree, hello'}),null);
 assert.ok(addressed('@BuilderOne I escaped. Please inspect the stairs.','BuilderOne',false));
});
