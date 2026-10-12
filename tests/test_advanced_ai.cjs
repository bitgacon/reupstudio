const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
const context=vm.createContext({document:{addEventListener(){}}});
for(const file of ['sequence-ui.js','advanced-ai.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),context);
const run=code=>JSON.parse(JSON.stringify(vm.runInContext(code,context)));
test('reacquisition proposal leaves gaps blank and does not mutate original',()=>{
  const doc={tracks:[]},result={start_ms:1000,duration_ms:5000,region_w:20,region_h:20,segments:[{start:0,end:200,keyframes:[{ms:0,x:30,y:50},{ms:200,x:30,y:50}]},{start:3000,end:5000,keyframes:[{ms:0,x:70,y:50},{ms:2000,x:70,y:50}]}]};
  const r=run(`seqTrackedProposal(${JSON.stringify(doc)},${JSON.stringify(result)},'',()=> 'id')`);
  assert.deepEqual(r.tracks[0].clips.map(c=>[c.start_ms,c.duration_ms]),[[1000,200],[4000,2000]]);
  assert.equal(doc.tracks.length,0);assert.equal(r.tracks[0].kind,'blur');assert.ok(r.tracks[0].clips.every(c=>c.keyframes.every(k=>k.ms<=c.duration_ms)));
});
test('reacquisition rejects short or missing segments instead of inserting invalid layer',()=>{
  assert.throws(()=>run(`seqTrackedProposal({tracks:[]},{start_ms:0,segments:[{start:0,end:50,keyframes:[{ms:0,x:50,y:50}]}]},'',()=> 'id')`),/không hợp lệ/);
});
