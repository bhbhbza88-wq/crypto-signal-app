import{a as M,r as d,j as a}from"./index-DWgcX8Xm.js";import{a as _}from"./api-DXCafRhN.js";const U=1400,q=.82;function P(n){if(!n)return!1;const s=(n.type||"").toLowerCase();if(s.startsWith("image/"))return!0;const e=(n.name||"").toLowerCase();return/\.(jpe?g|png|webp|heic|heif|gif)$/i.test(e)||!s}async function B(n){try{return await createImageBitmap(n)}catch{const s=URL.createObjectURL(n);try{const e=await new Promise((r,l)=>{const x=new Image;x.onload=()=>r(x),x.onerror=l,x.src=s}),t=document.createElement("canvas");return t.width=e.naturalWidth||e.width,t.height=e.naturalHeight||e.height,t.getContext("2d").drawImage(e,0,0),await createImageBitmap(t)}finally{URL.revokeObjectURL(s)}}}async function H(n){const s=await B(n),e=Math.min(1,U/Math.max(s.width,s.height)),t=Math.max(1,Math.round(s.width*e)),r=Math.max(1,Math.round(s.height*e)),l=document.createElement("canvas");l.width=t,l.height=r;const x=l.getContext("2d");x.fillStyle="#000",x.fillRect(0,0,t,r),x.drawImage(s,0,0,t,r),s.close();const f=await new Promise(m=>l.toBlob(m,"image/jpeg",q));if(!f)throw new Error("compress_failed");const u=await new Promise((m,h)=>{const g=new FileReader;g.onload=()=>m(g.result),g.onerror=h,g.readAsDataURL(f)});return{base64:String(u).split(",")[1]||"",mediaType:"image/jpeg",previewUrl:u,width:t,height:r}}function I({bias:n,t:s}){const e={long:{cls:"ca-bias long",label:s("chart.biasLong")},short:{cls:"ca-bias short",label:s("chart.biasShort")},flat:{cls:"ca-bias flat",label:s("chart.biasFlat")}},t=e[n]||e.flat;return a.jsx("span",{className:t.cls,children:t.label})}function $({confidence:n,t:s}){const e=n==="high"?"chart.confHigh":n==="medium"?"chart.confMed":"chart.confLow";return a.jsx("span",{className:`ca-conf ${n||"low"}`,children:s(e)})}function D(n,s){if(!n)return"";const e=new Date(n);if(Number.isNaN(e.getTime()))return"";const t=Date.now()-e.getTime(),r=Math.floor(t/6e4);if(r<60)return s("chart.social.agoMin",{n:Math.max(1,r)});const l=Math.floor(r/60);if(l<48)return s("chart.social.agoHrs",{n:l});const x=Math.floor(l/24);return s("chart.social.agoDays",{n:x})}function F({user:n,onNeedAuth:s,analysisDone:e}){const{t}=M(),[r,l]=d.useState(null),[x,f]=d.useState([]),[u,k]=d.useState(!0),[m,h]=d.useState(!1),[g,N]=d.useState(null),[b,j]=d.useState(null),v=d.useCallback(async()=>{try{const c=await _.getChartReviews(48);l(c.stats),f(c.reviews||[])}catch{}finally{k(!1)}},[]);d.useEffect(()=>{v()},[v]),d.useEffect(()=>{e&&(j(null),v())},[e,v]);async function y(c){if(!n){s==null||s();return}if(!(!z||m)){h(!0),N(null);try{const w=await _.voteChartHelp(c);w.stats&&l(w.stats),j(c)}catch(w){N(w.message||t("chart.social.err")),v()}finally{h(!1)}}}const L=(r==null?void 0:r.helped)??627,S=(r==null?void 0:r.not_helped)??244,C=(r==null?void 0:r.winrate)??72,z=!!(e&&(r!=null&&r.can_vote)),o=e&&!(r!=null&&r.can_vote)&&(b!=null||(r==null?void 0:r.my_vote)!=null),R=!!n;return a.jsxs("section",{className:"ca-social",children:[a.jsxs("div",{className:"ca-social-head",children:[a.jsxs("div",{children:[a.jsx("div",{className:"ca-social-kicker mono",children:t("chart.social.kicker")}),a.jsx("h2",{className:"ca-social-title",children:t("chart.social.title")}),a.jsx("p",{className:"ca-social-sub",children:t("chart.social.sub")})]}),a.jsxs("div",{className:"ca-social-stats",children:[a.jsxs("div",{className:"ca-stat accent",children:[a.jsxs("span",{className:"ca-stat-val mono",children:[L.toLocaleString("ru-RU"),"+"]}),a.jsx("span",{className:"ca-stat-lbl",children:t("chart.social.helped")})]}),a.jsxs("div",{className:"ca-stat",children:[a.jsxs("span",{className:"ca-stat-val mono",children:[C,"%"]}),a.jsx("span",{className:"ca-stat-lbl",children:t("chart.social.winrate")})]}),a.jsxs("div",{className:"ca-stat",children:[a.jsx("span",{className:"ca-stat-val mono",children:S.toLocaleString("ru-RU")}),a.jsx("span",{className:"ca-stat-lbl",children:t("chart.social.notHelped")})]})]})]}),a.jsxs("div",{className:"ca-social-grid",children:[a.jsxs("div",{className:"ca-social-feed",children:[u&&a.jsx("div",{className:"ca-social-empty mono",children:t("chart.social.loading")}),!u&&x.map(c=>a.jsxs("article",{className:"ca-review",children:[a.jsxs("div",{className:"ca-review-top",children:[a.jsx("span",{className:"ca-review-avatar",children:(c.display_name||"?").charAt(0).toUpperCase()}),a.jsxs("div",{className:"ca-review-who",children:[a.jsx("strong",{children:c.display_name}),a.jsx("span",{className:"mono",children:D(c.created_at,t)})]}),a.jsxs("div",{className:"ca-review-trade",children:[a.jsx("span",{className:"mono",children:c.symbol}),a.jsx("span",{className:`ca-review-side ${String(c.side).toLowerCase()}`,children:c.side}),a.jsxs("span",{className:`mono ${c.pnl_pct>=0?"pos":"neg"}`,children:[c.pnl_pct>=0?"+":"",Number(c.pnl_pct).toFixed(1),"%"]})]})]}),a.jsx("p",{className:"ca-review-text",children:c.comment})]},c.id))]}),a.jsxs("div",{className:`ca-social-vote ${z?"open":"locked"}`,children:[a.jsx("div",{className:"ca-form-title mono",children:t("chart.social.voteTitle")}),R?e?z?a.jsxs(a.Fragment,{children:[a.jsx("p",{className:"ca-form-hint",children:t("chart.social.voteHint")}),a.jsxs("div",{className:"ca-vote-row",children:[a.jsxs("button",{type:"button",className:"ca-vote-btn up",disabled:m,onClick:()=>y(!0),children:[a.jsx("span",{className:"ca-vote-ico",children:"+"}),a.jsx("span",{children:t("chart.social.voteYes")})]}),a.jsxs("button",{type:"button",className:"ca-vote-btn down",disabled:m,onClick:()=>y(!1),children:[a.jsx("span",{className:"ca-vote-ico",children:"−"}),a.jsx("span",{children:t("chart.social.voteNo")})]})]})]}):o?a.jsxs("div",{className:"ca-social-ok",children:[b??(r==null?void 0:r.my_vote)?t("chart.social.votedYes"):t("chart.social.votedNo"),a.jsx("div",{className:"ca-form-hint",style:{marginTop:8},children:t("chart.social.voteAgain")})]}):a.jsx("p",{className:"ca-form-hint",children:t("chart.social.voteNeedAnalyze")}):a.jsx("p",{className:"ca-form-hint",children:t("chart.social.voteNeedAnalyze")}):a.jsx("p",{className:"ca-form-hint",children:t("chart.social.voteNeedAuth")}),g&&a.jsx("div",{className:"ca-error",children:g})]})]})]})}function G({user:n,onNeedAuth:s}){var c,w,T,E;const{t:e,lang:t}=M(),r=d.useRef(null),[l,x]=d.useState(null),[f,u]=d.useState(null),[k,m]=d.useState(""),[h,g]=d.useState(!1),[N,b]=d.useState(null),[j,v]=d.useState(null),[y,L]=d.useState(null),S=d.useCallback(()=>{x(null),u(null),v(null),b(null),m(""),r.current&&(r.current.value="")},[]);async function C(i){if(i){b(null),v(null);try{if(!P(i)){b(e("chart.errType"));return}const p=await H(i);x(p.previewUrl),u(p)}catch{b(e("chart.errCompress"))}}}async function z(){if(!n){s==null||s();return}if(!(!f||h)){g(!0),b(null);try{const i=await _.chartAnalyze({image_base64:f.base64,media_type:f.mediaType,question:k.trim()||void 0,language:t});v(i.analysis),L({used:i.used,limit:i.limit})}catch(i){b(i.message||e("chart.errGeneric"))}finally{g(!1)}}}const o=j,R=o!=null&&o.symbol?`nowicki.trade/chart/${String(o.symbol).replace("/","")}`:"nowicki.trade/app/chart";return a.jsxs("div",{className:"ca-safari",children:[a.jsxs("div",{className:"sf-chrome",children:[a.jsxs("div",{className:"sf-titlebar",children:[a.jsxs("div",{className:"sf-lights","aria-hidden":"true",children:[a.jsx("span",{className:"sf-dot close"}),a.jsx("span",{className:"sf-dot min"}),a.jsx("span",{className:"sf-dot max"})]}),a.jsx("div",{className:"sf-tabs",children:a.jsxs("div",{className:"sf-tab active",children:[a.jsx("span",{className:"sf-tab-label",children:e("chart.title")}),a.jsx("span",{className:"sf-beta",children:"BETA"})]})})]}),a.jsxs("div",{className:"sf-toolbar",children:[a.jsxs("div",{className:"sf-nav",children:[a.jsx("button",{type:"button",className:"sf-nav-btn",disabled:!0,"aria-label":"Back",children:"‹"}),a.jsx("button",{type:"button",className:"sf-nav-btn",disabled:!0,"aria-label":"Forward",children:"›"}),a.jsx("button",{type:"button",className:"sf-nav-btn",onClick:S,"aria-label":"Refresh",children:"↻"})]}),a.jsxs("div",{className:"sf-urlbar",children:[a.jsx("span",{className:"sf-lock","aria-hidden":"true"}),a.jsx("span",{className:"sf-url mono",children:R}),h&&a.jsx("span",{className:"sf-pip","aria-hidden":"true"})]}),a.jsx("div",{className:"sf-toolbar-right",children:y&&a.jsx("span",{className:"sf-quota mono",children:e("chart.quota",{used:y.used,limit:y.limit})})})]})]}),a.jsxs("div",{className:"sf-page",children:[a.jsxs("div",{className:"ca-grid",children:[a.jsxs("div",{className:"ca-panel",children:[a.jsxs("div",{className:`ca-drop ${l?"has":""}`,onDragOver:i=>i.preventDefault(),onDrop:i=>{var p;i.preventDefault(),C((p=i.dataTransfer.files)==null?void 0:p[0])},onClick:()=>{var i;return(i=r.current)==null?void 0:i.click()},children:[a.jsx("input",{ref:r,type:"file",accept:"image/*,.heic,.heif,.jpg,.jpeg,.png,.webp",hidden:!0,onChange:i=>{var p;return C((p=i.target.files)==null?void 0:p[0])}}),l?a.jsx("img",{src:l,alt:"",className:"ca-preview"}):a.jsxs("div",{className:"ca-drop-empty",children:[a.jsx("span",{className:"ca-drop-ico",children:"▣"}),a.jsx("strong",{children:e("chart.dropTitle")}),a.jsx("span",{children:e("chart.dropHint")})]})]}),a.jsxs("label",{className:"ca-q",children:[a.jsx("span",{children:e("chart.question")}),a.jsx("textarea",{value:k,onChange:i=>m(i.target.value),placeholder:e("chart.questionPh"),rows:2,maxLength:300})]}),a.jsxs("div",{className:"ca-actions",children:[a.jsx("button",{className:"btn-primary ca-run",disabled:!f||h,onClick:z,children:e(h?"chart.analyzing":"chart.run")}),(l||j)&&a.jsx("button",{type:"button",className:"ca-clear",onClick:S,children:e("chart.clear")})]}),N&&a.jsx("div",{className:"ca-error",children:N})]}),a.jsxs("div",{className:"ca-panel ca-result",children:[!o&&!h&&a.jsxs("div",{className:"ca-empty",children:[a.jsx("h3",{children:e("chart.emptyTitle")}),a.jsx("p",{children:e("chart.emptyBody")}),a.jsxs("ul",{children:[a.jsx("li",{children:e("chart.rule1")}),a.jsx("li",{children:e("chart.rule2")}),a.jsx("li",{children:e("chart.rule3")})]})]}),h&&a.jsxs("div",{className:"ca-empty",children:[a.jsx("div",{className:"ca-spinner"}),a.jsx("p",{children:e("chart.analyzing")})]}),o&&!h&&a.jsxs("div",{className:"ca-out",children:[a.jsxs("div",{className:`ca-take ${o.bias||"flat"}`,children:[a.jsx("span",{className:"ca-take-label",children:e("chart.myTake")}),a.jsx("p",{children:o.take||e("chart.noReasons")})]}),a.jsxs("div",{className:"ca-out-head",children:[a.jsx(I,{bias:o.bias,t:e}),a.jsx($,{confidence:o.confidence,t:e}),!o.evidence_ok&&a.jsx("span",{className:"ca-warn",children:e("chart.weakEvidence")})]}),a.jsxs("div",{className:"ca-meta",children:[o.symbol&&a.jsx("span",{className:"mono",children:o.symbol}),o.timeframe&&a.jsx("span",{children:o.timeframe}),o.price_hint&&a.jsx("span",{className:"mono",children:o.price_hint})]}),!!((c=o.seen)!=null&&c.length)&&a.jsxs("section",{children:[a.jsx("h4",{children:e("chart.seen")}),a.jsx("ul",{children:o.seen.map((i,p)=>a.jsx("li",{children:i},p))})]}),a.jsxs("section",{children:[a.jsx("h4",{children:e("chart.reasons")}),a.jsx("ul",{children:((w=o.reasons)!=null&&w.length?o.reasons:[e("chart.noReasons")]).map((i,p)=>a.jsx("li",{children:i},p))})]}),a.jsxs("section",{className:"ca-inv",children:[a.jsx("h4",{children:e("chart.invalidation")}),a.jsx("p",{children:o.invalidation})]}),!!((T=o.risks)!=null&&T.length)&&a.jsxs("section",{children:[a.jsx("h4",{children:e("chart.risks")}),a.jsx("ul",{children:o.risks.map((i,p)=>a.jsx("li",{children:i},p))})]}),!!((E=o.watch)!=null&&E.length)&&a.jsxs("section",{children:[a.jsx("h4",{children:e("chart.watch")}),a.jsx("ul",{children:o.watch.map((i,p)=>a.jsx("li",{children:i},p))})]}),a.jsx("p",{className:"ca-disc",children:o.disclaimer||e("chart.disclaimer")})]})]})]}),a.jsx(F,{user:n,onNeedAuth:s,analysisDone:!!j})]}),a.jsx("style",{children:`
        .ca-safari {
          --sf-chrome: color-mix(in srgb, var(--surface) 88%, #8a8a90);
          --sf-chrome-2: color-mix(in srgb, var(--surface-2) 70%, #6e6e73);
          --sf-line: color-mix(in srgb, var(--border) 80%, #000);
          display: flex; flex-direction: column;
          height: 100%;
          max-height: 100%;
          min-height: 0;
          border-radius: 12px; overflow: hidden;
          background: var(--bg);
          border: 1px solid var(--border);
          box-shadow:
            0 0 0 0.5px color-mix(in srgb, var(--border) 60%, transparent),
            0 18px 48px color-mix(in srgb, #000 28%, transparent),
            inset 0 1px 0 color-mix(in srgb, #fff 10%, transparent);
        }

        .sf-chrome { flex-shrink: 0; }
        .sf-titlebar {
          display: flex; align-items: flex-end; gap: 10px;
          padding: 10px 12px 0;
          background: linear-gradient(180deg, var(--sf-chrome) 0%, var(--sf-chrome-2) 100%);
          border-bottom: 1px solid var(--sf-line);
          min-height: 44px;
        }
        .sf-lights {
          display: flex; align-items: center; gap: 7px;
          padding: 0 4px 12px; flex-shrink: 0;
        }
        .sf-dot {
          width: 12px; height: 12px; border-radius: 50%;
          box-shadow: inset 0 0 0 0.5px rgba(0,0,0,0.22);
        }
        .sf-dot.close { background: #ff5f57; }
        .sf-dot.min { background: #febc2e; }
        .sf-dot.max { background: #28c840; }

        .sf-tabs {
          display: flex; align-items: flex-end; gap: 2px;
          flex: 1; min-width: 0; overflow: hidden;
        }
        .sf-tab {
          display: flex; align-items: center; gap: 8px;
          max-width: 240px; min-width: 120px;
          padding: 8px 14px 9px;
          border-radius: 9px 9px 0 0;
          background: color-mix(in srgb, var(--bg) 55%, transparent);
          border: 1px solid transparent;
          border-bottom: none;
          color: var(--text-secondary);
          font-size: 12px; font-weight: 600;
        }
        .sf-tab.active {
          background: var(--bg);
          color: var(--text);
          border-color: var(--sf-line);
          box-shadow: 0 -1px 0 color-mix(in srgb, #fff 6%, transparent);
          position: relative; z-index: 1;
          margin-bottom: -1px; padding-bottom: 10px;
        }
        .sf-tab-label {
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
          font-family: var(--font-ui);
          letter-spacing: -0.01em;
        }
        .sf-beta {
          flex-shrink: 0;
          font-size: 9px; font-weight: 800; letter-spacing: 0.06em;
          padding: 2px 6px; border-radius: 5px;
          background: var(--accent-soft); color: var(--accent);
          font-family: var(--font-mono);
        }

        .sf-toolbar {
          display: grid; grid-template-columns: auto 1fr auto;
          align-items: center; gap: 10px;
          padding: 8px 12px;
          background: color-mix(in srgb, var(--surface) 92%, var(--bg));
          border-bottom: 1px solid var(--border);
        }
        .sf-nav { display: flex; align-items: center; gap: 2px; }
        .sf-nav-btn {
          width: 28px; height: 28px; border-radius: 7px;
          border: none; background: transparent;
          color: var(--text-secondary); font-size: 16px; line-height: 1;
          cursor: pointer; display: grid; place-items: center;
        }
        .sf-nav-btn:hover:not(:disabled) {
          background: color-mix(in srgb, var(--surface-2) 80%, transparent);
          color: var(--text);
        }
        .sf-nav-btn:disabled { opacity: 0.35; cursor: default; }

        .sf-urlbar {
          display: flex; align-items: center; justify-content: center; gap: 8px;
          min-height: 30px; padding: 0 14px;
          border-radius: 9px;
          background: color-mix(in srgb, var(--bg) 70%, var(--surface-2));
          border: 1px solid var(--border);
          box-shadow: inset 0 1px 2px color-mix(in srgb, #000 8%, transparent);
          max-width: 520px; width: 100%; margin: 0 auto;
        }
        .sf-lock {
          width: 14px; height: 14px; flex-shrink: 0;
          display: grid; place-items: center;
          font-size: 11px; line-height: 1; opacity: 0.75;
        }
        .sf-lock::before { content: '🔒'; }
        .sf-url {
          font-size: 12px; color: var(--text-secondary);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
          letter-spacing: -0.01em;
        }
        .sf-pip {
          width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
          background: var(--accent);
          box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
          animation: sf-pulse 1s ease-in-out infinite;
        }
        @keyframes sf-pulse {
          0%, 100% { opacity: 0.45; transform: scale(0.9); }
          50% { opacity: 1; transform: scale(1); }
        }
        .sf-toolbar-right {
          min-width: 72px; display: flex; justify-content: flex-end;
        }
        .sf-quota {
          font-size: 11px; color: var(--text-tertiary); white-space: nowrap;
        }

        .sf-page {
          flex: 1; min-height: 0; overflow: auto;
          padding: 18px 18px 24px;
          background: var(--bg);
        }

        .ca-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 900px) { .ca-grid { grid-template-columns: 1fr; } }
        .ca-panel {
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 12px; padding: 18px;
          box-shadow: var(--inset-highlight);
          backdrop-filter: saturate(160%) blur(16px);
        }
        .ca-drop {
          border: 1px dashed color-mix(in srgb, var(--accent) 35%, var(--border));
          border-radius: var(--radius-md); min-height: 220px; cursor: pointer;
          display: grid; place-items: center; overflow: hidden;
          background: color-mix(in srgb, var(--surface-2) 70%, transparent);
          transition: border-color .15s, background .15s;
        }
        .ca-drop:hover { border-color: var(--accent); }
        .ca-drop.has { border-style: solid; }
        .ca-drop-empty { text-align: center; padding: 24px; display: flex; flex-direction: column; gap: 6px; color: var(--text-secondary); }
        .ca-drop-empty strong { color: var(--text); font-size: 15px; }
        .ca-drop-empty span:last-child { font-size: 12px; color: var(--text-tertiary); }
        .ca-drop-ico { font-size: 28px; color: var(--accent); margin-bottom: 4px; }
        .ca-preview { width: 100%; max-height: 320px; object-fit: contain; display: block; background: #0a0a0a; }
        .ca-q {
          display: flex; flex-direction: column; gap: 6px; margin-top: 14px;
          font-size: 11px; font-weight: 700; letter-spacing: .04em;
          text-transform: uppercase; color: var(--text-tertiary);
        }
        .ca-q textarea {
          border: 1px solid var(--border); background: var(--surface-2); color: var(--text);
          border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; font-weight: 500;
          text-transform: none; letter-spacing: 0; font-family: inherit;
          resize: vertical; min-height: 64px;
        }
        .ca-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 14px; }
        .ca-run { min-width: 140px; }
        .ca-clear {
          border: 1px solid var(--border); background: transparent; color: var(--text-secondary);
          border-radius: 980px; padding: 10px 16px; cursor: pointer; font-size: 13px; font-weight: 600;
        }
        .ca-error {
          margin-top: 12px; padding: 10px 12px; border-radius: 10px; font-size: 13px;
          background: color-mix(in srgb, var(--danger, #e25) 12%, transparent);
          color: var(--danger, #e25); border: 1px solid color-mix(in srgb, var(--danger, #e25) 30%, var(--border));
        }
        .ca-result { min-height: 360px; }
        .ca-empty { color: var(--text-secondary); padding: 12px 4px; }
        .ca-empty h3 { margin: 0 0 8px; color: var(--text); font-size: 16px; }
        .ca-empty p { margin: 0 0 12px; font-size: 13px; line-height: 1.5; }
        .ca-empty ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.6; }
        .ca-spinner {
          width: 28px; height: 28px; border-radius: 50%;
          border: 2px solid var(--border); border-top-color: var(--accent);
          animation: ca-spin .8s linear infinite; margin-bottom: 12px;
        }
        @keyframes ca-spin { to { transform: rotate(360deg); } }
        .ca-out-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
        .ca-take {
          margin: 0 0 14px; padding: 14px 16px; border-radius: var(--radius-md);
          border: 1px solid var(--border);
          background: color-mix(in srgb, var(--surface-2) 80%, transparent);
        }
        .ca-take.long {
          border-color: color-mix(in srgb, var(--long) 40%, var(--border));
          background: color-mix(in srgb, var(--long) 10%, var(--surface));
        }
        .ca-take.short {
          border-color: color-mix(in srgb, var(--short) 40%, var(--border));
          background: color-mix(in srgb, var(--short) 10%, var(--surface));
        }
        .ca-take-label {
          display: block; margin-bottom: 6px;
          font-size: 11px; font-weight: 800; letter-spacing: .06em;
          text-transform: uppercase; color: var(--text-tertiary);
        }
        .ca-take p {
          margin: 0; font-size: 16px; line-height: 1.45; font-weight: 650; color: var(--text);
        }
        .ca-bias {
          font-size: 12px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
          padding: 6px 10px; border-radius: 999px; border: 1px solid var(--border);
        }
        .ca-bias.long { color: var(--long); border-color: color-mix(in srgb, var(--long) 40%, var(--border)); }
        .ca-bias.short { color: var(--short); border-color: color-mix(in srgb, var(--short) 40%, var(--border)); }
        .ca-bias.flat { color: var(--text-secondary); }
        .ca-conf {
          font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
          padding: 6px 10px; border-radius: 999px; background: var(--surface-2); color: var(--text-secondary);
        }
        .ca-conf.high { color: var(--accent); }
        .ca-conf.medium { color: var(--amber, #d4a017); }
        .ca-warn {
          font-size: 11px; font-weight: 700; color: var(--amber, #d4a017);
          border: 1px solid color-mix(in srgb, var(--amber, #d4a017) 35%, var(--border));
          padding: 5px 8px; border-radius: 8px;
        }
        .ca-meta { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; font-size: 13px; color: var(--text-secondary); }
        .ca-out section { margin-bottom: 14px; }
        .ca-out h4 {
          margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
          color: var(--text-tertiary); font-weight: 800;
        }
        .ca-out ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.55; color: var(--text); }
        .ca-inv p { margin: 0; font-size: 14px; line-height: 1.5; color: var(--text); }
        .ca-disc {
          margin: 18px 0 0; padding-top: 12px; border-top: 1px solid var(--border);
          font-size: 12px; color: var(--text-tertiary); line-height: 1.45;
        }

        /* ── Social proof / review wall ── */
        .ca-social {
          margin-top: 28px; padding: 22px;
          background: var(--surface); border: 1px solid var(--border);
          border-radius: 14px; box-shadow: var(--inset-highlight);
        }
        .ca-social-head {
          display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap;
          margin-bottom: 18px; align-items: flex-end;
        }
        .ca-social-kicker {
          font-size: 11px; color: var(--accent); margin-bottom: 6px;
        }
        .ca-social-title {
          margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.03em;
          font-family: var(--font-display); color: var(--text);
        }
        .ca-social-sub {
          margin: 6px 0 0; font-size: 13px; color: var(--text-secondary); max-width: 48ch; line-height: 1.45;
        }
        .ca-social-stats { display: flex; gap: 10px; flex-wrap: wrap; }
        .ca-stat {
          min-width: 110px; padding: 12px 14px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 55%, transparent);
          border: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px;
        }
        .ca-stat.accent {
          background: linear-gradient(160deg, color-mix(in srgb, var(--bg) 40%, transparent), var(--accent-soft));
          border-color: color-mix(in srgb, var(--accent) 28%, var(--border));
        }
        .ca-stat-val { font-size: 22px; font-weight: 700; color: var(--text); letter-spacing: -0.03em; }
        .ca-stat-val.pos { color: var(--long); }
        .ca-stat-lbl { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
        .ca-social-grid {
          display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; align-items: start;
        }
        @media (max-width: 900px) { .ca-social-grid { grid-template-columns: 1fr; } }
        .ca-social-feed {
          display: flex; flex-direction: column; gap: 10px;
          max-height: 520px; overflow: auto; padding-right: 4px;
        }
        .ca-social-empty { font-size: 12px; color: var(--text-tertiary); padding: 20px; }
        .ca-review {
          padding: 12px 14px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 50%, transparent);
          border: 1px solid var(--border);
        }
        .ca-review-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .ca-review-avatar {
          width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0;
          display: grid; place-items: center;
          background: var(--accent-soft); color: var(--accent);
          font-weight: 700; font-size: 13px; font-family: var(--font-mono);
        }
        .ca-review-who { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
        .ca-review-who strong { font-size: 13px; color: var(--text); }
        .ca-review-who span { font-size: 10px; color: var(--text-tertiary); }
        .ca-review-trade { display: flex; align-items: center; gap: 8px; font-size: 12px; }
        .ca-review-side {
          font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; font-family: var(--font-mono);
        }
        .ca-review-side.long { background: var(--long-soft); color: var(--long); }
        .ca-review-side.short { background: var(--short-soft); color: var(--short); }
        .ca-review-text {
          margin: 10px 0 0; font-size: 13px; line-height: 1.45; color: var(--text-secondary);
        }
        .ca-social-form {
          padding: 16px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 45%, transparent);
          border: 1px solid var(--border);
          display: flex; flex-direction: column; gap: 10px;
          position: sticky; top: 72px;
        }
        .ca-social-vote {
          padding: 18px 16px; border-radius: 12px;
          background: color-mix(in srgb, var(--bg) 45%, transparent);
          border: 1px solid var(--border);
          display: flex; flex-direction: column; gap: 12px;
          position: sticky; top: 72px;
        }
        .ca-social-vote.locked { opacity: 0.92; }
        .ca-social-vote.open {
          border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 12%, transparent);
        }
        .ca-form-title { font-size: 12px; color: var(--accent); font-weight: 600; }
        .ca-form-hint { margin: 0; font-size: 12px; color: var(--text-tertiary); line-height: 1.4; }
        .ca-vote-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .ca-vote-btn {
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          gap: 6px; min-height: 96px; border-radius: 12px; cursor: pointer;
          border: 1px solid var(--border); background: var(--surface);
          color: var(--text); font-size: 13px; font-weight: 650;
          transition: border-color .15s, background .15s, transform .12s;
        }
        .ca-vote-btn:hover:not(:disabled) { transform: translateY(-1px); }
        .ca-vote-btn:disabled { opacity: 0.6; cursor: wait; }
        .ca-vote-btn.up:hover:not(:disabled), .ca-vote-btn.up.active {
          border-color: color-mix(in srgb, var(--long) 45%, var(--border));
          background: var(--long-soft); color: var(--long);
        }
        .ca-vote-btn.down:hover:not(:disabled), .ca-vote-btn.down.active {
          border-color: color-mix(in srgb, var(--short) 45%, var(--border));
          background: var(--short-soft); color: var(--short);
        }
        .ca-vote-ico {
          font-size: 28px; font-weight: 700; line-height: 1;
          font-family: var(--font-mono);
        }
        .ca-social-ok {
          font-size: 12px; color: var(--long); background: var(--long-soft);
          padding: 8px 10px; border-radius: 8px;
        }
        .ca-social .pos { color: var(--long); }
        .ca-social .neg { color: var(--short); }

        @media (max-width: 640px) {
          .sf-toolbar { grid-template-columns: auto 1fr; }
          .sf-toolbar-right { grid-column: 1 / -1; justify-content: flex-start; }
          .sf-urlbar { max-width: none; }
        }
      `})]})}export{G as default};
