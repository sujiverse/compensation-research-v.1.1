# -*- coding: utf-8 -*-
import os, re, json, datetime, io, requests
from pathlib import Path
from typing import Dict, List, Optional
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

DOCS = Path("docs"); DOCS.mkdir(exist_ok=True, parents=True)
PAPERS = DOCS/"papers"; PAPERS.mkdir(exist_ok=True, parents=True)
VAULT = Path("ObsidianVault/Compensation")  # 그래프용(있으면 사용)

API = "https://api.openalex.org/works"
LIMIT = int(os.getenv("LIMIT", "8"))  # 1회 최대 처리 논문 수
QUERY = {
    "search": "compensation muscle weakness biomechanics rehabilitation",
    "per_page": LIMIT,
    "sort": "cited_by_count:desc",
}

UA = {"User-Agent": "compensation-wiki/0.2 (+mailto:you@example.com)"}
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

def get_best_pdf_url(w: Dict) -> Optional[str]:
    loc = w.get("best_oa_location") or w.get("primary_location") or {}
    url = (loc.get("pdf_url") or "").strip()
    if url: return url
    # 다른 OA 후보도 훑기
    for cand in (w.get("locations") or []):
        if cand.get("is_oa") and cand.get("pdf_url"): return cand["pdf_url"]
    return None

def stream_pdf_text(url: str, max_bytes: int = 6_000_000) -> str:
    """PDF를 파일로 저장하지 않고 스트림으로 텍스트만 추출."""
    with requests.get(url, headers=UA, stream=True, timeout=45) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        size = 0
        for chunk in r.iter_content(16384):
            if not chunk: break
            size += len(chunk)
            if size > max_bytes: break  # 너무 큰 PDF는 앞부분만
            buf.write(chunk)
        buf.seek(0)
        out = io.StringIO()
        extract_text_to_fp(buf, outfp=out, laparams=LAParams(), codec=None)
        return out.getvalue()

def restore_abstract(inv_idx: Dict) -> str:
    if not inv_idx: return ""
    # OpenAlex abstract_inverted_index 복원
    idx = []
    for token, poss in inv_idx.items():
        for pos in poss:
            idx.append((pos, token))
    idx.sort()
    return " ".join(tok for _, tok in idx)

def brief_summary(title: str, abstract: str, body: str) -> List[str]:
    """초간단 3줄 요약(추출식)."""
    text = (title + "\n" + abstract + "\n" + body).strip()
    text = re.sub(r"\s+", " ", text)
    sents = re.split(r"(?<=[.!?])\s+", text)
    # 키워드 가중치
    kws = ["compensation","weakness","overactivity","biomechanics","activation","rehabilitation",
           "gait","runner","gluteus","tfl","hamstring","serratus","trapezius","tibialis","peroneal"]
    scored = []
    for i, s in enumerate(sents):
        score = sum(s.lower().count(k) for k in kws) + min(len(s)/80.0, 2.0)
        scored.append((score, i, s.strip()))
    scored.sort(key=lambda x:(-x[0], x[1]))
    return [s for _,_,s in scored[:3]] or [text[:180]]

def paper_slug(title: str, year: Optional[int]) -> str:
    t = re.sub(r"[^a-z0-9\-]+","-", (title or "untitled").lower())
    t = re.sub(r"-+","-", t).strip("-")
    return f"{t}-{year or ''}".strip("-")

def make_md_from_work(w: Dict) -> str:
    title = (w.get("display_name") or "Untitled").strip()
    year = w.get("publication_year")
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    url = f"https://doi.org/{doi}" if doi else (w.get("primary_location") or {}).get("landing_page_url","")

    # 텍스트 확보: 1) PDF → 2) Abstract
    pdf_url = get_best_pdf_url(w)
    body = ""
    if pdf_url:
        try:
            body = stream_pdf_text(pdf_url)
        except Exception:
            body = ""
    if not body:
        body = restore_abstract(w.get("abstract_inverted_index") or "")

    lines = brief_summary(title, restore_abstract(w.get("abstract_inverted_index") or ""), body)
    summary_md = "\n".join(f"- {s}" for s in lines)

    meta = [
        f"# {title}",
        "",
        f"- 연도: {year}",
        f"- 인용수: {w.get('cited_by_count',0)}",
        f"- 링크: {url or 'N/A'}",
        f"- OA PDF: {pdf_url or 'N/A'}",
        "",
        "## 쟁점 요약",
        summary_md or "- (요약 불가)",
        "",
        "## 메모",
        "- ",
    ]
    return "\n".join(meta)

def fetch_openalex() -> List[Dict]:
    r = requests.get(API, params=QUERY, headers=UA, timeout=40)
    r.raise_for_status()
    return r.json().get("results", [])

def ensure_graph_assets():
    # graph.html은 한 번만 두고, graph.json은 summarize_cluster.py에서 갱신
    (DOCS/"graph.html").write_text("""
<!doctype html><meta charset="utf-8"><title>Graph</title>
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
  node.append("circle").attr("r",4).attr("class","c");
  node.append("title").text(d=>d.id);
  sim.on("tick",()=>{ link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
    .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y); node.attr("transform",d=>`translate(${d.x},${d.y})`); });
});
</script>
""", encoding="utf-8")

def write_index(papers_md_files: List[str]):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 보상작용 위키 (심플)",
        f"- 마지막 업데이트: **{now}**",
        "",
        "## 최신 논문",
    ]
    for fn in papers_md_files:
        title = Path(fn).stem
        lines.append(f"- [{title}](papers/{Path(fn).name})")
    lines += ["", "## 노드 그래프", "- 그래프 보기: [graph.html](graph.html)"]
    (DOCS/"index.md").write_text("\n".join(lines), encoding="utf-8")

def scan_vault_graph():
    nodes, edges = {}, []
    if not VAULT.exists(): return {"nodes": [], "links": []}
    md_files = list(VAULT.rglob("*.md"))
    for p in md_files:
        nid = str(p.relative_to(VAULT)).replace("\\","/")
        nodes.setdefault(nid, {"id": nid})
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        for tgt in LINK_RE.findall(txt):
            cand = tgt if tgt.endswith(".md") else tgt + ".md"
            local = p.parent / cand
            target = None
            if local.exists():
                target = str(local.relative_to(VAULT)).replace("\\","/")
            else:
                hits = list(VAULT.rglob(cand))
                if hits:
                    target = str(hits[0].relative_to(VAULT)).replace("\\","/")
            if target:
                nodes.setdefault(target, {"id": target})
                edges.append({"source": nid, "target": target})
    return {"nodes": list(nodes.values()), "links": edges}

def main():
    ensure_graph_assets()
    works = []
    try:
        works = fetch_openalex()
    except Exception as e:
        print("OpenAlex fetch failed:", e)

    created = []
    for w in works:
        title = (w.get("display_name") or "Untitled").strip()
        slug = paper_slug(title, w.get("publication_year"))
        mdpath = PAPERS/f"{slug}.md"
        md = make_md_from_work(w)
        mdpath.write_text(md, encoding="utf-8")
        created.append(mdpath.name)

    write_index(created)
    # 그래프 JSON은 summarize_cluster.py에서 갱신(여기선 Vault 기반만 업데이트 원하면 아래 라인 활성화)
    # (DOCS/"graph.json").write_text(json.dumps(scan_vault_graph(), ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
