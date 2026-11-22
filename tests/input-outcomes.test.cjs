const test=require('node:test'),assert=require('node:assert/strict');
const outcomes=require('../input-outcomes.cjs'),{randomUUID}=require('node:crypto');
const resumption=(id,task_id='original')=>({request_id:id,task_id,source:{id,message:'private original instruction'},arguments_hash:'retained',result:{task_id,status:'running',scheduled:true,execution_started:false}});

test('retained resumption does not fabricate evicted admission, terminal, or execution',()=>{
 const id=randomUUID(),d={work_resumptions:[resumption(id)]},r=outcomes.query(d,[id]).outcomes[0];
 assert.equal(r.delivery,'unknown');assert.equal(r.reason,'not_retained');assert.equal(r.terminal_at,null);assert.equal(r.conversation_only,null);
 assert.equal(r.work_resumptions.length,1);assert.equal(r.work_resumptions[0].execution_started,false);assert.equal(r.completion,'not_established');
});
test('resumption evidence requires matching original request, source and task result',()=>{
 const id=randomUUID(),other=randomUUID(),rows=[{...resumption(id),source:{id:other}},{...resumption(other),source:{id}}, {...resumption(id),result:{...resumption(id).result,task_id:'different'}},{...resumption(id),result:{task_id:'original',status:'running'}}];
 const d={work_resumptions:rows},before=JSON.stringify(d),r=outcomes.query(d,[id]).outcomes[0];
 assert.deepEqual(r.work_resumptions,[]);assert.equal(r.work_resumptions_omitted,true);assert.equal(JSON.stringify(d),before);
});
test('resumption projection is bounded with omission explicit and canonical receipts retained',()=>{
 const id=randomUUID(),d={work_resumptions:Array.from({length:20},(_,i)=>resumption(id,`task-${i}`))},before=JSON.stringify(d),r=outcomes.query(d,[id]).outcomes[0];
 assert.equal(r.work_resumptions.length,16);assert.equal(r.work_resumptions[0].task_id,'task-4');assert.equal(r.work_resumptions_omitted,true);assert.equal(JSON.stringify(d),before);
});
