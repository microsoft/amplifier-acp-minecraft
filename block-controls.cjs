// Ordinary survival interaction; server block state confirms the control, not
// a whole circuit's success. A button pulse is never automatically replayed.
const {createHash}=require('node:crypto');
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const hash=v=>createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const preflightRefusals=new WeakSet();
const noEffect=error=>preflightRefusals.has(error);
function revision(block){return block?hash({position:block.position,name:block.name,properties:block.getProperties()}):null;}
function setting(block,property){const value=block.getProperties()[property];return property==='delay'&&typeof value==='string'&&/^[1-4]$/.test(value)?Number(value):value;}
function reachable(bot,p){
 if(p.distanceTo(bot.entity.position)>4)throw Error('Move within reach of the control first');
 const eye=bot.entity.position.offset(0,bot.entity.eyeHeight||1.62,0),ray=p.offset(.5,.5,.5).minus(eye),distance=ray.norm();
 const hit=distance?bot.world.raycast(eye,ray.scaled(1/distance),distance):null;
 if(hit&&!hit.position.equals(p))throw Error('Control is obstructed; choose a clear reachable position');
}
class BlockControls {
 constructor(history){this.history=history;}
 save(id,value){
  const before=this.history.data.block_controls;
  this.history.data.block_controls={...before,[id]:value};
  try{this.history.save();}catch(error){this.history.data.block_controls=before;throw error;}
 }
 preflight(bot,p,args,check=()=>{}){
  const id=args.operation_id;
  if(typeof id!=='string'||!/^[a-zA-Z0-9_-]{8,100}$/.test(id))throw Error('Supply a unique operation_id; never replay a pulse');
  const fingerprint=hash(args),prior=this.history.data.block_controls?.[id];
  if(prior){
   if(prior.fingerprint!==fingerprint)throw Error('Control operation_id already used with different arguments');
   if(prior.status!=='settled')throw Error('Control outcome is uncertain; inspect the circuit, do not repeat this operation');
   return {duplicate:{...prior.result,duplicate:true}};
  }
  check();try{
  const block=bot.blockAt(p),button=block?.name.endsWith('_button'),lever=block?.name==='lever',repeater=block?.name==='repeater',comparator=block?.name==='comparator';
  if(!button&&!lever&&!repeater&&!comparator)throw Error('Only buttons, levers, repeaters and comparators are supported');
  reachable(bot,p);
  if(!args.block_revision||revision(block)!==args.block_revision)throw Error('Control changed; inspect again before acting');
  if(repeater||comparator){
   const property=repeater?'delay':'mode',current=setting(block,property),target=args[property];
   if(args.operation!=='set'||args.powered!==undefined||(repeater?args.mode!==undefined:args.delay!==undefined))throw Error('Set only the matching repeater delay or comparator mode');
   const valid=v=>repeater?Number.isInteger(v)&&v>=1&&v<=4:['compare','subtract'].includes(v);
   if(!valid(current)||!valid(target))throw Error('Repeater delay must be 1–4 redstone ticks; comparator mode must be compare or subtract');
   return {id,fingerprint,block,configuration:{property,current,target,count:repeater?(target-current+4)%4:Number(target!==current)}};
  }
  if(args.delay!==undefined||args.mode!==undefined)throw Error('Delay/mode only apply to repeaters/comparators');
  if(button&&(args.operation!=='press'||args.powered!==undefined)||lever&&(args.operation!=='set'||typeof args.powered!=='boolean'))throw Error('Press a button or set a lever to an explicit powered state');
  const powered=block.getProperties().powered;
  if(typeof powered!=='boolean')throw Error('Server control state is unavailable');
  if(button&&powered)throw Error('Button is already pressed; wait for release and inspect, do not repeat');
  const target=button?true:args.powered;
  return {id,fingerprint,block,button,lever,powered,target};
  }catch(error){preflightRefusals.add(error);throw error;}
 }
 async use(bot,p,args,check,{sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}){
  // Repeat the pure checks at the actual operation boundary; a changed stance
  // or block before intent is still a proven no-effect refusal.
  const selected=this.preflight(bot,p,args,check);
  if(selected.duplicate)return selected.duplicate;
  if(selected.configuration)return this.configure(bot,p,selected,check,sleep);
  const {id,fingerprint,block,button,lever,powered,target}=selected;
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
 async configure(bot,p,{id,fingerprint,block,configuration},check,sleep){
  const {property,target,count}=configuration,steps=[];
  const result=()=>({position:p,name:block.name,[property]:target,changed:count>0,verified:true,steps,
   scope:'Server-confirmed component configuration only. Intermediate clicks can affect a live circuit; timing and circuit behavior require separate verification.'});
  if(!count){const r=result();this.save(id,{fingerprint,status:'settled',result:r});return r;}
  let current=configuration.current,expectedRevision=revision(block);
  const intent={fingerprint,status:'started',task_id:this.history.task()?.id,at:new Date().toISOString(),configuration,steps:[]};
  this.save(id,intent);
  for(let i=0;i<count;i++){
   check();reachable(bot,p);const before=bot.blockAt(p);
   if(!before||revision(before)!==expectedRevision)throw Error('Component changed during configuration; inspect without replay');
   const next=property==='delay'?current%4+1:current==='compare'?'subtract':'compare';
   await bot.activateBlock(before);let confirmed=false;
   for(let attempt=0;attempt<20;attempt++){
    await sleep(50);check();const actual=bot.blockAt(p);
    if(actual?.name!==block.name)throw Error('Component changed during interaction; inspect effects');
    const value=setting(actual,property);
    if(value===next){expectedRevision=revision(actual);steps.push({[property]:value,block_revision:expectedRevision});current=value;confirmed=true;break;}
    if(value!==current)throw Error('Unexpected component state after click; inspect without replay');
   }
   if(!confirmed)throw Error('Server did not confirm component configuration; outcome uncertain, inspect without replay');
   // Commit every confirmed intermediate step; an interrupted operation is not
   // continued on a duplicate call, even when some clicks are known to settle.
   this.save(id,{...intent,steps:[...steps]});
  }
  const r=result();this.save(id,{fingerprint,status:'settled',result:r});return r;
 }
}
module.exports={BlockControls,revision,noEffect};
