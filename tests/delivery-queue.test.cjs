const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const {retireExpired}=require('../delivery-queue.cjs');
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'delivery-queue-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(dir,'workshop.json')),now=Date.now();h.data.inbox=[];
 h.data.task={id:'same-task',status:'needs_review',turns:31};h.data.last_turn={actions:[{id:'unknown-effect',status:'uncertain'}]};
 return {h,now,add(source,age,offer){const e=h.record({kind:'chat',source,time:new Date(now-age).toISOString(),message:'original source',accepted:true});
  const m={id:e.id,source,message:e.message,...(offer?{attention_offer:offer}:{})};h.data.inbox.push(m);h.save();return m;}};
}
test('eight expired peer deliveries cannot permanently occupy the inbox; restart preserves evidence and authority',t=>{
 const {h,now,add}=fixture(t),authority=JSON.stringify([h.data.task,h.data.last_turn]);
 const original=Array.from({length:8},()=>add('agent',7*3600000,{id:'offer',ticket:'old-ticket'}));
 assert.equal(h.data.inbox.length,8);
 assert.equal(retireExpired(h,h.data.inbox,now).retired,8);
 const loaded=new WorkshopState(h.file);
 assert.equal(loaded.data.inbox.length,0);assert.equal(JSON.stringify([loaded.data.task,loaded.data.last_turn]),authority);
 assert.deepEqual(loaded.data.delivery_retirements.map(r=>r.message),original);
 assert(loaded.data.delivery_retirements.every(r=>r.disposition==='undelivered'&&r.source.id===r.message.id));
 assert.equal(loaded.data.conversation_admissions,undefined);
 assert.equal(retireExpired(loaded,loaded.data.inbox,now).retired,0);
 add('human',0);assert.equal(h.data.inbox.length,1);
});
test('human sources, fresh peers, unknown timestamps and partial offers remain queued',t=>{
 const {h,now,add}=fixture(t),mixed={id:'mixed',ticket:'same'};
 add('human',7200000);add('agent',1);add('agent',7200000,mixed);add('human',7200000,mixed);
 h.data.inbox.push({id:'missing-source',source:'agent'});
 const before=JSON.stringify(h.data.inbox);assert.equal(retireExpired(h,h.data.inbox,now).retired,0);assert.equal(JSON.stringify(h.data.inbox),before);
});
test('no queue mutation during a turn and archive remains bounded without resetting sources',t=>{
 const {h,now,add}=fixture(t);add('agent',7200000);h.data.turn={request_ids:['active']};
 assert.equal(retireExpired(h,h.data.inbox,now).retired,0);h.data.turn=null;
 h.data.delivery_retirements=Array.from({length:64},(_,i)=>({id:i}));
 assert.equal(retireExpired(h,h.data.inbox,now).retired,1);assert.equal(h.data.delivery_retirements.length,64);
 assert.equal(h.data.events.length,1);
});
test('actual activity envelope expires by original observed time, never as human speech',t=>{
 const {h,now}=fixture(t),{ActivityParticipation}=require('../activity-participation.cjs');
 const activity=new ActivityParticipation(h,{username:'Fixture',human_engagement:{enabled:true,activity_scope:'conversation_only'}},{now:()=>now});
 activity.observe({uuid:'00000000-0000-4000-8000-000000000001',name:'Visitor',from:{x:0,y:0,z:0},to:{x:1,y:0,z:0},at:now});
 const p=activity.proposal();activity.apply({source_id:p.ids[0],signature:p.signature,action:'engage',offer:{id:'a',ticket:'t'}},h.data.inbox);
 assert.equal(retireExpired(h,h.data.inbox,now+119999).retired,0);
 assert.equal(retireExpired(h,h.data.inbox,now+120000).retired,1);
 assert.deepEqual(h.data.delivery_retirements[0].source,p.context.activities[0]);
 assert.equal(h.data.events.length,0);
});
