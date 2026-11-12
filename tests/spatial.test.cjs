const test=require('node:test');const assert=require('node:assert/strict');const {Vec3}=require('vec3');
const {FeetGoal,cell,footing,digGuard,harvestTool}=require('../spatial.cjs');
test('horizontal tolerance never accepts the wrong elevation',()=>{
 const goal=new FeetGoal(1,64,1,1);assert.ok(goal.isEnd(new Vec3(2,64,1)));assert.ok(!goal.isEnd(new Vec3(1,63,1)));assert.ok(!goal.isEnd(new Vec3(1,65,1)));
});
function world(blocks){return {blockAt:p=>blocks[`${p.x},${p.y},${p.z}`]||{name:'air',boundingBox:'empty'},entity:{position:new Vec3(0.5,1,0.5)},players:{}};}
test('map distinguishes footing, overhead obstruction, holes, water and unknown',()=>{
 const bot=world({'0,0,0':{name:'stone',boundingBox:'block'}}),p=new Vec3(0,1,0);assert.equal(cell(bot,p),'.');
 assert.equal(cell(bot,new Vec3(1,1,0)),'o');
 assert.equal(cell(world({'0,2,0':{name:'stone',boundingBox:'block'}}),p),'#');
 assert.equal(cell(world({'0,0,0':{name:'water',boundingBox:'empty'}}),p),'~');
 assert.equal(cell({blockAt:()=>null},p),'?');
});
test('digging protects own and another player footing',()=>{
 assert.ok(footing(new Vec3(0,0,0),[new Vec3(.5,1,.5)]));
 assert.ok(footing(new Vec3(1,0,0),[new Vec3(.85,1,.5)]));
 assert.ok(footing(new Vec3(0,0,0),[new Vec3(.5,.5,.5)]));
 const b=world({});b.players.Other={entity:{position:new Vec3(2.5,3,2.5)}};
 for(const p of [new Vec3(0,0,0),new Vec3(2,2,2)])assert.throws(()=>digGuard(b,{position:p,name:'dirt'}),/supporting/);
});
test('harvesting refuses missing tools and selects a tool that produces drops',()=>{
 const block={name:'coal_ore',canHarvest:t=>t===2};const bot={pathfinder:{bestHarvestTool:()=>({type:1,name:'axe'})},inventory:{items:()=>[{type:1},{type:2,name:'pickaxe'}]}};
 assert.equal(harvestTool(bot,block).name,'pickaxe');bot.inventory.items=()=>[{type:1}];assert.throws(()=>harvestTool(bot,block),/suitable harvesting tool/);
});
test('only an opened door with clear center counts as a passage',()=>{
 const {openPassage}=require('../spatial.cjs');
 const door={name:'oak_door',getProperties:()=>({open:true}),shapes:[[0,0,0,.1875,1,1]]};
 assert.ok(openPassage(door));assert.ok(!openPassage({...door,getProperties:()=>({open:false})}));
 assert.ok(!openPassage({...door,shapes:[[.4,0,0,.6,1,1]]}));
});

test('stalled navigation releases controls and permits another attempt',async()=>{
 const {gotoWithProgress}=require('../spatial.cjs');let cancelled=0,cleared=0;
 const bot={entity:{position:new Vec3(0,0,0)},pathfinder:{goto:()=>new Promise(()=>{}),setGoal:g=>{assert.equal(g,null);cancelled++;}},clearControlStates:()=>cleared++};
 await assert.rejects(gotoWithProgress(bot,{}, {stallMs:30,pollMs:10,settleMs:5}),e=>/Movement stalled/.test(e.message)&&e.movementOperationSettled===false);
 assert.equal(cancelled,1);assert.equal(cleared,1);
 bot.pathfinder.goto=async()=>{bot.entity.position=new Vec3(2,0,0);};
 await gotoWithProgress(bot,{}, {stallMs:30,pollMs:10});
 assert.equal(cancelled,1);assert.equal(cleared,1);
});

test('explicit ladder face selects the same supporting wall on every level',()=>{
 const {placementSupport}=require('../spatial.cjs');
 const bot={blockAt:p=>({name:'stone',boundingBox:'block',position:p})};
 for(let y=61;y<=63;y++){
  const p=new Vec3(21,y,70),s=placementSupport(bot,p,'north','ladder');
  assert.deepEqual(s.block.position,new Vec3(21,y,71));assert.deepEqual(s.normal,new Vec3(0,0,-1));
 }
 assert.throws(()=>placementSupport(bot,new Vec3(0,0,0),'up','ladder'),/horizontal/);
 assert.throws(()=>placementSupport({blockAt:()=>null},new Vec3(0,0,0),'east','ladder'),/no solid/);
});

