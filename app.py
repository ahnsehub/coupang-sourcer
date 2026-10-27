"""쿠팡 AI 꿀통키워드 소싱기 — 실행: streamlit run app.py"""
import io
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from sourcer import cache, scoring
from sourcer.ai_comment import sourcing_comment
from sourcer.coupang import BOOKMARKLET, import_paste
from sourcer.pipeline import Settings, run
from sourcer.seeds import CATEGORY_SEEDS

load_dotenv()
st.set_page_config(page_title="AI 꿀통키워드 소싱", page_icon="🍯", layout="wide")

# 클라우드(Streamlit Cloud) 배포 시: Secrets 값을 환경변수로 사용 (로컬은 .env)
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)):
            os.environ.setdefault(_k, str(_v))
except Exception:
    pass

# 비밀번호 잠금: APP_PASSWORD 가 설정돼 있으면 입력해야 사용 가능
_pw = os.environ.get("APP_PASSWORD", "")
if _pw and not st.session_state.get("authed"):
    st.title("🔒 AI 꿀통키워드 소싱")
    if st.text_input("비밀번호", type="password") == _pw:
        st.session_state.authed = True
        st.rerun()
    st.stop()

try:
    import playwright  # noqa: F401  (로컬 PC에서만 자동 크롬 모드 사용 가능)
    HAS_PW = True
except ImportError:
    HAS_PW = False
st.markdown("""<style>
.kw-card{border:1px solid #2a2f36;border-radius:14px;padding:14px 18px;margin-bottom:6px;background:#111418}
.grade{display:inline-block;min-width:38px;text-align:center;font-weight:800;border-radius:8px;padding:2px 8px;margin-right:8px}
.g-Sp{background:#7c3aed;color:#fff}.g-S{background:#16a34a;color:#fff}.g-A{background:#2563eb;color:#fff}.g-B{background:#475569;color:#fff}
.tag{display:inline-block;font-size:12px;border:1px solid #3b4250;border-radius:999px;padding:1px 8px;margin-left:4px;color:#cbd5e1}
.metric{color:#94a3b8;font-size:12px}.mv{font-size:18px;font-weight:700;color:#e2e8f0}
</style>""", unsafe_allow_html=True)

s = Settings.from_env()
TAG_ICON = {"급상승": "🔥", "신규": "🆕", "블루오션": "💎", "계절성": "📈", "로켓공백": "🚀", "고단가": "👆"}

# ---------------- 사이드바: 설정 ----------------
with st.sidebar:
    st.header("⚙️ 설정")
    if s.demo:
        st.warning("데모 모드 — 네이버 검색광고 API 키가 없어 **가짜 데이터**로 동작합니다. `.env` 파일(로컬) 또는 Secrets(클라우드)에 키를 넣으세요.")
    else:
        st.success("네이버 검색광고 API 연결됨")
    st.caption(f"네이버 데이터랩 키(트렌드): {'✅' if s.open_id else '❌ 없음 (급상승·계절성 태그 비활성)'}")
    st.caption(f"Claude API(AI 코멘트): {'✅' if s.anthropic_key else '❌ 없음'}")
    st.divider()
    st.subheader("판매량 추정 가정")
    s.purchase_rate = st.slider("검색→구매 전환율", 0.01, 0.15, 0.05, 0.01,
                                help="월 검색량 × 이 비율 = 키워드 월 구매수(추정). 실제 내 상품 데이터로 보정하세요.")
    s.coupang_ratio = st.slider("쿠팡/네이버 검색량 비율", 0.3, 3.0, 1.0, 0.1)
    s.max_candidates = st.slider("후보 키워드 수", 5, 100, 20, 5,
                                 help="쿠팡 데이터를 확인할 후보 수. 검색량 큰 순으로 고릅니다.")
    s.cache_days = st.number_input("캐시 유지 일수", 1, 60, 7)
    st.divider()
    mode = st.radio("쿠팡 데이터 수집 방식",
                    ["수동 보조 (북마크)"] + (["자동 크롬 (차단될 수 있음)"] if HAS_PW else []))
    s.coupang_mode = "manual" if mode.startswith("수동") else "auto"
    if s.coupang_mode == "auto":
        s.headless = st.checkbox("크롬 창 숨기기(headless)", False)
    with st.expander("📌 북마크 버튼 설치 방법"):
        st.markdown("1. 크롬 북마크바에서 우클릭 → **페이지 추가**\n"
                    "2. 이름: `쿠팡소싱복사`, URL 칸에 아래 코드 전체를 붙여넣기\n"
                    "3. 쿠팡 검색결과 화면에서 이 북마크를 클릭 → 상품 정보가 복사됨")
        st.code(BOOKMARKLET, language=None, wrap_lines=True)

