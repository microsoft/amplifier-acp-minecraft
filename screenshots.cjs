// On-demand player-view captures. Rendering, world geometry and provenance belong here;
// the agent decides whether to attach the resulting file through its current experience.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const MAX_BYTES=2*1024*1024;
const LIMITS=Object.freeze({max_files:256,max_total_bytes:256*1024*1024,cooldown_ms:10000});
function camera(bot,args={}){
 const p=bot.entity?.position;
 if(!p||![p.x,p.y,p.z].every(Number.isFinite))throw Error('Player is not connected');
 const eye={x:p.x,y:p.y+1.62,z:p.z};
 let yaw=bot.entity.yaw||0,pitch=bot.entity.pitch||0;
 if(args.look_at){
  const q=args.look_at;if(![q.x,q.y,q.z].every(Number.isFinite))throw Error('Invalid camera target');
  const dx=q.x-eye.x,dy=q.y-eye.y,dz=q.z-eye.z;
  if(Math.hypot(dx,dy,dz)>64||Math.hypot(dx,dy,dz)<.1)throw Error('Camera target must be within 64 blocks of your eyes');
  yaw=Math.atan2(-dx,-dz);pitch=Math.atan2(dy,Math.hypot(dx,dz));
 }
 return {position:{x:p.x,y:p.y,z:p.z},eye,yaw,pitch,look_at:args.look_at||null,fov:75};
}
function pngInfo(data){
 if(!Buffer.isBuffer(data)||data.length<33||data.length>MAX_BYTES||!data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw Error('Renderer did not return a bounded PNG');
 const width=data.readUInt32BE(16),height=data.readUInt32BE(20);
 if(width!==960||height!==540)throw Error('Unexpected capture dimensions');
 return {width,height};
}
class Screenshots{
 constructor({bot,directory,world='Minecraft',render,now=()=>Date.now(),browserPath,isReady=()=>true,onSaved=()=>{}}){
  this.bot=bot;this.directory=path.resolve(directory);this.world=world;this.render=render||((pose)=>require('./screenshot-renderer.cjs').render(bot,pose,{browserPath}));this.now=now;this.last=-Infinity;this.busy=false;this.isReady=isReady;this.onSaved=onSaved;
 }
 prepare(){
  fs.mkdirSync(this.directory,{recursive:true,mode:0o700});
  if(fs.lstatSync(this.directory).isSymbolicLink()||!fs.statSync(this.directory).isDirectory())throw Error('Screenshot storage must be a real directory');
 }
 list(){
  this.prepare();return fs.readdirSync(this.directory).filter(n=>/^capture-[0-9a-f-]{36}\.json$/.test(n)).map(n=>{
   try{const info=JSON.parse(this.readFile(n,16384).toString('utf8'));return typeof info.captured_at==='string'&&typeof info.id==='string'?info:null;}catch{return null;}
  }).filter(Boolean).sort((a,b)=>b.captured_at.localeCompare(a.captured_at));
 }
 readFile(name,limit){
  const fd=fs.openSync(path.join(this.directory,name),fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
  try{const st=fs.fstatSync(fd);if(!st.isFile()||st.size>limit)throw Error('Saved screenshot is not a bounded regular file');
   const data=Buffer.alloc(Math.min(st.size+1,limit+1));const n=fs.readSync(fd,data,0,data.length,0);if(n>limit)throw Error('Saved screenshot exceeds limit');return data.subarray(0,n);
  }finally{fs.closeSync(fd);}
 }
 read(id){
  if(!/^[0-9a-f-]{36}$/.test(id))throw Error('Choose a screenshot ID returned by this player');
  this.prepare();const file=path.join(this.directory,`capture-${id}.png`),meta=path.join(this.directory,`capture-${id}.json`);
  for(const p of [file,meta])if(!fs.lstatSync(p).isFile()||fs.lstatSync(p).isSymbolicLink())throw Error('Screenshot is not a regular saved file');
  if(fs.statSync(file).size>MAX_BYTES||fs.statSync(meta).size>16384)throw Error('Saved screenshot exceeds limit');
  const data=this.readFile(path.basename(file),MAX_BYTES),info=JSON.parse(this.readFile(path.basename(meta),16384).toString('utf8'));pngInfo(data);
  if(info.sha256!==crypto.createHash('sha256').update(data).digest('hex'))throw Error('Screenshot content no longer matches its receipt');
  return {info,data};
 }
 async capture(args={}){
  if(this.busy)throw Error('A screenshot is already being captured');
  if(!this.isReady())throw Error('Player is not connected; no current view to capture');
  if(this.now()-this.last<LIMITS.cooldown_ms)throw Error('Wait ten seconds between screenshots');
  const pose=camera(this.bot,args);this.prepare();
  const stored=fs.readdirSync(this.directory).filter(n=>/^capture-.*\.png$/.test(n)).map(n=>fs.lstatSync(path.join(this.directory,n)));
  if(stored.length>=LIMITS.max_files||stored.reduce((n,s)=>n+s.size,0)>=LIMITS.max_total_bytes-MAX_BYTES)throw Error('Screenshot storage limit reached; move older captures before taking more');
  this.busy=true;this.last=this.now();
  try{
   const started=this.now(),rendered=await this.render(pose);const data=rendered.png||rendered;const size=pngInfo(data);
   const id=crypto.randomUUID(),file=path.join(this.directory,`capture-${id}.png`),meta=path.join(this.directory,`capture-${id}.json`);
   const info={id,captured_at:new Date(started).toISOString(),completed_at:new Date(this.now()).toISOString(),player:this.bot.username,world:this.world,minecraft_version:this.bot.version,kind:'rendered_player_view',camera:pose,...size,bytes:data.length,sha256:crypto.createHash('sha256').update(data).digest('hex'),path:file,mime_type:'image/png',label:String(args.label||'').slice(0,160),loaded_chunks:rendered.loaded_chunks??null,limitations:'Rendered from this player’s loaded world and eye position. No game HUD, chat, or private conversations. Lighting, signs and entity appearances may differ from the official client. Not a screen recording.'};
   fs.writeFileSync(file,data,{flag:'wx',mode:0o600});try{fs.writeFileSync(meta,JSON.stringify(info,null,2)+'\n',{flag:'wx',mode:0o600});}catch(e){fs.unlinkSync(file);throw e;}
   this.onSaved(info);return {info,data};
  }finally{this.busy=false;}
 }
}
function content({info,data}){return {content:[{type:'text',text:JSON.stringify({...info,sharing:'Saved locally. Taking or reading a screenshot does not post it anywhere. Attach the saved image in the current conversation only when requested.'})},{type:'image',mimeType:'image/png',data:data.toString('base64')}]};}
function registerTools(server,photos,prefix=''){
 if(!photos)return;const {z}=require('zod');
 const register=(name,description,inputSchema,readonly,fn)=>server.registerTool(prefix+name,{description,inputSchema,annotations:{readOnlyHint:readonly,destructiveHint:false,openWorldHint:false}},async a=>{try{return await fn(a)}catch(e){return {isError:true,content:[{type:'text',text:e.message}]}}});
 register('screenshot','Capture your current Minecraft view as a local PNG and visual tool result. Optional look_at aims the camera without moving your player. This does not post anywhere or start game work. To show it in this conversation, use your agent’s image attachment capability with the returned saved path.',{label:z.string().max(160).optional(),look_at:z.object({x:z.number(),y:z.number(),z:z.number()}).optional()},false,async a=>content(await photos.capture(a)));
 register('screenshots','List your saved Minecraft screenshots and their timestamps, camera positions and local paths. Does not render a new image.',{},true,()=>({content:[{type:'text',text:JSON.stringify({screenshots:photos.list()})}]}));
 register('screenshot_read','Inspect a previously saved Minecraft screenshot by its ID. Does not capture or publish an image.',{id:z.string().uuid()},true,a=>content(photos.read(a.id)));
}
module.exports={Screenshots,camera,pngInfo,content,registerTools,MAX_BYTES,LIMITS};
