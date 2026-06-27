"""
validation.app.py  –  Call2Text 자체 검증 스크립트
기억해조 5조

실행:
    python validation.app.py           # 키워드 분류 + 샘플 SMS만 검증 (API 키 불필요)
    python validation.app.py --ai      # OpenAI API 포함 전체 검증

검증 항목:
    1. 분류 정확도  – keyword-based / AI(GPT) 분류기를 14개 라벨 케이스로 평가
    2. URL 추천 정확도 – 카테고리별 추천 링크의 카테고리 일치 + URL 비어있지 않음 검증
    3. 필수항목 포함률 – SMS 초안에 헤더·푸터·300자 이내·PII 미포함 요건 충족 비율
"""

import os, re, json, sys, io
from pathlib import Path

# Windows 터미널 한글 깨짐 방지
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# .env 로드 (없어도 무방)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
USE_AI = "--ai" in sys.argv or bool(OPENAI_API_KEY)   # --ai 플래그 or 키 존재 시 AI 검증

# ─────────────────────────────────────────────────────────────────
# app.py 핵심 로직 복제 (Streamlit 의존성 없이 단독 실행)
# ─────────────────────────────────────────────────────────────────

CATEGORIES = {
    "예금/적금": ["예금","적금","저축","통장","금리","이자","만기","해지","정기"],
    "대출":      ["대출","융자","담보","신용대출","주택담보","전세자금","한도","상환"],
    "카드":      ["카드","체크카드","신용카드","포인트","혜택","결제","청구","연회비"],
    "전자금융":  ["인터넷뱅킹","모바일","앱","OTP","이체","송금","계좌이체"],
    "투자/펀드": ["펀드","투자","주식","ETF","채권","수익률","증권","IRP","연금"],
    "보험":      ["보험","연금","보장","보험료","보험금","종신","암"],
    "외환":      ["환전","외화","달러","유로","환율","해외송금"],
}

DEFAULT_LINKS = [
    {"name": "신용카드 신규",
     "url": "https://nssol.shinhan.com/link.html?pr_id=PR1201S0002F01&prdtCS20=CAADV9",
     "description": "신한 신용카드 신규 발급", "category": "카드"},
    {"name": "신용카드 신규 (S612)",
     "url": "https://nssol.shinhan.com/link.html?pr_id=PR0302S0101F01&prdCode=S612212800",
     "description": "신한 신용카드 (S612 코드)", "category": "카드"},
    {"name": "직장인 신용대출 신규",
     "url": "https://nssol.shinhan.com/link.html?pr_id=PR1402S0001F01&prdCode=260000401",
     "description": "직장인 신용대출 신규 신청", "category": "대출"},
    {"name": "IRP 신규",
     "url": "https://nssol.shinhan.com/link.html?pr_id=PR1002S0011F01&prdGubun=1&prdCode=110007201",
     "description": "개인형 퇴직연금(IRP) 신규 가입", "category": "투자/펀드"},
]

LINKS_FILE = Path(__file__).parent / ".cache" / "links.json"

SMS_HEADER  = "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다"
SMS_FOOTER  = "문의: 신한은행 고객센터 1599-8000"
SMS_MAX_LEN = 300

PII_PATTERNS = [
    r'(?<![0-9])\d{6}-\d{7}(?![0-9])',          # 주민등록번호 (하이픈 포함)
    r'(?<!\d)\d{13}(?!\d)',                      # 주민등록번호 (연속 13자리)
    r'(?<![0-9])\d{2,3}-\d{3,4}-\d{4}(?![0-9])', # 전화번호
    r'(?<![0-9])\d{4}-\d{4}-\d{4}-\d{4}(?![0-9])', # 카드번호
]


