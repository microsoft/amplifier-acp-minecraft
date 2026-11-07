const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {PlayerRoster}=require('../player-roster.cjs');
test('initial roster is not a join burst; subsequent server transitions are exact and deduplicated',()=>{
 const bot=new EventEmitter(),events=[];let ready=false;const visitor={username:'Visitor',uuid:'server-id'},peer={username:'Peer',uuid:'peer-id'};
 bot.players={Visitor:visitor};new PlayerRoster(bot,['Peer'],()=>ready,(kind,fact)=>events.push({kind,...fact}));
 bot.emit('playerJoined',visitor);bot.emit('spawn');ready=true;bot.emit('playerJoined',visitor);assert.equal(events.length,0);
 bot.emit('playerJoined',peer);bot.emit('playerJoined',peer);bot.emit('playerLeft',visitor);bot.emit('playerLeft',visitor);
 assert.deepEqual(events.map(e=>[e.kind,e.username,e.source]),[['player_joined','Peer','agent'],['player_left','Visitor','human']]);
 assert.equal(events[1].uuid,'server-id');assert.equal(events[1].message,undefined);
 ready=false;bot.emit('end');bot.emit('playerLeft',peer);assert.equal(events.length,2);
});
