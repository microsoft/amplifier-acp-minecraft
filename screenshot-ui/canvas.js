// The viewer's entity name labels use a browser canvas; no native canvas dependency.
exports.createCanvas=(width,height)=>Object.assign(document.createElement('canvas'),{width,height});
