const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Vec3}=require('vec3'),{WorkshopState}=require('../workshop-state.cjs'),{BlockControls,revision}=require('../block-controls.cjs');
function fixture(t,name='stone_button'){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'controls-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(dir,'state.json')),p=new Vec3(0,64,1);let powered=false,calls=0;
 const block={name,position:p,getProperties:()=>({powered})},bot={entity:{position:new Vec3(0,64,0)},blockAt:()=>block,activateBlock:async()=>{calls++;powered=!powered;}};
 return {h,p,bot,block,c:new BlockControls(h),args:{x:0,y:64,z:1,operation_id:'unique-test',operation:name==='lever'?'set':'press',...(name==='lever'?{powered:true}:{}),block_revision:revision(block)},calls:()=>calls,power:v=>powered=v};
}
test('button confirms one server pulse; duplicate after release/reload never repeats it',async t=>{
 const f=fixture(t),result=await f.c.use(f.bot,f.p,f.args,()=>{},{sleep:async()=>{}});assert.equal(result.powered,true);assert.equal(f.calls(),1);f.power(false);
 const restored=new BlockControls(new WorkshopState(f.h.file));assert.equal((await restored.use(f.bot,f.p,f.args,()=>{})).duplicate,true);assert.equal(f.calls(),1);
 await assert.rejects(()=>restored.use(f.bot,f.p,{...f.args,x:2},()=>{}),/different arguments/);
});
test('lever sets requested state, supports no-op already-set, never toggles on duplicate',async t=>{
 const f=fixture(t,'lever');await f.c.use(f.bot,f.p,f.args,()=>{},{sleep:async()=>{}});assert.equal(f.calls(),1);
 const result=await f.c.use(f.bot,f.p,{...f.args,operation_id:'another-id',block_revision:revision(f.block)},()=>{});assert.equal(result.changed,false);assert.equal(f.calls(),1);
 const off=await f.c.use(f.bot,f.p,{...f.args,operation_id:'switch-off',block_revision:revision(f.block),powered:false},()=>{},{sleep:async()=>{}});assert.equal(off.powered,false);assert.equal(f.calls(),2);
});
test('uncertain effect or lost receipt write stays non-replayable after restart',async t=>{
 for(const failure of ['transport','save']){const f=fixture(t);if(failure==='transport')f.bot.activateBlock=async()=>{throw Error('closed');};else{const save=f.h.save.bind(f.h);let n=0;f.h.save=()=>{if(++n===2)throw Error('disk full');save();};}
  await assert.rejects(()=>f.c.use(f.bot,f.p,f.args,()=>{},{sleep:async()=>{}}));const restored=new BlockControls(new WorkshopState(f.h.file));await assert.rejects(()=>restored.use(f.bot,f.p,f.args,()=>{}),/uncertain/);
 }
});
test('stale selection, wrong block, out-of-reach and stopped authority make no control call',async t=>{
 for(const change of [f=>f.power(true),f=>f.block.name='chest',f=>f.bot.entity.position=new Vec3(50,64,0),f=>f.args.operation='set',f=>f.args.block_revision='stale']){
  const f=fixture(t);change(f);await assert.rejects(()=>f.c.use(f.bot,f.p,f.args,()=>{}));assert.equal(f.calls(),0);
 }
 const f=fixture(t);await assert.rejects(()=>f.c.use(f.bot,f.p,f.args,()=>{throw Error('stopped');}),/stopped/);assert.equal(f.calls(),0);
});
