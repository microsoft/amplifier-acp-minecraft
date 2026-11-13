// The locked viewer's Entity.js expects THREE from its upstream bundler.
// Inject that dependency into browser modules without modifying node_modules.
const THREE = require('three');
export { THREE };
