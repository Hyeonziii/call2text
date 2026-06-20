"""
Call2Text - AI 상담 요약 · 안내 문자 자동화
v2.0 | 기억해조 5조 | 신한은행
"""
import streamlit as st
import os, json, re, zipfile, glob, hmac, hashlib, uuid, io, requests
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Page config ───────────────────────────────────────────────
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

# 신한은행 기본 링크 (최초 1회 초기화)
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
if not LINKS_FILE.exists():
    LINKS_FILE.write_text(json.dumps(DEFAULT_LINKS, ensure_ascii=False, indent=2), encoding="utf-8")

# ── CSS (신한은행 브랜드) ─────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #001f6b 0%, #003DA5 100%) !important;
}
section[data-testid="stSidebar"] * { color: #ffffff !important; }
section[data-testid="stSidebar"] .stRadio label {
    font-size: 14px !important; padding: 8px 0 !important;
    border-bottom: 1px solid rgba(255,255,255,0.1) !important;
}
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.2) !important; }

/* ── Main bg ── */
.stApp { background: #f0f4f9 !important; }

/* ── Brand header ── */
.brand-header {
    background: linear-gradient(135deg, #003DA5 0%, #0055CC 100%);
    border-radius: 12px;
    padding: 24px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 20px;
    box-shadow: 0 4px 16px rgba(0,61,165,0.25);
}
.brand-title { font-size: 26px; font-weight: 700; color: #ffffff !important; margin: 0; }
.brand-sub   { font-size: 13px; color: rgba(255,255,255,0.85) !important; margin: 4px 0 0; }
.brand-badge {
    background: #FF6B35; color: #ffffff !important;
    padding: 4px 12px; border-radius: 20px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}

/* ── Step header ── */
.step-header {
    background: #003DA5; color: white !important;
    padding: 11px 20px; border-radius: 8px;
    margin: 22px 0 14px; font-size: 14px; font-weight: 600;
    border-left: 5px solid #FF6B35;
    display: flex; align-items: center; gap: 8px;
}

/* ── Page title ── */
.page-title { font-size: 26px; font-weight: 700; color: #003DA5; margin-bottom: 4px; }
.page-sub   { font-size: 13px; color: #666; margin-bottom: 20px; }

/* ── Cards ── */
.info-card {
    background: white; border-radius: 10px; padding: 18px 22px;
    border: 1px solid #dce4f0; margin-bottom: 14px;
    box-shadow: 0 2px 8px rgba(0,61,165,0.08);
}
.prod-card {
    background: #e8f0fc; border-radius: 8px; padding: 14px 16px;
    border-left: 4px solid #003DA5; margin-bottom: 10px;
}
.prod-card-stat {
    background: #e8f5e9; border-radius: 8px; padding: 14px 16px;
    border-left: 4px solid #2e7d32; margin-bottom: 10px;
}
.link-card {
    background: #fff8f0; border-radius: 8px; padding: 12px 16px;
    border-left: 4px solid #FF6B35; margin-bottom: 8px;
}

/* ── Badges ── */
.badge-ok  { background:#e8f5e9; color:#2e7d32; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:500; }
.badge-err { background:#fce4ec; color:#c62828; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:500; }
.char-ok   { color:#2e7d32; font-size:13px; font-weight:500; }
.char-warn { color:#e65100; font-size:13px; font-weight:500; }

/* ── Buttons ── */
.stButton>button[kind="primary"] {
    background: #003DA5 !important; border: none !important;
    font-weight: 600 !important; border-radius: 6px !important;
}
.stButton>button[kind="primary"]:hover {
    background: #0050CC !important;
}

/* ── Form ── */
div[data-testid="stForm"] { border: none !important; }

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: white; border-radius: 8px; padding: 12px;
    border: 1px solid #dce4f0;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
def _get_secret(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        try:
            val = st.secrets[key]
        except Exception:
            pass
    return val or ""

_DEFAULTS = {
    "openai_api_key":        _get_secret("OPENAI_API_KEY"),
    "solapi_api_key":        _get_secret("SOLAPI_API_KEY"),
    "solapi_api_secret":     _get_secret("SOLAPI_API_SECRET"),
    "solapi_from_number":    _get_secret("SOLAPI_FROM_NUMBER"),
    "transcript":            "",
    "masked_transcript":     "",
    "consultation_type":     "",
    "rag_results":           [],
    "sms_draft":             "",
    "recommended_products":  [],
    "consumer_products":     [],
    "step":                  0,
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
    # 전화번호
    text = re.sub(r"01[0-9]-?\d{3,4}-?\d{4}", "[전화번호]", text)
    # 주민등록번호 전체
    text = re.sub(r"\d{6}-[1-4]\d{6}", "[주민번호]", text)
    # 주민번호 / 생년월일 앞 6자리 (문맥 기반)
    text = re.sub(
        r"(?:주민(?:등록)?번호|생년월일)[^\d\n]{0,10}(\d{6})",
        lambda m: m.group().replace(m.group(1), "[주민번호앞자리]"), text
    )
    # 생년월일 8자리 (YYYYMMDD)
    text = re.sub(r"\b(19|20)\d{6}\b", "[생년월일]", text)
    # 통장/카드 비밀번호 4자리 (문맥 기반)
    text = re.sub(
        r"(?:비밀번호|PIN번호|pin번호)[^\d\n]{0,5}(\d{4})",
        lambda m: m.group().replace(m.group(1), "[비밀번호]"), text, flags=re.IGNORECASE
    )
    # 계좌번호
    text = re.sub(r"\d{3,6}-\d{2,6}-\d{4,8}", "[계좌번호]", text)
    # 카드번호 (16자리)
    text = re.sub(r"\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}", "[카드번호]", text)
    # 이메일
    text = re.sub(r"[\w.\-]+@[\w.\-]+\.\w+", "[이메일]", text)
    return text

# ── Consultation categories ───────────────────────────────────
CATEGORIES = {
    "예금/적금": ["예금", "적금", "저축", "통장", "금리", "이자", "만기", "해지", "정기"],
    "대출":      ["대출", "융자", "담보", "신용대출", "주택담보", "전세자금", "한도", "상환", "이자율", "대부"],
    "카드":      ["카드", "체크카드", "신용카드", "포인트", "혜택", "결제", "청구", "연회비"],
    "전자금융":  ["인터넷뱅킹", "모바일", "앱", "OTP", "이체", "송금", "계좌이체", "공인인증"],
    "투자/펀드": ["펀드", "투자", "주식", "ETF", "채권", "수익률", "위험", "증권", "적립", "IRP", "연금"],
    "보험":      ["보험", "연금", "보장", "보험료", "수익자", "보험금", "종신", "암"],
    "외환":      ["환전", "외화", "달러", "유로", "환율", "해외송금"],
}

def classify_keyword(text: str) -> str:
    scores = {cat: sum(1 for kw in kws if kw in text) for cat, kws in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "기타"

# ── RAG: CoT + 금융상담 (공공민원 제외) ──────────────────────
@st.cache_resource(show_spinner=False)
def get_rag_engine():
    from sklearn.feature_extraction.text import TfidfVectorizer
    corpus = []

    # 36번 CoT (금융상품 추천)
    pat = str(BASE_DIR / "36.금융상품·서비스 및 소비자 특성 데이터" / "**" / "02.라벨링데이터" / "*L_1.CoT*.zip")
    for zp in glob.glob(pat, recursive=True):
        try:
            with zipfile.ZipFile(zp) as zf:
                jfiles = [f for f in zf.namelist() if f.endswith(".json")]
                for fname in jfiles[:120]:
                    try:
                        d = json.loads(zf.read(fname).decode("utf-8"))
                        if isinstance(d, dict) and "question" in d:
                            corpus.append({
                                "type": "product_cot",
                                "category": d.get("category", ""),
                                "query_type": d.get("query_type", ""),
                                "question": d.get("question", ""),
                                "answer": d.get("answer", ""),
                                "product_names": d.get("product_names", []),
                                "cot1": d.get("cot1", ""),
                                "text": (d.get("question", "") + " " + d.get("cot1", ""))[:400],
                            })
                    except Exception:
                        continue
        except Exception:
            continue

    # 25번 금융상담
    pat = str(BASE_DIR / "25.금융분야_고객상담_데이터" / "**" / "02.라벨링데이터" / "*L_*.zip.part0")
    for zp in glob.glob(pat, recursive=True):
        try:
            with zipfile.ZipFile(zp) as zf:
                jfiles = [f for f in zf.namelist() if f.endswith(".json")]
                for fname in jfiles[:60]:
                    try:
                        d = json.loads(zf.read(fname).decode("utf-8"))
                        if isinstance(d, dict) and "qa_data" in d:
                            content = d.get("source", {}).get("consulting_content", "")[:300]
                            for qa in d["qa_data"][:3]:
                                q = qa.get("input", {}).get("question", "")
                                a = qa.get("output", "")
                                if q and a:
                                    corpus.append({
                                        "type": "bank_qa",
                                        "category": qa.get("qa_topic", ""),
                                        "question": q, "answer": a,
                                        "product_names": [],
                                        "text": content + " " + q,
                                    })
                    except Exception:
                        continue
        except Exception:
            continue

    if not corpus:
        return None, None, []

    texts = [c["text"] for c in corpus]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), max_features=30000)
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix, corpus


def search_rag(query: str, top_k: int = 6):
    from sklearn.metrics.pairwise import cosine_similarity
    vectorizer, matrix, corpus = get_rag_engine()
    if vectorizer is None:
        return []
    qvec = vectorizer.transform([query])
    scores = cosine_similarity(qvec, matrix).flatten()
    idxs = scores.argsort()[-top_k:][::-1]
    return [{**corpus[i], "score": float(scores[i])} for i in idxs if scores[i] > 0.03]


# ── 소비자 특성 데이터 ─────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_consumer_df():
    import pandas as pd
    dfs = []
    for split, prefix in [("Training", "TL"), ("Validation", "VL")]:
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
            profile["age"] = ag
            break
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
    if "age" in profile:
        mask &= df["age"] == profile["age"]
    if "gender" in profile:
        mask &= df["gender"] == profile["gender"]
    filtered = df[mask] if mask.sum() >= 20 else df
    top = filtered["product_name"].value_counts().head(top_k)
    results = []
    for pname, cnt in top.items():
        row = filtered[filtered["product_name"] == pname].iloc[0]
        results.append({
            "product_name": pname, "count": int(cnt),
            "age": row.get("age",""), "gender": row.get("gender",""),
            "income_bracket": row.get("income_bracket",""),
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
    buf = io.BytesIO(audio_bytes)
    buf.name = filename
    return client.audio.transcriptions.create(model="whisper-1", file=buf, language="ko").text

def ai_classify(text: str, api_key: str) -> str:
    cats = list(CATEGORIES.keys()) + ["기타"]
    result = openai_chat([
        {"role": "system", "content": f"상담 유형을 정확히 하나만 골라 답하세요: {', '.join(cats)}"},
        {"role": "user",   "content": text[:600]},
    ], api_key, temperature=0)
    for c in cats:
        if c in result:
            return c
    return "기타"

def ai_generate_draft(masked, ctype, rag_results, cot_products, consumer_products, links, api_key):
    rag_ctx = "\n".join(
        f"- Q: {r['question'][:80]}\n  A: {r['answer'][:120]}"
        for r in rag_results[:3] if r.get("type") == "bank_qa"
    )
    cot_ctx = "\n".join(
        f"{i}. {', '.join(p.get('product_names',[])[:2])}: {p.get('answer','')[:80]}"
        for i, p in enumerate(cot_products[:2], 1) if p.get("product_names")
    )
    stat_ctx = "\n".join(
        f"{i}. {p['product_name']} (유사고객 {p['count']}명)"
        for i, p in enumerate(consumer_products[:2], 1)
    )
    link_ctx = "\n".join(
        f"- {l['name']}: {l['url']}"
        for l in links[:2] if l.get("url")
    )

    prompt = f"""신한은행 고객 안내 문자를 작성하세요.

[상담 유형] {ctype}
[상담 요약] {masked[:700]}
[참조 상담] {rag_ctx or '없음'}
[AI 추천 상품] {cot_ctx or '없음'}
[유사고객 가입 상품] {stat_ctx or '없음'}
[안내 링크] {link_ctx or '없음'}

규칙:
- 반드시 첫 줄에 "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다" 로 시작
- 전체 300자 이내 (LMS)
- 정중하고 신뢰감 있는 어투
- 핵심 정보(상품명, 조건, 안내 링크)를 명확하게
- 마지막에 "문의: 신한은행 고객센터 1599-8000" 포함
- 개인정보 제외

문자 초안만 작성 (설명 없이):"""

    return openai_chat([
        {"role": "system", "content": "당신은 신한은행 고객 안내 문자 전문 작성자입니다."},
        {"role": "user", "content": prompt},
    ], api_key)


# ── SMS (Solapi) ──────────────────────────────────────────────
def send_sms(to, content, api_key, api_secret, from_num):
    date_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    salt = str(uuid.uuid4())
    sig = hmac.new(api_secret.encode(), (date_str + salt).encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"HMAC-SHA256 apiKey={api_key}, date={date_str}, salt={salt}, signature={sig}",
        "Content-Type": "application/json",
    }
    msg_type = "LMS" if len(content) > 90 else "SMS"
    payload = {"message": {"to": to.replace("-",""), "from": from_num.replace("-",""), "text": content, "type": msg_type}}
    r = requests.post("https://api.solapi.com/messages/v4/send", headers=headers, json=payload, timeout=10)
    return r.json()


# ── 링크 추천 (상담 유형 기반) ────────────────────────────────
def get_recommended_links(ctype: str) -> list:
    links = load_json(LINKS_FILE, DEFAULT_LINKS)
    return [l for l in links if l.get("category") == ctype]


# ═══════════════════════════════════════════════════════════════
# PAGE: 메인
# ═══════════════════════════════════════════════════════════════
def page_main():
    # 브랜드 헤더
    st.markdown("""
    <div class="brand-header">
        <div>
            <p class="brand-title">🏦 Call2Text</p>
            <p class="brand-sub">AI 상담 요약 · 안내 문자 자동화 | 기억해조 5조</p>
        </div>
        <span class="brand-badge">SHINHAN BANK</span>
    </div>
    """, unsafe_allow_html=True)

    api_key = st.session_state.get("openai_api_key", "") or _get_secret("OPENAI_API_KEY")
    if api_key:
        st.session_state["openai_api_key"] = api_key
    if not api_key:
        st.error("❌ OpenAI API 키가 설정되지 않았습니다. ⚙️ 설정 메뉴 또는 Streamlit Cloud의 App settings > Secrets에 OPENAI_API_KEY를 추가해주세요.")
        return

    # ── STEP 1 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">📥 STEP 1 &nbsp;·&nbsp; 상담 내용 입력</div>', unsafe_allow_html=True)

    input_method = st.radio(
        "입력 방식",
        ["✏️ 텍스트 직접 입력", "📁 음성 파일 업로드", "🎙️ 직접 녹음하기"],
        horizontal=True, key="input_method",
    )

    if input_method == "✏️ 텍스트 직접 입력":
        txt = st.text_area(
            "상담 내용", value=st.session_state.get("transcript",""), height=180,
            placeholder="TX (상담원): 안녕하세요, 신한은행입니다.\nRX (고객): 대출 한도 문의드립니다...",
            key="txt_input",
        )
        if st.button("✅ 다음 (마스킹)", key="btn_step1_txt", type="primary"):
            if not txt.strip():
                st.error("상담 내용을 입력하세요.")
            else:
                st.session_state["transcript"] = txt
                st.session_state["step"] = 2
                st.rerun()

    elif input_method == "📁 음성 파일 업로드":
        audio = st.file_uploader("음성 파일 (.wav .mp3 .m4a)", type=["wav","mp3","m4a"])
        if audio:
            st.audio(audio)
            if st.button("🔄 STT 변환", key="btn_stt_upload", type="primary"):
                with st.spinner("Whisper로 변환 중..."):
                    try:
                        text = whisper_stt(audio.read(), api_key, audio.name)
                        st.session_state["transcript"] = text
                        st.session_state["step"] = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"STT 오류: {e}")

    else:
        st.info("🎙️ 아래 버튼을 눌러 녹음하세요. 완료 후 STT 변환을 눌러주세요.")
        recorded = st.audio_input("녹음하기", key="audio_recorder")
        if recorded:
            st.audio(recorded)
            if st.button("🔄 STT 변환", key="btn_stt_record", type="primary"):
                with st.spinner("Whisper로 변환 중..."):
                    try:
                        text = whisper_stt(recorded.read(), api_key, "recording.wav")
                        st.session_state["transcript"] = text
                        st.session_state["step"] = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"STT 오류: {e}")

    if st.session_state.get("step", 0) < 2:
        return

    # ── STEP 2 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">🔒 STEP 2 &nbsp;·&nbsp; 개인정보 마스킹</div>', unsafe_allow_html=True)

    raw = st.session_state["transcript"]
    if not st.session_state.get("masked_transcript"):
        st.session_state["masked_transcript"] = mask_pii(raw)

    col_l, col_r = st.columns(2)
    with col_l:
        st.caption("원본")
        st.text_area("원본", value=raw, height=160, disabled=True, key="raw_view")
    with col_r:
        st.caption("마스킹 결과 (수정 가능)")
        masked_edit = st.text_area("마스킹", value=st.session_state["masked_transcript"], height=160, key="masked_edit")
        st.session_state["masked_transcript"] = masked_edit

    if st.button("✅ 다음 (분류·검색)", key="btn_step2", type="primary"):
        st.session_state.update({"step":3,"consultation_type":"","rag_results":[],
                                  "sms_draft":"","recommended_products":[],"consumer_products":[]})
        st.rerun()

    if st.session_state.get("step", 0) < 3:
        return

    # ── STEP 3 ────────────────────────────────────────────────
    st.markdown('<div class="step-header">🔍 STEP 3 &nbsp;·&nbsp; 상담 유형 분류 & 유사 상담 검색</div>', unsafe_allow_html=True)

    masked = st.session_state["masked_transcript"]
    with st.spinner("분류 & RAG 검색 중..."):
        if not st.session_state.get("consultation_type"):
            try:
                ctype = ai_classify(masked, api_key)
            except Exception:
                ctype = classify_keyword(masked)
            st.session_state["consultation_type"] = ctype
        if not st.session_state.get("rag_results"):
            st.session_state["rag_results"] = search_rag(masked, top_k=6)

    cats = list(CATEGORIES.keys()) + ["기타"]
    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        ctype_sel = st.selectbox(
            "📌 분류 결과 (수정 가능)", cats,
            index=cats.index(st.session_state["consultation_type"]) if st.session_state["consultation_type"] in cats else len(cats)-1,
            key="ctype_sel",
        )
        st.session_state["consultation_type"] = ctype_sel
        st.markdown("</div>", unsafe_allow_html=True)
    with col_b:
        results = st.session_state.get("rag_results", [])
        st.caption(f"유사 상담 {len(results)}건 검색됨")
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
    st.markdown('<div class="step-header">🤖 STEP 4 &nbsp;·&nbsp; 상품 추천 & AI 문자 초안 생성</div>', unsafe_allow_html=True)

    masked  = st.session_state["masked_transcript"]
    ctype   = st.session_state["consultation_type"]
    results = st.session_state.get("rag_results", [])

    if not st.session_state.get("recommended_products"):
        cot_prods = [r for r in results if r.get("type")=="product_cot" and r.get("product_names")]
        st.session_state["recommended_products"] = cot_prods[:3]
    if not st.session_state.get("consumer_products"):
        with st.spinner("소비자 데이터 분석 중..."):
            st.session_state["consumer_products"] = recommend_from_consumer(masked, top_k=3)

    cot_prods      = st.session_state["recommended_products"]
    consumer_prods = st.session_state["consumer_products"]

    col_cot, col_stat = st.columns(2)
    with col_cot:
        st.markdown("**🤖 AI CoT 추천 상품**")
        if cot_prods:
            for i, p in enumerate(cot_prods, 1):
                names = ", ".join(p.get("product_names",[])[:2]) or "상품명 없음"
                st.markdown(
                    f'<div class="prod-card"><strong>{i}. {names}</strong>'
                    f'<br><small>📂 {p.get("category","")}</small>'
                    f'<br><br>{p.get("answer","")[:160]}...</div>',
                    unsafe_allow_html=True)
        else:
            st.info("CoT 매칭 상품 없음")
    with col_stat:
        st.markdown("**📊 유사고객 실적 기반 추천**")
        if consumer_prods:
            for i, p in enumerate(consumer_prods, 1):
                profile_str = " · ".join(filter(None, [p.get("age",""), p.get("gender",""), p.get("income_bracket","")]))
                st.markdown(
                    f'<div class="prod-card-stat"><strong>{i}. {p["product_name"]}</strong>'
                    f'<br><small>👥 유사 고객 {p["count"]:,}명 가입 | {profile_str}</small></div>',
                    unsafe_allow_html=True)
        else:
            st.info("소비자 데이터 매칭 없음")

    # 상담 유형 기반 자동 링크 추천
    auto_links = get_recommended_links(ctype)

    if not st.session_state.get("sms_draft"):
        with st.spinner("AI 문자 초안 생성 중..."):
            try:
                draft = ai_generate_draft(masked, ctype, results, cot_prods, consumer_prods, auto_links, api_key)
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
    st.markdown('<div class="step-header">✉️ STEP 5 &nbsp;·&nbsp; 문자 편집 & SMS 발송</div>', unsafe_allow_html=True)

    all_links = load_json(LINKS_FILE, DEFAULT_LINKS)
    ctype     = st.session_state.get("consultation_type","")
    auto_links = [l for l in all_links if l.get("category") == ctype]
    other_links = [l for l in all_links if l.get("category") != ctype]

    col_edit, col_send = st.columns([3, 2])

    with col_edit:
        draft = st.text_area(
            "✉️ 문자 초안 (편집 가능)",
            value=st.session_state.get("sms_draft",""),
            height=220, key="sms_edit_area",
        )
        st.session_state["sms_draft"] = draft

        char_count = len(draft)
        msg_type   = "LMS" if char_count > 90 else "SMS"
        color_cls  = "char-warn" if char_count > 300 else "char-ok"
        st.markdown(f'<span class="{color_cls}">글자 수: {char_count}자 · {msg_type} 형식</span>', unsafe_allow_html=True)

        # 자동 추천 링크 (상담 유형 일치)
        if auto_links:
            st.markdown("**🔗 추천 링크** (상담 유형 일치)")
            for lk in auto_links:
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(
                        f'<div class="link-card"><strong>{lk["name"]}</strong>'
                        f'<br><small>{lk.get("description","")}</small>'
                        f'<br><code style="font-size:11px">{lk["url"][:60]}...</code></div>',
                        unsafe_allow_html=True)
                with col_btn:
                    if st.button("삽입", key=f"ins_{lk['name']}"):
                        st.session_state["sms_draft"] = draft + f"\n{lk['url']}"
                        st.rerun()

        # 기타 링크 직접 추가
        if other_links:
            with st.expander("🔗 기타 링크 추가"):
                for lk in other_links:
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**{lk['name']}** `{lk.get('category','')}` — {lk.get('description','')}")
                    with col_btn:
                        if st.button("삽입", key=f"ins_other_{lk['name']}"):
                            st.session_state["sms_draft"] = draft + f"\n{lk['url']}"
                            st.rerun()

        if st.button("🔄 초안 재생성", key="btn_regen"):
            st.session_state["sms_draft"] = ""
            st.session_state["step"] = 4
            st.rerun()

    with col_send:
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        st.markdown("**📨 발송 정보**")
        to_num = st.text_input("수신 번호", placeholder="010-1234-5678", key="to_num")

        sol_key    = st.session_state.get("solapi_api_key","")
        sol_secret = st.session_state.get("solapi_api_secret","")
        sol_from   = st.session_state.get("solapi_from_number","")

        approved = st.checkbox("✅ 내용 확인 후 발송 승인", key="sms_approve")
        send_btn = st.button("📨 SMS 발송", type="primary", key="btn_send", disabled=not approved)

        if send_btn:
            if not to_num:
                st.error("수신 번호를 입력하세요.")
            elif not sol_key or not sol_secret:
                st.error(".env 파일에 SOLAPI 키를 설정하세요.")
            elif char_count > 300:
                st.error("300자를 초과했습니다.")
            else:
                with st.spinner("발송 중..."):
                    try:
                        res = send_sms(to_num, draft, sol_key, sol_secret, sol_from)
                        if "groupId" in res or res.get("statusCode") == "2000":
                            st.success("✅ SMS 발송 완료!")
                            history = load_json(HISTORY_FILE, [])
                            history.append({
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "to": to_num, "type": ctype, "msg_type": msg_type,
                                "content": draft, "chars": char_count,
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
        filtered = [h for h in filtered if search in h.get("content","") or search in h.get("to","")]
    if type_f != "전체":
        filtered = [h for h in filtered if h.get("type") == type_f]

    st.caption(f"총 {len(filtered)}건")
    for h in filtered:
        label = f"[{h['timestamp']}] {h.get('type','')} | {h['to']} | {h.get('msg_type','SMS')} ({h.get('chars','-')}자)"
        with st.expander(label):
            st.text_area("내용", value=h["content"], height=120, disabled=True,
                         key=f"hist_{h['timestamp']}_{h['to']}")
    st.markdown("---")
    if st.button("🗑️ 전체 이력 삭제", key="clear_hist"):
        save_json(HISTORY_FILE, [])
        st.success("삭제 완료")
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# PAGE: 설정 (링크 관리)
# ═══════════════════════════════════════════════════════════════
def page_settings():
    st.markdown('<p class="page-title">⚙️ 설정</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-sub">안내 문자 발송 시 자동 추천될 링크를 관리합니다.</p>', unsafe_allow_html=True)

    links = load_json(LINKS_FILE, DEFAULT_LINKS)
    cats  = list(CATEGORIES.keys()) + ["기타"]

    # ── 링크 추가 폼 ──────────────────────────────────────────
    st.markdown("#### ➕ 링크 추가")
    with st.form("form_add_link", clear_on_submit=True):
        c1, c2 = st.columns(2)
        lname = c1.text_input("링크 이름 *", placeholder="직장인 신용대출 신규")
        lcat  = c2.selectbox("상담 유형 분류 *", cats)
        lurl  = st.text_input("URL *", placeholder="https://...")
        ldesc = st.text_input("링크 설명", placeholder="직장인 대상 신용대출 신규 신청 링크")
        if st.form_submit_button("➕ 추가", type="primary"):
            if lname and lurl:
                links.append({"name": lname, "url": lurl, "description": ldesc, "category": lcat})
                save_json(LINKS_FILE, links)
                st.success(f"✅ '{lname}' 링크가 추가되었습니다.")
                st.rerun()
            else:
                st.error("이름과 URL은 필수입니다.")

    st.markdown("---")

    # ── 등록된 링크 목록 ──────────────────────────────────────
    st.markdown("#### 📋 등록된 링크 목록")
    st.caption("상담 유형 분류가 일치하면 STEP 5에서 자동 추천됩니다.")

    # 분류별 그룹
    for cat in cats:
        cat_links = [l for l in links if l.get("category") == cat]
        if not cat_links:
            continue
        st.markdown(f"**{cat}** ({len(cat_links)}개)")
        for i, lk in enumerate(cat_links):
            col_name, col_url, col_desc, col_del = st.columns([2, 3, 2, 1])
            col_name.write(f"**{lk['name']}**")
            col_url.markdown(f"[{lk['url'][:40]}...]({lk['url']})" if len(lk['url'])>40 else f"[{lk['url']}]({lk['url']})")
            col_desc.write(lk.get("description",""))
            # 삭제 버튼
            global_idx = links.index(lk)
            if col_del.button("🗑️", key=f"del_{cat}_{i}"):
                links.pop(global_idx)
                save_json(LINKS_FILE, links)
                st.rerun()

    st.markdown("---")
    # 기본 링크 복원
    if st.button("🔄 기본 링크 복원 (신한은행 기본 4개)"):
        save_json(LINKS_FILE, DEFAULT_LINKS)
        st.success("기본 링크로 복원되었습니다.")
        st.rerun()

    # RAG 현황
    st.markdown("---")
    st.markdown("#### 📊 RAG 데이터 현황")
    try:
        _, __, corpus = get_rag_engine()
        df_c = get_consumer_df()
        col1, col2, col3 = st.columns(3)
        types = {}
        for c in corpus:
            types[c["type"]] = types.get(c["type"], 0) + 1
        labels = {"product_cot":"금융상품(CoT)","bank_qa":"금융상담"}
        for col, (t, cnt) in zip([col1,col2], types.items()):
            col.metric(labels.get(t,t), f"{cnt:,}건")
        col3.metric("소비자 데이터", f"{len(df_c):,}행" if df_c is not None else "없음")
    except Exception:
        st.warning("데이터 로딩 중...")


# ═══════════════════════════════════════════════════════════════
# Sidebar + routing
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏦 신한은행")
    st.markdown("### Call2Text")
    st.markdown("*AI 상담 문자 자동화*")
    st.markdown("---")

    menu = st.radio(
        "메뉴",
        ["📋 메인", "📜 발송 이력", "⚙️ 설정"],
        key="nav_menu",
        label_visibility="collapsed",
    )

    st.markdown("---")
    api_ok = bool(st.session_state.get("openai_api_key"))
    sms_ok = bool(st.session_state.get("solapi_api_key"))
    st.markdown(f"{'✅' if api_ok else '❌'} OpenAI &nbsp;&nbsp; {'✅' if sms_ok else '❌'} Solapi", unsafe_allow_html=True)

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
    st.caption("기억해조 5조 · v2.0")

if menu == "📋 메인":
    page_main()
elif menu == "📜 발송 이력":
    page_history()
elif menu == "⚙️ 설정":
    page_settings()
