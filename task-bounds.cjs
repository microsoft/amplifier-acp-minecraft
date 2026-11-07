// Explicit assignment bounds. Missing/malformed legacy limits are never unlimited.
const finite=value=>({kind:'finite',value});
const unbounded=()=>({kind:'no_configured_bound'});
function validate(b){
 if(!b||typeof b!=='object'||Array.isArray(b))throw Error('Unknown assignment bound');
 if(b.kind==='no_configured_bound'&&Object.keys(b).length===1)return b;
 if(b.kind==='finite'&&Object.keys(b).length===2&&Number.isSafeInteger(b.value)&&b.value>=0)return b;
 throw Error('Invalid or contradictory assignment bound');
}
function get(task){
 if(!task)throw Error('No assignment bounds');
 if(!Number.isSafeInteger(task.turns)||task.turns<0)throw Error('Unknown consumed turns');
 if(task.bounds!==undefined){
  const b=task.bounds;
  if(!b||b.version!==1||Object.keys(b).sort().join(',')!=='deadline_ms,max_turns,version')throw Error('Unknown assignment bounds version');
  for(const [key,field] of [['deadline_ms','deadline'],['max_turns','max_turns']]){
   const x=validate(b[key]);
   if(x.kind==='finite'?task[field]!==x.value:Object.hasOwn(task,field))throw Error('Conflicting assignment bound');
  }
  return b;
 }
 return {version:1,deadline_ms:validate(finite(task.deadline)),max_turns:validate(finite(task.max_turns))};
}
function valid(task){try{get(task);return true;}catch{return false;}}
function remaining(task,now=Date.now()){
 const b=get(task);
 return {remaining_ms:b.deadline_ms.kind==='finite'?finite(Math.max(0,b.deadline_ms.value-now)):unbounded(),
  remaining_turns:b.max_turns.kind==='finite'?finite(Math.max(0,b.max_turns.value-task.turns)):unbounded()};
}
function below(bound,value){validate(bound);return bound.kind==='finite'&&bound.value<value;}
function timeLow(task,minimum=1,now=Date.now()){try{return below(remaining(task,now).remaining_ms,minimum);}catch{return true;}}
function turnsLow(task,minimum=1){try{return below(remaining(task).remaining_turns,minimum);}catch{return true;}}
function within(task,{now=Date.now(),currentTurn=false,minimumMs=1}={}){
 try{const b=get(task);return !timeLow(task,minimumMs,now)&&(b.max_turns.kind==='no_configured_bound'||task.turns+(currentTurn?0:1)<=b.max_turns.value);}catch{return false;}
}
function clamp(task,until){const b=get(task).deadline_ms;return b.kind==='finite'?Math.min(until,b.value):until;}
function set(task,deadline,maxTurns){
 task.bounds={version:1,deadline_ms:validate(deadline),max_turns:validate(maxTurns)};
 for(const [field,b] of [['deadline',deadline],['max_turns',maxTurns]]){if(b.kind==='finite')task[field]=b.value;else delete task[field];}
 return task;
}
function publicRemaining(task,now=Date.now()){
 if(!valid(task))return {bound_status:'unknown',remaining_ms:null,remaining_turns:null};
 const r=remaining(task,now);return Object.fromEntries(Object.entries(r).map(([k,v])=>[k,v.kind==='finite'?v.value:null]));
}
module.exports={valid,finite,unbounded,validate,get,remaining,below,timeLow,turnsLow,within,clamp,set,publicRemaining};
