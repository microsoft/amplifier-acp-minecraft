const test=require('node:test'),assert=require('node:assert/strict'),policy=require('../activity-policy.cjs');
const cfg={human_engagement:{enabled:true,task_optional:true}};
function history(status='waiting'){return {data:{last_turn:{activity:true,started_at:new Date(Date.now()-600000).toISOString(),interrupted:false,actions:[],activity_report:{status,reported_at:new Date(Date.now()-300001).toISOString(),wait_for:'materials'}}}};}
test('settled waiting activity can reconsider without changing its original report or task',()=>{
 const h=history();h.data.task={id:'old',status:'blocked'};const before=JSON.stringify(h);
 assert.equal(policy.canContinue(h,cfg),true);assert.equal(JSON.stringify(h),before);
 h.data.last_turn.activity_report.reported_at=new Date().toISOString();assert.equal(policy.canContinue(h,cfg),false);
});
test('reconsideration preserves Stop, unknowns, review and installation policy',()=>{
 for(const status of ['blocked','review'])assert.equal(policy.canContinue(history(status),cfg),false);
 for(const change of [h=>h.data.activity_stop={at:1},h=>h.data.last_turn.interrupted=true,h=>h.data.last_turn.actions=[{status:'uncertain'}],h=>h.data.last_turn.actions=[{status:'pending'}],h=>h.data.last_turn.effect_review={future_work_only:true},h=>h.data.last_turn.activity_report.reported_at='invalid']){
  const h=history();change(h);assert.equal(policy.canContinue(h,cfg),false);
 }
 assert.equal(policy.canContinue(history(),{}),false);
});
