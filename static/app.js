(function(){
"use strict";
var d=document;
function $(s,r){return (r||d).querySelector(s)}
function el(t,c,x){var e=d.createElement(t);if(c)e.className=c;if(x)e.textContent=x;return e}
var meta=null;
(function(){var t=d.getElementById("today");if(!t)return;try{t.textContent=new Date().toLocaleDateString("hi-IN",{weekday:"long",day:"numeric",month:"long",year:"numeric",timeZone:"Asia/Kolkata"})}catch(e){}})();
function manifest(){
  if(meta)return meta;
  var b=d.querySelector('link[rel="manifest"]').getAttribute("href").replace(/\/site\.webmanifest$/,"");
  meta=fetch(b+"/data/index.json").then(function(r){return r.json()}).then(function(m){m._b=b;return m});
  return meta;
}
function row(a,b){
  var li=el("li","row");li.dataset.slug=a.slug;li.dataset.c=a.category;
  var t=el("a","rthumb");t.href=a.url;t.tabIndex=-1;t.setAttribute("aria-hidden","true");
  if(a.image){var i=el("img");i.src=a.image;i.alt="";i.loading="lazy";i.decoding="async";i.width=a.tw||400;i.height=a.th||225;t.appendChild(i)}
  var w=el("div");
  var c=el("a","cat",a.category_name);c.href=b+"/category/"+a.category+"/";
  var h=el("h3"),l=el("a","",a.title);l.href=a.url;h.appendChild(l);
  var tm=el("time","",a.date_hi||"");
  w.appendChild(c);w.appendChild(h);w.appendChild(tm);li.appendChild(t);li.appendChild(w);return li;
}
/* home: aur khabrein */
var list=$("#latest-list"),btn=$("#more");
if(list&&btn){
  var chunks=null,n=0;
  manifest().then(function(m){chunks=m.latest;if(chunks&&chunks.length){btn.hidden=false;var a=$("#archive-link");if(a)a.hidden=true}});
  btn.addEventListener("click",function(){
    if(!chunks||n>=chunks.length)return;
    btn.disabled=true;
    manifest().then(function(m){return fetch(m._b+"/data/"+chunks[n]).then(function(r){return r.json()}).then(function(items){
      var seen={};[].forEach.call(list.children,function(li){seen[li.dataset.slug]=1});
      var top={};[].forEach.call(d.querySelectorAll(".top a[href]"),function(x){top[x.getAttribute("href")]=1});
      items.forEach(function(a){if(!seen[a.slug]&&!top[a.url])list.appendChild(row(a,m._b))});
      n++;btn.disabled=false;if(n>=chunks.length){btn.hidden=true;var al=$("#archive-link");if(al)al.hidden=false}
    })}).catch(function(){btn.disabled=false;btn.textContent="दोबारा कोशिश करें"});
  });
}
/* search page */
var q=$("#q"),res=$("#s-results"),st=$("#s-status");
if(q&&res){
  var idx=null,tm;
  var norm=function(s){return (s||"").toLowerCase()};
  function run(){
    var v=norm(q.value).trim();res.textContent="";
    if(v.length<2){st.textContent="खोजने के लिए कम से कम 2 अक्षर लिखें।";return}
    manifest().then(function(m){
      return idx||(idx=fetch(m._b+"/data/search.json").then(function(r){return r.json()}))
    }).then(function(all){
      var words=v.split(/\s+/),out=[];
      all.forEach(function(a){var hay=norm(a.t+" "+a.c+" "+(a.g||[]).join(" "));if(words.every(function(w){return hay.indexOf(w)>-1}))out.push(a)});
      st.textContent=out.length?out.length+" नतीजे मिले":"कोई नतीजा नहीं मिला। दूसरे शब्द आज़माएँ।";
      meta.then(function(m){out.slice(0,40).forEach(function(a){
        var li=el("li","row");li.style.gridTemplateColumns="1fr";var w=el("div");
        w.appendChild(el("span","cat",a.c));var h=el("h3"),l=el("a","",a.t);l.href=m._b+"/news/"+a.s+"/";h.appendChild(l);w.appendChild(h);li.appendChild(w);res.appendChild(li)})});
    }).catch(function(){st.textContent="खोज अभी उपलब्ध नहीं है।"});
  }
  q.addEventListener("input",function(){clearTimeout(tm);tm=setTimeout(run,200)});
  var p=new URLSearchParams(location.search).get("q");if(p){q.value=p;run()}
}
/* link copy */
d.addEventListener("click",function(e){
  var b=e.target.closest("[data-copy]");if(!b)return;
  var u=b.getAttribute("data-copy"),ok=function(){var o=b.textContent;b.textContent="कॉपी हो गया";setTimeout(function(){b.textContent=o},1800)};
  if(navigator.clipboard)navigator.clipboard.writeText(u).then(ok);else{var t=el("textarea");t.value=u;d.body.appendChild(t);t.select();try{d.execCommand("copy");ok()}catch(x){}d.body.removeChild(t)}
});
})();
