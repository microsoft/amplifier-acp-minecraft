// Explanations of existing movement guards, never permission to bypass them.
const {createHash}=require('node:crypto');
const {Vec3}=require('vec3');
const rules=[
 [/different_elevation/,'different_elevation','walk_only cannot change feet height. Inspect the actual feet position and floor; choose a same-height destination. Use normal navigation only if stairs/climbing fit the task.'],
 [/unsafe_start/,'unsafe_start','Inspect feet, head and floor. walk_only requires full flat footing; slabs, stairs and ladders need their appropriate navigation mode. Do not dig the block supporting a player.'],
 [/elevation changed/,'elevation_changed','Compare observed feet height with the intended level. Inspect the floor and adjacent steps/slabs or holes, then plan from the actual position; repeating the old target does not repair the route.'],
 [/footing or clearance changed|route changed/,'terrain_changed','Inspect the reported feet/head/floor and nearby obstacles. Re-plan from current terrain; another player may have changed the path.'],
 [/supporting a player/,'player_support','Stand on separately verified safe footing before digging. If another player is supported by this block, ask them to move; this guard must remain in force.'],
 [/Movement stalled|movement stalled/,'stalled','Inspect nearby players, closed doors and collision blocks. Try a shorter verified waypoint or wait for the obstruction to clear; do not repeat the identical path unchanged.'],
 [/no_path|NoPath/,'no_path','Use map and inspect to locate clearance or a safe adjacent standing cell, then plan_route. A failed search is not permission to jump, dig or remove player structures.'],
 [/search_limit|path_too_long/,'search_limit','Choose a nearer waypoint in loaded terrain and plan_route again. A bounded search is not proof that no route exists.'],
 [/unloaded/,'unloaded','The route includes unknown terrain. Inspect loaded surroundings and choose a nearer confirmed waypoint; do not assume unknown blocks are empty.'],
 [/arrival did not match|without reaching/,'arrival_mismatch','Use the returned current feet position. Inspect the intended feet/head/floor and plan a short exact-height route; the earlier movement did not prove arrival.'],
 [/Walk-only time limit/,'time_limit','Inspect the actual current position and completed progress before planning a shorter route. Do not replay the original route automatically.']
];
class RepairHints {
 constructor(){this.failures=new Map();}
 explain(bot,action,args,error){
  if(!['move','dig','place','build','gather','follow','craft'].includes(action))return null;
  const rule=rules.find(([pattern])=>pattern.test(error.message));if(!rule)return null;
  const position=bot.entity.position.clone(),feet=position.floored();
  const block=p=>{const b=bot.blockAt(p);return {position:p,name:b?.name||'unloaded',properties:b?.getProperties?.()||{}};};
  const target=[args.x,args.y,args.z].every(Number.isInteger)?new Vec3(args.x,args.y,args.z):null;
  const observed={position,feet:block(feet),head:block(feet.offset(0,1,0)),floor:block(feet.offset(0,-1,0)),
   ...(target?{target_feet:block(target),target_head:block(target.offset(0,1,0)),target_floor:block(target.offset(0,-1,0))}:{})};
  // Include observed geometry so a changed route resets the repetition signal.
  const fingerprint=createHash('sha256').update(JSON.stringify({code:rule[1],action,target,mode:args.mode,range:args.range,expected:args.expected,feet:observed.feet,head:observed.head,floor:observed.floor,target_feet:observed.target_feet,target_head:observed.target_head,target_floor:observed.target_floor})).digest('hex');
  const repeated=(this.failures.get(fingerprint)||0)+1;
  this.failures.delete(fingerprint);this.failures.set(fingerprint,repeated);
  if(this.failures.size>32)this.failures.delete(this.failures.keys().next().value);
  return {code:rule[1],same_observation_failures:repeated,observed,
   next_steps:[...(repeated>1?['Do not retry these unchanged arguments. Inspect and change the route or report the specific blocker.']:[]),rule[2]],
   scope:'Local loaded observations and repair suggestions only. No blocks changed, movement retried, or guard disabled by this diagnostic.'};
 }
}
module.exports={RepairHints};