test('open door waypoint stays below the lintel rather than atop its thin edge',()=>{
 const {normalizePassages}=require('../spatial.cjs');
 const door=half=>({name:'oak_door',boundingBox:'block',getProperties:()=>({open:true,half}),shapes:[[0,0,0,.1875,1,1]]});
 const bot=world({'0,0,0':{name:'stone',boundingBox:'block'},'0,1,0':door('lower'),'0,2,0':door('upper'),'0,3,0':{name:'stone',boundingBox:'block'}});
 const result={path:[{x:.296875,y:2,z:.5},{x:.5,y:4,z:.5}]};normalizePassages(bot,result);
 assert.deepEqual(result.path,[{x:.5,y:1,z:.5},{x:.5,y:4,z:.5}]);
});

test('site survey distinguishes canopy from ground and marks unloaded columns',()=>{
 const {survey}=require('../spatial.cjs');
 const bot=world({'0,4,0':{name:'oak_leaves',boundingBox:'block'},'0,0,0':{name:'grass_block',boundingBox:'block'}});
 bot.entity.position=new Vec3(.5,5,.5);
 const sample=survey(bot,8).samples.find(s=>s.x===0&&s.z===0);
 assert.equal(sample.top.y,4);assert.equal(sample.ground.floor_y,0);assert.equal(sample.ground.feet_y,1);
 assert.equal(sample.ground.clearance,'.');
 const unknown=survey({...bot,blockAt:()=>null},8).samples;
 assert.ok(unknown.every(s=>s.unknown&&s.ground===null));
});

test('exact full-block target reports stance without searching; horizontal range still searches',()=>{
 const {route}=require('../spatial.cjs');let searches=0;
 const solid={name:'grass_block',boundingBox:'block',shapes:[[0,0,0,1,1,1]]};
 const bot=world({'2,1,0':solid});bot.pathfinder={movements:{},getPathTo(){searches++;return {status:'success',path:[]};}};
 const r=route(bot,new Vec3(2,1,0));assert.equal(r.status,'target_obstructed');assert.equal(r.target_stance.feet.name,'grass_block');assert.equal(searches,0);
 assert.equal(route(bot,new Vec3(2,1,0),1).status,'success');assert.equal(searches,1);
});
test('head obstruction is exact; partial, unknown and unloaded targets are not declared full obstructions',()=>{
 const {route}=require('../spatial.cjs');let searches=0;
 const bot=world({});bot.pathfinder={movements:{},getPathTo(){searches++;return {status:'partial',path:[]};}};
 const p=new Vec3(0,1,0);bot.blockAt=q=>q.y===2?{name:'stone',shapes:[[0,0,0,1,1,1]]}:{name:'air',shapes:[]};
 assert.equal(route(bot,p).status,'target_obstructed');assert.equal(searches,0);
 for(const b of [null,{name:'unknown'},{name:'oak_door',shapes:[[0,0,0,.1875,1,1]]},{name:'ladder',shapes:[]}]){
  bot.blockAt=()=>b;assert.equal(route(bot,p).status,'partial');
 }
 assert.equal(searches,4);
});

test('stalled navigation distinguishes acknowledged cancellation from a merely stopped goal',async()=>{
 const {gotoWithProgress}=require('../spatial.cjs');let reject;
 const bot={entity:{position:new Vec3(0,0,0)},pathfinder:{goto:()=>new Promise((_,r)=>{reject=r;}),setGoal(){reject(Error('cancelled'));}},clearControlStates(){}};
 await assert.rejects(gotoWithProgress(bot,{}, {stallMs:10,pollMs:5,settleMs:20}),e=>e.movementOperationSettled===true);
});

