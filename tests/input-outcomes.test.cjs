const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{randomUUID}=require('node:crypto');
const outcomes=require('../input-outcomes.cjs'),{WorkshopState}=require('../workshop-state.cjs');
function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'input-outcomes-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return new WorkshopState(path.join(dir,'workshop.json'));}
const publicReply=(h,text)=>h.record({kind:'chat_sent',time:new Date().toISOString(),provenance:'minecraft_public_chat',sent:text});
test('durable same-turn source sets, public responses and terminal survive rollover and restart without fulfillment',t=>{
 const h=fixture(t),ids=[randomUUID(),randomUUID()],other=randomUUID();h.data.inbox=ids.map(id=>({id}));
 assert.equal(outcomes.query(h.data,ids).outcomes[0].delivery,'queued');
 h.startTurn({requestIds:ids,activity:true});h.data.inbox=[];publicReply(h,'Here is what I saw.');h.finish();
 h.startTurn({requestIds:[other],activity:true});publicReply(h,'Unrelated later reply.');h.finish();
 for(let i=0;i<1100;i++)h.record({kind:'observation'});
 const loaded=new WorkshopState(h.file),before=fs.readFileSync(h.file,'utf8'),found=outcomes.query(loaded.data,ids);
 for(const r of found.outcomes){assert.equal(r.delivery,'terminal');assert.deepEqual(r.source_ids,ids);assert.equal(r.turn_task_id,null);assert.equal(r.responses.length,1);assert.equal(r.responses[0].text,'Here is what I saw.');assert.equal(r.completion,'not_established');}
 assert.equal(fs.readFileSync(h.file,'utf8'),before);assert.equal(loaded.data.task,null);
});
test('crash and Stop produce interrupted evidence, never automatic terminal success or source replay',t=>{
 const h=fixture(t),id=randomUUID();h.startTurn({requestIds:[id],activity:true});h.actionStarted('unknown-effect');
 const loaded=new WorkshopState(h.file),r=outcomes.query(loaded.data,[id]).outcomes[0];
 assert.equal(r.delivery,'interrupted');assert.equal(r.blocked_reason,'body_restarted');assert.equal(loaded.data.last_turn.actions[0].status,'pending');
 const next=randomUUID();loaded.startTurn({requestIds:[next],activity:true});loaded.stop({activity:true});
 const stopped=outcomes.query(loaded.data,[next]).outcomes[0];assert.equal(stopped.delivery,'interrupted');assert.equal(stopped.blocked_reason,'explicit_stop');
 loaded.startTurn({requestIds:[next],activity:true});publicReply(loaded,'Not reassociated');loaded.finish();
 assert.deepEqual(outcomes.query(loaded.data,[next]).outcomes[0],stopped);
});
test('private replies never enter outcome text; adjacent private or unrelated public speech cannot leak',t=>{
 const h=fixture(t),id=randomUUID();h.startTurn({requestIds:[id],activity:true});
 h.record({kind:'chat_sent',whisper:true,provenance:'minecraft_whisper',sent:'private secret',recipient:'Owner'});
 h.finish();publicReply(h,'Later unassociated public reply');
 const r=outcomes.query(h.data,[id]).outcomes[0];assert.deepEqual(r.responses,[]);assert.equal(r.private_responses_withheld,true);assert.ok(!JSON.stringify(r).includes('private secret'));
});
test('legacy admissions are not terminal proof; expired or missing input remains unknown without write',t=>{
 const h=fixture(t),id=randomUUID(),missing=randomUUID();h.data.last_turn={started_at:new Date().toISOString(),request_ids:[id],interrupted:false};h.save();
 const bytes=fs.readFileSync(h.file,'utf8'),r=outcomes.query(h.data,[id,missing]);
 assert.equal(r.outcomes[0].delivery,'admitted');assert.equal(r.outcomes[0].terminal_at,null);assert.equal(r.outcomes[0].reason,'terminal_not_retained');
 assert.equal(r.outcomes[1].delivery,'unknown');assert.equal(r.outcomes[1].reason,'not_retained');assert.equal(fs.readFileSync(h.file,'utf8'),bytes);
});
test('authority is linked by original source receipt, never latest task; blocked reason is captured',t=>{
 const h=fixture(t),id=randomUUID(),other=randomUUID();h.startTurn({requestIds:[id],activity:true});outcomes.blocked(h.data,'installation_chat_only');h.finish();
 h.data.task={id:'unrelated',status:'running'};h.data.task_authorizations=[{source:{id},operation:'accept',result:{task_id:'original',authority_revision:1}},{source:{id:other},operation:'amend',result:{task_id:'unrelated',authority_revision:9}}];
 const r=outcomes.query(h.data,[id]).outcomes[0];assert.equal(r.blocked_reason,'installation_chat_only');assert.deepEqual(r.task_authorizations,[{operation:'accept',task_id:'original',authority_revision:1}]);assert.equal(r.turn_task_id,null);
});
test('retention is bounded with active records pinned and omission explicit',()=>{
 const d={};let first,last;
 for(let i=0;i<510;i++){const id=randomUUID();first??=id;last=id;d.turn={request_ids:[id],started_at:new Date(i).toISOString()};outcomes.admit(d);if(i<509)outcomes.settle(d);}
 assert.equal(d.input_outcomes.length,500);assert.equal(outcomes.query(d,[first]).outcomes[0].delivery,'unknown');assert.equal(outcomes.query(d,[last]).outcomes[0].delivery,'admitted');
 for(let i=0;i<40;i++)outcomes.response(d,{kind:'chat_sent',id:String(i),time:new Date().toISOString(),provenance:'minecraft_public_chat',sent:'public'});
 const r=outcomes.query(d,[last]).outcomes[0];assert.equal(r.responses.length,32);assert.equal(r.responses_omitted,true);
});
test('query accepts only bounded distinct original UUIDs and exact parameter',()=>{
 const id=randomUUID();assert.deepEqual(outcomes.requestIds('/input-outcomes?ids='+id),[id]);
 for(const suffix of ['', '?ids=bad','?ids='+id+','+id,'?ids='+id+'&ids='+id,'?ids='+id+'&text=secret','?ids='+Array.from({length:17},randomUUID).join(',')])assert.throws(()=>outcomes.requestIds('/input-outcomes'+suffix));
});

test('oversized non-packet evidence is omitted explicitly, never clipped into a different utterance',t=>{
 const h=fixture(t),id=randomUUID();h.startTurn({requestIds:[id],activity:true});publicReply(h,'x'.repeat(241));h.finish();
 const r=outcomes.query(h.data,[id]).outcomes[0];assert.deepEqual(r.responses,[]);assert.equal(r.responses_omitted,true);
});
