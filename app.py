"""
Call2Text - AI 상담 요약 · 안내 문자 자동화
v2.1 | 기억해조 5조 | 신한은행
"""
import streamlit as st
import os, json, re, zipfile, glob, hmac, hashlib, uuid, io, requests
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(
    page_title="Call2Text | 신한은행 AI 상담 문자",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
CACHE_DIR      = BASE_DIR / ".cache"
HISTORY_FILE   = CACHE_DIR / "history.json"
LINKS_FILE     = CACHE_DIR / "links.json"
TEMPLATES_FILE = CACHE_DIR / "templates.json"
CACHE_DIR.mkdir(exist_ok=True)

# ── Default data ───────────────────────────────────────────────
DEFAULT_LINKS = [
    {"name": "신용카드 신규", "url": "https://nssol.shinhan.com/link.html?pr_id=PR1201S0002F01&prdtCS20=CAADV9",
     "description": "신한 신용카드 신규 발급", "category": "카드"},
    {"name": "신용카드 신규 (S612)", "url": "https://nssol.shinhan.com/link.html?pr_id=PR0302S0101F01&prdCode=S612212800",
     "description": "신한 신용카드 (S612 코드)", "category": "카드"},
    {"name": "직장인 신용대출 신규", "url": "https://nssol.shinhan.com/link.html?pr_id=PR1402S0001F01&prdCode=260000401",
     "description": "직장인 신용대출 신규 신청", "category": "대출"},
    {"name": "IRP 신규", "url": "https://nssol.shinhan.com/link.html?pr_id=PR1002S0011F01&prdGubun=1&prdCode=110007201",
     "description": "개인형 퇴직연금(IRP) 신규 가입", "category": "투자/펀드"},
]

SHINHAN_PRODUCTS_DEFAULT = [
    {"name": "쏠편한 정기예금", "category": "예금/적금", "description": "비대면 전용, 연 최대 3.5%, 6~24개월 자유 선택"},
    {"name": "신한 주거래 우대통장", "category": "예금/적금", "description": "주거래 고객 우대 이율, 이체 수수료 면제 혜택"},
    {"name": "신한 Hi통장", "category": "예금/적금", "description": "모임통장 기능, 이체 수수료 무제한 면제"},
    {"name": "미래설계 저축통장", "category": "예금/적금", "description": "목돈 마련·노후 설계 전용 장기 저축 상품"},
    {"name": "신한 직장인 신용대출", "category": "대출", "description": "직장인 대상, 최대 1억 5천만원, 최저 연 4.0%"},
    {"name": "신한 주택담보대출", "category": "대출", "description": "아파트·주택 담보, LTV 최대 70%"},
    {"name": "신한 전세자금대출", "category": "대출", "description": "전세 계약 시 최대 5억원 지원"},
    {"name": "신한카드 Deep Dream", "category": "카드", "description": "온라인 쇼핑·배달 앱 캐시백, 연회비 2만원"},
    {"name": "신한카드 Mr.Life", "category": "카드", "description": "주유·편의점·외식 할인, 생활 특화 카드"},
    {"name": "신한카드 B.Big", "category": "카드", "description": "대중교통·주유 특화, 월 최대 1만원 할인"},
    {"name": "신한체크카드 Deep ON", "category": "카드", "description": "편의점·커피·쇼핑 캐시백 체크카드"},
    {"name": "신한 IRP (개인형퇴직연금)", "category": "투자/펀드", "description": "연 최대 900만원 세액공제, 퇴직금 운용"},
    {"name": "쏠투자 로보어드바이저", "category": "투자/펀드", "description": "AI 기반 자동 포트폴리오, 최소 10만원"},
    {"name": "신한 글로벌 ETF펀드", "category": "투자/펀드", "description": "글로벌 우량 ETF 자동 분산투자 펀드"},
    {"name": "신한 연금보험", "category": "보험", "description": "노후 생활비 준비, 유연한 연금 수령"},
    {"name": "신한 암보험", "category": "보험", "description": "암 진단 시 최대 5천만원, 수술·입원 보장"},
    {"name": "신한 쏠(SOL) 뱅킹", "category": "전자금융", "description": "이체·조회 무제한, 비대면 상품 가입 가능"},
    {"name": "신한 외화예금", "category": "외환", "description": "달러·엔화 등 14개 외화 보통/정기 예금"},
    {"name": "신한 환전 서비스", "category": "외환", "description": "최대 90% 환율 우대, 공항 픽업 서비스"},
]

if not LINKS_FILE.exists():
    LINKS_FILE.write_text(json.dumps(DEFAULT_LINKS, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Brand images (load from local assets) ────────────────────
@st.cache_resource(show_spinner=False)
def get_brand_images():
    import base64
    imgs = {}
    assets = BASE_DIR / "assets"
    for key, fname in [("sol", "sol.png"), ("logo", "shinhan_logo.png")]:
        p = assets / fname
        if p.exists():
            imgs[key] = f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
    return imgs


# ── CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
html,body,[class*="css"]{font-family:'Noto Sans KR',sans-serif!important}

section[data-testid="stSidebar"]{background:linear-gradient(180deg,#001f6b 0%,#003DA5 100%)!important}
section[data-testid="stSidebar"] *{color:#ffffff!important}
section[data-testid="stSidebar"] .stRadio label{font-size:14px!important;padding:8px 0!important;border-bottom:1px solid rgba(255,255,255,0.1)!important}

.stApp{background:#f0f4f9!important}

.brand-header{background:linear-gradient(135deg,#002d84 0%,#003DA5 60%,#0050cc 100%);border-radius:14px;padding:20px 28px;margin-bottom:24px;display:flex;align-items:center;gap:16px;box-shadow:0 6px 24px rgba(0,61,165,0.30)}
.brand-text .title{font-size:24px;font-weight:700;color:#ffffff;margin:0;letter-spacing:-0.3px}
.brand-text .sub{font-size:12px;color:rgba(255,255,255,0.80);margin:4px 0 0}
.brand-badge{background:#FF6B35;color:#fff!important;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:0.5px;white-space:nowrap}

.step-header{background:#003DA5;color:white!important;padding:10px 20px;border-radius:8px;margin:20px 0 14px;font-size:14px;font-weight:600;border-left:5px solid #FF6B35}
.page-title{font-size:26px;font-weight:700;color:#003DA5;margin-bottom:4px}
.page-sub{font-size:13px;color:#666;margin-bottom:20px}

.info-card{background:white;border-radius:10px;padding:18px 22px;border:1px solid #dce4f0;margin-bottom:14px;box-shadow:0 2px 8px rgba(0,61,165,0.08)}
.prod-card{background:#e8f0fc;border-radius:8px;padding:14px 16px;border-left:4px solid #003DA5;margin-bottom:10px}
.prod-card-stat{background:#e8f5e9;border-radius:8px;padding:14px 16px;border-left:4px solid #2e7d32;margin-bottom:10px}
.link-card{background:#fff8f0;border-radius:8px;padding:10px 14px;border-left:4px solid #FF6B35;margin-bottom:6px}

.char-ok{color:#2e7d32;font-size:13px;font-weight:500}
.char-warn{color:#e65100;font-size:13px;font-weight:500}

.stButton>button[kind="primary"]{background:#003DA5!important;border:none!important;font-weight:600!important;border-radius:6px!important}
.stButton>button[kind="primary"]:hover{background:#0050CC!important}

[data-testid="metric-container"]{background:white;border-radius:8px;padding:12px;border:1px solid #dce4f0}
div[data-testid="stForm"]{border:none!important}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
_DEFAULTS = {
    "openai_api_key":     os.getenv("OPENAI_API_KEY", ""),
    "solapi_api_key":     os.getenv("SOLAPI_API_KEY", ""),
    "solapi_api_secret":  os.getenv("SOLAPI_API_SECRET", ""),
    "solapi_from_number": os.getenv("SOLAPI_FROM_NUMBER", ""),
    "transcript":         "",
    "masked_transcript":  "",
    "consultation_type":  "",
    "rag_results":        [],
    "sms_draft":          "",
    "shinhan_products":   [],
    "consumer_products":  [],
    "step":               0,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── JSON helpers ──────────────────────────────────────────────
def load_json(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── PII masking ───────────────────────────────────────────────
def mask_pii(text: str) -> str:
    if not text:
        return text
    masked = text

    # 1. 주민등록번호: 970405-1234567
    masked = re.sub(r'\b\d{6}-\d{7}\b', '******-*******', masked)

    # 1-2. 주민등록번호: 하이픈 없이 13자리 연속 (9704051234567)
    masked = re.sub(r'(?<!\d)\d{13}(?!\d)', '******-*******', masked)

    # 2. 휴대폰번호: 010-9876-5432 / 01098765432
    masked = re.sub(
        r'01[016789]-?\d{3,4}-?\d{4}',
        lambda m: f"{m.group()[:3]}-****-{m.group()[-4:]}",
        masked
    )

    # 3. 생년월일: 1990년 7월 18일 / 97년 4월 5일
    masked = re.sub(r'(\d{2,4})년\s*\d{1,2}월\s*\d{1,2}일', r'\1년 **월 **일', masked)

    # 4. 생년월일: 1990-07-18 / 1990.07.18 / 1990/07/18
    masked = re.sub(r'\b(\d{4})[-./](\d{1,2})[-./](\d{1,2})\b', r'\1-**-**', masked)

    # 5. 생년월일 8자리 (문맥 기반, 6자리보다 먼저)
    masked = re.sub(
        r'(생년월일은|생년월일:|생일은|생일:|출생일은|출생일:)\s*(\d{8})',
        lambda m: f"{m.group(1)} ********", masked
    )

    # 6. 생년월일 6자리 (문맥 기반)
    masked = re.sub(
        r'(생년월일은|생년월일:|생일은|생일:|출생일은|출생일:)\s*(\d{6})',
        lambda m: f"{m.group(1)} ******", masked
    )

    # 7. 계좌번호: 110-123-456789
    masked = re.sub(
        r'\b\d{2,6}-\d{2,6}-\d{3,10}\b',
        lambda m: m.group().split('-')[0] + '-***-******', masked
    )

    # 8. 이름: 저는 박서연입니다 / 제 이름은 김신한이고요
    masked = re.sub(
        r'(저는|제 이름은|이름은|고객명은)\s*([가-힣]{2,4})(입니다|이고요|이고|이에요|예요)?',
        lambda m: f"{m.group(1)} {m.group(2)[0]}**{m.group(3) or ''}", masked
    )

    # 9. 이름: 박서연 고객님
    masked = re.sub(
        r'([가-힣]{2,4})\s*고객님',
        lambda m: f"{m.group(1)[0]}** 고객님", masked
    )

    # 10. 주소 (문맥 기반): 주소는 서울시 영등포구 ...
    masked = re.sub(
        r'주소는\s*([가-힣]+시\s+[가-힣]+구)\s+[^.\n]+',
        r'주소는 \1 ****', masked
    )

    # 11. 주소 (패턴): 서울시 영등포구 국제금융로 20
    masked = re.sub(
        r'([가-힣]+시\s+[가-힣]+구)\s+[가-힣0-9\s로길\-]+',
        r'\1 ****', masked
    )

    # 12. 이메일
    masked = re.sub(r'[\w.\-]+@[\w.\-]+\.\w+', '[이메일]', masked)

    # 13. 카드번호 16자리
    masked = re.sub(r'\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}', '[카드번호]', masked)

    return masked


# ── Categories ────────────────────────────────────────────────
CATEGORIES = {
    "예금/적금": ["예금","적금","저축","통장","금리","이자","만기","해지","정기"],
    "대출":      ["대출","융자","담보","신용대출","주택담보","전세자금","한도","상환"],
    "카드":      ["카드","체크카드","신용카드","포인트","혜택","결제","청구","연회비"],
    "전자금융":  ["인터넷뱅킹","모바일","앱","OTP","이체","송금","계좌이체"],
    "투자/펀드": ["펀드","투자","주식","ETF","채권","수익률","증권","IRP","연금"],
    "보험":      ["보험","연금","보장","보험료","보험금","종신","암"],
    "외환":      ["환전","외화","달러","유로","환율","해외송금"],
}

def classify_keyword(text: str) -> str:
    scores = {cat: sum(1 for kw in kws if kw in text) for cat, kws in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "기타"


# ── Shinhan products (web crawl + fallback) ───────────────────
@st.cache_resource(show_spinner=False)
def get_shinhan_products():
    """Crawl Shinhan Bank product page; fall back to curated list if JS-only."""
    from bs4 import BeautifulSoup
    hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    products = []
    try:
        r = requests.get("https://www.shinhan.com/hpe/index.jsp",
                         headers=hdrs, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup.select("a[href*='prd'],a[href*='product'],li.prod-item,div.product-name"):
            name = tag.get_text(strip=True)[:60]
            if name and len(name) > 3:
                products.append({"name": name, "category": "기타",
                                  "description": "", "url": tag.get("href","")})
    except Exception:
        pass
    return products if len(products) >= 5 else SHINHAN_PRODUCTS_DEFAULT


def recommend_shinhan_products(ctype: str, top_k: int = 4) -> list:
    all_prods = get_shinhan_products()
    matched = [p for p in all_prods if p.get("category") == ctype]
    if not matched:
        matched = all_prods
    return matched[:top_k]


# ── RAG engine (25번 bank_qa only) ───────────────────────────
@st.cache_resource(show_spinner=False)
def get_rag_engine():
    from sklearn.feature_extraction.text import TfidfVectorizer
    corpus = []
    pat = str(BASE_DIR / "25.금융분야_고객상담_데이터" / "**" / "02.라벨링데이터" / "*L_*.zip.part0")
    for zp in glob.glob(pat, recursive=True):
        try:
            with zipfile.ZipFile(zp) as zf:
                jfiles = [f for f in zf.namelist() if f.endswith(".json")]
                for fname in jfiles[:60]:
                    try:
                        d = json.loads(zf.read(fname).decode("utf-8"))
                        if isinstance(d, dict) and "qa_data" in d:
                            content = d.get("source",{}).get("consulting_content","")[:300]
                            for qa in d["qa_data"][:3]:
                                q = qa.get("input",{}).get("question","")
                                a = qa.get("output","")
                                if q and a:
                                    corpus.append({
                                        "type":"bank_qa","category":qa.get("qa_topic",""),
                                        "question":q,"answer":a,"text":content+" "+q,
                                    })
                    except Exception:
                        continue
        except Exception:
            continue
    if not corpus:
        return None, None, []
    texts = [c["text"] for c in corpus]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2,3), max_features=30000)
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix, corpus


def search_rag(query: str, top_k: int = 4):
    from sklearn.metrics.pairwise import cosine_similarity
    vectorizer, matrix, corpus = get_rag_engine()
    if vectorizer is None:
        return []
    qvec = vectorizer.transform([query])
    scores = cosine_similarity(qvec, matrix).flatten()
    idxs = scores.argsort()[-top_k:][::-1]
    return [{**corpus[i],"score":float(scores[i])} for i in idxs if scores[i] > 0.03]


# ── Consumer data ─────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_consumer_df():
    import pandas as pd
    dfs = []
    for split, prefix in [("Training","TL"),("Validation","VL")]:
        zpath = (BASE_DIR / "36.금융상품·서비스 및 소비자 특성 데이터"
                 / "3.개방데이터" / "1.데이터" / split / "02.라벨링데이터"
                 / f"{prefix}_2.소비자.zip")
        if not zpath.exists():
            continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                fname = next(f for f in zf.namelist() if f.endswith(".csv"))
                raw = zf.read(fname).decode("utf-8-sig")
            dfs.append(pd.read_csv(io.StringIO(raw)))
        except Exception:
            continue
    if not dfs:
        return None
    import pandas as pd
    full = pd.concat(dfs, ignore_index=True)
    return full.sample(min(80_000, len(full)), random_state=42).reset_index(drop=True)


def extract_profile(text: str) -> dict:
    profile = {}
    for ag in ["10대","20대","30대","40대","50대","60대","70대"]:
        if ag in text:
            profile["age"] = ag; break
    if any(w in text for w in ["남성","남자","아버지","아들","남편"]):
        profile["gender"] = "남"
    elif any(w in text for w in ["여성","여자","어머니","딸","부인","아내"]):
        profile["gender"] = "여"
    return profile


def recommend_from_consumer(text: str, top_k: int = 3) -> list:
    import pandas as pd
    df = get_consumer_df()
    if df is None:
        return []
    profile = extract_profile(text)
    mask = pd.Series([True] * len(df))
    if "age" in profile and "age" in df.columns:
        mask &= df["age"] == profile["age"]
    if "gender" in profile and "gender" in df.columns:
        mask &= df["gender"] == profile["gender"]
    filtered = df[mask] if mask.sum() >= 20 else df
    if "product_name" not in filtered.columns:
        return []
    top = filtered["product_name"].value_counts().head(top_k)
    results = []
    for pname, cnt in top.items():
        row = filtered[filtered["product_name"] == pname].iloc[0]
        results.append({
            "product_name": pname, "count": int(cnt),
            "age": str(row.get("age","")), "gender": str(row.get("gender","")),
        })
    return results


# ── OpenAI helpers ────────────────────────────────────────────
def openai_chat(messages, api_key, model="gpt-4o-mini", temperature=0.4):
    import openai
    client = openai.OpenAI(api_key=api_key)
    r = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    return r.choices[0].message.content

def whisper_stt(audio_bytes: bytes, api_key: str, filename: str = "audio.wav") -> str:
    import openai
    client = openai.OpenAI(api_key=api_key)
    buf = io.BytesIO(audio_bytes); buf.name = filename
    return client.audio.transcriptions.create(model="whisper-1", file=buf, language="ko").text

def ai_classify(text: str, api_key: str) -> str:
    cats = list(CATEGORIES.keys()) + ["기타"]
    result = openai_chat([
        {"role":"system","content":f"상담 유형을 정확히 하나만 골라 답하세요: {', '.join(cats)}"},
        {"role":"user","content":text[:600]},
    ], api_key, temperature=0)
    for c in cats:
        if c in result:
            return c
    return "기타"


def ai_generate_draft(masked, ctype, rag_results, shinhan_products, consumer_products,
                      links, api_key, template=None):
    rag_ctx  = "\n".join(f"- Q: {r['question'][:80]}\n  A: {r['answer'][:120]}"
                         for r in rag_results[:3])
    prod_ctx = "\n".join(f"{i}. {p['name']}: {p.get('description','')[:80]}"
                         for i, p in enumerate(shinhan_products[:3], 1))
    stat_ctx = "\n".join(f"{i}. {p['product_name']} (유사고객 {p['count']}명)"
                         for i, p in enumerate(consumer_products[:2], 1))
    link_ctx = "\n".join(f"- {l['name']}: {l['url']}"
                         for l in links[:2] if l.get("url"))

    if template:
        prompt = f"""다음 템플릿 형식에 맞추어 신한은행 고객 안내 문자를 작성하세요.

[사용할 템플릿]
{template}

[상담 유형] {ctype}
[상담 내용 요약] {masked[:600]}
[참조 상담 예시] {rag_ctx or '없음'}
[추천 신한 상품] {prod_ctx or '없음'}
[유사고객 가입 상품] {stat_ctx or '없음'}
[안내 링크] {link_ctx or '없음'}

작성 규칙:
- 반드시 첫 줄: "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다"
- 템플릿의 {{중괄호}} 또는 빈 자리를 실제 내용으로 채울 것
- 전체 300자 이내
- 개인정보 절대 포함 금지
- 마지막: "문의: 신한은행 고객센터 1599-8000"

문자 초안만 출력 (설명 없이):"""
    else:
        prompt = f"""신한은행 고객 안내 문자를 작성하세요.

[상담 유형] {ctype}
[상담 내용 요약] {masked[:700]}
[참조 상담 예시] {rag_ctx or '없음'}
[추천 신한 상품] {prod_ctx or '없음'}
[유사고객 가입 상품] {stat_ctx or '없음'}
[안내 링크] {link_ctx or '없음'}

작성 규칙:
- 반드시 첫 줄: "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다"
- 전체 300자 이내 (LMS)
- 정중하고 신뢰감 있는 어투
- 핵심 정보(상품명, 조건, 링크) 명확하게
- 마지막: "문의: 신한은행 고객센터 1599-8000"
- 개인정보 절대 포함 금지

문자 초안만 출력 (설명 없이):"""

    return openai_chat([
        {"role":"system","content":"당신은 신한은행 고객 안내 문자 전문 작성자입니다."},
        {"role":"user","content":prompt},
    ], api_key)


# ── SMS (Solapi) ──────────────────────────────────────────────
def send_sms(to, content, api_key, api_secret, from_num):
    date_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    salt = uuid.uuid4().hex
    sig  = hmac.new(api_secret.encode(), (date_str+salt).encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"HMAC-SHA256 apiKey={api_key}, date={date_str}, salt={salt}, signature={sig}",
        "Content-Type": "application/json",
    }
    msg_type = "LMS" if len(content) > 90 else "SMS"
    payload  = {"message": {"to": to.replace("-",""), "from": from_num.replace("-",""),
                             "text": content, "type": msg_type}}
    r = requests.post("https://api.solapi.com/messages/v4/send",
                      headers=headers, json=payload, timeout=10)
    return r.json()


# ── Link helpers ──────────────────────────────────────────────
def get_recommended_links(ctype: str) -> list:
    return [l for l in load_json(LINKS_FILE, DEFAULT_LINKS) if l.get("category") == ctype]


# ── Brand header ──────────────────────────────────────────────
def render_brand_header():
    imgs = get_brand_images()
    logo_left_html = (
        f'<div style="background:#fff;border-radius:14px;padding:6px 10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">'
        f'<img src="{imgs["logo"]}" style="height:56px;object-fit:contain;"></div>'
        if "logo" in imgs else
        '<span style="font-size:40px;line-height:1;flex-shrink:0;">🏦</span>'
    )
    sol_right_html = (
        f'<div style="background:#fff;border-radius:12px;padding:3px;width:72px;height:72px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">'
        f'<img src="{imgs["sol"]}" style="height:64px;width:64px;object-fit:contain;"></div>'
        if "sol" in imgs else ""
    )
    st.markdown(f"""
<div class="brand-header">
    {logo_left_html}
    <div class="brand-text" style="flex:1;padding-left:12px;">
        <p class="title">Call2Text</p>
        <p class="sub">AI 상담 요약 · 안내 문자 자동화 | 기억해조 5조</p>
    </div>
    {sol_right_html}
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: 메인
# ═══════════════════════════════════════════════════════════════
def page_main():
    render_brand_header()

    api_key = st.session_state.get("openai_api_key", "")
    if not api_key:
        st.error("❌ .env 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
        return

    # ── STEP 1 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">📥 STEP 1 &nbsp;·&nbsp; 상담 내용 입력</div>',
                unsafe_allow_html=True)

    method = st.radio("입력 방식",
                      ["✏️ 텍스트 직접 입력", "📁 음성 파일 업로드", "🎙️ 직접 녹음하기"],
                      horizontal=True, key="input_method")

    def _go_to_step2(transcript: str):
        # 공통: 하위 상태 전체 초기화
        st.session_state["masked_transcript"] = ""
        st.session_state["consultation_type"] = ""
        st.session_state["rag_results"]       = []
        st.session_state["sms_draft"]         = ""
        st.session_state["shinhan_products"]  = []
        st.session_state["consumer_products"] = []
        st.session_state.pop("sms_edit_area",  None)
        st.session_state.pop("_draft_changed", None)

        if st.session_state.get("step", 0) > 0:
            # 이미 진행 중인 세션 → step1로 완전 리셋 (빈 화면)
            st.session_state["transcript"]   = ""
            st.session_state["_reset_input"] = True
            st.session_state["step"]         = 0
        else:
            # step=0 (초기/리셋 후) → step2로 진행
            st.session_state["transcript"] = transcript
            st.session_state["step"]       = 2
        st.rerun()

    if method == "✏️ 텍스트 직접 입력":
        if st.session_state.pop("_reset_input", False):
            st.session_state.pop("txt_input", None)
        txt = st.text_area(
            "상담 내용", value=st.session_state.get("transcript",""), height=180,
            placeholder="TX (상담원): 안녕하세요, 신한은행입니다.\nRX (고객): 대출 한도 문의드립니다...",
            key="txt_input",
        )
        if st.button("✅ 다음 (마스킹)", key="btn_step1_txt", type="primary"):
            if not txt.strip():
                st.error("상담 내용을 입력하세요.")
            else:
                _go_to_step2(txt)

    elif method == "📁 음성 파일 업로드":
        audio = st.file_uploader("음성 파일 (.wav .mp3 .m4a)", type=["wav","mp3","m4a"])
        if audio:
            st.audio(audio)
            if st.button("🔄 STT 변환", key="btn_stt_upload", type="primary"):
                with st.spinner("Whisper로 변환 중..."):
                    try:
                        _go_to_step2(whisper_stt(audio.read(), api_key, audio.name))
                    except Exception as e:
                        st.error(f"STT 오류: {e}")

    else:
        st.info("🎙️ 아래 버튼을 눌러 녹음 후 STT 변환을 눌러주세요.")
        recorded = st.audio_input("녹음하기", key="audio_recorder")
        if recorded:
            st.audio(recorded)
            if st.button("🔄 STT 변환", key="btn_stt_record", type="primary"):
                with st.spinner("Whisper로 변환 중..."):
                    try:
                        _go_to_step2(whisper_stt(recorded.read(), api_key, "recording.wav"))
                    except Exception as e:
                        st.error(f"STT 오류: {e}")

    if st.session_state.get("step", 0) < 2:
        return

    # ── STEP 2 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">🔒 STEP 2 &nbsp;·&nbsp; 개인정보 마스킹</div>',
                unsafe_allow_html=True)

    raw = st.session_state["transcript"]
    if not st.session_state.get("masked_transcript"):
        st.session_state["masked_transcript"] = mask_pii(raw)

    col_l, col_r = st.columns(2)
    with col_l:
        st.caption("원본")
        st.text_area("원본", value=raw, height=180, disabled=True, key="raw_view")
    with col_r:
        st.caption("마스킹 결과 (수정 가능)")
        edited = st.text_area("마스킹", value=st.session_state["masked_transcript"],
                              height=180, key="masked_edit")
        st.session_state["masked_transcript"] = edited

    if st.button("✅ 다음 (분류·검색)", key="btn_step2", type="primary"):
        st.session_state.update({
            "step": 3, "consultation_type": "", "rag_results": [],
            "sms_draft": "", "shinhan_products": [], "consumer_products": [],
        })
        st.rerun()

    if st.session_state.get("step", 0) < 3:
        return

    # ── STEP 3 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">🔍 STEP 3 &nbsp;·&nbsp; 상담 유형 분류 & 유사 상담 검색</div>',
                unsafe_allow_html=True)

    masked = st.session_state["masked_transcript"]
    with st.spinner("분류 & 검색 중..."):
        if not st.session_state.get("consultation_type"):
            try:
                ctype = ai_classify(masked, api_key)
            except Exception:
                ctype = classify_keyword(masked)
            st.session_state["consultation_type"] = ctype
        if not st.session_state.get("rag_results"):
            st.session_state["rag_results"] = search_rag(masked, top_k=4)

    cats = list(CATEGORIES.keys()) + ["기타"]
    col_a, col_b = st.columns([1, 2])
    with col_a:
        ctype_sel = st.selectbox(
            "📌 분류 결과 (수정 가능)", cats,
            index=cats.index(st.session_state["consultation_type"])
            if st.session_state["consultation_type"] in cats else len(cats)-1,
            key="ctype_sel",
        )
        st.session_state["consultation_type"] = ctype_sel
    with col_b:
        results = st.session_state.get("rag_results", [])
        st.caption(f"유사 상담 {len(results)}건")
        for i, r in enumerate(results[:3], 1):
            with st.expander(f"예시 {i} | {r.get('category','')[:30]} (유사도 {r['score']:.2f})"):
                st.write(f"**Q:** {r.get('question','')[:150]}")
                st.write(f"**A:** {r.get('answer','')[:200]}")

    if st.button("✅ 다음 (AI 초안 생성)", key="btn_step3", type="primary"):
        st.session_state["step"] = 4
        st.rerun()

    if st.session_state.get("step", 0) < 4:
        return

    # ── STEP 4 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">🤖 STEP 4 &nbsp;·&nbsp; 상품 추천 & AI 문자 초안 생성</div>',
                unsafe_allow_html=True)

    masked  = st.session_state["masked_transcript"]
    ctype   = st.session_state["consultation_type"]
    results = st.session_state.get("rag_results", [])

    if not st.session_state.get("shinhan_products"):
        st.session_state["shinhan_products"] = recommend_shinhan_products(ctype)

    shin_prods = st.session_state["shinhan_products"]

    st.markdown("**🏦 신한은행 추천 상품**")
    if shin_prods:
        cols4 = st.columns(2)
        for i, p in enumerate(shin_prods, 1):
            with cols4[(i - 1) % 2]:
                st.markdown(
                    f'<div class="prod-card"><strong>{i}. {p["name"]}</strong>'
                    f'<br><small>📂 {p.get("category","")}</small>'
                    f'<br>{p.get("description","")}</div>', unsafe_allow_html=True)
    else:
        st.info("상품 정보 없음")

    auto_links = get_recommended_links(ctype)
    if not st.session_state.get("sms_draft"):
        with st.spinner("AI 문자 초안 생성 중..."):
            try:
                draft = ai_generate_draft(masked, ctype, results, shin_prods,
                                          [], auto_links, api_key)
                st.session_state["sms_draft"] = draft
            except Exception as e:
                st.error(f"초안 생성 오류: {e}")
                return

    if st.button("✅ 다음 (편집·발송)", key="btn_step4", type="primary"):
        st.session_state["step"] = 5
        st.rerun()

    if st.session_state.get("step", 0) < 5:
        return

    # ── STEP 5 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">✉️ STEP 5 &nbsp;·&nbsp; 문자 편집 & SMS 발송</div>',
                unsafe_allow_html=True)

    ctype      = st.session_state.get("consultation_type","")
    all_links  = load_json(LINKS_FILE, DEFAULT_LINKS)
    auto_links = [l for l in all_links if l.get("category") == ctype]
    templates  = load_json(TEMPLATES_FILE, [])

    col_edit, col_send = st.columns([3, 2])

    with col_edit:
        # 템플릿 선택
        tpl_sel = "(없음)"
        if templates:
            tpl_names = ["(없음)"] + [t["name"] for t in templates]
            tpl_sel   = st.selectbox("📝 템플릿 선택 (재생성 시 적용)", tpl_names, key="tpl_sel_step5")

        # 문자 편집 — 프로그래밍 방식 업데이트 시 위젯 생성 전에 동기화
        if "sms_edit_area" not in st.session_state or st.session_state.pop("_draft_changed", False):
            st.session_state["sms_edit_area"] = st.session_state.get("sms_draft", "")
        st.text_area("✉️ 문자 초안 (편집 가능)", height=220, key="sms_edit_area")
        st.session_state["sms_draft"] = st.session_state["sms_edit_area"]

        char_count = len(st.session_state["sms_draft"])
        msg_type   = "LMS" if char_count > 90 else "SMS"
        cls        = "char-warn" if char_count > 300 else "char-ok"
        st.markdown(f'<span class="{cls}">글자 수: {char_count}자 · {msg_type} 형식</span>',
                    unsafe_allow_html=True)

        # 재생성
        if st.button("🔄 초안 재생성", key="btn_regen"):
            tpl_content = None
            if tpl_sel != "(없음)":
                tpl_content = next((t["content"] for t in templates if t["name"] == tpl_sel), None)
            with st.spinner("재생성 중..."):
                try:
                    new_draft = ai_generate_draft(
                        st.session_state.get("masked_transcript",""),
                        ctype,
                        st.session_state.get("rag_results",[]),
                        st.session_state.get("shinhan_products",[]),
                        st.session_state.get("consumer_products",[]),
                        auto_links, api_key, template=tpl_content,
                    )
                    st.session_state["sms_draft"]    = new_draft
                    st.session_state["_draft_changed"] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"재생성 오류: {e}")

        st.markdown("---")

        # ── 추천 링크 (상담 유형 일치) ───────────────────────
        if auto_links:
            st.markdown(f"**🔗 추천 링크** — `{ctype}` 유형 매칭")
            for lk in auto_links:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(
                        f'<div class="link-card"><strong>{lk["name"]}</strong>'
                        f'<br><small>{lk.get("description","")}</small></div>',
                        unsafe_allow_html=True)
                with c2:
                    if st.button("삽입", key=f"ins_auto_{lk['name']}_{ctype}"):
                        cur = st.session_state.get("sms_draft", "")
                        st.session_state["sms_draft"]      = cur + f"\n{lk['url']}"
                        st.session_state["_draft_changed"] = True
                        st.rerun()

        # ── 전체 링크 검색 + 스크롤 ──────────────────────────
        with st.expander("🔗 전체 링크에서 삽입"):
            link_q = st.text_input("🔍 링크 검색", key="link_search_q",
                                   placeholder="상품명·분류 검색")
            filtered_links = [
                l for l in all_links
                if not link_q
                or link_q.lower() in l.get("name","").lower()
                or link_q.lower() in l.get("category","").lower()
                or link_q.lower() in l.get("description","").lower()
            ]
            with st.container(height=240):
                if not filtered_links:
                    st.caption("검색 결과 없음")
                for lk in filtered_links:
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(
                            f"**{lk['name']}** `{lk.get('category','')}` "
                            f"— {lk.get('description','')[:40]}"
                        )
                    with c2:
                        btn_key = f"ins_all_{lk['name']}_{lk.get('category','')}"
                        if st.button("삽입", key=btn_key):
                            cur = st.session_state.get("sms_draft", "")
                            st.session_state["sms_draft"]      = cur + f"\n{lk['url']}"
                            st.session_state["_draft_changed"] = True
                            st.rerun()

    with col_send:
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        st.markdown("**📨 발송 정보**")
        to_num = st.text_input("수신 번호", placeholder="010-1234-5678", key="to_num")

        sol_key    = st.session_state.get("solapi_api_key","")
        sol_secret = st.session_state.get("solapi_api_secret","")
        sol_from   = st.session_state.get("solapi_from_number","")

        approved = st.checkbox("✅ 내용 확인 후 발송 승인", key="sms_approve")
        send_btn = st.button("📨 SMS 발송", type="primary", key="btn_send",
                             disabled=not approved)

        if send_btn:
            final_text = st.session_state.get("sms_draft","")
            if not to_num:
                st.error("수신 번호를 입력하세요.")
            elif not sol_key or not sol_secret:
                st.error(".env 파일에 SOLAPI 키를 설정하세요.")
            elif len(final_text) > 300:
                st.error("300자를 초과했습니다.")
            else:
                with st.spinner("발송 중..."):
                    try:
                        res = send_sms(to_num, final_text, sol_key, sol_secret, sol_from)
                        if "groupId" in res or res.get("statusCode") == "2000":
                            st.success("✅ SMS 발송 완료!")
                            history = load_json(HISTORY_FILE, [])
                            history.append({
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "to": to_num, "type": ctype, "msg_type": msg_type,
                                "content": final_text, "chars": len(final_text),
                            })
                            save_json(HISTORY_FILE, history)
                            st.balloons()
                        else:
                            st.error(f"발송 실패: {res}")
                    except Exception as e:
                        st.error(f"발송 오류: {e}")

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("---")
        if st.button("🆕 새 상담 시작", key="btn_reset"):
            for k in list(_DEFAULTS.keys()):
                st.session_state[k] = _DEFAULTS[k]
            for wk in ["sms_edit_area","masked_edit","txt_input","audio_recorder"]:
                st.session_state.pop(wk, None)
            st.rerun()


# ═══════════════════════════════════════════════════════════════
# PAGE: 발송 이력
# ═══════════════════════════════════════════════════════════════
def page_history():
    st.markdown('<p class="page-title">📜 발송 이력</p>', unsafe_allow_html=True)
    history = load_json(HISTORY_FILE, [])
    if not history:
        st.info("발송 이력이 없습니다.")
        return

    col1, col2, col3 = st.columns([2,1,1])
    with col1: search = st.text_input("🔍 검색", key="hist_search")
    with col2: type_f = st.selectbox("유형", ["전체"]+list(CATEGORIES.keys())+["기타"], key="hist_type")
    with col3: sort_d = st.selectbox("정렬", ["최신순","오래된순"], key="hist_sort")

    filtered = list(reversed(history)) if sort_d == "최신순" else list(history)
    if search:
        filtered = [h for h in filtered
                    if search in h.get("content","") or search in h.get("to","")]
    if type_f != "전체":
        filtered = [h for h in filtered if h.get("type") == type_f]

    st.caption(f"총 {len(filtered)}건")
    for h in filtered:
        label = (f"[{h['timestamp']}] {h.get('type','')} | "
                 f"{h['to']} | {h.get('msg_type','SMS')} ({h.get('chars','-')}자)")
        with st.expander(label):
            st.text_area("내용", value=h["content"], height=120, disabled=True,
                         key=f"hist_{h['timestamp']}_{h['to']}")

    st.markdown("---")
    if st.button("🗑️ 전체 이력 삭제", key="clear_hist"):
        save_json(HISTORY_FILE, [])
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# PAGE: 설정
# ═══════════════════════════════════════════════════════════════
def page_settings():
    st.markdown('<p class="page-title">⚙️ 설정</p>', unsafe_allow_html=True)

    tab_link, tab_tpl, tab_rag = st.tabs(["🔗 링크 관리", "📝 문자 템플릿", "📊 RAG 현황"])

    # ── 링크 관리 ─────────────────────────────────────────────
    with tab_link:
        links = load_json(LINKS_FILE, DEFAULT_LINKS)
        cats  = list(CATEGORIES.keys()) + ["기타"]

        st.markdown("#### ➕ 링크 추가")
        with st.form("form_add_link", clear_on_submit=True):
            c1, c2 = st.columns(2)
            lname = c1.text_input("링크 이름 *", placeholder="직장인 신용대출 신규")
            lcat  = c2.selectbox("상담 유형 분류 *", cats)
            lurl  = st.text_input("URL *", placeholder="https://...")
            ldesc = st.text_input("링크 설명", placeholder="직장인 대상 신용대출 신규 신청 링크")
            if st.form_submit_button("➕ 추가", type="primary"):
                if lname and lurl:
                    links.append({"name":lname,"url":lurl,"description":ldesc,"category":lcat})
                    save_json(LINKS_FILE, links)
                    st.success(f"'{lname}' 추가 완료")
                    st.rerun()
                else:
                    st.error("이름과 URL은 필수입니다.")

        st.markdown("---")
        st.markdown("#### 📋 등록된 링크 목록")
        for cat in cats:
            cat_links = [l for l in links if l.get("category") == cat]
            if not cat_links:
                continue
            st.markdown(f"**{cat}** ({len(cat_links)}개)")
            for lk in cat_links:
                idx = links.index(lk)
                c_nm, c_url, c_desc, c_del = st.columns([2,3,2,1])
                c_nm.write(f"**{lk['name']}**")
                short = lk['url'][:45]+"..." if len(lk['url'])>45 else lk['url']
                c_url.markdown(f"[{short}]({lk['url']})")
                c_desc.write(lk.get("description",""))
                if c_del.button("🗑️", key=f"del_link_{cat}_{idx}"):
                    links.pop(idx)
                    save_json(LINKS_FILE, links)
                    st.rerun()

        st.markdown("---")
        if st.button("🔄 기본 링크 복원 (신한은행 기본 4개)"):
            save_json(LINKS_FILE, DEFAULT_LINKS)
            st.success("기본 링크로 복원됐습니다.")
            st.rerun()

    # ── 문자 템플릿 ───────────────────────────────────────────
    with tab_tpl:
        templates = load_json(TEMPLATES_FILE, [])

        st.markdown("""#### 📝 문자 템플릿 관리
STEP 5에서 템플릿을 선택하면 AI가 해당 형식으로 문자를 생성합니다.
`{요약}`, `{상품명}`, `{링크}` 등 자유롭게 플레이스홀더를 써도 됩니다.""")

        with st.form("form_add_tpl", clear_on_submit=True):
            tname    = st.text_input("템플릿 이름 *", placeholder="카드 안내 기본형")
            tcontent = st.text_area("템플릿 내용 *", height=150,
                placeholder=(
                    "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다.\n\n"
                    "{상담 내용 요약}\n\n"
                    "추천 상품: {상품명}\n"
                    "신청 링크: {링크}\n\n"
                    "문의: 1599-8000"
                ))
            if st.form_submit_button("➕ 템플릿 추가", type="primary"):
                if tname and tcontent:
                    templates.append({"name":tname,"content":tcontent})
                    save_json(TEMPLATES_FILE, templates)
                    st.success(f"'{tname}' 템플릿 추가 완료")
                    st.rerun()
                else:
                    st.error("이름과 내용은 필수입니다.")

        st.markdown("---")
        if not templates:
            st.info("등록된 템플릿이 없습니다. 위에서 추가하세요.")
        else:
            st.markdown(f"#### 등록된 템플릿 ({len(templates)}개)")
            for i, t in enumerate(templates):
                with st.expander(f"📝 {t['name']}"):
                    st.text_area("내용", value=t["content"], height=100, disabled=True,
                                 key=f"tpl_view_{i}")
                    if st.button("🗑️ 삭제", key=f"del_tpl_{i}"):
                        templates.pop(i)
                        save_json(TEMPLATES_FILE, templates)
                        st.rerun()

    # ── RAG 현황 ──────────────────────────────────────────────
    with tab_rag:
        st.markdown("#### 📊 데이터 로딩 현황")
        try:
            _, __, corpus = get_rag_engine()
            df_c  = get_consumer_df()
            shin  = get_shinhan_products()
            c1, c2, c3 = st.columns(3)
            c1.metric("금융상담 RAG", f"{len(corpus):,}건")
            c2.metric("소비자 데이터", f"{len(df_c):,}행" if df_c is not None else "없음")
            c3.metric("신한 상품", f"{len(shin):,}개")
        except Exception as e:
            st.warning(f"데이터 로딩 중... ({e})")


# ═══════════════════════════════════════════════════════════════
# Sidebar + routing
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    _imgs = get_brand_images()
    if "logo" in _imgs:
        st.markdown(
            f'<img src="{_imgs["logo"]}" style="height:38px;object-fit:contain;filter:brightness(0) invert(1);display:block;margin-bottom:4px;">',
            unsafe_allow_html=True)
    else:
        st.markdown("## 🏦 신한은행")
    st.markdown("### Call2Text")
    st.markdown("*AI 상담 문자 자동화*")
    st.markdown("---")

    menu = st.radio("메뉴", ["📋 메인", "📜 발송 이력", "⚙️ 설정"],
                    key="nav_menu", label_visibility="collapsed")

    st.markdown("---")
    api_ok = bool(st.session_state.get("openai_api_key"))
    sms_ok = bool(st.session_state.get("solapi_api_key"))
    st.markdown(f"{'✅' if api_ok else '❌'} OpenAI &nbsp;&nbsp; {'✅' if sms_ok else '❌'} Solapi",
                unsafe_allow_html=True)

    try:
        _, __, corpus = get_rag_engine()
        df_c = get_consumer_df()
        st.caption(f"RAG: {len(corpus):,}건")
        st.caption(f"소비자: {len(df_c):,}행" if df_c is not None else "소비자 데이터 없음")
    except Exception:
        st.caption("데이터 로딩 중...")

    step = st.session_state.get("step", 0)
    if step > 0:
        st.markdown(f"진행 단계: **{step}/5**")

    st.markdown("---")
    st.caption("기억해조 5조 · v2.1")

if menu == "📋 메인":
    page_main()
elif menu == "📜 발송 이력":
    page_history()
elif menu == "⚙️ 설정":
    page_settings()
