const test=require('node:test'),assert=require('node:assert/strict');
const {ActionLease}=require('../action-lease.cjs');
function fixture(){let now=1000;const task={id:'same',status:'running',deadline:3600000,max_turns:135,turns:120};
 const turn={task_id:'same',actions:[],may_mutate:true};
 const lease=new ActionLease({now:()=>now});lease.begin(turn,task,true);
 return {lease,task,turn,advance:n=>now+=n,request:()=>({lease_id:lease.id,task_id:task.id})};}
test('hours of controller renewals retain exact task, turn and consumed limits',()=>{
 const f=fixture(),before=JSON.stringify(f.task),turnBefore=JSON.stringify(f.turn),id=f.lease.id;
 for(let i=0;i<100;i++){f.advance(30000);f.lease.renew(f.request(),f.task,f.turn);}
 assert.equal(f.lease.id,id);assert.equal(JSON.stringify(f.task),before);assert.equal(JSON.stringify(f.turn),turnBefore);
 assert.equal(f.lease.view(f.task).renewable,true);
});
test('renewals cannot exceed assignment deadline or revive an expired lease',()=>{
 const f=fixture();f.task.deadline=100000;f.lease.begin(f.turn,f.task,true);
 assert.equal(f.lease.until,100000);f.advance(50000);f.lease.renew(f.request(),f.task,f.turn);
 assert.equal(f.lease.until,100000);f.advance(49000);
 assert.throws(()=>f.lease.renew(f.request(),f.task,f.turn));
 const g=fixture();g.advance(240000);assert.throws(()=>g.lease.renew(g.request(),g.task,g.turn));
});
test('stale identity, changed grant/counter, Stop, and lost replies cannot renew wrong work',()=>{
 for(const change of [f=>f.task.id='new',f=>f.task.deadline++,f=>f.task.max_turns++,f=>f.task.turns++,f=>f.task.status='stopped',f=>f.lease.clear()]){
  const f=fixture(),r=f.request();change(f);assert.throws(()=>f.lease.renew(r,f.task,f.turn));
 }
 const f=fixture(),r=f.request();assert.throws(()=>f.lease.renew(r,f.task,{...f.turn}));
 f.advance(30000);const until=f.lease.renew(r,f.task,f.turn).expires_at;
 // Same authenticated lease renewal may be repeated, but never reserves work.
 assert.equal(f.lease.renew(r,f.task,f.turn).expires_at,until);assert.equal(f.task.turns,120);
 f.lease.begin(f.turn,f.task,true);assert.throws(()=>f.lease.renew(r,f.task,f.turn));
});
test('no task, expired task, peer-only post-task chat and legacy controller stay nonrenewable',()=>{
 for(const task of [null,{id:'old',status:'budget_exhausted',deadline:1,turns:1,max_turns:1}]){
  const lease=new ActionLease({now:()=>100});lease.begin({task_id:task?.id},task,true);
  assert.equal(lease.view(task).renewable,false);assert.throws(()=>lease.renew({lease_id:lease.id,task_id:task?.id},task,lease.turn));
 }
 const f=fixture();f.lease.begin(f.turn,f.task,false);assert.equal(f.lease.view(f.task).renewable,false);
});
