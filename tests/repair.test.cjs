const test=require('node:test'),assert=require('node:assert/strict');
const {Vec3}=require('vec3'),{RepairHints}=require('../repair.cjs');
function fixture(){let floor='stone';const bot={entity:{position:new Vec3(.5,64,.5)},blockAt:p=>({name:p.y===63?floor:'air',getProperties:()=>({})})};
 return {bot,setFloor:v=>{floor=v;}};}
test('repeated elevation guards give observed geometry and a changed-route remedy',()=>{
 const f=fixture(),hints=new RepairHints(),args={x:3,y:64,z:0,mode:'walk_only'},error=Error('Walk-only elevation changed; movement stopped. Inspect current footing.');
 const first=hints.explain(f.bot,'move',args,error),second=hints.explain(f.bot,'move',args,error);
 assert.equal(first.code,'elevation_changed');assert.equal(first.same_observation_failures,1);assert.equal(second.same_observation_failures,2);
 assert.equal(second.observed.floor.name,'stone');assert.match(second.next_steps[0],/Do not retry/);
 f.setFloor('oak_slab');assert.equal(hints.explain(f.bot,'move',args,error).same_observation_failures,1);
});
test('a different-elevation hint preserves walk-only constraint and unknown failures remain unknown',()=>{
 const {bot}=fixture(),hints=new RepairHints();
 const r=hints.explain(bot,'move',{x:2,y:63,z:0},Error('No walk-only route (different_elevation)'));
 assert.match(r.next_steps.join(' '),/only if stairs\/climbing fit the task/);assert.match(r.scope,/No blocks changed/);
 assert.equal(hints.explain(bot,'move',{},Error('Some unknown driver failure')),null);
});
test('player footing and arrival failures have specific repair suggestions without performing actions',()=>{
 const {bot}=fixture(),hints=new RepairHints();
 assert.equal(hints.explain(bot,'dig',{x:0,y:63,z:0},Error('Refusing to remove a block supporting a player')).code,'player_support');
 const r=hints.explain(bot,'place',{x:3,y:65,z:0},Error('Movement ended without reaching the requested destination'));
 assert.equal(r.code,'arrival_mismatch');assert.equal(r.observed.target_floor.position.y,64);
});
