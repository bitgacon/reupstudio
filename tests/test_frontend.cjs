// Source-level tests, not a browser or visual-layout acceptance test.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
test('timed tracks clamp move and trim without zero duration; end is exclusive',()=>{
  const ctx=vm.createContext({});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/layers-ui.js'),'utf8'),ctx);
  const run=code=>JSON.parse(JSON.stringify(vm.runInContext(code,ctx)));
  assert.deepEqual(run('trimInterval(1000,3000,-5000,null,5000)'),{start_ms:0,end_ms:2000});
  assert.deepEqual(run('trimInterval(1000,3000,5000,"start",5000)'),{start_ms:2900,end_ms:3000});
  assert.deepEqual(run('trimInterval(1000,3000,-5000,"end",5000)'),{start_ms:1000,end_ms:1100});
  assert.equal(run('timedActive({start_ms:1000,end_ms:2000},2000)'),false);
  assert.equal(run('timedActive({start_ms:1000,end_ms:null},20000)'),true);
});
test('voice selection keeps existing rows, focus target and scroll offset',()=>{
  const rows=['first','last'].map(id=>({dataset:{voiceId:id},classList:{toggle(name,value){this.selected=value;}},setAttribute(name,value){this[name]=value;}}));
  const list={scrollTop:850,querySelectorAll(){return rows;},replaceChildren(){throw Error('Selection must not rebuild the list');}};
  const label={};const context=vm.createContext({state:{selectedVoice:'first',voices:[{id:'last',name:'Giọng cuối'}]},localStorage:{setItem(){}},$:id=>id==='voice-list'?list:label});
  const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
  vm.runInContext(source.slice(source.indexOf('function selectVoice('),source.indexOf('function renderVoices(')),context);
  vm.runInContext('selectVoice("last")',context);
  assert.equal(list.scrollTop,850);assert.equal(rows[1]['aria-checked'],'true');assert.equal(rows[0]['aria-checked'],'false');assert.equal(label.textContent,'Đang chọn: Giọng cuối');
});
function fixture(){
  const area={value:'',selectionStart:0,selectionEnd:0,focus(){},setRangeText(text,start,end){this.value=this.value.slice(0,start)+text+this.value.slice(end);this.selectionStart=start;this.selectionEnd=start+text.length;}};
  const dom={'tts-text':{value:''},'tts-rate':{value:1},'audio-estimate':{textContent:''},'podcast-text':area,'app-version':{},'ui-update-notice':{hidden:true,classList:{toggle(name,value){dom['ui-update-notice'].hidden=value;}}}};
  const messages=[];const context=vm.createContext({$:id=>dom[id],document:{querySelector(){return {content:'build-current'};}},localStorage:{setItem(){}},renderSpeakers(){},toast:m=>messages.push(m)});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/editor-ui.js'),'utf8'),context);
  return {area,dom,context,messages,run:code=>vm.runInContext(code,context)};
}
test('matching UI build hides update notice; different build warns without reload',()=>{
  const f=fixture();f.run('updateBuildStatus("build-current")');assert.equal(f.dom['ui-update-notice'].hidden,true);
  f.run('updateBuildStatus("build-new")');assert.equal(f.dom['ui-update-notice'].hidden,false);
  assert.match(f.dom['app-version'].title,/build-new/);
  f.run('updateBuildStatus(undefined)');assert.equal(f.dom['ui-update-notice'].hidden,true);
});
test('empty estimate and rate-aware duration including explicit silence',()=>{
  const f=fixture();f.run('estimateDuration()');assert.equal(f.dom['audio-estimate'].textContent,'Ước tính audio: 0 giây');
  f.dom['tts-text'].value='Xin chào các bạn [nghỉ 1s]';f.run('estimateDuration()');assert.match(f.dom['audio-estimate'].textContent,/2–3 giây/);
  f.dom['tts-rate'].value=2;f.run('estimateDuration()');assert.match(f.dom['audio-estimate'].textContent,/1–2 giây/);
  f.dom['tts-text'].value='[2]';f.run('estimateDuration()');assert.match(f.dom['audio-estimate'].textContent,/2–2 giây/);
});
test('assign selected dialogue without dropping unselected text',()=>{
  const f=fixture();f.area.value='Trước\nXin chào\nSau';f.run('ui.selection=[6,14];assignCharacter("Nhân vật 3")');
  assert.equal(f.area.value,'Trước\n[Nhân vật 3]: Xin chào\nSau');
});
test('replace old speaker tags in multi-line selection',()=>{
  const f=fixture();f.area.value='[Host]: Câu một\n[Khách]: Câu hai';f.run(`ui.selection=[0,${f.area.value.length}];assignCharacter("Người thứ tư")`);
  assert.equal(f.area.value,'[Người thứ tư]: Câu một\nCâu hai');
});
test('click without selection does not change dialogue',()=>{
  const f=fixture();f.area.value='Giữ nguyên';f.run('assignCharacter("Host")');assert.equal(f.area.value,'Giữ nguyên');assert.equal(f.messages.length,1);
});
test('portrait output matches backend contain and cover geometry',()=>{
  const f=fixture();let g=f.run('canvasGeometry(1280,720,{output_ratio:"9:16",video_fit:"contain"})');
  assert.deepEqual([g.w,g.h,g.sw,g.sh,g.left,g.top],[720,1280,720,406,0,437]);
  g=f.run('canvasGeometry(1280,720,{output_ratio:"9:16",video_fit:"cover",video_x:100})');
  assert.deepEqual([g.w,g.h,g.sw,g.sh,g.left,g.top],[720,1280,2276,1280,-1556,0]);
});
test('custom canvas and rotated source keep center placement',()=>{
  const f=fixture(),g=f.run('canvasGeometry(1280,720,{output_ratio:"custom",output_width:1000,output_height:1000,rotation:90})');
  assert.deepEqual([g.w,g.h,g.sw,g.sh],[1000,1000,1000,562]);
  assert.ok(Math.abs(g.rw-562)<.00001);assert.ok(Math.abs(g.rh-1000)<.00001);
  assert.equal(g.left,0);assert.equal(g.top,219);
});
test('mask coordinates invert zoom, crop, offset and rotation',()=>{
  const f=fixture();
  for(const angle of [-90,-30,0,45,90,180]){
    const result=f.run(`(()=>{const c={output_ratio:'9:16',video_fit:'cover',zoom:1.5,rotation:${angle},video_x:70,video_y:30},g=canvasGeometry(1280,720,c),a=c.rotation*Math.PI/180,dx=g.sw*(.25-.5),dy=g.sh*(.8-.5);return sourcePoint(g.left+g.sw/2+dx*Math.cos(a)-dy*Math.sin(a),g.top+g.sh/2+dx*Math.sin(a)+dy*Math.cos(a),g,c.rotation);})()`);
    assert.ok(Math.abs(result.x-25)<.00001);assert.ok(Math.abs(result.y-80)<.00001);
  }
});
test('mask draw reverse directions and boundaries remain valid',()=>{
  const f=fixture(),rect=f.run('maskBounds({x:80,y:90},{x:10,y:20})');
  assert.deepEqual([rect.mask_x,rect.mask_y,rect.mask_w,rect.mask_h],[10,20,70,70]);
  const edge=f.run('maskBounds({x:120,y:120},{x:120,y:120})');
  assert.deepEqual([edge.mask_x,edge.mask_y,edge.mask_w,edge.mask_h],[99,99,1,1]);
  const whole=f.run('maskBounds({x:-20,y:-15},{x:140,y:140})');
  assert.deepEqual([whole.mask_x,whole.mask_y,whole.mask_w,whole.mask_h],[0,0,100,100]);
});