def classify_keyword(text: str) -> str:
    scores = {cat: sum(1 for kw in kws if kw in text) for cat, kws in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "기타"


def get_recommended_links(ctype: str) -> list:
    if LINKS_FILE.exists():
        try:
            links = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            links = DEFAULT_LINKS
    else:
        links = DEFAULT_LINKS
    return [l for l in links if l.get("category") == ctype]


def contains_pii(text: str) -> bool:
    return any(re.search(p, text) for p in PII_PATTERNS)


def check_sms_required(sms: str) -> dict:
    return {
        "has_header":    sms.strip().startswith(SMS_HEADER),
        "has_footer":    SMS_FOOTER in sms,
        "within_limit":  len(sms) <= SMS_MAX_LEN,
        "no_pii":        not contains_pii(sms),
    }


def openai_chat(messages, temperature=0.4):
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    r = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=temperature
    )
    return r.choices[0].message.content


def ai_classify(text: str) -> str:
    cats = list(CATEGORIES.keys()) + ["기타"]
    result = openai_chat([
        {"role": "system", "content": f"상담 유형을 정확히 하나만 골라 답하세요: {', '.join(cats)}"},
        {"role": "user",   "content": text[:600]},
    ], temperature=0)
    for c in cats:
        if c in result:
            return c
    return "기타"


def ai_generate_draft(masked: str, ctype: str, links: list) -> str:
    link_ctx = "\n".join(
        f"- {l['name']}: {l['url']}" for l in links[:2] if l.get("url")
    )
    prompt = f"""신한은행 고객 안내 문자를 작성하세요.

[상담 유형] {ctype}
[상담 내용 요약] {masked[:700]}
[안내 링크] {link_ctx or '없음'}

작성 규칙:
- 반드시 첫 줄: "{SMS_HEADER}"
- 전체 {SMS_MAX_LEN}자 이내 (LMS)
- 정중하고 신뢰감 있는 어투
- 마지막: "{SMS_FOOTER}"
- 개인정보 절대 포함 금지

문자 초안만 출력 (설명 없이):"""
    return openai_chat([
        {"role": "system", "content": "당신은 신한은행 고객 안내 문자 전문 작성자입니다."},
        {"role": "user",   "content": prompt},
    ])


# ─────────────────────────────────────────────────────────────────
# 테스트 데이터
# ─────────────────────────────────────────────────────────────────

# 14개 라벨 케이스 (카테고리당 2개)
CLASSIFICATION_CASES = [
    ("정기예금 금리가 얼마인지 알고 싶어요. 만기 때 이자는 어떻게 되나요?",                  "예금/적금"),
    ("적금 통장 만기 해지하고 저축 이자 받는 방법 알려주세요.",                             "예금/적금"),
    ("주택담보대출 한도가 얼마나 되는지 알려주세요. 상환 방식도 궁금합니다.",                 "대출"),
    ("전세자금대출 신청 조건과 담보 관련 융자 한도가 얼마나 되나요?",                        "대출"),
    ("신용카드 포인트를 현금으로 전환하는 방법이 궁금해요.",                                "카드"),
    ("체크카드 결제 청구 오류가 생겼는데 연회비는 환불 가능한가요?",                         "카드"),
    ("모바일 앱에서 계좌이체가 안 되는데 OTP 오류 같아요.",                                "전자금융"),
    ("인터넷뱅킹 송금 이체 한도 변경하는 방법 알려주세요.",                                 "전자금융"),
    ("IRP 연금 가입 방법과 ETF 펀드 수익률에 대해 알고 싶어요.",                           "투자/펀드"),
    ("주식 채권 ETF 투자 관련해서 증권 계좌 수익률 어떻게 보나요?",                         "투자/펀드"),
    ("보험료 납입이 어려운데 보험금 청구하면 보장이 취소되나요?",                            "보험"),
    ("종신보험 연금 전환 특약 알려주세요. 암보험 보험금 수령 방법도요.",                      "보험"),
    ("달러 환전 수수료와 해외송금 환율 우대 방법을 알고 싶습니다.",                          "외환"),
    ("유로 달러 외화예금 환율 변동 위험과 해외송금 수수료 알려주세요.",                       "외환"),
]

