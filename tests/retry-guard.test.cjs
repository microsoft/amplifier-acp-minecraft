const test=require('node:test'),assert=require('node:assert/strict');
const {Vec3}=require('vec3'),{RetryGuard}=require('../retry-guard.cjs');
test('unchanged observed dig mismatch refuses repetition but changed terrain permits a fresh check',()=>{
 const {bot,blocks}=fixture(),g=new RetryGuard(),a={x:2,y:64,z:0,expected:'stone'},e=Error('Dig target mismatch: expected stone, observed air at (2, 64, 0); inspect the actual block before digging.');
 blocks.set('(2, 64, 0)','air');g.failed(bot,'dig',a,e);g.failed(bot,'dig',a,e);
 assert.throws(()=>g.check(bot,'dig',a),/Unchanged failed action/);g.check(bot,'inspect',a);
 blocks.set('(2, 64, 0)','stone');g.check(bot,'dig',a);
});
function fixture(){const blocks=new Map();const bot={entity:{position:new Vec3(.5,64,.5)},inventory:{items:()=>[{name:'oak_planks',count:4}]},players:{},blockAt:p=>({name:blocks.get(p.toString())||'stone',getProperties:()=>({}),shapes:[[0,0,0,1,1,1]]})};return {bot,blocks};}
test('two identical known preconditions block the next execution, not authority or read tools',()=>{
 const {bot}=fixture(),guard=new RetryGuard(),args={x:2,y:64,z:0,item:'oak_planks'},error=Error('Target is not empty');
 guard.check(bot,'place',args);guard.failed(bot,'place',args,error);guard.check(bot,'place',args);guard.failed(bot,'place',args,error);
 assert.throws(()=>guard.check(bot,'place',args),e=>e.details.retry_guard.effect_attempted===false&&e.details.retry_guard.prior_failures===2);
 guard.check(bot,'inspect',args);guard.check(bot,'plan_route',args);guard.check(bot,'place',{...args,z:1});
});
test('moving, changing terrain, inventory or a supporting player permits fresh live checks',()=>{
 for(const change of [f=>f.bot.entity.position=new Vec3(1.5,64,.5),f=>f.blocks.set('(2, 64, 0)','air'),f=>f.bot.inventory.items=()=>[],f=>f.bot.players.Helper={username:'Helper',entity:{position:new Vec3(3,64,0)}}]){
  const f=fixture(),g=new RetryGuard(),a={x:2,y:64,z:0};g.failed(f.bot,'dig',a,Error('Refusing to remove a block supporting a player'));g.failed(f.bot,'dig',a,Error('Refusing to remove a block supporting a player'));change(f);g.check(f.bot,'dig',a);
 }
});
test('unknown, timed-out and partially settled failures never become retry permission or deterministic matches',()=>{
 const {bot}=fixture(),g=new RetryGuard(),a={x:2,y:64,z:0};
 for(const message of ['connection closed','Operation timed out','Movement stalled','Block update not confirmed'])for(let i=0;i<4;i++)g.failed(bot,'move',a,Error(message));
 assert.equal(g.failures.size,0);g.check(bot,'move',a);
});
test('changed arguments and changed observed geometry reset repeated-failure counts',()=>{
 const {bot,blocks}=fixture(),g=new RetryGuard(),a={x:2,y:64,z:0,mode:'walk_only'},e=Error('No walk-only route (unsafe_start)');
 g.failed(bot,'move',a,e);g.failed(bot,'move',a,e);g.check(bot,'move',{...a,mode:'normal'});
 blocks.set('(0, 63, 0)','oak_slab');g.failed(bot,'move',a,e);g.check(bot,'move',a);
});
