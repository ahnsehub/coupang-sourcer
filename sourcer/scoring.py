"""판매량 추정 · 점수 · 등급 · 태그 계산 (모두 '추정치'입니다)."""
import math

# 쿠팡 자연검색 순위별 구매 점유율(가정치). 상위 10개 합 ≈ 0.8
RANK_SHARE = [0.20, 0.13, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.04, 0.03]

TIERS = {
    "beginner": {"label": "초보 키워드", "badge": "입문추천", "min_rev": 3_000_000, "max_rev": 10_000_000,
                 "desc": "월매출 300만~1,000만 · 소자본으로 시작하기 좋은 안전한 시장", "search": (1_000, 40_000)},
    "mid": {"label": "중수 키워드", "badge": "안정매출", "min_rev": 10_000_000, "max_rev": 30_000_000,
            "desc": "월매출 1,000만~3,000만 · 매출 규모가 검증된 중급 시장", "search": (5_000, 120_000)},
    "pro": {"label": "고수 키워드", "badge": "고수익", "min_rev": 30_000_000, "max_rev": None,
            "desc": "월매출 3,000만+ · 큰 매출을 노리는 경쟁 시장", "search": (15_000, 2_000_000)},
    "trend": {"label": "트렌드 키워드", "badge": "급성장", "min_rev": 30_000_000, "max_rev": None, "max_top_review": 50,
              "desc": "리뷰 50 이하 + 월매출 3,000만+ · 리뷰가 적지만 매출이 터지는 신규 시장", "search": (15_000, 2_000_000)},
}

ALL_TAGS = ["급상승", "신규", "블루오션", "계절성", "로켓공백", "고단가"]


def estimate_products(products: list[dict], search_total: int, purchase_rate: float, coupang_ratio: float):
    """키워드 월 검색량 → 월 구매수 추정 → 순위별 점유율로 상품별 월판매/월매출 배분."""
    kw_purchases = search_total * coupang_ratio * purchase_rate
    for p, share in zip(products, RANK_SHARE):
        p["est_sales"] = round(kw_purchases * share)
        p["est_revenue"] = p["est_sales"] * p["price"]
    return products


def _clip(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _log_scale(v, v0, v100):
    """v0 → 0점, v100 → 100점 (로그 스케일)."""
    if v <= 0:
        return 0.0
    return _clip((math.log10(v) - math.log10(v0)) / (math.log10(v100) - math.log10(v0)) * 100)


def analyze(kw: dict, products: list[dict], trend: list[float] | None, shop_total: int | None,
            tier: str = "beginner") -> dict:
    """키워드 단위 지표 + 점수(0~100) + 등급 + 태그. 수요 점수는 선택한 티어의 매출 구간 기준."""
    top = products[:10]
    total_sales = sum(p.get("est_sales", 0) for p in top)
    total_rev = sum(p.get("est_revenue", 0) for p in top)
    total_reviews = sum(p["reviews"] for p in top)
    prices = [p["price"] for p in top if p["price"]]
    avg_price = round(sum(prices) / len(prices)) if prices else 0
    rocket_share = (sum(p["rocket"] for p in top) / len(top)) if top else 0
    hero = max(top, key=lambda p: p.get("est_revenue", 0)) if top else None  # 효자상품
    hero_reviews = hero["reviews"] if hero else 0
    # 경쟁도: 네이버 광고 경쟁도(낮음/중간/높음) + 쿠팡 상위10 리뷰 밀도 (네이버 쇼핑 API 종료로 상품수 대신 사용)
    ad_comp = {"낮음": 85, "중간": 55, "높음": 25}.get(kw.get("ad_competition", ""), 50)
    review_density = 100 - _log_scale(max(total_reviews, 1), 100, 20_000)

    t = TIERS[tier]
    s_demand = _log_scale(total_rev, t["min_rev"] / 3, t["max_rev"] or t["min_rev"] * 5)
    s_entry = 100 - _log_scale(max(hero_reviews, 1), 30, 5_000)
    s_comp = 0.5 * ad_comp + 0.5 * review_density
    s_rocket = (1 - rocket_share) * 100
    s_price = _log_scale(avg_price, 3_000, 50_000)
    score = round(0.25 * s_demand + 0.25 * s_entry + 0.20 * s_comp + 0.15 * s_rocket + 0.15 * s_price, 1)
    grade = "S+" if score >= 80 else "S" if score >= 70 else "A" if score >= 58 else "B"

    tags = []
    if trend and len(trend) >= 4:
        prev = sum(trend[-4:-1]) / 3
        if prev > 0 and trend[-1] / prev >= 1.3:
            tags.append("급상승")
        lo, hi = min(trend), max(trend)
        if lo > 0 and hi / lo >= 3:
            tags.append("계절성")
    if hero and hero_reviews <= 50:
        tags.append("신규")
    if kw.get("ad_competition") == "낮음" and total_reviews < 1_000 and kw["search_total"] >= 3000:
        tags.append("블루오션")
    if top and rocket_share <= 0.3:
        tags.append("로켓공백")
    if avg_price >= 30_000:
        tags.append("고단가")

    return {
        **kw,
        "total_sales": total_sales, "total_revenue": total_rev, "total_reviews": total_reviews,
        "avg_price": avg_price, "rocket_share": round(rocket_share, 2), "hero_reviews": hero_reviews,
        "hero_name": hero["name"] if hero else "",
        "score": score, "grade": grade, "tags": tags,
        "sub_scores": {"수요": round(s_demand), "진입난이도": round(s_entry), "경쟁": round(s_comp),
                       "로켓공백": round(s_rocket), "단가": round(s_price)},
    }


def mismatch_reason(row: dict, tier: str, max_review: int, tags: list[str]) -> str | None:
    """티어·필터에 안 맞으면 이유 문자열, 맞으면 None."""
    t = TIERS[tier]
    rev = row["total_revenue"] / 10_000
    if row["total_revenue"] < t["min_rev"]:
        return f"매출 미달 (추정 {rev:,.0f}만원 < {t['min_rev'] // 10_000:,}만원)"
    if t["max_rev"] and row["total_revenue"] > t["max_rev"]:
        return f"매출 초과 (추정 {rev:,.0f}만원 > {t['max_rev'] // 10_000:,}만원) → 상위 티어에서 확인"
    lim = min(max_review, t.get("max_top_review", 10**9))
    if row["hero_reviews"] > lim:
        return f"효자상품 리뷰 {row['hero_reviews']:,} > {lim:,}"
    if tags and not set(tags) & set(row["tags"]):
        return "선택한 태그 없음"
    return None


def match_tier(row: dict, tier: str, max_review: int, tags: list[str]) -> bool:
    return mismatch_reason(row, tier, max_review, tags) is None


def search_window(tier: str, purchase_rate: float, coupang_ratio: float) -> tuple[float, float, float]:
    """티어 매출 구간에 들어올 법한 월 검색량 범위(가격 5천~4만원 가정)와 중심값."""
    t = TIERS[tier]
    k = purchase_rate * coupang_ratio * sum(RANK_SHARE)
    max_rev = t["max_rev"] or t["min_rev"] * 5
    lo, hi = t["min_rev"] / (k * 40_000), max_rev / (k * 5_000)
    center = math.sqrt(t["min_rev"] * max_rev) / (k * 15_000)
    return lo, hi, center
