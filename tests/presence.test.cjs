const test=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const {once}=require('node:events');
const {createHandler,status,activity}=require('../presence.cjs');
const snapshot={username:'Builder',ready:true,position:{x:3,y:64,z:5},
  task:{id:'existing-task',goal:'An existing public goal',status:'waiting',turns:4,max_turns:12,deadline:100000,
    request:'Do not expose original source data',request_id:'private-request',progress:[{
      summary:'Waiting for material',request_id:'private-request',
      observation:{recent_actions:[{arguments:{message:'Private action input'}}]}}]},
  public_chat:[{id:'public',kind:'chat',username:'Player',message:'Hello'},
    {id:'operator',kind:'chat',username:'Operator',message:'Private management request',whisper:false},
    {id:'control',kind:'chat',username:'ControlAlias',message:'Private control with explicit provenance',provenance:'operator_control',whisper:false},
    {id:'private',kind:'chat',username:'Player',message:'Private whisper',whisper:true},
    {id:'receipt',kind:'action_result',result:{secret:'Do not expose raw receipts'}}],
  token:'never-public',receipts:[{private:true}]};
test('status keeps useful progress without source requests or control details',()=>{
 const result=status(snapshot,'Workshop');
 assert.equal(result.task.status,'waiting');assert.equal(result.position.y,64);
 assert.equal(result.task.request,undefined);assert.equal(result.task.request_id,undefined);
 assert.equal(result.token,undefined);assert.equal(result.receipts,undefined);
 assert.equal(result.task.progress[0].summary,'Waiting for material');
 assert.equal(result.task.progress[0].observation,undefined);
 assert.ok(!JSON.stringify(result).includes('private-request'));
 assert.equal(status({username:'Builder',ready:false},'Workshop').ready,false);
});
test('activity filters private messages and action receipts before slicing',()=>{
 const result=activity(snapshot,20,'Workshop');assert.deepEqual(result.messages.map(e=>e.id),['public']);
 assert.ok(!JSON.stringify(result).includes('Private whisper'));
 assert.ok(!JSON.stringify(result).includes('Private management request'));
 assert.ok(!JSON.stringify(result).includes('Private control'));
});
test('real MCP boundary exposes only observation tools and cannot begin work',async t=>{
 let reads=0;const before=JSON.stringify(snapshot);
 const errors=[];
 const handler=createHandler({token:'read-secret',snapshot:()=>{reads++;return snapshot;},label:'Workshop',onError:e=>errors.push(e)});
 const server=http.createServer(handler);server.listen(0,'127.0.0.1');await once(server,'listening');
 t.after(()=>new Promise(resolve=>server.close(resolve)));
 const url=`http://127.0.0.1:${server.address().port}/presence/mcp`;
 const rpc=async(method,params={},token='read-secret',headers={})=>fetch(url,{method:'POST',headers:{
   authorization:'Bearer '+token,'content-type':'application/json',accept:'application/json, text/event-stream',...headers
 },body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})});
 assert.equal((await rpc('tools/list',{},'controller-secret')).status,401);
 assert.equal((await rpc('tools/list',{},'context-secret')).status,401);
 assert.equal((await rpc('tools/list',{},'read-secret',{origin:'https://example.test'})).status,403);
 assert.equal(reads,0);
 const init=await rpc('initialize',{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'test',version:'1'}});
 assert.equal(init.status,200,errors.map(e=>e.stack).join('\n'));
 const listing=await (await rpc('tools/list')).json();
 assert.deepEqual(listing.result.tools.map(x=>x.name).sort(),['minecraft_recent_activity','minecraft_status']);
 const read=await (await rpc('tools/call',{name:'minecraft_status',arguments:{}})).json();
 assert.equal(JSON.parse(read.result.content[0].text).task.id,'existing-task');
 for(const name of ['work_begin','move','stop','task','minecraft_status;work_begin']){
   const denied=await (await rpc('tools/call',{name,arguments:{}})).json();
   assert.ok(denied.error||denied.result?.isError);
 }
 assert.equal(reads,1);assert.equal(JSON.stringify(snapshot),before);
});
test('missing presence token disables the optional endpoint',async()=>{
 let statusCode;const res={writeHead:c=>{statusCode=c;},end:()=>{}};
 await createHandler({snapshot:()=>{throw Error('must not read')}})({headers:{},method:'POST'},res);
 assert.equal(statusCode,403);
});
