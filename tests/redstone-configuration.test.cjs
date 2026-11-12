const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Vec3}=require('vec3'),{WorkshopState}=require('../workshop-state.cjs'),{BlockControls,revision}=require('../block-controls.cjs');
function fixture(t,name,initial){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'redstone-config-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const h=new WorkshopState(path.join(dir,'state.json')),p=new Vec3(1,64,0),property=name==='repeater'?'delay':'mode';let value=initial,calls=0;
 const block={name,position:p,getProperties:()=>({[property]:property==='delay'?String(value):value,facing:'north',powered:false,...(name==='repeater'?{locked:false}:{})})};
 const bot={entity:{position:new Vec3(0,64,0)},world:{raycast:()=>null},blockAt:()=>block,activateBlock:async()=>{calls++;value=property==='delay'?value%4+1:value==='compare'?'subtract':'compare';}};
 return {h,p,property,block,bot,c:new BlockControls(h),get:()=>value,set:v=>value=v,calls:()=>calls,args:target=>({x:1,y:64,z:0,operation:'set',operation_id:'config-unique',block_revision:revision(block),[property]:target})};
}
for(let from=1;from<=4;from++)for(let to=1;to<=4;to++)test(`repeater ${from} to ${to} confirms each step and never repeats settled operation`,async t=>{
 const f=fixture(t,'repeater',from),args=f.args(to),r=await f.c.use(f.bot,f.p,args,()=>{},{sleep:async()=>{}});assert.equal(r.delay,to);assert.equal(r.verified,true);assert.equal(f.get(),to);assert.equal(f.calls(),(to-from+4)%4);assert.equal(r.steps.length,f.calls());
 const restored=new BlockControls(new WorkshopState(f.h.file));assert.equal((await restored.use(f.bot,f.p,args,()=>{})).duplicate,true);assert.equal(f.calls(),(to-from+4)%4);
});
for(const from of ['compare','subtract'])for(const to of ['compare','subtract'])test(`comparator ${from} to ${to}`,async t=>{
 const f=fixture(t,'comparator',from),r=await f.c.use(f.bot,f.p,f.args(to),()=>{},{sleep:async()=>{}});assert.equal(r.mode,to);assert.equal(f.calls(),from===to?0:1);assert.equal(r.verified,true);
});
for(const kind of ['transport','stop','unexpected','save'])test('partial configuration '+kind+' is never resumed or replayed',async t=>{
 const f=fixture(t,'repeater',1),args=f.args(4),activate=f.bot.activateBlock;let checks=0;
 if(kind==='transport')f.bot.activateBlock=async()=>{await activate();throw Error('lost acknowledgment');};
 if(kind==='unexpected')f.bot.activateBlock=async()=>{await activate();f.set(4);};
 if(kind==='save'){const save=f.h.save.bind(f.h);let n=0;f.h.save=()=>{if(++n===2)throw Error('disk full');save();};}
 await assert.rejects(f.c.use(f.bot,f.p,args,()=>{if(kind==='stop'&&f.calls()===1&&++checks>=1)throw Error('stopped');},{sleep:async()=>{}}));
 const calls=f.calls();assert.equal(calls,1);const restored=new BlockControls(new WorkshopState(f.h.file));await assert.rejects(restored.use(f.bot,f.p,args,()=>{}),/uncertain/);assert.equal(f.calls(),calls);
});
for(const fields of [{delay:0},{delay:5},{delay:1.5},{delay:4,powered:true},{delay:4,mode:'subtract'},{mode:'subtract'}])test('invalid or mixed repeater target refuses before intent '+JSON.stringify(fields),async t=>{
 const f=fixture(t,'repeater',1),args={...f.args(4),...fields};if(!('delay'in fields))delete args.delay;
 await assert.rejects(f.c.use(f.bot,f.p,args,()=>{}));assert.equal(f.calls(),0);assert.equal(f.h.data.block_controls?.[args.operation_id],undefined);
});
