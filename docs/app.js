/* ============================================================
   docs/app.js
   탐색형 정적 대시보드 — 통합검색·필터·AI 에이전트 검색·카드/테이블 전환·상세 모달
   data/mock_dashboard.json 을 fetch 해서 클라이언트에서 모두 처리한다.
   외부 API 호출 없음. rule-based intent 해석.
============================================================ */
"use strict";

const SOURCE_LABEL = { auction: "경매", public_sale: "공매" };
const RISK_LABEL = { low: "낮음", medium: "보통", high: "높음" };

const QUICK_CHIPS = [
  { id: "all",      label: "전체" },
  { id: "auction",  label: "경매" },
  { id: "public",   label: "공매" },
  { id: "apt",      label: "아파트" },
  { id: "officetel",label: "오피스텔" },
  { id: "villa",    label: "빌라" },
  { id: "shop",     label: "상가" },
  { id: "land",     label: "토지" },
  { id: "high_rec", label: "고수익 후보" },
  { id: "low_risk", label: "저위험 후보" },
  { id: "imminent", label: "입찰임박" },
  { id: "high_risk",label: "고위험 주의" },
];

const AGENT_EXAMPLES = [
  "시세차익 큰 물건 5개 찾아줘",
  "서울 아파트 중 위험 낮은 물건 보여줘",
  "입찰기일 7일 이내 후보 보여줘",
  "고위험이어도 수익 큰 물건 따로 보여줘",
  "오늘 뭐부터 봐야 돼?",
];

// ── 글로벌 상태 ──────────────────────────────────────
const STATE = {
  data: null,
  items: [],
  filtered: [],
  view: "card",          // card | table
  filters: {
    q: "",
    chip: "all",
    region: "",
    item_type: "",
    source: "",
    price_min: null,
    price_max: null,
    fail_min: null,
    due_max: null,
    risk: "",
    grade: "",
    sort: "score_desc",
  },
};

// ── 유틸 ──────────────────────────────────────────────
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
function clearChildren(node) { while (node.firstChild) node.removeChild(node.firstChild); }

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

// ── Quick chips ─────────────────────────────────────
function renderQuickChips() {
  const root = $("quick-chips");
  clearChildren(root);
  QUICK_CHIPS.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "chip" + (STATE.filters.chip === c.id ? " active" : "");
    btn.type = "button";
    btn.dataset.chip = c.id;
    btn.textContent = c.label;
    btn.addEventListener("click", () => {
      STATE.filters.chip = c.id;
      renderQuickChips();
      applyFilters();
    });
    root.appendChild(btn);
  });
}

