import{a as J,r as n,j as e,t as C,G as R}from"./index-DWgcX8Xm.js";import{T as V,d as Z,c as A,S as H,g as rr}from"./shared-BfpJX4w4.js";import{a as h}from"./api-DXCafRhN.js";const er=rr;function tr({soon:a}){return a?e.jsx("span",{className:"pr-check soon","aria-hidden":!0,children:e.jsxs("svg",{width:"14",height:"14",viewBox:"0 0 14 14",fill:"none",children:[e.jsx("circle",{cx:"7",cy:"7",r:"5.5",stroke:"currentColor",strokeWidth:"1.4"}),e.jsx("path",{d:"M7 4.2v3.2M7 9.6h.01",stroke:"currentColor",strokeWidth:"1.4",strokeLinecap:"round"})]})}):e.jsx("span",{className:"pr-check","aria-hidden":!0,children:e.jsx("svg",{width:"14",height:"14",viewBox:"0 0 14 14",fill:"none",children:e.jsx("path",{d:"M3.2 7.2 5.8 9.8l5-5.6",stroke:"currentColor",strokeWidth:"1.6",strokeLinecap:"round",strokeLinejoin:"round"})})})}function nr({user:a,onNeedAuth:b,onUserUpdate:v}){const{t:r}=J(),[p,L]=n.useState("month"),[x,$]=n.useState(null),[q,z]=n.useState(!1),[S,P]=n.useState(null),[T,E]=n.useState(!1),[M,m]=n.useState(null),[_,B]=n.useState(!1),[f,I]=n.useState(null),[O,G]=n.useState(!1),[y,F]=n.useState(!1),[k,u]=n.useState(null);n.useEffect(()=>{h.paymentsConfig().then(i=>{B(!!i.heleket),I(i.heleket_plans||null),G(!!i.heleket_test_mode)}).catch(()=>B(!1)),new URLSearchParams(window.location.search).get("paid")==="1"&&F(!0)},[]),n.useEffect(()=>{if(!y||!a)return;if(a.tier==="premium"||a.tier==="vip"){u("unlocked");return}let t=!1,i=0;u("checking");async function s(){var c;if(!t){i+=1;try{const o=await h.syncHeleketPayment();o!=null&&o.user&&(v==null||v(o.user));const d=((c=o==null?void 0:o.user)==null?void 0:c.tier)||(o==null?void 0:o.tier);if(d==="premium"||d==="vip"||o!=null&&o.granted){t||u("unlocked");return}}catch{}if(!t){if(i>=12){u("waiting");return}setTimeout(s,i<4?2e3:4e3)}}}return s(),()=>{t=!0}},[y,a==null?void 0:a.id]);const w=n.useMemo(()=>[{key:"month",label:r("price.period.month"),mult:1,discount:0},{key:"3mo",label:r("price.period.3mo"),mult:3,discount:.14},{key:"lifetime",label:r("price.period.lifetime"),mult:null,discount:0}],[r]),W=n.useMemo(()=>[{key:"free",name:r("price.tier.free.name"),price:0,lifetime:0,features:[r("price.tier.free.f1"),r("price.tier.free.f2"),r("price.tier.free.f3")],cta:r("price.tier.free.cta")},{key:"premium",name:r("price.tier.premium.name"),price:29,lifetime:299,features:[r("price.tier.premium.f1"),r("price.tier.premium.f2"),r("price.tier.premium.f3"),r("price.tier.premium.f4"),{label:r("price.tier.premium.f5"),soon:!0}],cta:r("price.tier.premium.cta"),popular:!0}],[r]),X=n.useMemo(()=>[{q:r("price.faq.q1"),a:r("price.faq.a1")},{q:r("price.faq.q2"),a:r("price.faq.a2")},{q:r("price.faq.q3"),a:r("price.faq.a3")},{q:r("price.faq.q4"),a:r("price.faq.a4")},{q:r("price.faq.q5"),a:r("price.faq.a5")}],[r]),g=a&&(a.tier==="premium"||a.tier==="vip");async function Y(){z(!0),P(null);try{const t=await h.telegramLinkToken();window.open(t.bot_url,"_blank","noopener,noreferrer")}catch(t){P(t.message)}finally{z(!1)}}function D(t){var c;if(t.key==="free")return{amount:0,suffix:r("price.forever")};if(f&&t.key==="premium"){const o=p==="lifetime"?f.lifetime:f[p]??f.month,d=Math.round(Number(o)||0),l=p==="lifetime"?r("price.lifetimeSuffix"):p==="month"?r("price.perMonth"):r("price.perMonths",{n:((c=w.find(j=>j.key===p))==null?void 0:c.mult)??1});return{amount:d,suffix:l}}if(p==="lifetime")return{amount:t.lifetime,suffix:r("price.lifetimeSuffix")};const i=w.find(o=>o.key===p);return{amount:Math.round(t.price*i.mult*(1-i.discount)),suffix:p==="month"?r("price.perMonth"):r("price.perMonths",{n:i.mult})}}function K(t){if(t!=="free"){if(C(R.pricingClick,{tier:t,period:p,source:"app_pricing"}),_){if(!a){b==null||b(),m(r("price.loginRequired"));return}Q();return}C(R.telegramBot,{source:"app_pricing",tier:t}),window.open(er,"_blank","noopener,noreferrer")}}async function Q(){E(!0),m(null);try{const t=await h.createHeleketPayment(p);t.pay_url?window.location.href=t.pay_url:m(r("price.payError"))}catch(t){m(t.message||r("price.payError"))}finally{E(!1)}}return e.jsxs("div",{className:"pr-page",children:[e.jsxs("header",{className:"pr-hero",children:[e.jsx("p",{className:"pr-eyebrow",children:r("price.eyebrow")}),e.jsx("h1",{className:"pr-title",children:r("price.title")}),e.jsx("p",{className:"pr-sub",children:r("price.subtitle")}),e.jsxs("a",{className:"pr-results",href:V,target:"_blank",rel:"noopener noreferrer",children:[r("price.bannerLink"),e.jsx("span",{"aria-hidden":!0,children:"→"})]})]}),y&&e.jsx("div",{className:`pr-notice ${k==="unlocked"?"ok":""}`,role:"status",children:r(k==="unlocked"?"price.paidUnlocked":k==="checking"?"price.paidChecking":"price.paidNotice")}),O&&e.jsx("div",{className:"pr-notice warn",role:"status",children:r("price.testMode")}),M&&e.jsx("div",{className:"pr-notice err",role:"alert",children:M}),g&&e.jsxs("div",{className:"pr-active",children:[e.jsx("div",{className:"pr-active-dot","aria-hidden":!0}),e.jsxs("div",{className:"pr-active-copy",children:[e.jsx("div",{className:"pr-active-title",children:r("price.activeTitle")}),e.jsx("div",{className:"pr-active-hint",children:r("price.activeHint")})]})]}),a&&e.jsxs("div",{className:"pr-tg",children:[e.jsxs("div",{className:"pr-tg-copy",children:[e.jsx("div",{className:"pr-tg-title",children:r(g?"price.tg.premiumTitle":"price.tg.connectTitle")}),e.jsx("div",{className:"pr-tg-hint",children:r(g?"price.tg.premiumHint":"price.tg.connectHint")}),S&&e.jsx("div",{className:"pr-notice err",style:{marginTop:10,marginBottom:0},children:S})]}),e.jsx("button",{type:"button",className:"pr-tg-btn",onClick:Y,disabled:q,children:q?"…":r("price.tg.btn")})]}),e.jsx("div",{className:"pr-period",role:"tablist","aria-label":r("price.title"),children:w.map(t=>e.jsxs("button",{type:"button",role:"tab","aria-selected":p===t.key,className:`pr-period-btn ${p===t.key?"active":""}`,onClick:()=>L(t.key),children:[t.label,t.discount>0&&e.jsxs("span",{className:"pr-period-off",children:["−",Math.round(t.discount*100),"%"]})]},t.key))}),e.jsx("div",{className:"pr-grid",children:W.map((t,i)=>{const s=((a==null?void 0:a.base_tier)??(a==null?void 0:a.tier))===t.key||t.key==="premium"&&((a==null?void 0:a.tier)==="premium"||(a==null?void 0:a.tier)==="vip"),{amount:c,suffix:o}=D(t),d=s?r("price.yourPlan"):_&&t.key==="premium"?r("price.tier.premium.ctaPay"):t.cta;return e.jsxs("article",{className:["pr-card",t.popular?"popular":"",s?"current":"",t.key==="premium"&&g?"active-plan":""].filter(Boolean).join(" "),style:{animationDelay:`${.08+i*.08}s`},children:[t.popular&&!s&&e.jsx("div",{className:"pr-badge",children:r("price.popular")}),s&&e.jsx("div",{className:"pr-badge current",children:r("price.yourPlan")}),e.jsxs("div",{className:"pr-card-top",children:[e.jsx("h2",{className:"pr-name",children:t.name}),e.jsxs("div",{className:"pr-price",children:[e.jsxs("span",{className:"pr-amount",children:["$",c]}),e.jsx("span",{className:"pr-suffix",children:o})]})]}),e.jsx("ul",{className:"pr-features",children:t.features.map((l,j)=>{const U=typeof l=="string"?l:l.label,N=typeof l=="object"&&l.soon;return e.jsxs("li",{className:N?"soon":void 0,children:[e.jsx(tr,{soon:N}),e.jsxs("span",{children:[U,N&&e.jsx("span",{className:"pr-soon",children:r("price.soon")})]})]},j)})}),e.jsx("button",{type:"button",className:`pr-cta ${t.popular&&!s?"primary":""} ${s?"ghost":""}`,disabled:s||t.key==="free"||T,onClick:()=>K(t.key),children:T&&t.key==="premium"?"…":d})]},t.key)})}),e.jsx("p",{className:"pr-pay-hint",children:r("price.payHint")}),e.jsxs("div",{className:"pr-foot",children:[e.jsxs("p",{className:"pr-exchange",children:[r("price.exchangeNotePrefix")," ",e.jsx("strong",{children:"Bybit · Binance · OKX · Bitget · BingX · Bitunix"})," ",r("price.exchangeNoteSuffix")]}),e.jsxs("div",{className:"pr-support",children:[e.jsx("div",{className:"pr-support-title",children:r("price.supportTitle")}),e.jsxs("div",{className:"pr-support-body",children:[r("price.supportBody")," ",e.jsxs("a",{href:A,target:"_blank",rel:"noopener noreferrer",children:["@",Z]})," · ",e.jsx("a",{href:`mailto:${H}`,children:H})," · ",e.jsx("a",{href:"/support.html",children:r("price.supportPage")})]})]})]}),e.jsxs("section",{className:"pr-faq",children:[e.jsx("h2",{className:"pr-faq-title",children:r("price.faqTitle")}),e.jsx("div",{className:"pr-faq-list",children:X.map((t,i)=>e.jsxs("div",{className:`pr-faq-item ${x===i?"open":""}`,children:[e.jsxs("button",{type:"button",className:"pr-faq-q","aria-expanded":x===i,onClick:()=>$(x===i?null:i),children:[e.jsx("span",{children:t.q}),e.jsx("span",{className:"pr-faq-icon","aria-hidden":!0,children:x===i?"−":"+"})]}),e.jsx("div",{className:"pr-faq-a",hidden:x!==i,children:t.a})]},i))})]}),e.jsx("style",{children:`
        .pr-page {
          max-width: 820px;
          margin: 0 auto;
          padding: 8px 0 48px;
        }

        .pr-hero {
          text-align: center;
          padding: 28px 12px 8px;
          animation: pr-fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .pr-eyebrow {
          font-size: 12px;
          font-weight: 650;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--accent);
          margin-bottom: 12px;
        }
        .pr-title {
          font-family: var(--font-display);
          font-size: clamp(32px, 5vw, 44px);
          font-weight: 700;
          letter-spacing: -0.04em;
          line-height: 1.05;
          color: var(--text);
          margin: 0 0 12px;
        }
        .pr-sub {
          font-size: 16px;
          line-height: 1.45;
          color: var(--text-secondary);
          max-width: 420px;
          margin: 0 auto 18px;
        }
        .pr-results {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 14px;
          font-weight: 600;
          color: var(--accent);
          text-decoration: none;
          transition: opacity 0.2s;
        }
        .pr-results:hover { opacity: 0.75; }

        .pr-notice {
          margin: 20px auto 0;
          max-width: 640px;
          padding: 14px 18px;
          border-radius: var(--radius-md);
          background: var(--surface);
          border: 1px solid var(--border);
          font-size: 13px;
          line-height: 1.45;
          color: var(--text-secondary);
          text-align: center;
          animation: pr-fade-up 0.4s ease both;
        }
        .pr-notice.ok {
          border-color: color-mix(in srgb, var(--long) 40%, var(--border));
          background: color-mix(in srgb, var(--long-soft) 70%, var(--surface));
          color: var(--text);
        }
        .pr-notice.warn {
          border-color: color-mix(in srgb, var(--amber) 35%, var(--border));
          background: color-mix(in srgb, var(--amber-soft) 60%, var(--surface));
        }
        .pr-notice.err {
          border-color: color-mix(in srgb, var(--short) 35%, var(--border));
          background: color-mix(in srgb, var(--short-soft) 55%, var(--surface));
          color: var(--text);
        }

        .pr-active {
          display: flex;
          align-items: flex-start;
          gap: 14px;
          max-width: 640px;
          margin: 28px auto 0;
          padding: 18px 20px;
          border-radius: var(--radius-lg);
          background: color-mix(in srgb, var(--accent-soft) 80%, var(--surface));
          border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
          animation: pr-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.05s both;
        }
        .pr-active-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: var(--long);
          margin-top: 5px;
          flex-shrink: 0;
          box-shadow: 0 0 0 4px color-mix(in srgb, var(--long) 22%, transparent);
        }
        .pr-active-title {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 700;
          letter-spacing: -0.02em;
          color: var(--text);
        }
        .pr-active-hint {
          font-size: 13px;
          color: var(--text-secondary);
          margin-top: 4px;
          line-height: 1.45;
        }

        .pr-tg {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 20px;
          flex-wrap: wrap;
          max-width: 640px;
          margin: 20px auto 0;
          padding: 18px 20px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card), var(--inset-highlight);
          backdrop-filter: blur(16px);
          animation: pr-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.08s both;
        }
        .pr-tg-title {
          font-size: 15px;
          font-weight: 650;
          color: var(--text);
          letter-spacing: -0.01em;
        }
        .pr-tg-hint {
          font-size: 13px;
          color: var(--text-secondary);
          margin-top: 4px;
          max-width: 420px;
          line-height: 1.45;
        }
        .pr-tg-btn {
          flex-shrink: 0;
          border: none;
          border-radius: 980px;
          padding: 11px 20px;
          font-size: 13px;
          font-weight: 650;
          cursor: pointer;
          background: var(--text);
          color: var(--bg);
          transition: transform 0.2s, opacity 0.2s;
        }
        .pr-tg-btn:hover:not(:disabled) { transform: scale(1.02); }
        .pr-tg-btn:disabled { opacity: 0.55; cursor: default; }

        .pr-period {
          display: flex;
          justify-content: center;
          margin: 36px auto 28px;
          padding: 4px;
          gap: 2px;
          width: fit-content;
          max-width: 100%;
          background: var(--surface-2);
          border-radius: 980px;
          animation: pr-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.1s both;
        }
        .pr-period-btn {
          border: none;
          background: transparent;
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 600;
          padding: 9px 18px;
          border-radius: 980px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
          transition: color 0.2s, background 0.2s, box-shadow 0.2s;
          white-space: nowrap;
        }
        .pr-period-btn.active {
          background: var(--surface-solid);
          color: var(--text);
          box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
        }
        .pr-period-off {
          font-size: 10px;
          font-weight: 700;
          color: var(--long);
          letter-spacing: 0.02em;
        }

        .pr-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 16px;
          max-width: 680px;
          margin: 0 auto;
        }
        .pr-card {
          position: relative;
          display: flex;
          flex-direction: column;
          padding: 28px 26px 24px;
          border-radius: 22px;
          background: var(--surface-solid);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card);
          transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.28s, border-color 0.28s;
          animation: pr-fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .pr-card:hover {
          transform: translateY(-3px);
          box-shadow: var(--shadow-lg);
        }
        .pr-card.popular {
          border-color: color-mix(in srgb, var(--accent) 38%, var(--border));
          background:
            linear-gradient(180deg,
              color-mix(in srgb, var(--accent-soft) 55%, var(--surface-solid)) 0%,
              var(--surface-solid) 48%);
        }
        .pr-card.current,
        .pr-card.active-plan {
          border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
        }
        .pr-badge {
          position: absolute;
          top: -11px;
          left: 50%;
          transform: translateX(-50%);
          background: var(--accent);
          color: #fff;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          padding: 4px 12px;
          border-radius: 999px;
          white-space: nowrap;
        }
        .pr-badge.current {
          background: var(--text);
          color: var(--bg);
        }
        .pr-card-top { margin-bottom: 22px; }
        .pr-name {
          font-family: var(--font-display);
          font-size: 15px;
          font-weight: 650;
          letter-spacing: -0.01em;
          color: var(--text-secondary);
          margin: 0 0 10px;
        }
        .pr-price {
          display: flex;
          align-items: baseline;
          gap: 6px;
          flex-wrap: wrap;
        }
        .pr-amount {
          font-family: var(--font-display);
          font-size: clamp(36px, 5vw, 44px);
          font-weight: 700;
          letter-spacing: -0.045em;
          line-height: 1;
          color: var(--text);
        }
        .pr-suffix {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-tertiary);
        }
        .pr-features {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin: 0 0 28px;
          flex: 1;
          padding: 0;
        }
        .pr-features li {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          font-size: 14px;
          line-height: 1.4;
          color: var(--text);
        }
        .pr-features li.soon { color: var(--text-tertiary); }
        .pr-check {
          flex-shrink: 0;
          width: 22px; height: 22px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          margin-top: 0;
          background: color-mix(in srgb, var(--accent) 12%, transparent);
          color: var(--accent);
        }
        .pr-check.soon {
          background: var(--surface-2);
          color: var(--text-tertiary);
        }
        .pr-soon {
          display: inline-block;
          margin-left: 8px;
          font-size: 9px;
          font-weight: 700;
          letter-spacing: 0.08em;
          color: var(--text-tertiary);
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 2px 6px;
          vertical-align: 1px;
        }
        .pr-cta {
          width: 100%;
          border: 1px solid var(--border-strong);
          border-radius: 980px;
          padding: 13px 18px;
          font-size: 14px;
          font-weight: 650;
          cursor: pointer;
          background: transparent;
          color: var(--text);
          transition: transform 0.2s, background 0.2s, border-color 0.2s, opacity 0.2s;
        }
        .pr-cta.primary {
          background: var(--accent);
          border-color: transparent;
          color: #fff;
          box-shadow: 0 6px 18px color-mix(in srgb, var(--accent) 28%, transparent);
        }
        .pr-cta.primary:hover:not(:disabled) {
          transform: scale(1.015);
          background: color-mix(in srgb, var(--accent) 92%, #000);
        }
        .pr-cta.ghost,
        .pr-cta:disabled {
          cursor: default;
          opacity: 0.7;
          background: var(--surface-2);
          border-color: transparent;
          color: var(--text-secondary);
          box-shadow: none;
        }
        .pr-cta:not(.primary):not(.ghost):not(:disabled):hover {
          border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
          color: var(--accent);
        }

        .pr-pay-hint {
          text-align: center;
          font-size: 13px;
          color: var(--text-tertiary);
          margin: 22px auto 0;
          max-width: 420px;
          line-height: 1.45;
        }

        .pr-foot {
          max-width: 640px;
          margin: 40px auto 0;
          text-align: center;
        }
        .pr-exchange {
          font-size: 12px;
          color: var(--text-tertiary);
          margin-bottom: 20px;
        }
        .pr-support {
          padding: 18px 20px;
          border-radius: var(--radius-lg);
          border: 1px solid var(--border);
          background: var(--surface);
        }
        .pr-support-title {
          font-size: 14px;
          font-weight: 650;
          margin-bottom: 6px;
          color: var(--text);
        }
        .pr-support-body {
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.5;
        }
        .pr-support-body a {
          color: var(--accent);
          text-decoration: none;
          font-weight: 600;
        }
        .pr-support-body a:hover { text-decoration: underline; }

        .pr-faq {
          max-width: 640px;
          margin: 48px auto 0;
        }
        .pr-faq-title {
          font-family: var(--font-display);
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.03em;
          text-align: center;
          margin: 0 0 8px;
          color: var(--text);
        }
        .pr-faq-list { margin-top: 12px; }
        .pr-faq-item { border-bottom: 1px solid var(--border); }
        .pr-faq-q {
          width: 100%;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          padding: 18px 2px;
          background: transparent;
          border: none;
          color: var(--text);
          font-size: 15px;
          font-weight: 600;
          letter-spacing: -0.01em;
          text-align: left;
          cursor: pointer;
          transition: color 0.2s;
        }
        .pr-faq-q:hover { color: var(--accent); }
        .pr-faq-icon {
          width: 22px; height: 22px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          font-size: 16px;
          line-height: 1;
          color: var(--text-tertiary);
          background: var(--surface-2);
          flex-shrink: 0;
        }
        .pr-faq-item.open .pr-faq-icon {
          background: color-mix(in srgb, var(--accent) 12%, transparent);
          color: var(--accent);
        }
        .pr-faq-a {
          font-size: 14px;
          color: var(--text-secondary);
          line-height: 1.55;
          padding: 0 2px 18px;
          animation: pr-fade-up 0.25s ease both;
        }

        @keyframes pr-fade-up {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 640px) {
          .pr-page { padding: 0 0 32px; }
          .pr-hero { padding: 12px 4px 4px; }
          .pr-sub { font-size: 15px; }
          .pr-period {
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
          }
          .pr-period-btn { padding: 9px 14px; font-size: 12px; }
          .pr-grid {
            grid-template-columns: 1fr;
            gap: 14px;
          }
          .pr-card { padding: 24px 20px 20px; }
          .pr-tg { padding: 16px; }
          .pr-tg-btn { width: 100%; }
        }

        @media (prefers-reduced-motion: reduce) {
          .pr-hero, .pr-notice, .pr-active, .pr-tg, .pr-period, .pr-card, .pr-faq-a {
            animation: none !important;
          }
          .pr-card:hover, .pr-cta.primary:hover:not(:disabled), .pr-tg-btn:hover:not(:disabled) {
            transform: none;
          }
        }
      `})]})}export{nr as default};
