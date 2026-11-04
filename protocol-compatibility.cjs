// Mineflayer crafts from its versioned recipe registry, then our tools verify
// every result against server inventory. It does not consume declare_recipes.
// ViaBackwards can include newer recipe-preview item components that the 1.21
// decoder cannot read. Keep only this unused UI recipe-book payload opaque;
// actual inventory, block, entity and action packets remain fully decoded.
function protocolCompatibility(version){
 return version==='1.21.1'?{'1.21':{play:{toClient:{types:{packet_declare_recipes:'restBuffer'}}}}}:undefined;
}
function translationMetadata(c){
 if(c?.type!=='custom_data'||c.data?.type!=='compound')return false;
 const v=c.data.value;
 if(!v||Object.keys(v).sort().join(',')!=='VV|custom_data,VV|original_hashes')return false;
 if(v['VV|custom_data']?.type!=='byte'||v['VV|custom_data'].value!==1)return false;
 const h=v['VV|original_hashes'];
 if(h?.type!=='compound'||Object.keys(h.value||{}).sort().join(',')!=='backup_tag,id,removed')return false;
 const x=h.value;
 return x.id?.type==='int'&&Number.isInteger(x.id.value)&&x.id.value>=0&&
  x.backup_tag?.type==='string'&&x.backup_tag.value==='VB|Protocol1_21_5To1_21_4'&&
  x.removed?.type==='intArray'&&Array.isArray(x.removed.value)&&x.removed.value.length===0;
}
module.exports={protocolCompatibility,translationMetadata};
