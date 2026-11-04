const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Screenshots,camera,content,MAX_BYTES}=require('../screenshots.cjs');
function fixture(t,options={}){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'minecraft-capture-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const png=Buffer.alloc(64);Buffer.from('89504e470d0a1a0a','hex').copy(png);png.write('IHDR',12);png.writeUInt32BE(960,16);png.writeUInt32BE(540,20);const bot={username:'Builder',version:'1.21.1',entity:{position:{x:4,y:64,z:6},yaw:0,pitch:0}};return {dir,png,bot,photos:new Screenshots({bot,directory:dir,render:async()=>png,...options})};}
test('capture saves exact bytes, provenance and image content without moving the player',async t=>{
 const {photos,bot,dir,png}=fixture(t);const before=JSON.stringify(bot);const r=await photos.capture({look_at:{x:7,y:65,z:5},label:'Progress'});
 assert.equal(JSON.stringify(bot),before);assert.equal(r.info.camera.position.x,4);assert.equal(r.info.player,'Builder');
 assert.deepEqual(fs.readFileSync(r.info.path),png);assert.ok(r.info.path.startsWith(dir));assert.equal(photos.list().length,1);
 assert.deepEqual(photos.read(r.info.id).data,png);assert.equal(content(r).content[1].type,'image');
 if(process.platform!=='win32')assert.equal(fs.statSync(r.info.path).mode&0o777,0o600);
 await assert.rejects(photos.capture(),/ten seconds/);
 fs.writeFileSync(r.info.path,Buffer.concat([png,Buffer.from('changed')]));assert.throws(()=>photos.read(r.info.id),/receipt/);
});
test('bounded camera, invalid renderer, connection and overlap failures leave no false receipt',async t=>{
 const {bot}=fixture(t);assert.throws(()=>camera(bot,{look_at:{x:500,y:64,z:0}}),/within/);
 const bad=fixture(t,{render:async()=>Buffer.alloc(MAX_BYTES+1)});await assert.rejects(bad.photos.capture(),/bounded PNG/);assert.equal(bad.photos.list().length,0);
 const off=fixture(t,{isReady:()=>false});await assert.rejects(off.photos.capture(),/not connected/);
 let release;const gate=new Promise(r=>release=r);const f=fixture(t,{render:async()=>{await gate;return bad.png}});
 const first=f.photos.capture();await assert.rejects(f.photos.capture(),/already/);release();await first;
});
test('saved image lookup refuses arbitrary paths and symlinks',async t=>{
 const {photos,dir}=fixture(t);assert.throws(()=>photos.read('../anything'),/ID/);
 const r=await photos.capture();if(process.platform!=='win32'){
  fs.renameSync(r.info.path,path.join(dir,'elsewhere.png'));fs.symlinkSync(path.join(dir,'elsewhere.png'),r.info.path);assert.throws(()=>photos.read(r.info.id),/regular/);
 }
});
test('optional MCP capture is available on presence without granting game control',async t=>{
 const http=require('node:http'),{once}=require('node:events'),{createHandler}=require('../presence.cjs');const {photos}=fixture(t);
 const server=http.createServer(createHandler({token:'fixture',snapshot:()=>({ready:true}),screenshots:photos}));server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>new Promise(r=>server.close(r)));
 const rpc=async(method,params={})=>(await fetch(`http://127.0.0.1:${server.address().port}`,{method:'POST',headers:{authorization:'Bearer fixture','content-type':'application/json',accept:'application/json, text/event-stream'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})})).json();
 const list=await rpc('tools/list');assert.equal(list.result.tools.length,5);assert.equal(list.result.tools.find(t=>t.name==='minecraft_screenshot').annotations.readOnlyHint,false);
 const shot=await rpc('tools/call',{name:'minecraft_screenshot',arguments:{}});assert.equal(shot.result.content[1].type,'image');assert.equal(photos.list().length,1);
 const denied=await rpc('tools/call',{name:'move',arguments:{x:1,y:2,z:3}});assert.ok(denied.error||denied.result?.isError);
});
test('real Chromium renderer uses loaded world geometry, including below zero', {skip:process.env.RUN_SCREENSHOT_RENDER!=='1'},async t=>{
 const {render}=require('../screenshot-renderer.cjs'),Chunk=require('prismarine-chunk')('1.21.1'),{Vec3}=require('vec3'),mc=require('minecraft-data')('1.21.1');
 const {photos,bot}=fixture(t);const c=new Chunk();for(let x=0;x<16;x++)for(let z=0;z<16;z++)c.setBlockStateId(new Vec3(x,-1,z),mc.blocksByName.grass_block.defaultState);
 for(let y=0;y<3;y++)for(let x=4;x<9;x++)c.setBlockStateId(new Vec3(x,y,4),mc.blocksByName.oak_planks.defaultState);
 bot.entity.position=new Vec3(7,0,11);bot.world={getColumn:(x,z)=>x===0&&z===0?c:null};photos.render=pose=>render(bot,pose,{browserPath:process.env.SCREENSHOT_BROWSER_PATH});
 const r=await photos.capture();assert.equal(r.info.loaded_chunks,1);assert.ok(r.data.length>10000);
 const {PNG}=require('pngjs');const png=PNG.sync.read(r.data);const at=(x,y)=>Array.from(png.data.subarray((y*960+x)*4,(y*960+x)*4+3));
 assert.notDeepEqual(at(480,270),at(5,5),'wood wall must be visible, not an empty sky capture');
 assert.notDeepEqual(at(480,500),at(5,5),'floor must render below zero');
});