# ---------------- 메인: 조건 선택 ----------------
st.markdown("<p style='text-align:center;color:#4ade80;letter-spacing:2px'>CONFIGURATION</p>"
            "<h1 style='text-align:center'>AI 꿀통키워드 소싱</h1>"
            "<p style='text-align:center;color:#94a3b8'>수익성 높은 쿠팡 키워드를 찾아드립니다</p>",
            unsafe_allow_html=True)

st.subheader("어떤 키워드를 찾으시나요?")
cols = st.columns(4)
if "tier" not in st.session_state:
    st.session_state.tier = "beginner"
for col, (key, t) in zip(cols, scoring.TIERS.items()):
    with col:
        sel = st.session_state.tier == key
        st.markdown(f"<div class='kw-card' style='border-color:{'#4ade80' if sel else '#2a2f36'}'>"
                    f"<span class='tag'>{t['badge']}</span><h4>{t['label']}</h4>"
                    f"<div class='metric'>{t['desc']}</div></div>", unsafe_allow_html=True)
        if st.button("✓ 선택됨" if sel else "선택", key=f"tier_{key}", width="stretch",
                     type="primary" if sel else "secondary"):
            st.session_state.tier = key
            st.rerun()

with st.expander("고급 필터", expanded=False):
    max_review = st.slider("효자상품 최대 리뷰수 (매출 1위 상품의 리뷰가 이 수 이하)", 50, 1000, 500, 50)
    cats = st.multiselect("소싱할 상품 카테고리 (미선택 시 전체)", list(CATEGORY_SEEDS))
    tags = st.multiselect("관심 태그 (하나라도 포함)", scoring.ALL_TAGS,
                          format_func=lambda t: f"{TAG_ICON[t]} {t}")
    custom = st.text_input("직접 씨앗 키워드 입력 (쉼표 구분, 입력 시 카테고리 대신 사용)", "")

if st.button("소싱 시작하기 🚀", type="primary", width="stretch"):
    if custom.strip():
        seeds = {"직접입력": [k.strip() for k in custom.split(",") if k.strip()]}
    else:
        seeds = {c: CATEGORY_SEEDS[c] for c in (cats or CATEGORY_SEEDS)}
    st.session_state.args = (seeds, st.session_state.tier, max_review, tags)
    bar = st.progress(0.0, "준비 중…")
    st.session_state.res = run(*st.session_state.args, s, progress=lambda p, m: bar.progress(min(p, 1.0), m))
    bar.empty()

# ---------------- 결과 ----------------
res = st.session_state.get("res")
if res and res.pending:
    st.subheader(f"🛒 쿠팡 데이터 입력 — {len(res.pending)}개 남음")
    st.caption("링크를 눌러 쿠팡 검색 → 북마크 `쿠팡소싱복사` 클릭 → 아래 칸에 붙여넣기(Ctrl+V) → 저장. "
               "순서 상관없이 원하는 키워드만 해도 됩니다. 저장할 때마다 결과가 갱신됩니다.")
    from urllib.parse import quote
    links = " · ".join(f"[{c['keyword']}](https://www.coupang.com/np/search?q={quote(c['keyword'])}&listSize=36) "
                       f"<span class='metric'>({c['search_total']:,})</span>" for c in res.pending)
    st.markdown(links, unsafe_allow_html=True)
    with st.form("paste", clear_on_submit=True):
        pasted = st.text_area("북마크로 복사한 내용 붙여넣기", height=90)
        if st.form_submit_button("저장하고 결과 갱신", type="primary"):
            try:
                kw, prods = import_paste(pasted)
                cache.put("cp", kw, prods)
                st.session_state.res = run(*st.session_state.args, s)
                st.toast(f"저장됨: {kw} (상품 {len(prods)}개)")
                st.rerun()
            except Exception as e:
                st.error(f"붙여넣기 내용을 읽지 못했습니다: {e}")

