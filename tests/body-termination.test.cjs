// How the real body process ends, as its supervisor sees it. Status 0 is only
// for the body's own intended exits; a requested termination ends by the signal
// after cleanup, so a service manager can restart it after an outside SIGTERM.
// A silent loopback listener stands in for the game server. No world or model.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const posix={skip:process.platform==='win32'?'POSIX signal status':false};

const listening=server=>new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',()=>resolve(server.address().port));});
async function freePort(){const s=net.createServer(),port=await listening(s);await new Promise(done=>s.close(done));return port;}
function reachable(port){return new Promise(resolve=>{const s=net.connect(port,'127.0.0.1');s.once('connect',()=>{s.destroy();resolve(true);});s.once('error',()=>resolve(false));});}
async function until(check,what){for(let i=0;i<300;i++){if(await check())return;await new Promise(r=>setTimeout(r,100));}assert.fail('Timed out waiting for '+what);}

async function start(t,{game,connection}={}){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'body-termination-'));
 t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 const control=await freePort();
 fs.writeFileSync(path.join(home,'config.json'),JSON.stringify({username:'Fixture',host:'127.0.0.1',port:game||await freePort(),
  version:'1.21.1',auth:'offline',control_port:control,token:'fixture'}));
 if(connection){
  fs.mkdirSync(path.join(home,'installation-connections'));
  fs.writeFileSync(path.join(home,'installation-connections/state.json'),JSON.stringify(connection));
 }
 const child=spawn(process.execPath,[path.join(root,'body.cjs'),path.join(home,'config.json')],{cwd:root,stdio:['ignore','pipe','pipe']});
 let output='';child.stdout.on('data',d=>output+=d);child.stderr.on('data',d=>output+=d);
 const ended=new Promise(resolve=>child.once('exit',(code,signal)=>resolve({code,signal})));
 t.after(()=>{if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');});
 return {home,control,child,ended,output:()=>output};
}
function standIn(t,onConnection){
 // Like a real server it reads what arrives and closes when the client does.
 const sockets=[],server=net.createServer(socket=>{sockets.push(socket);socket.on('error',()=>{});socket.resume();onConnection?.(socket);});
 t.after(()=>{for(const s of sockets)s.destroy();server.close();});
 return {server,sockets};
}
const events=home=>JSON.parse(fs.readFileSync(path.join(home,'world-tools','state.json'),'utf8')).events.map(e=>e.kind);

test('requested termination leaves the game, then ends by the signal rather than status 0',posix,async t=>{
 const game=standIn(t),body=await start(t,{game:await listening(game.server)});
 // The control listener and the signal handler are installed by the same module load.
 await until(async()=>game.sockets.length===1&&await reachable(body.control),'the body to connect and listen');
 body.child.kill('SIGTERM');
 assert.deepEqual(await body.ended,{code:null,signal:'SIGTERM'},body.output());
 // Cleanup ran first: the game connection was closed and recorded.
 assert.ok(events(body.home).includes('disconnected'),body.output());
 assert.equal(await reachable(body.control),false);
});

test('a lost game connection is still a failure exit',async t=>{
 const game=standIn(t,socket=>socket.destroy()),body=await start(t,{game:await listening(game.server)});
 assert.deepEqual(await body.ended,{code:1,signal:null},body.output());
});

test('a disconnected saved connection is still an intended exit with status 0',async t=>{
 const body=await start(t,{connection:{schema:1,phase:'disconnected',request_id:'fixture'}});
 assert.deepEqual(await body.ended,{code:0,signal:null},body.output());
 assert.match(body.output(),/Saved Minecraft connection is disconnected/);
});

test('body unit template restarts after a failure or an outside SIGTERM only',()=>{
 const lines=fs.readFileSync(path.join(root,'ops/minecraft-body@.service'),'utf8').split('\n');
 const service=lines.slice(lines.indexOf('[Service]')+1,lines.indexOf('[Install]'));
 // Status 0 stays unrestarted; a stop through the service manager is never restarted.
 assert.deepEqual(service.filter(l=>l.startsWith('Restart')&&!l.startsWith('RestartSec=')),
  ['Restart=on-failure','RestartForceExitStatus=SIGTERM']);
});
