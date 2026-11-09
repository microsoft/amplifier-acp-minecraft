// Owner setup/update check only. No game connection, model, or external page.
const {spawnSync}=require('node:child_process');
async function ready({prepare=false,browserPath,playwright=require('playwright'),install=spawnSync}={}){
 if(prepare&&!browserPath){
  const cli=require('node:path').join(require('node:path').dirname(require.resolve('playwright/package.json')),'cli.js');
  const result=install(process.execPath,[cli,'install','--only-shell','chromium'],{env:{...process.env,PLAYWRIGHT_SKIP_BROWSER_GC:'1'},timeout:300000,stdio:['ignore',2,2]});
  if(result.error||result.status!==0)throw Error('Exact screenshot browser installation failed; preserve the current player installation');
 }
 let browser;
 try{
  browser=await playwright.chromium.launch({...(browserPath?{executablePath:browserPath}:{}),headless:true,timeout:20000,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
  const context=await browser.newContext({viewport:{width:32,height:32},serviceWorkers:'block'});
  await context.route('**/*',r=>r.abort());await context.routeWebSocket('**/*',ws=>ws.close());
  const page=await context.newPage();
  const gl=await page.evaluate(()=>!!document.createElement('canvas').getContext('webgl2'));
  if(!gl)throw Error('Screenshot browser lacks WebGL2 rendering support');
  return {ready:true,playwright_version:require('playwright/package.json').version,browser_version:browser.version(),custom_browser:!!browserPath,world_access:false};
 }finally{if(browser)await browser.close();}
}
if(require.main===module){
 const [action,...args]=process.argv.slice(2);
 if(!['prepare','check'].includes(action)||!(args.length===0||args.length===2&&args[0]==='--browser-path'&&require('node:path').isAbsolute(args[1]))){console.error('Use prepare|check [--browser-path /absolute/executable]');process.exitCode=1;}
 else ready({prepare:action==='prepare',browserPath:args[1]}).then(r=>console.log(JSON.stringify(r))).catch(e=>{console.error(e.message);process.exitCode=1;});
}
module.exports={ready};