if res:
    for e in res.errors[:10]:
        st.caption(f"⚠️ {e}")
    st.success(f"쿠팡 데이터가 있는 {len(res.scanned)}개 중 **{len(res.rows)}개가 조건에 맞는 꿀통키워드**입니다")
    if s.demo:
        st.info("데모 데이터입니다. 실제 키워드가 아닙니다.")

    for i, r in enumerate(res.rows):
        g = r["grade"].replace("+", "p")
        tag_html = "".join(f"<span class='tag'>{TAG_ICON[t]} {t}</span>" for t in r["tags"])
        st.markdown(
            f"<div class='kw-card'><span class='grade g-{g}'>{r['grade']}</span>"
            f"<b style='font-size:18px'>{r['keyword']}</b> <span class='metric'>· {r['category']} · 점수 {r['score']}</span>{tag_html}"
            f"<div style='display:flex;gap:28px;margin-top:10px;flex-wrap:wrap'>"
            f"<div><div class='metric'>월 검색량</div><div class='mv'>{r['search_total']:,}</div></div>"
            f"<div><div class='metric'>추정 월판매</div><div class='mv'>{r['total_sales']:,}개</div></div>"
            f"<div><div class='metric'>추정 월매출</div><div class='mv'>{r['total_revenue']/10000:,.0f}만원</div></div>"
            f"<div><div class='metric'>평균가</div><div class='mv'>{r['avg_price']:,}원</div></div>"
            f"<div><div class='metric'>상위10 총리뷰</div><div class='mv'>{r['total_reviews']:,}</div></div>"
            f"<div><div class='metric'>효자상품 리뷰</div><div class='mv'>{r['hero_reviews']:,}</div></div>"
            f"<div><div class='metric'>로켓 비율</div><div class='mv'>{r['rocket_share']*100:.0f}%</div></div>"
            f"<div><div class='metric'>광고 경쟁도</div><div class='mv'>{r.get('ad_competition') or '-'}</div></div>"
            f"</div></div>", unsafe_allow_html=True)
        with st.expander(f"효자상품 리스트 · 세부점수 — {r['keyword']}"):
            st.caption(" · ".join(f"{k} {v}" for k, v in r["sub_scores"].items()))
            df = pd.DataFrame(res.products[r["keyword"]])[["rank", "name", "price", "reviews", "rocket", "est_sales", "est_revenue", "url"]]
            df.columns = ["순위", "상품명", "가격", "리뷰", "로켓", "추정월판매", "추정월매출", "링크"]
            st.dataframe(df, hide_index=True, width="stretch",
                         column_config={"링크": st.column_config.LinkColumn(display_text="열기"),
                                        **{c: st.column_config.NumberColumn(format="localized")
                                           for c in ["가격", "리뷰", "추정월판매", "추정월매출"]}})
            ck = f"ai::{r['keyword']}"
            saved = cache.get("ai", r["keyword"], 30)
            if saved:
                st.info(saved)
            elif s.anthropic_key and st.button("🤖 AI 소싱 코멘트 생성", key=ck):
                try:
                    txt = sourcing_comment(r, res.products[r["keyword"]], s.anthropic_key, s.anthropic_model)
                    cache.put("ai", r["keyword"], txt)
                    st.info(txt)
                except Exception as e:
                    st.error(f"AI 코멘트 실패: {e}")

    misses = [r for r in res.scanned if r.get("reason")]
    if misses:
        with st.expander(f"조건에 안 맞은 키워드 {len(misses)}개 (이유 보기)", expanded=not res.rows):
            st.caption("매출 초과 키워드는 상단에서 중수/고수 티어를 선택하고 다시 소싱하면 결과에 나옵니다. 붙여넣은 데이터는 그대로 재사용됩니다.")
            st.dataframe(pd.DataFrame([{
                "등급": r["grade"], "키워드": r["keyword"], "점수": r["score"], "월검색량": r["search_total"],
                "추정월매출(만원)": round(r["total_revenue"] / 10_000), "효자상품 리뷰": r["hero_reviews"],
                "태그": ", ".join(r["tags"]), "제외 이유": r["reason"]} for r in sorted(misses, key=lambda r: -r["score"])]),
                hide_index=True, width="stretch")

    if res.scanned:
        out = pd.DataFrame([{**{k: v for k, v in r.items() if k != "sub_scores"}, "tags": ",".join(r["tags"])}
                            for r in res.scanned]).sort_values("score", ascending=False)
        buf = io.BytesIO()
        out.to_excel(buf, index=False)
        st.download_button("📥 전체 조회 결과 엑셀 다운로드", buf.getvalue(), "keyword_sourcing.xlsx")

st.caption("※ 판매량·매출은 '검색량 × 전환율 × 순위별 점유율' 기반 추정치입니다. 실제 판매 데이터가 아닙니다.")
