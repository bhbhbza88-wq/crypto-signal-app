import{j as e,a as y,r as d}from"./index-DWgcX8Xm.js";import{p as v,r as m,f as k,e as N,T as w}from"./shared-BfpJX4w4.js";import{g as T,B as f,X as u,Y as p,f as C,R as j,L as S,a as $,T as L,C as F}from"./LineChart-Dzfk13GY.js";var q=T({chartName:"BarChart",GraphicalChild:f,defaultTooltipEventType:"axis",validateTooltipEventTypes:["axis","item"],axisComponents:[{axisType:"xAxis",AxisComp:u},{axisType:"yAxis",AxisComp:p}],formatAxisMap:C});function A({winrate:r=0,total:l=0,size:s=132,label:n="winrate"}){const t=(s-10)/2,i=2*Math.PI*t,o=i-r/100*i,h=l===0?"var(--text-tertiary)":r>=50?"var(--long)":"var(--short)";return e.jsxs("div",{className:"ring-wrap",style:{width:s,height:s},children:[e.jsxs("svg",{width:s,height:s,viewBox:`0 0 ${s} ${s}`,children:[e.jsx("circle",{cx:s/2,cy:s/2,r:t,fill:"none",stroke:"var(--border)",strokeWidth:10}),l>0&&e.jsx("circle",{cx:s/2,cy:s/2,r:t,fill:"none",stroke:h,strokeWidth:10,strokeDasharray:i,strokeDashoffset:o,strokeLinecap:"round",transform:`rotate(-90 ${s/2} ${s/2})`,style:{transition:"stroke-dashoffset 0.6s ease"}})]}),e.jsxs("div",{className:"ring-center",children:[e.jsx("span",{className:"ring-value",children:l>0?`${r}%`:"—"}),e.jsx("span",{className:"ring-label",children:n})]}),e.jsx("style",{children:`
        .ring-wrap { position: relative; flex-shrink: 0; }
        .ring-center {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 2px;
        }
        .ring-value {
          font-family: var(--font-mono);
          font-size: 26px;
          font-weight: 600;
          color: var(--text);
        }
        .ring-label {
          font-size: 11px;
          color: var(--text-tertiary);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
      `})]})}function M({history:r,t:l}){const s=d.useMemo(()=>{const t={};return r.forEach(i=>{const o=i.date||"—";t[o]||(t[o]={date:o,pnl:0,count:0}),t[o].pnl+=parseFloat(i.pnl||0),t[o].count+=1}),Object.values(t).slice(-30)},[r]);if(s.length===0)return null;const n=s.reduce((t,i)=>t+i.pnl,0),a=n>=0;return e.jsxs("section",{className:"hist-sec",children:[e.jsxs("div",{className:"dash-sec-head",children:[e.jsx("h2",{className:"dash-sec-title mono",children:l("hist.chart.title")}),e.jsx("span",{className:"hist-sec-meta mono",children:l("hist.chart.sub",{n:s.length})}),e.jsxs("span",{className:`hist-chart-total mono ${a?"pos":"neg"}`,children:[a?"+":"",n.toFixed(1),"%"]})]}),e.jsx("div",{className:"rs-card hist-chart-card",children:e.jsx("div",{className:"hist-chart-inner",children:e.jsx(j,{width:"100%",height:"100%",children:e.jsxs(q,{data:s,margin:{top:8,right:8,bottom:0,left:0},barSize:s.length>20?8:14,children:[e.jsx(u,{dataKey:"date",tick:{fill:"var(--text-tertiary)",fontSize:10,fontFamily:"var(--font-mono)"},axisLine:!1,tickLine:!1,tickFormatter:t=>String(t).slice(5),interval:"preserveStartEnd",minTickGap:28}),e.jsx(p,{hide:!0}),e.jsx(L,{contentStyle:{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:10,fontFamily:"var(--font-mono)",fontSize:12},formatter:t=>[`${t>0?"+":""}${Number(t).toFixed(2)}%`,l("hist.chart.tooltipPnl")],labelFormatter:t=>t}),e.jsx(f,{dataKey:"pnl",radius:[3,3,0,0],children:s.map((t,i)=>e.jsx(F,{fill:t.pnl>=0?"var(--long)":"var(--short)",opacity:.85},i))})]})})})})]})}function b({history:r,stats:l,t:s}){var h;const n=d.useMemo(()=>v(r),[r]),a=d.useMemo(()=>k(l,n),[l,n]),t=d.useMemo(()=>N(r),[r]),i=n.filter(c=>c.pnl>0).length,o=n.reduce((c,x)=>!c||x.pnl>c.pnl?x:c,null);return e.jsxs("div",{className:"hist-overview",children:[e.jsxs("div",{className:"hist-overview-top",children:[e.jsxs("div",{className:"hist-overview-copy",children:[e.jsx("p",{className:"hist-overview-sub",children:s("hist.period.sub")}),e.jsx("a",{className:"hist-channel-link mono",href:w,target:"_blank",rel:"noopener noreferrer",children:s("hist.channel.link")})]}),e.jsx(A,{winrate:a.winrate,total:a.total,label:s("land.hero.statWinrate")})]}),e.jsxs("div",{className:"kpi-grid hist-kpi-grid",children:[e.jsxs("div",{className:"kpi-card accent",children:[e.jsx("div",{className:"kpi-key mono",children:"trades"}),e.jsx("div",{className:"kpi-val",children:a.total}),e.jsxs("div",{className:"kpi-meta",children:[e.jsx("span",{className:"kpi-label",children:s("hist.kpi.trades")}),e.jsx("span",{className:"kpi-sub",children:s("hist.kpi.wins",{n:i})})]})]}),e.jsxs("div",{className:"kpi-card",children:[e.jsx("div",{className:"kpi-key mono",children:"avg_pnl"}),e.jsxs("div",{className:"kpi-val pos",children:["+",a.avgPnl,"%"]}),e.jsxs("div",{className:"kpi-meta",children:[e.jsx("span",{className:"kpi-label",children:s("hist.kpi.avg")}),e.jsx("span",{className:"kpi-sub",children:s("hist.kpi.perTrade")})]})]}),e.jsxs("div",{className:"kpi-card",children:[e.jsx("div",{className:"kpi-key mono",children:"sum_pnl"}),e.jsxs("div",{className:`kpi-val ${a.totalPnl>=0?"pos":"neg"}`,children:[a.totalPnl>=0?"+":"",a.totalPnl,"%"]}),e.jsxs("div",{className:"kpi-meta",children:[e.jsx("span",{className:"kpi-label",children:s("hist.kpi.sum")}),e.jsx("span",{className:"kpi-sub",children:s("hist.kpi.monthSum")})]})]}),e.jsxs("div",{className:"kpi-card",children:[e.jsx("div",{className:"kpi-key mono",children:"best"}),e.jsx("div",{className:"kpi-val pos",children:o?`+${o.pnl}%`:"—"}),e.jsxs("div",{className:"kpi-meta",children:[e.jsx("span",{className:"kpi-label",children:s("hist.kpi.best")}),e.jsx("span",{className:"kpi-sub",children:o?String(o.symbol||"").replace("/USDT",""):s("hist.kpi.noBest")})]})]})]}),t.length>1&&e.jsxs("div",{className:"rs-card hist-equity",children:[e.jsxs("div",{className:"rs-chrome",children:[e.jsx("span",{className:"rs-prompt mono",children:s("hist.equity.title")}),e.jsx("strong",{className:"mono pos",children:((h=t[t.length-1])==null?void 0:h.equity)!=null?`+${t[t.length-1].equity}%`:"—"})]}),e.jsx("div",{className:"hist-equity-chart",children:e.jsx(j,{width:"100%",height:"100%",children:e.jsxs(S,{data:t,children:[e.jsx(p,{hide:!0,domain:["auto","auto"]}),e.jsx($,{type:"monotone",dataKey:"equity",stroke:"var(--accent)",strokeWidth:2.2,dot:!1})]})})})]})]})}function E({history:r,stats:l,onUpgrade:s,t:n}){return e.jsxs("div",{className:"history-wrap",children:[e.jsx(b,{history:r,stats:l,t:n}),e.jsxs("div",{className:"rs-card hist-lock-card",children:[e.jsx("div",{className:"hist-lock-kicker mono",children:"premium"}),e.jsx("div",{className:"hist-lock-title",children:n("hist.locked.title")}),e.jsx("div",{className:"hist-lock-feats",children:[n("hist.locked.f1"),n("hist.locked.f2"),n("hist.locked.f3")].map((a,t)=>e.jsx("span",{className:"hist-lock-feat",children:a},t))}),e.jsx("button",{type:"button",className:"hist-lock-btn",onClick:s,children:n("hist.locked.btn")})]})]})}function D({history:r,stats:l=null,isPremium:s=!0,onUpgrade:n}){const{t:a}=y(),t=d.useMemo(()=>v(r),[r]);return t!=null&&t.length?s?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"history-wrap",children:[e.jsx(b,{history:r,stats:l,t:a}),e.jsx(M,{history:t,t:a}),e.jsxs("section",{className:"hist-sec",children:[e.jsxs("div",{className:"dash-sec-head",children:[e.jsx("h2",{className:"dash-sec-title mono",children:a("hist.table.title")}),e.jsx("span",{className:"sec-count mono",children:t.length})]}),e.jsxs("div",{className:"rs-card history-table-wrap",children:[e.jsxs("table",{className:"history-table",children:[e.jsx("thead",{children:e.jsxs("tr",{children:[e.jsx("th",{children:a("hist.col.date")}),e.jsx("th",{children:a("hist.col.time")}),e.jsx("th",{children:a("hist.col.coin")}),e.jsx("th",{children:a("hist.col.signal")}),e.jsx("th",{className:"num-right",children:a("hist.col.entry")}),e.jsx("th",{children:a("hist.col.result")}),e.jsxs("th",{className:"num-right",children:[a("hist.col.pnl")," · 15x"]})]})}),e.jsx("tbody",{children:t.map(i=>{var o;return e.jsxs("tr",{children:[e.jsx("td",{className:"dim",children:i.date}),e.jsx("td",{className:"mono dim",children:i.time}),e.jsx("td",{className:"mono symbol-cell",children:i.symbol.replace("/USDT","")}),e.jsx("td",{children:e.jsx("span",{className:`dir-badge ${i.signal==="LONG"?"long":"short"}`,children:i.signal})}),e.jsx("td",{className:"mono dim num-right",children:(o=i.entry)==null?void 0:o.toFixed(4)}),e.jsx("td",{children:m(a,i.result)}),e.jsxs("td",{className:`mono pnl ${i.pnl>0?"pos":i.pnl<0?"neg":""} num-right`,children:[i.pnl>0?"+":"",i.pnl,"%"]})]},i.id)})})]}),e.jsx("div",{className:"history-cards",children:t.map(i=>e.jsxs("div",{className:"history-row-card",children:[e.jsxs("div",{className:"hrc-top",children:[e.jsxs("div",{className:"hrc-symbol-group",children:[e.jsx("span",{className:"mono symbol-cell",children:i.symbol.replace("/USDT","")}),e.jsx("span",{className:`dir-badge ${i.signal==="LONG"?"long":"short"}`,children:i.signal})]}),e.jsxs("span",{className:`mono pnl ${i.pnl>0?"pos":i.pnl<0?"neg":""} num-right`,children:[i.pnl>0?"+":"",i.pnl,"%"]})]}),e.jsxs("div",{className:"hrc-bottom",children:[e.jsx("span",{className:"dim",children:m(a,i.result)}),e.jsxs("span",{className:"dim",children:[i.date," · ",i.time]})]})]},i.id))})]})]})]}),e.jsx(g,{})]}):e.jsxs(e.Fragment,{children:[e.jsx(E,{history:r,stats:l,onUpgrade:n,t:a}),e.jsx(g,{})]}):e.jsxs("div",{className:"history-empty rs-card",children:[e.jsx("span",{className:"mono",children:a("hist.empty")}),e.jsx("style",{children:`
          .history-empty {
            padding: 36px 20px; text-align: center;
            color: var(--text-tertiary); font-size: 13px;
          }
        `})]})}function g(){return e.jsx("style",{children:`
      .history-wrap { display: flex; flex-direction: column; gap: 22px; }
      .hist-overview { display: flex; flex-direction: column; gap: 16px; }
      .hist-overview-top {
        display: flex; justify-content: space-between; align-items: center;
        gap: 20px; flex-wrap: wrap;
      }
      .hist-overview-sub {
        margin: 0; font-size: 13px; line-height: 1.5;
        color: var(--text-secondary); max-width: 48ch;
      }
      .hist-channel-link {
        display: inline-block; margin-top: 10px; font-size: 12px; font-weight: 650;
        color: var(--accent); text-decoration: none;
      }
      .hist-channel-link:hover { text-decoration: underline; }

      .hist-sec { display: flex; flex-direction: column; gap: 0; }
      .hist-sec-meta { font-size: 11px; color: var(--text-tertiary); }
      .hist-chart-total { font-size: 13px; font-weight: 700; margin-left: auto; }
      .hist-chart-card { padding: 8px 10px 4px; }
      .hist-chart-inner { height: 148px; }

      .hist-equity { overflow: hidden; }
      .hist-equity .rs-chrome strong { font-size: 13px; }
      .hist-equity-chart { height: 72px; padding: 4px 10px 10px; }

      .hist-lock-card {
        padding: 28px 24px; display: flex; flex-direction: column; align-items: center;
        gap: 10px; text-align: center;
      }
      .hist-lock-kicker {
        font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
        color: var(--accent); background: var(--accent-soft);
        padding: 4px 10px; border-radius: 8px;
      }
      .hist-lock-title {
        font-size: 16px; font-weight: 700; color: var(--text);
        font-family: var(--font-display); letter-spacing: -0.02em;
      }
      .hist-lock-feats { display: flex; flex-direction: column; gap: 7px; margin: 4px 0 8px; }
      .hist-lock-feat {
        font-size: 13px; color: var(--text-secondary);
        padding: 8px 12px; border-radius: 10px;
        background: color-mix(in srgb, var(--bg) 45%, transparent);
        border: 1px solid var(--border);
      }
      .hist-lock-btn {
        background: var(--accent); color: #fff;
        border: none; border-radius: 10px; padding: 11px 24px;
        font-size: 13px; font-weight: 700; cursor: pointer;
      }
      .hist-lock-btn:hover { opacity: 0.92; }

      .history-table-wrap { overflow: hidden; }
      .history-table { width: 100%; border-collapse: collapse; border-spacing: 0; font-size: 13px; display: table; }
      .history-table th {
        text-align: left; padding: 12px 16px;
        color: var(--text-tertiary); font-size: 10px;
        text-transform: uppercase; letter-spacing: 0.05em;
        font-weight: 650; border-bottom: 1px solid var(--border); white-space: nowrap;
        background: color-mix(in srgb, var(--surface-hover) 50%, transparent);
      }
      .history-table td {
        padding: 11px 16px; border-bottom: 1px solid var(--border);
        color: var(--text); white-space: nowrap;
        vertical-align: middle;
      }
      .history-table tbody tr:last-child td { border-bottom: none; }
      .history-table th.num-right,
      .history-table td.num-right { text-align: right; }
      .history-table tbody tr:nth-child(even) td {
        background: color-mix(in srgb, var(--surface-hover) 22%, transparent);
      }
      .history-table tbody tr:hover td {
        background: color-mix(in srgb, var(--bg) 40%, transparent);
      }
      .history-table tbody tr td { transition: background 0.15s ease; }
      .mono { font-family: var(--font-mono); }
      .dim { color: var(--text-secondary); }
      .symbol-cell { font-weight: 650; color: var(--text); }
      .dir-badge {
        font-size: 11px; font-weight: 650; padding: 3px 8px; border-radius: 6px;
        font-family: var(--font-mono);
        min-width: 72px;
        text-align: center;
      }
      .dir-badge.long { background: var(--long-soft); color: var(--long); }
      .dir-badge.short { background: var(--short-soft); color: var(--short); }
      .pnl.pos, .pos { color: var(--long); }
      .pnl.neg, .neg { color: var(--short); }
      .history-cards { display: none; }

      @media (max-width: 1100px) {
        .hist-kpi-grid { grid-template-columns: repeat(2, 1fr); }
      }
      @media (max-width: 680px) {
        .history-table { display: none; }
        .history-cards { display: flex; flex-direction: column; }
        .history-row-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 14px 14px;
          margin-bottom: 10px;
        }
        .hrc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .hrc-symbol-group { display: flex; align-items: center; gap: 8px; }
        .hrc-bottom { display: flex; justify-content: space-between; font-size: 12px; }
        .hist-overview-top { flex-direction: column; align-items: flex-start; }
      }
    `})}export{D as default};
