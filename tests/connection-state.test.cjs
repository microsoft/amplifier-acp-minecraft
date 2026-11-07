const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {transportAllowed}=require('../connection-state.cjs');
test('saved offline intent survives a fresh body launch without joining or changing work',()=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'saved-offline-'));
 try{
  assert.equal(transportAllowed(home),true);
  fs.mkdirSync(path.join(home,'installation-connections'));
  const state=path.join(home,'installation-connections/state.json');
  for(const phase of ['disconnecting','disconnected']){
   fs.writeFileSync(state,JSON.stringify({schema:1,phase,request_id:'original'}));
   assert.equal(transportAllowed(home),false);
   fs.writeFileSync(path.join(home,'config.json'),'{}');
   const output=execFileSync(process.execPath,[path.resolve(__dirname,'../body.cjs'),path.join(home,'config.json')],{timeout:10000,encoding:'utf8'});
   assert.match(output,/disconnected/);assert.equal(fs.existsSync(path.join(home,'workshop.json')),false);
  }
  fs.writeFileSync(state,JSON.stringify({schema:1,phase:'connecting',request_id:'explicit-new'}));
  assert.equal(transportAllowed(home),true);
  fs.writeFileSync(state,'{}');assert.throws(()=>transportAllowed(home),/Invalid/);
 }finally{fs.rmSync(home,{recursive:true,force:true});}
});
