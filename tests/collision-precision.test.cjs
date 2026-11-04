const test=require('node:test');
const assert=require('node:assert/strict');
const {Vec3}=require('vec3');
const {Physics,PlayerState}=require('prismarine-physics');
const data=require('minecraft-data')('1.21.1');
const Block=require('prismarine-block')('1.21.1');
const {alignPlayerCollision}=require('../spatial.cjs');

// A real simulated sprint-jump into the first block of a one-block rise.
// Check the result against the server's float EntityDimensions, not against
// the client's own narrower collision calculation.
function approach(axis,sign,origin,fix){
 const world={getBlock(p){
  p=p.floored();
  const wall=sign>0?p[axis]>=origin+1:p[axis]<origin;
  const b=Block.fromStateId(data.blocksByName[p.y<=0||(p.y===1&&wall)?'stone':'air'].defaultState);
  b.position=p;return b;
 }};
 const pos=new Vec3(.5,1,.5);pos[axis]+=origin;
 const velocity=new Vec3(0,0,0);velocity[axis]=.28*sign;
 const bot={version:'1.21.1',physics:Physics(data,world),jumpTicks:0,jumpQueued:false,fireworkRocketDuration:0,
  inventory:{slots:[]},entity:{position:pos,velocity,onGround:true,effects:{},
   yaw:axis==='x'?-sign*Math.PI/2:sign>0?Math.PI:0,pitch:0}};
 if(fix)alignPlayerCollision(bot);
 const state=new PlayerState(bot,{forward:true,back:false,left:false,right:false,jump:true,sprint:true,sneak:false});
 bot.physics.simulatePlayer(state,world);
 const halfServerWidth=Math.fround(.6)/2;
 return {edge:state.pos[axis]+sign*halfServerWidth,wall:origin+(sign>0?1:0),state};
}
test('sprint-jump collision agrees with server dimensions in every horizontal direction',()=>{
 for(const axis of ['x','z'])for(const sign of [-1,1])for(const origin of [0,-548,2048]){
  const before=approach(axis,sign,origin,false);
  assert.ok(sign*(before.edge-before.wall)>0,'original client overlaps the server block edge');
  const after=approach(axis,sign,origin,true);
  assert.ok(sign*(after.edge-after.wall)<=0,`server collision at ${axis} ${sign} ${origin}`);
  assert.ok(after.state.pos.y>1,'the ordinary jump remains possible');
 }
});
test('collision alignment preserves custom or already corrected dimensions',()=>{
 for(const width of [.4,Math.fround(.6)/2]){
  const bot={physics:{playerHalfWidth:width}};alignPlayerCollision(bot);assert.equal(bot.physics.playerHalfWidth,width);
 }
});
