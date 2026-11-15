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
test('roster facts say why a player was classified; a server-attested agent is not reported as a human',()=>{
 const {AgentIdentity,offlineUuid}=require('../agent-identity.cjs');
 const bot=new EventEmitter(),events=[];bot.players={};
 const join=(username,uuid)=>{const p={username,uuid};bot.players[username]=p;bot.emit('playerJoined',p);};
 const identity=new AgentIdentity({username:'Builder',bot_names:['Peer'],human_names:['Guest'],agent_identity:{offline_uuid:true}},{players:()=>bot.players});
 new PlayerRoster(bot,identity,()=>true,(kind,fact)=>events.push({kind,...fact}));
 join('Peer','peer-id');join('NewAgent',offlineUuid('NewAgent'));join('Player','3f2b8c1e-9a4d-4e6f-8b7a-5c0d1e2f3a4b');join('Guest',offlineUuid('Guest'));join('Lookalike',undefined);
 assert.deepEqual(events.map(e=>[e.username,e.source,e.classified_by]),[['Peer','agent','configured'],['NewAgent','agent','server_offline_uuid'],['Player','human','unknown'],['Guest','human','human_override'],['Lookalike','unknown','unknown']]);
 assert.ok(events.every(e=>e.kind==='player_joined'&&e.provenance==='server_player_roster'));
 // The same roster without the policy keeps the list as its only source.
 const plain=new EventEmitter(),seen=[];plain.players={};new PlayerRoster(plain,['Peer'],()=>true,(kind,fact)=>seen.push(fact));
 plain.emit('playerJoined',{username:'NewAgent',uuid:offlineUuid('NewAgent')});assert.deepEqual([seen[0].source,seen[0].classified_by],['human','unknown']);
});
