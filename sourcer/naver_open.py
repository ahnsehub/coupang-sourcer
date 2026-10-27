"""네이버 데이터랩 검색어 트렌드 (급상승·계절성 태그용).

- 네이버 쇼핑 검색 API는 2026-07-31 종료되어 사용하지 않습니다.
- 검색어 트렌드는 NAVER API HUB(네이버클라우드)로 이관됨. HUB 키로 먼저 시도하고,
  실패(401/403/404)하면 기존 개발자센터 엔드포인트로 재시도합니다(개발자센터는 2027-06-30까지).
"""
import datetime as dt

import requests

HUB_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
LEGACY_URL = "https://openapi.naver.com/v1/datalab/search"


def search_trend(keywords: list[str], client_id: str, client_secret: str) -> dict[str, list[float]]:
    """최근 12개월 월별 검색 추이(상대값). 한 번에 최대 5개 키워드."""
    end = dt.date.today().replace(day=1) - dt.timedelta(days=1)  # 지난달 말
    start = (end.replace(day=1) - dt.timedelta(days=330)).replace(day=1)
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "month",
        "keywordGroups": [{"groupName": k, "keywords": [k]} for k in keywords[:5]],
    }
    attempts = [
        (HUB_URL, {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}),
        (LEGACY_URL, {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}),
    ]
    last = None
    for url, h in attempts:
        r = requests.post(url, json=body, headers={**h, "Content-Type": "application/json"}, timeout=15)
        if r.status_code in (401, 403, 404):
            last = r
            continue
        r.raise_for_status()
        return {g["title"]: [d["ratio"] for d in g["data"]] for g in r.json().get("results", [])}
    last.raise_for_status()
    return {}
