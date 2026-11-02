const test=require('node:test'),assert=require('node:assert/strict');
const {Vec3}=require('vec3');const walking=require('../walking.cjs');
const full={name:'stone',boundingBox:'block',shapes:[[0,0,0,1,1,1]]},air={name:'air',boundingBox:'empty',shapes:[]};
function world(rows){
 return {entity:{position:new Vec3(.5,1,.5)},blockAt(p){
  if(!rows[p.z]?.[p.x])return full;
  if(p.y===0)return full;if(p.y===1&&rows[p.z][p.x]==='#')return full;
  return air;
 }};
}
test('walk-only route goes around a one-block wall without diagonal shortcuts',()=>{
 const bot=world(['.#.','.#.','...']),r=walking.plan(bot,new Vec3(2,1,0));assert.equal(r.status,'success');
 assert.equal(r.steps.length,7);
 r.steps.forEach((p,i)=>{assert.equal(p.y,1);if(i){const q=r.steps[i-1];assert.equal(Math.abs(p.x-q.x)+Math.abs(p.z-q.z),1);}});
});
test('walk-only rejects corner crossing, changed elevation, holes and partial footing',()=>{
 const bot=world(['.#','#.']);assert.equal(walking.plan(bot,new Vec3(1,1,1)).reachable,false);
 assert.equal(walking.plan(bot,new Vec3(0,2,0)).status,'different_elevation');
 const original=bot.blockAt;bot.blockAt=p=>p.y===0?air:original(p);assert.equal(walking.plan(bot,new Vec3(0,1,0)).status,'unsafe_start');
 bot.blockAt=p=>p.y===0?{...full,shapes:[[0,0,0,1,.5,1]]}:air;assert.equal(walking.walkable(bot,new Vec3(0,1,0)),false);
});
test('bounded and unloaded searches report their limited coverage',()=>{
 const bot=world(['.....']);assert.equal(walking.plan(bot,new Vec3(4,1,0),0,{maxNodes:2}).status,'search_limit');
 bot.blockAt=p=>p.x===1?null:p.y===0?full:air;assert.equal(walking.plan(bot,new Vec3(1,1,0),0,{radius:1}).reachable,false);
});
function moving(){
 const bot=world(['....']),controls={},calls=[];bot.pathfinder={setGoal(){}};bot.clearControlStates=()=>{for(const k of Object.keys(controls))controls[k]=false;};
 bot.setControlState=(k,v)=>{controls[k]=v;calls.push([k,v]);};bot.look=async yaw=>{bot.yaw=yaw;};
 const wait=async()=>{if(controls.forward)bot.entity.position=bot.entity.position.offset(-Math.sin(bot.yaw)*.1,0,-Math.cos(bot.yaw)*.1);};
 return {bot,controls,calls,wait};
}
test('walk-only executes and records actual height without requesting a jump',async()=>{
 const {bot,controls,calls,wait}=moving(),result=await walking.move(bot,new Vec3(3,1,0),0,()=>{},{wait});
 assert.equal(result.reached,true);assert.equal(result.observation.min_feet_y,1);assert.equal(result.observation.max_feet_y,1);
 assert.ok(!calls.some(([k,v])=>['jump','sprint'].includes(k)&&v));assert.ok(Object.values(controls).every(v=>!v));
});
test('Stop and newly obstructed routes release walking controls',async()=>{
 for(const cancel of [true,false]){
  const {bot,controls,wait}=moving();let ticks=0;const original=bot.blockAt;
  const check=()=>{if(cancel&&ticks>2)throw Error('Action cancelled');};
  const tick=async()=>{await wait();ticks++;if(!cancel&&ticks>2)bot.blockAt=p=>p.x===1&&p.y===1?full:original(p);};
  await assert.rejects(walking.move(bot,new Vec3(3,1,0),0,check,{wait:tick}),cancel?/cancelled/:/route changed/);
  assert.ok(Object.values(controls).every(v=>!v));
 }
});
test('unexpected vertical movement never reports a successful walk',async()=>{
 const {bot,controls,wait}=moving();const tick=async()=>{await wait();bot.entity.position.y+=.5;};
 await assert.rejects(walking.move(bot,new Vec3(3,1,0),0,()=>{},{wait:tick}),/elevation changed/);
 assert.ok(Object.values(controls).every(v=>!v));
});
