import{a as v,r as b,j as t,t as c,G as g}from"./index-DWgcX8Xm.js";import{a as f}from"./api-DXCafRhN.js";import{T as j,c as k,d as y,S as h,b as N}from"./shared-BfpJX4w4.js";function z({user:e,onNeedAuth:i,onOpenPricing:o}){const{t:r}=v(),[a,m]=b.useState(!1),[p,x]=b.useState(null),s=!!(e!=null&&e.telegram_id||e!=null&&e.telegram_linked),n=!!(e&&(e.tier==="premium"||e.tier==="vip"));async function l(){if(!e){i==null||i();return}m(!0),x(null);try{const d=await f.telegramLinkToken();c(g.telegramBot,{source:"app_telegram_tab",action:"connect"}),window.open(d.bot_url,"_blank","noopener,noreferrer")}catch(d){x(d.message||r("tg.err"))}finally{m(!1)}}function u(){if(c(g.telegramBot,{source:"app_telegram_tab",action:"open_bot"}),e){l();return}window.open(N,"_blank","noopener,noreferrer")}return t.jsxs("div",{className:"tg-page",children:[t.jsxs("header",{className:"tg-hero",children:[t.jsx("p",{className:"tg-eyebrow mono",children:r("tg.path")}),t.jsx("h1",{className:"tg-title",children:r("tg.title")}),t.jsx("p",{className:"tg-sub",children:r("tg.subtitle")})]}),e&&t.jsxs("div",{className:`tg-status ${s?"ok":""}`,role:"status",children:[t.jsx("span",{className:"tg-status-dot","aria-hidden":!0}),t.jsxs("div",{children:[t.jsx("div",{className:"tg-status-title",children:r(s?"tg.status.linked":"tg.status.unlinked")}),t.jsx("div",{className:"tg-status-hint",children:r(s?n?"tg.status.linkedPremium":"tg.status.linkedFree":"tg.status.unlinkedHint")})]})]}),p&&t.jsx("div",{className:"tg-notice err",role:"alert",children:p}),t.jsxs("div",{className:"tg-actions",children:[t.jsx("button",{type:"button",className:"tg-btn primary",onClick:l,disabled:a,children:a?"…":r(s?"tg.btn.relink":"tg.btn.connect")}),t.jsx("button",{type:"button",className:"tg-btn",onClick:u,disabled:a,children:r("tg.btn.bot")})]}),t.jsxs("div",{className:"tg-grid",children:[t.jsxs("a",{className:"tg-card",href:j,target:"_blank",rel:"noopener noreferrer",onClick:()=>c(g.telegramBot,{source:"app_telegram_tab",action:"results"}),children:[t.jsx("div",{className:"tg-card-label mono",children:r("tg.card.resultsLabel")}),t.jsx("div",{className:"tg-card-value",children:r("tg.card.resultsValue")}),t.jsx("div",{className:"tg-card-hint",children:r("tg.card.resultsHint")})]}),t.jsxs("a",{className:"tg-card",href:k,target:"_blank",rel:"noopener noreferrer",children:[t.jsx("div",{className:"tg-card-label mono",children:r("tg.card.supportLabel")}),t.jsxs("div",{className:"tg-card-value",children:["@",y]}),t.jsx("div",{className:"tg-card-hint",children:r("tg.card.supportHint")})]}),t.jsxs("a",{className:"tg-card",href:`mailto:${h}`,children:[t.jsx("div",{className:"tg-card-label mono",children:r("tg.card.emailLabel")}),t.jsx("div",{className:"tg-card-value mono",children:h}),t.jsx("div",{className:"tg-card-hint",children:r("tg.card.emailHint")})]})]}),!n&&t.jsxs("div",{className:"tg-premium",children:[t.jsxs("div",{className:"tg-premium-copy",children:[t.jsx("div",{className:"tg-premium-title",children:r("tg.premium.title")}),t.jsx("div",{className:"tg-premium-hint",children:r("tg.premium.hint")})]}),t.jsx("button",{type:"button",className:"tg-btn primary",onClick:()=>o==null?void 0:o(),children:r("tg.premium.cta")})]}),n&&t.jsxs("div",{className:"tg-premium ok",children:[t.jsxs("div",{className:"tg-premium-copy",children:[t.jsx("div",{className:"tg-premium-title",children:r("tg.premium.activeTitle")}),t.jsx("div",{className:"tg-premium-hint",children:r("tg.premium.activeHint")})]}),t.jsx("button",{type:"button",className:"tg-btn primary",onClick:l,disabled:a,children:a?"…":r("tg.premium.inviteCta")})]}),t.jsxs("ol",{className:"tg-steps",children:[t.jsx("li",{children:r("tg.step1")}),t.jsx("li",{children:r("tg.step2")}),t.jsx("li",{children:r("tg.step3")})]}),t.jsx("style",{children:`
        .tg-page {
          max-width: 720px;
          margin: 0 auto;
          padding: 8px 4px 40px;
        }
        .tg-hero { margin-bottom: 22px; }
        .tg-eyebrow {
          font-size: 11px;
          color: var(--text-tertiary);
          letter-spacing: 0.04em;
          margin: 0 0 10px;
        }
        .tg-title {
          font-size: clamp(22px, 3vw, 28px);
          font-weight: 700;
          letter-spacing: -0.03em;
          margin: 0 0 8px;
          color: var(--text);
        }
        .tg-sub {
          margin: 0;
          font-size: 14px;
          line-height: 1.5;
          color: var(--text-secondary);
          max-width: 520px;
        }
        .tg-status {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 14px 16px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          margin-bottom: 16px;
        }
        .tg-status.ok { border-color: color-mix(in srgb, var(--long) 35%, var(--border)); }
        .tg-status-dot {
          width: 8px; height: 8px; border-radius: 50%;
          margin-top: 6px; flex-shrink: 0;
          background: var(--text-tertiary);
        }
        .tg-status.ok .tg-status-dot { background: var(--long); box-shadow: 0 0 0 3px color-mix(in srgb, var(--long) 22%, transparent); }
        .tg-status-title { font-size: 14px; font-weight: 650; color: var(--text); }
        .tg-status-hint { font-size: 13px; color: var(--text-secondary); margin-top: 3px; line-height: 1.45; }
        .tg-notice.err {
          padding: 12px 14px;
          border-radius: var(--radius-lg);
          background: color-mix(in srgb, var(--short) 12%, var(--surface));
          border: 1px solid color-mix(in srgb, var(--short) 30%, var(--border));
          color: var(--short);
          font-size: 13px;
          margin-bottom: 14px;
        }
        .tg-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-bottom: 22px;
        }
        .tg-btn {
          border: 1px solid var(--border);
          background: var(--surface);
          color: var(--text);
          border-radius: 980px;
          padding: 11px 18px;
          font-size: 13px;
          font-weight: 650;
          cursor: pointer;
          transition: transform 0.2s, opacity 0.2s, border-color 0.2s;
        }
        .tg-btn:hover:not(:disabled) { transform: translateY(-1px); border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); }
        .tg-btn:disabled { opacity: 0.55; cursor: default; }
        .tg-btn.primary {
          border: none;
          background: var(--text);
          color: var(--bg);
        }
        .tg-btn.primary:hover:not(:disabled) { border: none; filter: brightness(1.05); }
        .tg-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
          margin-bottom: 20px;
        }
        .tg-card {
          display: block;
          text-decoration: none;
          color: inherit;
          padding: 16px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card), var(--inset-highlight);
          transition: transform 0.2s, border-color 0.2s;
        }
        .tg-card:hover {
          transform: translateY(-2px);
          border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
        }
        .tg-card-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-tertiary);
          font-weight: 700;
        }
        .tg-card-value {
          font-size: 15px;
          font-weight: 700;
          margin: 8px 0 6px;
          color: var(--accent);
          word-break: break-word;
        }
        .tg-card-hint {
          font-size: 12px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
        .tg-premium {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          flex-wrap: wrap;
          padding: 16px 18px;
          border-radius: var(--radius-lg);
          background: var(--surface);
          border: 1px solid var(--border);
          margin-bottom: 22px;
        }
        .tg-premium.ok { border-color: color-mix(in srgb, var(--long) 35%, var(--border)); }
        .tg-premium-title { font-size: 14px; font-weight: 650; color: var(--text); }
        .tg-premium-hint { font-size: 13px; color: var(--text-secondary); margin-top: 4px; line-height: 1.45; max-width: 420px; }
        .tg-steps {
          margin: 0;
          padding: 0 0 0 18px;
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.7;
        }
        .tg-steps li { margin-bottom: 4px; }
        @media (max-width: 720px) {
          .tg-grid { grid-template-columns: 1fr; }
          .tg-actions .tg-btn { flex: 1; text-align: center; }
          .tg-premium .tg-btn { width: 100%; }
        }
      `})]})}export{z as default};
