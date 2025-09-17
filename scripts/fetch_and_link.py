# -*- coding: utf-8 -*-
"""
매분 실행:
1) OpenAlex에서 OA(무료 전문) 논문 N편 스트리밍 수집 (PDF 저장 X)
2) 3줄 쟁점 요약 생성(추출식)
3) TF-IDF 유사도 → 관련 논문 링크(상위 5)
4) 간단 KMeans 클러스터 페이지 생성
5) /docs/index.md 갱신 + /docs/graph.json & graph.html 생성
"""
import os, re, io, json, datetime, requests
from pathlib import Path
from typing import Dict, List, Optional
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans

# ----------------- 설정 -----------------
DOCS = Path("docs"); DOCS.mkdir(parents=True, exist_ok=True)
PAPERS = DOCS/"papers"; PAPERS.mkdir(parents=True, exist_ok=True)
CLUST  = DOCS/"clusters"; CLUST.mkdir(parents=True, exist_ok=True)

BATCH = int(os.getenv("BATCH", "3"))               # 1회 수집 수
QUERY = os.getenv("QUERY", "compensation biomechanics")
API   = "https://api.openalex.org/works"
UA    = {"User-Agent":"compensation-wiki/0.3 (+contact@example.com)"}

# ----------------- 유틸 -----------------
def slugify(s: str) -> str:
    s = (s or "untitled").lower()
    s = re.sub(r"[^a-z0-9\-]+","-", s)
    s = re.sub(r"-+","-", s).strip("-")
    return s or "untitled"

def openalex_search(q: str, n: int) -> List[Dict]:
    params = {"search": q, "per_page": max(1, min(25, n*4)), "sort":"cited_by_count:desc"}
    r = requests.get(API, params=params, headers=UA, timeout=40); r.raise_for_status()
    return r.json().get("results", [])

def best_pdf_url(w: Dict) -> Optional[str]:
    for key in ("best_oa_location","primary_location"):
        loc = w.get(key) or {}
        if loc.get("pdf_url"): return loc["pdf_url"]
    for loc in (w.get("locations") or []):
        if loc.get("is_oa") and loc.get("pdf_url"): return loc["pdf_url"]
    return None

def stream_pdf_text(url: str, max_bytes=6_000_000) -> str:
    with requests.get(url, headers=UA, stream=True, timeout=45) as r:
        r.raise_for_status()
        buf, size = io.BytesIO(), 0
        for ch in r.iter_content(16384):
            if not ch: break
            size += len(ch)
            if size > max_bytes: break
            buf.write(ch)
        buf.seek(0); out = io.StringIO()
        extract_text_to_fp(buf, outfp=out, laparams=LAParams(), codec=None)
        return out.getvalue()

def restore_abs(inv):
    if not inv: return ""
    pairs = []
    for tok, pos in inv.items():
        for p in pos: pairs.append((p, tok))
    pairs.sort()
    return " ".join(t for _,t in pairs)

def summarize(title: str, abstract: str, body: str, k=3) -> List[str]:
    text = " ".join([title or "", abstract or "", body or ""])
    text = re.sub(r"\s+"," ", text).strip()
    sents = re.split(r"(?<=[.!?])\s+", text)
    kws = ["compensation","weakness","overactivity","biomechanics","activation","rehabilitation",
           "gait","runner","gluteus","tfl","hamstring","serratus","trapezius","tibialis","peroneal"]
    scored = []
    for i,s in enumerate(sents):
        score = sum(s.lower().count(k) for k in kws) + min(len(s)/80.0, 2.0)
        scored.append((score, i, s.strip()))
    scored.sort(key=lambda x:(-x[0], x[1]))
    top = [s for _,_,s in scored[:k]] or [text[:180]]
    return top

def write_graph_html_once():
    p = DOCS/"graph.html"
    if p.exists(): return
    p.write_text("""<!doctype html><meta charset="utf-8"><title>Graph</title>
<style>body{font:14px/1.4 system-ui,sans-serif;margin:0}#g{width:100vw;height:100vh}.n{stroke:#999;stroke-width:.5}.c{fill:#444}
a{position:fixed;left:12px;top:10px;text-decoration:none}</style>
<a href="index.html">← back</a><svg id="g"></svg>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script>
fetch("graph.json").then(r=>r.json()).then(({nodes,links})=>{
  const svg=d3.select("#g"), W=innerWidth, H=innerHeight; svg.attr("width",W).attr("height",H);
  const sim=d3.forceSimulation(nodes).force("link", d3.forceLink(links).id(d=>d.id).distance(60))
    .force("charge", d3.forceManyBody().strength(-120)).force("center", d3.forceCenter(W/2,H/2));
  const link=svg.append("g").selectAll("line").data(links).enter().append("line").attr("class","n");
  const node=svg.append("g").selectAll("g").data(nodes).enter().append("g").call(d3.drag()
    .on("start",(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;})
    .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y;})
    .on("end",(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));
  node.append("circle").attr("r",4).attr("class","c"); node.append("title").text(d=>d.title||d.id);
  sim.on("tick",()=>{ link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
    .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y); node.attr("transform",d=>`translate(${d.x},${d.y})`); });
});
</script>""", encoding="utf-8")

