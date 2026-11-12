// Refuse another identical, already-proven precondition failure. This is not
// an uncertain-effect retry policy and never retries or changes task authority.
const {createHash}=require('node:crypto');
const {Vec3}=require('vec3');
const proven=/^(Target is not empty|Dig target mismatch:|Target is out of reach; plan a safe standing position first|Requested support face has no solid supporting block|Refusing to remove a block supporting a player|No walk-only route \((?:unsafe_start|non_level_start|different_elevation)\))/;
const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
function observation(bot,args){
 const p=bot.entity.position;
 const cells=[];
 for(const center of [p.floored(),new Vec3(args.x,args.y,args.z)]){
  for(const d of [[0,0,0],[0,1,0],[0,-1,0],[1,0,0],[-1,0,0],[0,0,1],[0,0,-1]]){
   const at=center.offset(...d),b=bot.blockAt(at);
   cells.push({at,name:b?.name??null,properties:b?.getProperties?.()??null,shapes:b?.shapes??null});
  }
 }
 return {position:{x:Math.round(p.x*100)/100,y:Math.round(p.y*100)/100,z:Math.round(p.z*100)/100},cells,
  inventory:(bot.inventory?.items()||[]).map(i=>({name:i.name,count:i.count,type:i.type,metadata:i.metadata})),
  players:Object.values(bot.players||{}).filter(v=>v.entity?.position).map(v=>({name:v.username,position:v.entity.position}))};
}
class RetryGuard{
 constructor(){this.failures=new Map();}
 key(action,args){return digest({action,args:Object.fromEntries(Object.entries(args).sort(([a],[b])=>a.localeCompare(b)))});}
 eligible(action,args){return ['move','dig','place'].includes(action)&&[args.x,args.y,args.z].every(Number.isInteger);}
 failed(bot,action,args,error){
  if(!this.eligible(action,args)||!proven.test(error.message))return;
  const key=this.key(action,args),state=digest(observation(bot,args)),previous=this.failures.get(key);
  this.failures.delete(key);this.failures.set(key,{state,count:previous?.state===state?previous.count+1:1,error:error.message});
  if(this.failures.size>32)this.failures.delete(this.failures.keys().next().value);
 }
 check(bot,action,args){
  if(!this.eligible(action,args))return;
  const previous=this.failures.get(this.key(action,args));
  if(!previous||previous.count<2||previous.state!==digest(observation(bot,args)))return;
  const error=Error('Unchanged failed action blocked before execution. Choose a different supported standing position/target using map, inspect and plan_route, or report the blocker. Reading alone does not repair unchanged terrain.');
  error.details={retry_guard:{code:'unchanged_precondition',prior_failures:previous.count,prior_error:previous.error,effect_attempted:false,
   scope:'Same arguments, observed local/target geometry, player positions and inventory. No action retried or authority changed; original live guards still apply to a different plan.'}};
  throw error;
 }
}
module.exports={RetryGuard};
