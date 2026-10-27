"""소싱 파이프라인: 씨앗 → 연관키워드 확장 → 후보 선별 → 쿠팡/네이버 지표 → 점수·등급."""
import hashlib
import os
import random
from dataclasses import dataclass, field

from . import cache, naver_ads, naver_open, scoring
from .coupang import CoupangScraper


@dataclass
class Settings:
    ads_key: str = ""
    ads_secret: str = ""
    ads_customer: str = ""
    open_id: str = ""
    open_secret: str = ""
    anthropic_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    purchase_rate: float = 0.05     # 검색 1회당 구매 전환율(가정)
    coupang_ratio: float = 1.0      # 쿠팡 검색수 / 네이버 검색수 (가정)
    max_candidates: int = 30        # 쿠팡까지 조회할 후보 수
    cache_days: float = 7
    headless: bool = False
    coupang_mode: str = "manual"    # manual: 북마클릿으로 직접 붙여넣기 / auto: 자동 크롬(차단될 수 있음)
    demo: bool = False

    @classmethod
    def from_env(cls):
        e = os.environ.get
        s = cls(ads_key=e("NAVER_AD_API_KEY", ""), ads_secret=e("NAVER_AD_SECRET_KEY", ""),
                ads_customer=e("NAVER_AD_CUSTOMER_ID", ""), open_id=e("NAVER_CLIENT_ID", ""),
                open_secret=e("NAVER_CLIENT_SECRET", ""), anthropic_key=e("ANTHROPIC_API_KEY", ""),
                anthropic_model=e("ANTHROPIC_MODEL", "claude-sonnet-4-5"))
        s.demo = not (s.ads_key and s.ads_secret and s.ads_customer)
        return s


@dataclass
class Result:
    rows: list = field(default_factory=list)       # 등급 매긴 키워드(조건 일치)
    scanned: list = field(default_factory=list)    # 조회한 전체 키워드
    products: dict = field(default_factory=dict)   # keyword → 상품 리스트
    errors: list = field(default_factory=list)
    pending: list = field(default_factory=list)    # 쿠팡 데이터가 아직 없는 후보 키워드


# ---------------- 데모(가짜) 데이터 ----------------
def _rng(key):
    return random.Random(int(hashlib.md5(key.encode()).hexdigest()[:8], 16))


def _demo_related(seed):
    r = _rng(seed)
    suffixes = ["", "세트", "대용량", "스텐", "실리콘", "미니", "휴대용", "2개입", "고급", "접이식", "국산", "대형"]
    return [{"keyword": seed + s, "search_pc": (pc := r.randint(100, 8000)), "search_mobile": (mo := r.randint(500, 60000)),
             "search_total": pc + mo, "ad_competition": r.choice(["낮음", "중간", "높음"])} for s in suffixes]


