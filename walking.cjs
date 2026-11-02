// Strict level walking is intentionally separate from the general pathfinder:
// one cardinal cell at a time, without its jump/shortcut post-processing.
const {Vec3}=require('vec3');
const {cell,FeetGoal}=require('./spatial.cjs');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const key=p=>`${p.x},${p.z}`;
function walkable(bot,p){
 if(cell(bot,p)!=='.')return false;
 const floor=bot.blockAt(p.offset(0,-1,0));
 // Full flat footing only. Slabs/stairs/climbing belong to normal navigation.
 return (floor.shapes||[]).some(s=>s[0]===0&&s[1]===0&&s[2]===0&&s[3]===1&&s[4]===1&&s[5]===1);
}
function plan(bot,target,range=0,{maxNodes=4096,radius=64}={}){
 const start=bot.entity.position.floored(),goal=new FeetGoal(target.x,target.y,target.z,range);
 const result=(status,path=[],examined=0)=>({mode:'walk_only',reachable:status==='success',status,target,range,exact_feet_y:true,
  steps:path.map(p=>({x:p.x,y:p.y,z:p.z})),examined,
  constraints:'Level cardinal walking on full footing; no jumping, climbing, swimming, digging or diagonal shortcuts.',
  coverage:'Loaded terrain, bounded search. Rechecked during movement; planning is not arrival.'});
 if(target.y!==start.y)return result('different_elevation');
 if(!walkable(bot,start))return result('unsafe_start');
 const queue=[start],parents=new Map([[key(start),null]]),seen=new Set([key(start)]);
 let cursor=0,bounded=false,unknown=false;
 while(cursor<queue.length&&cursor<maxNodes){
  const p=queue[cursor++];
  if(goal.isEnd(p)){
   const path=[];for(let n=p;n;n=parents.get(key(n)))path.unshift(n);
   if(path.length>256)return result('path_too_long',[],cursor);
   return result('success',path,cursor);
  }
  for(const [dx,dz]of [[0,-1],[1,0],[0,1],[-1,0]]){
   const n=p.offset(dx,0,dz),k=key(n);if(seen.has(k))continue;seen.add(k);
   if(Math.abs(n.x-start.x)>radius||Math.abs(n.z-start.z)>radius){bounded=true;continue;}
   if(cell(bot,n)==='?'){unknown=true;continue;}
   if(walkable(bot,n)){parents.set(k,p);queue.push(n);}
  }
 }
 return result(cursor>=maxNodes||bounded?'search_limit':unknown?'unloaded':'no_path',[],cursor);
}
async function move(bot,target,range,check,{wait=sleep,stallMs=2500,maxMs=55000}={}){
 const route=plan(bot,target,range);if(!route.reachable)throw Error(`No walk-only route (${route.status}); inspect the terrain. No movement performed.`);
 const before=bot.entity.position.clone(),started=Date.now(),height=before.floored().y;
 let minY=before.y,maxY=before.y,samples=0;const visited=[];
 bot.pathfinder.setGoal(null);bot.clearControlStates();
 const guard=()=>{
  check();const p=bot.entity.position;minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y);samples++;
  if(Date.now()-started>maxMs)throw Error('Walk-only time limit; movement stopped. Inspect before continuing.');
  if(p.y<height-.05||p.y>height+.125)throw Error('Walk-only elevation changed; movement stopped. Inspect current footing.');
  if(!walkable(bot,p.floored()))throw Error('Walk-only footing or clearance changed; movement stopped.');
 };
 try{
  for(const node of route.steps){
   const p=new Vec3(node.x,node.y,node.z),center=p.offset(.5,0,.5);
   let best=Infinity,lastProgress=Date.now();
   while(true){
    guard();if(!walkable(bot,p))throw Error('Walk-only route changed; inspect and plan again.');
    const delta=center.minus(bot.entity.position),distance=Math.hypot(delta.x,delta.z);
    if(distance<=.12){bot.setControlState('forward',false);break;}
    if(distance<best-.04){best=distance;lastProgress=Date.now();}
    if(Date.now()-lastProgress>stallMs)throw Error('Walk-only movement stalled; inspect players and obstacles before retrying.');
    await bot.look(Math.atan2(-delta.x,-delta.z),0,true);guard();
    bot.setControlState('jump',false);bot.setControlState('sprint',false);bot.setControlState('forward',true);
    await wait(50);
   }
   visited.push(node);
  }
  bot.clearControlStates();await wait(150);guard();
  if(!new FeetGoal(target.x,target.y,target.z,range).isEnd(bot.entity.position.floored()))throw Error('Walk-only arrival did not match the target.');
  return {mode:'walk_only',before,position:bot.entity.position.clone(),target,reached:true,exact_feet_y:true,
   traversed:visited,observation:{min_feet_y:minY,max_feet_y:maxY,samples,jump_requested:false}};
 }finally{bot.clearControlStates();}
}
module.exports={walkable,plan,move};
