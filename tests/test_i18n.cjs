const test=require('node:test'),assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const {UI_LANGUAGES,UI_TEXT,uiText,uiLabel}=require('../web/i18n.js');
test('UI languages are local and labels have complete English/Chinese pairs',()=>{
 assert.deepEqual(Object.keys(UI_LANGUAGES),['vi','en','zh']);
 for(const [key,value] of Object.entries(UI_TEXT)){assert.equal(value.length,2,key);assert(value.every(s=>typeof s==='string'&&s.length),key);}
 assert.equal(uiText('Cài đặt','en'),'Settings');assert.equal(uiText('Cài đặt','zh'),'设置');
 assert.equal(uiText('Cài thư viện','en'),'Install');assert.equal(uiText('Gỡ bỏ','zh'),'移除');
});
test('Icons, numeric steps and counters translate without changing their values',()=>{
 assert.equal(uiLabel('↓ Tải video / audio','en'),'↓ Download video / audio');
 assert.equal(uiLabel('◷ Lịch sử ','zh'),'◷ 历史记录 ');
 assert.equal(uiLabel('1. Phụ đề & nhận dạng','en'),'1. Subtitles & transcription');
 assert.equal(uiLabel('Đóng ×','en'),'Close ×');
 assert.equal(uiLabel('Đang chọn: Kim Thanh','en'),'Selected: Kim Thanh');
 assert.equal(uiLabel('171 ký tự · 26 từ','en'),'171 characters · 26 words');
 assert.equal(uiLabel('Ước tính audio: 5–8 giây · đã tính luật đọc','en'),'Estimated audio: 5–8s · reading rules included');
 assert.equal(uiLabel('Nam · Bắc · Phong cách tin tức','en'),'Male · Northern · News style');
 assert.equal(uiLabel('Private script is here','zh'),'Private script is here');
 assert.equal(uiLabel('↓ Tải video / audio','vi'),'↓ Tải video / audio');
});
test('Every main tab and major dynamic menu has both translations',()=>{
 for(const label of ['Văn bản đọc','Thư viện giọng','Bộ TTS · ngôn ngữ & diễn xuất','Lồng tiếng video','Biên tập video','Tải video / audio','Xóa phụ đề gốc','Hội thoại / Podcast','Đọc tài liệu','Lịch sử','Keyframe · bố cục','Phối nhiều lớp tự động','Chất lượng video đầu ra','Từ điển phát âm & viết tắt'])for(const lang of ['en','zh'])assert.notEqual(uiLabel(label,lang),label,label);
});
test('Reported populated-state labels translate with numbers and machine IDs intact',()=>{
 assert.equal(uiLabel('75 câu · 75 đã tạo','zh'),'75 句 · 已生成 75 句');
 assert.equal(uiLabel('720×1280 · nguồn 720×1280','en'),'720×1280 · source 720×1280');
 assert.equal(uiLabel('1 đã chọn','zh'),'1 已选');
 assert.equal(uiLabel('→ Lồng tiếng','zh'),'→ 配音');
 assert.equal(uiLabel('Bản cá nhân: chưa kết nối máy chủ bản quyền. Mã máy: machine-test-001','en'),'Personal edition: license server not connected. Machine ID: machine-test-001');
 assert.equal(uiLabel('Zoom','en'),'Zoom');assert.equal(uiLabel('Zoom','zh'),'缩放');
 for(const key of ['Mặc định: thư mục data của ứng dụng (video: trong dự án)','Preset nhiều track','Đã cài/kiểm tra và nhận diện thư viện. Cần thử đoạn ngắn để xác nhận chất lượng model trên máy.','Chưa thiết lập nguồn phát hành. Khi có nguồn, app luôn tự kiểm tra và tải bản mới.'])for(const lang of ['en','zh'])assert.notEqual(uiLabel(key,lang),key);
});
test('Native dialogs localize messages but preserve defaults, replies and cancellation',()=>{
 let seen,answer=null;const context={window:{confirm:m=>{seen=m;return false;},prompt:(m,v)=>{seen=[m,v];return answer;}}};vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../web/i18n.js'),'utf8'),context);vm.runInContext("uiLanguage='en'",context);
 assert.equal(context.window.confirm('Xóa nội dung đang soạn?'),false);assert.equal(seen,'Clear the text you are editing?');
 assert.equal(context.window.prompt('Tên dự án biên tập:','Cài đặt'),null);assert.deepEqual(seen,['Editor project name:','Cài đặt']);
 answer='Cài đặt';assert.equal(context.window.prompt('Tên track:','Nam'),'Cài đặt');assert.deepEqual(seen,['Track name:','Nam']);
});
test('Unknown user text is never translated; Vietnamese labels remain original',()=>{
 for(const original of ['SGK','My private script','key-sk-private','A video name.mp4','Xin chào thế giới'])assert.equal(uiText(original,'en'),original);
 assert.equal(uiText('Cài đặt','vi'),'Cài đặt');
});