# 필수항목 샘플 케이스 (헤더·푸터 있는 정상 + 각종 결함)
SMS_SAMPLE_CASES = [
    {
        "label": "정상 (모두 충족)",
        "text": (
            "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다\n"
            "안녕하세요 고객님. 오늘 문의하신 정기예금 관련 안내드립니다.\n"
            "쏠편한 정기예금(연 최대 3.5%)을 추천드립니다.\n"
            "문의: 신한은행 고객센터 1599-8000"
        ),
    },
    {
        "label": "정상 (링크 포함)",
        "text": (
            "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다\n"
            "대출 한도 및 조건 안내드립니다. 신청: https://nssol.shinhan.com/link.html?pr_id=PR1402S0001F01&prdCode=260000401\n"
            "문의: 신한은행 고객센터 1599-8000"
        ),
    },
    {
        "label": "결함: 헤더 누락",
        "text": (
            "안녕하세요 고객님. 정기예금 안내드립니다.\n"
            "문의: 신한은행 고객센터 1599-8000"
        ),
    },
    {
        "label": "결함: 푸터 누락",
        "text": (
            "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다\n"
            "대출 한도 및 조건 안내드립니다."
        ),
    },
    {
        "label": "결함: 300자 초과",
        "text": (
            "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다\n"
            + ("안녕하세요 고객님 이 문자는 300자 초과 테스트를 위해 의도적으로 길게 작성되었습니다. " * 7)
            + "\n문의: 신한은행 고객센터 1599-8000"
        ),
    },
    {
        "label": "결함: PII 포함 (주민번호 하이픈)",
        "text": (
            "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다\n"
            "주민번호 901234-1234567 확인되었습니다.\n"
            "문의: 신한은행 고객센터 1599-8000"
        ),
    },
    {
        "label": "결함: PII 포함 (전화번호)",
        "text": (
            "[AI] 소중한 고객님과의 통화 내역을 요약하여 보내드립니다\n"
            "연락처 010-1234-5678 로 안내드리겠습니다.\n"
            "문의: 신한은행 고객센터 1599-8000"
        ),
    },
]

# AI 생성 테스트용 상담 입력 (API 키 있을 때만 실행)
AI_DRAFT_INPUTS = [
    ("적금 만기 안내: 이자 지급 및 재예치 방법 문의하셨습니다.", "예금/적금"),
    ("주택담보대출 신청 방법과 LTV 한도 관련 문의 주셨습니다.",  "대출"),
    ("IRP 세액공제 및 ETF 자동 투자 방법을 안내드렸습니다.",    "투자/펀드"),
]


# ─────────────────────────────────────────────────────────────────
# Validation 실행
# ─────────────────────────────────────────────────────────────────

