/* ============================================================
   docs/app.js
   data/mock_dashboard.json 을 fetch 해서 화면에 렌더링.
   GitHub Pages / 로컬 file:// 모두에서 동작하도록 fetch 실패 시 안내.
============================================================ */
"use strict";

const SOURCE_LABEL = { auction: "경매", public_sale: "공매" };
const RISK_LABEL = { low: "낮음", medium: "보통", high: "높음" };

function $(id) { return document.getElementById(id); }
function fmtMan(n) {
  if (n === null || n === undefined || isNaN(n)) return "-";
  return Number(n).toLocaleString("ko-KR") + "만원";
}
function fmtPct(n, digits) {
  if (n === null || n === undefined || isNaN(n)) return "-";
  return Number(n).toFixed(digits === undefined ? 1 : digits) + "%";
}
function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstChild;
}

function renderGeneratedAt(iso) {
  if (!iso) return;
  const d = new Date(iso);
  if (isNaN(d.getTime())) {
    $("generated-at").textContent = `생성: ${iso}`;
    return;
  }
  const pad = (x) => String(x).padStart(2, "0");
  const txt = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
              `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  $("generated-at").textContent = `데이터 기준 ${txt}`;
}

function renderBriefing(b, summary) {
  const m = $("briefing-metrics");
  m.innerHTML = "";
  const metrics = [
    { label: "총 분석 물건", value: summary.total_items },
    { label: "분석 완료", value: summary.analyzed_items },
    { label: "추천 후보", value: summary.recommended_items },
    { label: "고위험 후보", value: summary.high_risk_items },
  ];
  metrics.forEach((mt) => {
    m.appendChild(el(
      `<div class="metric">
         <div class="label">${escapeHtml(mt.label)}</div>
         <div class="value">${escapeHtml(String(mt.value))}</div>
       </div>`
    ));
  });
  $("briefing-summary").textContent = b && b.summary ? b.summary : "";
}

function renderRecs(recs) {
  const g = $("rec-grid");
  g.innerHTML = "";
  if (!recs || !recs.length) {
    g.appendChild(el(`<p class="caption">표시할 추천 결과가 없습니다.</p>`));
    return;
  }
  recs.forEach((r) => {
    const grade = r.recommendation_grade || r.grade || "C";
    const risk = r.risk_level || "medium";
    const profit = r.expected_profit !== undefined ? r.expected_profit : r.profit_estimate;
    const roi = r.expected_profit_rate !== undefined ? r.expected_profit_rate : r.roi_estimate;
    const next = r.next_actions && r.next_actions.length
      ? `<div class="rec-next"><b>다음 확인:</b> ${escapeHtml(r.next_actions.join(" · "))}</div>` : "";
    const reason = r.recommendation_reason
      ? `<div class="rec-reason">${escapeHtml(r.recommendation_reason)}</div>` : "";
    g.appendChild(el(
      `<article class="rec-card">
         <div class="rec-head">
           <span class="rec-rank">#${escapeHtml(String(r.rank || ""))}</span>
           <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
           <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
           <span class="badge" style="background:#eef2f7;color:#2c3e50">
             ${escapeHtml(SOURCE_LABEL[r.source] || r.source || "")}
           </span>
         </div>
         <div class="rec-title">${escapeHtml(r.title || r.address || "")}</div>
         <div class="rec-meta">${escapeHtml(r.address || "")} · ${escapeHtml(r.item_type || "")}</div>
         <div class="rec-stats">
           <span class="rec-stat"><strong>${fmtMan(profit)}</strong> 차익</span>
           <span class="rec-stat">ROI <strong>${fmtPct(roi)}</strong></span>
           <span class="rec-stat">최저가 ${fmtMan(r.min_bid_price || r.minimum_price)}</span>
           <span class="rec-stat">시세 ${fmtMan(r.market_price)}</span>
           <span class="rec-stat">점수 <strong>${escapeHtml(String(r.recommendation_score || r.score || "-"))}</strong></span>
         </div>
         ${reason}
         ${next}
       </article>`
    ));
  });
}

function renderActions(actions) {
  const g = $("action-grid");
  g.innerHTML = "";
  if (!actions || !actions.length) {
    g.appendChild(el(`<p class="caption">오늘 등록된 액션이 없습니다.</p>`));
    return;
  }
  actions.forEach((a) => {
    const p = (a.priority || "medium").toLowerCase();
    g.appendChild(el(
      `<div class="action-card">
         <div class="priority ${escapeHtml(p)}">${escapeHtml(p)}</div>
         <div class="title">${escapeHtml(a.title || "")}</div>
         <div class="detail">${escapeHtml(a.detail || "")}</div>
         <div class="caption">${escapeHtml(a.address || a.target || "")}</div>
       </div>`
    ));
  });
}

function renderRiskSummary(rs) {
  const root = $("risk-summary");
  root.innerHTML = "";
  if (!rs) {
    root.appendChild(el(`<p class="caption">위험 통계가 없습니다.</p>`));
    return;
  }
  const total = (rs.low || 0) + (rs.medium || 0) + (rs.high || 0);
  const pct = (n) => total ? (n / total * 100).toFixed(1) + "%" : "0%";
  root.appendChild(el(
    `<div class="risk-bar" aria-label="위험 분포">
       <span class="low" style="flex:${rs.low || 0}"></span>
       <span class="medium" style="flex:${rs.medium || 0}"></span>
       <span class="high" style="flex:${rs.high || 0}"></span>
     </div>
     <div class="risk-counts">
       <span><span class="dot low"></span>낮음 ${rs.low || 0}건 (${pct(rs.low || 0)})</span>
       <span><span class="dot medium"></span>보통 ${rs.medium || 0}건 (${pct(rs.medium || 0)})</span>
       <span><span class="dot high"></span>높음 ${rs.high || 0}건 (${pct(rs.high || 0)})</span>
     </div>`
  ));
  if (rs.top_flags && rs.top_flags.length) {
    const ul = document.createElement("ul");
    ul.className = "flag-list";
    rs.top_flags.forEach((f) => {
      const li = document.createElement("li");
      li.textContent = `${f.keyword || f.flag_type || "키워드"} (${f.count || 0})`;
      ul.appendChild(li);
    });
    root.appendChild(ul);
  }
}

function renderConfidence(c, summary) {
  const root = $("confidence-summary");
  root.innerHTML = "";
  const overall = (summary && summary.avg_confidence !== undefined)
    ? summary.avg_confidence : (c && c.overall);
  const bars = [
    ["시세 신뢰도", c && c.price],
    ["권리위험 신뢰도", c && c.risk],
    ["문서 완성도", c && c.document],
    ["주소 매칭", c && c.address],
    ["전체 신뢰도", overall],
  ];
  bars.forEach(([label, v]) => {
    const pct = v === undefined || v === null ? 0 : Math.max(0, Math.min(100, v * 100));
    root.appendChild(el(
      `<div class="conf-row">
         <div class="conf-label">${escapeHtml(label)}</div>
         <div class="conf-bar"><div class="conf-fill" style="width:${pct.toFixed(1)}%"></div></div>
         <div class="conf-pct">${pct.toFixed(0)}%</div>
       </div>`
    ));
  });
  if (c && c.note) {
    root.appendChild(el(`<p class="caption" style="margin-top:8px">${escapeHtml(c.note)}</p>`));
  }
}

function renderItems(items) {
  const tbody = $("items-table").querySelector("tbody");
  tbody.innerHTML = "";
  if (!items || !items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="9" class="caption">표시할 물건이 없습니다.</td>`;
    tbody.appendChild(tr);
    return;
  }
  items.forEach((it, i) => {
    const tr = document.createElement("tr");
    const risk = it.risk_level || "medium";
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</td>
      <td>${escapeHtml(it.address || "")}</td>
      <td>${escapeHtml(it.item_type || "")}</td>
      <td class="num">${(it.appraisal_price || 0).toLocaleString("ko-KR")}</td>
      <td class="num">${(it.min_bid_price || 0).toLocaleString("ko-KR")}</td>
      <td class="num">${it.fail_count !== undefined ? it.fail_count : "-"}</td>
      <td>${escapeHtml(it.bid_date || "-")}</td>
      <td><span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAgents(agents) {
  const g = $("agent-grid");
  g.innerHTML = "";
  if (!agents || !agents.length) {
    g.appendChild(el(`<p class="caption">에이전트 정보가 없습니다.</p>`));
    return;
  }
  agents.forEach((a) => {
    const status = (a.status || "ok").toLowerCase();
    g.appendChild(el(
      `<div class="agent-row">
         <span class="agent-name">${escapeHtml(a.name)}</span>
         <span class="agent-status ${escapeHtml(status)}">${escapeHtml(a.status || "OK")}</span>
       </div>`
    ));
  });
}

function showError(msg) {
  const main = document.querySelector("main.container");
  main.innerHTML = `
    <section class="card">
      <h2>데이터 로드 실패</h2>
      <p class="caption">${escapeHtml(msg)}</p>
      <p class="caption">
        파일 시스템(file://)에서 직접 열면 브라우저가 fetch 를 차단할 수 있습니다.
        다음 중 하나로 실행해 주세요:<br>
        - 로컬: <code>python -m http.server 8000 -d docs</code> 후
        <a href="http://localhost:8000">http://localhost:8000</a><br>
        - GitHub Pages 배포 후 <a href="https://1976haru.github.io/auction/">https://1976haru.github.io/auction/</a>
      </p>
    </section>`;
}

function render(data) {
  if (!data || typeof data !== "object") {
    showError("mock_dashboard.json 의 형식이 올바르지 않습니다.");
    return;
  }
  const summary = data.summary || {};
  renderGeneratedAt(data.generated_at);
  renderBriefing(data.briefing || {}, summary);
  renderRecs(data.recommendations);
  renderActions(data.action_items);
  renderRiskSummary(data.risk_summary);
  renderConfidence(data.confidence_summary, summary);
  renderItems(data.items);
  renderAgents(data.agent_status);
}

async function load() {
  try {
    const resp = await fetch("data/mock_dashboard.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    render(data);
  } catch (e) {
    showError(`mock_dashboard.json 을 불러오지 못했습니다: ${e && e.message ? e.message : e}`);
  }
}

document.addEventListener("DOMContentLoaded", load);
