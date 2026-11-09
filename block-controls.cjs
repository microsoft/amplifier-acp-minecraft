// Ordinary survival interaction; server block state confirms the control, not
// a whole circuit's success. A button pulse is never automatically replayed.
const {createHash}=require('node:crypto');
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const hash=v=>createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
function revision(block){return block?hash({position:block.position,name:block.name,properties:block.getProperties()}):null;}
class BlockControls {
 constructor(history){this.history=history;}
 save(id,value){
  const before=this.history.data.block_controls;
  this.history.data.block_controls={...before,[id]:value};
  try{this.history.save();}catch(error){this.history.data.block_controls=before;throw error;}
 }
 async use(bot,p,args,check,{sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}){
  const id=args.operation_id;
  if(typeof id!=='string'||!/^[a-zA-Z0-9_-]{8,100}$/.test(id))throw Error('Supply a unique operation_id; never replay a pulse');
  const fingerprint=hash(args),prior=this.history.data.block_controls?.[id];
  if(prior){
   if(prior.fingerprint!==fingerprint)throw Error('Control operation_id already used with different arguments');
   if(prior.status!=='settled')throw Error('Control outcome is uncertain; inspect the circuit, do not repeat this operation');
   return {...prior.result,duplicate:true};
  }
  check();const block=bot.blockAt(p),button=block?.name.endsWith('_button'),lever=block?.name==='lever';
  if(!button&&!lever)throw Error('Only ordinary buttons and levers are supported');
  if(p.distanceTo(bot.entity.position)>4)throw Error('Move within reach of the control first');
  const eye=bot.entity.position.offset(0,bot.entity.eyeHeight||1.62,0),ray=p.offset(.5,.5,.5).minus(eye),distance=ray.norm();
  const hit=distance?bot.world.raycast(eye,ray.scaled(1/distance),distance):null;
  if(hit&&!hit.position.equals(p))throw Error('Control is obstructed; choose a clear reachable position');
  if(!args.block_revision||revision(block)!==args.block_revision)throw Error('Control changed; inspect again before acting');
  if(button&&(args.operation!=='press'||args.powered!==undefined)||lever&&(args.operation!=='set'||typeof args.powered!=='boolean'))throw Error('Press a button or set a lever to an explicit powered state');
  const powered=block.getProperties().powered;
  if(typeof powered!=='boolean')throw Error('Server control state is unavailable');
  if(button&&powered)throw Error('Button is already pressed; wait for release and inspect, do not repeat');
  const target=button?true:args.powered;
  if(lever&&powered===target){const result={position:p,name:block.name,powered,changed:false,verified:true};this.save(id,{fingerprint,status:'settled',result});return result;}
  // Persist intent before the only effect. Any error/lost outcome leaves this
  // operation non-replayable across process restart.
  this.save(id,{fingerprint,status:'started',task_id:this.history.task()?.id,at:new Date().toISOString()});
  check();await bot.activateBlock(block);
  for(let attempt=0;attempt<20;attempt++){
   await sleep(50);check();const current=bot.blockAt(p);
   if(current?.name!==block.name)throw Error('Control block changed during interaction; inspect effects');
   if(current.getProperties().powered===target){
    const result={position:p,name:block.name,powered:target,changed:true,verified:true,
     scope:button?'Server confirmed button powered; automatic release and circuit behavior require separate observation.':'Server confirmed lever state; inspect circuit behavior separately.'};
    this.save(id,{fingerprint,status:'settled',result});return result;
   }
  }
  throw Error('Server did not confirm control state; outcome uncertain, inspect without replay');
 }
}
module.exports={BlockControls,revision};
