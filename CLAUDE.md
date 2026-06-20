# Call2Text — 프로젝트 가이드

**AI 상담 요약 · 안내 문자 자동화** | 기억해조 5조 | PRD v2.0

---

## 실행

```bash
streamlit run app.py
```

의존성 설치:
```bash
pip install -r requirements.txt
```

---

## 파일 구조

```
기억해조/
├── app.py                          # 메인 앱 (단일 파일, 전체 로직 포함)
├── requirements.txt
├── .env                            # API 키 (git에 커밋하지 말 것)
├── CLAUDE.md
├── .cache/                         # 앱 실행 시 자동 생성
│   ├── history.json                # SMS 발송 이력
│   ├── links.json                  # 관리자 등록 안내 링크
│   └── templates.json              # 문자 템플릿
│
├── 36.금융상품·서비스 및 소비자 특성 데이터/
│   └── 3.개방데이터/1.데이터/{Training,Validation}/02.라벨링데이터/
│       ├── TL_1.CoT_1.증권_*.zip   # 증권 상품 추천 CoT 데이터
│       ├── TL_1.CoT_2.보험_*.zip   # 보험 상품 추천 CoT 데이터
│       ├── VL_1.CoT_*.zip          # Validation 세트 (동일 구조)
│       └── TL_2.소비자.zip          # 소비자 특성 데이터
│
├── 25.금융분야_고객상담_데이터/
│   └── 3.개방데이터/2.데이터(NIA)/{Training,Validation}/02.라벨링데이터/
│       ├── TL_은행.zip.part0        # 은행 상담 Q&A
│       ├── TL_증권.zip.part0
│       ├── TL_보험.zip.part0
│       └── VL_*.zip.part0
│
└── 24.공공 민원 상담 LLM 사전학습 및 Instruction Tuning 데이터/
    └── 3.개방데이터/1.데이터/{Training,Validation}/02.라벨링데이터/
        ├── TL_중앙행정기관_질의응답.zip
        ├── TL_지방행정기관_질의응답.zip
        └── VL_*_질의응답.zip
```

> **RAG 규칙**: 01.원천데이터는 사용하지 않는다. 02.라벨링데이터만 사용.

---

## 환경 변수 (.env)

```env
OPENAI_API_KEY=sk-proj-...
SOLAPI_API_KEY=
SOLAPI_API_SECRET=
SOLAPI_FROM_NUMBER=
```

앱 시작 시 `load_dotenv()`로 자동 로드 → `st.session_state`에 주입.  
설정 메뉴에서 런타임 중 변경도 가능 (session state에만 저장, .env는 수정 안 함).

---

## 아키텍처

### 단일 파일 구조 (app.py)

모든 로직이 `app.py` 하나에 있다. 함수 구분:

| 영역 | 함수 |
|------|------|
| 데이터 I/O | `load_json()`, `save_json()` |
| PII 마스킹 | `mask_pii()` |
| 분류 | `classify_keyword()`, `ai_classify()` |
| RAG | `get_rag_engine()`, `search_rag()` |
| LLM | `openai_chat()`, `whisper_stt()`, `ai_generate_draft()` |
| SMS | `send_sms()` |
| 페이지 | `page_main()`, `page_history()`, `page_settings()` |

### 페이지 라우팅

Streamlit 기본 multipage 미사용. `st.sidebar.radio`로 메뉴 선택 → 해당 `page_*()` 함수 호출.

```python
if menu == "📋 메인":      page_main()
elif menu == "📜 발송 이력": page_history()
elif menu == "⚙️ 설정":    page_settings()
```

### 메인 페이지 플로우 (step 기반)

`st.session_state["step"]` 값으로 단계 제어. 각 단계는 이전 단계가 완료돼야 렌더링.

```
step=0  →  STEP 1: 텍스트 입력 or 음성 업로드(Whisper STT)
step=2  →  STEP 2: PII 마스킹 (regex, 수정 가능)
step=3  →  STEP 3: 상담 유형 분류 + RAG 검색
step=4  →  STEP 4: 상품 추천(CoT) + AI 문자 초안 생성
step=5  →  STEP 5: 편집 + Solapi SMS 발송
```

단계를 다시 실행할 때 하위 state를 초기화해야 한다:
```python
# STEP 2 → 3 이동 시
st.session_state["consultation_type"] = ""
st.session_state["rag_results"] = []
st.session_state["sms_draft"] = ""
st.session_state["recommended_products"] = []
```

---

## RAG 엔진

### 데이터 로딩 (`get_rag_engine`)

`@st.cache_resource`로 캐싱 — 세션 내 최초 1회만 실행.

각 데이터 소스별 로딩 한도 (속도/메모리 균형):

| 소스 | glob 패턴 | 파일당 한도 | record 구조 |
|------|-----------|------------|-------------|
| 36번 CoT | `*L_1.CoT*.zip` | 120개 JSON | `{type:"product_cot", question, answer, product_names, cot1}` |
| 25번 금융상담 | `*L_*.zip.part0` | 60개 JSON × QA 3건 | `{type:"bank_qa", question, answer, category}` |
| 24번 공공민원 | `*L_*_질의응답.zip` | 25개 JSON × 2건 | `{type:"public_qa", question, answer, category}` |

