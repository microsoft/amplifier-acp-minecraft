const test=require('node:test'),assert=require('node:assert/strict');
const {HumanActivity}=require('../human-activity.cjs');
test('walking is activity; stationary presence, known agents and missing identity are not',()=>{
 let now=1000;const tracker=new HumanActivity(['Maker'],{now:()=>now,activeMs:5000});
 const players={Human:{username:'Human',uuid:'h',entity:{position:{x:0,y:64,z:0}}},Maker:{username:'Maker',uuid:'m',entity:{position:{x:0,y:64,z:0}}},Unknown:{username:'Unknown',entity:{position:{x:0,y:64,z:0}}}};
 tracker.sample(players);assert.equal(tracker.snapshot().players.length,1);assert.equal(tracker.snapshot().players[0].active,false);
 players.Human.entity.position.x=0.3;tracker.sample(players);assert.equal(tracker.snapshot().players[0].active,true);
 now+=6000;tracker.sample(players);assert.equal(tracker.snapshot().players[0].active,false);
 tracker.sample({});assert.equal(tracker.snapshot().players.length,0);
});
test('small position changes accumulate; first observed presence and reconnect are not activity',()=>{
 const tracker=new HumanActivity([]),human={username:'Human',uuid:'h',entity:{position:{x:0,y:64,z:0}}};
 tracker.sample({human});human.entity.position.x=.1;tracker.sample({human});assert.equal(tracker.snapshot().players[0].active,false);
 human.entity.position.x=.3;tracker.sample({human});assert.equal(tracker.snapshot().players[0].active,true);
 tracker.sample({});tracker.sample({human});assert.equal(tracker.snapshot().players[0].active,false);
});
test('source callback reports actual movement times, never idle or first presence',()=>{
 let now=1000;const facts=[],tracker=new HumanActivity([],{now:()=>now,onMovement:f=>facts.push(f)}),human={username:'Human',uuid:'h',entity:{position:{x:0,y:64,z:0}}};
 tracker.sample({human});now=2000;tracker.sample({human});assert.equal(facts.length,0);
 human.entity.position.x=1;tracker.sample({human});assert.equal(facts.length,1);assert.equal(facts[0].at,2000);assert.equal(facts[0].from.x,0);assert.equal(facts[0].to.x,1);
});

test('attributed arm swing wakes activity for stationary humans, never mobs/peers/stale entities',()=>{
 let now=1000;const facts=[],tracker=new HumanActivity(['Peer'],{now:()=>now,onInteraction:f=>facts.push(f)});
 const entity={position:{x:0,y:64,z:0}},p={username:'Human',uuid:'h',entity},players={p};
 tracker.sample(players);tracker.interaction({...entity},players);assert.equal(facts.length,0);
 tracker.interaction(entity,players);assert.equal(facts.length,1);assert.equal(facts[0].kind,'interaction');
 assert.equal(tracker.snapshot().players[0].active,true);assert.equal(facts[0].at,1000);
 now+=120001;tracker.sample(players);assert.equal(tracker.snapshot().players[0].active,false);
 tracker.interaction(entity,{p:{...p,username:'Peer'}});tracker.interaction(entity,{p:{...p,uuid:null}});
 assert.equal(facts.length,1);
});
