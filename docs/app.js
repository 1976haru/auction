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
  { id: "notes",    label: "📝 메모" },
  { id: "viewed",   label: "👁 최근 본" },
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
  // ── 확장 빠른 메뉴 ──
  { id: "fail2",        label: "유찰 2회+" },
  { id: "grade_a",      label: "A등급" },
  { id: "undervalued",  label: "시세 저평가" },
  { id: "multi_house",  label: "연립/다세대" },
  { id: "single_house", label: "단독/다가구" },
  { id: "factory",      label: "공장/창고" },
  { id: "vehicle",      label: "차량" },
  { id: "public_shop",  label: "공매 상가" },
  { id: "auction_apt",  label: "경매 아파트" },
  { id: "land_under",   label: "토지 저평가" },
  { id: "docs_missing", label: "문서 미공개" },
  { id: "field_survey", label: "현장조사 필요" },
  { id: "tenant_warn",  label: "임차인 주의" },
  { id: "lien_warn",    label: "유치권 주의" },
  { id: "share_warn",   label: "지분매각 주의" },
  { id: "farm_warn",    label: "농지 주의" },
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

const SEARCHES_KEY = "auction:searches:v1";
const SEARCHES_MAX = 8;
function loadSearches() {
  try {
    const raw = localStorage.getItem(SEARCHES_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr)
      ? arr.filter((x) => typeof x === "string" && x.trim()).slice(0, SEARCHES_MAX)
      : [];
  } catch { return []; }
}
function saveSearches(arr) {
  try { localStorage.setItem(SEARCHES_KEY, JSON.stringify(arr)); } catch {}
}

const VIEWED_KEY = "auction:viewed:v1";
const VIEWED_MAX = 20;
function loadViewed() {
  try {
    const raw = localStorage.getItem(VIEWED_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((x) => x && (typeof x.id === "string" || typeof x.id === "number"))
      .map((x) => ({ id: String(x.id), ts: Number(x.ts) || 0 }))
      .slice(0, VIEWED_MAX);
  } catch { return []; }
}
function saveViewed(arr) {
  try { localStorage.setItem(VIEWED_KEY, JSON.stringify(arr)); } catch {}
}
function recordViewed(id) {
  const k = String(id);
  const now = Date.now();
  let arr = STATE.viewed.filter((x) => x.id !== k);
  arr.unshift({ id: k, ts: now });
  if (arr.length > VIEWED_MAX) arr.length = VIEWED_MAX;
  STATE.viewed = arr;
  saveViewed(arr);
}

const DENSITY_KEY = "auction:density:v1";

const NOTES_KEY = "auction:notes:v1";
function loadNotes() {
  try {
    const raw = localStorage.getItem(NOTES_KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return (obj && typeof obj === "object" && !Array.isArray(obj)) ? obj : {};
  } catch { return {}; }
}
function saveNotes(obj) {
  try { localStorage.setItem(NOTES_KEY, JSON.stringify(obj)); } catch {}
}
function getNote(id) {
  const k = String(id);
  const n = STATE.notes[k];
  return (n && typeof n.text === "string") ? n : null;
}
function setNote(id, text) {
  const k = String(id);
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    delete STATE.notes[k];
  } else {
    STATE.notes[k] = { text: trimmed, updatedAt: new Date().toISOString() };
  }
  saveNotes(STATE.notes);
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
  recentSearches: loadSearches(),
  notes: loadNotes(),
  viewed: loadViewed(),
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
    // ── 고급 필터 ──
    court: "",        // 법원/기관 (court_name 또는 agency_name)
    sido: "",
    sigungu: "",
    dong: "",
    item_group: "",
    confidence: "",   // high | medium | low | very_low
    document_status: "", // present | missing
    appraisal_min: null,
    appraisal_max: null,
    market_min: null,
    market_max: null,
    profit_min: null,
    profit_max: null,
    roi_min: null,
    roi_max: null,
    bid_date_from: "",
    bid_date_to: "",
    exclude_flags: [],  // 제외할 위험 키워드
    include_flags: [],  // 반드시 포함할 위험 키워드
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
  // ── 고급 필터 동기화 ──
  const setVal = (id, v) => { const n = $(id); if (n) n.value = (v ?? ""); };
  setVal("f-court", f.court);
  setVal("f-group", f.item_group);
  setVal("f-confidence", f.confidence);
  setVal("f-doc", f.document_status);
  setVal("f-appraisal-min", f.appraisal_min);
  setVal("f-appraisal-max", f.appraisal_max);
  setVal("f-market-min", f.market_min);
  setVal("f-market-max", f.market_max);
  setVal("f-profit-min", f.profit_min);
  setVal("f-profit-max", f.profit_max);
  setVal("f-roi-min", f.roi_min);
  setVal("f-roi-max", f.roi_max);
  setVal("f-date-from", f.bid_date_from);
  setVal("f-date-to", f.bid_date_to);
  if (typeof refreshSigunguOptions === "function") { refreshSigunguOptions(); refreshDongOptions(); }
  setVal("f-sido", f.sido);
  setVal("f-sigungu", f.sigungu);
  setVal("f-dong", f.dong);
  const exSet = new Set(f.exclude_flags || []);
  document.querySelectorAll("[data-exclude]").forEach((chk) => { chk.checked = exSet.has(chk.dataset.exclude); });
  const inSet = new Set(f.include_flags || []);
  document.querySelectorAll("[data-include]").forEach((chk) => { chk.checked = inSet.has(chk.dataset.include); });
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
  const before = snapshotFilters();
  const overrides = preset.apply() || {};
  // 기본값으로 리셋 후 프리셋 덮어쓰기 (사용자가 매번 깨끗한 상태에서 시작)
  STATE.filters = JSON.parse(JSON.stringify(FILTER_DEFAULTS));
  // _scoreMin 같은 임시 키도 같이 받도록 머지
  Object.entries(overrides).forEach(([k, v]) => { STATE.filters[k] = v; });
  syncControlsFromState();
  renderQuickChips();
  applyFilters();
  showToast(`프리셋 적용: ${preset.label} — ${preset.note || ""}`, "되돌리기", () => restoreFilters(before));
  setTimeout(hideToast, 4500);
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
    const active = STATE.filters.chip === c.id;
    const btn = document.createElement("button");
    btn.className = "chip" + (active ? " active" : "");
    btn.type = "button";
    btn.dataset.chip = c.id;
    btn.textContent = c.label;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    btn.setAttribute("aria-label", `빠른 메뉴: ${c.label}`);
    btn.title = c.label;
    btn.addEventListener("click", () => {
      STATE.filters.chip = c.id;
      renderQuickChips();
      applyFilters();
    });
    root.appendChild(btn);
  });
}

// ── Filter dropdowns ───────────────────────────────
function _fillSelect(id, values, keep) {
  const sel = $(id);
  if (!sel) return;
  const cur = keep ? sel.value : "";
  // 첫 옵션(전체)만 남기고 비움
  while (sel.options.length > 1) sel.remove(1);
  values.forEach((v) => sel.appendChild(el(`<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`)));
  if (keep && values.includes(cur)) sel.value = cur;
}

function populateFilterOptions() {
  const uniqSorted = (fn) =>
    Array.from(new Set(STATE.items.map(fn).filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b), "ko"));
  _fillSelect("f-region", uniqSorted((it) => it.region));
  _fillSelect("f-type", uniqSorted((it) => it.item_type));
  // 법원/기관: court_name ∪ agency_name
  const courts = Array.from(new Set([
    ...STATE.items.map((it) => it.court_name).filter(Boolean),
    ...STATE.items.map((it) => it.agency_name).filter(Boolean),
  ])).sort((a, b) => String(a).localeCompare(String(b), "ko"));
  _fillSelect("f-court", courts);
  _fillSelect("f-group", uniqSorted((it) => it.item_group));
  _fillSelect("f-sido", uniqSorted((it) => it.sido || it.region));
  refreshSigunguOptions();
  refreshDongOptions();
}

