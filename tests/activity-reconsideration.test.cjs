const test=require('node:test'),assert=require('node:assert/strict'),policy=require('../activity-policy.cjs');
const cfg={human_engagement:{enabled:true,task_optional:true}};
function history(status='waiting'){return {data:{last_turn:{activity:true,started_at:new Date(Date.now()-600000).toISOString(),interrupted:false,actions:[],activity_report:{status,reported_at:new Date(Date.now()-300001).toISOString(),wait_for:'materials'}}}};}
test('settled waiting activity can reconsider without changing its original report or task',()=>{
 const h=history();h.data.task={id:'old',status:'blocked'};const before=JSON.stringify(h);
 assert.equal(policy.canContinue(h,cfg),true);assert.equal(JSON.stringify(h),before);
 h.data.last_turn.activity_report.reported_at=new Date().toISOString();assert.equal(policy.canContinue(h,cfg),false);
});
test('reconsideration preserves Stop, unknowns, review and installation policy',()=>{
 for(const status of ['review'])assert.equal(policy.canContinue(history(status),cfg),false);
 for(const change of [h=>h.data.activity_stop={at:1},h=>h.data.last_turn.interrupted=true,h=>h.data.last_turn.actions=[{status:'uncertain'}],h=>h.data.last_turn.actions=[{status:'pending'}],h=>h.data.last_turn.effect_review={future_work_only:true},h=>h.data.last_turn.activity_report.reported_at='invalid']){
  const h=history();change(h);assert.equal(policy.canContinue(h,cfg),false);
 }
 assert.equal(policy.canContinue(history(),{}),false);
});
for(const status of ['blocked',null])test(`settled ${status??'missing'} report allows fresh planning without rewriting receipts or task limits`,()=>{
 const h=history(status);if(status===null)delete h.data.last_turn.activity_report;
 h.data.task={id:'original',status:'budget_exhausted',turns:4,max_turns:4,deadline:1};
 h.data.last_turn.actions=[{id:'completed-once',status:'succeeded'}];
 const before=JSON.stringify(h);assert.equal(policy.canContinue(h,cfg),true);assert.equal(JSON.stringify(h),before);
 const fresh=history(status);fresh.data.last_turn.started_at=new Date().toISOString();
 if(status===null)delete fresh.data.last_turn.activity_report;else fresh.data.last_turn.activity_report.reported_at=new Date().toISOString();
 assert.equal(policy.canContinue(fresh,cfg),false);
 for(const change of [h=>h.data.activity_stop={at:1},h=>h.data.last_turn.interrupted=true,h=>h.data.last_turn.actions=[{id:'unknown',status:'uncertain'}],h=>h.data.last_turn.actions=[{id:'pending',status:'pending'}],h=>h.data.last_turn.effect_review={future_work_only:true}]){
  const held=structuredClone(h);change(held);const retained=JSON.stringify(held);assert.equal(policy.canContinue(held,cfg),false);assert.equal(JSON.stringify(held),retained);
 }
 assert.equal(policy.canContinue(h,{}),false);
});
