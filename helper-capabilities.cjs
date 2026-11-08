// Static local helper discovery, independent of ACP/Instance or model features.
const fs=require('node:fs');
const {promisify}=require('node:util');
const exec=promisify(require('node:child_process').execFile);
const cache=new Map();
function identity(command){try{const s=fs.statSync(command);return `${s.dev}:${s.ino}:${s.size}:${s.mtimeMs}:${s.ctimeMs}`;}catch{return null;}}
function supports(value,name){
 const h=value?.helpers?.[name];
 return value?.schema_version===1&&h?.version===2&&h.command===`${name}-v2`&&
  Array.isArray(h.bound_kinds)&&h.bound_kinds.includes('finite')&&h.bound_kinds.includes('no_configured_bound')&&
  (name!=='watch'||(h.watch_ttl_seconds?.minimum===30&&h.watch_ttl_seconds?.maximum===1800));
}
function current(command){const c=cache.get(command);return c&&c.identity===identity(command)?c.value:null;}
async function discover(command){
 const key=identity(command);if(!key)return null;
 const previous=cache.get(command);if(previous?.identity===key)return previous.promise;
 const entry={identity:key,value:null};cache.set(command,entry);
 entry.promise=(async()=>{try{
  const {stdout}=await exec(command,['helper-capabilities'],{timeout:5000,maxBuffer:32768});
  const value=JSON.parse(stdout);if(identity(command)!==key)return null;
  entry.value=value;return value;
 }catch{return null;}})();return entry.promise;
}
function ready(command){
 const v=current(command);
 // An idle helper update changes the binary without restarting the body.
 // Re-discover its identity on ordinary state reads; remain closed until done.
 // discover coalesces concurrent reads and caches failures for that identity.
 if(v===null||v===undefined)void discover(command);
 return supports(v,'watch')&&supports(v,'continuation');
}
module.exports={discover,current,supports,ready};