// 시도 선택 시 해당 시군구만, 시군구 선택 시 해당 동만 (cascade)
function refreshSigunguOptions() {
  const f = STATE.filters;
  const vals = Array.from(new Set(STATE.items
    .filter((it) => !f.sido || (it.sido || it.region) === f.sido)
    .map((it) => it.sigungu).filter(Boolean)))
    .sort((a, b) => String(a).localeCompare(String(b), "ko"));
  _fillSelect("f-sigungu", vals, true);
}
function refreshDongOptions() {
  const f = STATE.filters;
  const vals = Array.from(new Set(STATE.items
    .filter((it) => (!f.sido || (it.sido || it.region) === f.sido) && (!f.sigungu || it.sigungu === f.sigungu))
    .map((it) => it.dong).filter(Boolean)))
    .sort((a, b) => String(a).localeCompare(String(b), "ko"));
  _fillSelect("f-dong", vals, true);
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
    // ── 고급 필터 ──
    "f-court":     (v) => STATE.filters.court = v,
    "f-group":     (v) => STATE.filters.item_group = v,
    "f-confidence":(v) => STATE.filters.confidence = v,
    "f-doc":       (v) => STATE.filters.document_status = v,
    "f-appraisal-min": (v) => STATE.filters.appraisal_min = v ? Number(v) : null,
    "f-appraisal-max": (v) => STATE.filters.appraisal_max = v ? Number(v) : null,
    "f-market-min": (v) => STATE.filters.market_min = v ? Number(v) : null,
    "f-market-max": (v) => STATE.filters.market_max = v ? Number(v) : null,
    "f-profit-min": (v) => STATE.filters.profit_min = (v !== "" ? Number(v) : null),
    "f-profit-max": (v) => STATE.filters.profit_max = (v !== "" ? Number(v) : null),
    "f-roi-min":    (v) => STATE.filters.roi_min = (v !== "" ? Number(v) : null),
    "f-roi-max":    (v) => STATE.filters.roi_max = (v !== "" ? Number(v) : null),
    "f-date-from":  (v) => STATE.filters.bid_date_from = v || "",
    "f-date-to":    (v) => STATE.filters.bid_date_to = v || "",
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
  // 지역(시도/시군구/동) cascade
  const sidoSel = $("f-sido");
  if (sidoSel) sidoSel.addEventListener("change", () => {
    STATE.filters.sido = sidoSel.value;
    STATE.filters.sigungu = ""; STATE.filters.dong = "";
    refreshSigunguOptions(); refreshDongOptions();
    applyFilters();
  });
  const sgSel = $("f-sigungu");
  if (sgSel) sgSel.addEventListener("change", () => {
    STATE.filters.sigungu = sgSel.value;
    STATE.filters.dong = "";
    refreshDongOptions();
    applyFilters();
  });
  const dongSel = $("f-dong");
  if (dongSel) dongSel.addEventListener("change", () => {
    STATE.filters.dong = dongSel.value;
    applyFilters();
  });
  // 위험 키워드 포함/제외 체크박스
  document.querySelectorAll("[data-exclude]").forEach((chk) => {
    chk.addEventListener("change", () => {
      const kw = chk.dataset.exclude;
      const set = new Set(STATE.filters.exclude_flags);
      chk.checked ? set.add(kw) : set.delete(kw);
      STATE.filters.exclude_flags = [...set];
      applyFilters();
    });
  });
  document.querySelectorAll("[data-include]").forEach((chk) => {
    chk.addEventListener("change", () => {
      const kw = chk.dataset.include;
      const set = new Set(STATE.filters.include_flags);
      chk.checked ? set.add(kw) : set.delete(kw);
      STATE.filters.include_flags = [...set];
      applyFilters();
    });
  });
  // 고급 필터 펼치기/접기
  const advToggle = $("adv-toggle");
  if (advToggle) advToggle.addEventListener("click", () => {
    const body = $("adv-filter-body");
    const hidden = body.hasAttribute("hidden");
    if (hidden) { body.removeAttribute("hidden"); advToggle.textContent = "－ 고급 필터 접기"; advToggle.setAttribute("aria-expanded", "true"); }
    else { body.setAttribute("hidden", ""); advToggle.textContent = "＋ 고급 필터"; advToggle.setAttribute("aria-expanded", "false"); }
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

function snapshotFilters() {
  return JSON.parse(JSON.stringify(STATE.filters));
}
function restoreFilters(snap) {
  if (!snap) return;
  STATE.filters = JSON.parse(JSON.stringify(snap));
  syncControlsFromState();
  renderQuickChips();
  applyFilters();
  hideAgentResult();
}

function resetFilters() {
  const before = snapshotFilters();
  STATE.filters = JSON.parse(JSON.stringify(FILTER_DEFAULTS));
  syncControlsFromState();
  renderQuickChips();
  applyFilters();
  hideAgentResult();
  // 의미 있는 변경이 있었던 경우에만 되돌리기 제안
  if (JSON.stringify(before) !== JSON.stringify(STATE.filters)) {
    showToast("필터를 초기화했어요.", "되돌리기", () => restoreFilters(before));
    setTimeout(hideToast, 5000);
  }
}

// ── Filter application ─────────────────────────────
function chipMatch(chip, it) {
  switch (chip) {
    case "all":       return true;
    case "favorites": return STATE.favorites.has(String(it.id));
    case "notes":     return !!getNote(it.id);
    case "viewed":    return STATE.viewed.some((v) => v.id === String(it.id));
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
    // ── 확장 빠른 메뉴 ──
    case "fail2":        return (it.fail_count || 0) >= 2;
    case "grade_a":      return it.recommendation_grade === "A";
    case "undervalued":  return _mtmRatio(it) !== null && _mtmRatio(it) <= 85;
    case "multi_house":  return ["연립", "다세대", "빌라"].some((t) => (it.item_type || "").includes(t));
    case "single_house": return ["단독", "다가구"].some((t) => (it.item_type || "").includes(t));
    case "factory":      return ["공장", "창고"].some((t) => (it.item_type || "").includes(t));
    case "vehicle":      return (it.item_type || "").includes("차량");
    case "public_shop":  return it.source === "public_sale" && (it.item_type || "").includes("상가");
    case "auction_apt":  return it.source === "auction" && (it.item_type || "").includes("아파트");
    case "land_under":   return _isLand(it) && _mtmRatio(it) !== null && _mtmRatio(it) <= 85;
    case "docs_missing": return it.documents_missing === true
                                || /미공개/.test(it.document_status || "");
    case "field_survey": return (it.field_survey_needed !== undefined)
                                ? it.field_survey_needed === true
                                : _hasText([...(it.next_actions || []), ...(it.checklist || [])], "현장");
    case "tenant_warn":  return _hasRiskKeyword(it, "임차");
    case "lien_warn":    return _hasRiskKeyword(it, "유치권");
    case "share_warn":   return _hasRiskKeyword(it, "지분");
    case "farm_warn":    return _hasRiskKeyword(it, "농지");
    default: return true;
  }
}

// 빠른 메뉴 보조 함수
function _mtmRatio(it) {
  if (it.minimum_to_market_ratio !== null && it.minimum_to_market_ratio !== undefined)
    return it.minimum_to_market_ratio;
  if (it.market_price) return (it.min_bid_price / it.market_price) * 100;
  return null;
}
function _isLand(it) {
  if ((it.item_group || "").includes("토지")) return true;
  return ["토지", "전", "답", "임야"].some((t) => (it.item_type || "").includes(t));
}
function _riskKeywords(it) {
  const a = (it.risk_keywords && it.risk_keywords.length)
    ? it.risk_keywords
    : (it.risk_flags || []).map((f) => f && f.keyword);
  return a.filter(Boolean);
}
function _hasRiskKeyword(it, sub) {
  return _riskKeywords(it).some((k) => String(k).includes(sub));
}
function _hasText(arr, sub) {
  return (arr || []).some((s) => String(s || "").includes(sub));
}
// 수익률 안전 변환: 0.12(분수) / 12(퍼센트) 혼용 → 퍼센트로 통일
function _roiPct(v) {
  if (v === null || v === undefined || isNaN(v)) return 0;
  const n = Number(v);
  return (Math.abs(n) > 0 && Math.abs(n) < 1) ? n * 100 : n;
}
// 신뢰도 점수(0~1) → 구간
function _confBand(score) {
  const s = Number(score);
  if (isNaN(s)) return "";
  if (s >= 0.8) return "high";
  if (s >= 0.6) return "medium";
  if (s >= 0.4) return "low";
  return "very_low";
}
// 문서 미공개 여부 (documents_missing / document_status / documents 배열 함께 확인)
function _docsMissing(it) {
  if (it.documents_missing === true) return true;
  if (/미공개/.test(it.document_status || "")) return true;
  if (Array.isArray(it.documents) && it.documents.length === 0) return true;
  return false;
}
// 입찰기일 시작일 (bid_date "YYYY-MM-DD~YYYY-MM-DD" 또는 단일) → "YYYY-MM-DD"
function _bidStart(it) {
  const s = String(it.bid_date || "").split("~")[0].trim();
  return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : "";
}

// 통합검색 대상 텍스트 — 주소/사건번호/관리번호/법원·기관명/지역/물건종류/위험키워드/추천이유까지
function searchableText(it) {
  if (!it) return "";
  const riskKw = (it.risk_keywords && it.risk_keywords.length)
    ? it.risk_keywords
    : (it.risk_flags || []).map((f) => f && (f.keyword || f.description));
  return [
    it.title, it.address, it.region, it.sido, it.sigungu, it.dong,
    it.case_no, it.item_no, it.mgmt_no,
    it.court_name, it.court_region, it.agency_name, it.source_site, it.sale_type,
    it.item_type, it.item_group, it.risk_level,
    ...(riskKw || []),
    it.recommendation_reason, it.caution_reason, it.agent_opinion, it.document_status,
    ...(it.warnings || []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function passQuery(q, it) {
  if (!q) return true;
  // 공백 구분 다중 토큰 — 모든 토큰이 포함돼야 매칭 (AND)
  const tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const hay = searchableText(it);
  return tokens.every((t) => hay.includes(t));
}

function _is_beginner_friendly(it) {
  if (!it) return false;
  if (it.risk_level === "high") return false;
  if ((it.confidence_score || 0) < 0.6) return false;
  const grade = it.recommendation_grade || "C";
  if (!["A", "B"].includes(grade)) return false;
  const itype = it.item_type || "";
  if (!["아파트", "오피스텔", "주택", "빌라"].includes(itype)) return false;
  const forbidden = ["유치권", "법정지상권", "지분매각", "농지취득자격증명", "분묘기지권"];
  for (const flag of (it.risk_flags || [])) {
    if (forbidden.includes(flag.keyword)) return false;
  }
  return true;
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

  // ── 고급 필터 ──
  if (f.court) out = out.filter((it) =>
    it.court_name === f.court || it.agency_name === f.court ||
    it.court_region === f.court || it.source_site === f.court);
  if (f.sido)    out = out.filter((it) => (it.sido || it.region || "") === f.sido);
  if (f.sigungu) out = out.filter((it) => (it.sigungu || "") === f.sigungu);
  if (f.dong)    out = out.filter((it) => (it.dong || "") === f.dong);
  if (f.item_group) out = out.filter((it) => (it.item_group || "") === f.item_group);
  if (f.confidence) out = out.filter((it) => _confBand(it.confidence_score) === f.confidence);
  if (f.document_status === "missing") out = out.filter((it) => _docsMissing(it));
  if (f.document_status === "present") out = out.filter((it) => !_docsMissing(it));
  if (f.appraisal_min !== null) out = out.filter((it) => (it.appraisal_price || 0) >= f.appraisal_min);
  if (f.appraisal_max !== null) out = out.filter((it) => (it.appraisal_price || 0) <= f.appraisal_max);
  if (f.market_min !== null) out = out.filter((it) => (it.market_price || 0) >= f.market_min);
  if (f.market_max !== null) out = out.filter((it) => (it.market_price || 0) <= f.market_max);
  if (f.profit_min !== null) out = out.filter((it) => (it.expected_profit || 0) >= f.profit_min);
  if (f.profit_max !== null) out = out.filter((it) => (it.expected_profit || 0) <= f.profit_max);
  if (f.roi_min !== null) out = out.filter((it) => _roiPct(it.expected_profit_rate) >= f.roi_min);
  if (f.roi_max !== null) out = out.filter((it) => _roiPct(it.expected_profit_rate) <= f.roi_max);
  if (f.bid_date_from) out = out.filter((it) => _bidStart(it) && _bidStart(it) >= f.bid_date_from);
  if (f.bid_date_to)   out = out.filter((it) => _bidStart(it) && _bidStart(it) <= f.bid_date_to);
  if (f.exclude_flags && f.exclude_flags.length)
    out = out.filter((it) => !f.exclude_flags.some((kw) => _hasRiskKeyword(it, kw)));
  if (f.include_flags && f.include_flags.length)
    out = out.filter((it) => f.include_flags.every((kw) => _hasRiskKeyword(it, kw)));

  // 초보자 모드: 고위험, 복잡한 물건 제외
  if (BEGINNER_MODE_ENABLED) {
    out = out.filter((it) => {
      if (it.risk_level === "high") return false;  // 고위험 제외
      if ((it.confidence_score || 0) < 0.6) return false;  // 신뢰도 낮음 제외
      const grade = it.recommendation_grade || "C";
      if (!["A", "B"].includes(grade)) return false;  // A/B 등급만
      const itype = it.item_type || "";
      if (!["아파트", "오피스텔", "주택", "빌라"].includes(itype)) return false;  // 주거용만
      const forbidden = ["유치권", "법정지상권", "지분매각", "농지취득자격증명", "분묘기지권"];
      for (const flag of (it.risk_flags || [])) {
        if (forbidden.includes(flag.keyword)) return false;
      }
      return true;
    });
  }

  // '최근 본' 칩일 땐 본 순서대로 정렬을 강제 (사용자가 명시 정렬을 바꾸면 그대로 따름)
  if (f.chip === "viewed" && f.sort === "score_desc") {
    const order = new Map(STATE.viewed.map((v, i) => [v.id, i]));
    out = out.slice().sort((a, b) => {
      const ai = order.has(String(a.id)) ? order.get(String(a.id)) : Infinity;
      const bi = order.has(String(b.id)) ? order.get(String(b.id)) : Infinity;
      return ai - bi;
    });
  } else {
    out = sortItems(out, f.sort);
  }

  // 기본 보기(전체 칩 + 키워드 필터 없음)에서는 ★ 관심 매물을 맨 위로
  // — JS Array.sort 는 안정 정렬이라 내부 순서는 직전 sortItems 결과 유지
  if (f.chip === "all" && !f.flag && STATE.favorites.size > 0) {
    out = out.slice().sort((a, b) => {
      const af = STATE.favorites.has(String(a.id)) ? 0 : 1;
      const bf = STATE.favorites.has(String(b.id)) ? 0 : 1;
      return af - bf;
    });
  }
  STATE.filtered = out;
  STATE.pageShown = PAGE_SIZE;  // 필터/검색 바뀌면 항상 처음부터
  resetCardFocus();             // 키보드 카드 포커스도 초기화
  renderItems();
  renderItemsHead();
  renderAppliedFilters();
  renderCharts();
  renderPersonalRecs();
  pushUrlState();
}

function renderItemsHead() {
  const f = STATE.filters;
  const root = $("items-count");
  const sortLabel = SORT_LABEL[f.sort] || SORT_LABEL.score_desc;
  let chips = `<span class="meta-chip">정렬 · ${escapeHtml(sortLabel)}</span>`;
  if (f.q) {
    chips += ` <span class="meta-chip meta-chip-q" data-clear-q="1">검색어 · "${escapeHtml(f.q)}" <b>×</b></span>`;
  }
  if (f.flag) {
    chips += ` <span class="meta-chip meta-chip-warn" data-clear-flag="1">키워드 · ${escapeHtml(f.flag)} <b>×</b></span>`;
  }
  if (f.chip && f.chip !== "all") {
    const cf = QUICK_CHIPS.find((c) => c.id === f.chip);
    if (cf) chips += ` <span class="meta-chip">${escapeHtml(cf.label)}</span>`;
  }
  const shown = Math.min(STATE.pageShown, STATE.filtered.length);
  const showCount = (shown < STATE.filtered.length)
    ? `전체 ${STATE.items.length}건 중 ${STATE.filtered.length}건 (현재 ${shown}건 표시)`
    : `전체 ${STATE.items.length}건 중 ${STATE.filtered.length}건 표시`;
  const hint = f.q
    ? `<span class="search-target-hint caption">주소·사건번호·관리번호·법원/기관명·지역·물건종류·위험키워드·추천이유에서 검색</span>`
    : "";
  root.innerHTML = `${showCount} ${chips} ${hint}`;
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
  const clearQ = root.querySelector('[data-clear-q="1"]');
  if (clearQ) {
    clearQ.style.cursor = "pointer";
    clearQ.addEventListener("click", () => {
      STATE.filters.q = "";
      const qi = $("q-input"); if (qi) qi.value = "";
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
    const begLabel = BEGINNER_GRADE_LABEL[grade] || "";
    const begPill = (itFull && itFull.beginner_friendly)
      ? `<span class="beginner-pill ok">🎓 ${escapeHtml(begLabel)}</span>`
      : (begLabel ? `<span class="beginner-pill">🎓 ${escapeHtml(begLabel)}</span>` : "");
    const easyProfit = (itFull && itFull.simple_profit_summary)
      ? `<div class="rec-easy">💰 ${escapeHtml(itFull.simple_profit_summary)}</div>` : "";
    const easyRisk = (itFull && itFull.simple_risk_summary)
      ? `<div class="rec-easy">⚠ 조심할 점: ${escapeHtml(itFull.simple_risk_summary)}</div>` : "";
    const card = el(
      `<article class="rec-card" data-item-id="${r.item_id || ""}">
         <div class="rec-head">
           <span class="rec-rank">#${escapeHtml(String(r.rank || ""))}</span>
           <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
           <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
           <span class="source-pill">${escapeHtml(SOURCE_LABEL[r.source] || r.source || "")}</span>
           ${begPill}
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
         ${easyProfit}
         ${easyRisk}
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
function priceTrendBadge(it) {
  const trend = it && it.price_trend;
  if (!Array.isArray(trend) || trend.length < 4) return "";
  const N = Math.min(3, Math.floor(trend.length / 2));
  const head = trend.slice(0, N);
  const tail = trend.slice(-N);
  const headAvg = head.reduce((a, b) => a + (b.avg_price || 0), 0) / N;
  const tailAvg = tail.reduce((a, b) => a + (b.avg_price || 0), 0) / N;
  if (!headAvg) return "";
  const ratio = tailAvg / headAvg;
  let icon, cls, label;
  if (ratio >= 1.05)      { icon = "↑↑"; cls = "trend-up-strong"; label = "강한 상승"; }
  else if (ratio >= 1.02) { icon = "↑";  cls = "trend-up";        label = "완만한 상승"; }
  else if (ratio >= 0.98) { icon = "→";  cls = "trend-flat";      label = "거의 평탄"; }
  else if (ratio >= 0.95) { icon = "↓";  cls = "trend-down";      label = "완만한 하락"; }
  else                    { icon = "↓↓"; cls = "trend-down-strong"; label = "강한 하락"; }
  const pct = ((ratio - 1) * 100);
  const pctStr = (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";
  return `<span class="trend-badge ${cls}" title="시세 트렌드: ${label} (${pctStr}, ${trend.length}개월)">${icon}</span>`;
}

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
function noteBadgeHtml(it) {
  const n = getNote(it.id);
  if (!n) return "";
  const preview = (n.text || "").replace(/\s+/g, " ").slice(0, 40);
  return `<span class="note-badge" title="메모: ${escapeHtml(preview)}">📝</span>`;
}
function itemCardHtml(it) {
  const grade = it.recommendation_grade || "C";
  const risk = it.risk_level || "medium";
  const due = (it.days_left !== null && it.days_left !== undefined && it.days_left >= 0)
    ? `D-${it.days_left}`
    : (it.bid_date ? "기일 " + (it.bid_date.split("~")[0] || it.bid_date) : "기일 미정");
  return `
    <article class="item-card" data-item-id="${it.id}" data-grade="${escapeHtml(grade)}" data-risk="${escapeHtml(risk)}" tabindex="0" role="button" aria-label="물건 상세 보기">
      <div class="item-head">
        <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
        <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
        <span class="source-pill">${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</span>
        ${urgencyBadge(it)}
        <span class="caption">${escapeHtml(it.item_type || "")}</span>
        ${changeBadgesHtml(it)}
        ${noteBadgeHtml(it)}
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
        ${priceTrendBadge(it)}
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
    cardRoot.appendChild(buildZeroState());
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
    if (SELECTED.has(String(it.id))) card.classList.add("selected");
    bindTap(card, () => {
      if (SELECTING) toggleSelected(it.id);
      else openDetailById(it.id);
    }, {
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

function _activeFilterChips() {
  const f = STATE.filters;
  const chips = [];
  if (f.q) chips.push({ key: "q", label: `검색 "${f.q}"`, clear: () => { STATE.filters.q = ""; $("q-input").value = ""; } });
  if (f.chip && f.chip !== "all") {
    const c = QUICK_CHIPS.find((x) => x.id === f.chip);
    if (c) chips.push({ key: "chip", label: c.label, clear: () => { STATE.filters.chip = "all"; renderQuickChips(); } });
  }
  if (f.region) chips.push({ key: "region", label: `지역 ${f.region}`, clear: () => { STATE.filters.region = ""; $("f-region").value = ""; } });
  if (f.item_type) chips.push({ key: "item_type", label: f.item_type, clear: () => { STATE.filters.item_type = ""; $("f-type").value = ""; } });
  if (f.source) chips.push({ key: "source", label: SOURCE_LABEL[f.source] || f.source, clear: () => { STATE.filters.source = ""; $("f-source").value = ""; } });
  if (f.grade) chips.push({ key: "grade", label: `${f.grade} 등급`, clear: () => { STATE.filters.grade = ""; $("f-grade").value = ""; } });
  if (f.risk) chips.push({ key: "risk", label: `위험 ${RISK_LABEL[f.risk] || f.risk}`, clear: () => { STATE.filters.risk = ""; $("f-risk").value = ""; } });
  if (f.fail_min !== null && f.fail_min !== undefined) chips.push({ key: "fail_min", label: `유찰 ${f.fail_min}+`, clear: () => { STATE.filters.fail_min = null; $("f-fail").value = ""; } });
  if (f.due_max !== null && f.due_max !== undefined) chips.push({ key: "due_max", label: `D-${f.due_max} 이내`, clear: () => { STATE.filters.due_max = null; $("f-due").value = ""; } });
  if (f.price_min !== null && f.price_min !== undefined) chips.push({ key: "price_min", label: `최저가 ${f.price_min.toLocaleString("ko-KR")}만↑`, clear: () => { STATE.filters.price_min = null; $("f-price-min").value = ""; } });
  if (f.price_max !== null && f.price_max !== undefined) chips.push({ key: "price_max", label: `최저가 ${f.price_max.toLocaleString("ko-KR")}만↓`, clear: () => { STATE.filters.price_max = null; $("f-price-max").value = ""; } });
  if (f.flag) chips.push({ key: "flag", label: `키워드 ${f.flag}`, clear: () => { STATE.filters.flag = ""; } });
  if (f._scoreMin !== undefined && f._scoreMin !== null) chips.push({ key: "_scoreMin", label: `점수 ${f._scoreMin}+`, clear: () => { delete STATE.filters._scoreMin; } });
  // ── 고급 필터 칩 ──
  if (f.court) chips.push({ key: "court", label: `법원/기관 ${f.court}`, clear: () => { STATE.filters.court = ""; const n = $("f-court"); if (n) n.value = ""; } });
  if (f.sido) chips.push({ key: "sido", label: `시도 ${f.sido}`, clear: () => { STATE.filters.sido = ""; STATE.filters.sigungu = ""; STATE.filters.dong = ""; refreshSigunguOptions(); refreshDongOptions(); const n = $("f-sido"); if (n) n.value = ""; } });
  if (f.sigungu) chips.push({ key: "sigungu", label: `시군구 ${f.sigungu}`, clear: () => { STATE.filters.sigungu = ""; STATE.filters.dong = ""; refreshDongOptions(); const n = $("f-sigungu"); if (n) n.value = ""; } });
  if (f.dong) chips.push({ key: "dong", label: `동 ${f.dong}`, clear: () => { STATE.filters.dong = ""; const n = $("f-dong"); if (n) n.value = ""; } });
  if (f.item_group) chips.push({ key: "item_group", label: `그룹 ${f.item_group}`, clear: () => { STATE.filters.item_group = ""; const n = $("f-group"); if (n) n.value = ""; } });
  if (f.confidence) chips.push({ key: "confidence", label: `신뢰도 ${f.confidence}`, clear: () => { STATE.filters.confidence = ""; const n = $("f-confidence"); if (n) n.value = ""; } });
  if (f.document_status) chips.push({ key: "document_status", label: f.document_status === "missing" ? "문서 미공개" : "문서 있음", clear: () => { STATE.filters.document_status = ""; const n = $("f-doc"); if (n) n.value = ""; } });
  if (f.appraisal_min !== null) chips.push({ key: "appraisal_min", label: `감정가 ${f.appraisal_min.toLocaleString("ko-KR")}만↑`, clear: () => { STATE.filters.appraisal_min = null; const n = $("f-appraisal-min"); if (n) n.value = ""; } });
  if (f.appraisal_max !== null) chips.push({ key: "appraisal_max", label: `감정가 ${f.appraisal_max.toLocaleString("ko-KR")}만↓`, clear: () => { STATE.filters.appraisal_max = null; const n = $("f-appraisal-max"); if (n) n.value = ""; } });
  if (f.market_min !== null) chips.push({ key: "market_min", label: `시세 ${f.market_min.toLocaleString("ko-KR")}만↑`, clear: () => { STATE.filters.market_min = null; const n = $("f-market-min"); if (n) n.value = ""; } });
  if (f.market_max !== null) chips.push({ key: "market_max", label: `시세 ${f.market_max.toLocaleString("ko-KR")}만↓`, clear: () => { STATE.filters.market_max = null; const n = $("f-market-max"); if (n) n.value = ""; } });
  if (f.profit_min !== null) chips.push({ key: "profit_min", label: `차익 ${f.profit_min.toLocaleString("ko-KR")}만↑`, clear: () => { STATE.filters.profit_min = null; const n = $("f-profit-min"); if (n) n.value = ""; } });
  if (f.profit_max !== null) chips.push({ key: "profit_max", label: `차익 ${f.profit_max.toLocaleString("ko-KR")}만↓`, clear: () => { STATE.filters.profit_max = null; const n = $("f-profit-max"); if (n) n.value = ""; } });
  if (f.roi_min !== null) chips.push({ key: "roi_min", label: `수익률 ${f.roi_min}%↑`, clear: () => { STATE.filters.roi_min = null; const n = $("f-roi-min"); if (n) n.value = ""; } });
  if (f.roi_max !== null) chips.push({ key: "roi_max", label: `수익률 ${f.roi_max}%↓`, clear: () => { STATE.filters.roi_max = null; const n = $("f-roi-max"); if (n) n.value = ""; } });
  if (f.bid_date_from) chips.push({ key: "bid_date_from", label: `기일 ${f.bid_date_from}~`, clear: () => { STATE.filters.bid_date_from = ""; const n = $("f-date-from"); if (n) n.value = ""; } });
  if (f.bid_date_to) chips.push({ key: "bid_date_to", label: `기일 ~${f.bid_date_to}`, clear: () => { STATE.filters.bid_date_to = ""; const n = $("f-date-to"); if (n) n.value = ""; } });
  (f.exclude_flags || []).forEach((kw) => chips.push({ key: `ex_${kw}`, label: `${kw} 제외`, clear: () => { STATE.filters.exclude_flags = STATE.filters.exclude_flags.filter((x) => x !== kw); const c = document.querySelector(`[data-exclude="${kw}"]`); if (c) c.checked = false; } }));
  (f.include_flags || []).forEach((kw) => chips.push({ key: `in_${kw}`, label: `${kw} 포함`, clear: () => { STATE.filters.include_flags = STATE.filters.include_flags.filter((x) => x !== kw); const c = document.querySelector(`[data-include="${kw}"]`); if (c) c.checked = false; } }));
  return chips;
}

// 현재 적용 필터 칩을 필터 영역 하단에 항상 표시 (개별 × 제거 가능)
function renderAppliedFilters() {
  const root = $("applied-filters");
  if (!root) return;
  const chips = _activeFilterChips();
  clearChildren(root);
  if (!chips.length) { root.hidden = true; return; }
  root.hidden = false;
  root.appendChild(el(`<span class="applied-label">적용 필터</span>`));
  chips.forEach((c) => {
    const b = el(`<button class="applied-chip" type="button">${escapeHtml(c.label)} <span class="x">×</span></button>`);
    b.addEventListener("click", () => { c.clear(); applyFilters(); });
    root.appendChild(b);
  });
  const clearAll = el(`<button class="applied-clear" type="button">전체 해제</button>`);
  clearAll.addEventListener("click", resetFilters);
  root.appendChild(clearAll);
}

function buildZeroState() {
  const wrap = document.createElement("div");
  wrap.className = "zero-state";
  const chips = _activeFilterChips();
  let chipsHtml = "";
  const qNote = STATE.filters.q
    ? `<p class="zero-msg">검색어 <b>"${escapeHtml(STATE.filters.q)}"</b> 와 일치하는 물건이 없어요. 검색어를 줄이거나 필터를 초기화해 보세요.</p>`
    : "";
  if (chips.length) {
    chipsHtml = `
      ${qNote}
      <p class="zero-msg">아래 조건이 적용돼 있어요. 칩의 ×로 하나씩 풀거나 한 번에 초기화해 보세요.</p>
      <div class="zero-chips">
        ${chips.map((c, i) =>
          `<button class="zero-chip" data-zero-idx="${i}" type="button">${escapeHtml(c.label)} <span class="x">×</span></button>`
        ).join("")}
      </div>
    `;
  } else {
    chipsHtml = `<p class="zero-msg">표시할 매물이 없어요. 데이터가 비어 있을 수 있습니다.</p>`;
  }
  wrap.innerHTML = `
    <div class="zero-icon" aria-hidden="true">🔎</div>
    <h3 class="zero-title">조건에 맞는 매물이 없어요</h3>
    ${chipsHtml}
    <div class="zero-actions">
      <button class="btn btn-primary" type="button" data-zero-action="reset">필터 초기화</button>
      ${STATE.filters.q ? `<button class="btn btn-ghost" type="button" data-zero-action="clear-q">검색어만 지우기</button>` : ""}
    </div>
  `;
  // 이벤트 — 클로저로 chips 캡처
  wrap.querySelectorAll(".zero-chip").forEach((btn) => {
    const idx = Number(btn.dataset.zeroIdx);
    btn.addEventListener("click", () => {
      const c = chips[idx];
      if (c && c.clear) {
        c.clear();
        applyFilters();
      }
    });
  });
  wrap.querySelector('[data-zero-action="reset"]').addEventListener("click", resetFilters);
  const clearQ = wrap.querySelector('[data-zero-action="clear-q"]');
  if (clearQ) clearQ.addEventListener("click", () => {
    STATE.filters.q = "";
    $("q-input").value = "";
    applyFilters();
  });
  return wrap;
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
  // 모든 fav-btn 시각 갱신
  document.querySelectorAll(`[data-fav="${key}"]`).forEach((btn) => {
    const on = STATE.favorites.has(key);
    btn.classList.toggle("on", on);
    btn.textContent = on ? "★" : "☆";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  // 칩이 'favorites' 면 목록 자체에서 빠지거나 들어오므로 재필터,
  // 'all' + 키워드 필터 없음(=즐겨찾기 우선 모드)이면 매물 순서가 바뀌므로 재필터
  const f = STATE.filters;
  if (f.chip === "favorites" || (f.chip === "all" && !f.flag)) {
    applyFilters();
  }
  refreshUrgentBanner();
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

function _sortedCompareItems(items, mode) {
  if (!mode) return items.slice();
  const RISK_RANK = { low: 0, medium: 1, high: 2 };
  const GRADE_RANK = { A: 4, B: 3, C: 2, D: 1, X: 0 };
  const cmp = {
    grade:    (a, b) => (GRADE_RANK[b.recommendation_grade] ?? -1) - (GRADE_RANK[a.recommendation_grade] ?? -1),
    score:    (a, b) => (b.recommendation_score || 0) - (a.recommendation_score || 0),
    profit:   (a, b) => (b.expected_profit || 0) - (a.expected_profit || 0),
    roi:      (a, b) => (b.expected_profit_rate || 0) - (a.expected_profit_rate || 0),
    price_asc:(a, b) => (a.min_bid_price || 0) - (b.min_bid_price || 0),
    risk_asc: (a, b) => (RISK_RANK[a.risk_level] ?? 1) - (RISK_RANK[b.risk_level] ?? 1),
  }[mode];
  return cmp ? items.slice().sort(cmp) : items.slice();
}

function _renderCompareWithSort() {
  const ids = STATE.compare.slice();
  const items = ids
    .map((id) => STATE.items.find((x) => String(x.id) === id))
    .filter(Boolean);
  if (items.length < COMPARE_MIN) return;
  const sortSel = $("compare-sort");
  const mode = sortSel ? sortSel.value : "";
  const sorted = _sortedCompareItems(items, mode);
  $("compare-title").textContent = `물건 비교 (${items.length}건)`;
  $("compare-body").innerHTML = renderCompareTable(sorted);
}

function openCompareModal() {
  const ids = STATE.compare.slice();
  if (ids.length < COMPARE_MIN) return;
  const items = ids
    .map((id) => STATE.items.find((x) => String(x.id) === id))
    .filter(Boolean);
  if (items.length < COMPARE_MIN) return;

  // 정렬 select 초기화 (모달 처음 열 때 '담은 순서')
  const sortSel = $("compare-sort");
  if (sortSel && !sortSel.dataset.bound) {
    sortSel.value = "";
    sortSel.addEventListener("change", _renderCompareWithSort);
    sortSel.dataset.bound = "1";
  }

  _renderCompareWithSort();
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

function renderPriceHistogramChart(items) {
  const host = $("chart-price-hist");
  if (!host) return;
  host.innerHTML = "";
  const prices = items.map((it) => it.min_bid_price || 0).filter((p) => p > 0);
  if (!prices.length) {
    host.appendChild(el(`<p class="chart-empty">가격 데이터가 없습니다.</p>`));
    return;
  }
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const N = 10;
  const span = Math.max(1, maxP - minP);
  const binSize = span / N;
  const bins = new Array(N).fill(0);
  for (const p of prices) {
    const idx = Math.min(N - 1, Math.floor((p - minP) / binSize));
    bins[idx]++;
  }
  const maxCount = Math.max(...bins);

  const W = 360, H = 180;
  const padL = 30, padR = 10, padT = 14, padB = 30;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const barW = innerW / N;

  const svg = svgEl("svg", {
    viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "최저가 분포",
  });
  svgEl("line", {
    x1: padL, y1: H - padB, x2: W - padR, y2: H - padB, class: "axis-line",
  }, svg);

  bins.forEach((count, i) => {
    if (count === 0) return;
    const h = (count / maxCount) * innerH;
    const x = padL + i * barW + barW * 0.1;
    const y = H - padB - h;
    const w = barW * 0.8;
    const rect = svgEl("rect", {
      x, y, width: w, height: Math.max(1, h),
      fill: "#1f77b4", rx: 2, ry: 2,
    }, svg);
    const binMin = minP + i * binSize;
    const binMax = minP + (i + 1) * binSize;
    rect.appendChild(svgEl("title", {}));
    rect.lastChild.textContent =
      `${Math.round(binMin).toLocaleString("ko-KR")}~${Math.round(binMax).toLocaleString("ko-KR")}만원 · ${count}건`;
    if (count >= Math.max(1, maxCount * 0.55)) {
      svgEl("text", {
        x: x + w / 2, y: y - 3, "text-anchor": "middle", class: "bar-label",
      }, svg).textContent = String(count);
    }
  });

  // x축 라벨 (시작/중간/끝, 만원 단위)
  [0, Math.floor(N / 2), N - 1].forEach((i) => {
    const v = minP + (i + 0.5) * binSize;
    const x = padL + (i + 0.5) * barW;
    svgEl("text", {
      x, y: H - padB + 14, "text-anchor": "middle", class: "axis-label",
    }, svg).textContent = Math.round(v).toLocaleString("ko-KR");
  });
  // y축 max
  svgEl("text", {
    x: padL - 4, y: padT + 9, "text-anchor": "end", class: "axis-label",
  }, svg).textContent = String(maxCount);

  host.appendChild(svg);
}

function renderCharts() {
  const items = STATE.filtered;
  renderGradeProfitChart(items);
  renderRegionRiskChart(items);
  renderPriceHistogramChart(items);
  const cap = $("charts-caption");
  if (cap) cap.textContent = `현재 필터 결과 ${items.length}건 기준`;
}

/* ─── 사용자 피드백 기반 맞춤 추천 ──────────────────────────── */
const PERSONAL_MIN_SIGNALS = 3;

function _signalItems() {
  // ★ + 📝 + 👁 합집합. 가중치 (★=3, 📝=3, 👁=1)
  const weights = new Map();
  STATE.favorites.forEach((id) => weights.set(String(id), (weights.get(String(id)) || 0) + 3));
  Object.keys(STATE.notes).forEach((id) => weights.set(String(id), (weights.get(String(id)) || 0) + 3));
  STATE.viewed.forEach((v) => weights.set(String(v.id), (weights.get(String(v.id)) || 0) + 1));
  // STATE.items 와 매칭되는 것만
  const out = [];
  for (const [id, w] of weights) {
    const it = STATE.items.find((x) => String(x.id) === id);
    if (it) out.push({ item: it, weight: w });
  }
  return out;
}

function buildUserProfile() {
  const signals = _signalItems();
  if (signals.length < PERSONAL_MIN_SIGNALS) return null;
  const counts = (key) => {
    const m = new Map();
    for (const { item, weight } of signals) {
      const k = item[key];
      if (!k) continue;
      m.set(k, (m.get(k) || 0) + weight);
    }
    return m;
  };
  const top = (m) => {
    let bestK = null, bestV = -1;
    for (const [k, v] of m) if (v > bestV) { bestK = k; bestV = v; }
    return bestK;
  };

  const regions = counts("region");
  const types = counts("item_type");
  const sources = counts("source");
  const grades = counts("recommendation_grade");
  const risks = counts("risk_level");

  let totalW = 0, totalPrice = 0;
  for (const { item, weight } of signals) {
    if (item.min_bid_price) {
      totalPrice += item.min_bid_price * weight;
      totalW += weight;
    }
  }
  const avgPrice = totalW > 0 ? totalPrice / totalW : null;

  return {
    signalCount: signals.length,
    signalIds: new Set(signals.map((s) => String(s.item.id))),
    topRegion: top(regions),
    topType: top(types),
    topSource: top(sources),
    topGrade: top(grades),
    topRisk: top(risks),
    avgPrice,
    distRegion: regions,
    distType: types,
  };
}

function scoreAgainstProfile(it, profile) {
  let score = 0;
  const reasons = [];
  if (profile.topRegion && it.region === profile.topRegion) {
    score += 30; reasons.push(`선호 지역 ${profile.topRegion}`);
  }
  if (profile.topType && it.item_type === profile.topType) {
    score += 25; reasons.push(`선호 종류 ${profile.topType}`);
  }
  if (profile.topSource && it.source === profile.topSource) {
    score += 8;
  }
  if (profile.avgPrice && it.min_bid_price) {
    const ratio = it.min_bid_price / profile.avgPrice;
    if (ratio >= 0.8 && ratio <= 1.2) {
      score += 15; reasons.push("비슷한 가격대");
    } else if (ratio >= 0.6 && ratio <= 1.4) {
      score += 7;
    }
  }
  if (it.recommendation_grade === "A") { score += 10; reasons.push("A등급"); }
  else if (it.recommendation_grade === "B") { score += 6; }
  if (profile.topRisk && it.risk_level === profile.topRisk) {
    score += 6;
  }
  return { score, reasons };
}

/* 동·구 클러스터: 같은 위치(시/도 + 구 + 동)에 2건 이상 모인 곳 top 5 */
function _parseLocation(address) {
  if (!address) return null;
  const tokens = address.split(/\s+/);
  let region = null, gu = null, dong = null;
  for (const t of tokens) {
    if (!region && /(특별시|광역시|특별자치시|특별자치도|도|시)$/.test(t)) {
      region = t;
    } else if (!gu && /(시|군|구)$/.test(t)) {
      gu = t;
    } else if (!dong && /(동|읍|면|가|리)$/.test(t)) {
      dong = t;
    }
  }
  if (!region || !dong) return null;
  return { region, gu, dong, key: [region, gu, dong].filter(Boolean).join(" ") };
}

function buildClusters(items) {
  const map = new Map();
  for (const it of items) {
    const loc = _parseLocation(it.address);
    if (!loc) continue;
    if (!map.has(loc.key)) {
      map.set(loc.key, { key: loc.key, region: loc.region, gu: loc.gu, dong: loc.dong, items: [] });
    }
    map.get(loc.key).items.push(it);
  }
  const clusters = Array.from(map.values())
    .filter((c) => c.items.length >= 2)
    .map((c) => {
      const grades = { A: 0, B: 0, C: 0, D: 0, X: 0 };
      let totalProfit = 0;
      let totalPrice = 0;
      let totalScore = 0;
      let highRisk = 0;
      for (const it of c.items) {
        grades[it.recommendation_grade || "C"] = (grades[it.recommendation_grade || "C"] || 0) + 1;
        totalProfit += it.expected_profit || 0;
        totalPrice += it.min_bid_price || 0;
        totalScore += it.recommendation_score || 0;
        if (it.risk_level === "high") highRisk++;
      }
      return {
        ...c,
        count: c.items.length,
        grades,
        avgProfit: Math.round(totalProfit / c.items.length),
        avgPrice: Math.round(totalPrice / c.items.length),
        avgScore: c.items.length ? totalScore / c.items.length : 0,
        highRisk,
      };
    });
  clusters.sort((a, b) => b.count - a.count || b.avgScore - a.avgScore);
  return clusters;
}

function renderClusterDonut(grades, total) {
  const order = ["A", "B", "C", "D", "X"];
  const nonZero = order.filter((g) => (grades[g] || 0) > 0);
  if (!nonZero.length || !total) return "";
  const cx = 25, cy = 25, r = 22, innerR = 13;
  let parts = "";
  if (nonZero.length === 1) {
    const g = nonZero[0];
    parts = `<circle cx="${cx}" cy="${cy}" r="${(r + innerR) / 2}" fill="none"
              stroke="${GRADE_COLOR[g]}" stroke-width="${r - innerR}">
              <title>${g} 등급 ${grades[g]}건</title>
            </circle>`;
  } else {
    let cumAngle = -Math.PI / 2;
    for (const g of order) {
      const v = grades[g] || 0;
      if (v === 0) continue;
      const angle = (v / total) * Math.PI * 2;
      const a1 = cumAngle, a2 = cumAngle + angle;
      const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
      const ix2 = cx + innerR * Math.cos(a2), iy2 = cy + innerR * Math.sin(a2);
      const ix1 = cx + innerR * Math.cos(a1), iy1 = cy + innerR * Math.sin(a1);
      const large = angle > Math.PI ? 1 : 0;
      const d =
        `M ${x1.toFixed(2)} ${y1.toFixed(2)} ` +
        `A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} ` +
        `L ${ix2.toFixed(2)} ${iy2.toFixed(2)} ` +
        `A ${innerR} ${innerR} 0 ${large} 0 ${ix1.toFixed(2)} ${iy1.toFixed(2)} Z`;
      parts += `<path d="${d}" fill="${GRADE_COLOR[g] || '#999'}">
                  <title>${g} 등급 ${v}건</title>
                </path>`;
      cumAngle = a2;
    }
  }
  return `
    <svg viewBox="0 0 50 50" class="cluster-donut" aria-hidden="true">
      ${parts}
      <text x="25" y="29" text-anchor="middle" font-size="11" font-weight="700" fill="currentColor">${total}</text>
    </svg>
  `;
}

function renderClusters() {
  const sec = $("section-clusters");
  const grid = $("clusters-grid");
  const cap = $("clusters-caption");
  if (!sec || !grid) return;
  const clusters = buildClusters(STATE.items).slice(0, 5);
  if (!clusters.length) {
    sec.hidden = true;
    return;
  }
  sec.hidden = false;
  cap.textContent = `같은 동에 2건 이상 모인 위치 — 클릭하면 그 동 매물만 필터`;
  grid.innerHTML = "";
  clusters.forEach((c) => {
    const gradeStr = ["A","B","C","D","X"]
      .map((g) => c.grades[g] ? `<span class="grade-pill grade-${g}">${g} ${c.grades[g]}</span>` : "")
      .filter(Boolean).join("");
    const card = el(
      `<article class="cluster-card" data-cluster-key="${escapeHtml(c.key)}" tabindex="0" role="button" aria-label="${escapeHtml(c.key)} 매물 ${c.count}건 보기">
         ${renderClusterDonut(c.grades, c.count)}
         <div class="cluster-head">
           <span class="cluster-count">${c.count}건</span>
           <span class="cluster-loc">${escapeHtml(c.key)}</span>
         </div>
         <div class="cluster-grades">${gradeStr}</div>
         <div class="cluster-stats">
           <span>평균 점수 <strong>${c.avgScore.toFixed(1)}</strong></span>
           <span>평균 차익 <strong>${fmtMan(c.avgProfit)}</strong></span>
           <span>평균 최저가 <strong>${fmtMan(c.avgPrice)}</strong></span>
           ${c.highRisk ? `<span class="cluster-warn">고위험 ${c.highRisk}건</span>` : ""}
         </div>
       </article>`
    );
    bindTap(card, () => {
      // 검색바에 위치 키워드 넣고 적용 → 그 동 매물만 노출
      $("q-input").value = c.dong || c.gu || c.region;
      STATE.filters.q = $("q-input").value;
      pushSearchHistory(STATE.filters.q);
      applyFilters();
      const items = $("section-items");
      if (items) items.scrollIntoView({ behavior: "smooth", block: "start" });
      showToast(`'${c.key}' 매물 ${c.count}건만 봅니다.`, "되돌리기", () => {
        $("q-input").value = "";
        STATE.filters.q = "";
        applyFilters();
      });
      setTimeout(hideToast, 4000);
    });
    grid.appendChild(card);
  });
}

/* 카드 다중 선택 모드 */
const SELECTED = new Set();
let SELECTING = false;

function setSelectionMode(on) {
  SELECTING = !!on;
  document.body.classList.toggle("selecting", SELECTING);
  $("select-bar").hidden = !SELECTING;
  $("select-mode").classList.toggle("on", SELECTING);
  if (!SELECTING) {
    SELECTED.clear();
    document.querySelectorAll(".item-card.selected").forEach((c) => c.classList.remove("selected"));
  }
  updateSelectionBar();
}

function toggleSelected(id) {
  const key = String(id);
  if (SELECTED.has(key)) SELECTED.delete(key);
  else SELECTED.add(key);
  document.querySelectorAll(`.item-card[data-item-id="${key}"]`)
    .forEach((c) => c.classList.toggle("selected", SELECTED.has(key)));
  updateSelectionBar();
}

function updateSelectionBar() {
  const c = $("select-count");
  if (c) c.textContent = `선택 ${SELECTED.size}개`;
}

function bindSelectionMode() {
  const btn = $("select-mode");
  if (btn) btn.addEventListener("click", () => setSelectionMode(!SELECTING));

  $("sel-exit").addEventListener("click", () => setSelectionMode(false));
  $("sel-clear").addEventListener("click", () => {
    SELECTED.clear();
    document.querySelectorAll(".item-card.selected").forEach((c) => c.classList.remove("selected"));
    updateSelectionBar();
  });
  $("sel-fav").addEventListener("click", () => {
    if (!SELECTED.size) return;
    // 모두 ★ 가 아니면 일괄 ★, 모두 ★ 면 일괄 해제 (toggle)
    const allFav = Array.from(SELECTED).every((id) => STATE.favorites.has(id));
    SELECTED.forEach((id) => {
      if (allFav) STATE.favorites.delete(id);
      else STATE.favorites.add(id);
    });
    saveFavorites(STATE.favorites);
    showToast(allFav ? `${SELECTED.size}개 매물 관심 해제` : `${SELECTED.size}개 매물 관심 등록`, null);
    setTimeout(hideToast, 2500);
    applyFilters();  // ★ 우선 정렬 갱신
    // 카드 ☆ 표시 즉시 갱신
    document.querySelectorAll(".fav-btn").forEach((fb) => {
      const id = fb.dataset.fav;
      const on = STATE.favorites.has(String(id));
      fb.classList.toggle("on", on);
      fb.textContent = on ? "★" : "☆";
      fb.setAttribute("aria-pressed", on ? "true" : "false");
    });
  });
  $("sel-compare").addEventListener("click", () => {
    if (!SELECTED.size) return;
    let added = 0, skipped = 0;
    SELECTED.forEach((id) => {
      if (STATE.compare.includes(id)) { skipped++; return; }
      if (STATE.compare.length >= COMPARE_MAX) { skipped++; return; }
      STATE.compare.push(id);
      added++;
    });
    saveCompare(STATE.compare);
    document.querySelectorAll(".cmp-btn").forEach((cb) => {
      const id = cb.dataset.cmp;
      const on = STATE.compare.includes(String(id));
      cb.classList.toggle("on", on);
      cb.textContent = on ? "⇆ 담김" : "⇆ 비교";
      cb.setAttribute("aria-pressed", on ? "true" : "false");
    });
    renderCompareTray();
    showToast(`비교에 ${added}개 추가, ${skipped}개 스킵 (한도 ${COMPARE_MAX})`, null);
    setTimeout(hideToast, 3000);
  });
  $("sel-csv").addEventListener("click", () => {
    if (!SELECTED.size) return;
    const items = STATE.items.filter((it) => SELECTED.has(String(it.id)));
    if (!items.length) return;
    downloadBlob(buildCsv(items), `auction_selected_${timestampSlug()}.csv`,
                 "text/csv;charset=utf-8");
  });
}

/* 매물 상세용: 비슷한 매물 N개 (지역·종류·가격대) */
function findSimilarItems(target, n) {
  if (!target) return [];
  const limit = n || 3;
  const tPrice = target.min_bid_price || 0;
  const scored = [];
  for (const it of STATE.items) {
    if (String(it.id) === String(target.id)) continue;
    let score = 0;
    const reasons = [];
    if (target.region && it.region === target.region) {
      score += 30; reasons.push("같은 지역");
    }
    if (target.item_type && it.item_type === target.item_type) {
      score += 25; reasons.push("같은 종류");
    }
    if (tPrice && it.min_bid_price) {
      const ratio = it.min_bid_price / tPrice;
      if (ratio >= 0.8 && ratio <= 1.2) {
        score += 15; reasons.push("비슷한 가격대");
      } else if (ratio >= 0.6 && ratio <= 1.4) {
        score += 6;
      }
    }
    if (target.source && it.source === target.source) score += 5;
    if (target.recommendation_grade && it.recommendation_grade === target.recommendation_grade) {
      score += 6;
    }
    if (score >= 25) {
      scored.push({ item: it, score, reasons });
    }
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit);
}

function renderSimilarItemsHtml(target) {
  const similar = findSimilarItems(target, 3);
  if (!similar.length) {
    return `<p class="caption">조건이 비슷한 다른 매물이 없어요.</p>`;
  }
  const cards = similar.map(({ item, score, reasons }) => {
    const grade = item.recommendation_grade || "C";
    const risk = item.risk_level || "medium";
    return `
      <article class="similar-card" data-similar-id="${item.id}">
        <div class="similar-head">
          <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
          <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
          <span class="similar-score" title="유사도">${score}</span>
        </div>
        <div class="similar-title">${escapeHtml(item.title || item.address || "주소 미상")}</div>
        <div class="similar-meta">${escapeHtml(item.item_type || "")} · 최저가 ${fmtMan(item.min_bid_price)}</div>
        <div class="similar-stats">
          <span>차익 <strong>${fmtMan(item.expected_profit)}</strong></span>
          <span>ROI <strong>${fmtPct(item.expected_profit_rate)}</strong></span>
          <span>점수 <strong>${escapeHtml(String(item.recommendation_score || "-"))}</strong></span>
        </div>
        <div class="similar-reason">${escapeHtml(reasons.slice(0,3).join(" · "))}</div>
      </article>
    `;
  }).join("");
  return `<div class="similar-grid">${cards}</div>`;
}

function wireSimilarItems() {
  document.querySelectorAll(".similar-card").forEach((card) => {
    const id = card.dataset.similarId;
    bindTap(card, () => {
      // 모달 안에서 바로 다른 매물로 이동
      openDetailById(id);
      const body = $("detail-body");
      if (body) body.scrollTop = 0;
    });
  });
}

function renderPersonalRecs() {
  const sec = $("section-personal-recs");
  const grid = $("personal-rec-grid");
  const cap = $("personal-recs-caption");
  if (!sec || !grid) return;

  const profile = buildUserProfile();
  if (!profile) {
    sec.hidden = true;
    return;
  }

  // 시그널에 들어 있지 않은 매물 중 점수 desc 상위 5
  const candidates = STATE.items.filter((it) => !profile.signalIds.has(String(it.id)));
  const scored = candidates.map((it) => ({ it, ...scoreAgainstProfile(it, profile) }));
  scored.sort((a, b) => b.score - a.score);
  const top5 = scored.filter((x) => x.score >= 25).slice(0, 5);

  if (!top5.length) {
    sec.hidden = true;
    return;
  }

  sec.hidden = false;
  cap.textContent = `★/📝/👁 ${profile.signalCount}건 시그널 기반 — 선호 ${profile.topRegion || ""} ${profile.topType || ""}`.trim();

  grid.innerHTML = "";
  top5.forEach(({ it, score, reasons }, idx) => {
    const grade = it.recommendation_grade || "C";
    const risk = it.risk_level || "medium";
    const profit = it.expected_profit;
    const roi = it.expected_profit_rate;
    const reasonText = reasons.slice(0, 3).join(" · ") || "유사도 점수 기반";
    const card = el(
      `<article class="rec-card" data-item-id="${it.id}">
         <div class="rec-head">
           <span class="rec-rank">맞춤 #${idx + 1}</span>
           <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
           <span class="risk-pill ${escapeHtml(risk)}">${escapeHtml(RISK_LABEL[risk] || risk)}</span>
           <span class="source-pill">${escapeHtml(SOURCE_LABEL[it.source] || it.source || "")}</span>
           <span class="personal-score" title="당신 시그널 대비 유사도">유사도 ${score}</span>
         </div>
         <div class="rec-title">${escapeHtml(it.title || it.address || "주소 미상")}</div>
         <div class="rec-meta">${escapeHtml(it.address || "")} · ${escapeHtml(it.item_type || "")}</div>
         <div class="rec-stats">
           <span class="rec-stat"><strong>${fmtMan(profit)}</strong> 차익</span>
           <span class="rec-stat">ROI <strong>${fmtPct(roi)}</strong></span>
           <span class="rec-stat">최저가 ${fmtMan(it.min_bid_price)}</span>
           <span class="rec-stat">점수 <strong>${escapeHtml(String(it.recommendation_score || "-"))}</strong></span>
         </div>
         <div class="rec-reason">${escapeHtml(reasonText)}</div>
       </article>`
    );
    bindTap(card, () => openDetailById(it.id), {
      onLongPress: () => toggleCompare(it.id),
    });
    grid.appendChild(card);
  });
}

/* 입찰가 시뮬레이터 — modules/profit_calculator.py 의 JS 미러 */
const ACQUISITION_TAX_RATE = 0.035;
const DEFAULT_REPAIR_COST = 500;
const DEFAULT_EVICTION_COST = 300;
const FINANCE_RATE = 0.04;
const FINANCE_MONTHS = 6;

function calcAcquisitionTax(priceMan, itemType) {
  const eok = priceMan / 10000;
  let rate = ACQUISITION_TAX_RATE;
  if (itemType === "아파트" || itemType === "오피스텔") {
    if (eok <= 6) rate = 0.01;
    else if (eok <= 9) rate = ACQUISITION_TAX_RATE;
    else rate = 0.03;
  }
  return Math.round(priceMan * rate);
}

function calcProfit(marketMan, bidMan, itemType, opts) {
  const repair = (opts && opts.repair !== undefined) ? opts.repair : DEFAULT_REPAIR_COST;
  const eviction = (opts && opts.eviction !== undefined) ? opts.eviction : DEFAULT_EVICTION_COST;
  const acq = calcAcquisitionTax(bidMan, itemType);
  const finance = Math.round(bidMan * FINANCE_RATE * (FINANCE_MONTHS / 12));
  const totalCost = acq + repair + eviction + finance;
  const invested = bidMan + totalCost;
  const profit = marketMan - invested;
  const roi = invested > 0 ? (profit / invested * 100) : 0;
  return {
    bidMan, marketMan, itemType,
    acq, repair, eviction, finance,
    totalCost, invested, profit, roi,
  };
}

function renderBidSimulator(it) {
  const market = Math.max(0, it.market_price || 0);
  const minBid = Math.max(1, it.min_bid_price || 0);
  if (!market || !minBid) {
    return `<div class="detail-section">
      <h3>입찰가 시뮬레이터</h3>
      <p class="caption">시세 또는 최저가 데이터가 부족해 시뮬레이션을 표시하지 못했어요.</p>
    </div>`;
  }
  const slMax = Math.max(minBid + 1, Math.round(market * 0.95));
  const initial = Math.min(slMax, Math.max(minBid, Math.round(minBid * 1.05)));
  return `
    <div class="detail-section sim-section" data-sim-market="${market}" data-sim-min="${minBid}" data-sim-type="${escapeHtml(it.item_type || "아파트")}">
      <h3>입찰가 시뮬레이터</h3>
      <div class="sim-row">
        <label class="sim-label">입찰가
          <input type="number" class="sim-num" id="sim-bid-num" min="${minBid}" max="${slMax}" step="100" value="${initial}" />
          <span class="sim-unit">만원</span>
        </label>
        <input type="range" class="sim-range" id="sim-bid-range" min="${minBid}" max="${slMax}" step="100" value="${initial}" />
        <div class="sim-bounds">
          <span>최저가 ${fmtMan(minBid)}</span>
          <span>시세 95% ${fmtMan(slMax)}</span>
        </div>
      </div>
      <div class="sim-curve-host" id="sim-curve"></div>
      <div class="sim-grid" id="sim-out"></div>
      <p class="caption" style="margin-top:6px">
        ※ 취득세(아파트·오피스텔 6억↓ 1%, ~9억 ${(ACQUISITION_TAX_RATE*100).toFixed(1)}%, 9억↑ 3%) +
        수리 ${DEFAULT_REPAIR_COST}만 + 명도 ${DEFAULT_EVICTION_COST}만 +
        금융 ${(FINANCE_RATE*100).toFixed(1)}% × ${FINANCE_MONTHS}개월 가정. mock 추정치이며 실제와 다를 수 있어요.
      </p>
    </div>
  `;
}

function buildProfitCurve(market, minBid, slMax, itemType, currentBid) {
  const N = 30;
  const samples = [];
  for (let i = 0; i <= N; i++) {
    const bid = Math.round(minBid + (slMax - minBid) * (i / N));
    const r = calcProfit(market, bid, itemType);
    samples.push({ bid, profit: r.profit });
  }
  if (!samples.length) return "";
  const profits = samples.map((s) => s.profit);
  const maxP = Math.max(...profits, 0);
  const minP = Math.min(...profits, 0);
  const range = Math.max(1, maxP - minP);

  const W = 360, H = 110;
  const padL = 6, padR = 64, padT = 10, padB = 18;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const xAt = (bid) => padL + ((bid - minBid) / Math.max(1, slMax - minBid)) * innerW;
  const yAt = (profit) => padT + (1 - (profit - minP) / range) * innerH;
  const yZero = yAt(0);

  // 라인 path
  let d = "";
  samples.forEach((s, i) => {
    const x = xAt(s.bid).toFixed(2);
    const y = yAt(s.profit).toFixed(2);
    d += (i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`);
  });

  // 손익 분기점 (보간)
  let breakEven = null;
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i];
    if ((a.profit >= 0) !== (b.profit >= 0)) {
      // linear interp
      const t = a.profit / (a.profit - b.profit);
      breakEven = Math.round(a.bid + (b.bid - a.bid) * t);
      break;
    }
  }

  // 현재 입찰가 마커
  const cx = xAt(currentBid).toFixed(2);
  const curR = calcProfit(market, currentBid, itemType);
  const cy = yAt(curR.profit).toFixed(2);
  const profitColor = curR.profit >= 0 ? "#2ca02c" : "#d62728";

  // 영역(양/음) 음영
  const profitArea = `M ${padL} ${yZero} L ${samples.map((s,i)=> xAt(s.bid).toFixed(2)+' '+yAt(s.profit).toFixed(2)).join(' L ')} L ${xAt(samples[samples.length-1].bid).toFixed(2)} ${yZero} Z`;

  const beLabel = breakEven
    ? `<g>
         <line x1="${xAt(breakEven).toFixed(2)}" x2="${xAt(breakEven).toFixed(2)}" y1="${padT}" y2="${H - padB}" stroke="#888" stroke-width="1" stroke-dasharray="2,3"/>
         <text x="${xAt(breakEven).toFixed(2)}" y="${padT + 8}" text-anchor="middle" font-size="9" fill="var(--color-text-muted)">손익분기 ${breakEven.toLocaleString("ko-KR")}</text>
       </g>` : "";

  return `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="입찰가-차익 곡선">
      <path d="${profitArea}" fill="rgba(31,119,180,0.10)" stroke="none"/>
      <line x1="${padL}" x2="${W - padR}" y1="${yZero}" y2="${yZero}" stroke="#888" stroke-width="1" stroke-dasharray="3,3"/>
      <text x="${W - padR + 4}" y="${yZero + 3}" font-size="9" fill="var(--color-text-muted)">손익 0</text>
      <path d="${d}" fill="none" stroke="#1f77b4" stroke-width="1.6" stroke-linejoin="round"/>
      ${beLabel}
      <line x1="${cx}" x2="${cx}" y1="${padT}" y2="${H - padB}" stroke="${profitColor}" stroke-width="1.5"/>
      <circle cx="${cx}" cy="${cy}" r="3.5" fill="${profitColor}"/>
      <text x="${cx}" y="${H - padB + 12}" text-anchor="middle" font-size="9" fill="${profitColor}" font-weight="700">${currentBid.toLocaleString("ko-KR")}</text>
      <text x="${W - padR + 4}" y="${padT + 8}" font-size="9" fill="#2ca02c">+${Math.max(0, maxP).toLocaleString("ko-KR")}</text>
      <text x="${W - padR + 4}" y="${H - padB - 2}" font-size="9" fill="#d62728">${Math.min(0, minP).toLocaleString("ko-KR")}</text>
    </svg>
  `;
}

function wireBidSimulator() {
  const sec = document.querySelector(".sim-section");
  if (!sec) return;
  const market = Number(sec.dataset.simMarket) || 0;
  const minBid = Number(sec.dataset.simMin) || 0;
  const itemType = sec.dataset.simType || "아파트";
  const numEl = sec.querySelector("#sim-bid-num");
  const rangeEl = sec.querySelector("#sim-bid-range");
  const out = sec.querySelector("#sim-out");
  const curve = sec.querySelector("#sim-curve");
  const slMax = Number(rangeEl.max) || (market || minBid);

  const refresh = (v) => {
    const bid = Math.max(0, Math.round(Number(v) || 0));
    numEl.value = bid;
    rangeEl.value = bid;
    const r = calcProfit(market, bid, itemType);
    const profitClass = r.profit >= 0 ? "sim-profit-pos" : "sim-profit-neg";
    if (curve && market && minBid) {
      curve.innerHTML = buildProfitCurve(market, minBid, slMax, itemType, bid);
    }
    out.innerHTML = `
      <div class="sim-card sim-bid">
        <div class="sim-k">입찰가</div>
        <div class="sim-v">${fmtMan(r.bidMan)}</div>
        <div class="sim-sub">시세 ${fmtMan(market)}</div>
      </div>
      <div class="sim-card ${profitClass}">
        <div class="sim-k">예상 차익</div>
        <div class="sim-v">${fmtMan(r.profit)}</div>
        <div class="sim-sub">ROI ${fmtPct(r.roi)}</div>
      </div>
      <div class="sim-card">
        <div class="sim-k">총 투자</div>
        <div class="sim-v">${fmtMan(r.invested)}</div>
        <div class="sim-sub">입찰가 + 비용</div>
      </div>
      <div class="sim-card sim-cost">
        <div class="sim-k">총 비용</div>
        <div class="sim-v">${fmtMan(r.totalCost)}</div>
        <div class="sim-sub">취득세 ${r.acq.toLocaleString("ko-KR")} · 수리 ${r.repair} · 명도 ${r.eviction} · 금융 ${r.finance}</div>
      </div>
    `;
  };
  rangeEl.addEventListener("input", () => refresh(rangeEl.value));
  numEl.addEventListener("input", () => refresh(numEl.value));
  refresh(rangeEl.value);
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
  const shareBtn = $("share-results");
  if (shareBtn) shareBtn.addEventListener("click", shareResults);
}

function buildResultsSummary() {
  const f = STATE.filters;
  const parts = [];
  const chip = QUICK_CHIPS.find((c) => c.id === f.chip);
  if (chip && chip.id !== "all") parts.push(chip.label);
  if (f.q) parts.push(`"${f.q}"`);
  if (f.region) parts.push(`지역 ${f.region}`);
  if (f.item_type) parts.push(f.item_type);
  if (f.source) parts.push(SOURCE_LABEL[f.source] || f.source);
  if (f.grade) parts.push(`${f.grade} 등급`);
  if (f.risk) parts.push(`위험 ${RISK_LABEL[f.risk] || f.risk}`);
  if (f.fail_min !== null && f.fail_min !== undefined) parts.push(`유찰 ${f.fail_min}+`);
  if (f.due_max !== null && f.due_max !== undefined) parts.push(`D-${f.due_max} 이내`);
  if (f.price_min !== null && f.price_min !== undefined) parts.push(`최저가 ${f.price_min.toLocaleString("ko-KR")}만↑`);
  if (f.price_max !== null && f.price_max !== undefined) parts.push(`최저가 ${f.price_max.toLocaleString("ko-KR")}만↓`);
  if (f.flag) parts.push(`키워드 ${f.flag}`);
  parts.push(`정렬 ${SORT_LABEL[f.sort] || SORT_LABEL.score_desc}`);
  return parts.join(" · ");
}

function shareResults() {
  // 매물 모달이 열려 있어 #item-... 해시가 붙어 있으면 공유 URL 에서 제거
  const url = new URL(window.location.href);
  url.hash = "";
  const shareUrl = url.toString();

  const summary = buildResultsSummary();
  const lines = [
    "경매·공매 지능형 에이전트 — 검색 결과",
    `${STATE.filtered.length}건 / ${summary}`,
    "이 링크를 열면 동일 검색 결과가 그대로 보여요.",
  ];
  const text = lines.join("\n");
  const title = "경매·공매 검색 결과";

  if (navigator.share) {
    navigator.share({ title, text, url: shareUrl }).catch((err) => {
      if (err && err.name === "AbortError") return;
      copyShareLink(text, shareUrl);
    });
  } else {
    copyShareLink(text, shareUrl);
  }
}

function applyDensity(mode) {
  const dense = mode === "dense";
  document.body.classList.toggle("density-dense", dense);
  const btn = $("density-btn");
  if (btn) {
    btn.classList.toggle("on", dense);
    btn.title = dense ? "조밀 → 표준 으로 전환" : "표준 → 조밀 (더 많이 한 화면에)";
    btn.setAttribute("aria-pressed", dense ? "true" : "false");
  }
  try { localStorage.setItem(DENSITY_KEY, dense ? "dense" : "normal"); } catch (_) {}
}

function bindDensity() {
  const btn = $("density-btn");
  if (!btn) return;
  // 초기 상태 복원
  let saved = "normal";
  try { saved = localStorage.getItem(DENSITY_KEY) || "normal"; } catch (_) {}
  applyDensity(saved);
  btn.addEventListener("click", () => {
    const next = document.body.classList.contains("density-dense") ? "normal" : "dense";
    applyDensity(next);
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
  recordViewed(it.id);
  // '최근 본' 칩이 활성화돼 있으면 새로 본 매물이 즉시 위로 올라오도록 재필터
  if (STATE.filters.chip === "viewed") applyFilters();
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

    ${renderBidSimulator(it)}

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

    <div class="detail-section">
      <h3>비슷한 매물</h3>
      ${renderSimilarItemsHtml(it)}
    </div>

    <div class="detail-section note-section" data-note-item-id="${escapeHtml(String(it.id))}">
      <h3>내 메모 <span class="note-status caption" id="note-status"></span></h3>
      <textarea class="note-input" id="note-input" rows="3" placeholder="이 매물에 대한 메모를 남겨두세요. 예: 1차 현장조사 완료, 임차인 만남 예정, 보증금 협의 필요 등. (자기 폰에만 저장됨)" maxlength="2000">${escapeHtml((getNote(it.id) || {}).text || "")}</textarea>
      <div class="note-actions">
        <button class="btn btn-ghost note-clear" id="note-clear" type="button">메모 지우기</button>
      </div>
    </div>

    <p class="caption" style="margin-top:14px">
      ※ 본 분석은 mock 데이터를 기반으로 한 참고용 정보입니다. 법률·투자 판단을 단정하지 않으며,
      실제 입찰 전 등기부등본·전입세대열람·현장조사·전문가 자문이 필요합니다.
    </p>
  `;
  $("detail-modal").hidden = false;
  document.body.style.overflow = "hidden";
  wireBidSimulator();
  wireNoteSection();
  wireSimilarItems();
  updateNavButtons();
}

function wireNoteSection() {
  const sec = document.querySelector(".note-section");
  if (!sec) return;
  const itemId = sec.dataset.noteItemId;
  const ta = sec.querySelector("#note-input");
  const status = sec.querySelector("#note-status");
  const clearBtn = sec.querySelector("#note-clear");

  // 초기 상태 표시
  const initial = getNote(itemId);
  status.textContent = initial && initial.updatedAt
    ? `· 마지막 저장 ${formatRelative(initial.updatedAt)}`
    : "· 아직 메모 없음";

  let t = null;
  const persist = () => {
    setNote(itemId, ta.value);
    const n = getNote(itemId);
    status.textContent = n
      ? `· 저장됨 ${formatRelative(n.updatedAt)}`
      : "· 메모 없음";
    // 카드 배지 즉시 반영
    refreshNoteBadgeForItem(itemId);
  };
  ta.addEventListener("input", () => {
    if (t) clearTimeout(t);
    status.textContent = "· 입력 중…";
    t = setTimeout(persist, 600);
  });
  ta.addEventListener("blur", persist);

  clearBtn.addEventListener("click", () => {
    ta.value = "";
    persist();
  });
}

function formatRelative(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const now = new Date();
  const sec = Math.floor((now - d) / 1000);
  if (sec < 30) return "방금 전";
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function refreshNoteBadgeForItem(itemId) {
  document.querySelectorAll(`.item-card[data-item-id="${itemId}"], .rec-card[data-item-id="${itemId}"]`).forEach((card) => {
    const head = card.querySelector(".item-head, .rec-head");
    if (!head) return;
    const existing = head.querySelector(".note-badge");
    if (existing) existing.remove();
    const it = STATE.items.find((x) => String(x.id) === String(itemId));
    if (!it) return;
    const html = noteBadgeHtml(it);
    if (!html) return;
    // change_tags 뒤, head-spacer 앞에 삽입 (최대한 자연스럽게)
    const spacer = head.querySelector(".head-spacer");
    if (spacer) {
      spacer.insertAdjacentHTML("beforebegin", html);
    } else {
      head.insertAdjacentHTML("beforeend", html);
    }
  });
  // 만약 현재 칩이 '메모'이고 메모가 사라졌으면 결과 즉시 갱신
  if (STATE.filters.chip === "notes") applyFilters();
  // 시그널 변화 → 맞춤 추천 갱신
  renderPersonalRecs();
}

let CURRENT_DETAIL_ID = null;

function bindModalClose() {
  const close = () => closeDetailModal();
  $("detail-close").addEventListener("click", close);
  $("detail-modal").addEventListener("click", (e) => {
    if (e.target instanceof HTMLElement && e.target.dataset.close === "1") close();
  });
  document.addEventListener("keydown", (e) => {
    if (!$("detail-modal").hidden) {
      if (e.key === "Escape") { close(); return; }
      // 좌/우 화살표 — 입력 포커스 중엔 무시
      if (isTextFocus(e.target)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); navDetail(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); navDetail(1); }
      else if (e.key === "f" || e.key === "F") {
        if (CURRENT_DETAIL_ID) { e.preventDefault(); toggleFavorite(CURRENT_DETAIL_ID); }
      }
      else if (e.key === "b" || e.key === "B") {
        if (CURRENT_DETAIL_ID) { e.preventDefault(); toggleCompare(CURRENT_DETAIL_ID); }
      }
      else if (e.key === "n" || e.key === "N") {
        const ta = document.querySelector(".note-section #note-input");
        if (ta) {
          e.preventDefault();
          ta.focus();
          ta.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      }
      else if (e.key === "p" || e.key === "P") {
        e.preventDefault(); printDetail();
      }
      else if (e.key === "s" || e.key === "S") {
        e.preventDefault(); shareDetail();
      }
    }
  });
  const printBtn = $("detail-print");
  if (printBtn) printBtn.addEventListener("click", printDetail);
  const shareBtn = $("detail-share");
  if (shareBtn) shareBtn.addEventListener("click", shareDetail);
  const prevBtn = $("detail-prev");
  if (prevBtn) prevBtn.addEventListener("click", () => navDetail(-1));
  const nextBtn = $("detail-next");
  if (nextBtn) nextBtn.addEventListener("click", () => navDetail(1));
}

function navDetail(direction) {
  if (!CURRENT_DETAIL_ID) return;
  const list = STATE.filtered.length ? STATE.filtered : STATE.items;
  const idx = list.findIndex((it) => String(it.id) === String(CURRENT_DETAIL_ID));
  if (idx < 0) return;
  const next = idx + direction;
  if (next < 0 || next >= list.length) return;
  openDetailById(list[next].id);
  const body = $("detail-body");
  if (body) body.scrollTop = 0;
}

function updateNavButtons() {
  const prev = $("detail-prev");
  const next = $("detail-next");
  if (!prev || !next || !CURRENT_DETAIL_ID) return;
  const list = STATE.filtered.length ? STATE.filtered : STATE.items;
  const idx = list.findIndex((it) => String(it.id) === String(CURRENT_DETAIL_ID));
  prev.disabled = (idx <= 0);
  next.disabled = (idx < 0 || idx >= list.length - 1);
  // 위치 표시는 title 옆 caption 으로 — 간단 텍스트 추가
  const title = $("detail-title");
  if (title && idx >= 0) {
    const existing = title.querySelector(".nav-pos");
    if (existing) existing.remove();
    const pos = document.createElement("span");
    pos.className = "nav-pos caption";
    pos.style.marginLeft = "8px";
    pos.style.fontWeight = "400";
    pos.textContent = `${idx + 1}/${list.length}`;
    title.appendChild(pos);
  }
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

function _printNow() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function printDetail() {
  if ($("detail-modal").hidden) return;
  // 인쇄 footer 채우기
  const urlEl = $("pf-detail-url");
  const whenEl = $("pf-detail-when");
  if (urlEl) {
    const url = new URL(window.location.href);
    if (CURRENT_DETAIL_ID) url.hash = `item-${CURRENT_DETAIL_ID}`;
    urlEl.textContent = url.toString();
  }
  if (whenEl) whenEl.textContent = _printNow();

  // 메모 textarea → 인쇄용 div 미러 (PDF 가독성)
  const ta = document.querySelector(".note-section #note-input");
  if (ta) {
    let printDiv = document.querySelector(".note-section .note-print");
    const txt = (ta.value || "").trim();
    if (txt) {
      if (!printDiv) {
        printDiv = document.createElement("div");
        printDiv.className = "note-print";
        ta.parentNode.insertBefore(printDiv, ta);
      }
      printDiv.textContent = txt;
      printDiv.hidden = false;
    } else if (printDiv) {
      printDiv.hidden = true;
    }
  }

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
  const whenEl = $("pf-compare-when");
  if (whenEl) whenEl.textContent = _printNow();

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
function pushSearchHistory(q) {
  q = String(q || "").trim();
  if (q.length < 2) return;
  let arr = STATE.recentSearches.slice();
  arr = arr.filter((x) => x !== q);
  arr.unshift(q);
  if (arr.length > SEARCHES_MAX) arr.length = SEARCHES_MAX;
  STATE.recentSearches = arr;
  saveSearches(arr);
}

function removeSearchHistory(q) {
  STATE.recentSearches = STATE.recentSearches.filter((x) => x !== q);
  saveSearches(STATE.recentSearches);
  renderSearchSuggest();
}

function clearSearchHistory() {
  STATE.recentSearches = [];
  saveSearches(STATE.recentSearches);
  renderSearchSuggest();
}

function showSearchSuggest() {
  renderSearchSuggest();
  $("search-suggest").hidden = false;
}
function hideSearchSuggest() {
  $("search-suggest").hidden = true;
}

function _matchItemsForSuggest(q, limit) {
  const needle = String(q || "").trim().toLowerCase();
  if (needle.length < 2) return [];
  const matches = [];
  for (const it of STATE.items) {
    if (searchableText(it).includes(needle)) {
      matches.push(it);
      if (matches.length >= limit) break;
    }
  }
  return matches;
}

function _highlightMatch(text, q) {
  if (!q) return escapeHtml(text || "");
  const safe = escapeHtml(text || "");
  const safeQ = escapeHtml(q);
  // 대소문자 무시 매칭, 첫 매칭만 강조
  const idx = safe.toLowerCase().indexOf(safeQ.toLowerCase());
  if (idx < 0) return safe;
  return safe.slice(0, idx) + `<mark>${safe.slice(idx, idx + safeQ.length)}</mark>` + safe.slice(idx + safeQ.length);
}

function renderSearchSuggest() {
  const root = $("search-suggest");
  if (!root) return;
  const input = $("q-input");
  const currentQ = (input && input.value || "").trim();
  const recents = STATE.recentSearches;
  const matched = _matchItemsForSuggest(currentQ, 5);

  if (!recents.length && !matched.length) {
    root.innerHTML = `<p class="search-suggest-empty">최근 검색어가 없어요. 검색 후 Enter 또는 검색 버튼을 누르면 여기 모입니다.</p>`;
    return;
  }
  let body = "";
  // 매물 매칭 (입력 2+ 자일 때만)
  if (matched.length) {
    body += `<div class="search-suggest-head">매물 매칭</div>`;
    body += matched.map((it) => {
      const grade = it.recommendation_grade || "C";
      return `<div class="search-suggest-row search-suggest-item" role="option" data-item-id="${escapeHtml(String(it.id))}">
         <span class="grade-pill grade-${escapeHtml(grade)}" style="font-size:0.66rem;padding:1px 6px">${escapeHtml(grade)}</span>
         <span class="q">${_highlightMatch(it.title || it.address || "주소 미상", currentQ)}</span>
         <span class="search-suggest-meta">${escapeHtml(it.item_type || "")}</span>
       </div>`;
    }).join("");
  }
  if (recents.length) {
    body += `<div class="search-suggest-head">최근 검색어</div>`;
    body += recents.map((q) =>
      `<div class="search-suggest-row" role="option" data-q="${escapeHtml(q)}">
         <span class="ico">⏱</span>
         <span class="q">${escapeHtml(q)}</span>
         <button class="x" type="button" data-remove="${escapeHtml(q)}" aria-label="이 검색어 지우기">×</button>
       </div>`
    ).join("");
    body += `<div class="search-suggest-foot">
      <button id="search-clear-all" type="button">전체 지우기</button>
    </div>`;
  }
  root.innerHTML = body;

  // 클릭 위임 — 행 클릭/× 버튼/전체 지우기
  root.querySelectorAll(".search-suggest-row").forEach((row) => {
    row.addEventListener("mousedown", (e) => e.preventDefault()); // blur 방지
    row.addEventListener("click", (e) => {
      const xBtn = e.target.closest(".x");
      if (xBtn) {
        e.stopPropagation();
        removeSearchHistory(xBtn.dataset.remove);
        return;
      }
      // 매물 매칭 row 면 그 매물 상세 모달 직접 오픈
      const itemId = row.dataset.itemId;
      if (itemId) {
        hideSearchSuggest();
        const inp = $("q-input");
        if (inp) inp.blur();
        openDetailById(itemId);
        return;
      }
      // 최근 검색어 row
      const q = row.dataset.q || "";
      const input = $("q-input");
      input.value = q;
      STATE.filters.q = q;
      pushSearchHistory(q);
      applyFilters();
      hideSearchSuggest();
      input.blur();
    });
  });
  const clearAll = root.querySelector("#search-clear-all");
  if (clearAll) {
    clearAll.addEventListener("mousedown", (e) => e.preventDefault());
    clearAll.addEventListener("click", clearSearchHistory);
  }
}

/* 음성 검색 (Web Speech API) — 지원 브라우저에서만 활성 */
function bindVoiceSearch() {
  const btn = $("voice-btn");
  if (!btn) return;
  const Recog = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recog) return; // 미지원이면 버튼 hidden 그대로

  btn.hidden = false;
  let rec = null;
  let listening = false;

  const stop = () => {
    if (rec) { try { rec.stop(); } catch (_) {} }
    listening = false;
    btn.classList.remove("listening");
  };

  btn.addEventListener("click", () => {
    if (listening) { stop(); return; }
    try {
      rec = new Recog();
      rec.lang = "ko-KR";
      rec.interimResults = true;
      rec.continuous = false;
      rec.maxAlternatives = 1;

      rec.addEventListener("start", () => {
        listening = true;
        btn.classList.add("listening");
        showToast("말씀하세요… (다시 누르면 멈춤)", null);
      });
      rec.addEventListener("result", (e) => {
        const last = e.results[e.results.length - 1];
        const transcript = (last && last[0] && last[0].transcript) || "";
        const input = $("q-input");
        if (input) input.value = transcript.trim();
        if (last && last.isFinal) {
          STATE.filters.q = (input.value || "").trim();
          if (STATE.filters.q) pushSearchHistory(STATE.filters.q);
          applyFilters();
          hideSearchSuggest();
          hideToast();
        }
      });
      rec.addEventListener("error", (e) => {
        listening = false;
        btn.classList.remove("listening");
        const msg = e.error === "not-allowed"
          ? "마이크 권한이 거부됐어요. 브라우저 설정에서 허용해 주세요."
          : `음성 인식 실패: ${e.error || "알 수 없음"}`;
        showToast(msg, null);
        setTimeout(hideToast, 3500);
      });
      rec.addEventListener("end", () => {
        listening = false;
        btn.classList.remove("listening");
      });

      rec.start();
    } catch (err) {
      showToast(`음성 인식 시작 실패: ${err && err.message ? err.message : err}`, null);
      setTimeout(hideToast, 3000);
    }
  });
}

function bindSearch() {
  const input = $("q-input");
  const submit = (explicit) => {
    STATE.filters.q = input.value.trim();
    applyFilters();
    if (explicit) {
      pushSearchHistory(STATE.filters.q);
      hideSearchSuggest();
    }
  };
  $("q-submit").addEventListener("click", () => submit(true));
  $("q-reset").addEventListener("click", resetFilters);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      submit(true);
      input.blur();
    } else if (e.key === "Escape") {
      hideSearchSuggest();
    }
  });
  // 디바운스 입력 갱신은 explicit=false (히스토리에 안 저장)
  let t;
  input.addEventListener("input", () => {
    clearTimeout(t);
    // 입력 즉시 suggest 재렌더 (debounce 없이) — 자동완성 응답성
    if (!$("search-suggest").hidden) renderSearchSuggest();
    t = setTimeout(() => submit(false), 200);
  });
  // 포커스 시 추천 패널, blur 시 살짝 늦춰 닫음 (행 클릭 허용)
  input.addEventListener("focus", showSearchSuggest);
  input.addEventListener("blur", () => setTimeout(hideSearchSuggest, 180));

  // 검색바 외부 클릭 시 닫기
  document.addEventListener("click", (e) => {
    const sb = document.querySelector(".search-bar");
    if (sb && !sb.contains(e.target)) hideSearchSuggest();
  });

  // 검색 예시 칩 — 클릭 시 해당 검색어로 즉시 검색
  document.querySelectorAll(".search-ex-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const ex = chip.dataset.ex || chip.textContent.trim();
      input.value = ex;
      STATE.filters.q = ex;
      applyFilters();
      pushSearchHistory(ex);
      hideSearchSuggest();
      const sec = $("section-items");
      if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
    });
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

  // 법원/기관
  const COURTS = ["서울중앙지방법원", "서울동부지방법원", "서울남부지방법원", "서울북부지방법원",
    "서울서부지방법원", "의정부지방법원", "인천지방법원", "수원지방법원", "대전지방법원",
    "대구지방법원", "부산지방법원", "광주지방법원", "울산지방법원", "창원지방법원",
    "제주지방법원", "춘천지방법원", "청주지방법원", "전주지방법원"];
  for (const c of COURTS) {
    if (q.includes(c)) { intent.filters.court = c; intent.note.push(`법원: ${c}`); break; }
  }
  if (!intent.filters.court && (q.includes("캠코") || q.includes("자산관리공사"))) {
    intent.filters.court = "한국자산관리공사"; intent.note.push("기관: 한국자산관리공사");
  }

  // 물건그룹
  if (q.includes("주거")) { intent.filters.item_group = "주거용 건물"; intent.note.push("주거용"); }
  else if (q.includes("상업")) { intent.filters.item_group = "상업용 건물"; intent.note.push("상업용"); }

  // 유찰 N회 이상
  const failMatch = q.match(/유찰\s*(\d+)\s*회/);
  if (failMatch) { intent.filters.fail_min = Number(failMatch[1]); intent.note.push(`유찰 ${failMatch[1]}회+`); }

  // 문서 상태
  if (q.includes("미공개")) {
    if (/(빼|제외|말고)/.test(q)) { intent.filters.document_status = "present"; intent.note.push("문서 있음"); }
    else { intent.filters.document_status = "missing"; intent.note.push("문서 미공개"); }
  }

  // 위험 키워드 제외 / 포함
  intent.filters.exclude_flags = [];
  ["유치권", "법정지상권", "지분", "농지"].forEach((kw) => {
    if (q.includes(kw) && /(제외|빼|말고)/.test(q)) { intent.filters.exclude_flags.push(kw); intent.note.push(`${kw} 제외`); }
  });
  intent.filters.include_flags = [];
  if (q.includes("임차") && /(포함|만)/.test(q)) { intent.filters.include_flags.push("임차"); intent.note.push("임차인 포함"); }

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
  // ── 고급 필터 연동 ──
  if (f.court) arr = arr.filter((it) =>
    (it.court_name || "").includes(f.court) || (it.agency_name || "").includes(f.court));
  if (f.item_group) arr = arr.filter((it) => (it.item_group || "") === f.item_group);
  if (f.fail_min !== undefined) arr = arr.filter((it) => (it.fail_count || 0) >= f.fail_min);
  if (f.document_status === "missing") arr = arr.filter((it) => _docsMissing(it));
  if (f.document_status === "present") arr = arr.filter((it) => !_docsMissing(it));
  if (f.exclude_flags && f.exclude_flags.length)
    arr = arr.filter((it) => !f.exclude_flags.some((kw) => _hasRiskKeyword(it, kw)));
  if (f.include_flags && f.include_flags.length)
    arr = arr.filter((it) => f.include_flags.every((kw) => _hasRiskKeyword(it, kw)));

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

  renderClusters();
  refreshUrgentBanner();
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
    renderAppHome();  // 홈 화면 렌더링
  } catch (e) {
    showError(`mock_dashboard.json 을 불러오지 못했습니다: ${e && e.message ? e.message : e}`);
  }
}

// ── 설정 / 데이터 백업·복원 ─────────────────────────
const BACKUP_VERSION = 1;

function buildBackup() {
  return {
    version: BACKUP_VERSION,
    exported_at: new Date().toISOString(),
    favorites: Array.from(STATE.favorites),
    notes: STATE.notes,
    compare: STATE.compare,
    searches: STATE.recentSearches,
    viewed: STATE.viewed,
    theme: localStorage.getItem(THEME_KEY) || null,
  };
}

function applyBackup(payload, mode) {
  if (!payload || typeof payload !== "object") {
    throw new Error("형식이 잘못된 백업 파일입니다.");
  }
  if (payload.version && payload.version > BACKUP_VERSION) {
    throw new Error("이 백업 파일은 더 새로운 버전입니다. 페이지를 새로고침해 주세요.");
  }
  const merge = mode === "merge";

  // favorites
  if (Array.isArray(payload.favorites)) {
    const incoming = payload.favorites.map(String);
    if (merge) {
      incoming.forEach((id) => STATE.favorites.add(id));
    } else {
      STATE.favorites = new Set(incoming);
    }
    saveFavorites(STATE.favorites);
  }
  // notes
  if (payload.notes && typeof payload.notes === "object" && !Array.isArray(payload.notes)) {
    if (merge) {
      Object.entries(payload.notes).forEach(([k, v]) => {
        if (!v || typeof v.text !== "string") return;
        const existing = STATE.notes[k];
        // 같은 키는 더 최근 updatedAt 가 이김
        if (!existing || (v.updatedAt && (!existing.updatedAt || v.updatedAt > existing.updatedAt))) {
          STATE.notes[k] = { text: v.text, updatedAt: v.updatedAt || new Date().toISOString() };
        }
      });
    } else {
      const cleaned = {};
      Object.entries(payload.notes).forEach(([k, v]) => {
        if (v && typeof v.text === "string") {
          cleaned[k] = { text: v.text, updatedAt: v.updatedAt || new Date().toISOString() };
        }
      });
      STATE.notes = cleaned;
    }
    saveNotes(STATE.notes);
  }
  // compare
  if (Array.isArray(payload.compare)) {
    const incoming = payload.compare.map(String).slice(0, COMPARE_MAX);
    if (merge) {
      const existing = new Set(STATE.compare);
      incoming.forEach((id) => { if (!existing.has(id) && STATE.compare.length < COMPARE_MAX) STATE.compare.push(id); });
    } else {
      STATE.compare = incoming;
    }
    saveCompare(STATE.compare);
  }
  // viewed history
  if (Array.isArray(payload.viewed)) {
    const incoming = payload.viewed
      .filter((x) => x && (typeof x.id === "string" || typeof x.id === "number"))
      .map((x) => ({ id: String(x.id), ts: Number(x.ts) || 0 }));
    if (merge) {
      const seen = new Set(STATE.viewed.map((v) => v.id));
      incoming.forEach((v) => { if (!seen.has(v.id)) STATE.viewed.push(v); });
      STATE.viewed.sort((a, b) => b.ts - a.ts);
      if (STATE.viewed.length > VIEWED_MAX) STATE.viewed.length = VIEWED_MAX;
    } else {
      STATE.viewed = incoming.slice(0, VIEWED_MAX);
    }
    saveViewed(STATE.viewed);
  }
  // searches
  if (Array.isArray(payload.searches)) {
    const incoming = payload.searches.filter((x) => typeof x === "string" && x.trim());
    if (merge) {
      const seen = new Set(STATE.recentSearches);
      incoming.forEach((q) => { if (!seen.has(q)) { STATE.recentSearches.unshift(q); seen.add(q); }});
      if (STATE.recentSearches.length > SEARCHES_MAX) STATE.recentSearches.length = SEARCHES_MAX;
    } else {
      STATE.recentSearches = incoming.slice(0, SEARCHES_MAX);
    }
    saveSearches(STATE.recentSearches);
  }
  // theme
  if (typeof payload.theme === "string" && (payload.theme === "light" || payload.theme === "dark")) {
    applyTheme(payload.theme, true);
  }
}

function clearAllUserData() {
  STATE.favorites = new Set();
  STATE.notes = {};
  STATE.compare = [];
  STATE.recentSearches = [];
  STATE.viewed = [];
  saveFavorites(STATE.favorites);
  saveNotes(STATE.notes);
  saveCompare(STATE.compare);
  saveSearches(STATE.recentSearches);
  saveViewed(STATE.viewed);
}

function renderSettingsStats() {
  const root = $("settings-stats");
  if (!root) return;
  const noteCount = Object.keys(STATE.notes).length;
  root.innerHTML = `
    <div class="stat"><span class="k">★ 관심 매물</span><span class="v">${STATE.favorites.size}</span></div>
    <div class="stat"><span class="k">📝 메모</span><span class="v">${noteCount}</span></div>
    <div class="stat"><span class="k">⇆ 비교 트레이</span><span class="v">${STATE.compare.length} / ${COMPARE_MAX}</span></div>
    <div class="stat"><span class="k">🔍 최근 검색어</span><span class="v">${STATE.recentSearches.length}</span></div>
    <div class="stat"><span class="k">👁 최근 본 매물</span><span class="v">${STATE.viewed.length} / ${VIEWED_MAX}</span></div>
  `;
}

function renderMemoList(filterText) {
  const root = $("memo-list");
  if (!root) return;
  const q = (filterText || "").trim().toLowerCase();
  const entries = Object.entries(STATE.notes)
    .map(([id, n]) => {
      const it = STATE.items.find((x) => String(x.id) === String(id));
      return {
        id,
        title: (it && (it.title || it.address)) || `#${id}`,
        text: (n && n.text) || "",
        updatedAt: (n && n.updatedAt) || "",
      };
    })
    .filter((e) => e.text);
  if (!entries.length) {
    root.innerHTML = `<div class="memo-empty">아직 메모가 없어요. 매물 상세 모달의 '내 메모' 에 적으면 여기 모입니다.</div>`;
    return;
  }
  let filtered = entries;
  if (q) {
    filtered = entries.filter((e) =>
      e.title.toLowerCase().includes(q) || e.text.toLowerCase().includes(q)
    );
  }
  // 최근 수정 desc
  filtered.sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
  if (!filtered.length) {
    root.innerHTML = `<div class="memo-empty">'${escapeHtml(q)}' 검색 결과가 없어요.</div>`;
    return;
  }
  root.innerHTML = filtered.map((e) =>
    `<a class="memo-row" data-memo-id="${escapeHtml(e.id)}" tabindex="0" role="button">
       <span class="memo-title">${escapeHtml(e.title)}</span>
       <span class="memo-snippet">${escapeHtml(e.text)}</span>
       <span class="memo-when">${escapeHtml(formatRelative(e.updatedAt))}</span>
     </a>`
  ).join("");
  root.querySelectorAll(".memo-row").forEach((row) => {
    bindTap(row, () => {
      const id = row.dataset.memoId;
      closeSettingsModal();
      openDetailById(id);
    });
  });
}

function openSettingsModal() {
  renderSettingsStats();
  renderMemoList("");
  const search = $("memo-search");
  if (search) {
    search.value = "";
    search.oninput = () => renderMemoList(search.value);
  }
  $("settings-modal").hidden = false;
  document.body.style.overflow = "hidden";
}
function closeSettingsModal() {
  $("settings-modal").hidden = true;
  if (allModalsClosed()) document.body.style.overflow = "";
}

function allModalsClosed() {
  return $("detail-modal").hidden &&
         $("compare-modal").hidden &&
         $("kbd-modal").hidden &&
         $("settings-modal").hidden &&
         $("about-modal").hidden;
}

function openAboutModal() {
  $("about-modal").hidden = false;
  document.body.style.overflow = "hidden";
}
function closeAboutModal() {
  $("about-modal").hidden = true;
  if (allModalsClosed()) document.body.style.overflow = "";
}

function bindAbout() {
  const openBtn = $("about-btn");
  if (openBtn) openBtn.addEventListener("click", openAboutModal);
  const closeBtn = $("about-close");
  if (closeBtn) closeBtn.addEventListener("click", closeAboutModal);
  const modal = $("about-modal");
  if (modal) modal.addEventListener("click", (e) => {
    if (e.target instanceof HTMLElement && e.target.dataset.close === "1") closeAboutModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("about-modal").hidden) closeAboutModal();
  });
}

function bindSettings() {
  const openBtn = $("settings-btn");
  if (openBtn) openBtn.addEventListener("click", openSettingsModal);

  const closeBtn = $("settings-close");
  if (closeBtn) closeBtn.addEventListener("click", closeSettingsModal);
  const modal = $("settings-modal");
  if (modal) modal.addEventListener("click", (e) => {
    if (e.target instanceof HTMLElement && e.target.dataset.close === "1") closeSettingsModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("settings-modal").hidden) closeSettingsModal();
  });

  // 백업 다운로드
  const exportBtn = $("settings-export");
  if (exportBtn) exportBtn.addEventListener("click", () => {
    const payload = buildBackup();
    const fname = `auction_backup_${timestampSlug()}.json`;
    downloadBlob(JSON.stringify(payload, null, 2), fname,
                 "application/json;charset=utf-8");
    showToast("백업 파일을 다운로드했어요.", null);
    setTimeout(hideToast, 2500);
  });

  // 복원 업로드
  const importBtn = $("settings-import");
  const importFile = $("settings-import-file");
  if (importBtn && importFile) {
    importBtn.addEventListener("click", () => importFile.click());
    importFile.addEventListener("change", async () => {
      const file = importFile.files && importFile.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const payload = JSON.parse(text);
        const mode = (document.querySelector('input[name="restore-mode"]:checked') || {}).value || "overwrite";
        applyBackup(payload, mode);
        renderSettingsStats();
        // 화면 즉시 갱신
        renderQuickChips();
        applyFilters();
        renderCompareTray();
        showToast(`복원 완료 (${mode === "merge" ? "추가" : "덮어쓰기"})`, null);
        setTimeout(hideToast, 3000);
      } catch (e) {
        showToast(`복원 실패: ${e && e.message ? e.message : e}`, null);
        setTimeout(hideToast, 4000);
      } finally {
        importFile.value = "";
      }
    });
  }

  // 전체 지우기
  const clearBtn = $("settings-clear-all");
  if (clearBtn) clearBtn.addEventListener("click", () => {
    if (!confirm("정말 관심·메모·비교·최근 검색어를 모두 지울까요? 이 작업은 되돌릴 수 없어요.")) return;
    clearAllUserData();
    renderSettingsStats();
    renderQuickChips();
    applyFilters();
    renderCompareTray();
    showToast("내 데이터를 모두 비웠어요.", null);
    setTimeout(hideToast, 2500);
  });
}

// ── 매물 카드 키보드 네비게이션 (j/k, Up/Down, Enter) ─────
let CARD_FOCUS_IDX = -1;

function _allCardsInView() {
  return Array.from(document.querySelectorAll("#items-card-view .item-card"));
}

function focusCardAt(idx) {
  const cards = _allCardsInView();
  if (!cards.length) { CARD_FOCUS_IDX = -1; return; }
  const clamped = Math.max(0, Math.min(cards.length - 1, idx));
  cards.forEach((c) => c.classList.remove("kbd-focused"));
  const target = cards[clamped];
  target.classList.add("kbd-focused");
  target.scrollIntoView({ block: "nearest", behavior: "smooth" });
  try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
  CARD_FOCUS_IDX = clamped;
}

function resetCardFocus() {
  CARD_FOCUS_IDX = -1;
  document.querySelectorAll("#items-card-view .item-card.kbd-focused")
    .forEach((c) => c.classList.remove("kbd-focused"));
}

function bindCardKbdNav() {
  document.addEventListener("keydown", (e) => {
    const anyModalOpen = !$("detail-modal").hidden ||
                         !$("compare-modal").hidden ||
                         !$("kbd-modal").hidden ||
                         !$("settings-modal").hidden ||
                         !$("about-modal").hidden;
    if (anyModalOpen) return;
    if (isTextFocus(e.target)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (STATE.view !== "card") return; // 테이블 보기에선 비활성

    if (e.key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      focusCardAt(CARD_FOCUS_IDX < 0 ? 0 : CARD_FOCUS_IDX + 1);
    } else if (e.key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      focusCardAt(Math.max(0, CARD_FOCUS_IDX < 0 ? 0 : CARD_FOCUS_IDX - 1));
    } else if (e.key === "Enter" && CARD_FOCUS_IDX >= 0) {
      const cards = _allCardsInView();
      const target = cards[CARD_FOCUS_IDX];
      if (target && target.dataset.itemId) {
        e.preventDefault();
        openDetailById(target.dataset.itemId);
      }
    }
  });
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

/* ★ 매물 중 D-3 이내가 있으면 배너 노출 */
let URGENT_BANNER_DISMISSED = false;

function refreshUrgentBanner() {
  const banner = $("urgent-banner");
  if (!banner) return;
  if (URGENT_BANNER_DISMISSED) { banner.hidden = true; return; }
  if (!STATE.favorites.size) { banner.hidden = true; return; }
  const favItems = STATE.items.filter((it) => STATE.favorites.has(String(it.id)));
  const urgent = favItems.filter((it) =>
    it.days_left !== null && it.days_left !== undefined &&
    it.days_left >= 0 && it.days_left <= 3
  );
  if (!urgent.length) { banner.hidden = true; return; }
  const msg = $("urgent-banner-msg");
  if (msg) {
    msg.textContent = `★ 관심 매물 ${favItems.length}건 중 ${urgent.length}건이 D-3 이내 임박입니다.`;
  }
  banner.hidden = false;
}

function bindUrgentBanner() {
  const action = $("urgent-banner-action");
  if (action) {
    action.addEventListener("click", () => {
      // 관심 칩 + 기일 임박 정렬
      STATE.filters = JSON.parse(JSON.stringify(FILTER_DEFAULTS));
      STATE.filters.chip = "favorites";
      STATE.filters.sort = "due_asc";
      syncControlsFromState();
      renderQuickChips();
      applyFilters();
      const items = $("section-items");
      if (items) items.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  const close = $("urgent-banner-close");
  if (close) {
    close.addEventListener("click", () => {
      URGENT_BANNER_DISMISSED = true;
      $("urgent-banner").hidden = true;
    });
  }
}

function bindScrollTop() {
  const btn = $("scroll-top");
  if (!btn) return;
  let raf = 0;
  const update = () => {
    raf = 0;
    const y = window.scrollY || window.pageYOffset || 0;
    const show = y > 600;
    if (show && btn.hidden) btn.hidden = false;
    else if (!show && !btn.hidden) btn.hidden = true;
  };
  window.addEventListener("scroll", () => {
    if (raf) return;
    raf = requestAnimationFrame(update);
  }, { passive: true });
  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  // Home 키 단축
  document.addEventListener("keydown", (e) => {
    if (e.key === "Home" && !isTextFocus(e.target)) {
      const anyModalOpen = !$("detail-modal").hidden ||
                           !$("compare-modal").hidden ||
                           !$("kbd-modal").hidden ||
                           !$("settings-modal").hidden ||
                           !$("about-modal").hidden;
      if (!anyModalOpen) {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }
  });
  update();
}

function setupStickyOffset() {
  const sec = document.querySelector(".search-section");
  if (!sec) return;
  const update = () => {
    document.documentElement.style.setProperty("--items-head-top", `${sec.offsetHeight}px`);
  };
  update();
  if (window.ResizeObserver) {
    new ResizeObserver(update).observe(sec);
  } else {
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
  }
}

// ── 홈 화면 (초보자 친화형) ───────────────────────
let BEGINNER_MODE_ENABLED = false;

function getBeginnerfMode() {
  try {
    const saved = localStorage.getItem("auction:beginner:v1");
    return saved === "true";
  } catch {
    return false;
  }
}

function setBeginnerfMode(enabled) {
  BEGINNER_MODE_ENABLED = !!enabled;
  try {
    localStorage.setItem("auction:beginner:v1", enabled ? "true" : "false");
  } catch {}
  applyFilters();  // 필터 재적용
}

// 추천등급 → 초보자용 라벨
const BEGINNER_GRADE_LABEL = {
  A: "초보자 검토 가능",
  B: "조심해서 검토",
  C: "보류 후보",
  D: "낮은 우선순위",
  X: "초보자 비추천",
};

function renderAppHome() {
  // AI 브리핑 텍스트 업데이트
  const briefing = STATE.data && STATE.data.briefing;
  const briefingBox = $("app-briefing-text");
  if (briefingBox && briefing && briefing.summary) {
    const lines = briefing.summary.split("\n");
    briefingBox.textContent = lines[0] || "오늘의 경매·공매 분석 결과입니다";
  }

  renderStatusCards();
  renderDataTimestamp();
  renderTodayItems();
}

function renderDataTimestamp() {
  const node = $("app-data-ts");
  if (!node) return;
  const s = (STATE.data && STATE.data.summary) || {};
  const raw = s.data_timestamp || (STATE.data && STATE.data.generated_at) || "";
  let text = "데이터 기준: 알 수 없음";
  if (raw) {
    const d = new Date(raw);
    if (!isNaN(d.getTime())) {
      const pad = (n) => String(n).padStart(2, "0");
      text = `데이터 기준: ${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
        + `${pad(d.getHours())}:${pad(d.getMinutes())} (mock)`;
    } else {
      text = `데이터 기준: ${escapeHtml(String(raw))} (mock)`;
    }
  }
  node.textContent = text;
}

function renderStatusCards() {
  const grid = $("status-grid");
  if (!grid) return;
  clearChildren(grid);
  const s = (STATE.data && STATE.data.summary) || {};
  const gradeA = (s.grade_distribution && s.grade_distribution.A != null)
    ? s.grade_distribution.A
    : STATE.items.filter((it) => it.recommendation_grade === "A").length;
  const highRisk = (s.high_risk_items != null)
    ? s.high_risk_items
    : (s.risk_distribution && s.risk_distribution.high != null
        ? s.risk_distribution.high
        : STATE.items.filter((it) => it.risk_level === "high").length);
  const cards = [
    { label: "전체 물건", value: s.total_items ?? STATE.items.length, cls: "stat-total" },
    { label: "분석 완료", value: s.analyzed_items ?? STATE.items.length, cls: "stat-analyzed" },
    { label: "추천 후보", value: s.recommended_items ?? "-", cls: "stat-rec" },
    { label: "고위험 후보", value: highRisk, cls: "stat-risk" },
    { label: "입찰임박", value: s.urgent_items ?? "-", cls: "stat-urgent" },
    { label: "A등급 후보", value: gradeA, cls: "stat-gradea" },
  ];
  cards.forEach((c) => {
    const card = el(
      `<div class="status-card ${c.cls}">
         <span class="status-value">${escapeHtml(String(c.value))}</span>
         <span class="status-label">${escapeHtml(c.label)}</span>
       </div>`
    );
    grid.appendChild(card);
  });
}

function renderTodayItems() {
  const list = $("today-items-list");
  if (!list) return;
  clearChildren(list);

  // 오늘 우선 볼 물건: 초보자 친화 물건 중 예상차익 큰 순 → 입찰기일 임박 순, 3개
  const candidates = STATE.items
    .filter((it) => it.beginner_friendly || _is_beginner_friendly(it))
    .sort((a, b) => {
      const p = (b.expected_profit || 0) - (a.expected_profit || 0);
      if (p !== 0) return p;
      return (a.days_left ?? 999) - (b.days_left ?? 999);
    })
    .slice(0, 3);

  if (!candidates.length) {
    list.appendChild(el(`<p class="caption">초보자에게 바로 권할 물건이 오늘은 없어요. 전체 물건을 탐색해 보세요.</p>`));
    return;
  }

  list.appendChild(el(`<p class="today-lead">AI가 오늘 먼저 볼 물건을 골랐어요.</p>`));

  candidates.forEach((item) => {
    const grade = item.recommendation_grade || "B";
    const label = BEGINNER_GRADE_LABEL[grade] || "검토 후보";
    const caution = item.simple_risk_summary || item.simple_next_action || "기본 확인 필요";
    const card = el(
      `<div class="today-item">
         <div class="today-item-tags">
           <span class="grade-pill grade-${escapeHtml(grade)}">${escapeHtml(grade)}</span>
           <span class="beginner-pill">🎓 ${escapeHtml(label)}</span>
         </div>
         <div class="today-item-title">${escapeHtml(item.title || item.address || "주소 미상")}</div>
         <div class="today-item-addr">${escapeHtml(item.address || "")} · ${escapeHtml(item.item_type || "")}</div>
         <div class="today-item-desc">💰 예상 시세차익 ${fmtMan(item.expected_profit)}</div>
         <div class="today-item-caution">⚠ 조심할 점: ${escapeHtml(caution)}</div>
         <button class="today-item-detail" type="button">상세보기 →</button>
       </div>`
    );
    bindTap(card.querySelector(".today-item-detail"), () => openDetailById(item.id));
    bindTap(card, () => openDetailById(item.id));
    list.appendChild(card);
  });
}

function scrollToSection(id) {
  const sec = $(id);
  if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
  return sec;
}

// 카테고리 → 데모 데이터에 존재하는 물건종류 매핑
const CATEGORY_TYPE_MAP = { 주택: "빌라" };

function selectCategory(category) {
  const type = CATEGORY_TYPE_MAP[category] || category;
  STATE.filters.chip = "all";
  STATE.filters.item_type = type;
  const sel = $("f-type");
  if (sel) {
    const has = Array.from(sel.options).some((o) => o.value === type);
    sel.value = has ? type : "";
    if (!has) STATE.filters.item_type = "";  // 데모에 없는 종류면 전체로
  }
  applyFilters();
  scrollToSection("section-items");
  if (!STATE.filters.item_type) {
    showToast(`데모 데이터에는 '${category}' 물건이 아직 없어요. 전체 물건을 보여드릴게요.`, null);
    setTimeout(hideToast, 2800);
  }
}

// 유틸리티 메뉴 → 기존 섹션 연결
const UTIL_ACTIONS = {
  news:       () => scrollToSection("section-briefing"),
  rights:     () => openGlossary(),
  quiz:       () => openGlossary(),
  simulation: () => scrollToSection("section-recommendations"),
  results:    () => scrollToSection("section-items"),
  map:        () => scrollToSection("section-charts"),
  calendar:   () => {
    STATE.filters.sort = "due_asc";
    const sortSel = $("f-sort"); if (sortSel) sortSel.value = "due_asc";
    applyFilters();
    scrollToSection("section-items");
  },
  loan:       () => scrollToSection("section-recommendations"),
};

function bindAppHome() {
  // 초보자 모드 토글
  const toggle = document.getElementById("beginner-mode-toggle");
  if (toggle) {
    toggle.checked = getBeginnerfMode();
    toggle.addEventListener("change", () => {
      setBeginnerfMode(toggle.checked);
      showToast(toggle.checked
        ? "초보자 모드 ON — 위험·복잡 물건을 숨기고 A/B 주거용만 보여줘요."
        : "초보자 모드 OFF — 모든 물건을 보여줘요.", null);
      setTimeout(hideToast, 2500);
    });
  }

  // 카테고리 버튼 클릭
  document.querySelectorAll(".cat-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectCategory(btn.dataset.category));
  });

  // 유틸리티 버튼 클릭 → 기존 섹션/기능 연결
  document.querySelectorAll(".util-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fn = UTIL_ACTIONS[btn.dataset.utility];
      if (fn) fn();
    });
  });

  // AI 물건 검색 → AI 에이전트 검색 섹션으로 스크롤
  const aiSearchBtn = document.getElementById("btn-ai-search");
  if (aiSearchBtn) {
    aiSearchBtn.addEventListener("click", () => {
      scrollToSection("section-agent-search");
      const aq = $("agent-q");
      if (aq) setTimeout(() => aq.focus(), 350);
    });
  }

  // AI 물건 분석 → 추천 TOP 5 섹션으로 스크롤
  const aiAnalyzeBtn = document.getElementById("btn-ai-analyze");
  if (aiAnalyzeBtn) {
    aiAnalyzeBtn.addEventListener("click", () => scrollToSection("section-recommendations"));
  }

  // 전체 탐색 버튼
  const exploreBtn = document.getElementById("btn-explore");
  if (exploreBtn) {
    exploreBtn.addEventListener("click", () => scrollToSection("section-items"));
  }

  // 빠른 진입 버튼
  document.querySelectorAll(".quicknav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fn = QUICKNAV_ACTIONS[btn.dataset.quick];
      if (fn) fn();
    });
  });

  bindGlossary();
}

// 필터 섹션을 펼치고 특정 select 로 포커스 이동
function openFiltersAndFocus(selectId) {
  const body = $("filter-body");
  const toggle = $("filter-toggle");
  if (body && body.hidden && toggle) toggle.click();
  scrollToSection("section-filters");
  const sel = $(selectId);
  if (sel) setTimeout(() => { sel.focus(); }, 350);
}

// 칩 기반 빠른 필터 적용 + 결과로 스크롤
function applyChipAndScroll(chipId) {
  STATE.filters.chip = chipId;
  if (typeof renderQuickChips === "function") renderQuickChips();
  applyFilters();
  scrollToSection("section-items");
}

// 빠른 진입 버튼 → 섹션 스크롤 / 필터 적용
const QUICKNAV_ACTIONS = {
  search: () => {
    scrollToSection("search-section");
    const q = $("q-input");
    if (q) setTimeout(() => q.focus(), 350);
  },
  court: () => {
    openFiltersAndFocus("f-region");
    showToast("데모 데이터에는 법원 구분이 없어 지역 필터로 안내합니다.", null);
    setTimeout(hideToast, 2800);
  },
  region: () => openFiltersAndFocus("f-region"),
  type:   () => openFiltersAndFocus("f-type"),
  rec:    () => scrollToSection("section-recommendations"),
  urgent: () => applyChipAndScroll("imminent"),
  risk:   () => applyChipAndScroll("high_risk"),
  ai:     () => {
    scrollToSection("section-agent-search");
    const aq = $("agent-q");
    if (aq) setTimeout(() => aq.focus(), 350);
  },
};

// ── 용어 쉽게 설명 (초보자 권리분석 용어집) ──────────
const GLOSSARY = {
  "유치권": "건설업자나 자재 공급자가 못 받은 대금을 담보로 물건을 점유할 수 있는 권리. 낙찰 후 새 주인이 이 돈을 떠안아야 할 수 있어요.",
  "법정지상권": "토지와 건물 주인이 다를 때, 건물 주인이 그 땅을 계속 쓸 수 있는 권리. 건물을 낙찰받아도 토지 사용료를 계속 내야 할 수 있어요.",
  "대항력": "임차인이 등기에 없어도 새 주인에게 권리를 주장할 수 있는 힘. 임차인이 살고 있으면 보증금을 떠안아야 할 수 있어요.",
  "선순위임차인": "지금 주인보다 먼저 계약한 임차인. 낙찰 후에도 그 보증금을 먼저 돌려줘야 할 수 있어요.",
  "지분매각": "물건 전체가 아니라 일부 지분만 파는 경우. 권리관계가 복잡하고 분쟁 가능성이 높아 초보자에게 어려워요.",
  "농지취득자격증명": "농지를 사려면 필요한 자격 증명서. 없으면 낙찰받아도 농지로 못 쓸 수 있어요.",
  "분묘기지권": "남의 땅에 무덤을 쓸 수 있는 권리. 땅 주인이 바뀌어도 그 권리는 계속 유지돼요.",
  "명도": "사는 사람이나 점유자를 내보내는 절차. 시간과 비용이 들고 법원 집행이 필요할 수 있어요.",
  "말소기준권리": "이 권리를 기준으로 뒤에 붙은 권리들이 낙찰 후 사라지는, 권리분석의 기준점이에요.",
  "매각물건명세서": "법원이 물건 상태·권리를 정리해 공개하는 공식 문서. 가장 믿을 수 있는 정보예요.",
  "현황조사서": "법원이 직접 현장을 조사해 점유 상태·하자 등을 기록한 보고서예요.",
  "감정평가서": "감정사가 매긴 시장 가치 문서. 경매 최저가의 근거가 되는 가격이에요.",
};

function renderGlossary(filter) {
  const list = $("glossary-list");
  if (!list) return;
  clearChildren(list);
  const q = (filter || "").trim().toLowerCase();
  const entries = Object.entries(GLOSSARY).filter(
    ([term, exp]) => !q || term.toLowerCase().includes(q) || exp.toLowerCase().includes(q)
  );
  if (!entries.length) {
    list.appendChild(el(`<p class="caption">검색 결과가 없어요.</p>`));
    return;
  }
  entries.forEach(([term, exp]) => {
    list.appendChild(el(
      `<div class="glossary-item">
         <div class="glossary-term">${escapeHtml(term)}</div>
         <div class="glossary-exp">${escapeHtml(exp)}</div>
       </div>`
    ));
  });
}

function openGlossary(term) {
  const modal = $("glossary-modal");
  if (!modal) return;
  const search = $("glossary-search");
  if (search) search.value = term || "";
  renderGlossary(term || "");
  modal.hidden = false;
}

function bindGlossary() {
  const modal = $("glossary-modal");
  if (!modal) return;
  const hide = () => { modal.hidden = true; };
  const close = $("glossary-close");
  if (close) close.addEventListener("click", hide);
  modal.addEventListener("click", (e) => {
    if (e.target instanceof HTMLElement && e.target.dataset.close === "1") hide();
  });
  document.addEventListener("keydown", (e) => {
    if (!modal.hidden && e.key === "Escape") hide();
  });
  const search = $("glossary-search");
  if (search) search.addEventListener("input", () => renderGlossary(search.value));
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
  bindSettings();
  bindAbout();
  bindCardKbdNav();
  bindSelectionMode();
  bindUrgentBanner();
  bindDensity();
  bindScrollTop();
  bindVoiceSearch();
  bindMoreButton();
  bindPwa();
  bindAppHome();  // 홈 화면 바인딩 추가
  setupStickyOffset();
  BEGINNER_MODE_ENABLED = getBeginnerfMode();  // 초보자 모드 상태 복원
  load();
});
