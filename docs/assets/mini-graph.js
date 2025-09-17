<script>
(function(){
  // 어느 경로에서든 graph.json 상대경로 계산
  const base = (location.pathname.includes('/papers/') || location.pathname.includes('/clusters/')) ? '../' : '';
  const box = document.createElement('div');
  box.id = 'mini-graph-wrap';
  box.innerHTML = '<div class="title">연결 그래프</div><svg id="mini-graph"></svg><div class="legend">● 클릭으로 이동</div>';
  document.body.appendChild(box);

  const svg = document.getElementById('mini-graph');
  const W = svg.clientWidth || 260, H = svg.clientHeight || 220;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  fetch(base + 'graph.json').then(r=>r.json()).then(({nodes,links})=>{
    // 간단한 force 레이아웃 (D3 없이 mini)
    // 임의 좌표 초기화
    nodes.forEach((n,i)=>{ n.x = Math.random()*W; n.y = Math.random()*H; n.vx=0; n.vy=0; });
    // 80프레임 정도만 간단하게 돌림
    const steps = 80, k = 0.05, charge = -80, linkDist = 55;

    function step(){
      // 링크 스프링
      links.forEach(l=>{
        const a = (typeof l.source==='number')? nodes[l.source]: nodes.find(n=>n.id===l.source);
        const b = (typeof l.target==='number')? nodes[l.target]: nodes.find(n=>n.id===l.target);
        if(!a||!b) return;
        const dx=b.x-a.x, dy=b.y-a.y, d=Math.max(1, Math.hypot(dx,dy));
        const f = k*(d-linkDist);
        const ux=dx/d, uy=dy/d;
        a.vx += f*ux; a.vy += f*uy;
        b.vx -= f*ux; b.vy -= f*uy;
      });
      // 전하(서로 밀기)
      for(let i=0;i<nodes.length;i++){
        for(let j=i+1;j<nodes.length;j++){
          const a=nodes[i], b=nodes[j], dx=b.x-a.x, dy=b.y-a.y, d=Math.max(1, Math.hypot(dx,dy));
          const f = charge/(d*d);
          const ux=dx/d, uy=dy/d;
          a.vx += f*ux; a.vy += f*uy;
          b.vx -= f*ux; b.vy -= f*uy;
        }
      }
      // 위치 업데이트 + 벽 반사
      nodes.forEach(n=>{
        n.x = Math.min(W-10, Math.max(10, n.x + n.vx));
        n.y = Math.min(H-10, Math.max(10, n.y + n.vy));
        n.vx *= 0.85; n.vy *= 0.85;
      });
      draw();
    }

    function draw(){
      // clear
      svg.innerHTML = '';
      // links
      links.slice(0,120).forEach(l=>{
        const a = (typeof l.source==='number')? nodes[l.source]: nodes.find(n=>n.id===l.source);
        const b = (typeof l.target==='number')? nodes[l.target]: nodes.find(n=>n.id===l.target);
        if(!a||!b) return;
        const line = document.createElementNS('http://www.w3.org/2000/svg','line');
        line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
        line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
        line.setAttribute('stroke', '#c9ced6'); line.setAttribute('stroke-width', '0.6');
        svg.appendChild(line);
      });
      // nodes
      nodes.slice(0,180).forEach(n=>{
        const g = document.createElementNS('http://www.w3.org/2000/svg','g');
        const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
        c.setAttribute('cx', n.x); c.setAttribute('cy', n.y); c.setAttribute('r','3.2');
        c.setAttribute('fill', '#3b82f6'); c.style.cursor='pointer';
        c.addEventListener('click', ()=>{
          // 각 노드 id는 papers 파일명(.md)임
          const target = base + 'papers/' + (n.id.endsWith('.md')? n.id : (n.id + '.md'));
          location.href = target;
        });
        c.addEventListener('mouseenter', ()=>{ c.setAttribute('fill','#1f2937'); });
        c.addEventListener('mouseleave', ()=>{ c.setAttribute('fill','#3b82f6'); });
        const title = document.createElementNS('http://www.w3.org/2000/svg','title');
        title.textContent = n.title || n.id;
        g.appendChild(c); g.appendChild(title); svg.appendChild(g);
      });
    }

    let i=0; const timer = setInterval(()=>{ step(); if(++i>80) clearInterval(timer); }, 16);
    draw();
  }).catch(()=>{ /* graph.json 없으면 조용히 패스 */ });
})();
</script>

