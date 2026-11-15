const test=require('node:test'),assert=require('node:assert/strict');
const {AgentIdentity,agentIdentity,offlineUuid}=require('../agent-identity.cjs');
// Fictional accounts: a licensed Java login (version 4) and a Floodgate Bedrock id (zero high half).
const account='3f2b8c1e-9a4d-4e6f-8b7a-5c0d1e2f3a4b',bedrock='00000000-0000-0000-0009-01f3a5b6c7d8';
const human={kind:'human',classified_by:'unknown'},attested={kind:'agent',classified_by:'server_offline_uuid'},configured={kind:'agent',classified_by:'configured'};
// A server player list keyed by username; a bare name gets the offline UUID a server would derive for it.
const listed=(...entries)=>Object.fromEntries(entries.map(e=>Array.isArray(e)?e:[e,offlineUuid(e)]).map(([username,uuid])=>[username,{username,uuid}]));

test('offline UUID is the Java name UUID a server derives for an unauthenticated login',()=>{
 // Reference values from an independent MD5 name-UUID implementation; the first is widely published.
 assert.equal(offlineUuid('Notch'),'b50ad385-829d-3141-a216-7e7d7539ba7f');
 assert.equal(offlineUuid('BuilderOne'),'aeb7c013-68ea-3a7f-9946-96ee8c0b9be3');
 assert.equal(offlineUuid('NewAgent'),'4e58cb33-c147-34b1-abd4-32788d07825b');
 assert.notEqual(offlineUuid('notch'),offlineUuid('Notch'));
 for(const name of ['A','Builder_Two','x'.repeat(16)])assert.match(offlineUuid(name),/^[0-9a-f]{8}-[0-9a-f]{4}-3[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
test('configuration alone: bot_names and the own username are agents without case sensitivity, nobody else',()=>{
 const players=listed('NewAgent'),i=new AgentIdentity({username:'BuilderOne',bot_names:['BuilderTwo']},{players:()=>players});
 assert.deepEqual(i.classify('buildertwo'),configured);assert.deepEqual(i.classify('BUILDERONE'),configured);
 // The policy is off by default, so a matching offline UUID changes nothing.
 assert.deepEqual(i.classify('NewAgent',offlineUuid('NewAgent')),human);assert.equal(i.isAgent('NewAgent'),false);
 assert.deepEqual(i.agentNames(),['BuilderOne','BuilderTwo']);assert.deepEqual(i.policy(),{offline_uuid:false});
 for(const value of ['true',1,{},null])assert.equal(new AgentIdentity({agent_identity:{offline_uuid:value}}).isAgent('NewAgent',offlineUuid('NewAgent')),false);
 for(const name of [undefined,null,'',42])assert.deepEqual(i.classify(name),human);
});
test('opt-in policy: only a server-observed UUID equal to the offline UUID of that exact name is an agent',()=>{
 const players={...listed('NewAgent',['Player',account],['.Tablet',bedrock],['Lookalike',offlineUuid('NewAgent')]),Nameless:{username:'Nameless'}};
 const i=new AgentIdentity({username:'BuilderOne',agent_identity:{offline_uuid:true}},{players:()=>players});
 assert.deepEqual(i.classify('NewAgent',offlineUuid('NewAgent')),attested);assert.deepEqual(i.classify('NewAgent',offlineUuid('NewAgent').toUpperCase()),attested);
 // Without a supplied UUID the server's current player list answers for that exact name.
 assert.deepEqual(i.classify('NewAgent'),attested);assert.deepEqual(i.classify('newagent'),human);assert.deepEqual(i.policy(),{offline_uuid:true});
 // Licensed and Bedrock accounts, another name's offline UUID, and a supplied UUID that is not offline or not a UUID.
 for(const [name,uuid] of [['Player',account],['.Tablet',bedrock],['Lookalike',offlineUuid('NewAgent')],['NewAgent',account],['NewAgent','not-a-uuid'],['NewAgent',42]])assert.deepEqual(i.classify(name,uuid),human,name);
 for(const name of ['Player','.Tablet','Lookalike','Nameless','Absent','constructor','__proto__'])assert.deepEqual(i.classify(name),human,name);
});
test('an unknown server UUID falls back to configuration; an absent player is never guessed to be an agent',()=>{
 let players=listed('NewAgent');const i=new AgentIdentity({username:'BuilderOne',bot_names:['BuilderTwo'],agent_identity:{offline_uuid:true}},{players:()=>players});
 assert.equal(i.isAgent('NewAgent'),true);players={};assert.equal(i.isAgent('NewAgent'),false);assert.equal(i.isAgent('BuilderTwo'),true);
 players=null;assert.equal(i.isAgent('NewAgent'),false);
 // No player list attached: configuration, or a UUID the caller took from server attribution.
 const bare=new AgentIdentity({bot_names:['BuilderTwo'],agent_identity:{offline_uuid:true}});
 assert.equal(bare.isAgent('NewAgent'),false);assert.equal(bare.isAgent('BuilderTwo'),true);assert.equal(bare.isAgent('NewAgent',offlineUuid('NewAgent')),true);
});
test('human_names always wins; configuration precedes the server-attested kind',()=>{
 const players=listed('NewAgent','BuilderTwo',['Lead',account]);
 const i=new AgentIdentity({username:'BuilderOne',bot_names:['BuilderTwo','Lead','Former'],human_names:['newagent','FORMER'],agent_identity:{offline_uuid:true}},{players:()=>players});
 const override={kind:'human',classified_by:'human_override'};
 assert.deepEqual(i.classify('NewAgent',offlineUuid('NewAgent')),override);assert.deepEqual(i.classify('NewAgent'),override);assert.deepEqual(i.classify('Former'),override);
 assert.deepEqual(i.classify('BuilderTwo',offlineUuid('BuilderTwo')),configured);
 // A configured agent on a licensed account stays an agent.
 assert.deepEqual(i.classify('Lead',account),configured);
 assert.deepEqual(i.agentNames(),['BuilderOne','BuilderTwo','Lead']);assert.equal(i.canonical('former'),undefined);assert.equal(i.canonical('NEWAGENT'),undefined);
 assert.throws(()=>new AgentIdentity({username:'BuilderOne',human_names:['builderone']}),/own username/);
 for(const bad of [{human_names:'NewAgent'},{human_names:[7]},{bot_names:'Lead'},{bot_names:[null]}])assert.throws(()=>new AgentIdentity(bad),/must be a list of player names/);
 assert.deepEqual(new AgentIdentity({bot_names:['','Lead'],human_names:['']}).agentNames(),['Lead']);
});
test('agent names are configured spellings plus agents the server currently lists; canonical lookup ignores case',()=>{
 let players=listed('NewAgent',['Player',account]);
 const i=new AgentIdentity({username:'Bea',bot_names:['Lena','Omar','Bea'],agent_identity:{offline_uuid:true}},{players:()=>players});
 assert.deepEqual(i.agentNames(),['Bea','Lena','Omar','NewAgent']);
 assert.equal(i.canonical('omar'),'Omar');assert.equal(i.canonical('NEWAGENT'),'NewAgent');assert.equal(i.canonical('player'),undefined);assert.equal(i.canonical(''),undefined);
 players={};assert.deepEqual(i.agentNames(),['Bea','Lena','Omar']);assert.equal(i.canonical('newagent'),undefined);
 assert.deepEqual(new AgentIdentity({username:'Bea',bot_names:['Lena']},{players:()=>listed('NewAgent')}).agentNames(),['Bea','Lena']);
});
test('one identity per configuration object; a bare name list is configuration only',()=>{
 const cfg={username:'BuilderOne',bot_names:['BuilderTwo'],agent_identity:{offline_uuid:true}},players=listed('NewAgent');
 const early=agentIdentity(cfg);assert.equal(early.isAgent('NewAgent'),false);
 // The body attaches the live player list; every module holding the same cfg then sees it.
 assert.equal(agentIdentity(cfg,{players:()=>players}),early);assert.equal(agentIdentity(cfg).isAgent('NewAgent'),true);
 assert.equal(agentIdentity(early),early);assert.notEqual(agentIdentity({...cfg}),early);
 const bare=agentIdentity(['Peer']);assert.equal(bare.isAgent('peer'),true);assert.equal(bare.isAgent('NewAgent',offlineUuid('NewAgent')),false);
});
