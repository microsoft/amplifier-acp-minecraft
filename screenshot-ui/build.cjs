const path=require('node:path');const fs=require('node:fs');const esbuild=require('esbuild');
const out=path.join(__dirname,'dist');fs.mkdirSync(out,{recursive:true});
esbuild.build({entryPoints:[path.join(__dirname,'main.js')],outfile:path.join(out,'capture.js'),bundle:true,platform:'browser',define:{'global':'globalThis','__dirname':'""'},loader:{'.png':'dataurl'},minify:true,
 plugins:[{name:'viewer-browser-assets',setup(build){
  build.onResolve({filter:/^\.\.?\/utils(\.electron\.js)?$/},args=>args.importer.includes('prismarine-viewer')?{path:require.resolve('prismarine-viewer/viewer/lib/utils.web.js')}:null);
  build.onResolve({filter:/^canvas$/},()=>({path:path.join(__dirname,'canvas.js')}));
 }}]
}).then(()=>esbuild.build({entryPoints:[path.join(__dirname,'worker.js')],outfile:path.join(out,'worker.js'),bundle:true,platform:'browser',minify:true,define:{global:'globalThis',__dirname:'""'},inject:[path.join(__dirname,'globals.js')],plugins:[{name:'meshing-data-only',setup(build){
 const keep=new Set(['blocks','blockCollisionShapes','tints','blockStates','biomes','features','version','legacy','versions','protocolVersions']);
 // Bundle the tested game version and the viewer's tint reference, rather
 // than every historical edition (hundreds of MB in each worker).
 build.onLoad({filter:/minecraft-data[\\/]data\.js$/},args=>{
  const data=require(args.path),pc={};for(const version of [...require('./versions.json'),'1.16.2'])pc[version]=Object.fromEntries(Object.entries(data.pc[version]).filter(([key])=>keep.has(key)));
  return {contents:'module.exports='+JSON.stringify({pc,bedrock:{}}),loader:'js'};
 });
 build.onLoad({filter:/minecraft-data.*\.json$/},args=>keep.has(path.basename(args.path,'.json'))?null:{contents:'module.exports=[]',loader:'js'});
 build.onResolve({filter:/^zlib$/},()=>({path:'zlib',namespace:'empty'}));
 build.onLoad({filter:/.*/,namespace:'empty'},()=>({contents:'module.exports={}',loader:'js'}));
}}]})).then(()=>{
 fs.writeFileSync(path.join(out,'index.html'),'<!doctype html><html><meta charset="utf-8"><title>Player capture</title><style>html,body{margin:0;overflow:hidden;background:#000}canvas{display:block}</style><script src="capture.js"></script></html>');
 console.log('Screenshot renderer built');
}).catch(e=>{console.error(e);process.exitCode=1});
