"""
Call2Text — RAG 파이프라인 독립 실행 및 평가 스크립트
기억해조 5조 | 신한은행 AI 해커톤

사용법:
    python rag_pipeline_eval.py                     # 전체 평가 실행
    python rag_pipeline_eval.py --query "대출 한도"  # 단일 쿼리 검색
    python rag_pipeline_eval.py --eval              # 평가 지표만 출력
"""

import argparse
import glob
import json
import zipfile
from pathlib import Path
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ─────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).parent
THRESHOLD    = 0.03      # 유사도 하한선
TOP_K        = 4         # 기본 검색 결과 수
MAX_FILES    = 60        # zip당 최대 JSON 파일 수
MAX_QA       = 3         # 파일당 최대 QA 추출 수
TFIDF_PARAMS = dict(
    analyzer="char_wb",
    ngram_range=(2, 3),
    max_features=30_000,
)

# 평가용 쿼리 세트 (상담 유형별 10개)
EVAL_QUERIES = [
    {"query": "정기예금 금리가 얼마나 되나요? 6개월 만기로 가입하고 싶어요",
     "expected_category": "예금/적금"},
    {"query": "적금 해지하면 이자 어떻게 되나요",
     "expected_category": "예금/적금"},
    {"query": "주택담보대출 한도 조회 하려고 합니다",
     "expected_category": "대출"},
    {"query": "신용대출 이자율 알고 싶어요. 최저 금리는 얼마예요",
     "expected_category": "대출"},
    {"query": "신용카드 포인트 사용 방법 알려주세요",
     "expected_category": "카드"},
    {"query": "체크카드 분실 신고 어떻게 하나요",
     "expected_category": "카드"},
    {"query": "인터넷뱅킹 이체 한도 높이는 방법",
     "expected_category": "전자금융"},
    {"query": "펀드 가입하고 싶은데 IRP 세액공제 얼마나 되나요",
     "expected_category": "투자/펀드"},
    {"query": "달러 환전 수수료 우대 받을 수 있나요",
     "expected_category": "외환"},
    {"query": "암보험 보험금 청구 절차 알려주세요",
     "expected_category": "보험"},
]


# ─────────────────────────────────────────────────────────────
# 데이터 로딩
# ─────────────────────────────────────────────────────────────

def load_corpus() -> list[dict]:
    """25번 금융상담 데이터에서 RAG 코퍼스 구축"""
    corpus = []
    pat = str(BASE_DIR / "25.금융분야_고객상담_데이터" / "**" /
              "02.라벨링데이터" / "*L_*.zip.part0")
    zip_files = glob.glob(pat, recursive=True)

    if not zip_files:
        print("[WARNING] 25번 데이터 파일 없음. 빈 코퍼스로 실행됩니다.")
        return corpus

    print(f"[INFO] 발견된 zip 파일: {len(zip_files)}개")

    for zp in zip_files:
        try:
            with zipfile.ZipFile(zp) as zf:
                jfiles = [f for f in zf.namelist() if f.endswith(".json")]
                loaded = 0
                for fname in jfiles[:MAX_FILES]:
                    try:
                        d = json.loads(zf.read(fname).decode("utf-8"))
                        if not isinstance(d, dict) or "qa_data" not in d:
                            continue
                        content = d.get("source", {}).get("consulting_content", "")[:300]
                        for qa in d["qa_data"][:MAX_QA]:
                            q = qa.get("input", {}).get("question", "")
                            a = qa.get("output", "")
                            if q and a:
                                corpus.append({
                                    "type": "bank_qa",
                                    "category": qa.get("qa_topic", ""),
                                    "question": q,
                                    "answer": a,
                                    "text": content + " " + q,
                                })
                                loaded += 1
                    except Exception:
                        continue
                print(f"  {Path(zp).name}: {loaded}건 로딩")
        except Exception as e:
            print(f"  [ERROR] {Path(zp).name}: {e}")

    return corpus


# ─────────────────────────────────────────────────────────────
# 인덱스 빌드
# ─────────────────────────────────────────────────────────────