`*L_` 패턴으로 TL_(Training) + VL_(Validation) 동시 커버.

### 검색 (`search_rag`)

TF-IDF (char n-gram 2~3, max 30,000 features) + cosine similarity.  
OpenAI 임베딩 불필요 → API 키 없어도 RAG 검색 동작.  
최소 유사도 임계값: `0.03` (너무 낮으면 노이즈, 높이면 결과 없음).

### 데이터 스키마

**36번 CoT JSON** (파일 1개 = 레코드 1개):
```json
{
  "cot_id": 15,
  "category": "증권",
  "gender": "여",
  "age": "50대",
  "query_type": "고객특성 강조형",
  "question": "...",
  "cot1": "고객 분석...",
  "cot2": "상품 필터링...",
  "cot3": "최종 추천 근거...",
  "answer": "최종 추천 문구",
  "product_names": ["상품명A", "상품명B"]
}
```

**25번 금융상담 JSON** (파일 1개 = 상담 1건):
```json
{
  "source": { "source_institution": "하나은행", "consulting_content": "TX...\nRX..." },
  "qa_data": [
    {
      "qa_topic": "대출문의",
      "instruction": "...",
      "input": { "question": "...", "answer": "...", "follow_up_question": "..." },
      "output": "정제된 답변"
    }
  ]
}
```

**24번 공공민원 JSON** (파일 1개 = 리스트):
```json
[{
  "source": "국토교통부",
  "consulting_category": "부동산개발정책과",
  "consulting_content": "Q: ...\nA: ...",
  "instructions": [{ "tuning_type": "질의응답", "data": [{ "instruction": "...", "output": "..." }] }]
}]
```

---

## LLM 연동

모델: `gpt-4o-mini` (기본값, `openai_chat()` 호출 시 변경 가능)

### 분류 (`ai_classify`)
- temperature=0, 카테고리 목록에서 정확히 하나 선택
- 실패 시 `classify_keyword()`로 fallback

### 문자 초안 생성 (`ai_generate_draft`)
- 상담 유형 + 마스킹된 상담 내용 + RAG 참조(bank_qa) + 추천 상품(CoT)을 컨텍스트로 사용
- SMS(90자 이하) / LMS(91~300자) 자동 구분

### Whisper STT (`whisper_stt`)
- 모델: `whisper-1`, language=`ko`
- 지원 형식: wav, mp3, m4a

---

## SMS 발송 (Solapi)

REST API 직접 호출 (SDK 미사용).  
인증: HMAC-SHA256 (`date_str + salt` 서명).

```python
sig = hmac.new(api_secret.encode(), (date_str + salt).encode(), hashlib.sha256).hexdigest()
```

엔드포인트: `POST https://api.solapi.com/messages/v4/send`

성공 판별: 응답에 `"groupId"` 키 존재 또는 `statusCode == "2000"`.

---

## 세션 상태 키 목록

| 키 | 타입 | 설명 |
|----|------|------|
| `openai_api_key` | str | OpenAI API 키 |
| `solapi_api_key` | str | Solapi API Key |
| `solapi_api_secret` | str | Solapi API Secret |
| `solapi_from_number` | str | SMS 발신 번호 |
| `transcript` | str | 원본 상담 텍스트 (STT 결과 또는 직접 입력) |
| `masked_transcript` | str | PII 마스킹 후 텍스트 |
| `consultation_type` | str | 분류 결과 (예금/적금, 대출, 카드 등) |
| `rag_results` | list | RAG 검색 결과 (score, type, question, answer 포함) |
| `recommended_products` | list | CoT에서 추출한 추천 상품 (product_names 있는 것만) |
| `sms_draft` | str | AI 생성 문자 초안 (편집 가능) |
| `step` | int | 현재 진행 단계 (0~5) |

---

## 상담 유형 분류 카테고리

```python
CATEGORIES = {
    "예금/적금": [...],
    "대출":      [...],
    "카드":      [...],
    "전자금융":  [...],
    "투자/펀드": [...],
    "보험":      [...],
    "외환":      [...],
}
```

키워드 기반(`classify_keyword`) 또는 GPT 기반(`ai_classify`) 둘 다 이 딕셔너리 기준.

---

## 영구 저장소 (.cache/)

JSON 파일 기반 (DB 미사용).

| 파일 | 내용 | 수정 함수 |
|------|------|-----------|
| `history.json` | 발송 이력 리스트 | `save_json(HISTORY_FILE, ...)` |
| `links.json` | 안내 링크 `[{name, url}]` | ⚙️ 설정 > 링크 관리 |
| `templates.json` | 문자 템플릿 `[{name, content}]` | ⚙️ 설정 > 템플릿 관리 |

---

## 주의 사항

- `.env` 파일은 절대 git에 커밋하지 말 것 (API 키 포함)
- RAG 인덱스는 세션마다 재빌드됨 (디스크 캐시 없음). 앱 재시작 시 수십 초 소요될 수 있음
- 25번 데이터는 `.zip.part0` 확장자지만 단독 완결 zip 파일로 동작함
- SMS 300자 초과 시 발송 불가 (앱에서 경고 표시)
- `get_rag_engine()`은 인수 없는 `@st.cache_resource`이므로 동일 세션 내 항상 같은 객체 반환
