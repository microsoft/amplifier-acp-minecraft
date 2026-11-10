const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http');
const {HuddleHttp}=require('../huddle-http.cjs'),{HuddleJournal}=require('../huddle-journal.cjs');
const id='d68c0154-aea4-40a9-b4b7-83233ed02de9',token='private-fixture-token-'.repeat(3);
async function server(t,handler){const s=http.createServer(handler);await new Promise(r=>s.listen(0,'127.0.0.1',r));t.after(()=>{s.closeAllConnections();s.close();});return `http://127.0.0.1:${s.address().port}`;}
test('fixed participant routes carry credential only in header; lost post ack queries same operation',async t=>{
 let posts=0;const paths=[],url=await server(t,async(req,res)=>{
  assert.equal(req.headers.authorization,`Bearer ${token}`);paths.push(req.url);
  if(req.method==='POST'){posts++;let data='';for await(const c of req)data+=c;assert.equal(JSON.parse(data).request_id,id);req.socket.destroy();return;}
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify({state:'saved',request_id:id}));
 });
 const config={url,room_id:'room',token},c=new HuddleHttp(config),history={data:{},save(){}};
 const journal=new HuddleJournal(history,{host:url,room_id:'room',agent_id:'agent',connection_id:'game'}),payload={request_id:id,text:'Test',target_agent_ids:[],kind:'message'};
 assert.equal(journal.begin(payload).send,true);await assert.rejects(c.post(payload),/outcome unavailable/);
 assert.equal(journal.begin(payload).send,false);const found=await c.status(id);assert.equal(found.found,true);assert.equal(found.value.request_id,id);assert.equal(posts,1);
 assert.deepEqual(paths,['/api/v1/huddles/room/posts',`/api/v1/huddles/room/posts/${id}`]);assert.ok(!JSON.stringify(c).includes(token));
});
test('404, credential revocation and redirect are not successful post evidence',async t=>{
 const url=await server(t,(req,res)=>{if(req.url.includes('/posts/'))res.writeHead(404);else if(req.url.includes('/messages'))res.writeHead(403);else res.writeHead(302,{Location:'/secret-target'});res.end(token);}),c=new HuddleHttp({url,room_id:'room',token});
 assert.deepEqual(await c.status(id),{found:false});await assert.rejects(c.messages(),/HTTP 403/);await assert.rejects(c.descriptor(),e=>!e.message.includes(token)&&/outcome unavailable/.test(e.message));
});
test('response size, type and time are bounded without disclosing remote text',async t=>{
 const url=await server(t,(req,res)=>{if(req.url.includes('/messages')){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({text:token.repeat(8)}));}else if(req.url.includes('/posts/')){res.setHeader('Content-Type','text/plain');res.end(token);}else{res.setHeader('Content-Type','application/json');res.write('{');}}),c=new HuddleHttp({url,room_id:'room',token},{maxBytes:100,timeoutMs:100});
 await assert.rejects(c.messages(),/bounded read/);await assert.rejects(c.status(id),/non-JSON/);await assert.rejects(c.descriptor(),/outcome unavailable/);
});
test('no browser-selected host, insecure nonloopback, URL credentials, query or path',()=>{
 for(const url of ['http://example.com','http://localhost','https://user:secret@example.com','https://example.com/path','https://example.com/?token=x','https://example.com/#secret'])assert.throws(()=>new HuddleHttp({url,room_id:'room',token}));
 const c=new HuddleHttp({url:'https://example.com',room_id:'room',token});assert.throws(()=>c.messages(-1));assert.throws(()=>c.messages(0,101));assert.throws(()=>c.status('../other'));
});
