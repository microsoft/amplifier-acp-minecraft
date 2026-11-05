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
function edgeFixture(){
 const blocks=new Map(),reads=[];
 const air={name:'air',shapes:[],getProperties:()=>({})};
 const bot={entity:{position:new Vec3(-466.7474,71.5,-596.7154),height:1.8},physics:{playerHalfWidth:Math.fround(.6)/2},
  blockAt:p=>{reads.push(p);return blocks.has(p.toString())?blocks.get(p.toString()):air;}};
 const set=(x,y,z,b)=>blocks.set(new Vec3(x,y,z).toString(),b);
 set(-467,70,-597,{name:'grass_block',shapes:[[0,0,0,1,1,1]],getProperties:()=>({snowy:false})});
 set(-467,71,-598,{name:'oak_slab',shapes:[[0,0,0,1,.5,1]],getProperties:()=>({type:'bottom'})});
 return {bot,set,reads};
}
test('edge support explains fractional elevation even when the center feet cell is air',()=>{
 const {bot,reads}=edgeFixture(),hints=new RepairHints();
 const r=hints.explain(bot,'move',{x:-468,y:71,z:-597,mode:'walk_only'},Error('Walk-only elevation changed'));
 assert.equal(r.observed.feet.name,'air');assert.equal(r.observed.floor.name,'grass_block');
 assert.deepEqual(r.observed.footprint.support_contacts.map(b=>({name:b.name,position:b.position,shapes:b.shapes})),[
  {name:'oak_slab',position:new Vec3(-467,71,-598),shapes:[[0,0,0,1,.5,1]]}
 ]);
 assert.equal(r.observed.footprint.body_obstructions.length,0);assert.equal(r.observed.footprint.unknown.length,0);
 assert.match(r.next_steps.join(' '),/support_contacts/);assert.match(r.observed.footprint.coverage,/do not prove/);
 assert.ok(reads.length<=30,'diagnostic stays local and bounded');
});
test('footprint observations distinguish obstacles, unknown cells and changed support',()=>{
 const {bot,set}=edgeFixture(),hints=new RepairHints(),args={x:-468,y:71,z:-597,mode:'walk_only'},error=Error('Walk-only elevation changed');
 hints.explain(bot,'move',args,error);assert.equal(hints.explain(bot,'move',args,error).same_observation_failures,2);
 set(-467,71,-598,{name:'oak_slab',shapes:[[0,0,0,1,1,1]],getProperties:()=>({type:'double'})});
 set(-467,72,-597,null);
 const r=hints.explain(bot,'move',args,error);
 assert.equal(r.same_observation_failures,1);assert.equal(r.observed.footprint.support_contacts.length,0);
 assert.equal(r.observed.footprint.body_obstructions[0].name,'oak_slab');
 assert.equal(r.observed.footprint.unknown[0].reason,'unloaded');
 assert.deepEqual(r.observed.footprint.unknown[0].position,new Vec3(-467,72,-597));
});
test('non-level starts get an explicit remedy and shape-less blocks stay unknown',()=>{
 const {bot}=fixture();bot.entity.position.y=64.5;
 const r=new RepairHints().explain(bot,'move',{x:2,y:64,z:0,mode:'walk_only'},Error('No walk-only route (non_level_start)'));
 assert.equal(r.code,'non_level_start');assert.match(r.next_steps.join(' '),/separately verified full footing/);
 assert.ok(r.observed.footprint.unknown.some(b=>b.reason==='collision_shapes_unavailable'));
 assert.equal(r.observed.footprint.support_contacts.length,0);
});
