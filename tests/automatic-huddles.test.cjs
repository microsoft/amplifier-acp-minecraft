const test=require('node:test'),assert=require('node:assert/strict');
const {AutomaticHuddles,roomSource}=require('../automatic-huddles.cjs');
const {ConversationAdmission}=require('../conversation-admission.cjs');
const crypto=require('node:crypto'),id=()=>crypto.randomUUID();
const caps={version:1,external_participants:true,read:true,post:true,post_status:true,outcomes:true,quiet_follow:true,max_text_bytes:6000,max_evidence_items:8,max_metadata_bytes:8000,max_page_items:100};
function fixture(){
 const config={url:'https://rooms.test',token:'private-token-'.repeat(4),installation_id:'lead-install',agent_id:'lead',connection_id:'lead-game',conversation_id:'world',namespace:'pool'};
 const event={id:id(),time:new Date().toISOString(),kind:'chat',username:'Human',message:'Please compare',source:'human',accepted:true,provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',username:'Human',uuid:id()}};
 const history={data:{events:[event],inbox:[],task:{id:'old',status:'budget_exhausted',turns:8},turn:{request_ids:[event.id],conversation_only:true}},save(){this.saved=structuredClone(this.data);}};history.save();
 const own={id:config.installation_id,agent_id:'lead',connection_id:'lead-game',conversation_id:'world',namespace:'pool',service:'minecraft',enabled:true,availability:'unknown'};
 const peer={...own,id:'peer-install',agent_id:'peer',connection_id:'peer-game'};
 let requests=0,lose=false,descriptor;
 const transport={host:'https://rooms.test',roster:async()=>({version:1,installation:own,items:[peer],capabilities:{automatic:1}}),ensure:async payload=>{requests++;descriptor={...makeRoom(payload.origin),request_id:payload.request_id,status:"saved",reused:false,membership:"active"};if(lose)throw Error('lost');return descriptor;},ensureStatus:async()=>descriptor?{found:true,value:descriptor}:{found:false}};
 const manager=new AutomaticHuddles(history,config,{transport,canPost:()=>true});
 function makeRoom(origin){return {version:1,id:'room',conversation_id:'room',participant:{agent_id:'lead',connection_id:'lead-game'},participants:[{id:'lead'},{id:'peer'}],state:'open',revision:1,origin,inspect_url:'https://rooms.test/?conversation=room',capabilities:caps};}
 const args={request_id:id(),source_id:event.id,title:'Compare',purpose:'Inspect independently',peer_installation_ids:['peer-install']};
 return {manager,history,config,event,args,transport,makeRoom,peer,own,requests:()=>requests,lose:()=>{lose=true;}};
}
test('model ensure derives original source and creates dynamic binding without altering task or creating ACP session',async()=>{
 const f=fixture(),before=structuredClone(f.history.data.task);const r=await f.manager.ensure(f.args);
 assert.equal(r.state,'saved');assert.equal(r.room.origin.source_id,f.event.id);assert.equal(r.room.origin.actor.id,f.event.transport.uuid);assert.deepEqual(f.history.data.task,before);assert.equal(f.requests(),1);assert.equal(f.manager.state().rooms.room.membership,'active');
 assert.equal((await f.manager.ensure(f.args)).state,'saved');assert.equal(f.requests(),1);
});
test('lost ensure response/restart is status only, changed payload or alternative request cannot resend',async()=>{
 const f=fixture();f.lose();await assert.rejects(f.manager.ensure(f.args),/unknown/);assert.equal(f.requests(),1);
 await assert.rejects(f.manager.ensure({...f.args,request_id:id()}),/uncertain/);
 const again=new AutomaticHuddles(f.history,f.config,{transport:f.transport,canPost:()=>true});assert.equal((await again.ensure(f.args)).state,'saved');assert.equal(f.requests(),1);
 await assert.rejects(again.ensure({...f.args,title:'Different'}),/different payload/);
});
test('missing ensure status is unknown, not permission to submit again',async()=>{
 const f=fixture();f.transport.ensure=async()=>{throw Error('lost');};await assert.rejects(f.manager.ensure(f.args));assert.equal((await f.manager.ensureStatus(f.args.request_id)).state,'unknown');await assert.rejects(f.manager.ensure({...f.args,request_id:id()}),/uncertain/);
});
test('only a current retained public human source and approved roster peer can originate a room',async()=>{
 for(const change of ['private','peer','old','foreign-peer','namespace']){
  const f=fixture();if(change==='private')f.event.whisper=true;if(change==='peer')f.event.source='agent';if(change==='old')f.history.data.turn.request_ids=[];if(change==='foreign-peer')f.args.peer_installation_ids=['unknown'];if(change==='namespace')f.peer.namespace='other-world';
  await assert.rejects(f.manager.ensure(f.args));assert.equal(f.requests(),0);
 }
});
function message(){return {id:id(),seq:2,role:'assistant',actor:'Peer',agent_id:'peer',text:'I observed the east route.',status:'complete',created_at:Date.now(),target_agent_ids:['lead'],source:null,kind:'message',outcome:null};}
async function ingested(){const f=fixture();await f.manager.ensure(f.args);const m=message();f.manager.ingest('room',{items:[m],next_cursor:2});return {...f,m};}
test('room source and cursor are durable, distinct from game human input and deduplicated after restart',async()=>{
 const f=await ingested(),p=f.manager.proposal();assert.equal(p.context.conversation_id,'room');assert.equal(p.context.participants[1].is_agent,true);assert.equal(p.occurred_at,f.m.created_at);assert.equal(f.history.data.events.length,1);assert.equal(f.history.data.inbox.length,0);
 f.manager.ingest('room',{items:[f.m],next_cursor:2});assert.equal(f.manager.state().pending.length,1);
 const again=new AutomaticHuddles(f.history,f.config,{transport:f.transport,canPost:()=>true});assert.deepEqual(again.proposal(),p);
 assert.notEqual(roomSource(f.transport.host,'different',f.m).id,p.ids[0]);
});
test('existing admission receives truthful room source and keeps final speech private without granting work',async()=>{
 const f=await ingested(),p=f.manager.proposal();f.history.data.turn=null;const old=structuredClone(f.history.data.task);
 const applied=f.manager.apply({signature:p.signature,source_id:p.ids[0],action:'engage'},f.history.data.inbox);assert.equal(applied.acp_admitted,false);assert.equal(f.history.data.inbox[0].source,'huddle');
 const admission=new ConversationAdmission(f.history,{human_engagement:{enabled:true}});admission.huddleEligible=m=>f.manager.eligible(m);assert.deepEqual(admission.status(f.history.data.inbox).eligible_ids,p.ids);
 admission.start(p.ids,f.history.data.inbox);assert.equal(f.history.data.turn.huddle_room_id,'room');assert.equal(f.history.data.turn.explicit_speech,true);assert.equal(f.history.data.turn.task_id,null);assert.deepEqual(f.history.data.task,old);
 assert.throws(()=>f.manager.apply({signature:p.signature,source_id:p.ids[0],action:'engage'},f.history.data.inbox),/changed/);
});
test('host hold settles only original room source without inbox/authority mutation',async()=>{
 const f=await ingested(),p=f.manager.proposal(),old=structuredClone(f.history.data.task);f.manager.apply({signature:p.signature,source_id:p.ids[0],action:'hold'},f.history.data.inbox);assert.equal(f.manager.proposal(),null);assert.equal(f.history.data.inbox.length,0);assert.deepEqual(f.history.data.task,old);
});
test('failed durable queue save rolls back inbox and source, allowing truthful fresh status',async()=>{
 const f=await ingested(),p=f.manager.proposal();f.history.save=()=>{throw Error('disk');};assert.throws(()=>f.manager.apply({signature:p.signature,source_id:p.ids[0],action:'engage'},f.history.data.inbox),/disk/);assert.equal(f.history.data.inbox.length,0);assert.equal(f.manager.proposal().signature,p.signature);
});
test('Stop/revocation closes pending and queued room delivery; stale saved ensure cannot reopen it',async()=>{
 for(const revoked of [false,true]){
  const f=await ingested(),p=f.manager.proposal(),row=f.manager.state().rooms.room.descriptor;f.manager.apply({signature:p.signature,source_id:p.ids[0],action:'engage'},f.history.data.inbox);
  const queued=f.history.data.inbox[0];f.manager.observe({...row,state:revoked?'open':'stopped',revision:2},revoked?'revoked':'active');assert.equal(f.manager.eligible(queued),false);assert.equal(f.history.data.inbox.length,0);
  await f.manager.ensureStatus(f.args.request_id);assert.equal(f.manager.eligible(queued),false);assert.equal(f.requests(),1);
 }
});
test('unrelated targets and self posts do not become pending replies',async()=>{
 const f=fixture();await f.manager.ensure(f.args);f.manager.ingest('room',{items:[{...message(),target_agent_ids:['other']},{...message(),seq:3,agent_id:'lead'}],next_cursor:3});assert.equal(f.manager.proposal(),null);assert.equal(f.manager.state().rooms.room.cursor,3);
});
test('authenticated web-human room input preserves provenance and can reply without game attribution or task authority',async()=>{
 const f=fixture();await f.manager.ensure(f.args);f.history.data.turn=null;
 const before=structuredClone(f.history.data.task),events=structuredClone(f.history.data.events);
 const m={...message(),role:'user',actor:'browser-member-17',agent_id:null,text:'I joined here. What did you find?',created_at:1794310000123};
 f.manager.ingest('room',{items:[m],next_cursor:m.seq});
 const p=f.manager.proposal(),sender=p.context.participants[1];
 assert.equal(sender.id,'human:'+m.actor);assert.equal(sender.is_agent,false);
 assert.equal(p.context.messages[0].sender,sender.id);assert.deepEqual(p.context.messages[0].recipients,['lead']);
 assert.equal(p.occurred_at,m.created_at);assert.equal(p.sources[0].occurredAt,m.created_at);
 assert.notEqual(p.ids[0],f.event.id);assert.deepEqual(f.history.data.events,events);
 f.manager.apply({signature:p.signature,source_id:p.ids[0],action:'engage'},f.history.data.inbox);
 const queued=f.history.data.inbox[0];assert.equal(queued.room_actor_kind,'human');assert.equal(queued.source,'huddle');assert.equal(queued.transport,undefined);
 const admission=new ConversationAdmission(f.history,{human_engagement:{enabled:true},human_reply_turns_per_hour:0});
 admission.huddleEligible=m=>f.manager.eligible(m);
 assert.deepEqual(admission.status(f.history.data.inbox).eligible_ids,p.ids);
 admission.start(p.ids,f.history.data.inbox);
 assert.equal(f.history.data.turn.huddle_room_id,'room');assert.equal(f.history.data.turn.task_id,null);assert.equal(f.history.data.turn.may_mutate,false);
 assert.deepEqual(f.history.data.task,before);assert.deepEqual(f.history.data.events,events);
 await assert.rejects(f.manager.ensure({...f.args,request_id:id(),source_id:p.ids[0]}),/retained original human source/);
});
test('web-human message targeting another participant is not offered locally',async()=>{
 const f=fixture();await f.manager.ensure(f.args);
 const m={...message(),role:'user',agent_id:null,actor:'browser-member-17',target_agent_ids:['other']};
 f.manager.ingest('room',{items:[m],next_cursor:m.seq});assert.equal(f.manager.proposal(),null);assert.equal(f.manager.state().rooms.room.cursor,m.seq);
});
