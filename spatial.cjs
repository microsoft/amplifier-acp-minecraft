const {Vec3}=require('vec3');
const {goals,Movements}=require('mineflayer-pathfinder');
function alignPlayerCollision(bot){
 // Minecraft EntityDimensions stores width as a float, then divides by 2f.
 // Prismarine's 0.3 double is slightly narrower. A sprint-jump can therefore
 // clip a block edge on the server and trigger repeated position corrections.
 // Keep upstream/custom dimensions if they no longer have the affected value.
 if(bot.physics.playerHalfWidth===0.3)bot.physics.playerHalfWidth=Math.fround(0.6)/2;
}
function openPassage(b){return !!b?.getProperties?.().open&&/(?:_door|_fence_gate)$/.test(b.name)&&!(b.shapes||[]).some(s=>s[0]<.8&&s[3]>.2&&s[2]<.8&&s[5]>.2);}
class SpatialMovements extends Movements {
 getBlock(...args){const b=super.getBlock(...args);if(openPassage(b)){b.safe=true;b.physical=false;b.height=b.position.y;}return b;}
}
const hazards=new Set(['lava','fire','soul_fire','cactus','magma_block','sweet_berry_bush','powder_snow']);
const faces={north:[0,0,-1],south:[0,0,1],east:[1,0,0],west:[-1,0,0],up:[0,1,0],down:[0,-1,0]};
function placementSupport(bot,p,face,item){
 if(face){
  if(!faces[face]||(item==='ladder'&&['up','down'].includes(face)))throw Error('Choose a horizontal support_face for ladders');
  const normal=new Vec3(...faces[face]),block=bot.blockAt(p.minus(normal));
  if(block?.boundingBox!=='block')throw Error('Requested support face has no solid supporting block');
  return {block,normal};
 }
 for(const v of [[0,-1,0],[1,0,0],[-1,0,0],[0,0,1],[0,0,-1]]){
  if(item==='ladder'&&v[1])continue;
  const offset=new Vec3(...v),block=bot.blockAt(p.plus(offset));
  if(block?.boundingBox==='block')return {block,normal:offset.scaled(-1)};
 }
 throw Error('No solid support face');
}
function cell(bot,p){
 const foot=bot.blockAt(p),head=bot.blockAt(p.offset(0,1,0)),floor=bot.blockAt(p.offset(0,-1,0));
 if(!foot||!head||!floor)return '?';
 if([foot,head,floor].some(b=>hazards.has(b.name)))return '!';
 if([foot,head,floor].some(b=>b.name==='water'))return '~';
 if(foot.name==='ladder'||foot.name==='vine')return 'L';
 if((foot.boundingBox==='block'&&!openPassage(foot))||(head.boundingBox==='block'&&!openPassage(head)))return '#';
 return floor.boundingBox==='block'?'.':'o';
}
function supported(bot,p){return cell(bot,p)==='.';}
// Loaded facts only. A full cube proves an exact feet/head cell is blocked;
// partial shapes, climbable blocks and unknown geometry remain planner decisions.
function targetStance(bot,p){
 const sample=(position)=>{
  const b=bot.blockAt(position);if(!b)return {position,name:null,geometry:'unloaded'};
  const shapes=b.shapes;
  const full=Array.isArray(shapes)&&shapes.some(s=>s.length===6&&s[0]===0&&s[1]===0&&s[2]===0&&s[3]===1&&s[4]===1&&s[5]===1);
  return {position,name:b.name,geometry:full?'full_block':Array.isArray(shapes)?shapes.length?'partial':'empty':'unknown'};
 };
 const feet=sample(p),head=sample(p.offset(0,1,0)),support=sample(p.offset(0,-1,0));
 return {feet,head,support,exact_target_obstructed:[feet,head].some(b=>b.geometry==='full_block'),
  meaning:'Target coordinates are feet, not the supporting block. Partial or unloaded geometry is not proof of clearance; no alternative destination is selected.'};
}