// ── Filter dropdowns ───────────────────────────────
function populateFilterOptions() {
  const regions = Array.from(new Set(STATE.items.map((it) => it.region).filter(Boolean))).sort();
  const types   = Array.from(new Set(STATE.items.map((it) => it.item_type).filter(Boolean))).sort();
  const regSel = $("f-region");
  const typSel = $("f-type");
  regions.forEach((r) => regSel.appendChild(el(`<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`)));
  types.forEach((t) => typSel.appendChild(el(`<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)));
}

function bindFilterEvents() {
  const map = {
    "f-region":    (v) => STATE.filters.region = v,
    "f-type":      (v) => STATE.filters.item_type = v,
    "f-source":    (v) => STATE.filters.source = v,
    "f-price-min": (v) => STATE.filters.price_min = v ? Number(v) : null,
    "f-price-max": (v) => STATE.filters.price_max = v ? Number(v) : null,
    "f-fail":      (v) => STATE.filters.fail_min = v ? Number(v) : null,
    "f-due":       (v) => STATE.filters.due_max  = v ? Number(v) : null,
    "f-risk":      (v) => STATE.filters.risk = v,
    "f-grade":     (v) => STATE.filters.grade = v,
    "f-sort":      (v) => STATE.filters.sort = v || "score_desc",
  };
  Object.entries(map).forEach(([id, setter]) => {
    const node = $(id);
    if (!node) return;
    const evt = node.tagName === "SELECT" ? "change" : "input";
    node.addEventListener(evt, () => {
      setter(node.value);
      applyFilters();
    });
  });
  $("f-reset").addEventListener("click", resetFilters);
  $("filter-toggle").addEventListener("click", () => {
    const body = $("filter-body");
    const hidden = body.hasAttribute("hidden");
    if (hidden) {
      body.removeAttribute("hidden");
      $("filter-toggle").textContent = "접기";
      $("filter-toggle").setAttribute("aria-expanded", "true");
    } else {
      body.setAttribute("hidden", "");
      $("filter-toggle").textContent = "펼치기";
      $("filter-toggle").setAttribute("aria-expanded", "false");
    }
  });
}

function resetFilters() {
  STATE.filters = {
    q: "", chip: "all", region: "", item_type: "", source: "",
    price_min: null, price_max: null, fail_min: null, due_max: null,
    risk: "", grade: "", sort: "score_desc",
  };
  $("q-input").value = "";
  ["f-region","f-type","f-source","f-fail","f-due","f-risk","f-grade"].forEach((id) => { $(id).value = ""; });
  $("f-price-min").value = "";
  $("f-price-max").value = "";
  $("f-sort").value = "score_desc";
  renderQuickChips();
  applyFilters();
  hideAgentResult();
}

// ── Filter application ─────────────────────────────
function chipMatch(chip, it) {
  switch (chip) {
    case "all":       return true;
    case "auction":   return it.source === "auction";
    case "public":    return it.source === "public_sale";
    case "apt":       return (it.item_type || "").includes("아파트");
    case "officetel": return (it.item_type || "").includes("오피스텔");
    case "villa":     return (it.item_type || "").includes("빌라");
    case "shop":      return (it.item_type || "").includes("상가");
    case "land":      return (it.item_type || "").includes("토지");
    case "high_rec":  return (it.recommendation_score || 0) >= 70;
    case "low_risk":  return it.risk_level === "low";
    case "imminent":  return it.days_left !== null && it.days_left !== undefined
                              && it.days_left <= 7 && it.days_left >= 0;
    case "high_risk": return it.risk_level === "high";
    default: return true;
  }
}

function passQuery(q, it) {
  if (!q) return true;
  const needle = q.toLowerCase();
  return [it.title, it.address, it.region, it.item_type, it.case_no,
          it.recommendation_reason, (it.warnings || []).join(" ")]
    .some((s) => s && String(s).toLowerCase().includes(needle));
}

function applyFilters() {
  const f = STATE.filters;
  let out = STATE.items.filter((it) => chipMatch(f.chip, it) && passQuery(f.q, it));
  if (f.region)    out = out.filter((it) => it.region === f.region);
  if (f.item_type) out = out.filter((it) => it.item_type === f.item_type);
  if (f.source)    out = out.filter((it) => it.source === f.source);
  if (f.price_min !== null) out = out.filter((it) => (it.min_bid_price || 0) >= f.price_min);
  if (f.price_max !== null) out = out.filter((it) => (it.min_bid_price || 0) <= f.price_max);
  if (f.fail_min !== null)  out = out.filter((it) => (it.fail_count || 0) >= f.fail_min);
  if (f.due_max !== null)   out = out.filter((it) =>
    it.days_left !== null && it.days_left !== undefined &&
    it.days_left >= 0 && it.days_left <= f.due_max);
  if (f.risk)      out = out.filter((it) => it.risk_level === f.risk);
  if (f.grade)     out = out.filter((it) => it.recommendation_grade === f.grade);

  out = sortItems(out, f.sort);
  STATE.filtered = out;
  renderItems();
  $("items-count").textContent = `결과 ${out.length}건 / 전체 ${STATE.items.length}건`;
}

function sortItems(arr, mode) {
  const copy = arr.slice();
  const num = (v) => (v === null || v === undefined || isNaN(v)) ? -Infinity : Number(v);
  const map = {
    score_desc:  (a, b) => num(b.recommendation_score) - num(a.recommendation_score),
    profit_desc: (a, b) => num(b.expected_profit) - num(a.expected_profit),
    roi_desc:    (a, b) => num(b.expected_profit_rate) - num(a.expected_profit_rate),
    due_asc:     (a, b) => (a.days_left ?? 9999) - (b.days_left ?? 9999),
    price_asc:   (a, b) => (a.min_bid_price || 0) - (b.min_bid_price || 0),
    risk_asc:    (a, b) => ({low:0,medium:1,high:2}[a.risk_level||"medium"]) -
                            ({low:0,medium:1,high:2}[b.risk_level||"medium"]),
  };
  copy.sort(map[mode] || map.score_desc);
  return copy;
}

// ── Briefing / risk / confidence ───────────────────
function renderBriefing(b, summary) {
  const m = $("briefing-metrics");
  clearChildren(m);
  const metrics = [
    { label: "총 분석 물건", value: summary.total_items ?? "-" },
    { label: "추천 후보", value: summary.recommended_items ?? "-" },
    { label: "고위험 후보", value: summary.high_risk_items ?? "-" },
    { label: "입찰 임박(D-7)", value: summary.urgent_items ?? "-" },
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
  clearChildren(g);
  if (!recs || !recs.length) {
    g.appendChild(el(`<p class="caption">표시할 추천 결과가 없습니다.</p>`));
    return;
  }
  recs.forEach((r) => {
    const grade = r.recommendation_grade || "C";
    const risk = r.risk_level || "medium";
    const profit = r.expected_profit;
    const roi = r.expected_profit_rate;
    const next = r.next_actions && r.next_actions.length
      ? `<div class="rec-next"><b>다음 확인:</b> ${escapeHtml(r.next_actions.join(" · "))}</div>` : "";
    const reason = r.recommendation_reason
      ? `<div class="rec-reason">${escapeHtml(r.recommendation_reason)}</div>` : "";
    const card = el(
      `<article class="rec-card" data-item-id="${r.item_id || ""}">
         <div class="rec-head">
           <span class="rec-rank">#${escapeHtml(String(r.rank || ""))}</span>
           <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
           <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
           <span class="source-pill">${escapeHtml(SOURCE_LABEL[r.source] || r.source || "")}</span>
         </div>
         <div class="rec-title">${escapeHtml(r.title || r.address || "")}</div>
         <div class="rec-meta">${escapeHtml(r.address || "")} · ${escapeHtml(r.item_type || "")}</div>
         <div class="rec-stats">
           <span class="rec-stat"><strong>${fmtMan(profit)}</strong> 차익</span>
           <span class="rec-stat">ROI <strong>${fmtPct(roi)}</strong></span>
           <span class="rec-stat">최저가 ${fmtMan(r.min_bid_price)}</span>
           <span class="rec-stat">시세 ${fmtMan(r.market_price)}</span>
           <span class="rec-stat">점수 <strong>${escapeHtml(String(r.recommendation_score || "-"))}</strong></span>
         </div>
         ${reason}
         ${next}
       </article>`
    );
    if (r.item_id) {
      card.addEventListener("click", () => openDetailById(r.item_id));
    }
    g.appendChild(card);
  });
}

function renderActions(actions) {
  const g = $("action-grid");
  clearChildren(g);
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
  clearChildren(root);
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
  clearChildren(root);
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

// ── Items rendering ───────────────────────────────
function itemCardHtml(it) {
  const grade = it.recommendation_grade || "C";
  const risk = it.risk_level || "medium";
  const due = (it.days_left !== null && it.days_left !== undefined && it.days_left >= 0)
    ? `D-${it.days_left}`
    : (it.bid_date ? "기일 " + (it.bid_date.split("~")[0] || it.bid_date) : "기일 미정");
  return `
    <article class="item-card" data-item-id="${it.id}">
      <div class="item-head">
        <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
        <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
        <span class="source-pill">${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</span>
        <span class="caption">${escapeHtml(it.item_type || "")}</span>
      </div>
      <div class="item-title">${escapeHtml(it.title || "주소 미상")}</div>
      <div class="item-sub">${escapeHtml(it.address || "")} · ${escapeHtml(it.case_no || "사건번호 없음")}</div>
      <div class="item-stats">
        <span class="k">감정가</span><span class="v">${fmtMan(it.appraisal_price)}</span>
        <span class="k">최저가</span><span class="v">${fmtMan(it.min_bid_price)}</span>
        <span class="k">예상시세</span><span class="v">${fmtMan(it.market_price)}</span>
        <span class="k">예상차익</span><span class="v">${fmtMan(it.expected_profit)}</span>
        <span class="k">예상수익률</span><span class="v">${fmtPct(it.expected_profit_rate)}</span>
        <span class="k">추천점수</span><span class="v">${escapeHtml(String(it.recommendation_score ?? "-"))}</span>
      </div>
      ${it.recommendation_reason ? `<div class="item-reason">${escapeHtml(it.recommendation_reason)}</div>` : ""}
      <div class="item-foot">
        <span>${escapeHtml(due)}</span>
        <span>· 유찰 ${escapeHtml(String(it.fail_count ?? 0))}회</span>
        <span>· 신뢰도 ${escapeHtml(String((it.confidence_score || 0).toFixed(2)))}</span>
      </div>
    </article>`;
}

function renderItems() {
  const cardRoot = $("items-card-view");
  const tableBody = $("items-table").querySelector("tbody");
  clearChildren(cardRoot);
  clearChildren(tableBody);

  const list = STATE.filtered;
  if (!list.length) {
    cardRoot.appendChild(el(`<p class="caption">조건에 맞는 물건이 없습니다.</p>`));
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="13" class="caption">조건에 맞는 물건이 없습니다.</td>`;
    tableBody.appendChild(tr);
    return;
  }
  list.forEach((it, idx) => {
    const card = el(itemCardHtml(it));
    card.addEventListener("click", () => openDetailById(it.id));
    cardRoot.appendChild(card);

    const tr = document.createElement("tr");
    tr.dataset.itemId = it.id;
    const grade = it.recommendation_grade || "C";
    const risk = it.risk_level || "medium";
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</td>
      <td><span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span></td>
      <td>${escapeHtml(it.address || "")}</td>
      <td>${escapeHtml(it.item_type || "")}</td>
      <td class="num">${(it.appraisal_price || 0).toLocaleString("ko-KR")}</td>
      <td class="num">${(it.min_bid_price || 0).toLocaleString("ko-KR")}</td>
      <td class="num">${(it.market_price || 0).toLocaleString("ko-KR")}</td>
      <td class="num">${(it.expected_profit || 0).toLocaleString("ko-KR")}</td>
      <td class="num">${fmtPct(it.expected_profit_rate)}</td>
      <td class="num">${it.fail_count !== undefined ? it.fail_count : "-"}</td>
      <td>${escapeHtml(it.bid_date || "-")}</td>
      <td><span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span></td>
    `;
    tr.addEventListener("click", () => openDetailById(it.id));
    tableBody.appendChild(tr);
  });
}

function bindViewToggle() {
  document.querySelectorAll(".view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const v = btn.dataset.view;
      STATE.view = v;
      document.querySelectorAll(".view-btn").forEach((b) => {
        const active = b.dataset.view === v;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
      $("items-card-view").hidden = (v !== "card");
      $("items-table-view").hidden = (v !== "table");
    });
  });
}

// ── Agents ───────────────────────────────────────
function renderAgents(agents) {
  const g = $("agent-grid");
  clearChildren(g);
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

// ── Detail modal ─────────────────────────────────
function openDetailById(id) {
  const it = STATE.items.find((x) => String(x.id) === String(id));
  if (!it) return;
  $("detail-title").textContent = it.title || "물건 상세";
  const body = $("detail-body");
  const grade = it.recommendation_grade || "C";
  const risk = it.risk_level || "medium";
  const flags = (it.risk_flags || []).map((f) => f.keyword || f.flag_type || "키워드");
  const flagList = flags.length
    ? `<ul>${flags.map((k) => `<li>${escapeHtml(k)}</li>`).join("")}</ul>`
    : `<p class="caption">검출된 위험 키워드 없음</p>`;
  const checklist = (it.checklist || []).length
    ? `<ul>${it.checklist.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`
    : `<p class="caption">추가 확인사항 없음</p>`;
  const next = (it.next_actions || []).length
    ? `<ul>${it.next_actions.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`
    : `<p class="caption">다음 액션 미지정</p>`;
  const expectedBidLow = Math.round((it.min_bid_price || 0) * 1.02);
  const expectedBidMid = Math.round((it.min_bid_price || 0) * 1.10);
  const expectedBidHi  = Math.round((it.min_bid_price || 0) * 1.18);
  const aiVerdict = (() => {
    const score = it.recommendation_score || 0;
    if (grade === "A") return "데이터 기준 검토 가치 높음 — 단, 등기부등본/현장조사 필수";
    if (grade === "B") return "조건 충족 양호 — 위험 키워드 보완 후 재평가 권장";
    if (grade === "C") return "보통 — 시세차익 또는 위험 항목 중 하나는 보완 필요";
    if (grade === "D") return "검토 보류 권장 — 점수 낮음";
    return `점수 ${score} — 수익 대비 위험 큼, 추가 확인 필수`;
  })();

  body.innerHTML = `
    <div class="detail-grid">
      <span class="k">구분</span><span class="v">${escapeHtml(SOURCE_LABEL[it.source] || it.source || "-")}</span>
      <span class="k">사건번호</span><span class="v">${escapeHtml(it.case_no || "-")}</span>
      <span class="k">주소</span><span class="v">${escapeHtml(it.address || "-")}</span>
      <span class="k">물건종류</span><span class="v">${escapeHtml(it.item_type || "-")}</span>
      <span class="k">감정가</span><span class="v">${fmtMan(it.appraisal_price)}</span>
      <span class="k">최저가</span><span class="v">${fmtMan(it.min_bid_price)}</span>
      <span class="k">예상시세</span><span class="v">${fmtMan(it.market_price)}</span>
      <span class="k">유찰</span><span class="v">${escapeHtml(String(it.fail_count ?? 0))}회</span>
      <span class="k">입찰기일</span><span class="v">${escapeHtml(it.bid_date || "미정")}</span>
      <span class="k">위험도</span><span class="v"><span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span></span>
      <span class="k">추천등급</span><span class="v"><span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span> · 점수 ${escapeHtml(String(it.recommendation_score ?? "-"))}</span>
      <span class="k">신뢰도</span><span class="v">${escapeHtml(String((it.confidence_score || 0).toFixed(2)))}</span>
    </div>

    <div class="detail-section">
      <h3>시세 분석</h3>
      <p>${escapeHtml(it.detail_summary || "-")}</p>
    </div>

    <div class="detail-section">
      <h3>예상 입찰가</h3>
      <ul>
        <li>보수: ${fmtMan(expectedBidLow)} (최저가 +2%)</li>
        <li>기준: ${fmtMan(expectedBidMid)} (최저가 +10%)</li>
        <li>공격: ${fmtMan(expectedBidHi)} (최저가 +18%)</li>
      </ul>
      <p class="caption">예상 입찰가는 mock 데이터 기반 단순 추정치입니다.</p>
    </div>

    <div class="detail-section">
      <h3>위험 분석</h3>
      ${flagList}
    </div>

    <div class="detail-section">
      <h3>추가 확인사항</h3>
      ${checklist}
    </div>

    <div class="detail-section">
      <h3>현장조사 / 다음 액션</h3>
      ${next}
    </div>

    <div class="detail-section">
      <h3>AI 추천 이유</h3>
      <p>${escapeHtml(it.recommendation_reason || "-")}</p>
      <p class="caption"><b>AI 한줄 판단:</b> ${escapeHtml(aiVerdict)}</p>
    </div>

    <p class="caption" style="margin-top:14px">
      ※ 본 분석은 mock 데이터를 기반으로 한 참고용 정보입니다. 법률·투자 판단을 단정하지 않으며,
      실제 입찰 전 등기부등본·전입세대열람·현장조사·전문가 자문이 필요합니다.
    </p>
  `;
  $("detail-modal").hidden = false;
  document.body.style.overflow = "hidden";
}

function bindModalClose() {
  const close = () => {
    $("detail-modal").hidden = true;
    document.body.style.overflow = "";
  };
  $("detail-close").addEventListener("click", close);
  $("detail-modal").addEventListener("click", (e) => {
    if (e.target instanceof HTMLElement && e.target.dataset.close === "1") close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("detail-modal").hidden) close();
  });
}

// ── Search bar ───────────────────────────────────
function bindSearch() {
  const input = $("q-input");
  const submit = () => {
    STATE.filters.q = input.value.trim();
    applyFilters();
  };
  $("q-submit").addEventListener("click", submit);
  $("q-reset").addEventListener("click", resetFilters);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
  // 가벼운 디바운스 - 입력 중에도 즉시 결과 갱신
  let t;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(submit, 200);
  });
}

// ── AI agent (rule-based intent) ─────────────────
function parseIntent(text) {
  const q = (text || "").toLowerCase();
  const intent = { sort: null, filters: {}, limit: null, note: [] };

  // 지역
  const regionPatterns = ["서울", "경기", "인천", "부산", "대전", "대구", "광주", "울산", "세종", "강원"];
  for (const r of regionPatterns) {
    if (q.includes(r)) {
      intent.filters.regionContains = r;
      intent.note.push(`지역: ${r}`);
      break;
    }
  }
  // 물건종류
  const typePatterns = ["아파트", "오피스텔", "빌라", "상가", "토지"];
  for (const t of typePatterns) {
    if (q.includes(t)) {
      intent.filters.item_type = t;
      intent.note.push(`종류: ${t}`);
      break;
    }
  }
  // 경매/공매
  if (q.includes("공매")) { intent.filters.source = "public_sale"; intent.note.push("공매"); }
  else if (q.includes("경매")) { intent.filters.source = "auction"; intent.note.push("경매"); }

  // 위험
  if (q.includes("위험 낮은") || q.includes("저위험") || q.includes("안전")) {
    intent.filters.risk = "low"; intent.note.push("저위험");
  } else if (q.includes("고위험") || q.includes("위험 높은")) {
    intent.filters.risk = "high"; intent.note.push("고위험");
  }

  // 입찰기일
  const dueMatch = q.match(/(\d+)\s*일\s*이내/);
  if (dueMatch) {
    intent.filters.due_max = Number(dueMatch[1]);
    intent.note.push(`${dueMatch[1]}일 이내`);
  } else if (q.includes("임박")) {
    intent.filters.due_max = 7; intent.note.push("입찰임박");
  }

  // 정렬
  if (q.includes("수익률")) { intent.sort = "roi_desc"; intent.note.push("수익률 높은순"); }
  else if (q.includes("차익") || q.includes("수익")) { intent.sort = "profit_desc"; intent.note.push("차익 큰순"); }
  else if (q.includes("점수") || q.includes("추천")) { intent.sort = "score_desc"; intent.note.push("추천점수 순"); }
  else if (q.includes("저렴") || q.includes("싼") || q.includes("저가")) { intent.sort = "price_asc"; intent.note.push("최저가 낮은순"); }

  // 개수
  const cntMatch = q.match(/(\d+)\s*(개|건)/);
  if (cntMatch) {
    intent.limit = Math.max(1, Math.min(50, Number(cntMatch[1])));
    intent.note.push(`상위 ${intent.limit}개`);
  }

  // 오늘 뭐부터 등 모호한 입력 → 추천점수 정렬 + top5
  if (!intent.sort && (q.includes("뭐부터") || q.includes("오늘") || q.includes("괜찮") || !q)) {
    intent.sort = "score_desc";
    if (!intent.limit) intent.limit = 5;
    intent.note.push("오늘 우선 후보");
  }

  return intent;
}

function runAgentSearch(text) {
  const intent = parseIntent(text);
  let arr = STATE.items.slice();
  const f = intent.filters;
  if (f.regionContains) arr = arr.filter((it) => (it.region || "").includes(f.regionContains));
  if (f.item_type) arr = arr.filter((it) => (it.item_type || "").includes(f.item_type));
  if (f.source) arr = arr.filter((it) => it.source === f.source);
  if (f.risk) arr = arr.filter((it) => it.risk_level === f.risk);
  if (f.due_max !== undefined) arr = arr.filter((it) =>
    it.days_left !== null && it.days_left !== undefined &&
    it.days_left >= 0 && it.days_left <= f.due_max);

  arr = sortItems(arr, intent.sort || "score_desc");
  const limit = intent.limit || 10;
  const result = arr.slice(0, limit);

  const root = $("agent-result");
  root.classList.add("show");
  root.innerHTML = `
    <h3>AI 결과 — ${escapeHtml(intent.note.join(" · ") || "기본 정렬")} (${result.length}건)</h3>
    <p class="caption">자연어를 rule-based 로 해석해 현재 mock 데이터를 다시 정렬·필터한 결과입니다.</p>
    <div class="agent-result-grid"></div>
  `;
  const grid = root.querySelector(".agent-result-grid");
  if (!result.length) {
    grid.appendChild(el(`<p class="caption">조건에 맞는 물건이 없습니다.</p>`));
    return;
  }
  result.forEach((it) => {
    const card = el(itemCardHtml(it));
    card.addEventListener("click", () => openDetailById(it.id));
    grid.appendChild(card);
  });
}

function hideAgentResult() {
  const root = $("agent-result");
  root.classList.remove("show");
  root.innerHTML = "";
}

function bindAgentSearch() {
  const input = $("agent-q");
  const root = $("agent-examples");
  AGENT_EXAMPLES.forEach((ex) => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.textContent = ex;
    chip.addEventListener("click", () => {
      input.value = ex;
      runAgentSearch(ex);
    });
    root.appendChild(chip);
  });
  $("agent-go").addEventListener("click", () => runAgentSearch(input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runAgentSearch(input.value);
  });
}

// ── Error / loader ────────────────────────────────
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
  STATE.data = data;
  STATE.items = Array.isArray(data.items) ? data.items.slice() : [];
  STATE.filtered = STATE.items.slice();

  const summary = data.summary || {};
  renderGeneratedAt(data.generated_at);
  renderBriefing(data.briefing || {}, summary);
  renderRecs(data.recommendations);
  renderActions(data.action_items);
  renderRiskSummary(data.risk_summary);
  renderConfidence(data.confidence_summary, summary);

  populateFilterOptions();
  renderQuickChips();
  applyFilters();

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

document.addEventListener("DOMContentLoaded", () => {
  bindFilterEvents();
  bindSearch();
  bindAgentSearch();
  bindViewToggle();
  bindModalClose();
  load();
});
