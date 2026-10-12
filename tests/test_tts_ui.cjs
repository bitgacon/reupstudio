const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/tts-provider-ui.js'),'utf8');
function context(saved=null){return vm.createContext({document:{addEventListener(){}},localStorage:{getItem:()=>saved},state:{selectedVoice:'old-vieneu'},$:id=>({value:id==='tts-text'?'Hello':'1'})});}
test('legacy TTS starts with VieNeu, broken preferences recover without network',()=>{
 const c=context('bad json');vm.runInContext(source,c);assert.equal(vm.runInContext('ttsSaved().provider',c),'vieneu');
 assert.equal(vm.runInContext('ttsGeneratePayload().voice',c),'old-vieneu');
});
test('external TTS cannot borrow stale VieNeu voice or silently consent cloud',()=>{
 const c=context(JSON.stringify({provider:'kokoro',language:'en-us'}));vm.runInContext(source,c);
 assert.throws(()=>vm.runInContext('ttsGeneratePayload()',c),/Chọn giọng/);
 vm.runInContext(`ttsMain={value:()=>({provider:'elevenlabs',language:'en',voice:'remote',cloud_consent:false})}`,c);
 assert.throws(()=>vm.runInContext('ttsGeneratePayload()',c),/cho phép/);
 vm.runInContext(`ttsMain={value:()=>({provider:'kokoro',language:'en-us',voice:'af_sarah'})}`,c);
 assert.equal(vm.runInContext('ttsGeneratePayload().voice',c),'af_sarah');
});
test('podcast keeps per-person language/emotion and old VieNeu mapping, excludes unused cloud character',()=>{
 const dom={'podcast-text':{value:'[Việt]: Xin chào\n[Alice]: Hello\n[Ryan]: Bonjour'},'podcast-rate':{value:'1'},'podcast-pause':{value:'.4'}};
 const saved=JSON.stringify({Alice:{provider:'kokoro',language:'en-us',voice:'af_sarah'},Ryan:{provider:'qwen',language:'fr',voice:'ryan',emotion:'happy'},Unused:{provider:'elevenlabs',voice:'cloud',cloud_consent:false}});
 const ctx=vm.createContext({document:{addEventListener(){}},localStorage:{getItem:()=>saved,setItem(){}},state:{speakers:{'Việt':'voice-old'}},$:id=>dom[id]});vm.runInContext(source,ctx);
 const payload=JSON.parse(JSON.stringify(vm.runInContext('podcastGeneratePayload()',ctx)));
 assert.equal(payload.speakers['Việt'],'voice-old');assert.equal(payload.speakers.Alice,'af_sarah');assert.equal(payload.speaker_tts.Ryan.language,'fr');assert.equal(payload.speaker_tts.Ryan.emotion,'happy');assert.equal(payload.speaker_tts.Unused,undefined);
 vm.runInContext(`podcastSpeechMap().Alice={provider:'elevenlabs',language:'en',voice:'cloud',cloud_consent:false}`,ctx);
 assert.throws(()=>vm.runInContext('podcastGeneratePayload()',ctx),/cho phép/);
});