test('reported dry drop bound matches actual upstream landing-floor semantics',()=>{
 const {Movements}=require('mineflayer-pathfinder');const {movementCapabilities}=require('../spatial.cjs');
 for(const limit of [2,3]){
  const m={maxDropDown:limit,canDig:false,allowParkour:false,allow1by1towers:false,bot:{game:{minY:-64}}};
  const bot={pathfinder:{movements:m}};
  assert.equal(movementCapabilities(bot).normal.max_dry_full_block_feet_drop_per_edge,limit-1);
  for(const descent of [1,2,3]){
   const floor=64-descent-1;
   m.getBlock=(node,dx,dy,dz)=>{const p=new Vec3(node.x+dx,node.y+dy,node.z+dz);return {position:p,physical:p.y===floor,safe:true,liquid:false};};
   const landing=Movements.prototype.getLandingBlock.call(m,new Vec3(0,64,0),{x:1,z:0});
   assert.equal(landing?.position.y??null,descent<limit?64-descent:null);
  }
 }
 assert.equal(movementCapabilities({}).normal.max_dry_full_block_feet_drop_per_edge,null);
});
test('route reports its movement limits without rejecting a larger total descent',()=>{
 const {route}=require('../spatial.cjs');let searches=0;
 const bot=world({});bot.pathfinder={movements:{maxDropDown:2,canDig:false,allowParkour:false,allow1by1towers:false},getPathTo(){searches++;return {status:'success',path:[new Vec3(1,63,0),new Vec3(2,62,0),new Vec3(3,61,0)]};}};
 const r=route(bot,new Vec3(3,61,0));
 assert.equal(r.reachable,true);assert.equal(searches,1);assert.equal(r.steps.length,3);
 assert.equal(r.movement_capabilities.normal.max_dry_full_block_feet_drop_per_edge,1);
 assert.equal(r.movement_capabilities.normal.can_dig,false);
});

// Reproduce the physical rule through the pinned upstream neighbor generator,
// not a duplicate approximation of its jump algorithm.
test('geometry clarity rise limit agrees with actual upstream full-block jump and clearance',()=>{
 const {Movements}=require('mineflayer-pathfinder');const {movementCapabilities}=require('../spatial.cjs');
 for(const height of [1,2])for(const overhead of [false,true]){
  const m={maxDropDown:2,canDig:false,allowParkour:false,allow1by1towers:false,scafoldingBlocks:[],
   getNumEntitiesAt:()=>0,safeOrBreak:b=>b.physical?1000:0,
   getBlock(node,dx,dy,dz){const p=new Vec3(node.x+dx,node.y+dy,node.z+dz);
    const solid=(p.x===0&&p.y===53)||(p.x===1&&p.y>=54&&p.y<54+height)||(overhead&&p.x===0&&p.y===56);
    return {position:p,physical:solid,height:p.y+(solid?1:0),replaceable:!solid};}};
  const neighbors=[];Movements.prototype.getMoveJumpUp.call(m,{x:0,y:54,z:0,remainingBlocks:0},{x:1,z:0},neighbors);
  assert.equal(neighbors.length,height===1&&!overhead?1:0);
  if(neighbors.length){assert.equal(neighbors[0].y,55);assert.deepEqual(neighbors[0].toBreak,[]);assert.deepEqual(neighbors[0].toPlace,[]);}
  const facts=movementCapabilities({pathfinder:{movements:m}}).normal;
  assert.equal(facts.max_dry_full_block_feet_rise_per_edge,1);assert.equal(facts.scaffolding_configured,false);
 }
 assert.equal(movementCapabilities({}).normal.max_dry_full_block_feet_rise_per_edge,null);
 assert.equal(movementCapabilities({}).normal.scaffolding_configured,null);
});
test('geometry clarity places a full cube below feet and exposes blocked head without claiming reachability',()=>{
 const {placementGeometry}=require('../spatial.cjs'),p=new Vec3(-530,55,-547);
 const cube=name=>({name,shapes:[[0,0,0,1,1,1]],boundingBox:'block'});
 for(const blocked of [false,true]){
  const bot={blockAt:q=>q.equals(p)?cube('cobblestone'):q.equals(p.offset(0,2,0))&&blocked?cube('stone'):{name:'air',shapes:[],boundingBox:'empty'}};
  const result=placementGeometry(bot,p),stance=result.stance_above_full_block;
  assert.equal(result.coordinate_role,'block');assert.equal(result.block.position.y,55);
  assert.equal(stance.feet.position.y,56);assert.equal(stance.head.position.y,57);assert.equal(stance.support.position.y,55);
  assert.equal(stance.support.name,'cobblestone');assert.equal(stance.exact_target_obstructed,blocked);
  assert.equal(result.reachable,undefined);assert.equal(result.safe,undefined);
 }
});
test('geometry clarity does not invent standing height for partial or missing placement geometry',()=>{
 const {placementGeometry}=require('../spatial.cjs');
 for(const b of [null,{name:'stone_slab',shapes:[[0,0,0,1,.5,1]]},{name:'cobblestone'},{name:'air',shapes:[]}]){
  const result=placementGeometry({blockAt:()=>b},new Vec3(1,55,2));assert.equal(result.stance_above_full_block,null);
 }
});
