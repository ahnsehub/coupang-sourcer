"""(선택) Claude API로 키워드별 소싱 코멘트 생성. ANTHROPIC_API_KEY 가 있을 때만 동작."""
import json

import requests


def sourcing_comment(row: dict, products: list[dict], api_key: str, model: str) -> str:
    brief = {
        "키워드": row["keyword"], "월검색량": row["search_total"], "추정월매출": row["total_revenue"],
        "평균가": row["avg_price"], "효자상품리뷰": row["hero_reviews"], "로켓비율": row["rocket_share"],
        "광고경쟁도": row.get("ad_competition"), "태그": row["tags"], "등급": row["grade"],
        "상위상품": [{k: p[k] for k in ("name", "price", "reviews", "rocket")} for p in products[:5]],
    }
    prompt = ("당신은 쿠팡 셀러 소싱 컨설턴트입니다. 아래 데이터(판매량·매출은 검색량 기반 추정치)를 보고 "
              "한국어 3줄 이내로: ①진입 판단 ②차별화 포인트(옵션·구성·가격대) ③주의할 리스크를 써주세요. "
              "데이터에 없는 사실은 지어내지 마세요.\n" + json.dumps(brief, ensure_ascii=False))
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"]).strip()
