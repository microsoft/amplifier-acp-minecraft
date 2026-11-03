const test=require('node:test');const assert=require('node:assert/strict');
const {context,messageEnvelope}=require('../watch-bridge.cjs');
test('watch projection scopes to current responsibility, excludes whispers and separates evidence',()=>{
 const task={id:'task',goal:'Design a welcoming place',status:'waiting',deadline:999999,max_turns:12,turns:3,started_at:'2026-11-02T15:00:00Z'};
 const history={task:()=>task,data:{events:[
  {id:'old',kind:'chat',time:'2026-11-02T14:59:00Z',message:'old'},
  {id:'private',kind:'chat',time:'2026-11-02T15:01:00Z',message:'private',whisper:true},
  {id:'new',kind:'chat',time:'2026-11-02T15:02:00Z',message:'Ready to inspect',username:'Peer',source:'agent'},
  {id:'action',kind:'action_failed',time:'2026-11-02T15:03:00Z',action:'move',error:'No path'}]}};
 const c=context({username:'One'},history,{ready:true,position:{x:1.1,y:64,z:5},health:20,inventory:[],players:[]});
 assert.equal(c.scope,'minecraft:workshop:One');assert.equal(c.task.remaining_turns,9);
 assert.deepEqual(c.events.map(e=>e.id),['new','action','environment:self','environment:peers']);
 assert.equal(c.events[0].kind,'message');assert.equal(c.events[1].kind,'tool');
 assert.equal(c.events[2].content.position.x,1);assert.ok(!JSON.stringify(c).includes('private'));
});
test('message envelope separates the speaker and first addressee from body mentions',()=>{
 const cfg={username:'Bea',bot_names:['Lena','Omar','Bea']};
 assert.deepEqual(messageEnvelope(cfg,{username:'Lena',message:'@Omar Please give supplies. Bea already delivered hers.'}),{author:'Lena',recipients:['Omar'],intent:'request'});
 assert.deepEqual(messageEnvelope(cfg,{username:'Omar',message:'@Bea [FYI] Three beds ready; I am gathering more wool.'}),{author:'Omar',recipients:['Bea'],intent:'update'});
 assert.deepEqual(messageEnvelope(cfg,{username:'Omar',message:'@Bea [ACK] Thanks.'}),{author:'Omar',recipients:['Bea'],intent:'ack'});
});
test('quoted/later mentions and public broadcasts are not invented recipients',()=>{
 const cfg={username:'Bea',bot_names:['Lena','Omar']};
 for(const message of ['Omar said "@Bea please help" yesterday.','Completed the review. @Bea may want the result.','Everyone, the review passed.']){
  const meta=messageEnvelope(cfg,{username:'Lena',message});assert.deepEqual(meta.recipients,[]);assert.equal(meta.intent,null);
 }
 assert.deepEqual(messageEnvelope({...cfg,aliases:{Omar:['om']}},{username:'Bea',message:'@om [FYI] Completed review.'}).recipients,['Omar']);
});
test('host message metadata enriches rather than rewrites legacy event content/cursor inputs',()=>{
 const e={id:'m',kind:'chat',time:'2026-11-03T17:00:00Z',username:'Lena',source:'agent',message:'@Omar Help Bea later; deliver supplies here.'};
 const c=context({username:'Bea',bot_names:['Lena','Omar']},{task:()=>null,data:{events:[e]}},{ready:false});
 assert.equal(c.events[0].id,'m');assert.equal(c.events[0].source,'Public agent report: Lena');
 assert.deepEqual(c.events[0].content,{time:e.time,text:e.message});assert.deepEqual(c.events[0].message.recipients,['Omar']);
});
test('environment facts use containing blocks including negative coordinates and aggregate inventory stacks',()=>{
 const c=context({username:'One'},{task:()=>null,data:{events:[]}},{ready:true,position:{x:-0.2,y:65,z:67.9},inventory:[{name:'oak_log',count:12},{name:'oak_log',count:8}],players:[{name:'Peer',position:{x:-3.5,y:64,z:2.9}}]});
 assert.deepEqual(c.events[0].content.position,{x:-1,y:65,z:67});assert.equal(c.events[0].content.inventory_counts.oak_log,20);
 assert.equal(c.events[1].content[0].position.x,-4);
});
