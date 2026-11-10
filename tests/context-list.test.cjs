const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs');
const cfg={username:'Builder',conversation_id:'minecraft:one-world',context_grant:'shared-grant'};
const accesses=[{mode:'owner'},{mode:'grant',grant:'shared-grant'}];
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'minecraft-list-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 return new WorkshopState(path.join(dir,'workshop.json'));
}
test('LIST is bounded discovery, preserves expired recorded state, and points to READ',t=>{
 const s=fixture(t);
 s.data.task={id:'existing-task',status:'waiting',goal:'Long unrelated goal '.repeat(2000),turns:3,max_turns:8,deadline:1,
  progress:[{summary:'Detailed progress '.repeat(2000),observation:{private:'PRIVATE_OBSERVATION'}}],
  last_observed:{inventory:'CANONICAL_OBSERVATION'.repeat(2000)},authority:{secret:'PRIVATE_AUTHORITY'}};
 s.save();const before=fs.readFileSync(s.file,'utf8');
 for(const access of accesses){
  const result=s.query({operation:'list',access},cfg,{connected:true,busy:false,turn_active:false,position:{x:1,y:64,z:2},future_detail:'LIVE_DETAIL'.repeat(2000)});
  const item=result.items[0],encoded=JSON.stringify(result);
  assert.ok(Buffer.byteLength(encoded)<1500,`LIST grew to ${Buffer.byteLength(encoded)} bytes`);
  assert.deepEqual(item.read,{operation:'read',conversation_id:cfg.conversation_id});
  assert.equal(item.activity.connected,true);assert.equal(item.activity.busy,false);
  assert.deepEqual(Object.keys(item.activity.task).sort(),['id','limit_state','status']);
  assert.equal(item.activity.task.status,'waiting','status is recorded, not a fabricated completion/expiry reason');
  assert.equal(item.activity.task.limit_state.deadline.elapsed,true);assert.equal(item.activity.task.limit_state.turns.remaining,5);
  assert.equal(item.activity.task.limit_state.observed_at,result.observed_at);
  for(const omitted of ['PRIVATE_', 'CANONICAL_OBSERVATION','Long unrelated goal','Detailed progress','LIVE_DETAIL','position'])assert.ok(!encoded.includes(omitted));
 }
 assert.equal(fs.readFileSync(s.file,'utf8'),before);
 assert.equal(s.data.task.status,'waiting');
});
test('READ and orientation retain owner details and grant projection after compact discovery',t=>{
 const s=fixture(t);s.data.task={id:'task',goal:'Existing goal',status:'stopped',turns:2,max_turns:8,deadline:1,
  progress:[{summary:'Shared progress',observation:{private:'PRIVATE_PROGRESS'}}],last_observed:{private:'PRIVATE_OBSERVATION'},authority:{private:'PRIVATE_AUTHORITY'}};
 s.save();const before=fs.readFileSync(s.file,'utf8');
 for(const access of accesses){
  const item=s.query({operation:'list',access},cfg,{}).items[0];
  for(const operation of [item.read.operation,'orientation']){
   const result=s.query({operation,conversation_id:item.read.conversation_id,access},cfg,{position:{x:1,y:64,z:2}});
   assert.equal(result.current.activity.task.goal,'Existing goal');assert.equal(result.current.activity.task.progress[0].summary,'Shared progress');
   assert.deepEqual(result.current.activity.position,{x:1,y:64,z:2});
   if(access.mode==='owner')assert.deepEqual(result.current.activity.task.last_observed,s.data.task.last_observed);
   else assert.ok(!JSON.stringify(result).includes('PRIVATE_'));
  }
 }
 assert.equal(fs.readFileSync(s.file,'utf8'),before);
});
test('LIST keeps absent tasks and unknown observations distinct from false or exhausted',t=>{
 const s=fixture(t);
 const absent=s.query({operation:'list',access:accesses[0]},cfg,{}).items[0];
 assert.equal(absent.activity.task,null);
 assert.deepEqual(absent.activity,{connected:null,busy:null,turn_active:null,task:null});
 s.data.task={id:'unknown',status:'needs_review',progress:[],bounds:{deadline:{kind:'unknown'}}};s.save();
 const item=s.query({operation:'list',access:accesses[0]},cfg,{connected:'yes',busy:false}).items[0];
 assert.equal(item.activity.connected,null);assert.equal(item.activity.busy,false);
 assert.equal(item.activity.task.limit_state.deadline.kind,'unknown');assert.equal(item.activity.task.limit_state.deadline.elapsed,null);
 assert.equal(item.activity.task.limit_state.turns.kind,'unknown');assert.equal(item.activity.task.status,'needs_review');
});
test('compact discovery retains access and conversation isolation',t=>{
 const s=fixture(t);
 assert.throws(()=>s.query({operation:'list',access:{mode:'grant',grant:'other'}},cfg,{}));
 assert.throws(()=>s.query({operation:'list',access:accesses[0],conversation_id:'minecraft:other-world'},cfg,{}));
});
