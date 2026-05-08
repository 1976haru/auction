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
  { id: "favorites",label: "★ 내 관심" },
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

const SORT_LABEL = {
  score_desc: "추천점수 높은순",
  profit_desc: "차익 큰순",
  roi_desc: "수익률 높은순",
  due_asc: "기일 임박순",
  price_asc: "최저가 낮은순",
  risk_asc: "위험 낮은순",
};

const FAV_KEY = "auction:favorites:v1";
function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr.map(String) : []);
  } catch { return new Set(); }
}
function saveFavorites(set) {
  try { localStorage.setItem(FAV_KEY, JSON.stringify(Array.from(set))); }
  catch {}
}

// ── 글로벌 상태 ──────────────────────────────────────
const STATE = {
  data: null,
  items: [],
  filtered: [],
  view: "card",          // card | table
  favorites: loadFavorites(),
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
    flag: "",     // 위험 키워드 단일 (예: "임차인")
  },
};

const FILTER_DEFAULTS = JSON.parse(JSON.stringify(STATE.filters));
let URL_SYNC_ENABLED = false;

function urlFromState() {
  const p = new URLSearchParams();
  const f = STATE.filters;
  if (f.q) p.set("q", f.q);
  if (f.chip && f.chip !== "all") p.set("chip", f.chip);
  if (f.region) p.set("region", f.region);
  if (f.item_type) p.set("type", f.item_type);
  if (f.source) p.set("src", f.source);
  if (f.price_min !== null) p.set("pmin", String(f.price_min));
  if (f.price_max !== null) p.set("pmax", String(f.price_max));
  if (f.fail_min !== null) p.set("fail", String(f.fail_min));
  if (f.due_max !== null) p.set("due", String(f.due_max));
  if (f.risk) p.set("risk", f.risk);
  if (f.grade) p.set("grade", f.grade);
  if (f.sort && f.sort !== "score_desc") p.set("sort", f.sort);
  if (f.flag) p.set("flag", f.flag);
  if (STATE.view !== "card") p.set("view", STATE.view);
  const qs = p.toString();
  return qs ? "?" + qs : window.location.pathname;
}
function pushUrlState() {
  if (!URL_SYNC_ENABLED) return;
  const next = urlFromState();
  if (next !== (window.location.search || window.location.pathname)) {
    history.replaceState(null, "", next);
  }
}
function applyUrlToState() {
  const p = new URLSearchParams(window.location.search);
  const f = STATE.filters;
  const num = (k) => {
    const v = p.get(k);
    return v === null || v === "" ? null : Number(v);
  };
  if (p.has("q")) f.q = p.get("q") || "";
  if (p.has("chip")) f.chip = p.get("chip") || "all";
  if (p.has("region")) f.region = p.get("region") || "";
  if (p.has("type")) f.item_type = p.get("type") || "";
  if (p.has("src")) f.source = p.get("src") || "";
  if (p.has("pmin")) f.price_min = num("pmin");
  if (p.has("pmax")) f.price_max = num("pmax");
  if (p.has("fail")) f.fail_min = num("fail");
  if (p.has("due")) f.due_max = num("due");
  if (p.has("risk")) f.risk = p.get("risk") || "";
  if (p.has("grade")) f.grade = p.get("grade") || "";
  if (p.has("sort")) f.sort = p.get("sort") || "score_desc";
  if (p.has("flag")) f.flag = p.get("flag") || "";
  if (p.has("view")) STATE.view = p.get("view") === "table" ? "table" : "card";
}
function syncControlsFromState() {
  const f = STATE.filters;
  $("q-input").value = f.q || "";
  $("f-region").value = f.region || "";
  $("f-type").value = f.item_type || "";
  $("f-source").value = f.source || "";
  $("f-price-min").value = f.price_min ?? "";
  $("f-price-max").value = f.price_max ?? "";
  $("f-fail").value = f.fail_min ?? "";
  $("f-due").value = f.due_max ?? "";
  $("f-risk").value = f.risk || "";
  $("f-grade").value = f.grade || "";
  $("f-sort").value = f.sort || "score_desc";
  // 보기 토글
  document.querySelectorAll(".view-btn").forEach((b) => {
    const active = b.dataset.view === STATE.view;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", active ? "true" : "false");
  });
  $("items-card-view").hidden = (STATE.view !== "card");
  $("items-table-view").hidden = (STATE.view !== "table");
}

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

