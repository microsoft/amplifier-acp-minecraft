const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {Huddle}=require('../huddle.cjs'),{publicSource}=require('../source-revision.cjs');
const sha=v=>crypto.createHash('sha256').update(v).digest('hex');
const id='d68c0154-aea4-40a9-b4b7-83233ed02de9';
const caps={version:1,external_participants:true,read:true,post:true,post_status:true,outcomes:true,quiet_follow:true,max_text_bytes:6000,max_evidence_items:8,max_metadata_bytes:8000,max_page_items:100};
function fixture(){
 const event={id:'source',time:'2026-11-10T12:00:00.000Z',kind:'chat',source:'human',accepted:true,username:'Human',message:'Coordinate the check',provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',uuid:'human-uuid',username:'Human'}};
 const history={data:{events:[event],task:{id:'retained',status:'budget_exhausted',turns:8},inbox:[]},save(){}};
 const origin={kind:'external',service:'minecraft',connection_id:'game',conversation_id:'public-game',request_id:'original',source_id:event.id,source_revision:publicSource(event).revision,occurred_at:Date.parse(event.time),actor:{id:'human-uuid',kind:'human'}};
 const config={url:'https://room.test',room_id:'room',agent_id:'agent',connection_id:'game',conversation_id:'public-game',token:'t'.repeat(40),origin};
 const descriptor={version:1,id:'room',conversation_id:'room',participant:{agent_id:'agent',connection_id:'game'},state:'open',revision:1,origin,inspect_url:'https://room.test/?conversation=room',capabilities:{...caps},participants:[{id:'agent'},{id:'peer'}],purpose:'Check together'};
 const saved=new Map(),sent=[],f={history,config,descriptor,posts:0,allow:true,loseAck:false};
 const transport={host:'https://room.test',async descriptor(){return structuredClone(descriptor);},async messages(after){return {version:1,items:[{id:'peer-message',seq:after+1,role:'assistant',actor:'Peer',agent_id:'peer',text:'Checked',status:'complete',created_at:1,target_agent_ids:['agent'],source:null,kind:'message',outcome:null}],next_cursor:after+1,has_more:false,coverage:{after,through:after+1,complete_through_cursor:true},state:descriptor.state,revision:descriptor.revision};},async post(p){
  f.posts++;const r={version:1,status:'saved',message_id:p.request_id,request_id:p.request_id,room_id:'room',sequence:1,kind:p.kind,created_at:1,agent_id:'agent',connection_id:'game',origin,return:p.kind==='outcome'?{state:'available',delivery:'domain_owned'}:{state:'not_requested'},revision:sha(JSON.stringify(p)),text_sha256:sha(p.text),source:p.source,outcome:p.outcome,target_agent_ids:p.target_agent_ids,inspect_url:descriptor.inspect_url};saved.set(p.request_id,r);if(f.loseAck)throw Error('lost');return r;
 },async status(id){return saved.has(id)?{found:true,value:structuredClone(saved.get(id))}:{found:false};}};
 f.transport=transport;f.saved=saved;f.sent=sent;f.bridge=new Huddle(history,config,{transport,canPost:()=>f.allow,sendPublic:async args=>{sent.push(args);return {transport_submitted:true,recipient_delivery_verified:false,operation_id:'speech'};}});return f;
}
test('measured capabilities and exact installed participant/origin required before post',async()=>{
 for(const change of [d=>{delete d.capabilities.post_status;},d=>{d.capabilities.version=2;},d=>{d.participant.agent_id='other';},d=>{d.origin={...d.origin,request_id:'other'};},d=>{d.inspect_url='javascript:alert(1)';}]){
  const f=fixture();change(f.descriptor);await assert.rejects(f.bridge.post({request_id:id,text:'Check',kind:'message'}));assert.equal(f.posts,0);
 }
});
test('room read preserves actor/time/source and does not enqueue, claim work or public speech',async()=>{
 const f=fixture(),before=JSON.stringify(f.history.data),r=await f.bridge.read();assert.equal(r.items[0].agent_id,'peer');assert.equal(r.items[0].created_at,1);assert.equal(r.room.state,'open');assert.equal(JSON.stringify(f.history.data),before);assert.deepEqual(f.sent,[]);
});
test('lost ack and restart use original saved receipt without another post',async()=>{
 const f=fixture(),p={request_id:id,text:'Checked',kind:'message',source_id:'source'};f.loseAck=true;await assert.rejects(f.bridge.post(p),/unknown/);
 f.bridge=new Huddle(f.history,f.config,{transport:f.transport,canPost:()=>true});const r=await f.bridge.post(p);assert.equal(r.state,'saved');assert.equal(f.posts,1);assert.equal(r.receipt.source.occurred_at,f.config.origin.occurred_at);assert.equal(r.receipt.source.revision,f.config.origin.source_revision);
 await assert.rejects(f.bridge.post({...p,text:'Altered'}),/different payload/);assert.equal(f.posts,1);
});
test('reply addresses actual read actor explicitly; lost ack cannot change targets or broadcast',async()=>{
 const f=fixture(),task=JSON.stringify(f.history.data.task),page=await f.bridge.read();
 const reply={request_id:id,text:'Here is my check.',kind:'message',target_agent_ids:[page.items[0].agent_id]};
 f.loseAck=true;await assert.rejects(f.bridge.post(reply),/unknown/);
 const saved=await f.bridge.status(id);assert.equal(saved.state,'saved');assert.deepEqual(saved.receipt.target_agent_ids,['peer']);assert.equal(f.posts,1);
 await assert.rejects(f.bridge.post({...reply,target_agent_ids:[]}),/different payload/);assert.equal(f.posts,1);
 assert.equal(JSON.stringify(f.history.data.task),task);assert.deepEqual(f.sent,[]);
 const untargeted=fixture();await untargeted.bridge.read();const roomPost=await untargeted.bridge.post({request_id:id,text:'A room observation.'});
 assert.deepEqual(roomPost.payload.target_agent_ids,[]);assert.deepEqual(roomPost.receipt.target_agent_ids,[]);assert.equal(roomPost.receipt.return.state,'not_requested');
});
test('saved receipt tampering and absent status preserve unknown',async()=>{
 const f=fixture();await f.bridge.post({request_id:id,text:'Checked'});f.saved.get(id).text_sha256='wrong';await assert.rejects(f.bridge.status(id),/does not match/);
 f.saved.delete(id);assert.equal((await f.bridge.status(id)).state,'unknown');assert.equal(f.posts,1);
});
test('stopped room remains inspectable; unrelated task and later human reply authority are untouched',async()=>{
 const f=fixture(),before=JSON.stringify(f.history.data);f.descriptor.state='stopped';assert.equal((await f.bridge.read()).state,'stopped');await assert.rejects(f.bridge.post({request_id:id,text:'Continue'}),/stopped/);assert.equal(f.posts,0);assert.equal(JSON.stringify(f.history.data),before);
});
test('local turn ends during descriptor check: no post intent or transport',async()=>{
 const f=fixture();f.transport.descriptor=async()=>{f.allow=false;return f.descriptor;};await assert.rejects(f.bridge.post({request_id:id,text:'Continue'}),/current turn/);assert.equal(f.posts,0);assert.equal(f.history.data.huddle_operations,undefined);
});
test('meaningful exact original public outcome returns once, without consuming source or completing task',async()=>{
 const f=fixture(),task=JSON.stringify(f.history.data.task);await f.bridge.post({request_id:id,text:'The route is checked.',kind:'outcome',outcome:{kind:'result',evidence:[{label:'Walk receipt',reference:'operation:test'}]}});
 const r=await f.bridge.returnOutcome(id,'conversation-revision');assert.equal(r.state,'transport_submitted');assert.equal(r.read_by_human,null);assert.equal(r.work_completion,'not_established');assert.equal(f.sent.length,1);assert.ok(f.sent[0].text.endsWith(f.descriptor.inspect_url));assert.equal(f.sent[0].conversation_revision,'conversation-revision');
 assert.equal((await f.bridge.returnOutcome(id,'conversation-revision')).duplicate,true);assert.equal(f.sent.length,1);assert.equal(JSON.stringify(f.history.data.task),task);assert.deepEqual(f.history.data.inbox,[]);
});
test('uncertain public return is never resent and private source cannot become public return',async()=>{
 const f=fixture();await f.bridge.post({request_id:id,text:'Checked',kind:'outcome',outcome:{kind:'result'}});f.bridge.sendPublic=async()=>{f.sent.push('attempt');throw Error('lost speech');};await assert.rejects(f.bridge.returnOutcome(id,'revision'));
 assert.equal((await f.bridge.returnOutcome(id,'revision')).state,'unknown');assert.equal(f.sent.length,1);
 f.history.data.events[0].whisper=true;await assert.rejects(f.bridge.returnOutcome(id,'revision'),/source/);assert.equal(f.sent.length,1);
});
test('missing or stale public revision is a no-effect rejection, not an uncertain speech reservation',async()=>{
 const f=fixture();await f.bridge.post({request_id:id,text:'Checked',kind:'outcome',outcome:{kind:'result'}});
 await assert.rejects(f.bridge.returnOutcome(id),/conversation_revision/);assert.equal(f.bridge.journal.read(id).public_return,undefined);
 f.bridge.validatePublic=()=>{throw Error('Conversation changed');};await assert.rejects(f.bridge.returnOutcome(id,'stale'),/Conversation changed/);assert.equal(f.bridge.journal.read(id).public_return,undefined);assert.equal(f.sent.length,0);
 f.bridge.validatePublic=()=>{};await f.bridge.returnOutcome(id,'fresh');assert.equal(f.sent.length,1);
});
test('post metadata and byte bounds, target membership and actor spoof reject without transport',async()=>{
 for(const a of [{text:'😀'.repeat(1600)},{target_agent_ids:['absent']},{actor:{id:'human'}},{outcome:{kind:'result'}},{kind:'outcome',outcome:{kind:'result',evidence:[{label:'x',reference:'x'.repeat(1001)}]}}]){const f=fixture();await assert.rejects(f.bridge.post({request_id:id,text:'Check',...a}));assert.equal(f.posts,0);}
});
module.exports={fixture};
