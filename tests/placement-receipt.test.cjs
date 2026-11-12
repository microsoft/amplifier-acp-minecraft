const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events'),{Vec3}=require('vec3');
const receipt=require('../placement-receipt.cjs');
for(const mode of ['confirmed','no_ack','reversed','timeout','unloaded','changed','mismatched','success'])test('placement settlement evidence '+mode,async()=>{
 const bot=new EventEmitter(),target=new Vec3(1,64,1),support={position:target.offset(0,-1,0)},air={type:0,name:'air'};bot.blockAt=()=>air;
 const error=new Error(mode==='timeout'?'Server did not answer the placement':`Server refused to place stone at ${mode==='mismatched'?'another cell':target}: the block is still air`);
 const send=async()=>{
  const ref=()=>bot.emit(`blockUpdate:${support.position}`,{},{}),update=next=>bot.emit(`blockUpdate:${target}`,air,next);
  if(mode==='reversed'){update(air);ref();}else if(mode!=='no_ack'){ref();update(mode==='unloaded'?null:air);if(mode==='changed')update({type:1,name:'stone'});}
  if(mode==='success')return {ok:true};throw error;
 };
 if(mode==='success')assert.deepEqual(await receipt.attempt(bot,support,target,'stone',send),{ok:true});
 else await assert.rejects(receipt.attempt(bot,support,target,'stone',send),e=>e===error);
 assert.equal(!!receipt.refusal(error),mode==='confirmed');assert.equal(bot.eventNames().length,0);
});