function footing(p,positions){return positions.some(v=>p.x>=Math.floor(v.x-.299)&&p.x<=Math.floor(v.x+.299)&&p.z>=Math.floor(v.z-.299)&&p.z<=Math.floor(v.z+.299)&&Math.floor(v.y-.001)===p.y);}
class FeetGoal extends goals.GoalNear {
 isEnd(n){return n.y===this.y&&((n.x-this.x)**2+(n.z-this.z)**2)<=this.rangeSq;}
}
function route(bot,p,range=0){
 const target_stance=targetStance(bot,p);
 if(range===0&&target_stance.exact_target_obstructed)return {reachable:false,status:'target_obstructed',target:p,range,exact_feet_y:true,steps:[],target_stance,coverage:'Loaded exact destination is obstructed; no path search or movement performed'};
 const goal=new FeetGoal(p.x,p.y,p.z,range);
 const r=bot.pathfinder.getPathTo(bot.pathfinder.movements,goal,150);normalizePassages(bot,r);
 return {reachable:r.status==='success',status:r.status,target:p,range,target_stance,exact_feet_y:true,steps:(r.path||[]).map(n=>({x:n.x,y:n.y,z:n.z})).slice(0,64),coverage:'Loaded terrain only; a planned path is not proof of arrival'};
}
// Pathfinder's post-processing targets the top of collision shapes, including
// the thin edge of an open door. Keep the waypoint in its clear lower passage.
function normalizePassages(bot,result){
 for(const n of result.path||[]){
  const p=new Vec3(Math.floor(n.x),Math.floor(n.y)-1,Math.floor(n.z)),b=bot.blockAt(p);
  if(openPassage(b)&&b.getProperties().half==='lower'&&cell(bot,p)==='.'){
   n.x=p.x+.5;n.y=p.y;n.z=p.z+.5;
  }
 }
 return result;
}
function localMap(bot,radius=4){
 const center=bot.entity.position.floored(),layers=[],standing=[];
 for(let y=center.y-3;y<=center.y+3;y++){
  const rows=[];
  for(let z=center.z-radius;z<=center.z+radius;z++){
   let row='';for(let x=center.x-radius;x<=center.x+radius;x++){
    const p=new Vec3(x,y,z),c=cell(bot,p);row+=p.equals(center)?'@':c;
    if(c==='.')standing.push({x,y,z});
   }rows.push(row);
  }layers.push({feet_y:y,rows});
 }
 standing.sort((a,b)=>center.distanceTo(new Vec3(a.x,a.y,a.z))-center.distanceTo(new Vec3(b.x,b.y,b.z)));
 return {center,x_min:center.x-radius,z_min:center.z-radius,axes:'Columns increase east (+x); rows increase south (+z); y is the player feet height, not floor height.',legend:{'@':'you','.':'clear feet/head with solid footing','#':'feet or head obstructed','o':'unsupported air','~':'water','!':'hazard','L':'ladder/vine','?':'unloaded'},layers,standing_candidates:standing.slice(0,24),coverage:'Conservative block-cell occupancy. Candidates are not proven reachable; use plan_route. Partial blocks, doors and ladders need inspect.'};
}
// Sparse loaded-world survey: distinguish building ground from canopy.
function survey(bot,radius=16){
 const center=bot.entity.position.floored(),samples=[];
 for(let z=center.z-radius;z<=center.z+radius;z+=4)for(let x=center.x-radius;x<=center.x+radius;x+=4){
  let top=null,ground=null,unknown=false;
  for(let y=Math.min(319,center.y+16);y>=Math.max(-64,center.y-24);y--){
   const b=bot.blockAt(new Vec3(x,y,z));if(!b){unknown=true;break;}
   if(!top&&(b.boundingBox==='block'||b.name==='water'))top={y,block:b.name};
   if((b.boundingBox==='block'||b.name==='water')&&!/_(leaves|log|wood)$/.test(b.name)){
    ground={floor_y:y,block:b.name,feet_y:y+1,clearance:cell(bot,new Vec3(x,y+1,z))};break;
   }
  }
  samples.push({x,z,top,ground,unknown});
 }
 return {center,spacing:4,samples,coverage:'Loaded columns only, 24 blocks below/16 above you. Sampled terrain, not a complete footprint; tree logs/leaves excluded from ground. Inspect every planned building area and confirm routes.'};
}
function digGuard(bot,block){
 const positions=[bot.entity.position,...Object.values(bot.players||{}).map(p=>p.entity?.position).filter(Boolean)];
 if(footing(block.position,positions))throw Error('Refusing to remove a block supporting a player; move to safe footing first');
 if(hazards.has(block.name)||block.name==='water')throw Error('Hazardous target');
 const above=bot.blockAt(block.position.offset(0,1,0));
 if(above&&['sand','red_sand','gravel'].includes(above.name))throw Error('Falling material above this block; choose another route');
 for(const d of [[1,0,0],[-1,0,0],[0,1,0],[0,0,1],[0,0,-1]]){
  if(['water','lava'].includes(bot.blockAt(block.position.offset(...d))?.name))throw Error('Digging would open adjacent liquid; choose another block');
 }
}
function harvestTool(bot,block){
 const best=bot.pathfinder.bestHarvestTool(block);
 if(best&&block.canHarvest(best.type))return best;
 const valid=bot.inventory.items().find(i=>block.canHarvest(i.type));
 if(valid)return valid;
 if(block.canHarvest(null))return null;
 throw Error(`A suitable harvesting tool is required for ${block.name}; mining it now would not collect its normal drop`);
}
async function gotoWithProgress(bot,goal,{stallMs=8000,pollMs=500,settleMs=1000}={}){
 let timer,drainTimer,settled=false,last=bot.entity.position.clone(),lastMoved=Date.now();
 const operation=Promise.resolve().then(()=>bot.pathfinder.goto(goal));
 const completion=operation.then(()=>{settled=true;},()=>{settled=true;});
 try{
  await Promise.race([operation,new Promise((_,reject)=>{
   timer=setInterval(()=>{
    const p=bot.entity.position;
    if(p.distanceTo(last)>.2){last=p.clone();lastMoved=Date.now();}
    else if(Date.now()-lastMoved>=stallMs)reject(Error('Movement stalled without position progress; inspect nearby blocks and choose a different route. This turn remains available.'));
   },pollMs);
  })]);
 }catch(error){
  let cancelled=true;try{bot.pathfinder.setGoal(null);bot.clearControlStates();}catch{cancelled=false;}
  await Promise.race([completion,new Promise(resolve=>{drainTimer=setTimeout(resolve,settleMs);})]);
  error.movementOperationSettled=settled&&cancelled;throw error;
 }finally{clearInterval(timer);clearTimeout(drainTimer);}
}

module.exports={alignPlayerCollision,survey,openPassage,SpatialMovements,cell,targetStance,supported,footing,FeetGoal,route,localMap,digGuard,harvestTool,gotoWithProgress,placementSupport,normalizePassages};
