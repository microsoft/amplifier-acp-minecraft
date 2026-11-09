const test=require('node:test');const assert=require('node:assert/strict');
const bounds=require('../task-bounds.cjs');
const now=2000;
test('limit reporting distinguishes deadline, turns, both and neither at exact boundaries',()=>{
 for(const [deadline,turns,expired,reached] of [[2000,3,true,false],[2001,8,false,true],[1999,9,true,true],[2001,3,false,false]]){
  const task={status:'budget_exhausted',deadline,max_turns:8,turns};const before=JSON.stringify(task);
  const result=bounds.limitState(task,now);
  assert.equal(result.deadline.elapsed,expired);assert.equal(result.turns.reached,reached);
  assert.equal(result.turns.remaining,Math.max(0,8-turns));assert.equal(JSON.stringify(task),before);
 }
});
test('explicit unbounded limits are distinct from unknown and mixed bounds remain accurate',()=>{
 const t={turns:3};bounds.set(t,bounds.unbounded(),bounds.finite(8));
 let r=bounds.limitState(t,now);assert.equal(r.deadline.kind,'no_configured_bound');assert.equal(r.deadline.elapsed,false);assert.equal(r.turns.remaining,5);
 bounds.set(t,bounds.finite(1000),bounds.unbounded());r=bounds.limitState(t,now);
 assert.equal(r.deadline.elapsed,true);assert.equal(r.turns.kind,'no_configured_bound');assert.equal(r.turns.reached,false);
 for(const bad of [{turns:3},{...t,max_turns:9},{deadline:1000,max_turns:8,turns:-1}]){
  r=bounds.limitState(bad,now);assert.equal(r.deadline.kind,'unknown');assert.equal(r.deadline.elapsed,null);assert.equal(r.turns.reached,null);
 }
});
