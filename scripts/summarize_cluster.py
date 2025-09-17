# -*- coding: utf-8 -*-
"""
docs/papers/*.md 를 읽어:
- '쟁점 요약' 자동 생성(간단 추출식)
- TF-IDF 코사인 유사도로 '관련 논문' 연결
- KMeans로 비슷한 논문 클러스터 페이지 생성 (docs/clusters/*.md)
요구: pip install scikit-learn nltk
"""
import os, re, json, math, pathlib, collections
from pathlib import Path
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path("docs")
PAPERS_DIR = ROOT / "papers"
CLUSTERS_DIR = ROOT / "clusters"
CLUSTERS_DIR.mkdir(parents=True, exist_ok=True)

SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|[\n]+")

def read_papers() -> List[Dict]:
    """docs/papers/*.md에서 제목/본문을 수집"""
    items = []
    if not PAPERS_DIR.exists():
        return items
    for p in sorted(PAPERS_DIR.glob("*.md")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        title = txt.splitlines()[0].strip("# ").strip() if txt.strip() else p.stem
        body = "\n".join(txt.splitlines()[1:]).strip()
        items.append({"path": p, "id": p.name, "title": title, "text": body})
    return items

def extractive_summary(text: str, max_sents: int = 3) -> str:
    """아주 단순한 추출 요약: 길이/키워드로 상위 문장 고르기"""
    if not text: 
        return "데이터 부족으로 요약 불가."
    sents = [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]
    if not sents:
        return (text[:200] + "…") if len(text) > 200 else text
    # 키워드 가중치(도수 기반): compensation/weakness 등
    keywords = ["compensation","weakness","overactivity","biomechanics","rehabilitation",
                "activation","dysfunction","valgus","gait","runner","gluteus","tfl",
                "serratus","trapezius","tibialis","peroneal"]
    scores = []
    for i, s in enumerate(sents):
        base = len(s) / 80.0  # 너무 짧거나 긴 문장 페널티 완화
        key = sum(s.lower().count(k) for k in keywords)
        scores.append((key + base, i, s))
    scores.sort(key=lambda x: (-x[0], x[1]))
    picked = [s for _, _, s in scores[:max_sents]]
    return " ".join(picked)

def ensure_section(md: str, header: str, content: str) -> str:
    """md 문서에 '## header' 섹션을 갱신/삽입"""
    pat = re.compile(rf"\n##\s+{re.escape(header)}\s*\n", re.IGNORECASE)
    if pat.search(md):
        # 기존 섹션을 header 다음 섹션 시작 전까지 대체
        parts = re.split(rf"(\n##\s+{re.escape(header)}\s*\n)", md, flags=re.IGNORECASE)
        head, marker, tail = parts[0], parts[1], "".join(parts[2:])
        # tail에서 다음 ## 위치 찾기
        m = re.search(r"\n##\s+", tail)
        if m:
            new_tail = "\n" + content.strip() + "\n" + tail[m.start():]
        else:
            new_tail = "\n" + content.strip() + "\n"
        return head + marker + new_tail
    else:
        if not md.endswith("\n"):
            md += "\n"
        return md + f"\n## {header}\n{content.strip()}\n"

def build_similarity(items: List[Dict]) -> Dict[str, List[str]]:
    """TF-IDF → cosine sim → 각 논문당 상위 관련 5편 id 반환"""
    if not items:
        return {}
    docs = [ (it["title"] + "\n" + it["text"]).lower() for it in items ]
    vec = TfidfVectorizer(max_df=0.9, min_df=1, ngram_range=(1,2))
    X = vec.fit_transform(docs)
    sim = cosine_similarity(X)
    related = {}
    for i in range(len(items)):
        order = [ (sim[i,j], j) for j in range(len(items)) if j!=i ]
        order.sort(reverse=True)
        top = [items[j]["id"] for _, j in order[:5]]
        related[items[i]["id"]] = top
    return related

def clusterize(items: List[Dict], X, k: int):
    """KMeans로 문서 클러스터. k 자동 추정: n/5 범위에서 2~10"""
    n = len(items)
    if n < 3:
        return None, None
    if k is None:
        k = max(2, min(10, n // 5 or 2))
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)
    return km, labels

def label_terms(X, vectorizer, labels, topn=6):
    """클러스터 상위 키워드 추출"""
    import numpy as np
    terms = vectorizer.get_feature_names_out()
    labels = np.array(labels)
    res = []
    for lbl in sorted(set(labels)):
        idx = np.where(labels==lbl)[0]
        centroid = X[idx].mean(axis=0)
        arr = centroid.A1
        tops = arr.argsort()[::-1][:topn]
        res.append((lbl, [terms[t] for t in tops]))
    return res

def main():
    items = read_papers()
    if not items:
        print("no papers found in docs/papers/*.md")
        return

    # 요약 생성
    for it in items:
        it["summary"] = extractive_summary(it["text"], max_sents=3)

    # 벡터화 & 유사도/클러스터
    texts = [ (it["title"] + "\n" + it["text"]).lower() for it in items ]
    vec = TfidfVectorizer(max_df=0.9, min_df=1, ngram_range=(1,2))
    X = vec.fit_transform(texts)
    related = build_similarity(items)

    km, labels = clusterize(items, X, k=None)
    # 클러스터 페이지 생성
    clusters_map = collections.defaultdict(list)
    if labels is not None:
        for it, lbl in zip(items, labels):
            clusters_map[int(lbl)].append(it)

        # 클러스터 키워드 라벨
        term_labels = dict(label_terms(X, vec, labels, topn=6))

        # 인덱스
        lines = ["# 논문 클러스터", ""]
        for lbl, group in sorted(clusters_map.items()):
            slug = f"cluster-{lbl}.md"
            title = ", ".join(term_labels.get(lbl, [])) or f"cluster-{lbl}"
            lines.append(f"- [{title}]({slug}) ({len(group)})")
        (CLUSTERS_DIR/"index.md").write_text("\n".join(lines), encoding="utf-8")

        # 각 클러스터 페이지
        for lbl, group in sorted(clusters_map.items()):
            title = ", ".join(term_labels.get(lbl, [])) or f"cluster-{lbl}"
            page = [f"# Cluster {lbl}", f"**키워드:** {title}", ""]
            for it in group:
                page.append(f"- **{it['title']}** → [파일](../papers/{it['id']})")
            (CLUSTERS_DIR/f"cluster-{lbl}.md").write_text("\n".join(page), encoding="utf-8")

    # 각 논문 md 업데이트(쟁점 요약 + 관련 논문)
    for it in items:
        md = it["path"].read_text(encoding="utf-8", errors="ignore")
        md = ensure_section(md, "쟁점 요약", "- " + it["summary"])
        rel = related.get(it["id"], [])
        if rel:
            rel_lines = []
            for rid in rel:
                rel_lines.append(f"- [{rid.replace('.md','')}](./{rid})")
            md = ensure_section(md, "관련 논문", "\n".join(rel_lines))
        it["path"].write_text(md, encoding="utf-8")

    # 루트 인덱스에 클러스터 링크 한 줄 추가/보장
    index = ROOT/"index.md"
    if index.exists():
        txt = index.read_text(encoding="utf-8", errors="ignore")
        if "clusters/index.md" not in txt:
            txt += "\n\n## 클러스터\n- [논문 클러스터](clusters/index.md)\n"
        index.write_text(txt, encoding="utf-8")

    print(f"done: {len(items)} papers, clusters={len(clusters_map)}")
    
if __name__ == "__main__":
    main()
