// One ordinary hoe interaction. No movement, digging, planting or retry loop.
const {refreshInventory}=require('./inventory.cjs');
const hoes=new Set(['wooden_hoe','stone_hoe','iron_hoe','golden_hoe','diamond_hoe','netherite_hoe']);
function target(bot,p,expected){
 const b=bot.blockAt(p);
 if(!['grass_block','dirt'].includes(expected)||b?.name!==expected)throw Error('Till requires the expected grass_block or dirt; inspect first. Coarse/rooted dirt need separate preparation.');
 if(!['air','cave_air','void_air'].includes(bot.blockAt(p.offset(0,1,0))?.name))throw Error('Tilling needs clear air above the soil. Inspect and clear only authorized obstacles first.');
 const eye=bot.entity.position.offset(0,1.62,0),top=p.offset(.5,1,.5),delta=top.minus(eye),distance=delta.norm();
 if(distance>4||eye.y<=p.y+1)throw Error('Stand beside the soil within four blocks with its top face visible; till does not move you.');
 const hit=bot.world.raycast(eye,delta.scaled(1/distance),distance+.02);
 if(hit&&!hit.position.equals(p))throw Error('Soil top is obstructed; choose a clear reachable position.');
 return b;
}
async function till(bot,p,a,check,{timeoutMs=3000}={}){
 target(bot,p,a.expected);
 if(!bot.supportFeature('blockPlaceHasInsideBlock'))throw Error('Tilling requires the modern Java block interaction protocol');
 if(bot.currentWindow||bot.inventory.selectedItem)throw Error('Resolve the open inventory window/cursor before using a hoe');
 await refreshInventory(bot);check();
 const hoe=bot.inventory.items().find(i=>hoes.has(i.name));
 if(!hoe)throw Error('A hoe is required. Craft one from two sticks and two matching tool materials, then inspect inventory.');
 await bot.equip(hoe,'hand');await refreshInventory(bot);check();
 if(!hoes.has(bot.heldItem?.name))throw Error('Server did not confirm a held hoe; refresh inventory before retrying.');
 // Mineflayer activateBlock awaits lookAt internally before writing. Split that
 // operation so Stop and changed soil are rechecked immediately before send.
 await bot.lookAt(p.offset(.5,1,.5),false);check();
 const block=target(bot,p,a.expected);
 if(!hoes.has(bot.heldItem?.name))throw Error('Held hoe changed before tilling');
 let timer,confirmed=false,sent=false,resolve;
 const update=new Promise(r=>{resolve=r;});
 const listener=(_old,b)=>{if(b?.position.equals(p)&&b.name==='farmland'){confirmed=true;resolve();}};
 bot.on('blockUpdate',listener);
 try{
  timer=setTimeout(resolve,timeoutMs);
  check();sent=true;
  bot._client.write('block_place',{location:block.position,direction:1,hand:0,cursorX:.5,cursorY:1,cursorZ:.5,insideBlock:false,sequence:0,worldBorderHit:false});
  bot.swingArm();
  await update;check();
  const actual=bot.blockAt(p),verified=confirmed&&actual?.name==='farmland';
  return {position:p,operation:'till',status:verified?'confirmed':'unconfirmed',verified,observed:actual?.name||'unloaded',
   properties:actual?.getProperties?.(),...(!verified?{error:'Server did not confirm farmland'}:{}),evidence:confirmed?'Server block update at the requested soil':'No matching server farmland update before deadline',
   guidance:verified?'Farmland observed. Hydration and planting are separate; avoid trampling it.':'Inspect this block before trying again; an interaction was sent and its effect is uncertain.'};
 }catch(e){
  if(!sent)throw e;
  return {position:p,operation:'till',status:'unconfirmed',verified:false,observed:bot.blockAt(p)?.name||'unloaded',
   error:e.message,guidance:'An interaction may have reached the server. Inspect before retrying; no automatic retry occurred.'};
 }finally{clearTimeout(timer);bot.removeListener('blockUpdate',listener);}
}
module.exports={till,target};
