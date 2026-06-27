# Call2Text — AI 상담 요약 · 안내 문자 자동화

> 기억해조 5조 | 신한은행 AI 해커톤 | v2.1

금융 상담 통화 내용을 입력받아 PII를 자동 마스킹하고, RAG 기반 유사 상담 검색 및 LLM을 활용해 SMS/LMS 초안을 자동 생성·발송하는 Streamlit 웹 애플리케이션입니다.

---

## 목차

1. [시스템 요구사항](#시스템-요구사항)
2. [설치 방법](#설치-방법)
3. [환경 변수 설정](#환경-변수-설정)
4. [데이터 준비](#데이터-준비)
5. [실행 방법](#실행-방법)
6. [주요 기능](#주요-기능)
7. [산출물 안내](#산출물-안내)
8. [문제 해결](#문제-해결)

---

## 시스템 요구사항

| 항목 | 버전 |
|------|------|
| Python | 3.9 이상 |
| OS | Windows 10/11, macOS 12+, Ubuntu 20.04+ |
| RAM | 4GB 이상 권장 (RAG 인덱스 빌드 시 2~3GB 사용) |

---

## 설치 방법

```bash
# 1. 저장소 클론
git clone https://github.com/Hyeonziii/call2text.git
cd call2text

# 2. 가상환경 생성 (권장)
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt
```

---

## 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 아래 키를 입력합니다.

```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxx
SOLAPI_API_KEY=your_solapi_api_key
SOLAPI_API_SECRET=your_solapi_api_secret
SOLAPI_FROM_NUMBER=0212345678
```

| 변수 | 필수 여부 | 설명 |
|------|-----------|------|
| `OPENAI_API_KEY` | **필수** | GPT-4o-mini 분류·초안 생성, Whisper STT 사용 |
| `SOLAPI_API_KEY` | SMS 발송 시 필수 | Solapi 문자 발송 API Key |
| `SOLAPI_API_SECRET` | SMS 발송 시 필수 | Solapi API Secret |
| `SOLAPI_FROM_NUMBER` | SMS 발송 시 필수 | 발신 번호 (Solapi 사전 등록 필요) |

> OpenAI API 키만 있으면 SMS 발송을 제외한 모든 기능(STT, 분류, RAG, 초안 생성)을 사용할 수 있습니다.

---

## 데이터 준비

RAG 검색과 상품 추천 기능은 아래 공개 데이터셋을 사용합니다. AI Hub에서 다운로드 후 아래 경로에 배치하세요.

```
call2text/
├── 25.금융분야_고객상담_데이터/
│   └── 3.개방데이터/2.데이터(NIA)/
│       ├── Training/02.라벨링데이터/
│       │   ├── TL_은행.zip.part0
│       │   ├── TL_증권.zip.part0
│       │   └── TL_보험.zip.part0
│       └── Validation/02.라벨링데이터/
│           └── VL_*.zip.part0
│
└── 36.금융상품·서비스 및 소비자 특성 데이터/
    └── 3.개방데이터/1.데이터/
        ├── Training/02.라벨링데이터/
        │   ├── TL_1.CoT_1.증권_*.zip
        │   ├── TL_1.CoT_2.보험_*.zip
        │   └── TL_2.소비자.zip
        └── Validation/02.라벨링데이터/
            └── VL_*.zip
```

> **데이터 없이도 실행 가능합니다.** 데이터가 없으면 RAG 검색이 비활성화되고, 신한은행 상품 큐레이션 목록(코드 내 hardcoded)으로 대체됩니다.

---

## 실행 방법

```bash
# 앱 시작
streamlit run app.py
```

브라우저가 자동으로 열리며 `http://localhost:8501`에서 접근 가능합니다.

### 사용 흐름

```
STEP 1  상담 내용 입력 (텍스트 직접 입력 / 음성 파일 업로드 / 직접 녹음)
  ↓
STEP 2  개인정보 자동 마스킹 확인 및 수정
  ↓
STEP 3  상담 유형 자동 분류 + 유사 상담 RAG 검색 결과 확인
  ↓
STEP 4  신한은행 상품 추천 + AI 문자 초안 자동 생성
  ↓
STEP 5  문자 편집 + 링크 삽입 + SMS/LMS 발송
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **STT** | Whisper-1 모델로 음성 → 텍스트 변환 (한국어) |
| **PII 마스킹** | 주민번호·전화번호·계좌번호·이름·주소 등 정규식 자동 마스킹 |
| **상담 분류** | GPT-4o-mini 기반 7개 카테고리 분류 + 키워드 fallback |
| **RAG 검색** | TF-IDF + Cosine Similarity로 유사 금융 상담 검색 |
| **SMS 초안 생성** | LLM + RAG 컨텍스트 기반 300자 이내 초안 자동 생성 |
| **SMS 발송** | Solapi REST API 연동 (HMAC-SHA256 인증) |
| **이력 관리** | 발송 이력 JSON 저장 및 검색·필터링 |

---

## 산출물 안내

| 파일 | 설명 |
|------|------|
| `README.md` | 실행 방법 및 프로젝트 개요 (이 파일) |
| `problem_definition.md` | 문제 정의서 (해결 문제·가설·성공 기준·데이터 한계) |
| `eda_analysis.ipynb` | EDA 및 전처리 분석 노트북 |
| `rag_pipeline_eval.py` | RAG 파이프라인 독립 실행 및 평가 스크립트 |
| `app.py` | 메인 Streamlit 애플리케이션 |

---

## 문제 해결

**Q. RAG 인덱스 빌드가 너무 오래 걸립니다.**  
A. 25번 데이터 zip 파일당 최대 60개 JSON을 로딩합니다. 데이터 파일이 많을수록 초기 로딩 시간이 길어지며, 이후에는 `@st.cache_resource`로 캐싱됩니다.

**Q. `ModuleNotFoundError: No module named 'sklearn'` 오류가 납니다.**  
A. `pip install scikit-learn` 또는 `pip install -r requirements.txt`를 다시 실행하세요.

**Q. SMS 발송 시 인증 오류가 발생합니다.**  
A. Solapi 콘솔에서 발신번호가 사전 등록되어 있는지 확인하세요. `SOLAPI_FROM_NUMBER`는 하이픈 없이 숫자만 입력해도 됩니다.

**Q. OpenAI API 오류가 발생합니다.**  
A. `.env`의 `OPENAI_API_KEY`가 유효한지, 크레딧이 남아있는지 확인하세요. API 키 없이 테스트하려면 상담 유형 수동 선택 후 STEP 3 → STEP 4로 건너뛸 수 있습니다.