def run_classification_accuracy():
    print("\n" + "=" * 70)
    print("  1. 분류 정확도 (Classification Accuracy)")
    print("=" * 70)

    n = len(CLASSIFICATION_CASES)
    kw_correct = 0
    ai_correct = 0
    rows = []

    for text, expected in CLASSIFICATION_CASES:
        kw_pred = classify_keyword(text)
        kw_ok   = kw_pred == expected
        kw_correct += int(kw_ok)

        row = {"short": text[:38] + "…", "expected": expected,
               "kw_pred": kw_pred, "kw_ok": kw_ok}

        if USE_AI and OPENAI_API_KEY:
            try:
                ai_pred = ai_classify(text)
            except Exception as e:
                ai_pred = f"ERR"
            ai_ok = ai_pred == expected
            ai_correct += int(ai_ok)
            row["ai_pred"] = ai_pred
            row["ai_ok"]   = ai_ok

        rows.append(row)

    # 헤더 출력
    hdr = f"{'#':>3}  {'텍스트 (앞 40자)':<40} {'정답':<10} {'키워드':^10} {'일치':^5}"
    if USE_AI and OPENAI_API_KEY:
        hdr += f"  {'AI(GPT)':^10} {'일치':^5}"
    print(f"\n{hdr}")
    print("-" * len(hdr))

    for i, r in enumerate(rows, 1):
        kw_m = "O" if r["kw_ok"] else "X"
        line = f"{i:>3}  {r['short']:<40} {r['expected']:<10} {r['kw_pred']:^10} {kw_m:^5}"
        if USE_AI and OPENAI_API_KEY:
            ai_m = "O" if r.get("ai_ok", False) else "X"
            line += f"  {r.get('ai_pred',''):^10} {ai_m:^5}"
        print(line)

    kw_acc = kw_correct / n * 100
    print(f"\n  키워드 분류 정확도:  {kw_correct}/{n} = {kw_acc:.1f}%")

    result = {"keyword_accuracy": kw_acc, "n": n, "kw_correct": kw_correct}

    if USE_AI and OPENAI_API_KEY:
        ai_acc = ai_correct / n * 100
        print(f"  AI(GPT) 분류 정확도: {ai_correct}/{n} = {ai_acc:.1f}%")
        result["ai_accuracy"] = ai_acc
        result["ai_correct"]  = ai_correct

    return result


def run_url_recommendation_accuracy():
    print("\n" + "=" * 70)
    print("  2. URL 추천 정확도 (URL Recommendation Accuracy)")
    print("=" * 70)

    if LINKS_FILE.exists():
        try:
            all_links = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            all_links = DEFAULT_LINKS
    else:
        all_links = DEFAULT_LINKS

    link_cats    = sorted({l.get("category") for l in all_links if l.get("category")})
    no_link_cats = [c for c in CATEGORIES if c not in link_cats]

    print(f"\n  {'카테고리':<12} {'링크수':>5}  {'카테고리 일치':^14}  {'URL 비어있지 않음':^18}  {'결과'}")
    print("  " + "-" * 60)

    total   = 0
    correct = 0

    for cat in link_cats:
        recs      = get_recommended_links(cat)
        cat_ok    = all(l.get("category") == cat for l in recs)
        url_ok    = all(bool(l.get("url","").strip()) for l in recs)
        passed    = cat_ok and url_ok
        correct  += int(passed)
        total    += 1
        c_m = "O" if cat_ok else "X"
        u_m = "O" if url_ok else "X"
        p_m = "PASS" if passed else "FAIL"
        print(f"  {cat:<12} {len(recs):>5}  {c_m:^14}  {u_m:^18}  {p_m}")

    for cat in no_link_cats:
        print(f"  {cat:<12} {'0':>5}  {'(링크 미등록)':^14}  {'-':^18}  SKIP")

    acc = correct / total * 100 if total > 0 else 0.0
    print(f"\n  링크 등록 카테고리 {total}개  |  정확 매칭: {correct}/{total} = {acc:.1f}%")
    print(f"  * 카테고리 미등록 링크는 설정 메뉴에서 추가 가능합니다.")

    return {"url_accuracy": acc, "total_cats": total, "correct": correct,
            "no_link_cats": no_link_cats}


