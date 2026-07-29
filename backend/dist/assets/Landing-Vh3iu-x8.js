import{u as P,a as E,r as n,j as e,t as g,G as u}from"./index-DWgcX8Xm.js";import{a as T}from"./api-DXCafRhN.js";import{u as O,a as R,T as z,C as L,r as A,b as v,c as $,d as I,S as N,p as D,e as M,f as B}from"./shared-BfpJX4w4.js";import{R as U,L as H,Y as F,a as G}from"./LineChart-Dzfk13GY.js";const w=["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","LINK","DOT","NEAR","APT","ARB","OP","SUI","PEPE","WIF"];function W(){const[s,a]=n.useState(null),[c,f]=n.useState([]);n.useEffect(()=>{async function o(){try{const[x,h]=await Promise.all([T.getStats(),T.getHistory(500,30)]);a(x),f(h)}catch{}}o();const l=setInterval(o,6e4);return()=>clearInterval(l)},[]);const p=n.useMemo(()=>D(c),[c]),b=n.useMemo(()=>p.slice(0,8),[p]),d=n.useMemo(()=>M(c),[c]),t=n.useMemo(()=>B(s,p),[s,p]);return{stats:s,recent:b,curve:d,display:t}}function Y({prices:s,t:a}){const[c,f]=n.useState(0),[p,b]=n.useState([]);n.useEffect(()=>{const t=setInterval(()=>{f(o=>{const l=(o+1)%w.length,x=w[l],h=[a("land.scan.a1"),a("land.scan.a2"),a("land.scan.a3"),a("land.scan.a4"),a("land.scan.a5")],q=h[l%h.length];return b(j=>[`${x}/USDT · ${q}`,...j].slice(0,5)),l})},900);return()=>clearInterval(t)},[a]);const d=w[c];return e.jsxs("div",{className:"scanner","aria-hidden":"true",children:[e.jsxs("div",{className:"scanner-top",children:[e.jsxs("span",{className:"tl-row","aria-hidden":"true",children:[e.jsx("span",{className:"tl r"}),e.jsx("span",{className:"tl a"}),e.jsx("span",{className:"tl g"})]}),e.jsxs("span",{className:"live-pill",children:[e.jsx("span",{className:"live-dot"})," ONLINE"]}),e.jsx("span",{className:"scanner-title",children:a("land.scan.widgetTitle")}),s&&e.jsxs("span",{className:"scanner-tickers",children:["BTC $",s.btc.price," · ETH $",s.eth.price]})]}),e.jsxs("div",{className:"scanner-body",children:[e.jsxs("div",{className:"radar",children:[e.jsx("div",{className:"ring"}),e.jsx("div",{className:"ring r2"}),e.jsx("div",{className:"ring r3"}),e.jsx("div",{className:"sweep"}),e.jsx("div",{className:"core",children:d}),w.slice(0,8).map((t,o)=>{const l=o/8*Math.PI*2-Math.PI/2,x=36+o%3*10;return e.jsx("span",{className:`blip ${t===d?"on":""}`,style:{left:`${50+Math.cos(l)*x}%`,top:`${50+Math.sin(l)*x}%`}},t)})]}),e.jsxs("div",{className:"scan-feed",children:[e.jsxs("div",{className:"scan-now",children:[a("land.scan.now")," ",e.jsxs("b",{children:[d,"/USDT"]})]}),e.jsx("ul",{children:p.map((t,o)=>e.jsx("li",{children:t},`${t}-${o}`))})]})]})]})}function J(){const s=P(),{t:a,lang:c,setLang:f,locales:p}=E(),b=O(),{recent:d,curve:t,display:o}=W(),[l,x]=n.useState(null),h=n.useMemo(()=>[{q:a("land.faq.q1"),a:a("land.faq.a1")},{q:a("land.faq.q2"),a:a("land.faq.a2")},{q:a("land.faq.q3"),a:a("land.faq.a3")},{q:a("land.faq.q4"),a:a("land.faq.a4")}],[a]),q=n.useMemo(()=>[{key:"free",name:a("land.tier.free.name"),price:"0",unit:a("land.tier.free.unit"),features:[a("land.tier.free.f1"),a("land.tier.free.f2"),a("land.tier.free.f3")]},{key:"premium",name:a("land.tier.premium.name"),price:"29",unit:a("land.tier.premium.unit"),features:[a("land.tier.premium.f1"),a("land.tier.premium.f2"),a("land.tier.premium.f3")],popular:!0},{key:"premium3",name:a("land.tier.premium3.name"),price:"75",unit:a("land.tier.premium3.unit"),features:[a("land.tier.premium3.f1"),a("land.tier.premium3.f2"),a("land.tier.premium3.f3")]},{key:"lifetime",name:a("land.tier.lifetime.name"),price:"299",unit:a("land.tier.lifetime.unit"),features:[a("land.tier.lifetime.f1"),a("land.tier.lifetime.f2"),a("land.tier.lifetime.f3")]}],[a]),[j,C]=n.useState(!1),[y,_]=n.useState(()=>{const r=localStorage.getItem("theme");return r?r==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches});R([d,o]),n.useEffect(()=>{document.documentElement.setAttribute("data-theme",y?"dark":"light"),localStorage.setItem("theme",y?"dark":"light")},[y]);const k=t.length?t[t.length-1].equity:null,S=k==null?null:k>=0,m=r=>{var i;C(!1),r.startsWith("#")?(i=document.querySelector(r))==null||i.scrollIntoView({behavior:"smooth"}):s(r)};return e.jsxs("div",{className:"lp",children:[e.jsx("nav",{className:"navbar glass","aria-label":a("land.nav.aria"),children:e.jsxs("div",{className:"nav-inner",children:[e.jsxs("button",{type:"button",className:"nav-logo",onClick:()=>window.scrollTo({top:0,behavior:"smooth"}),children:[e.jsx("span",{className:"nav-mark",children:"N"}),e.jsx("span",{className:"nav-word",children:"NOWICKI"})]}),e.jsxs("div",{className:`nav-links ${j?"open":""}`,children:[e.jsx("a",{href:"#signals",onClick:r=>{r.preventDefault(),m("#signals")},children:a("land.nav.signals")}),e.jsx("a",{href:"#pricing",onClick:r=>{r.preventDefault(),m("#pricing")},children:a("land.nav.pricing")}),e.jsx("a",{href:"#about",onClick:r=>{r.preventDefault(),m("#about")},children:a("land.nav.about")}),e.jsx("a",{href:"#support",onClick:r=>{r.preventDefault(),m("#support")},children:a("land.nav.support")}),e.jsx("a",{href:z,target:"_blank",rel:"noopener noreferrer",children:a("land.nav.results")})]}),e.jsxs("div",{className:"nav-right",children:[e.jsx("div",{className:"lang-switch",role:"group","aria-label":"Language",children:p.map(r=>e.jsx("button",{type:"button",className:`lang-btn ${c===r.code?"active":""}`,onClick:()=>f(r.code),children:r.short},r.code))}),e.jsx("button",{type:"button",className:"theme-btn","aria-label":a("land.theme.aria"),onClick:()=>_(r=>!r),children:y?"☀":"☾"}),e.jsx("button",{type:"button",className:"btn-ghost",onClick:()=>s("/app/overview?auth=login"),children:a("top.login")}),e.jsx("button",{type:"button",className:"btn-solid",onClick:()=>s("/app/overview?auth=register"),children:a("land.start")}),e.jsxs("button",{type:"button",className:"burger","aria-label":a("land.menu.aria"),"aria-expanded":j,onClick:()=>C(r=>!r),children:[e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{})]})]})]})}),e.jsxs("section",{className:"hero",children:[e.jsx("div",{className:"hero-plane","aria-hidden":"true"}),e.jsxs("div",{className:"hero-grid",children:[e.jsxs("div",{className:"hero-copy animate-in",children:[e.jsxs("span",{className:"eyebrow",children:[e.jsx("span",{className:"live-dot"})," ",a("land.hero.eyebrow")]}),e.jsxs("h1",{children:[a("land.hero.titleLine1"),e.jsx("br",{}),a("land.hero.titleLine2")]}),e.jsx("p",{children:a("land.hero.desc")}),e.jsxs("div",{className:"hero-cta",children:[e.jsx("button",{type:"button",className:"btn-solid lg",onClick:()=>s("/app/overview?auth=register"),children:a("land.hero.ctaSignals")}),e.jsx("button",{type:"button",className:"btn-ghost lg",onClick:()=>m("#signals"),children:a("land.hero.ctaTrack")})]}),e.jsxs("div",{className:"hero-stats",children:[e.jsxs("div",{children:[e.jsx(L,{className:"hs-num",value:o.winrate,suffix:"%"}),e.jsx("span",{children:a("land.hero.statWinrate")})]}),e.jsxs("div",{children:[e.jsx(L,{className:"hs-num",value:o.total}),e.jsx("span",{children:a("land.hero.statTrades")})]}),e.jsxs("div",{children:[e.jsxs("span",{className:"hs-num pos",children:["+",o.avgPnl,"%"]}),e.jsx("span",{children:a("land.hero.statAvgPnl")})]})]})]}),e.jsxs("div",{className:"hero-stage animate-in",children:[e.jsx(Y,{prices:b,t:a}),e.jsxs("div",{className:"equity-mini",children:[e.jsxs("div",{className:"eq-meta",children:[e.jsx("span",{children:a("land.equity.label")}),e.jsx("strong",{className:S?"pos":"neg",children:k!=null?`${S?"+":""}${k.toFixed(1)}%`:"—"})]}),e.jsx("div",{className:"eq-chart",children:t.length>1&&e.jsx(U,{width:"100%",height:"100%",children:e.jsxs(H,{data:t,children:[e.jsx(F,{hide:!0,domain:["auto","auto"]}),e.jsx(G,{type:"monotone",dataKey:"equity",stroke:"var(--accent)",strokeWidth:2.2,dot:!1,animationDuration:1e3})]})})})]})]})]})]}),e.jsx("section",{id:"signals",className:"section",children:e.jsxs("div",{className:"inner",children:[e.jsx("h2",{className:"sec-title reveal",children:a("land.signals.title")}),e.jsx("p",{className:"sec-sub reveal",children:a("land.signals.sub")}),e.jsxs("div",{className:"signal-lock-wrap reveal",children:[e.jsxs("div",{className:"signal-rows signal-blur",children:[d.map(r=>{const i=(r.pnl??0)>=0;return e.jsxs("div",{className:"sig-row","aria-hidden":"true",children:[e.jsx("span",{className:"mono",children:r.symbol.replace("/USDT","")}),e.jsx("span",{className:`dir ${r.signal==="LONG"?"long":"short"}`,children:r.signal}),e.jsx("span",{className:"muted",children:A(a,r.result)}),e.jsxs("span",{className:`mono ${i?"pos":"neg"}`,children:[i?"+":"",r.pnl,"%"]})]},r.id)}),!d.length&&e.jsx("div",{className:"muted pad",children:a("land.signals.empty")})]}),!!d.length&&e.jsxs("div",{className:"signal-lock",children:[e.jsx("span",{className:"signal-lock-icon",children:"🔒"}),e.jsx("span",{className:"signal-lock-text",children:a("land.signals.lockText")}),e.jsx("button",{type:"button",className:"btn-solid",onClick:()=>{g(u.telegramBot,{source:"landing_signals_lock"}),window.open(`${v}?start=premium`,"_blank","noopener,noreferrer")},children:a("land.signals.unlock")}),e.jsx("button",{type:"button",className:"btn-ghost",onClick:()=>s("/app/overview?auth=register"),children:a("land.signals.registerCta")})]})]})]})}),e.jsx("section",{id:"about",className:"section alt",children:e.jsxs("div",{className:"inner about",children:[e.jsxs("div",{className:"reveal",children:[e.jsx("h2",{className:"sec-title",children:a("land.about.title")}),e.jsxs("ul",{className:"honest-list",children:[e.jsx("li",{children:a("land.about.b1")}),e.jsx("li",{children:a("land.about.b2")}),e.jsx("li",{children:a("land.about.b3")}),e.jsx("li",{children:a("land.about.b4")})]})]}),e.jsxs("div",{className:"honest-cta reveal",children:[e.jsx("a",{className:"btn-solid",href:v,target:"_blank",rel:"noopener noreferrer",onClick:()=>g(u.telegramBot,{source:"landing_about"}),children:a("land.about.openBot")}),e.jsx("a",{className:"btn-ghost",href:z,target:"_blank",rel:"noopener noreferrer",children:a("land.about.viewResults")})]})]})}),e.jsx("section",{id:"pricing",className:"section",children:e.jsxs("div",{className:"inner",children:[e.jsx("h2",{className:"sec-title reveal",children:a("land.pricing.title")}),e.jsx("p",{className:"sec-sub reveal",children:a("land.pricing.sub")}),e.jsx("div",{className:"price-grid reveal",children:q.map(r=>e.jsxs("div",{className:`price-card ${r.popular?"popular":""}`,children:[r.popular&&e.jsx("span",{className:"pop",children:a("land.pricing.popular")}),e.jsx("div",{className:"price-name",children:r.name}),e.jsxs("div",{className:"price-amt",children:["$",r.price,e.jsx("small",{children:r.unit})]}),e.jsx("ul",{children:r.features.map(i=>e.jsx("li",{children:i},i))}),e.jsx("button",{type:"button",className:"btn-solid",onClick:()=>{g(u.pricingClick,{tier:r.key,source:"landing"}),r.key==="free"?s("/app/overview"):(g(u.telegramBot,{source:"landing_pricing",tier:r.key}),window.open(`${v}?start=premium`,"_blank","noopener,noreferrer"))},children:r.key==="free"?a("land.tier.free.cta"):a("land.tier.premium.cta")})]},r.key))})]})}),e.jsx("section",{className:"section alt",children:e.jsxs("div",{className:"inner",children:[e.jsx("h2",{className:"sec-title reveal",children:a("land.faq.title")}),e.jsx("div",{className:"faq reveal",children:h.map((r,i)=>e.jsxs("div",{className:`faq-item ${l===i?"open":""}`,children:[e.jsxs("button",{type:"button",className:"faq-q","aria-expanded":l===i,onClick:()=>x(l===i?null:i),children:[e.jsx("span",{children:r.q}),e.jsx("span",{"aria-hidden":"true",children:l===i?"−":"+"})]}),l===i&&e.jsx("div",{className:"faq-a",children:r.a})]},r.q))})]})}),e.jsx("section",{id:"support",className:"section",children:e.jsxs("div",{className:"inner",children:[e.jsx("h2",{className:"sec-title reveal",children:a("land.support.title")}),e.jsx("p",{className:"sec-sub reveal",children:a("land.support.sub")}),e.jsxs("div",{className:"support-grid reveal",children:[e.jsxs("a",{className:"support-card",href:$,target:"_blank",rel:"noopener noreferrer",children:[e.jsx("div",{className:"support-label",children:a("land.support.tgLabel")}),e.jsxs("div",{className:"support-value",children:["@",I]}),e.jsx("div",{className:"support-hint",children:a("land.support.tgHint")})]}),e.jsxs("a",{className:"support-card",href:`mailto:${N}`,children:[e.jsx("div",{className:"support-label",children:a("land.support.emailLabel")}),e.jsx("div",{className:"support-value",children:N}),e.jsx("div",{className:"support-hint",children:a("land.support.emailHint")})]}),e.jsxs("a",{className:"support-card",href:v,target:"_blank",rel:"noopener noreferrer",onClick:()=>g(u.telegramBot,{source:"landing_support"}),children:[e.jsx("div",{className:"support-label",children:a("land.support.botLabel")}),e.jsx("div",{className:"support-value",children:a("land.support.botValue")}),e.jsx("div",{className:"support-hint",children:a("land.support.botHint")})]})]}),e.jsx("p",{className:"support-hours reveal",children:a("land.support.hours")})]})}),e.jsx("footer",{className:"footer",children:e.jsxs("div",{className:"inner foot",children:[e.jsxs("div",{children:[e.jsx("div",{className:"nav-word",children:"NOWICKI"}),e.jsx("p",{className:"muted",children:a("land.footer.desc")}),e.jsxs("p",{className:"muted small",style:{marginTop:8},children:[a("land.footer.products"),": Free · Premium $29/mo · Premium 3mo $75 · Lifetime $299"]})]}),e.jsxs("div",{className:"foot-links",children:[e.jsx("a",{href:z,target:"_blank",rel:"noopener noreferrer",children:a("land.footer.results")}),e.jsx("a",{href:"#pricing",onClick:r=>{r.preventDefault(),m("#pricing")},children:a("land.footer.premium")}),e.jsx("a",{href:v,target:"_blank",rel:"noopener noreferrer",onClick:()=>g(u.telegramBot,{source:"landing_footer"}),children:a("land.footer.bot")}),e.jsx("a",{href:"#support",onClick:r=>{r.preventDefault(),m("#support")},children:a("land.footer.support")}),e.jsx("a",{href:"/support.html",children:a("land.footer.contacts")}),e.jsx("button",{type:"button",onClick:()=>s("/app/overview"),children:a("land.footer.platform")})]}),e.jsxs("div",{className:"muted small",children:[e.jsxs("div",{children:[a("land.footer.supportLine"),": ",e.jsxs("a",{href:$,target:"_blank",rel:"noopener noreferrer",children:["@",I]})," · ",e.jsx("a",{href:`mailto:${N}`,children:N})]}),e.jsx("div",{style:{marginTop:6},children:a("land.footer.disclaimer",{year:new Date().getFullYear()})})]})]})}),e.jsx("style",{children:`
        .lp { min-height: 100vh; background: transparent; color: var(--text); font-family: var(--font-ui); overflow-x: hidden; }
        .reveal { opacity: 0; transform: translateY(18px); transition: opacity .6s ease, transform .6s ease; }
        .reveal.in { opacity: 1; transform: none; }
        .animate-in { animation: fadeIn .5s ease forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%{box-shadow:0 0 0 0 color-mix(in srgb, var(--long) 40%, transparent)} 70%{box-shadow:0 0 0 8px transparent} 100%{box-shadow:0 0 0 0 transparent} }
        .pos { color: var(--long) !important; } .neg { color: var(--short) !important; }
        .mono { font-family: var(--font-mono); }
        .muted { color: var(--text-secondary); } .small { font-size: 12px; } .pad { padding: 24px; }

        .navbar { position: sticky; top: 0; z-index: 50; border-bottom: 1px solid var(--border); }
        .nav-inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; height: 56px; display: flex; align-items: center; gap: 16px; }
        .nav-logo { display: flex; align-items: center; gap: 10px; background: none; border: none; color: inherit; padding: 0; }
        .nav-mark {
          width: 30px; height: 30px; border-radius: 9px; background: var(--accent); color: #fff;
          display: grid; place-items: center; font-family: var(--font-display); font-weight: 700;
          box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .nav-word { font-family: var(--font-display); font-weight: 700; letter-spacing: -.02em; font-size: 16px; }
        .nav-links { display: flex; gap: 2px; flex: 1; justify-content: center; }
        .nav-links a { padding: 8px 14px; border-radius: 980px; font-size: 13px; color: var(--text-secondary); font-weight: 550; }
        .nav-links a:hover { color: var(--text); background: var(--surface-hover); }
        .nav-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }
        .lang-switch { display: flex; gap: 2px; padding: 2px; border: 1px solid var(--border); border-radius: 980px; background: var(--surface); }
        .lang-btn { border: none; background: transparent; color: var(--text-tertiary); font-size: 11px; font-weight: 700; padding: 6px 9px; border-radius: 980px; cursor: pointer; letter-spacing: 0.04em; }
        .lang-btn.active { background: var(--accent); color: #fff; }
        .theme-btn { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--border); background: var(--surface); }
        .burger { display: none; flex-direction: column; gap: 5px; background: none; border: none; padding: 4px; }
        .burger span { width: 20px; height: 2px; background: var(--text); border-radius: 2px; }

        .btn-solid {
          background: var(--accent); color: #fff; border: none; border-radius: 980px; padding: 10px 18px;
          font-weight: 650; font-size: 14px; box-shadow: 0 4px 14px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .btn-solid.lg { padding: 14px 26px; font-size: 15px; }
        .btn-ghost {
          background: color-mix(in srgb, var(--surface) 70%, transparent); border: 1px solid var(--border); color: var(--text);
          border-radius: 980px; padding: 10px 16px; font-weight: 600; font-size: 14px; text-decoration: none;
          display: inline-flex; align-items: center; backdrop-filter: blur(8px);
        }
        .btn-ghost.lg { padding: 14px 22px; font-size: 15px; }
        .btn-ghost:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); color: var(--accent); }

        .hero { position: relative; padding: 56px 0 64px; overflow: hidden; }
        .hero-plane { position: absolute; inset: 0; background:
          radial-gradient(ellipse 70% 50% at 85% 15%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 60%),
          radial-gradient(ellipse 50% 40% at 10% 85%, color-mix(in srgb, var(--long) 8%, transparent), transparent 55%);
          pointer-events: none; }
        .hero-grid { position: relative; z-index: 1; max-width: 1120px; margin: 0 auto; padding: 0 20px; display: grid; grid-template-columns: 1.05fr .95fr; gap: 40px; align-items: center; }
        .eyebrow { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; color: var(--accent); margin-bottom: 16px; }
        .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--long); animation: pulse 2s infinite; }
        .hero-copy h1 { font-family: var(--font-display); font-size: clamp(34px, 5vw, 52px); font-weight: 700; letter-spacing: -.04em; line-height: 1.05; margin: 0 0 16px; }
        .hero-copy p { font-size: 17px; color: var(--text-secondary); line-height: 1.55; max-width: 40ch; margin: 0 0 26px; }
        .hero-cta { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 32px; }
        .hero-stats { display: flex; gap: 32px; flex-wrap: wrap; }
        .hero-stats > div { display: flex; flex-direction: column; gap: 4px; }
        .hs-num { font-family: var(--font-mono); font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
        .hero-stats span:last-child { font-size: 12px; color: var(--text-tertiary); }

        .scanner {
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
          box-shadow: var(--shadow-lg), var(--inset-highlight); backdrop-filter: saturate(160%) blur(20px);
        }
        .scanner-top {
          display: flex; align-items: center; gap: 10px; padding: 12px 14px;
          border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--surface-hover) 70%, transparent); flex-wrap: wrap;
        }
        .tl-row { display: flex; gap: 6px; margin-right: 4px; }
        .tl { width: 11px; height: 11px; border-radius: 50%; box-shadow: inset 0 0 0 .5px rgba(0,0,0,.15); }
        .tl.r { background: #ff5f57; } .tl.a { background: #febc2e; } .tl.g { background: #28c840; }
        .live-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 700; color: var(--long); letter-spacing: .08em; }
        .scanner-title { font-family: var(--font-ui); font-size: 12px; font-weight: 600; color: var(--text-secondary); }
        .scanner-tickers { margin-left: auto; font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }
        .scanner-body { display: grid; grid-template-columns: 1fr 1fr; gap: 0; min-height: 220px; }
        .radar { position: relative; height: 220px; background: color-mix(in srgb, var(--bg) 80%, transparent); }
        .ring { position: absolute; inset: 18px; border: 1px solid var(--border-strong); border-radius: 50%; opacity: .55; }
        .ring.r2 { inset: 42px; } .ring.r3 { inset: 66px; }
        .sweep { position: absolute; inset: 18px; border-radius: 50%; background: conic-gradient(from 0deg, transparent 0deg, var(--accent) 50deg, transparent 90deg); opacity: .22; animation: spin 3s linear infinite; }
        .core {
          position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 52px; height: 52px; border-radius: 50%;
          background: var(--accent); color: #fff; display: grid; place-items: center; font-family: var(--font-mono); font-weight: 700; font-size: 13px;
          box-shadow: 0 6px 18px color-mix(in srgb, var(--accent) 35%, transparent);
        }
        .blip { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: var(--text-tertiary); transform: translate(-50%,-50%); }
        .blip.on { background: var(--long); box-shadow: 0 0 0 4px color-mix(in srgb, var(--long) 25%, transparent); width: 9px; height: 9px; }
        .scan-feed { padding: 16px; border-left: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
        .scan-now { font-size: 13px; font-weight: 600; }
        .scan-now b { font-family: var(--font-mono); color: var(--accent); }
        .scan-feed ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
        .scan-feed li { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }

        .equity-mini {
          margin-top: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md);
          padding: 12px 14px 0; box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(12px);
        }
        .eq-meta { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
        .eq-meta strong { font-family: var(--font-mono); font-size: 22px; text-transform: none; letter-spacing: -.02em; }
        .eq-chart { height: 88px; }

        .inner { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
        .section { padding: 72px 0; }
        .section.alt { background: color-mix(in srgb, var(--surface) 55%, transparent); border-block: 1px solid var(--border); backdrop-filter: blur(8px); }
        .sec-title { font-family: var(--font-display); font-size: clamp(26px, 3.5vw, 36px); font-weight: 700; letter-spacing: -.03em; margin: 0 0 10px; }
        .sec-sub { color: var(--text-secondary); max-width: 48ch; margin: 0 0 24px; line-height: 1.55; }

        .signal-lock-wrap { position: relative; }
        .signal-rows {
          display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
          background: var(--surface); min-height: 180px; box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(16px);
        }
        .signal-rows.signal-blur { filter: blur(5px); pointer-events: none; user-select: none; }
        .sig-row { display: grid; grid-template-columns: 1fr auto 1fr auto; gap: 12px; align-items: center; padding: 14px 16px; border: none; border-bottom: 1px solid var(--border); background: transparent; color: inherit; text-align: left; font-size: 14px; }
        .sig-row:last-child { border-bottom: none; }
        .sig-row:hover { background: var(--surface-hover); }
        .signal-lock {
          position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
          text-align: center; padding: 24px; border-radius: var(--radius-lg);
          background: color-mix(in srgb, var(--bg) 55%, transparent); backdrop-filter: blur(8px);
        }
        .signal-lock-icon { font-size: 22px; opacity: .75; }
        .signal-lock-text { font-size: 14px; font-weight: 650; color: var(--text); max-width: 320px; }
        .dir { font-size: 11px; font-weight: 700; font-family: var(--font-mono); padding: 3px 8px; border-radius: 8px; }
        .dir.long { background: var(--long-soft); color: var(--long); }
        .dir.short { background: var(--short-soft); color: var(--short); }

        .about { display: grid; grid-template-columns: 1.4fr .8fr; gap: 40px; align-items: center; }
        .honest-list { margin: 18px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 14px; }
        .honest-list li { padding-left: 18px; position: relative; color: var(--text-secondary); line-height: 1.5; }
        .honest-list li::before { content: ''; position: absolute; left: 0; top: .55em; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
        .honest-cta { display: flex; flex-direction: column; gap: 10px; }

        .price-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 280px)); gap: 16px; justify-content: center; }
        .price-card {
          position: relative; border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px;
          background: var(--surface); display: flex; flex-direction: column; gap: 12px;
          box-shadow: var(--shadow-card), var(--inset-highlight); backdrop-filter: blur(16px);
        }
        .price-card.popular { border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); box-shadow: var(--shadow-lg); }
        .pop { position: absolute; top: -10px; left: 20px; background: var(--accent); color: #fff; font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; padding: 4px 12px; border-radius: 999px; }
        .price-name { font-family: var(--font-display); font-weight: 700; font-size: 18px; letter-spacing: -.02em; }
        .price-amt { font-family: var(--font-mono); font-size: 36px; font-weight: 650; letter-spacing: -.03em; }
        .price-amt small { font-size: 14px; color: var(--text-tertiary); font-weight: 500; margin-left: 4px; }
        .price-card ul { list-style: none; padding: 0; margin: 0 0 8px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
        .price-card li { font-size: 13px; color: var(--text-secondary); }

        .faq { max-width: 720px; }
        .faq-item { border-bottom: 1px solid var(--border); }
        .faq-q { width: 100%; display: flex; justify-content: space-between; gap: 16px; padding: 18px 0; background: none; border: none; color: var(--text); font-size: 15px; font-weight: 600; text-align: left; }
        .faq-a { padding-bottom: 16px; color: var(--text-secondary); font-size: 14px; line-height: 1.6; }

        .support-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; max-width: 900px; }
        .support-card {
          display: block; text-decoration: none; color: inherit;
          border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px;
          background: var(--surface); box-shadow: var(--shadow-card), var(--inset-highlight);
          transition: border-color .2s, transform .2s;
        }
        .support-card:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); transform: translateY(-2px); }
        .support-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--text-tertiary); font-weight: 700; }
        .support-value { font-size: 18px; font-weight: 700; margin: 8px 0 6px; font-family: var(--font-mono); color: var(--accent); }
        .support-hint { font-size: 13px; color: var(--text-secondary); line-height: 1.45; }
        .support-hours { margin-top: 16px; font-size: 13px; color: var(--text-tertiary); }

        .footer { padding: 48px 0 28px; border-top: 1px solid var(--border); }
        .foot { display: grid; gap: 20px; }
        .foot-links { display: flex; gap: 16px; flex-wrap: wrap; }
        .foot-links a, .foot-links button { background: none; border: none; color: var(--text-secondary); font-size: 14px; padding: 0; }
        .foot-links a:hover, .foot-links button:hover { color: var(--accent); }

        @media (max-width: 900px) {
          .hero-grid, .about, .price-grid, .support-grid { grid-template-columns: 1fr; }
          .scanner-body { grid-template-columns: 1fr; }
          .scan-feed { border-left: none; border-top: 1px solid var(--border); }
        }
        @media (max-width: 768px) {
          .nav-links { display: none; position: absolute; top: 56px; left: 0; right: 0; background: var(--glass); border-bottom: 1px solid var(--border); flex-direction: column; padding: 12px; backdrop-filter: blur(20px); }
          .nav-links.open { display: flex; }
          .burger { display: flex; }
          .btn-ghost:not(.lg) { display: none; }
          .sig-row { grid-template-columns: 1fr auto; }
          .sig-row .muted { display: none; }
          .scanner-tickers { display: none; }
        }
      `})]})}export{J as default};
