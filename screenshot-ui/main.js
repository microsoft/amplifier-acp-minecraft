const THREE=require('three');
const TWEEN=require('@tweenjs/tween.js');
const {Viewer}=require('prismarine-viewer/viewer/lib/viewer');
(async()=>{
 const snapshot=await fetch('snapshot.json').then(r=>{if(!r.ok)throw Error('Snapshot unavailable');return r.json()});
 let texturesLoading=false,textureFailed=false;
 THREE.DefaultLoadingManager.onStart=()=>{texturesLoading=true};
 THREE.DefaultLoadingManager.onLoad=()=>{texturesLoading=false};
 THREE.DefaultLoadingManager.onError=()=>{textureFailed=true};
 const renderer=new THREE.WebGLRenderer({antialias:false,preserveDrawingBuffer:true});renderer.setPixelRatio(1);renderer.setSize(960,540);document.body.appendChild(renderer.domElement);
 const viewer=new Viewer(renderer);
 for(const worker of viewer.world.workers)worker.onerror=e=>{window.captureError='World renderer: '+e.message};
 if(!viewer.setVersion(snapshot.version))throw Error('Unsupported Minecraft rendering version');
 viewer.camera.fov=snapshot.camera.fov;viewer.camera.updateProjectionMatrix();
 viewer.camera.position.set(snapshot.camera.eye.x,snapshot.camera.eye.y,snapshot.camera.eye.z);viewer.camera.rotation.set(snapshot.camera.pitch,snapshot.camera.yaw,0,'ZYX');
 for(const c of snapshot.chunks)viewer.addColumn(c.x,c.z,c.chunk);
 // The upstream viewer defaults to 0..255; modern worlds also have sections
 // below zero and above 255. Request the loaded dimension's remaining range.
 for(const c of snapshot.chunks)for(let y=snapshot.minY;y<snapshot.minY+snapshot.height;y+=16)if(y<0||y>=256)viewer.world.setSectionDirty({x:c.x,y,z:c.z});
 for(const e of snapshot.entities)viewer.updateEntity(e);
 await viewer.waitForChunksToRender();
 while(texturesLoading||!viewer.world.material.map?.image?.complete){
  if(textureFailed)throw Error('Screenshot texture unavailable');
  await new Promise(r=>setTimeout(r,20));
 }
 if(textureFailed)throw Error('Screenshot texture unavailable');
 // This is one immutable snapshot, not the viewer's animation loop. Complete
 // its entity position/yaw tweens before capturing the recorded coordinates.
 TWEEN.update(Infinity);
 renderer.render(viewer.scene,viewer.camera);
 window.captureReady={loaded_chunks:snapshot.chunks.length};
})().catch(e=>{window.captureError=String(e.message||e);console.error(e)});
