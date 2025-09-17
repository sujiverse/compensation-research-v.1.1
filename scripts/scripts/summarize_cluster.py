# -*- coding: utf-8 -*-
"""
docs/papers/*.md 를 읽어:
- '쟁점 요약' 생성(추출식 3문장)
- TF-IDF 코사인 유사도 기반 '관련 논문' 상위 5편 링크
- KMeans 클러스터 페이지 생성(docs/clusters/*.md)
요구: pip install scikit-learn nltk
"""
import re, collections
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
    items = []
    if not PAPERS_DIR.exists(): return items
    for p in sorted(PAPERS_DIR.glob("*.md")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        title = (txt.splitlines()[0].strip("# ").strip()
                 if txt.strip() else p.stem.replace("-", " "))
        body = "\n".join(txt.splitlines()[1:]).strip()
        items.append({"path": p, "id": p.name, "title": title, "text": body})
    return items

def extractive_summary(text: str, k: int = 3) -> str:
    if not text: return "데이터 부족으로 요약 불가."
    sents = [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]
    if not sents: return (text[:200] + "…") if len(text) > 200 else text
    keywords = ["compensation","weakness","overactivity","biomechanics",
                "rehabilitation","activation","dysfunction","gait",
                "gluteus","tfl","hamstring","serratus","trapezius",
                "tibialis","peroneal","valgus","runner"]
    scored = []
    for i, s in enumerate(sents):
        key = sum(s.lower().count(kw) for kw in keywords)
        len_score = min(len(s)/80.0, 2.0)  # 너무 짧/김 보정
        scored.append((key + len_score, i, s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return " ".join(s for _,_,s in scored[:k])

def ensure_section(md: str, header: str, content_md: str) -> str:
    """문서에 ## header 섹션을 갱신/삽입"""
    pat = re.compile(rf"(^|\n)##\s+{re.escape(header)}\s*\n", re.IGNORECASE)
    if not pat.search(md):
        if not md.endswith("\n"): md += "\n"
        return md + f"\n## {header}\n{content_md.strip()}\n"
    # 기존 섹션 덮어쓰기
    parts = re.split(rf"(\n##\s+{re.escape(header)}\s*\n)", md, flags=re.IGNORECASE)
    head, marker, tail = parts[0], parts[1], "".join(parts[2:])
    nxt = re.search(r"\n##\s+", tail)
    new_tail = ("\n" + content_md.strip() + "\n" + tail[nxt.start():]) if nxt else ("\n" + content_md.strip() + "\n")
    return head + marker + new_tail

def tfidf_matrix(items: List[Dict]):
    texts = [ (it["title"] + "\n" + it["text"]).lower() for it in items ]
    vec = TfidfVectorizer(max_df=0.9, min_df=1, ngram_range=(1,2))
    X = vec.fit_transform(texts)
    return vec, X

def related_map(X, items: List[Dict], topk=5):
    sim = cosine_similarity(X)
    rel = {}
    n = len(items)
    for i in range(n):
        order = sorted(((sim[i,j], j) for j in range(n) if j!=i), reverse=True)
        rel[items[i]["id"]] = [items[j]["id"] for _, j in order[:topk]]
    return rel

def auto_k(n: int) -> int:
    return max(2, min(10, n//5 or 2))

def write_clusters(vec, X, items: List[Dict]):
    if len(items) < 3: return
    k = auto_k(len(items))
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)
    groups = collections.defaultdict(list)
    for it, lab in zip(items, labels): groups[int(lab)].append(it)

    # 키워드 레이블
    import numpy as np
    terms = vec.get_feature_names_out()
    label_terms = {}
    for lab in sorted(groups.keys()):
        idx = [i for i,(it,l) in enumerate(zip(items, labels)) if l==lab]
        centroid = X[idx].mean(axis=0).A1
        tops = centroid.argsort()[::-1][:6]
        label_terms[lab] = ", ".join(terms[t] for t in tops)

    # 인덱스
    lines = ["# 논문 클러스터", ""]
    for lab in sorted(groups.keys()):
        lines.append(f"- [{label_terms[lab]}](cluster-{lab}.md) ({len(groups[lab])})")
    (CLUSTERS_DIR/"index.md").write_text("\n".join(lines), encoding="utf-8")

    # 각 클러스터 페이지
    for lab in sorted(groups.keys()):
        page = [f"# Cluster {lab}", f"**키워드:** {label_terms[lab]}", ""]
        for it in groups[lab]:
            page.append(f"- **{it['title']}** → [파일](../papers/{it['id']})")
        (CLUSTERS_DIR/f"cluster-{lab}.md").write_text("\n".join(page), encoding="utf-8")

def main():
    items = read_papers()
    if not items:
        print("No papers in docs/papers/*.md")
        return

    # 요약
    for it in items:
        it["summary"] = extractive_summary(it["text"], 3)

    # 벡터화/유사도/클러스터
    vec, X = tfidf_matrix(items)
    rel = related_map(X, items, topk=5)
    write_clusters(vec, X, items)

    # 각 논문 md 갱신: 쟁점 요약 + 관련 논문
    for it in items:
        md = it["path"].read_text(encoding="utf-8", errors="ignore")
        md = ensure_section(md, "쟁점 요약", "- " + it["summary"])
        links = rel.get(it["id"], [])
        if links:
            md = ensure_section(md, "관련 논문",
                                "\n".join(f"- [{rid.replace('.md','')}](./{rid})" for rid in links))
        it["path"].write_text(md, encoding="utf-8")

    # 루트 index에 클러스터 링크 보장
    idx = ROOT/"index.md"
    if idx.exists():
        t = idx.read_text(encoding="utf-8", errors="ignore")
        if "clusters/index.md" not in t:
            t += "\n\n## 클러스터\n- [논문 클러스터](clusters/index.md)\n"
        idx.write_text(t, encoding="utf-8")

    print(f"OK: {len(items)} papers processed.")

if __name__ == "__main__":
    main()
