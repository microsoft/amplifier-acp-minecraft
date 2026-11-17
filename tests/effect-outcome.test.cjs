const test=require('node:test'),assert=require('node:assert/strict');
const outcome=require('../effect-outcome.cjs').create(),policy=require('../activity-policy.cjs');
test('only internal error identity carries evidence, never caller text or JSON',()=>{
 const error=Error('failed'),detail={kind:'settled_failed_movement',position:{x:1}};
 outcome.settled(error,detail);detail.position.x=5;
 assert.equal(outcome.get(error).position.x,1);
 assert.equal(outcome.get({...error,details:{settled_failure:detail}}),null);
 assert.equal(outcome.get(Error('failed')),null);
 assert.equal(require('../effect-outcome.cjs').create().get(error),null,'Evidence cannot cross action boundaries');
 const copy=outcome.get(error);copy.position.x=9;assert.equal(outcome.get(error).position.x,1);
});
test('old exact blockers remain visible beyond recent observation tail without changing history',()=>{
 const history={data:{last_turn:{started_at:'old',actions:[{id:'old',status:'uncertain'}]},events:[{kind:'action_started',action_id:'old',arguments:{x:1}},{kind:'action_failed',action_id:'old',error:'unknown'},...Array.from({length:100},()=>({kind:'chat'}))]}};
 const before=JSON.stringify(history);const result=policy.blockers(history);
 assert.equal(result[0].terminals[0].error,'unknown');assert.equal(result[0].start.arguments.x,1);assert.equal(JSON.stringify(history),before);
 assert.equal(policy.reason(history,{human_engagement:{enabled:true,task_optional:true}}),null,'This fixture is not an activity turn');
 history.data.last_turn.activity=true;assert.equal(policy.reason(history,{human_engagement:{enabled:true,task_optional:true}}),'unresolved_activity_effects');
});
