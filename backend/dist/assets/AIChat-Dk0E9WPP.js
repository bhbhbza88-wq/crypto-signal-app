import{a as E,r as s,j as e}from"./index-DWgcX8Xm.js";import{a as z}from"./api-DXCafRhN.js";function R(a){return String(a).replace(/\*\*([^*]+)\*\*/g,"$1").replace(/`([^`]+)`/g,"$1").replace(/^#+\s*/gm,"").replace(/^\s*[-*•]\s+/gm,"  • ")}function T({role:a,content:n,streaming:o}){const u=R(n||" ").split(`
`),f=a==="user"?"you@nowicki ~ %":"nick@desk ~ %",m=a==="user"?"user":"asst";return e.jsx("div",{className:`term-block ${m}`,children:u.map((h,p)=>e.jsxs("div",{className:"term-line",children:[e.jsx("span",{className:"term-gutter",children:p===0?e.jsxs("span",{className:"term-prompt",children:[f," "]}):null}),e.jsxs("span",{className:"term-text",children:[h||" ",o&&p===u.length-1?e.jsx("span",{className:"term-cursor blink",children:"█"}):null]})]},p))})}function B(){var v;const{t:a}=E(),[n,o]=s.useState([{role:"assistant",content:a("ai.greeting")}]),[u,f]=s.useState(""),[m,h]=s.useState(!1),[p,x]=s.useState(!1),[k,j]=s.useState(null),N=s.useRef(null),g=s.useRef(null);s.useEffect(()=>{var t;(t=N.current)==null||t.scrollIntoView({behavior:"smooth"})},[n,m,p]),s.useEffect(()=>{var t;(t=g.current)==null||t.focus()},[]);function S(t){o(i=>{const l=[...i],c=l[l.length-1];return!c||c.role!=="assistant"?[...i,{role:"assistant",content:t}]:(l[l.length-1]={...c,content:c.content+t},l)})}async function q(t){if(!t.trim()||m)return;const i={role:"user",content:t},l=[...n.filter(r=>r.role!=="system").map(r=>({role:r.role,content:r.content})),i];o(r=>[...r,i]),f(""),h(!0),x(!1);let c=!1;try{if(await z.aiChatStream(l,{onToken:r=>{c?S(r):(c=!0,x(!0),o(d=>[...d,{role:"assistant",content:r}]))},onDone:({used:r,limit:d})=>{r!=null&&j({used:r,limit:d})}}),!c){const r=await z.aiChat(l);j({used:r.used,limit:r.limit});const d=r.reply||"";x(!0);let C="";o(b=>[...b,{role:"assistant",content:""}]);for(const b of d){C+=b;const M=C;o(y=>{const w=[...y];return w[w.length-1]={role:"assistant",content:M},w}),b!==" "&&await new Promise(y=>setTimeout(y,4))}}}catch(r){o(d=>[...d,{role:"assistant",content:`error: ${r.message}`}])}finally{x(!1),h(!1),requestAnimationFrame(()=>{var r;return(r=g.current)==null?void 0:r.focus()})}}const I=m&&!p&&((v=n[n.length-1])==null?void 0:v.role)==="user";return e.jsxs("div",{className:"ai-chat term-window",onClick:()=>{var t;return(t=g.current)==null?void 0:t.focus()},children:[e.jsxs("div",{className:"chat-titlebar",children:[e.jsxs("div",{className:"traffic-lights","aria-hidden":"true",children:[e.jsx("span",{className:"tl tl-close"}),e.jsx("span",{className:"tl tl-min"}),e.jsx("span",{className:"tl tl-max"})]}),e.jsx("div",{className:"chat-titlebar-center",children:e.jsx("span",{className:"chat-title",children:"nick — zsh — 120×40"})}),e.jsx("div",{className:"chat-header-right",children:k&&e.jsx("span",{className:"quota-text",children:a("ai.quotaToday",{used:k.used,limit:k.limit})})})]}),e.jsxs("div",{className:"term-body",children:[e.jsx("pre",{className:"term-boot",children:`# NOWICKI · octo-cmd
# session online · type a command / question
# ─────────────────────────────────────────`}),n.map((t,i)=>e.jsx(T,{role:t.role,content:t.content,streaming:p&&i===n.length-1&&t.role==="assistant"},i)),I&&e.jsx("div",{className:"term-block asst",children:e.jsxs("div",{className:"term-line",children:[e.jsx("span",{className:"term-gutter",children:e.jsx("span",{className:"term-prompt",children:"nick@desk ~ % "})}),e.jsx("span",{className:"term-text",children:e.jsx("span",{className:"term-cursor blink",children:"█"})})]})}),e.jsxs("div",{className:"term-input-row",children:[e.jsx("span",{className:"term-prompt",children:"you@nowicki ~ % "}),e.jsx("input",{ref:g,className:"term-input",value:u,onChange:t=>f(t.target.value),onKeyDown:t=>{t.key==="Enter"&&!t.shiftKey&&(t.preventDefault(),q(u))},placeholder:a("ai.placeholder"),disabled:m,spellCheck:!1,autoComplete:"off",autoCorrect:"off",autoCapitalize:"off"}),!m&&!u&&e.jsx("span",{className:"term-cursor blink ghost",children:"█"})]}),e.jsx("div",{ref:N})]}),e.jsx("style",{children:`
        .ai-chat.term-window {
          display: flex; flex-direction: column;
          height: 100%; width: 100%; min-height: 0;
          border-radius: 12px; overflow: hidden;
          background: #1e1e1e;
          border: 1px solid rgba(255,255,255,0.1);
          box-shadow:
            0 0 0 0.5px rgba(0,0,0,0.35),
            0 24px 56px rgba(0,0,0,0.45),
            inset 0 1px 0 rgba(255,255,255,0.08);
          font-family: var(--font-mono), ui-monospace, Menlo, Monaco, "Courier New", monospace;
        }

        .term-window .chat-titlebar {
          height: 40px; flex-shrink: 0;
          display: grid; grid-template-columns: 1fr auto 1fr;
          align-items: center; gap: 12px;
          padding: 0 14px;
          background: linear-gradient(180deg, #3a3a3c 0%, #2c2c2e 100%);
          border-bottom: 1px solid rgba(0,0,0,0.45);
        }
        .traffic-lights { display: flex; align-items: center; gap: 8px; justify-self: start; }
        .tl {
          width: 12px; height: 12px; border-radius: 50%;
          box-shadow: inset 0 0 0 0.5px rgba(0,0,0,0.25);
        }
        .tl-close { background: #ff5f57; }
        .tl-min { background: #febc2e; }
        .tl-max { background: #28c840; }
        .chat-titlebar-center { justify-self: center; }
        .chat-title {
          font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.72);
          font-family: var(--font-ui); letter-spacing: -0.01em;
        }
        .chat-header-right { justify-self: end; }
        .quota-text {
          font-size: 10px; color: rgba(255,255,255,0.4);
          font-family: var(--font-mono);
        }

        .term-body {
          flex: 1; overflow-y: auto; min-height: 0;
          padding: 14px 16px 18px;
          background: #0c0c0c;
          color: #d4d4d4;
          display: flex; flex-direction: column; gap: 14px;
        }
        .term-boot {
          margin: 0; white-space: pre-wrap;
          color: #6a9955; font-size: 12px; line-height: 1.45;
          font-family: inherit;
        }

        .term-block { display: flex; flex-direction: column; gap: 2px; }
        .term-line {
          display: grid;
          grid-template-columns: 16ch 1fr;
          align-items: start;
          font-size: 13px; line-height: 1.55; word-break: break-word;
        }
        .term-block.asst .term-line { grid-template-columns: 14ch 1fr; }
        .term-gutter { flex-shrink: 0; white-space: pre; }
        .term-prompt { font-weight: 600; white-space: pre; }
        .term-block.user .term-prompt { color: #4ec9b0; }
        .term-block.asst .term-prompt { color: #569cd6; }
        .term-text { color: #d4d4d4; white-space: pre-wrap; }
        .term-block.user .term-text { color: #ce9178; }
        .term-block.asst .term-text { color: #dcdcaa; }

        .term-cursor {
          display: inline-block; color: #4ec9b0;
          font-weight: 400; line-height: 1.55; font-size: 13px;
        }
        .term-cursor.ghost {
          position: absolute; pointer-events: none; margin-left: 2px;
          color: rgba(78, 201, 176, 0.7);
        }
        .term-cursor.blink { animation: termBlink 1.05s step-end infinite; }
        @keyframes termBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }

        .term-input-row {
          display: flex; align-items: center; position: relative;
          font-size: 13px; line-height: 1.55; margin-top: 4px;
        }
        .term-input-row .term-prompt { color: #4ec9b0; }
        .term-input {
          flex: 1; min-width: 0;
          background: transparent; border: none; outline: none;
          color: #ce9178; font-family: inherit; font-size: 13px;
          line-height: 1.55; padding: 0; caret-color: #4ec9b0;
        }
        .term-input::placeholder { color: rgba(255,255,255,0.22); }
        .term-input:disabled { opacity: 0.5; }

        .term-body::-webkit-scrollbar { width: 8px; }
        .term-body::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.12); border-radius: 4px;
        }
        .term-body::-webkit-scrollbar-track { background: transparent; }

        @media (max-width: 720px) {
          .quota-text { display: none; }
          .term-body { padding: 12px; }
          .term-line, .term-input-row, .term-input { font-size: 12px; }
          .term-line, .term-block.asst .term-line { grid-template-columns: 1fr; }
          .term-gutter:empty { display: none; }
        }
      `})]})}export{B as default};
