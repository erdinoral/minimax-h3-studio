const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict'),test=require('node:test');
const translations=fs.readFileSync('studio/static/i18n.js','utf8');
function dictionary(){const window={};vm.runInNewContext(translations,{window,document:{addEventListener(){}},localStorage:{getItem:()=> 'en'}});return window.H3_I18N;}
test('all localized markup has EN and TR translations, including accessibility labels',()=>{
 const dict=dictionary();const html=fs.readFileSync('studio/static/index.html','utf8');
 for(const match of html.matchAll(/data-i18n(?:-placeholder|-title|-aria-label|-empty)?="([^"]+)"/g))for(const lang of ['tr','en'])assert.ok(dict[lang][match[1]],`${lang}: ${match[1]}`);
 for(const [key,value] of Object.entries(dict.en))assert.doesNotMatch(value,/[çğıöşüÇĞİÖŞÜ]/,key);
});
test('system status labels translate while scene text and unknown labels remain intact',()=>{
 const dict=dictionary();let lang='en';const source=fs.readFileSync('studio/static/app.js','utf8');const start=source.indexOf('  function localizeSystemLabel('),end=source.indexOf('  function errDetail(',start);
 const context={tt:k=>dict[lang][k]||k,tf:(k,args)=>Object.entries(args).reduce((s,[name,val])=>s.replace('{'+name+'}',val),dict[lang][k]||k)};
 vm.createContext(context);vm.runInContext(source.slice(start,end),context);
 assert.equal(context.localizeSystemLabel('örnekleme 4/20 · 12s'),'Sampling 4/20 · 12s');
 assert.equal(context.localizeSystemLabel('Comfy kuyruğunda · 2m03s'),'In Comfy queue · 2m03s');
 const scene='NEA boş metroda yürür.';assert.equal(context.localizeSystemLabel(scene),scene);
 lang='tr';assert.equal(context.localizeSystemLabel('sırada'),'sırada');
});
