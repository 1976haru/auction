"""
modules/price/molit_api.py
국토교통부 실거래가 API 클라이언트
API 키: data.go.kr 에서 무료 발급
"""
import requests
import json
from datetime import datetime, timedelta
from core.config import PUBLIC_DATA_KEY
from core.database import get_connection
from core.logger import log

# 아파트 실거래가 엔드포인트
APT_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
# 연립·다세대 실거래가
VILLA_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcRHTradeDev/getRTMSDataSvcRHTradeDev"


def get_region_code(si: str, gu: str) -> str:
    """시·구 이름으로 법정동 코드 앞 5자리 반환 (간략 매핑)"""
    mapping = {
        ("서울특별시", "강남구"): "11680",
        ("서울특별시", "마포구"): "11440",
        ("서울특별시", "성동구"): "11200",
        ("서울특별시", "서초구"): "11650",
        ("서울특별시", "송파구"): "11710",
        ("서울특별시", "노원구"): "11350",
        ("서울특별시", "강동구"): "11740",
        ("서울특별시", "용산구"): "11170",
        ("서울특별시", "영등포구"): "11560",
        ("서울특별시", "관악구"): "11620",
        ("경기도", "수원시"): "41110",
        ("경기도", "성남시"): "41130",
        ("경기도", "고양시"): "41280",
    }
    return mapping.get((si, gu), "")


def fetch_apt_trades(region_code: str, ym: str) -> list[dict]:
    """
    아파트 실거래가 조회.
    region_code: 법정동코드 5자리
    ym: 조회 년월 (예: "202404")
    """
    if not PUBLIC_DATA_KEY:
        log.warning("[실거래가] PUBLIC_DATA_KEY 없음 — 빈 결과 반환")
        return []

    params = {
        "serviceKey": PUBLIC_DATA_KEY,
        "LAWD_CD": region_code,
        "DEAL_YMD": ym,
        "numOfRows": 100,
        "pageNo": 1,
    }
    try:
        resp = requests.get(APT_URL, params=params, timeout=15)
        resp.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        items = []
        for item in root.iter("item"):
            def g(tag):
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else ""
            try:
                price_str = g("거래금액").replace(",", "").replace(" ", "")
                items.append({
                    "complex_name": g("아파트"),
                    "area_m2":      float(g("전용면적") or 0),
                    "trade_price":  int(price_str) if price_str else 0,
                    "trade_date":   f"{g('년')}-{g('월').zfill(2)}-{g('일').zfill(2)}",
                    "floor":        g("층"),
                    "address_dong": g("법정동"),
                })
            except (ValueError, TypeError):
                continue
        log.info(f"[실거래가] {region_code}/{ym} → {len(items)}건")
        return items

    except Exception as e:
        log.error(f"[실거래가] API 오류: {e}")
        return []


def get_avg_price(item_id: int, address_si: str, address_gu: str,
                  area_m2: float, months: int = 6) -> dict:
    """
    해당 물건 주변 실거래가 평균 계산.
    반환: {avg_price, count, min_price, max_price, source}
    """
    region_code = get_region_code(address_si, address_gu)
    if not region_code:
        return {"avg_price": 0, "count": 0, "note": "지역코드 매핑 없음"}

    all_trades = []
    now = datetime.now()
    for i in range(months):
        ym = (now - timedelta(days=30 * i)).strftime("%Y%m")
        trades = fetch_apt_trades(region_code, ym)
        # 비슷한 면적(±10㎡) 필터
        filtered = [t for t in trades if abs(t["area_m2"] - area_m2) <= 10]
        all_trades.extend(filtered)

    if not all_trades:
        return {"avg_price": 0, "count": 0, "note": "실거래 데이터 없음"}

    prices = [t["trade_price"] for t in all_trades if t["trade_price"] > 0]
    avg    = int(sum(prices) / len(prices)) if prices else 0

    # DB 저장
    conn = get_connection()
    c = conn.cursor()
    for t in all_trades[:20]:  # 최대 20건만 저장
        c.execute("""
            INSERT OR IGNORE INTO price_records
                (item_id, address_dong, complex_name, area_m2, trade_price, trade_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (item_id, t.get("address_dong"), t.get("complex_name"),
              t.get("area_m2"), t.get("trade_price"), t.get("trade_date")))
    conn.commit()
    conn.close()

    return {
        "avg_price": avg,
        "count":     len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
        "source":    "molit",
    }
