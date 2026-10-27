"""쿠팡 검색결과 1페이지 수집 (내 PC의 크롬으로 실행).

쿠팡은 공식 검색 API가 없어 화면에서 가격·리뷰수·로켓배송 여부를 읽는다.
- 요청 간격을 충분히 두고(기본 4~7초) 소량만 조회하세요.
- 쿠팡 화면 구조가 바뀌면 SELECTORS 를 수정해야 할 수 있습니다.
- 쿠팡 이용약관을 확인하고 본인 책임 하에 개인 리서치 용도로만 사용하세요.
"""
import random
import re
import time
from pathlib import Path
from urllib.parse import quote

SELECTORS = {
    "item": 'li[class*="ProductUnit_productUnit"]',
    "name": '[class*="ProductUnit_productName"]',
    "price_area": '[class*="PriceArea_priceArea"]',
    "rating": '[class*="ProductRating_productRating"]',
    "badge": "[data-badge-id]",
}
ROCKET_BADGES = {"ROCKET", "ROCKET_FRESH", "ROCKET_LUXURY", "COUPANG_GLOBAL", "ROCKET_JIKGU"}

_JS = """
(sel) => [...document.querySelectorAll(sel.item)].map(li => {
  const a = li.querySelector('a');
  const priceTxt = [...(li.querySelector(sel.price_area)?.querySelectorAll('span') || [])]
      .map(s => s.textContent).filter(t => /^[0-9,]+원$/.test(t.trim()));
  const rating = li.querySelector(sel.rating);
  const reviewTxt = rating ? (rating.innerText.match(/\\(([0-9,]+)\\)/) || [])[1] : null;
  return {
    name: (li.querySelector(sel.name)?.textContent || '').trim(),
    url: a ? a.href : '',
    is_ad: !!(a && a.href.includes('_ads')) || /\\n광고$/.test(li.innerText.trim()),
    price: priceTxt.length ? priceTxt[0] : null,
    reviews: reviewTxt,
    rating: rating?.querySelector('[aria-label]')?.getAttribute('aria-label') || null,
    badges: [...li.querySelectorAll(sel.badge)].map(b => b.dataset.badgeId),
  };
})
"""


def _num(s):
    return int(re.sub(r"[^0-9]", "", s)) if s and re.search(r"[0-9]", s) else 0


class CoupangScraper:
    def __init__(self, profile_dir: str = ".coupang_profile", headless: bool = False,
                 delay=(4.0, 7.0)):
        self.profile_dir = str(Path(profile_dir).resolve())
        self.headless = headless
        self.delay = delay
        self._pw = self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = dict(headless=self.headless, locale="ko-KR", viewport={"width": 1280, "height": 900})
        try:  # 설치된 크롬 사용 (차단 확률 낮음)
            self._ctx = self._pw.chromium.launch_persistent_context(self.profile_dir, channel="chrome", **kw)
        except Exception:
            self._ctx = self._pw.chromium.launch_persistent_context(self.profile_dir, **kw)
        return self

    def __exit__(self, *a):
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()

    def search(self, keyword: str, top_n: int = 10) -> list[dict]:
        page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        page.goto(f"https://www.coupang.com/np/search?q={quote(keyword)}&listSize=36",
                  wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector(SELECTORS["item"], timeout=15000)
        except Exception:
            raise RuntimeError("쿠팡 상품 목록을 찾지 못했습니다 (차단 또는 화면 구조 변경).")
        page.mouse.wheel(0, 2500)
        time.sleep(1.0)
        raw = page.evaluate(_JS, SELECTORS)
        time.sleep(random.uniform(*self.delay))
        return parse_items(raw, top_n)


def parse_items(raw: list[dict], top_n: int = 10) -> list[dict]:
    """광고 제외 자연검색 상위 top_n 상품만 정리."""
    out = []
    for it in raw:
        if it.get("is_ad") or not it.get("name"):
            continue
        badges = set(it.get("badges") or [])
        out.append({
            "rank": len(out) + 1,
            "name": it["name"],
            "url": it.get("url", "").split("&clickEventId")[0],
            "price": _num(it.get("price")),
            "reviews": _num(it.get("reviews")),
            "rating": float(it["rating"]) if it.get("rating") else None,
            "rocket": bool(badges & ROCKET_BADGES),
            "seller_rocket": "ROCKET_MERCHANT" in badges,
        })
        if len(out) >= top_n:
            break
    return out


# ---------------- 수동 보조 모드 (북마클릿) ----------------
# 평소 쓰는 크롬에서 쿠팡 검색 → 북마크 클릭 → 상위 상품 정보가 클립보드에 복사됨 → 소싱기에 붙여넣기
BOOKMARKLET = (
    "javascript:(()=>{const q=new URLSearchParams(location.search).get('q');"
    "const it=[...document.querySelectorAll('li[class*=\"ProductUnit_productUnit\"]')].slice(0,40).map(li=>{"
    "const a=li.querySelector('a');"
    "const pr=[...(li.querySelector('[class*=\"PriceArea_priceArea\"]')?.querySelectorAll('span')||[])]"
    ".map(s=>s.textContent.trim()).filter(t=>/^[0-9,]+원$/.test(t));"
    "const r=li.querySelector('[class*=\"ProductRating_productRating\"]');"
    "const rv=r?(r.innerText.match(/\\(([0-9,]+)\\)/)||[])[1]:null;"
    "return{name:(li.querySelector('[class*=\"ProductUnit_productName\"]')?.textContent||'').trim(),"
    "url:a?a.href.split('&clickEventId')[0]:'',"
    "is_ad:!!(a&&a.href.includes('_ads'))||/\\n광고$/.test(li.innerText.trim()),"
    "price:pr[0]||null,reviews:rv,"
    "rating:r?.querySelector('[aria-label]')?.getAttribute('aria-label')||null,"
    "badges:[...li.querySelectorAll('[data-badge-id]')].map(b=>b.dataset.badgeId)}});"
    "if(!q||!it.length){alert('쿠팡 검색결과 페이지에서 눌러주세요');return}"
    "const s=JSON.stringify({keyword:q,items:it});"
    "const done=()=>alert(q+' : 상품 '+it.length+'개 복사됨. 소싱기에 붙여넣으세요');"
    "navigator.clipboard.writeText(s).then(done,()=>{const t=document.createElement('textarea');"
    "t.value=s;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();done()})})()"
)


def import_paste(text: str, top_n: int = 10) -> tuple[str, list[dict]]:
    """북마클릿이 복사한 JSON → (키워드, 상위상품 리스트)."""
    import json
    data = json.loads(text.strip())
    kw = (data.get("keyword") or "").strip()
    prods = parse_items(data.get("items") or [], top_n)
    if not kw or not prods:
        raise ValueError("키워드 또는 상품 정보가 비어 있습니다.")
    return kw, prods
