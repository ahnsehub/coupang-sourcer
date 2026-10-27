"""네이버 검색광고 API - 키워드도구(연관키워드 + 월간 검색량)."""
import base64
import hashlib
import hmac
import time

import requests

BASE_URL = "https://api.searchad.naver.com"


def _signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _headers(method: str, uri: str, api_key: str, secret_key: str, customer_id: str) -> dict:
    ts = str(round(time.time() * 1000))
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": ts,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _signature(ts, method, uri, secret_key),
    }


def _to_int(v) -> int:
    # 검색량이 적으면 "< 10" 문자열로 내려옴
    if isinstance(v, (int, float)):
        return int(v)
    return 5 if isinstance(v, str) and "<" in v else int(str(v).replace(",", "") or 0)


def related_keywords(hints: list[str], api_key: str, secret_key: str, customer_id: str) -> list[dict]:
    """힌트 키워드(최대 5개)로 연관 키워드 + 월간 검색량(PC+모바일)을 가져온다."""
    uri = "/keywordstool"
    hints = [h.replace(" ", "") for h in hints if h.strip()][:5]
    params = {"hintKeywords": ",".join(hints), "showDetail": "1"}
    r = requests.get(BASE_URL + uri, params=params,
                     headers=_headers("GET", uri, api_key, secret_key, customer_id), timeout=20)
    r.raise_for_status()
    out = []
    for row in r.json().get("keywordList", []):
        pc, mo = _to_int(row.get("monthlyPcQcCnt", 0)), _to_int(row.get("monthlyMobileQcCnt", 0))
        out.append({
            "keyword": row["relKeyword"],
            "search_pc": pc,
            "search_mobile": mo,
            "search_total": pc + mo,
            "ad_competition": row.get("compIdx", ""),  # 낮음/중간/높음 (광고 경쟁도)
        })
    return out
