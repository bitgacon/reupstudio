"use strict";
let readingConfig=null;
let readingEstimateSettings=null,readingEstimateTimer=null;
const pauseLabels={period:"Dấu chấm .",comma:"Dấu phẩy ,",question:"Dấu hỏi ?",exclamation:"Dấu chấm than !",colon:"Dấu hai chấm :",semicolon:"Dấu chấm phẩy ;",ellipsis:"Dấu ba chấm …",newline:"Xuống dòng"};
function setupReadingUI(){
  const controls=element("div","reading-actions");controls.append(makeButton("Ⅱ Thiết lập ngắt nghỉ",()=>openReading("pauses")),makeButton("Aᵃ Từ điển / viết tắt",()=>openReading("rules")));
  document.querySelector(".editor-tools").append(controls);
  const dialog=element("dialog","reading-dialog");dialog.id="reading-dialog";
  const header=element("div","card-heading"),title=element("h2");title.id="reading-title";header.append(title,makeButton("×",()=>dialog.close(),"icon"));
  const content=element("div");content.id="reading-content";
  const footer=element("div","reading-actions");footer.append(makeButton("Hủy",()=>dialog.close()),makeButton("Lưu thiết lập",saveReading,"primary"));
  dialog.append(header,element("p","hint","Lưu trên máy, dùng cho TTS, nghe thử clone, hội thoại và lồng tiếng. Chỉ đổi lúc đọc; văn bản gốc và SRT giữ nguyên."),content,footer);document.body.append(dialog);
  api("reading").then(value=>{readingEstimateSettings=value;estimateDuration();}).catch(()=>{});
}
async function openReading(mode){
  readingConfig=await api("reading");const body=$("reading-content");body.replaceChildren();$("reading-title").textContent=mode==="pauses"?"Thiết lập ngắt nghỉ":"Từ điển phát âm & viết tắt";
  if(mode==="pauses"){
    const label=element("label","check"),enabled=element("input");enabled.type="checkbox";enabled.checked=readingConfig.pauses.enabled;enabled.onchange=()=>readingConfig.pauses.enabled=enabled.checked;label.append(enabled,document.createTextNode(" Bật ngắt nghỉ theo dấu câu"));body.append(label);
    const grid=element("div","edit-fields");body.append(grid);
    for(const [key,name] of Object.entries(pauseLabels)){const field=element("label","field",name+" (giây)"),input=element("input");Object.assign(input,{type:"number",min:0,max:10,step:.1,value:readingConfig.pauses[key]});input.oninput=()=>readingConfig.pauses[key]=Number(input.value);field.append(input);grid.append(field);}
    body.append(element("p","hint","0 = giữ ngắt tự nhiên của model. Giá trị khác 0 chèn thêm khoảng lặng vào audio; model vẫn có thể có khoảng dừng tự nhiên. Dấu trong số 3.14, 1,000 và từ VieNeu.vn không bị tách."),element("p","hint","Nghỉ tại vị trí bất kỳ: gõ [0.8], [2] hoặc [nghỉ 0.8s]. Tối đa 30 giây mỗi thẻ. Bật nhiều dấu nghỉ có thể làm tổng hợp chậm hơn vì chia thành nhiều đoạn."));
    body.append(makeButton("Trở về đọc tự nhiên",()=>{readingConfig.pauses.enabled=false;enabled.checked=false;}));
  }else{
    const sample=element("label","field","Thử một câu"),input=element("input");input.id="reading-test-text";input.value="SGK giúp học sinh ôn bài.";sample.append(input);body.append(sample);
    const preview=element("p","notice");preview.id="reading-preview";body.append(preview);
    body.append(makeButton("Xem cách đọc",previewReading),makeButton("Lưu & nghe thử giọng đang chọn",async()=>{if(!state.selectedVoice)throw Error("Chọn giọng trong TTS trước.");await saveReading(false);await startTask("tts",{text:input.value,voice:state.selectedVoice,rate:Number($("tts-rate").value)},{play:true,title:"Thử từ điển"});}));
    const rows=element("div");rows.id="reading-rules";body.append(rows);
    const actions=element("div","reading-actions");actions.append(makeButton("＋ Thêm luật",()=>{if(readingConfig.rules.length>=500)throw Error("Tối đa 500 luật.");readingConfig.rules.push({source:"",spoken:"",whole_word:true,case_sensitive:false,enabled:true});renderReadingRules();}));
    const importer=element("label","field","Nhập TXT (mỗi dòng: SGK = Sách giáo khoa)"),file=element("input");file.type="file";file.accept=".txt";file.onchange=async()=>{try{if(!file.files[0])return;if(file.files[0].size>200000)throw Error("Tệp từ điển tối đa 200 KB.");const lines=(await file.files[0].text()).replace(/^\uFEFF/,"").split(/\r?\n/),rules=[];for(const line of lines){if(!line.trim()||line.trim().startsWith("#"))continue;const at=line.indexOf("=");if(at<1||!line.slice(at+1).trim())throw Error("Dòng cần có dạng từ = cách đọc: "+line.slice(0,80));rules.push({source:line.slice(0,at).trim(),spoken:line.slice(at+1).trim(),whole_word:true,case_sensitive:false,enabled:true});}if(rules.length+readingConfig.rules.length>500)throw Error("Tối đa 500 luật.");readingConfig.rules.push(...rules);renderReadingRules();toast("Đã nhập; bấm Lưu thiết lập để dùng.");}catch(e){toast(e.message,true);}};importer.append(file);actions.append(importer);body.append(actions,element("p","hint","Luật dài hơn ưu tiên trước; thay một lần, không thay dây chuyền. Ví dụ SGK → Sách giáo khoa; km/h → ki lô mét trên giờ. Không thay các thẻ cảm xúc hoặc nghỉ trong ngoặc vuông."));renderReadingRules();await previewReading();
  }
  $("reading-dialog").showModal();
}
function renderReadingRules(){
  const target=$("reading-rules");target.replaceChildren();if(!readingConfig.rules.length)target.append(element("p","hint","Chưa có luật. Bấm Thêm luật, nhập SGK và Sách giáo khoa."));
  readingConfig.rules.forEach((row,index)=>{const line=element("div","reading-rule");
    for(const [key,label] of [["source","Viết là"],["spoken","Đọc thành"]]){const field=element("label","field",label),input=element("input");input.value=row[key];input.maxLength=key==="source"?120:500;input.setAttribute("aria-label",label+" luật "+(index+1));input.oninput=()=>row[key]=input.value;field.append(input);line.append(field);}
    for(const [key,label] of [["whole_word","Cả từ"],["case_sensitive","Hoa/thường"],["enabled","Bật"]]){const field=element("label","check",label),input=element("input");input.type="checkbox";input.checked=row[key];input.onchange=()=>row[key]=input.checked;field.append(input);line.append(field);}line.append(makeButton("×",()=>{readingConfig.rules.splice(index,1);renderReadingRules();},"icon"));target.append(line);
  });
}
async function previewReading(){
  const settings={...readingConfig,rules:readingConfig.rules.filter(r=>r.source.trim()&&r.spoken.trim())};const response=await api("reading-preview",{text:$("reading-test-text").value,settings});$("reading-preview").textContent="Engine đọc: "+response.pieces.map(p=>p.spoken??`[nghỉ ${p.silence/1000}s]`).join(" ");
}
async function saveReading(close=true){
  const empty=readingConfig.rules.find(r=>!r.source.trim()||!r.spoken.trim());if(empty)throw Error("Mỗi luật cần đủ Viết là và Đọc thành; xóa dòng trống nếu không dùng.");
  readingConfig=await api("reading",readingConfig);readingEstimateSettings=readingConfig;estimateDuration();toast("Đã lưu ngắt nghỉ và từ điển trên máy.");if(close)$("reading-dialog").close();
}
function scheduleReadingEstimate(){
  clearTimeout(readingEstimateTimer);const settings=readingEstimateSettings,text=$("tts-text").value,rate=Number($("tts-rate").value);
  if(!settings||(!settings.pauses.enabled&&!settings.rules.some(r=>r.enabled))||text.length>10000)return;
  readingEstimateTimer=setTimeout(async()=>{try{const {pieces}=await api("reading-preview",{text,settings});if($("tts-text").value!==text||Number($("tts-rate").value)!==rate)return;
    const words=pieces.filter(p=>p.spoken).map(p=>p.spoken.replace(/\[[^\]]*\]/g,"")).join(" ").trim().split(/\s+/).filter(Boolean).length;
    const pauses=pieces.reduce((n,p)=>n+(p.silence||0),0)/1000,seconds=words/4.5/rate;
    $("audio-estimate").textContent=words||pauses?`Ước tính audio: ${Math.max(1,Math.round(seconds*.8+pauses))}–${Math.max(1,Math.ceil(seconds*1.25+pauses))} giây · đã tính luật đọc`:"Ước tính audio: 0 giây";
  }catch{}},300);
}
