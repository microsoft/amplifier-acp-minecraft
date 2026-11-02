// Ordinary sign interaction. No operator commands or client-side NBT edits.
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function isSign(block){return !!block&&/_sign$/.test(block.name);}
function lines(text){return String(text||'').split('\n').concat(['','','','']).slice(0,4);}
function read(bot,p){
 const block=bot.blockAt(p);if(!isSign(block))throw Error('No loaded sign at that position');
 const [front='',back='']=block.getSignText();
 return {position:p,name:block.name,front:lines(front),back:lines(back),properties:block.getProperties(),waxed:!!block.blockEntity?.is_waxed};
}
function validate(value){
 if(!Array.isArray(value)||value.length<1||value.length>4||value.some(s=>typeof s!=='string'||s.length>45||/[\x00-\x1f\x7f]/.test(s)))throw Error('Use one to four plain lines, at most 45 characters each; short lines fit best.');
 return value.concat(['','','','']).slice(0,4);
}
async function write(bot,p,a,check,{wait=sleep,timeoutMs=3000}={}){
 const desired=validate(a.lines),side=a.side||'front',before=read(bot,p);
 if(!['front','back'].includes(side))throw Error('Choose front or back');
 if(p.offset(.5,.5,.5).distanceTo(bot.entity.position.offset(0,1.62,0))>4)throw Error('Move within four blocks of the sign first; writing never moves automatically.');
 if(before.waxed)throw Error('The sign is waxed and cannot be edited.');
 if(a.expected_lines&&JSON.stringify(validate(a.expected_lines))!==JSON.stringify(before[side]))throw Error('Sign text changed; read it again before replacing it.');
 if(JSON.stringify(before[side])===JSON.stringify(desired))return {...before,side,verified:true,changed:false};
 check();await bot.unequip('hand');check();
 let editor=null;
 const opened=packet=>{const q=packet.location;if(q&&q.x===p.x&&q.y===p.y&&q.z===p.z)editor=packet;};
 bot._client.on('open_sign_entity',opened);
 try{
  await bot.activateBlock(bot.blockAt(p));check();const deadline=Date.now()+timeoutMs;
  while(!editor&&Date.now()<deadline){await wait(50);check();}
  if(!editor)throw Error('Server did not open this sign for editing; check reach, wax or another player editing.');
  if(editor.isFrontText!==(side==='front'))throw Error(`You are facing the ${editor.isFrontText?'front':'back'} of the sign. Move to the requested ${side} side and retry; text was not changed.`);
  const current=read(bot,p);
  if(current.name!==before.name||JSON.stringify(current[side])!==JSON.stringify(before[side]))throw Error('Sign changed while opening its editor; read it again.');
  check();bot.updateSign(bot.blockAt(p),desired.join('\n'),side==='back');
  const until=Date.now()+timeoutMs;
  while(Date.now()<until){
   await wait(50);check();const actual=read(bot,p);
   if(actual.name===before.name&&JSON.stringify(actual[side])===JSON.stringify(desired))return {...actual,side,verified:true,changed:true};
  }
  throw Error('Server did not echo the requested sign text. Read the sign before retrying; text may have been rejected or changed.');
 }finally{bot._client.removeListener('open_sign_entity',opened);}
}
module.exports={isSign,read,write,validate};
