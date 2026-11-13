// A short-lived, loopback-only renderer. It cannot move the player or fetch external pages.
const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');const http=require('node:http');
async function render(bot,camera,{browserPath}={}){
 if(!require('./screenshot-ui/versions.json').includes(bot.version))throw Error('Player screenshots currently support Minecraft Java 1.21.1');
 const {chromium}=require('playwright');const express=require('express');
 const entry=path.join(__dirname,'screenshot-ui/dist');if(!fs.existsSync(path.join(entry,'capture.js')))throw Error('Screenshot renderer is not installed; run npm run build:screenshots');
 const chunks=[],cx=Math.floor(camera.position.x/16),cz=Math.floor(camera.position.z/16);
 for(let x=cx-2;x<=cx+2;x++)for(let z=cz-2;z<=cz+2;z++){
  const c=bot.world.getColumn(x,z);if(c)chunks.push({x:x*16,z:z*16,chunk:c.toJson()});
 }
 if(!chunks.length)throw Error('No loaded world chunks to capture');
 const entities=Object.values(bot.entities||{}).filter(e=>e!==bot.entity&&e.position&&Math.hypot(e.position.x-camera.position.x,e.position.z-camera.position.z)<=48).slice(0,64).map(e=>({id:e.id,name:e.name,pos:{x:e.position.x,y:e.position.y,z:e.position.z},width:e.width,height:e.height,username:e.username,yaw:e.yaw,pitch:e.pitch}));
 const snapshot=JSON.stringify({version:bot.version,camera,chunks,entities,minY:bot.game?.minY??-64,height:bot.game?.height??384});if(Buffer.byteLength(snapshot)>32*1024*1024)throw Error('Loaded world snapshot exceeds capture limit');
 const nonce=crypto.randomBytes(24).toString('hex'),prefix='/'+nonce+'/';
 const app=express();app.disable('x-powered-by');
 const assets=path.join(path.dirname(require.resolve('prismarine-viewer/package.json')),'public');
 app.get(prefix+'snapshot.json',(req,res)=>res.type('json').send(snapshot));
 app.use(prefix,express.static(entry));app.use(prefix,express.static(assets));
 const server=http.createServer(app);let browser;
 try{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)});
  const origin=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({...(browserPath?{executablePath:browserPath}:{}),headless:true,timeout:20000,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
  const context=await browser.newContext({viewport:{width:960,height:540},deviceScaleFactor:1,serviceWorkers:'block'});
  await context.route('**/*',r=>r.request().url().startsWith(origin+prefix)?r.continue():r.abort());
  await context.routeWebSocket('**/*',ws=>ws.close());
  const page=await context.newPage();await page.goto(origin+prefix,{waitUntil:'domcontentloaded',timeout:20000});
  await page.waitForFunction(()=>window.captureReady||window.captureError,null,{timeout:20000});
  const error=await page.evaluate(()=>window.captureError);if(error)throw Error(error);
  const png=await page.locator('canvas').screenshot({type:'png',timeout:10000});return {png,loaded_chunks:chunks.length};
 }finally{
  if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));
 }
}
module.exports={render};
