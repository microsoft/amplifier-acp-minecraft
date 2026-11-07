// Explanations of existing movement guards, never permission to bypass them.
const {createHash}=require('node:crypto');
const {Vec3}=require('vec3');
const rules=[
 [/Target is out of reach/,'out_of_reach','Use map and plan_route to choose a supported standing cell within reach. Verify arrival before retrying; changing the target coordinates without moving does not improve reach.'],
 [/Target is not empty/,'occupied_target','Inspect the existing target block. It may already match your intended result. Do not place again or remove it merely to repeat placement; preserve existing builds.'],
 [/Requested support face has no solid supporting block/,'missing_support','Inspect the neighbor on the opposite side of the selected support_face. Choose a confirmed solid support and an empty target. Do not repeat the same unsupported placement.'],
 [/Server refused to place|Placement mismatch/,'placement_unconfirmed','Placement was not confirmed. Inspect the target and inventory before another attempt. For solid blocks, stand outside the target cell and other players; air alone does not prove that placement space is free. Do not remove existing blocks or blindly repeat the request.'],
 [/non_level_start/,'non_level_start','Your actual feet are between full block levels. Inspect footprint support_contacts and adjacent slabs/stairs. If appropriate, use normal navigation to separately verified full footing, then re-plan walk_only. Do not dig supporting blocks or repeat the unchanged level-walking request.'],
 [/different_elevation/,'different_elevation','walk_only cannot change feet height. Inspect the actual feet position and floor; choose a same-height destination. Use normal navigation only if stairs/climbing fit the task.'],
 [/unsafe_start/,'unsafe_start','Inspect feet, head and floor. walk_only requires full flat footing; slabs, stairs and ladders need their appropriate navigation mode. Do not dig the block supporting a player.'],
 [/elevation changed/,'elevation_changed','Compare observed feet height with the intended level. Inspect footprint support_contacts and body_obstructions as well as the center floor: an edge can rest on a neighboring slab. Re-plan from the actual position; repeating the old target does not repair the route.'],
 [/footing or clearance changed|route changed/,'terrain_changed','Inspect the reported feet/head/floor and nearby obstacles. Re-plan from current terrain; another player may have changed the path.'],
 [/supporting a player/,'player_support','Stand on separately verified safe footing before digging. If another player is supported by this block, ask them to move; this guard must remain in force.'],
 [/Movement stalled|movement stalled/,'stalled','Inspect nearby players, closed doors and collision blocks. Try a shorter verified waypoint or wait for the obstruction to clear; do not repeat the identical path unchanged.'],
 [/no_path|NoPath/,'no_path','Use map and inspect to locate clearance or a safe adjacent standing cell, then plan_route. A failed search is not permission to jump, dig or remove player structures.'],
 [/search_limit|path_too_long|Took too? long to decide path to goal/,'search_limit','Inspect the current position first; the failed search may have included movement. Choose a nearer waypoint in loaded terrain and plan_route again. A bounded search is not proof that no route exists.'],
 [/unloaded/,'unloaded','The route includes unknown terrain. Inspect loaded surroundings and choose a nearer confirmed waypoint; do not assume unknown blocks are empty.'],
 [/arrival did not match|without reaching/,'arrival_mismatch','Use the returned current feet position. Inspect the intended feet/head/floor and plan a short exact-height route; the earlier movement did not prove arrival.'],
 [/Walk-only time limit/,'time_limit','Inspect the actual current position and completed progress before planning a shorter route. Do not replay the original route automatically.']
];
// Center-cell observations miss contacts along the player's edges. These are
// current loaded collision observations, not a claim about what caused motion.
function footprint(bot,position){
 const half=Number.isFinite(bot.physics?.playerHalfWidth)&&bot.physics.playerHalfWidth>0&&bot.physics.playerHalfWidth<=1?bot.physics.playerHalfWidth:Math.fround(.6)/2;
 const height=Number.isFinite(bot.entity.height)&&bot.entity.height>0&&bot.entity.height<=3?bot.entity.height:1.8;
 const support_contacts=[],body_obstructions=[],unknown=[];
 const minX=position.x-half,maxX=position.x+half,minZ=position.z-half,maxZ=position.z+half;
 for(let x=Math.floor(minX);x<=Math.floor(maxX);x++)for(let z=Math.floor(minZ);z<=Math.floor(maxZ);z++){
  // Fences may support the player above their nominal one-block cell.
  for(let y=Math.floor(position.y)-2;y<=Math.floor(position.y+height);y++){
   const p=new Vec3(x,y,z),b=bot.blockAt(p);
   if(!b||!Array.isArray(b.shapes)){unknown.push({position:p,reason:b?'collision_shapes_unavailable':'unloaded'});continue;}
   const support=[],obstructions=[];
   for(const s of b.shapes){
    if(!Array.isArray(s)||s.length!==6||!s.every(Number.isFinite))continue;
    if(x+s[0]>=maxX||x+s[3]<=minX||z+s[2]>=maxZ||z+s[5]<=minZ)continue;
    const top=y+s[4],bottom=y+s[1];
    if(Math.abs(top-position.y)<=.05)support.push(s);
    if(top>position.y+.05&&bottom<position.y+height)obstructions.push(s);
   }
   const item=shapes=>({position:p,name:b.name,properties:b.getProperties?.()||{},shapes});
   if(support.length)support_contacts.push(item(support));
   if(obstructions.length)body_obstructions.push(item(obstructions));
  }
 }
 return {half_width:half,height,support_contacts,body_obstructions,unknown,
  coverage:'Loaded block collision shapes overlapping the current player footprint. Contacts do not prove the cause of earlier movement or that a route is safe; unloaded/missing shape data remains unknown.'};
}
// Possible target-cell occupation, not prospective block collision geometry.
// Report observations only; partial/non-solid placements still use live rules.
function targetPlayers(bot,target){
 if(!target)return [];
 const entries=[{name:bot.username||'self',entity:bot.entity,self:true},
  ...Object.entries(bot.players||{}).filter(([,p])=>p.entity&&p.entity!==bot.entity).slice(0,32)
   .map(([name,p])=>({name,entity:p.entity,self:false}))];
 return entries.flatMap(({name,entity,self})=>{
  const p=entity.position;if(!p||![p.x,p.y,p.z].every(Number.isFinite))return [];
  const half=self&&Number.isFinite(bot.physics?.playerHalfWidth)&&bot.physics.playerHalfWidth>0&&bot.physics.playerHalfWidth<=1?bot.physics.playerHalfWidth:
   Number.isFinite(entity.width)&&entity.width>0&&entity.width<=2?entity.width/2:Math.fround(.6)/2;
  const height=Number.isFinite(entity.height)&&entity.height>0&&entity.height<=3?entity.height:1.8;
  return p.x+half>target.x&&p.x-half<target.x+1&&p.z+half>target.z&&p.z-half<target.z+1&&p.y+height>target.y&&p.y<target.y+1?
   [{name,self,position:{x:p.x,y:p.y,z:p.z},half_width:half,height}]:[];
 });
}
class RepairHints {
 constructor(){this.failures=new Map();}
 explain(bot,action,args,error){
  if(!['move','dig','place','build','gather','follow','craft'].includes(action))return null;
  const rule=rules.find(([pattern])=>pattern.test(error.message));if(!rule)return null;
  const position=bot.entity.position.clone(),feet=position.floored();
  const block=p=>{const b=bot.blockAt(p);return {position:p,name:b?.name||'unloaded',properties:b?.getProperties?.()||{}};};
  const target=[args.x,args.y,args.z].every(Number.isInteger)?new Vec3(args.x,args.y,args.z):null;
  const observed={position,feet:block(feet),head:block(feet.offset(0,1,0)),floor:block(feet.offset(0,-1,0)),footprint:footprint(bot,position),
   ...(target?{target_feet:block(target),target_head:block(target.offset(0,1,0)),target_floor:block(target.offset(0,-1,0)),target_player_overlaps:targetPlayers(bot,target)}:{})};
  // Include observed geometry so a changed route resets the repetition signal.
  const fingerprint=createHash('sha256').update(JSON.stringify({code:rule[1],action,target,mode:args.mode,range:args.range,expected:args.expected,feet:observed.feet,head:observed.head,floor:observed.floor,footprint:observed.footprint,target_feet:observed.target_feet,target_head:observed.target_head,target_floor:observed.target_floor,target_player_overlaps:observed.target_player_overlaps})).digest('hex');
  const repeated=(this.failures.get(fingerprint)||0)+1;
  this.failures.delete(fingerprint);this.failures.set(fingerprint,repeated);
  if(this.failures.size>32)this.failures.delete(this.failures.keys().next().value);
  return {code:rule[1],same_observation_failures:repeated,observed,
   next_steps:[...(repeated>1?['Do not retry these unchanged arguments. Inspect and change the route or report the specific blocker.']:[]),
    ...(action==='place'&&observed.target_player_overlaps?.length?['The target cell currently overlaps a player body. Choose separate supported footing outside the placement cell; these bounds are not proof of the exact cause or of future clearance.']:[]),rule[2]],
   scope:'Local loaded observations and repair suggestions only. No blocks changed, movement retried, or guard disabled by this diagnostic.'};
 }
}
module.exports={RepairHints};
