import{a as f,c as v,u as b,r,j as e,L as m}from"./index-DWgcX8Xm.js";import{a as w,s as y}from"./api-DXCafRhN.js";function z(){const{t:a}=f(),[n]=v(),d=b(),[t,s]=r.useState("loading"),[p,o]=r.useState("");return r.useEffect(()=>{const u=n.get("token");if(!u){s("err"),o(a("auth.verify.noToken"));return}w.verifyEmail(u).then(i=>{y(i.token),s("ok"),o(a("auth.verify.success")),setTimeout(()=>d("/app/overview",{replace:!0}),1200)}).catch(i=>{s("err"),o(i.message||a("auth.verify.failed"))})},[n,d]),e.jsxs(k,{title:a("auth.verify.title"),children:[t==="loading"&&e.jsx("p",{className:"as-muted",children:a("auth.verify.checking")}),t==="ok"&&e.jsx("p",{className:"as-ok",children:p}),t==="err"&&e.jsxs(e.Fragment,{children:[e.jsx("p",{className:"as-err",children:p}),e.jsx(m,{to:"/",className:"as-link",children:a("auth.verify.home")})]})]})}function P(){const{t:a}=f(),[n]=v(),d=b(),t=n.get("token")||"",[s,p]=r.useState(""),[o,u]=r.useState(""),[i,l]=r.useState(null),[x,g]=r.useState(!1);async function j(c){if(c.preventDefault(),l(null),s.length<8){l(a("auth.reset.minLength"));return}if(s!==o){l(a("auth.reset.mismatch"));return}if(!t){l(a("auth.reset.noToken"));return}g(!0);try{const h=await w.resetPassword(t,s);y(h.token),d("/app/overview",{replace:!0})}catch(h){l(h.message)}finally{g(!1)}}return e.jsx(k,{title:a("auth.reset.title"),children:t?e.jsxs("form",{onSubmit:j,className:"as-form",children:[e.jsx("label",{className:"as-label",children:a("auth.reset.newPassword")}),e.jsx("input",{className:"as-input",type:"password",autoComplete:"new-password",minLength:8,value:s,onChange:c=>p(c.target.value),required:!0}),e.jsx("label",{className:"as-label",children:a("auth.reset.repeat")}),e.jsx("input",{className:"as-input",type:"password",autoComplete:"new-password",minLength:8,value:o,onChange:c=>u(c.target.value),required:!0}),i&&e.jsx("p",{className:"as-err",children:i}),e.jsx("button",{className:"as-btn",type:"submit",disabled:x,children:x?"...":a("auth.reset.save")})]}):e.jsxs(e.Fragment,{children:[e.jsx("p",{className:"as-err",children:a("auth.reset.incompleteLink")}),e.jsx(m,{to:"/",className:"as-link",children:a("auth.verify.home")})]})})}function k({title:a,children:n}){return e.jsxs("div",{className:"as-page",children:[e.jsxs("div",{className:"as-card",children:[e.jsx(m,{to:"/",className:"as-brand",children:"NOWICKI"}),e.jsx("h1",{className:"as-title",children:a}),n]}),e.jsx("style",{children:`
        .as-page { min-height: 100vh; display: grid; place-items: center; padding: 24px;
          background:
            radial-gradient(ellipse 80% 50% at 20% 0%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 55%),
            radial-gradient(ellipse 60% 40% at 90% 100%, color-mix(in srgb, var(--long) 8%, transparent), transparent 50%),
            var(--bg); }
        .as-card {
          width: 100%; max-width: 400px; background: var(--glass);
          border: 1px solid var(--glass-border); border-radius: var(--radius-lg); padding: 28px;
          box-shadow: var(--shadow-lg), var(--inset-highlight);
          backdrop-filter: saturate(180%) blur(28px);
          -webkit-backdrop-filter: saturate(180%) blur(28px);
        }
        .as-brand { font-family: var(--font-display); font-weight: 700;
          font-size: 18px; color: var(--accent); letter-spacing: -0.03em; }
        .as-title { font-family: var(--font-display); font-size: 24px;
          font-weight: 700; margin: 16px 0 12px; color: var(--text); letter-spacing: -0.02em; }
        .as-form { display: flex; flex-direction: column; gap: 8px; }
        .as-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary);
          text-transform: uppercase; letter-spacing: 0.04em; }
        .as-input { background: var(--surface-2); border: 1px solid var(--border);
          border-radius: var(--radius-sm); padding: 11px 14px; font-size: 14px; color: var(--text); font-family: var(--font-ui); }
        .as-btn { margin-top: 8px; background: var(--accent); color: #fff; border: none;
          border-radius: 980px; padding: 12px; font-weight: 650; cursor: pointer;
          box-shadow: 0 4px 14px color-mix(in srgb, var(--accent) 28%, transparent); }
        .as-btn:disabled { opacity: 0.6; box-shadow: none; }
        .as-muted { color: var(--text-secondary); font-size: 14px; }
        .as-ok { color: var(--accent); font-size: 14px; }
        .as-err { color: var(--short); font-size: 14px; }
        .as-link { display: inline-block; margin-top: 12px; color: var(--accent);
          font-weight: 600; font-size: 14px; }
      `})]})}export{P as ResetPasswordPage,z as VerifyEmailPage};
