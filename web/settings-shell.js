"use strict";
const SETTINGS_SECTIONS=[['general','☷','Chung'],['appearance','◐','Giao diện'],['transcriber','▥','Nhận dạng'],['speech','♫','Giọng đọc'],['translation','⇄','Dịch & API'],['libraries','▦','Thư viện'],['storage','▣','Lưu trữ'],['ai','✧','AI nâng cao'],['about','ⓘ','Ứng dụng & bản quyền']];
let settingsSection='general',settingsScroll={},uiPrefs={language:'vi',theme:'light',density:'compact'};
function settingsChoose(section,focus=false){
 if(!SETTINGS_SECTIONS.some(r=>r[0]===section))section='general';
 const content=$('settings-content');settingsScroll[settingsSection]=content.scrollTop;settingsSection=section;
 document.querySelectorAll('.settings-page').forEach(p=>p.hidden=p.id!=='settings-'+section);
 document.querySelectorAll('#settings-nav button').forEach(b=>{const active=b.dataset.section===section;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;if(active&&focus)b.focus();});
 content.scrollTop=settingsScroll[section]||0;localStorage.setItem('rv-settings-section',section);
 if(section==='libraries')refreshLibraries().catch(e=>toast(e.message,true));
 if(section==='ai')settingsAIReadiness().catch(e=>toast(e.message,true));
}
function settingsPlacePanels(){
 const mapping=[['#optional-libraries','libraries'],['#advanced-ai-settings','ai'],['#tts-provider-settings','speech'],['.storage-settings:not([id])','storage'],['.distribution-card','about']];
 for(const [selector,section] of mapping){const node=$('settings-form').querySelector(selector),target=$('settings-'+section);if(node&&node.parentElement!==target){if(node.tagName==='DETAILS')node.open=true;target.append(node);}}
 // Tool links call settingsChoose explicitly. Delayed details toggle events must
 // never steal the selected page or scroll position.
}
function settingsApplyUI(prefs){
 uiPrefs={...uiPrefs,...prefs};uiSetLanguage(uiPrefs.language);
 const theme=uiPrefs.theme==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):uiPrefs.theme;
 document.documentElement.dataset.theme=theme;document.documentElement.dataset.density=uiPrefs.density;localStorage.setItem('rv-theme',theme);
 for(const key of ['language','theme','density'])$('ui-'+key).value=uiPrefs[key];
}
async function settingsSaveUI(value){
 const previous={...uiPrefs};settingsApplyUI(value);
 try{const saved=await api('ui-preferences',value);settingsApplyUI(saved);$('settings-save-info').textContent='Đã lưu giao diện';}
 catch(e){settingsApplyUI(previous);throw e;}
}
async function settingsAIReadiness(){
 const rows=await api('advanced-ai/status'),box=$('ai-readiness');box.replaceChildren();
 for(const row of rows.features){const card=element('article');card.dataset.ready=String(row.files_ready);card.append(element('strong','',row.name),element('p','hint',row.id==='compose'?'Có thể dùng · xử lý trên máy':row.files_ready?'Đã có file · chưa kiểm tra suy luận':'Cần cài/kết nối'),element('p','hint',row.message));box.append(card);}
}
document.addEventListener('DOMContentLoaded',()=>{
 const nav=$('settings-nav');nav.setAttribute('role','tablist');nav.setAttribute('aria-orientation','vertical');
 for(const [id,icon,title] of SETTINGS_SECTIONS){const b=element('button');b.type='button';b.id='settings-tab-'+id;b.dataset.section=id;b.setAttribute('role','tab');b.setAttribute('aria-controls','settings-'+id);b.append(element('span','settings-symbol',icon),element('span','',title));b.onclick=()=>settingsChoose(id);b.onkeydown=e=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;e.preventDefault();const n=SETTINGS_SECTIONS.findIndex(r=>r[0]===settingsSection),next=e.key==='Home'?0:e.key==='End'?SETTINGS_SECTIONS.length-1:(n+(e.key==='ArrowDown'?1:-1)+SETTINGS_SECTIONS.length)%SETTINGS_SECTIONS.length;settingsChoose(SETTINGS_SECTIONS[next][0],true);};nav.append(b);const panel=$('settings-'+id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',b.id);}
 document.querySelectorAll('[data-settings-go]').forEach(b=>b.onclick=()=>settingsChoose(b.dataset.settingsGo));
 settingsPlacePanels();new MutationObserver(settingsPlacePanels).observe($('settings-form'),{childList:true,subtree:true});
 settingsChoose(localStorage.getItem('rv-settings-section')||'general');
 for(const key of ['language','theme','density'])on('ui-'+key,'change',()=>settingsSaveUI({[key]:$('ui-'+key).value}));
 on('settings-open','click',()=>{settingsPlacePanels();settingsChoose(settingsSection);});
 on('theme','click',()=>settingsSaveUI({theme:document.documentElement.dataset.theme}));
 matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if(uiPrefs.theme==='system')settingsApplyUI(uiPrefs);});
 api('ui-preferences').then(p=>{if(!p.configured)p.theme=localStorage.getItem('rv-theme')||p.theme;settingsApplyUI(p);}).catch(e=>toast(e.message,true));
});