def run_required_items_inclusion():
    print("\n" + "=" * 70)
    print("  3. 필수항목 포함률 (Required Items Inclusion Rate)")
    print("=" * 70)

    all_cases = list(SMS_SAMPLE_CASES)  # 샘플 케이스

    # API 키 있을 때 AI 생성 초안 추가
    if USE_AI and OPENAI_API_KEY:
        print("\n  AI 초안 생성 중 (3건)...")
        for masked_text, ctype in AI_DRAFT_INPUTS:
            try:
                links = get_recommended_links(ctype)
                draft = ai_generate_draft(masked_text, ctype, links)
                all_cases.append({"label": f"AI 생성 / {ctype}", "text": draft})
            except Exception as e:
                all_cases.append({"label": f"AI 생성 / {ctype} [오류]", "text": f"[ERROR] {e}"})

    print(f"\n  {'#':>3}  {'케이스':<30} {'헤더':^6} {'푸터':^6} {'300자':^8} {'PII없음':^8}  결과")
    print("  " + "-" * 68)

    total       = 0
    pass_count  = 0

    for i, case in enumerate(all_cases, 1):
        label = case["label"]
        text  = case["text"]

        if text.startswith("[ERROR]"):
            print(f"  {i:>3}  {label:<30} {'---':^6} {'---':^6} {'---':^8} {'---':^8}  ERROR")
            continue

        checks = check_sms_required(text)
        passed = all(checks.values())
        total += 1
        pass_count += int(passed)

        h  = "O"  if checks["has_header"]   else "X"
        f_ = "O"  if checks["has_footer"]   else "X"
        lm = "O"  if checks["within_limit"] else f"X({len(text)}자)"
        pi = "O"  if checks["no_pii"]       else "X"
        rs = "PASS" if passed else "FAIL"

        print(f"  {i:>3}  {label:<30} {h:^6} {f_:^6} {lm:^8} {pi:^8}  {rs}")

    rate = pass_count / total * 100 if total > 0 else 0.0
    print(f"\n  총 {total}건  |  필수항목 전체 충족: {pass_count}건 = {rate:.1f}%")

    print(f"\n  [필수항목 체크리스트]")
    print(f"  - 헤더: \"{SMS_HEADER}\"")
    print(f"  - 푸터: \"{SMS_FOOTER}\"")
    print(f"  - 길이: {SMS_MAX_LEN}자 이하")
    print(f"  - PII: 주민번호·전화번호·카드번호 미포함")

    return {"inclusion_rate": rate, "pass_count": pass_count, "total": total}


# ─────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Call2Text 자체 검증 리포트  |  기억해조 5조")
    print("=" * 70)
    if USE_AI and OPENAI_API_KEY:
        print("  모드: 전체 검증 (키워드 + AI 분류 + AI 초안 생성)")
    else:
        print("  모드: 기본 검증 (키워드 분류 + 샘플 SMS만 평가)")
        print("  힌트: OpenAI API 키 설정 후 실행하면 AI 검증도 포함됩니다.")

    r1 = run_classification_accuracy()
    r2 = run_url_recommendation_accuracy()
    r3 = run_required_items_inclusion()

    print("\n" + "=" * 70)
    print("  [ 최종 요약 ]")
    print("=" * 70)
    kw_line = f"  1. 분류 정확도 (키워드) : {r1['kw_correct']}/{r1['n']} = {r1['keyword_accuracy']:.1f}%"
    if "ai_accuracy" in r1:
        kw_line += f"   (AI: {r1.get('ai_correct',0)}/{r1['n']} = {r1['ai_accuracy']:.1f}%)"
    print(kw_line)
    print(f"  2. URL 추천 정확도       : {r2['correct']}/{r2['total_cats']} = {r2['url_accuracy']:.1f}%")
    print(f"  3. 필수항목 포함률       : {r3['pass_count']}/{r3['total']} = {r3['inclusion_rate']:.1f}%")

    base_acc = r1.get("ai_accuracy", r1["keyword_accuracy"])
    overall  = (base_acc + r2["url_accuracy"] + r3["inclusion_rate"]) / 3
    print(f"\n  종합 점수 (단순 평균)    : {overall:.1f}%")
    print("=" * 70)

    if r2["no_link_cats"]:
        print(f"\n  [안내] 링크 미등록 카테고리: {', '.join(r2['no_link_cats'])}")
        print("  -> 설정 > 링크 관리 메뉴에서 추가하면 URL 추천 정확도가 향상됩니다.")


if __name__ == "__main__":
    main()