def build_index(corpus: list[dict]):
    """TF-IDF 인덱스 빌드 및 결과 반환"""
    if not corpus:
        return None, None

    texts = [c["text"] for c in corpus]
    vectorizer = TfidfVectorizer(**TFIDF_PARAMS)
    matrix = vectorizer.fit_transform(texts)

    print(f"[INFO] 인덱스 빌드 완료 — 코퍼스: {len(corpus):,}건, "
          f"어휘: {len(vectorizer.vocabulary_):,}개")
    return vectorizer, matrix


# ─────────────────────────────────────────────────────────────
# 검색
# ─────────────────────────────────────────────────────────────

def search(query: str, vectorizer, matrix, corpus: list[dict],
           top_k: int = TOP_K, threshold: float = THRESHOLD) -> list[dict]:
    """쿼리에 대한 유사 상담 검색"""
    qvec = vectorizer.transform([query])
    scores = cosine_similarity(qvec, matrix).flatten()
    idxs = scores.argsort()[-top_k:][::-1]
    return [
        {**corpus[i], "score": float(scores[i])}
        for i in idxs
        if scores[i] > threshold
    ]


# ─────────────────────────────────────────────────────────────
# 평가
# ─────────────────────────────────────────────────────────────

def evaluate(vectorizer, matrix, corpus: list[dict]) -> dict:
    """
    평가 지표:
    - 히트율(Hit Rate): 검색 결과가 1건 이상 반환된 쿼리 비율
    - 평균 top-1 유사도: 각 쿼리의 최고 유사도 평균
    - 카테고리 일치율: top-1 결과의 카테고리가 기대 카테고리와 일치하는 비율
    - 평균 결과 수: 쿼리당 반환되는 결과 평균 수
    """
    if vectorizer is None:
        print("[WARNING] 인덱스 없음 — 평가 불가")
        return {}

    hit_count   = 0
    top1_scores = []
    cat_match   = 0
    result_cnts = []

    cat_counter = Counter(c.get("category", "") for c in corpus)

    print("\n" + "=" * 70)
    print(f"{'쿼리':<35} {'결과수':>5} {'top1':>6} {'카테고리일치':>10}")
    print("=" * 70)

    for item in EVAL_QUERIES:
        q   = item["query"]
        exp = item["expected_category"]

        results = search(q, vectorizer, matrix, corpus, top_k=TOP_K, threshold=THRESHOLD)
        n = len(results)
        result_cnts.append(n)

        if n > 0:
            hit_count += 1
            score = results[0]["score"]
            top1_scores.append(score)
            res_cat = results[0].get("category", "")
            # 카테고리 부분 일치 허용 (예: "대출문의" ⊃ "대출")
            matched = exp in res_cat or res_cat in exp
            if matched:
                cat_match += 1
            mark = "✅" if matched else "❌"
        else:
            top1_scores.append(0.0)
            mark = "—"

        q_trunc = q[:32] + ".." if len(q) > 32 else q
        score_str = f"{top1_scores[-1]:.3f}" if n > 0 else "  N/A"
        print(f"  {q_trunc:<35} {n:>5} {score_str:>6}  {mark}")

    total = len(EVAL_QUERIES)
    metrics = {
        "hit_rate":       hit_count / total,
        "avg_top1_score": float(np.mean(top1_scores)),
        "cat_match_rate": cat_match / hit_count if hit_count > 0 else 0.0,
        "avg_results":    float(np.mean(result_cnts)),
        "corpus_size":    len(corpus),
        "n_queries":      total,
    }

    print("=" * 70)
    print("\n📊 평가 지표 요약")
    print(f"  코퍼스 크기      : {metrics['corpus_size']:,}건")
    print(f"  평가 쿼리 수     : {metrics['n_queries']}개")
    print(f"  히트율           : {metrics['hit_rate']*100:.1f}%  "
          f"({hit_count}/{total})")
    print(f"  평균 top-1 유사도: {metrics['avg_top1_score']:.4f}")
    print(f"  카테고리 일치율  : {metrics['cat_match_rate']*100:.1f}%  "
          f"({cat_match}/{hit_count}건 히트 중)")
    print(f"  쿼리당 평균 결과 : {metrics['avg_results']:.1f}건")

    # 성공 기준 대비 달성 여부
    print("\n🎯 성공 기준 달성 여부")
    checks = [
        ("히트율 ≥ 80%",            metrics["hit_rate"] >= 0.80),
        ("평균 top-1 유사도 ≥ 0.08", metrics["avg_top1_score"] >= 0.08),
        ("카테고리 일치율 ≥ 50%",    metrics["cat_match_rate"] >= 0.50),
    ]
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'}  {label}")

    return metrics