/* 모바일 스크롤 중 우발 탭을 흡수하지 않으면서, 일반 탭/클릭/키보드 모두로
   상세를 열 수 있게 한다. pointerdown 좌표와 pointerup 좌표 차이가 크면 무시. */
function bindTap(node, handler) {
  let sx = 0, sy = 0, moved = false;
  node.addEventListener("pointerdown", (e) => {
    sx = e.clientX; sy = e.clientY; moved = false;
  }, { passive: true });
  node.addEventListener("pointermove", (e) => {
    if (Math.abs(e.clientX - sx) > 8 || Math.abs(e.clientY - sy) > 8) moved = true;
  }, { passive: true });
  node.addEventListener("click", (e) => {
    if (moved) { moved = false; return; }
    handler(e);
  });
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handler(e);
    }
  });
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
  STATE.filters = JSON.parse(JSON.stringify(FILTER_DEFAULTS));
  syncControlsFromState();
  renderQuickChips();
  applyFilters();
  hideAgentResult();
}

// ── Filter application ─────────────────────────────
function chipMatch(chip, it) {
  switch (chip) {
    case "all":       return true;
    case "favorites": return STATE.favorites.has(String(it.id));
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
  if (f.flag)      out = out.filter((it) =>
    (it.risk_flags || []).some((fl) => (fl.keyword || "").includes(f.flag)));

  out = sortItems(out, f.sort);
  STATE.filtered = out;
  renderItems();
  renderItemsHead();
  renderCharts();
  pushUrlState();
}

function renderItemsHead() {
  const f = STATE.filters;
  const root = $("items-count");
  const sortLabel = SORT_LABEL[f.sort] || SORT_LABEL.score_desc;
  let chips = `<span class="meta-chip">정렬 · ${escapeHtml(sortLabel)}</span>`;
  if (f.flag) {
    chips += ` <span class="meta-chip meta-chip-warn" data-clear-flag="1">키워드 · ${escapeHtml(f.flag)} <b>×</b></span>`;
  }
  if (f.chip && f.chip !== "all") {
    const cf = QUICK_CHIPS.find((c) => c.id === f.chip);
    if (cf) chips += ` <span class="meta-chip">${escapeHtml(cf.label)}</span>`;
  }
  root.innerHTML = `결과 ${STATE.filtered.length}건 / 전체 ${STATE.items.length}건 ${chips}`;
  const csvBtn = $("dl-csv"); const jsonBtn = $("dl-json");
  if (csvBtn && jsonBtn) {
    const empty = STATE.filtered.length === 0;
    csvBtn.disabled = empty; jsonBtn.disabled = empty;
  }
  const clearFlag = root.querySelector('[data-clear-flag="1"]');
  if (clearFlag) {
    clearFlag.style.cursor = "pointer";
    clearFlag.addEventListener("click", () => {
      STATE.filters.flag = "";
      applyFilters();
    });
  }
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
      card.setAttribute("tabindex", "0");
      card.setAttribute("role", "button");
      bindTap(card, () => openDetailById(r.item_id));
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
      const kw = f.keyword || f.flag_type || "키워드";
      const li = document.createElement("li");
      li.className = "flag-item";
      li.textContent = `${kw} (${f.count || 0})`;
      li.title = `'${kw}' 키워드를 가진 매물만 보기`;
      li.setAttribute("role", "button");
      li.setAttribute("tabindex", "0");
      bindTap(li, () => {
        STATE.filters.flag = (STATE.filters.flag === kw) ? "" : kw;
        applyFilters();
        const items = document.getElementById("section-items");
        if (items) items.scrollIntoView({ behavior: "smooth", block: "start" });
      });
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
function urgencyBadge(it) {
  const d = it.days_left;
  if (d === null || d === undefined) return "";
  if (d < 0) return "";
  if (d <= 3) return `<span class="badge-urgent">D-${d} 임박</span>`;
  if (d <= 7) return `<span class="badge-soon">D-${d}</span>`;
  return "";
}
function favoriteBtnHtml(it) {
  const on = STATE.favorites.has(String(it.id));
  return `<button class="fav-btn${on ? " on" : ""}" data-fav="${it.id}" aria-pressed="${on ? "true" : "false"}" aria-label="관심 매물 ${on ? "해제" : "등록"}">${on ? "★" : "☆"}</button>`;
}
function itemCardHtml(it) {
  const grade = it.recommendation_grade || "C";
  const risk = it.risk_level || "medium";
  const due = (it.days_left !== null && it.days_left !== undefined && it.days_left >= 0)
    ? `D-${it.days_left}`
    : (it.bid_date ? "기일 " + (it.bid_date.split("~")[0] || it.bid_date) : "기일 미정");
  return `
    <article class="item-card" data-item-id="${it.id}" tabindex="0" role="button" aria-label="물건 상세 보기">
      <div class="item-head">
        <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
        <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
        <span class="source-pill">${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</span>
        ${urgencyBadge(it)}
        <span class="caption">${escapeHtml(it.item_type || "")}</span>
        <span class="head-spacer"></span>
        ${favoriteBtnHtml(it)}
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
    bindTap(card, () => openDetailById(it.id));
    wireFavoriteButtons(card);
    cardRoot.appendChild(card);

    const tr = document.createElement("tr");
    tr.dataset.itemId = it.id;
    const grade = it.recommendation_grade || "C";
    const risk = it.risk_level || "medium";
    const u = urgencyBadge(it);
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</td>
      <td><span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span></td>
      <td>${escapeHtml(it.address || "")} ${u}</td>
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
    tr.setAttribute("tabindex", "0");
    tr.setAttribute("role", "button");
    bindTap(tr, () => openDetailById(it.id));
    tableBody.appendChild(tr);
  });
}

function toggleFavorite(id) {
  const key = String(id);
  if (STATE.favorites.has(key)) STATE.favorites.delete(key);
  else STATE.favorites.add(key);
  saveFavorites(STATE.favorites);
  // 즉시 시각 갱신: 관심 칩 활성 시에는 목록 자체에서 빠질 수 있어 재필터
  if (STATE.filters.chip === "favorites") applyFilters();
  // 그렇지 않으면 해당 카드/모달 버튼만 새로고침
  document.querySelectorAll(`[data-fav="${key}"]`).forEach((btn) => {
    const on = STATE.favorites.has(key);
    btn.classList.toggle("on", on);
    btn.textContent = on ? "★" : "☆";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function wireFavoriteButtons(root) {
  root.querySelectorAll(".fav-btn").forEach((btn) => {
    const id = btn.dataset.fav;
    const handler = (e) => {
      e.stopPropagation();
      e.preventDefault();
      toggleFavorite(id);
    };
    btn.addEventListener("click", handler);
    btn.addEventListener("pointerdown", (e) => e.stopPropagation());
  });
}

// ── Mini charts (pure SVG, no deps) ───────────────
const GRADE_ORDER = ["A", "B", "C", "D", "X"];
const GRADE_COLOR = {
  A: "#2ca02c", B: "#1f77b4", C: "#f0a500", D: "#888", X: "#d62728",
};
const RISK_COLOR = { low: "#2ca02c", medium: "#f0a500", high: "#d62728" };

function svgEl(tag, attrs, parent) {
  const NS = "http://www.w3.org/2000/svg";
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  });
  if (parent) parent.appendChild(node);
  return node;
}

function renderGradeProfitChart(items) {
  const host = $("chart-grade-profit");
  if (!host) return;
  host.innerHTML = "";
  if (!items.length) {
    host.appendChild(el(`<p class="chart-empty">표시할 데이터가 없습니다.</p>`));
    return;
  }
  // 그룹 평균
  const groups = {};
  GRADE_ORDER.forEach((g) => groups[g] = []);
  items.forEach((it) => {
    const g = it.recommendation_grade || "C";
    if (!groups[g]) groups[g] = [];
    groups[g].push(it.expected_profit || 0);
  });
  const stats = GRADE_ORDER.map((g) => {
    const arr = groups[g];
    const sum = arr.reduce((a, b) => a + b, 0);
    return {
      grade: g,
      count: arr.length,
      mean: arr.length ? sum / arr.length : 0,
    };
  });
  const maxAbs = Math.max(1, ...stats.map((s) => Math.abs(s.mean)));

  // 좌표계
  const W = 360, H = 180;
  const padL = 40, padR = 14, padT = 14, padB = 30;
  const bw = (W - padL - padR) / GRADE_ORDER.length;
  const innerH = H - padT - padB;
  const yZero = padT + innerH / 2;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "등급별 평균 예상차익" });

  // 0 축
  svgEl("line", { x1: padL, y1: yZero, x2: W - padR, y2: yZero, class: "axis-line" }, svg);
  svgEl("text", {
    x: padL - 4, y: yZero + 3, "text-anchor": "end", class: "axis-label",
  }, svg).textContent = "0";

  // 최대값 라벨
  svgEl("text", {
    x: padL - 4, y: padT + 9, "text-anchor": "end", class: "axis-label",
  }, svg).textContent = `+${Math.round(maxAbs).toLocaleString("ko-KR")}`;
  svgEl("text", {
    x: padL - 4, y: H - padB - 1, "text-anchor": "end", class: "axis-label",
  }, svg).textContent = `-${Math.round(maxAbs).toLocaleString("ko-KR")}`;

  stats.forEach((s, i) => {
    const x = padL + bw * i + bw * 0.18;
    const w = bw * 0.64;
    const ratio = maxAbs ? s.mean / maxAbs : 0;
    const half = innerH / 2;
    let y, h;
    if (ratio >= 0) {
      h = ratio * half;
      y = yZero - h;
    } else {
      h = -ratio * half;
      y = yZero;
    }
    const rect = svgEl("rect", {
      x, y, width: w, height: Math.max(1, h),
      fill: GRADE_COLOR[s.grade] || "#999",
      rx: 3, ry: 3,
    }, svg);
    rect.appendChild(svgEl("title", {}));
    rect.lastChild.textContent = `${s.grade} 등급 · ${s.count}건 · 평균 ${Math.round(s.mean).toLocaleString("ko-KR")} 만원`;

    svgEl("text", {
      x: x + w / 2, y: H - padB + 13, "text-anchor": "middle", class: "axis-label",
    }, svg).textContent = `${s.grade} (${s.count})`;

    if (s.count > 0) {
      const labelY = ratio >= 0 ? Math.max(padT + 10, y - 3) : Math.min(H - padB - 2, y + h + 11);
      svgEl("text", {
        x: x + w / 2, y: labelY, "text-anchor": "middle", class: "bar-label",
      }, svg).textContent = Math.round(s.mean).toLocaleString("ko-KR");
    }
  });

  host.appendChild(svg);
}

function renderRegionRiskChart(items) {
  const host = $("chart-region-risk");
  if (!host) return;
  host.innerHTML = "";
  if (!items.length) {
    host.appendChild(el(`<p class="chart-empty">표시할 데이터가 없습니다.</p>`));
    return;
  }
  // 지역별 위험 카운트
  const byRegion = new Map();
  items.forEach((it) => {
    const r = it.region || "기타";
    if (!byRegion.has(r)) byRegion.set(r, { low: 0, medium: 0, high: 0, total: 0 });
    const slot = byRegion.get(r);
    const lvl = it.risk_level || "medium";
    slot[lvl] = (slot[lvl] || 0) + 1;
    slot.total += 1;
  });
  const sorted = Array.from(byRegion.entries())
    .sort((a, b) => b[1].total - a[1].total)
    .slice(0, 8);
  if (!sorted.length) {
    host.appendChild(el(`<p class="chart-empty">표시할 데이터가 없습니다.</p>`));
    return;
  }
  const maxTotal = Math.max(...sorted.map(([, v]) => v.total));

  // 가로 스택 막대 (지역명 좌측, 막대 우측)
  const W = 360;
  const rowH = 22;
  const padT = 6, padB = 6;
  const labelW = 96;
  const padR = 36;
  const innerW = W - labelW - padR;
  const H = padT + padB + sorted.length * rowH;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "지역별 위험 분포" });

  sorted.forEach(([region, v], i) => {
    const y = padT + i * rowH + 4;
    const bh = rowH - 8;
    const barW = (v.total / maxTotal) * innerW;
    let x = labelW;
    const segs = [
      ["low", v.low], ["medium", v.medium], ["high", v.high],
    ];
    segs.forEach(([key, count]) => {
      if (!count) return;
      const segW = (count / v.total) * barW;
      const rect = svgEl("rect", {
        x, y, width: segW, height: bh,
        fill: RISK_COLOR[key], rx: 2, ry: 2,
      }, svg);
      rect.appendChild(svgEl("title", {}));
      rect.lastChild.textContent =
        `${region} · ${({low:"낮음",medium:"보통",high:"높음"}[key])} ${count}건`;
      x += segW;
    });
    // 지역명
    svgEl("text", {
      x: labelW - 6, y: y + bh / 2 + 3.5, "text-anchor": "end", class: "axis-label",
    }, svg).textContent = region.length > 7 ? region.slice(0, 7) + "…" : region;
    // 합계
    svgEl("text", {
      x: labelW + barW + 4, y: y + bh / 2 + 3.5, class: "bar-label",
    }, svg).textContent = String(v.total);
  });

  host.appendChild(svg);
}

function renderCharts() {
  const items = STATE.filtered;
  renderGradeProfitChart(items);
  renderRegionRiskChart(items);
  const cap = $("charts-caption");
  if (cap) cap.textContent = `현재 필터 결과 ${items.length}건 기준`;
}

// ── CSV/JSON download ─────────────────────────────
const EXPORT_COLUMNS = [
  ["id", "ID"],
  ["source", "구분"],
  ["case_no", "사건번호"],
  ["title", "물건명"],
  ["address", "주소"],
  ["region", "지역"],
  ["item_type", "물건종류"],
  ["appraisal_price", "감정가(만원)"],
  ["min_bid_price", "최저가(만원)"],
  ["market_price", "예상시세(만원)"],
  ["expected_profit", "예상차익(만원)"],
  ["expected_profit_rate", "예상수익률(%)"],
  ["recommendation_score", "추천점수"],
  ["recommendation_grade", "추천등급"],
  ["confidence_score", "신뢰도"],
  ["risk_level", "위험도"],
  ["fail_count", "유찰"],
  ["bid_date", "입찰기일"],
  ["days_left", "D-N"],
  ["recommendation_reason", "추천이유"],
  ["warnings", "주의키워드"],
  ["checklist", "추가확인사항"],
  ["next_actions", "다음액션"],
];

function flattenItem(it) {
  const row = {};
  EXPORT_COLUMNS.forEach(([k]) => {
    let v = it[k];
    if (k === "source") v = SOURCE_LABEL[v] || v || "";
    else if (k === "risk_level") v = RISK_LABEL[v] || v || "";
    else if (Array.isArray(v)) {
      v = v.map((x) => (typeof x === "object" && x !== null) ? (x.keyword || x.flag_type || JSON.stringify(x)) : x).join(" / ");
    }
    if (v === null || v === undefined) v = "";
    row[k] = v;
  });
  return row;
}

function csvEscape(v) {
  const s = String(v ?? "");
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function buildCsv(items) {
  const header = EXPORT_COLUMNS.map(([, label]) => csvEscape(label)).join(",");
  const lines = items.map((it) => {
    const row = flattenItem(it);
    return EXPORT_COLUMNS.map(([k]) => csvEscape(row[k])).join(",");
  });
  // ﻿: Excel UTF-8 BOM
  return "﻿" + header + "\r\n" + lines.join("\r\n") + "\r\n";
}

function buildJson(items) {
  const payload = {
    generated_at: new Date().toISOString(),
    source: "github-pages-export",
    filters: STATE.filters,
    sort: STATE.filters.sort,
    count: items.length,
    items: items.map((it) => {
      const row = flattenItem(it);
      // CSV 친화 평탄화는 그대로 두되, JSON 에선 원본 배열도 보존
      row.warnings = it.warnings || [];
      row.checklist = it.checklist || [];
      row.next_actions = it.next_actions || [];
      row.risk_flags = it.risk_flags || [];
      return row;
    }),
  };
  return JSON.stringify(payload, null, 2);
}

function downloadBlob(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function timestampSlug() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`;
}

function bindDownloads() {
  const csvBtn = $("dl-csv");
  const jsonBtn = $("dl-json");
  if (!csvBtn || !jsonBtn) return;
  csvBtn.addEventListener("click", () => {
    const items = STATE.filtered;
    if (!items.length) { alert("내려받을 결과가 없습니다."); return; }
    downloadBlob(buildCsv(items), `auction_results_${timestampSlug()}.csv`,
                 "text/csv;charset=utf-8");
  });
  jsonBtn.addEventListener("click", () => {
    const items = STATE.filtered;
    if (!items.length) { alert("내려받을 결과가 없습니다."); return; }
    downloadBlob(buildJson(items), `auction_results_${timestampSlug()}.json`,
                 "application/json;charset=utf-8");
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
      pushUrlState();
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
  const title = $("detail-title");
  title.innerHTML = `${escapeHtml(it.title || "물건 상세")} ${favoriteBtnHtml(it)}`;
  wireFavoriteButtons(title);
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
    bindTap(card, () => openDetailById(it.id));
    wireFavoriteButtons(card);
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
  applyUrlToState();
  syncControlsFromState();
  URL_SYNC_ENABLED = true;
  renderQuickChips();
  applyFilters();

  renderAgents(data.agent_status);

  // 뒤로가기/앞으로가기 시 URL → state 복원
  window.addEventListener("popstate", () => {
    URL_SYNC_ENABLED = false;
    applyUrlToState();
    syncControlsFromState();
    renderQuickChips();
    applyFilters();
    URL_SYNC_ENABLED = true;
  });
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

// ── PWA: install prompt + service worker + 오프라인 토스트 ─────
let DEFERRED_INSTALL = null;

function showToast(message, actionLabel, onAction) {
  const toast = $("pwa-toast");
  if (!toast) return;
  $("pwa-toast-msg").textContent = message;
  const action = $("pwa-toast-action");
  if (actionLabel) {
    action.textContent = actionLabel;
    action.hidden = false;
    action.onclick = () => { try { onAction && onAction(); } finally { hideToast(); } };
  } else {
    action.hidden = true;
    action.onclick = null;
  }
  toast.hidden = false;
}
function hideToast() {
  const toast = $("pwa-toast");
  if (toast) toast.hidden = true;
}

function bindPwa() {
  const closeBtn = $("pwa-toast-close");
  if (closeBtn) closeBtn.addEventListener("click", hideToast);

  const installBtn = $("install-btn");
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    DEFERRED_INSTALL = e;
    if (installBtn) installBtn.hidden = false;
  });
  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      if (!DEFERRED_INSTALL) return;
      installBtn.hidden = true;
      try {
        await DEFERRED_INSTALL.prompt();
        await DEFERRED_INSTALL.userChoice;
      } catch (_) { /* 사용자 취소 등 */ }
      DEFERRED_INSTALL = null;
    });
  }
  window.addEventListener("appinstalled", () => {
    if (installBtn) installBtn.hidden = true;
    DEFERRED_INSTALL = null;
    showToast("앱으로 설치 완료. 홈 화면에서 바로 열 수 있어요.", null);
    setTimeout(hideToast, 3500);
  });

  // 오프라인 / 온라인
  window.addEventListener("offline", () => {
    showToast("오프라인 — 캐시된 데이터를 표시합니다.", null);
  });
  window.addEventListener("online", () => {
    showToast("온라인 복귀 — 데이터를 새로 받아옵니다.", "새로고침", () => location.reload());
  });

  // 서비스 워커 등록
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js", { scope: "./" }).then((reg) => {
        // 새 SW 가 대기 중이면 사용자에게 새로고침 옵션 노출
        const handleWaiting = () => {
          if (reg.waiting) {
            showToast("새 버전이 준비됐어요.", "새로고침", () => {
              reg.waiting.postMessage("SKIP_WAITING");
            });
          }
        };
        if (reg.waiting) handleWaiting();
        reg.addEventListener("updatefound", () => {
          const sw = reg.installing;
          if (!sw) return;
          sw.addEventListener("statechange", () => {
            if (sw.state === "installed" && navigator.serviceWorker.controller) {
              handleWaiting();
            }
          });
        });
      }).catch(() => { /* SW 등록 실패는 무시 */ });

      let reloaded = false;
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (reloaded) return;
        reloaded = true;
        location.reload();
      });
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  bindFilterEvents();
  bindSearch();
  bindAgentSearch();
  bindViewToggle();
  bindDownloads();
  bindModalClose();
  bindPwa();
  load();
});