# ----------------- 메인 파이프라인 -----------------
def main():
    write_graph_html_once()

    works = openalex_search(QUERY, BATCH)
    picked = []
    for w in works:
        if len(picked) >= BATCH: break
        pdf = best_pdf_url(w)
        if not pdf: continue
        title = (w.get("display_name") or "Untitled").strip()
        year  = w.get("publication_year")
        doi   = (w.get("doi") or "").replace("https://doi.org/","")
        url   = f"https://doi.org/{doi}" if doi else (w.get("primary_location") or {}).get("landing_page_url","")

        # 텍스트 확보(가능하면 PDF, 아니면 초록)
        body = ""
        try:
            body = stream_pdf_text(pdf)
        except Exception:
            body = ""
        if not body:
            body = restore_abs(w.get("abstract_inverted_index"))

        lines = summarize(title, restore_abs(w.get("abstract_inverted_index")), body, k=3)
        md = [
            f"# {title}",
            "",
            f"- 연도: {year}  ·  인용수: {w.get('cited_by_count',0)}",
            f"- 링크: {url or 'N/A'}",
            f"- OA PDF: {pdf or 'N/A'}",
            "",
            "## 쟁점 요약",
            *[f"- {s}" for s in lines],
            "",
        ]
        fn = f"{slugify(title)}-{year or ''}.md".strip("-")
        (PAPERS/fn).write_text("\n".join(md), encoding="utf-8")
        picked.append({"id": fn, "title": title})

    # ----- 유사도 기반 링크 & 클러스터 -----
    paper_files = sorted(PAPERS.glob("*.md"))
    if paper_files:
        texts, titles, ids = [], [], []
        for p in paper_files:
            t = p.read_text(encoding="utf-8", errors="ignore")
            titles.append(t.splitlines()[0].strip("# ").strip() or p.stem)
            ids.append(p.name)
            texts.append(t.lower())

        vec = TfidfVectorizer(max_df=0.9, min_df=1, ngram_range=(1,2))
        X = vec.fit_transform(texts)
        sim = cosine_similarity(X)

        # 각 문서 상위 5개 링크 섹션 갱신
        for i, p in enumerate(paper_files):
            order = sorted(((sim[i,j], j) for j in range(len(paper_files)) if j!=i), reverse=True)[:5]
            related = [f"- [{titles[j]}](./{ids[j]})" for _, j in order]
            md = p.read_text(encoding="utf-8", errors="ignore")
            md = re.sub(r"(?s)\n## 관련 논문\n.*?(?=\n## |\Z)", "", md)  # 기존 섹션 제거
            if not md.endswith("\n"): md += "\n"
            md += "\n## 관련 논문\n" + "\n".join(related) + "\n"
            p.write_text(md, encoding="utf-8")

        # 간단 클러스터 페이지
        k = max(2, min(10, len(paper_files)//5 or 2))
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        labels = km.labels_
        CLUST.mkdir(exist_ok=True, parents=True)
        idx = ["# 논문 클러스터", ""]
        for lab in sorted(set(labels)):
            members = [i for i,l in enumerate(labels) if l==lab]
            page = [f"# Cluster {lab}", ""]
            for i in members:
                page.append(f"- [{titles[i]}](../papers/{ids[i]})")
            (CLUST/f"cluster-{lab}.md").write_text("\n".join(page), encoding="utf-8")
            idx.append(f"- [Cluster {lab}](cluster-{lab}.md) ({len(members)})")
        (CLUST/"index.md").write_text("\n".join(idx), encoding="utf-8")

        # 그래프 데이터(문서간 링크)
        nodes = [{"id": ids[i], "title": titles[i]} for i in range(len(ids))]
        links = []
        for i in range(len(ids)):
            order = sorted(((sim[i,j], j) for j in range(len(ids)) if j!=i), reverse=True)[:5]
            for _, j in order:
                links.append({"source": ids[i], "target": ids[j]})
        (DOCS/"graph.json").write_text(json.dumps({"nodes":nodes,"links":links}, ensure_ascii=False), encoding="utf-8")

    # ----- index 갱신 -----
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 보상작용 위키 (심플)",
        f"- 마지막 업데이트: **{now}**",
        "",
        "## 최신 논문",
    ]
    for p in sorted(PAPERS.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        lines.append(f"- [{p.stem}](papers/{p.name})")
    lines += ["", "## 노드 그래프", "- 그래프 보기: [graph.html](graph.html)", "", "## 클러스터", "- [논문 클러스터](clusters/index.md)"]
    (DOCS/"index.md").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