# ─────────────────────────────────────────────────────────────
# 단일 쿼리 데모
# ─────────────────────────────────────────────────────────────

def demo_query(query: str, vectorizer, matrix, corpus: list[dict]) -> None:
    """단일 쿼리에 대한 검색 결과를 출력"""
    print(f'\n🔍 검색 쿼리: "{query}"')
    print("-" * 60)
    results = search(query, vectorizer, matrix, corpus,
                     top_k=TOP_K, threshold=THRESHOLD)

    if not results:
        print("  결과 없음 (유사도 임계값 이하)")
        return

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] 유사도: {r['score']:.4f}  카테고리: {r.get('category','')}")
        print(f"  Q: {r['question'][:120]}")
        print(f"  A: {r['answer'][:180]}")


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Call2Text RAG 파이프라인 평가")
    parser.add_argument("--query", type=str, default=None,
                        help="단일 쿼리 검색 (예: --query '대출 한도')")
    parser.add_argument("--eval", action="store_true",
                        help="평가 지표만 출력")
    parser.add_argument("--top_k", type=int, default=TOP_K,
                        help=f"검색 결과 수 (기본: {TOP_K})")
    parser.add_argument("--threshold", type=float, default=THRESHOLD,
                        help=f"유사도 임계값 (기본: {THRESHOLD})")
    args = parser.parse_args()

    print("=" * 70)
    print("  Call2Text — RAG 파이프라인 평가")
    print("  기억해조 5조 | 신한은행 AI 해커톤")
    print("=" * 70)

    # 코퍼스 로딩
    corpus = load_corpus()
    if not corpus:
        print("\n[INFO] 샘플 데이터로 대체 실행합니다.")
        corpus = [
            {"type": "bank_qa", "category": "예금/적금",
             "question": "정기예금 금리가 얼마나 되나요?",
             "answer": "현재 신한은행 쏠편한 정기예금 기준 연 3.5%입니다. 가입 기간에 따라 다를 수 있습니다.",
             "text": "정기예금 금리 이자 만기 적금"},
            {"type": "bank_qa", "category": "대출문의",
             "question": "주택담보대출 한도는 얼마나 되나요?",
             "answer": "주택담보대출 한도는 담보 가치의 최대 70%(LTV)까지 가능합니다.",
             "text": "주택담보대출 한도 LTV 담보 신청"},
            {"type": "bank_qa", "category": "카드",
             "question": "신용카드 포인트 어떻게 사용하나요?",
             "answer": "신한 쏠 앱에서 포인트 메뉴를 선택 후 현금 전환 또는 결제 시 사용 가능합니다.",
             "text": "신용카드 포인트 사용 방법 적립 혜택"},
        ]

    # 인덱스 빌드
    vectorizer, matrix = build_index(corpus)

    if args.query:
        # 단일 쿼리 모드
        demo_query(args.query, vectorizer, matrix, corpus)
    else:
        # 전체 평가 + 데모
        if vectorizer is not None:
            evaluate(vectorizer, matrix, corpus)
            if not args.eval:
                print("\n\n📌 예시 쿼리 데모")
                for q in EVAL_QUERIES[:3]:
                    demo_query(q["query"], vectorizer, matrix, corpus)


if __name__ == "__main__":
    main()