def _demo_products(kw):
    r = _rng("p" + kw)
    base = r.choice([3000, 6000, 9000, 15000, 25000, 39000])
    return [{"rank": i + 1, "name": f"[데모] {kw} 상품 {i + 1}", "url": "", "price": int(base * r.uniform(0.7, 1.5) // 100 * 100),
             "reviews": int(r.choice([5, 20, 40, 120, 400, 1500]) * r.uniform(0.5, 2)), "rating": 4.5,
             "rocket": r.random() < r.choice([0.1, 0.4, 0.8]), "seller_rocket": False} for i in range(10)]


def _demo_trend(kw):
    r = _rng("t" + kw)
    amp = r.choice([0.1, 0.5, 2.0])
    return [max(1, 50 + 50 * amp * (0.5 - abs(((m + r.randint(0, 11)) % 12) - 6) / 6) + r.uniform(-5, 5)) for m in range(12)]


# ---------------- 메인 ----------------
def run(seeds_by_cat: dict[str, list[str]], tier: str, max_review: int, tags: list[str],
        s: Settings, progress=lambda pct, msg: None) -> Result:
    res = Result()

    # 1) 연관 키워드 확장
    pool: dict[str, dict] = {}
    chunks = [[(c, k) for k in ks[i:i + 5]] for c, ks in seeds_by_cat.items() for i in range(0, len(ks), 5)]
    for i, chunk in enumerate(chunks):
        progress(0.02 + 0.13 * i / max(1, len(chunks)), f"연관 키워드 확장 중… ({', '.join(k for _, k in chunk)})")
        try:
            if s.demo:
                rel = [x for _, k in chunk for x in _demo_related(k)]
            else:
                ck = ",".join(k for _, k in chunk)
                rel = cache.get("rel", ck, s.cache_days)
                if rel is None:
                    rel = naver_ads.related_keywords([k for _, k in chunk], s.ads_key, s.ads_secret, s.ads_customer)
                    cache.put("rel", ck, rel)
        except Exception as e:
            res.errors.append(f"연관키워드 실패({chunk}): {e}")
            continue
        cat = chunk[0][0]
        for row in rel:
            pool.setdefault(row["keyword"], {**row, "category": cat})

    # 2) 후보 선별: 티어 매출에 맞을 법한 검색량 구간에서 중심값에 가까운 순.
    #    이미 쿠팡 데이터를 붙여넣은 키워드는 항상 포함(추가 작업 없음).
    import math
    lo, hi, center = scoring.search_window(tier, s.purchase_rate, s.coupang_ratio)
    in_win = sorted((v for v in pool.values() if lo <= v["search_total"] <= hi),
                    key=lambda v: abs(math.log(max(v["search_total"], 1) / center)))
    cached = [v for v in pool.values() if not s.demo and cache.get("cp", v["keyword"], s.cache_days) is not None]
    seen, cands = set(), []
    for v in cached + in_win:
        if v["keyword"] not in seen:
            seen.add(v["keyword"])
            cands.append(v)
    cands = cands[: s.max_candidates + len(cached)]
    if not cands:
        res.errors.append("검색량 조건에 맞는 후보 키워드가 없습니다. 씨앗 키워드를 바꿔보세요.")
        return res

    # 3) 데이터랩 트렌드 (5개씩)
    trends = {}
    if s.demo:
        trends = {c["keyword"]: _demo_trend(c["keyword"]) for c in cands}
    elif s.open_id:
        for i in range(0, len(cands), 5):
            ks = [c["keyword"] for c in cands[i:i + 5]]
            hit = {k: cache.get("trend", k, s.cache_days) for k in ks}
            trends.update({k: v for k, v in hit.items() if v})
            ks = [k for k, v in hit.items() if not v]
            if not ks:
                continue
            try:
                got = naver_open.search_trend(ks, s.open_id, s.open_secret)
                for k, v in got.items():
                    cache.put("trend", k, v)
                trends.update(got)
            except Exception as e:
                res.errors.append(f"데이터랩 실패: {e}")

    # 4) 쿠팡 상위상품
    scraper = None
    try:
        if not s.demo:
            todo = [c for c in cands if cache.get("cp", c["keyword"], s.cache_days) is None]
            if todo and s.coupang_mode == "auto":
                scraper = CoupangScraper(headless=s.headless).__enter__()
        for i, c in enumerate(cands):
            kw = c["keyword"]
            progress(0.15 + 0.8 * i / len(cands), f"쿠팡 분석 중… {kw} ({i + 1}/{len(cands)})")
            try:
                if s.demo:
                    prods = _demo_products(kw)
                else:
                    prods = cache.get("cp", kw, s.cache_days)
                    if prods is None and scraper is None:
                        res.pending.append(c)   # 수동 모드: 사용자가 붙여넣을 때까지 대기
                        continue
                    if prods is None:
                        prods = scraper.search(kw)
                        cache.put("cp", kw, prods)
            except Exception as e:
                res.errors.append(f"{kw}: {e}")
                continue
            if not prods:
                continue
            prods = scoring.estimate_products(prods, c["search_total"], s.purchase_rate, s.coupang_ratio)
            row = scoring.analyze(c, prods, trends.get(kw), None, tier)
            row["reason"] = scoring.mismatch_reason(row, tier, max_review, tags)
            res.scanned.append(row)
            res.products[kw] = prods
            if row["reason"] is None:
                res.rows.append(row)
    finally:
        if scraper:
            scraper.__exit__(None, None, None)

    res.rows.sort(key=lambda r: -r["score"])
    progress(1.0, "완료")
    return res
