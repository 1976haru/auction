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
  { id: "changes",  label: "🆕 변화" },
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

// 한 번에 여러 필터를 세팅하는 프리셋 — chipMatch 가 처리하지 못하는 조건은
// 추가 후처리(filter)에서 score/risk 등 제약을 더 둘 수 있도록 둔다.
const PRESETS = [
  {
    id: "p_recommended",
    label: "⭐ 추천 후보",
    apply: () => ({ chip: "all", grade: "", risk: "", source: "",
                    sort: "score_desc", _scoreMin: 60 }),
    note: "점수 60 이상 + 추천점수 정렬",
  },
  {
    id: "p_high_low",
    label: "🚀 고수익 저위험",
    apply: () => ({ chip: "all", grade: "", risk: "low", source: "",
                    sort: "profit_desc" }),
    note: "위험 낮음 + 차익 큰순",
  },
  {
    id: "p_imminent",
    label: "⏰ 임박 후보",
    apply: () => ({ chip: "all", grade: "", risk: "", source: "",
                    due_max: 7, sort: "due_asc" }),
    note: "7일 이내 + 기일 임박순",
  },
  {
    id: "p_seoul_apt",
    label: "🏠 서울 아파트",
    apply: () => ({ chip: "all", region: "서울특별시", item_type: "아파트",
                    sort: "score_desc" }),
    note: "서울 + 아파트 + 추천 정렬",
  },
  {
    id: "p_grade_a",
    label: "🥇 A등급만",
    apply: () => ({ chip: "all", grade: "A", sort: "score_desc" }),
    note: "A등급 추천 정렬",
  },
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

const COMPARE_KEY = "auction:compare:v1";
const COMPARE_MAX = 5;
const COMPARE_MIN = 2;
function loadCompare() {
  try {
    const raw = localStorage.getItem(COMPARE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.map(String).slice(0, COMPARE_MAX) : [];
  } catch { return []; }
}
function saveCompare(list) {
  try { localStorage.setItem(COMPARE_KEY, JSON.stringify(list)); } catch {}
}

// ── 글로벌 상태 ──────────────────────────────────────
const PAGE_SIZE = 30;
const STATE = {
  data: null,
  items: [],
  filtered: [],
  view: "card",          // card | table
  pageShown: PAGE_SIZE,
  favorites: loadFavorites(),
  compare: loadCompare(),  // ordered list of item ids (string)
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
   상세를 열 수 있게 한다. pointerdown 좌표와 pointerup 좌표 차이가 크면 무시.
   opts.onLongPress 가 있으면 길게 누름(>=550ms) 시 호출, 이때 click 은 발화하지 않는다. */
function bindTap(node, handler, opts) {
  let sx = 0, sy = 0, moved = false, longPressed = false;
  let timer = null;
  const longMs = (opts && opts.longPressMs) || 550;
  const onLongPress = opts && opts.onLongPress;

  const cancelTimer = () => {
    if (timer) { clearTimeout(timer); timer = null; }
  };

  node.addEventListener("pointerdown", (e) => {
    sx = e.clientX; sy = e.clientY; moved = false; longPressed = false;
    if (onLongPress) {
      timer = setTimeout(() => {
        if (!moved) {
          longPressed = true;
          onLongPress(e);
        }
      }, longMs);
    }
  }, { passive: true });
  node.addEventListener("pointermove", (e) => {
    if (Math.abs(e.clientX - sx) > 8 || Math.abs(e.clientY - sy) > 8) {
      moved = true;
      cancelTimer();
    }
  }, { passive: true });
  node.addEventListener("pointerup", cancelTimer, { passive: true });
  node.addEventListener("pointercancel", cancelTimer, { passive: true });
  node.addEventListener("pointerleave", cancelTimer, { passive: true });
  node.addEventListener("click", (e) => {
    if (moved || longPressed) { moved = false; longPressed = false; return; }
    handler(e);
  });
  node.addEventListener("contextmenu", (e) => {
    // 길게 누르면 일부 폰에서 컨텍스트 메뉴가 뜨는 것 방지 (onLongPress 가 있을 때만)
    if (onLongPress) e.preventDefault();
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

// ── Preset chips ─────────────────────────────────────
function applyPreset(preset) {
  const overrides = preset.apply() || {};
  // 기본값으로 리셋 후 프리셋 덮어쓰기 (사용자가 매번 깨끗한 상태에서 시작)
  STATE.filters = JSON.parse(JSON.stringify(FILTER_DEFAULTS));
  // _scoreMin 같은 임시 키도 같이 받도록 머지
  Object.entries(overrides).forEach(([k, v]) => { STATE.filters[k] = v; });
  syncControlsFromState();
  renderQuickChips();
  applyFilters();
  showToast(`프리셋 적용: ${preset.label} — ${preset.note || ""}`, "초기화", () => resetFilters());
  setTimeout(hideToast, 3500);
  // 결과 영역으로 자동 스크롤
  const items = document.getElementById("section-items");
  if (items) items.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPresets() {
  const root = $("preset-chips");
  if (!root) return;
  clearChildren(root);
  PRESETS.forEach((p) => {
    const btn = document.createElement("button");
    btn.className = "preset-chip";
    btn.type = "button";
    btn.textContent = p.label;
    btn.title = p.note || "";
    btn.addEventListener("click", () => applyPreset(p));
    root.appendChild(btn);
  });
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
    case "changes":   return Array.isArray(it.change_tags) && it.change_tags.length > 0;
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
  if (f._scoreMin !== undefined && f._scoreMin !== null)
    out = out.filter((it) => (it.recommendation_score || 0) >= f._scoreMin);

  out = sortItems(out, f.sort);
  STATE.filtered = out;
  STATE.pageShown = PAGE_SIZE;  // 필터/검색 바뀌면 항상 처음부터
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
  const shown = Math.min(STATE.pageShown, STATE.filtered.length);
  const showCount = (shown < STATE.filtered.length)
    ? `표시 ${shown} / 결과 ${STATE.filtered.length} / 전체 ${STATE.items.length}건`
    : `결과 ${STATE.filtered.length}건 / 전체 ${STATE.items.length}건`;
  root.innerHTML = `${showCount} ${chips}`;
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
    // 매물 상세 데이터(변화 태그 등)는 items 배열에서 join
    const itFull = r.item_id ? STATE.items.find((x) => String(x.id) === String(r.item_id)) : null;
    const recCh = itFull ? changeBadgesHtml(itFull) : "";
    const card = el(
      `<article class="rec-card" data-item-id="${r.item_id || ""}">
         <div class="rec-head">
           <span class="rec-rank">#${escapeHtml(String(r.rank || ""))}</span>
           <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
           <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
           <span class="source-pill">${escapeHtml(SOURCE_LABEL[r.source] || r.source || "")}</span>
           ${recCh}
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
      bindTap(card, () => openDetailById(r.item_id), {
        onLongPress: () => toggleCompare(r.item_id),
      });
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

const CHANGE_LABEL = {
  new: "🆕 신규",
  price_drop: "⬇ 최저가 인하",
  price_up: "⬆ 최저가 인상",
  bid_date: "📅 기일 변경",
  fail_inc: "🔄 유찰 추가",
  status: "⚠ 상태 변경",
};
function changeBadgesHtml(it) {
  const tags = it.change_tags;
  if (!Array.isArray(tags) || !tags.length) return "";
  return tags.map((t) => {
    const k = (t && t.key) || "new";
    const label = CHANGE_LABEL[k] || (t && t.label) || "변화";
    return `<span class="badge-change badge-change-${escapeHtml(k)}">${escapeHtml(label)}</span>`;
  }).join("");
}
function favoriteBtnHtml(it) {
  const on = STATE.favorites.has(String(it.id));
  return `<button class="fav-btn${on ? " on" : ""}" data-fav="${it.id}" aria-pressed="${on ? "true" : "false"}" aria-label="관심 매물 ${on ? "해제" : "등록"}">${on ? "★" : "☆"}</button>`;
}
function compareBtnHtml(it) {
  const on = STATE.compare.includes(String(it.id));
  return `<button class="cmp-btn${on ? " on" : ""}" data-cmp="${it.id}" aria-pressed="${on ? "true" : "false"}" aria-label="비교에 ${on ? "제거" : "담기"}" title="비교 트레이에 ${on ? "제거" : "담기"} (카드 길게 눌러도 동일)">${on ? "⇆ 담김" : "⇆ 비교"}</button>`;
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
        ${changeBadgesHtml(it)}
        <span class="head-spacer"></span>
        ${compareBtnHtml(it)}
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

  const fullList = STATE.filtered;
  if (!fullList.length) {
    cardRoot.appendChild(el(`<p class="caption">조건에 맞는 물건이 없습니다.</p>`));
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="13" class="caption">조건에 맞는 물건이 없습니다.</td>`;
    tableBody.appendChild(tr);
    updateMoreRow();
    return;
  }
  // 페이지네이션 — 처음 pageShown 만 그린다
  const list = fullList.slice(0, STATE.pageShown);
  list.forEach((it, idx) => {
    const card = el(itemCardHtml(it));
    bindTap(card, () => openDetailById(it.id), {
      onLongPress: () => toggleCompare(it.id),
    });
    wireFavoriteButtons(card);
    wireCompareButtons(card);
    cardRoot.appendChild(card);

    const tr = document.createElement("tr");
    tr.dataset.itemId = it.id;
    const grade = it.recommendation_grade || "C";
    const risk = it.risk_level || "medium";
    const u = urgencyBadge(it);
    const ch = changeBadgesHtml(it);
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</td>
      <td><span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span></td>
      <td>${escapeHtml(it.address || "")} ${u} ${ch}</td>
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
    bindTap(tr, () => openDetailById(it.id), {
      onLongPress: () => toggleCompare(it.id),
    });
    tableBody.appendChild(tr);
  });
  updateMoreRow();
}

function updateMoreRow() {
  const row = $("more-row");
  const btn = $("more-btn");
  if (!row || !btn) return;
  const total = STATE.filtered.length;
  const shown = Math.min(STATE.pageShown, total);
  const remaining = Math.max(0, total - shown);
  if (remaining > 0) {
    row.hidden = false;
    btn.textContent = `더 보기 (+${Math.min(PAGE_SIZE, remaining)} / ${remaining}건 남음)`;
    btn.disabled = false;
  } else {
    row.hidden = true;
    btn.disabled = true;
  }
}

function bindMoreButton() {
  const btn = $("more-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    STATE.pageShown += PAGE_SIZE;
    renderItems();
    renderItemsHead();
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

function toggleCompare(id) {
  const key = String(id);
  const idx = STATE.compare.indexOf(key);
  if (idx >= 0) {
    STATE.compare.splice(idx, 1);
  } else {
    if (STATE.compare.length >= COMPARE_MAX) {
      showToast(`비교는 최대 ${COMPARE_MAX}개까지 담을 수 있어요.`, null);
      setTimeout(hideToast, 2500);
      return;
    }
    STATE.compare.push(key);
  }
  saveCompare(STATE.compare);
  // 모든 cmp-btn / 카드 시각 갱신
  document.querySelectorAll(`[data-cmp="${key}"]`).forEach((btn) => {
    const on = STATE.compare.includes(key);
    btn.classList.toggle("on", on);
    btn.textContent = on ? "⇆ 담김" : "⇆ 비교";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  renderCompareTray();
}

function wireCompareButtons(root) {
  root.querySelectorAll(".cmp-btn").forEach((btn) => {
    const id = btn.dataset.cmp;
    const handler = (e) => {
      e.stopPropagation();
      e.preventDefault();
      toggleCompare(id);
    };
    btn.addEventListener("click", handler);
    btn.addEventListener("pointerdown", (e) => e.stopPropagation());
  });
}

function renderCompareTray() {
  const tray = $("compare-tray");
  if (!tray) return;
  const ids = STATE.compare.slice();
  if (!ids.length) { tray.hidden = true; return; }
  tray.hidden = false;

  const chipsRoot = $("tray-chips");
  chipsRoot.innerHTML = "";
  ids.forEach((id) => {
    const it = STATE.items.find((x) => String(x.id) === id);
    const label = it ? (it.title || it.address || `#${id}`) : `#${id}`;
    const grade = (it && it.recommendation_grade) || "?";
    const chip = el(
      `<span class="tray-chip" data-id="${escapeHtml(id)}">
         <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
         <span>${escapeHtml(label.length > 24 ? label.slice(0,24) + "…" : label)}</span>
         <button class="tray-chip-x" type="button" aria-label="비교에서 제거">×</button>
       </span>`
    );
    chip.querySelector(".tray-chip-x").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleCompare(id);
    });
    chipsRoot.appendChild(chip);
  });
  $("tray-count").textContent = `${ids.length}/${COMPARE_MAX}`;
  $("tray-open").disabled = ids.length < COMPARE_MIN;
}

function bindCompareTray() {
  const closeBtn = $("compare-close");
  if (closeBtn) closeBtn.addEventListener("click", closeCompareModal);
  const printBtn = $("compare-print");
  if (printBtn) printBtn.addEventListener("click", printCompare);
  const modal = $("compare-modal");
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target instanceof HTMLElement && e.target.dataset.close === "1") closeCompareModal();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("compare-modal").hidden) closeCompareModal();
  });
  $("tray-clear").addEventListener("click", () => {
    STATE.compare = [];
    saveCompare(STATE.compare);
    document.querySelectorAll(".cmp-btn.on").forEach((btn) => {
      btn.classList.remove("on");
      btn.textContent = "⇆ 비교";
      btn.setAttribute("aria-pressed", "false");
    });
    renderCompareTray();
  });
  $("tray-open").addEventListener("click", openCompareModal);
}

function closeCompareModal() {
  $("compare-modal").hidden = true;
  document.body.style.overflow = "";
}

function openCompareModal() {
  const ids = STATE.compare.slice();
  if (ids.length < COMPARE_MIN) return;
  const items = ids
    .map((id) => STATE.items.find((x) => String(x.id) === id))
    .filter(Boolean);
  if (items.length < COMPARE_MIN) return;

  $("compare-title").textContent = `물건 비교 (${items.length}건)`;
  $("compare-body").innerHTML = renderCompareTable(items);
  $("compare-modal").hidden = false;
  document.body.style.overflow = "hidden";
}

function renderCompareTable(items) {
  const RISK_RANK = { low: 0, medium: 1, high: 2 };
  // 각 row 의 best/worst 마킹 정의: dir = "max" | "min"
  const rows = [
    { section: "기본" },
    { key: "grade",       label: "추천등급", dir: null,
      get: (it) => it.recommendation_grade || "-",
      cmp: (it) => ({ A: 4, B: 3, C: 2, D: 1, X: 0 }[it.recommendation_grade] ?? -1), bestDir: "max" },
    { key: "score",       label: "추천점수", dir: "max",
      get: (it) => Number(it.recommendation_score || 0).toFixed(1),
      cmp: (it) => Number(it.recommendation_score || 0) },
    { key: "risk",        label: "위험도",   dir: "min",
      get: (it) => RISK_LABEL[it.risk_level] || it.risk_level || "-",
      cmp: (it) => RISK_RANK[it.risk_level] ?? 1 },
    { key: "source",      label: "구분",     dir: null,
      get: (it) => SOURCE_LABEL[it.source] || it.source || "-" },

    { section: "가격" },
    { key: "appraisal",   label: "감정가",   dir: null,
      get: (it) => fmtMan(it.appraisal_price) },
    { key: "min_bid",     label: "최저가",   dir: "min",
      get: (it) => fmtMan(it.min_bid_price), cmp: (it) => it.min_bid_price || Infinity },
    { key: "market",      label: "예상시세", dir: null,
      get: (it) => fmtMan(it.market_price) },
    { key: "profit",      label: "예상차익", dir: "max",
      get: (it) => fmtMan(it.expected_profit), cmp: (it) => it.expected_profit || 0 },
    { key: "roi",         label: "예상수익률", dir: "max",
      get: (it) => fmtPct(it.expected_profit_rate), cmp: (it) => it.expected_profit_rate || 0 },

    { section: "일정" },
    { key: "bid_date",    label: "입찰기일", dir: null,
      get: (it) => it.bid_date || "-" },
    { key: "days_left",   label: "D-N",      dir: "min",
      get: (it) => (it.days_left === null || it.days_left === undefined) ? "-"
                   : (it.days_left < 0 ? "지남" : `D-${it.days_left}`),
      cmp: (it) => (it.days_left === null || it.days_left === undefined || it.days_left < 0) ? Infinity : it.days_left },
    { key: "fail_count",  label: "유찰",     dir: "min",
      get: (it) => `${it.fail_count ?? 0}회`, cmp: (it) => it.fail_count || 0 },
    { key: "case_no",     label: "사건번호", dir: null,
      get: (it) => it.case_no || "-" },

    { section: "위험·신뢰도" },
    { key: "flags",       label: "위험 키워드", dir: null,
      get: (it) => {
        const arr = (it.risk_flags || []).map((f) => f.keyword || f.flag_type).filter(Boolean);
        return arr.length ? arr.slice(0, 4).map(escapeHtml).join(", ") : "—";
      }, html: true },
    { key: "confidence",  label: "신뢰도",   dir: "max",
      get: (it) => Number(it.confidence_score || 0).toFixed(2),
      cmp: (it) => Number(it.confidence_score || 0) },

    { section: "추천 / 액션" },
    { key: "reason",      label: "추천 이유", dir: null,
      get: (it) => it.recommendation_reason || "-" },
    { key: "next",        label: "다음 액션", dir: null,
      get: (it) => (it.next_actions || []).length
                   ? "<ul style='margin:0;padding-left:18px'>" +
                     it.next_actions.slice(0, 4).map((c) => `<li>${escapeHtml(c)}</li>`).join("") +
                     "</ul>"
                   : "—",
      html: true },
    { key: "checklist",   label: "추가 확인",  dir: null,
      get: (it) => (it.checklist || []).length
                   ? "<ul style='margin:0;padding-left:18px'>" +
                     it.checklist.slice(0, 4).map((c) => `<li>${escapeHtml(c)}</li>`).join("") +
                     "</ul>"
                   : "—",
      html: true },
  ];

  // 헤더 (각 매물 컬럼)
  const colHeads = items.map((it) => {
    const grade = it.recommendation_grade || "C";
    const risk = it.risk_level || "medium";
    const u = urgencyBadge(it);
    return `<th>
      <div class="compare-col-head">
        <div class="pills">
          <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
          <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
          <span class="source-pill">${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</span>
          ${u}
        </div>
        <div class="ttl">${escapeHtml(it.title || "주소 미상")}</div>
        <div class="meta">${escapeHtml(it.address || "")} · ${escapeHtml(it.item_type || "")}</div>
      </div>
    </th>`;
  }).join("");

  // 본문
  let body = "";
  rows.forEach((row) => {
    if (row.section) {
      body += `<tr class="compare-section-row">
        <th colspan="${items.length + 1}">${escapeHtml(row.section)}</th>
      </tr>`;
      return;
    }
    let bestIdx = -1, worstIdx = -1;
    if (row.cmp && (row.dir || row.bestDir)) {
      const dir = row.dir || row.bestDir;
      const vals = items.map((it) => row.cmp(it));
      const numeric = vals.filter((v) => Number.isFinite(v));
      if (numeric.length >= 2) {
        const best = (dir === "min") ? Math.min(...numeric) : Math.max(...numeric);
        const worst = (dir === "min") ? Math.max(...numeric) : Math.min(...numeric);
        bestIdx = vals.findIndex((v) => v === best);
        worstIdx = (best !== worst) ? vals.findIndex((v) => v === worst) : -1;
      }
    }
    const cells = items.map((it, idx) => {
      const v = row.get(it);
      const safe = row.html ? v : escapeHtml(v);
      let cls = "";
      let mark = "";
      if (idx === bestIdx) { cls = "best"; mark = `<span class="mark-best" title="이 비교에서 최고">▲</span>`; }
      else if (idx === worstIdx) { cls = "worst"; mark = `<span class="mark-worst" title="이 비교에서 최저">▼</span>`; }
      return `<td class="${cls}">${mark}${safe}</td>`;
    }).join("");
    body += `<tr><th scope="row">${escapeHtml(row.label)}</th>${cells}</tr>`;
  });

  return `
    <p class="caption" style="margin:0 0 10px">
      ▲ 이 비교에서 최고값 / ▼ 최저값 — mock 데이터 기반 단순 비교이며 법률·투자 판단을 대체하지 않습니다.
    </p>
    <div class="compare-table-wrap">
      <table class="compare-table">
        <thead><tr><th></th>${colHeads}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
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

/* 추천 점수 분해 — 각 기여 항목별 가로 막대 */
const BREAKDOWN_COLOR = {
  profit: "#1f77b4",
  roi: "#2ca02c",
  risk: "#f0a500",
  confidence: "#9467bd",
  urgency: "#d62728",
};
function renderScoreBreakdown(it) {
  const parts = it && it.score_breakdown;
  if (!Array.isArray(parts) || !parts.length) return "";
  const sum = parts.reduce((a, p) => a + (p.contribution || 0), 0);
  const total = parts.reduce((a, p) => a + (p.max || 0), 0) || 100;
  const rows = parts.map((p) => {
    const c = p.contribution || 0;
    const m = p.max || 1;
    const pct = Math.max(0, Math.min(100, (c / m) * 100));
    const color = BREAKDOWN_COLOR[p.key] || "#1f77b4";
    return `
      <div class="bk-row">
        <span class="bk-label">${escapeHtml(p.label || p.key || "-")}</span>
        <span class="bk-bar" aria-hidden="true">
          <span class="bk-fill" style="width:${pct.toFixed(1)}%; background:${color}"></span>
        </span>
        <span class="bk-val"><b>${c}</b><span class="bk-max">/${m}</span></span>
        <span class="bk-note caption">${escapeHtml(p.note || "")}</span>
      </div>`;
  }).join("");
  return `
    <div class="score-breakdown" aria-label="추천 점수 분해">
      <div class="bk-head">
        <span class="caption">기여 항목</span>
        <span class="bk-total">합계 <b>${sum}</b><span class="bk-max">/${total}</span></span>
      </div>
      ${rows}
      <p class="caption" style="margin-top:6px">
        ※ 각 항목은 점수 기여도이며 합계는 추천 점수와 약간 다를 수 있어요. 위험·신뢰도가 낮을수록 막대가 짧습니다.
      </p>
    </div>
  `;
}

/* 매물 상세용 sparkline. price_trend = [{ym, avg_price, count}, ...] */
function renderPriceTrendSvg(it) {
  const pts = (it && it.price_trend) || [];
  if (!pts.length) {
    return `<p class="caption">표본이 부족해 시세 트렌드를 표시할 수 없습니다.</p>`;
  }
  const W = 360, H = 130;
  const padL = 36, padR = 10, padT = 12, padB = 22;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const refs = {
    "감정가": it.appraisal_price || 0,
    "최저가": it.min_bid_price || 0,
    "추정시세": it.market_price || 0,
  };
  const refColors = { "감정가": "#888", "최저가": "#1f77b4", "추정시세": "#2ca02c" };

  const ys = pts.map((p) => p.avg_price);
  const refVals = Object.values(refs).filter((v) => v > 0);
  const minY = Math.min(...ys, ...refVals);
  const maxY = Math.max(...ys, ...refVals);
  const range = Math.max(1, maxY - minY);

  const xAt = (i) => padL + (pts.length === 1 ? innerW / 2 : (innerW * i) / (pts.length - 1));
  const yAt = (v) => padT + innerH - ((v - minY) / range) * innerH;

  let lines = "";
  // 기준선 (점선)
  Object.entries(refs).forEach(([label, v]) => {
    if (!v) return;
    const y = yAt(v).toFixed(2);
    lines += `<line x1="${padL}" x2="${W - padR}" y1="${y}" y2="${y}"
      stroke="${refColors[label]}" stroke-width="1" stroke-dasharray="3,3" opacity="0.55"/>
      <text x="${W - padR - 2}" y="${(parseFloat(y) - 2).toFixed(1)}"
        text-anchor="end" font-size="9" fill="${refColors[label]}">
        ${label} ${Math.round(v).toLocaleString("ko-KR")}
      </text>`;
  });

  // 라인 (avg_price)
  let dPath = "";
  pts.forEach((p, i) => {
    const x = xAt(i).toFixed(2), y = yAt(p.avg_price).toFixed(2);
    dPath += (i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`);
  });

  // 점 + tooltip
  let dots = "";
  pts.forEach((p, i) => {
    const x = xAt(i).toFixed(2), y = yAt(p.avg_price).toFixed(2);
    dots += `<g><circle cx="${x}" cy="${y}" r="2.5" fill="#1f77b4"/>
      <title>${p.ym} · 평균 ${p.avg_price.toLocaleString("ko-KR")} 만원 (${p.count || 0}건)</title>
    </g>`;
  });

  // x축 라벨 (시작/중간/끝)
  const xticks = [0, Math.floor(pts.length / 2), pts.length - 1]
    .filter((v, idx, a) => a.indexOf(v) === idx);
  let xLabels = "";
  xticks.forEach((i) => {
    const x = xAt(i).toFixed(2);
    xLabels += `<text x="${x}" y="${H - padB + 14}" text-anchor="middle"
      font-size="9" fill="var(--color-text-muted)">${pts[i].ym}</text>`;
  });

  // y축 라벨 (min/max)
  const yLabels = `
    <text x="${padL - 4}" y="${(yAt(maxY) + 3).toFixed(1)}" text-anchor="end"
      font-size="9" fill="var(--color-text-muted)">${Math.round(maxY).toLocaleString("ko-KR")}</text>
    <text x="${padL - 4}" y="${(yAt(minY) + 3).toFixed(1)}" text-anchor="end"
      font-size="9" fill="var(--color-text-muted)">${Math.round(minY).toLocaleString("ko-KR")}</text>
  `;

  return `
    <div class="trend-host">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="월별 시세 트렌드">
        ${lines}
        <path d="${dPath}" fill="none" stroke="#1f77b4" stroke-width="1.8"
              stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
        ${yLabels}
        ${xLabels}
      </svg>
      <div class="trend-legend">
        <span><i style="background:#1f77b4"></i>월평균 거래가</span>
        <span><i style="background:#888"></i>감정가</span>
        <span><i style="background:#2ca02c"></i>추정시세</span>
      </div>
    </div>
  `;
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
  CURRENT_DETAIL_ID = String(it.id);
  // 공유 가능한 해시 딥링크 동기화 (사이드 효과로 popstate 가 일어나면 무시)
  const wantHash = `#item-${it.id}`;
  if (window.location.hash !== wantHash) {
    history.replaceState(null, "", window.location.pathname + window.location.search + wantHash);
  }
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
      ${renderPriceTrendSvg(it)}
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
      <h3>최근 변화 (7일)</h3>
      ${(it.change_events || []).length
        ? `<ul>${it.change_events.map((ev) => {
            const old = ev.old_value || "-"; const cur = ev.new_value || "-";
            const msg = ev.message || ev.event_type || "변화";
            return `<li>${escapeHtml(msg)} — <code>${escapeHtml(old)}</code> → <code>${escapeHtml(cur)}</code></li>`;
          }).join("")}</ul>`
        : `<p class="caption">최근 7일 내 기록된 변경 이력이 없습니다.</p>`}
      ${(it.change_tags || []).length
        ? `<div class="detail-tags">${changeBadgesHtml(it)}</div>` : ""}
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
      ${renderScoreBreakdown(it)}
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

let CURRENT_DETAIL_ID = null;

function bindModalClose() {
  const close = () => closeDetailModal();
  $("detail-close").addEventListener("click", close);
  $("detail-modal").addEventListener("click", (e) => {
    if (e.target instanceof HTMLElement && e.target.dataset.close === "1") close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("detail-modal").hidden) close();
  });
  const printBtn = $("detail-print");
  if (printBtn) printBtn.addEventListener("click", printDetail);
  const shareBtn = $("detail-share");
  if (shareBtn) shareBtn.addEventListener("click", shareDetail);
}

function closeDetailModal() {
  $("detail-modal").hidden = true;
  if ($("compare-modal").hidden && $("kbd-modal").hidden) {
    document.body.style.overflow = "";
  }
  // 해시가 현재 매물이면 정리
  if (CURRENT_DETAIL_ID && window.location.hash === `#item-${CURRENT_DETAIL_ID}`) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  CURRENT_DETAIL_ID = null;
}

function shareDetail() {
  if (!CURRENT_DETAIL_ID) return;
  const it = STATE.items.find((x) => String(x.id) === String(CURRENT_DETAIL_ID));
  if (!it) return;

  // 해시 포함 절대 URL 생성 (수신자가 열면 바로 매물 모달 오픈)
  const url = new URL(window.location.href);
  url.hash = `item-${it.id}`;
  const shareUrl = url.toString();

  const grade = it.recommendation_grade || "C";
  const risk = RISK_LABEL[it.risk_level] || it.risk_level || "-";
  const lines = [
    `[${grade}등급] ${it.title || it.address || "물건"}`,
    `점수 ${it.recommendation_score ?? "-"} · 차익 ${(it.expected_profit || 0).toLocaleString("ko-KR")}만원 · 위험 ${risk}`,
    `${SOURCE_LABEL[it.source] || it.source || ""} · ${it.item_type || ""} · ${it.bid_date || "기일 미정"}`,
  ];
  const text = lines.join("\n");
  const title = "경매·공매 지능형 에이전트";

  if (navigator.share) {
    navigator.share({ title, text, url: shareUrl })
      .catch((err) => {
        // 사용자가 취소했거나 권한 거부 — 폴백 안 함
        if (err && err.name === "AbortError") return;
        copyShareLink(text, shareUrl);
      });
  } else {
    copyShareLink(text, shareUrl);
  }
}

function copyShareLink(text, url) {
  const payload = `${text}\n${url}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(payload).then(() => {
      showToast("링크와 요약이 복사됐어요. 붙여 넣어 공유하세요.", null);
      setTimeout(hideToast, 2500);
    }).catch(() => fallbackCopy(payload));
  } else {
    fallbackCopy(payload);
  }
}

function fallbackCopy(text) {
  // 구형 브라우저 폴백
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try {
    document.execCommand("copy");
    showToast("링크가 복사됐어요.", null);
    setTimeout(hideToast, 2500);
  } catch (_) {
    showToast("복사가 차단됐어요. 주소창의 URL을 직접 공유해 주세요.", null);
    setTimeout(hideToast, 3500);
  } finally {
    document.body.removeChild(ta);
  }
}

function printDetail() {
  if ($("detail-modal").hidden) return;
  document.body.classList.add("printing-detail");
  const cleanup = () => {
    document.body.classList.remove("printing-detail");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  setTimeout(cleanup, 5000);
  try { window.print(); } catch (_) { cleanup(); }
}

function printCompare() {
  if ($("compare-modal").hidden) return;
  document.body.classList.add("printing-compare");
  const cleanup = () => {
    document.body.classList.remove("printing-compare");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  setTimeout(cleanup, 5000);
  try { window.print(); } catch (_) { cleanup(); }
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
    bindTap(card, () => openDetailById(it.id), {
      onLongPress: () => toggleCompare(it.id),
    });
    wireFavoriteButtons(card);
    wireCompareButtons(card);
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
  renderPresets();
  applyFilters();

  // 비교 트레이: 데이터에 더 이상 없는 id 는 제거
  const validIds = new Set(STATE.items.map((it) => String(it.id)));
  STATE.compare = STATE.compare.filter((id) => validIds.has(id));
  saveCompare(STATE.compare);
  renderCompareTray();

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

  // 해시 딥링크: #item-123 이면 해당 매물 모달 자동 오픈
  routeHashToDetail();
  window.addEventListener("hashchange", routeHashToDetail);
}

function routeHashToDetail() {
  const m = window.location.hash.match(/^#item-(\d+)$/);
  if (!m) {
    // 모달이 열려 있는데 해시가 사라졌다면 닫기
    if (CURRENT_DETAIL_ID && !$("detail-modal").hidden) closeDetailModal();
    return;
  }
  const id = m[1];
  if (CURRENT_DETAIL_ID === String(id) && !$("detail-modal").hidden) return;
  // STATE.items 가 채워진 시점에서 호출되므로 안전
  openDetailById(id);
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

// ── 키보드 단축키 ────────────────────────────────
const GRADE_ROTATION = ["", "A", "B", "C", "D", "X"];

function isTextFocus(target) {
  if (!target) return false;
  const tag = (target.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

function openKbdModal() {
  $("kbd-modal").hidden = false;
  document.body.style.overflow = "hidden";
}
function closeKbdModal() {
  $("kbd-modal").hidden = true;
  // 다른 모달이 열려 있을 수 있어 무조건 본문 스크롤 복구는 안 한다
  if ($("detail-modal").hidden && $("compare-modal").hidden) {
    document.body.style.overflow = "";
  }
}

function bindKbdShortcuts() {
  // 모달 닫기 버튼/배경
  const closeBtn = $("kbd-close");
  if (closeBtn) closeBtn.addEventListener("click", closeKbdModal);
  const modal = $("kbd-modal");
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target instanceof HTMLElement && e.target.dataset.close === "1") closeKbdModal();
    });
  }
  const helpBtn = $("kbd-help-btn");
  if (helpBtn) helpBtn.addEventListener("click", openKbdModal);

  document.addEventListener("keydown", (e) => {
    // 모달 열려 있으면 Esc 만 처리하고 종료
    const anyModalOpen = !$("detail-modal").hidden ||
                         !$("compare-modal").hidden ||
                         !$("kbd-modal").hidden;
    if (e.key === "Escape") {
      if (!$("kbd-modal").hidden) { closeKbdModal(); return; }
      // 다른 모달은 각자 핸들러가 담당
      if (!anyModalOpen && document.activeElement === $("q-input")) {
        $("q-input").blur();
      }
      return;
    }
    if (anyModalOpen) return;
    if (isTextFocus(e.target)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    switch (e.key) {
      case "/":
        e.preventDefault();
        $("q-input").focus();
        $("q-input").select();
        break;
      case "?":
        e.preventDefault();
        openKbdModal();
        break;
      case "r":
      case "R":
        e.preventDefault();
        resetFilters();
        break;
      case "t":
      case "T": {
        e.preventDefault();
        const cur = effectiveTheme();
        applyTheme(cur === "dark" ? "light" : "dark", true);
        break;
      }
      case "1": {
        e.preventDefault();
        STATE.view = "card";
        syncControlsFromState();
        pushUrlState();
        break;
      }
      case "2": {
        e.preventDefault();
        STATE.view = "table";
        syncControlsFromState();
        pushUrlState();
        break;
      }
      case "c":
      case "C":
        if (STATE.compare.length >= COMPARE_MIN) {
          e.preventDefault();
          openCompareModal();
        }
        break;
      case "g":
      case "G": {
        e.preventDefault();
        const cur = STATE.filters.grade || "";
        const nextIdx = (GRADE_ROTATION.indexOf(cur) + 1) % GRADE_ROTATION.length;
        STATE.filters.grade = GRADE_ROTATION[nextIdx];
        $("f-grade").value = STATE.filters.grade;
        applyFilters();
        const label = STATE.filters.grade || "전체";
        showToast(`등급 필터: ${label}`, null);
        setTimeout(hideToast, 1500);
        break;
      }
    }
  });
}

// ── Theme (light/dark) ─────────────────────────────
const THEME_KEY = "auction:theme:v1";
const THEME_COLORS = { light: "#1f77b4", dark: "#0f141a" };

function effectiveTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)
    ? "dark" : "light";
}
function applyTheme(theme, persist) {
  const root = document.documentElement;
  if (theme === "dark") root.setAttribute("data-theme", "dark");
  else if (theme === "light") root.setAttribute("data-theme", "light");
  else root.removeAttribute("data-theme");
  // 메타 theme-color 동기화 (모바일 브라우저 상단 바 색)
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", THEME_COLORS[theme] || THEME_COLORS.light);
  // 토글 아이콘
  const btn = $("theme-btn");
  if (btn) {
    btn.textContent = theme === "dark" ? "☀️" : "🌙";
    btn.setAttribute("title",
      theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환");
  }
  if (persist) {
    try { localStorage.setItem(THEME_KEY, theme); } catch (_) {}
  }
}

function bindTheme() {
  const initial = effectiveTheme();
  applyTheme(initial, false);
  const btn = $("theme-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      const cur = effectiveTheme();
      applyTheme(cur === "dark" ? "light" : "dark", true);
    });
  }
  // 사용자가 명시 저장하지 않은 경우 OS 변화 추적
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const stored = localStorage.getItem(THEME_KEY);
      if (stored !== "light" && stored !== "dark") {
        applyTheme(mq.matches ? "dark" : "light", false);
      }
    };
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else if (mq.addListener) mq.addListener(handler);
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
  bindTheme();
  bindFilterEvents();
  bindSearch();
  bindAgentSearch();
  bindViewToggle();
  bindDownloads();
  bindModalClose();
  bindCompareTray();
  bindKbdShortcuts();
  bindMoreButton();
  bindPwa();
  load();
});
