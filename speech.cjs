// Packetize one completed utterance, never infer ACP completion from punctuation.
function packets(text,prefix='',width=240){
 const clean=String(text).replace(/[\r\n\x00-\x1f]/g,' ').trim();
 if(!clean||clean.startsWith('/')||clean.length>4000)throw Error('Use 1–4000 characters of ordinary chat');
 const available=width-prefix.length;if(available<40)throw Error('Address is too long');
 let remaining=clean;const result=[];
 while(remaining){
  let part=remaining.slice(0,available);
  // Java's chat length is UTF-16; do not split a surrogate pair.
  if(/[\uD800-\uDBFF]$/.test(part))part=part.slice(0,-1);
  if(part.length<remaining.length){
   const endings=[...part.matchAll(/[.!?…]["'”’)]*(?=\s|$)/g)];
   if(endings.length){const last=endings.at(-1);part=part.slice(0,last.index+last[0].length);}
   else if(part.includes(' '))part=part.slice(0,part.lastIndexOf(' '));
  }
  result.push(prefix+part);remaining=remaining.slice(part.length).trimStart();
 }
 return result;
}
module.exports={packets};
