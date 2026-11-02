const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {Vec3}=require('vec3'),signs=require('../signs.cjs');
function setup({front=true,echo=true}={}){
 const p=new Vec3(0,1,0);let saved=['Old\n\n\n',''],writes=0;
 const block={name:'oak_sign',position:p,getSignText:()=>saved,getProperties:()=>({rotation:8}),blockEntity:{is_waxed:0}};
 const bot={entity:{position:new Vec3(.5,1,-1.5)},blockAt:()=>block,_client:new EventEmitter(),unequip:async()=>{},activateBlock:async()=>{bot._client.emit('open_sign_entity',{location:p,isFrontText:front});},updateSign:(b,text,back)=>{writes++;if(echo)saved[back?1:0]=text;}};
 return {bot,p,block,writes:()=>writes};
}
test('sign edit verifies saved text and preserves the other side',async()=>{
 const {bot,p,writes}=setup();const result=await signs.write(bot,p,{lines:['Welcome','Walk the lanes'],expected_lines:['Old']},()=>{});
 assert.equal(result.verified,true);assert.equal(result.front[0],'Welcome');assert.equal(result.back.join(''),'');assert.equal(writes(),1);
 assert.equal(bot._client.listenerCount('open_sign_entity'),0);
});
test('sign edit refuses wrong side, wax and stale expected text before sending text',async()=>{
 for(const kind of ['side','wax','stale']){
  const {bot,p,block,writes}=setup({front:kind!=='side'});if(kind==='wax')block.blockEntity.is_waxed=1;
  await assert.rejects(signs.write(bot,p,{lines:['New'],...(kind==='stale'?{expected_lines:['Other']}:{})},()=>{}),/facing|waxed|changed/);
  assert.equal(writes(),0);assert.equal(bot._client.listenerCount('open_sign_entity'),0);
 }
});
test('sign writes require server echo and cancellation cleans listeners',async()=>{
 const {bot,p}=setup({echo:false});await assert.rejects(signs.write(bot,p,{lines:['New']},()=>{},{timeoutMs:10}),/did not echo/);
 let checks=0;await assert.rejects(signs.write(bot,p,{lines:['New']},()=>{if(++checks>=3)throw Error('cancelled');}),/cancelled/);
 assert.equal(bot._client.listenerCount('open_sign_entity'),0);
});
test('sign input never permits control characters or extra lines',()=>{
 assert.throws(()=>signs.validate(['a\nb']),/plain lines/);assert.throws(()=>signs.validate(['1','2','3','4','5']),/plain lines/);
 assert.throws(()=>signs.validate(['x'.repeat(46)]),/plain lines/);assert.deepEqual(signs.validate(['Hello']),['Hello','','','']);
});
