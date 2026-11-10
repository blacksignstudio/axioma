"""Render a self-contained, offline reader for the already generated graph.

The reader is a bounded view of source records, not a semantic authority or a
network service. Rendering does not verify the graph's source digests anew.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .cli import InvalidProject, safe


OUTPUT = "assets/graph-explorer.html"


def _validate(graph):
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise InvalidProject("Explorer requires graph nodes and edges")
    identifiers = set()
    for node in graph["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise InvalidProject("Explorer node requires a nonempty ID")
        if node["id"] in identifiers:
            raise InvalidProject("Explorer graph contains duplicate node IDs")
        identifiers.add(node["id"])
    for edge in graph["edges"]:
        if not isinstance(edge, dict) or edge.get("source") not in identifiers or edge.get("target") not in identifiers:
            raise InvalidProject("Explorer graph contains a dangling edge")
        if not isinstance(edge.get("type"), str) or not edge["type"]:
            raise InvalidProject("Explorer edge requires a type")


def render(root):
    """Write the fixed derived HTML path atomically; return its absolute Path.

    Both graph input and output reject linked paths through the shared release
    path guard. No path from graph data is opened, and no network is used.
    """
    root = Path(root).resolve()
    source = safe(root, "graph.json", exists=True)
    target = safe(root, OUTPUT)
    if target.exists() and not target.is_file():
        raise InvalidProject("Explorer output must be a regular file")
    if target.parent.exists() and not target.parent.is_dir():
        raise InvalidProject("Explorer output parent is not a directory")
    try:
        graph = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise InvalidProject("Explorer graph JSON is invalid") from exc
    _validate(graph)
    embedded = json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    for character, replacement in (("&", r"\u0026"), ("<", r"\u003c"), (">", r"\u003e"), ("\u2028", r"\u2028"), ("\u2029", r"\u2029")):
        embedded = embedded.replace(character, replacement)
    html = _TEMPLATE.replace("__GRAPH_JSON__", embedded)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=target.parent,
                                         prefix=".explorer-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(html)
        safe(root, OUTPUT)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target


_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>AXIOMA · Graph explorer</title>
<style>
:root{color-scheme:light;--paper:#f6f3e9;--ink:#183d32;--muted:#5c6f63;--line:#d7ddcf;--green:#356b51;--gold:#a48239;--blue:#52728d}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 Georgia,serif}header,main,footer{max-width:1500px;margin:auto;padding:24px 30px}header{border-bottom:1px solid var(--line)}h1{font-weight:400;letter-spacing:.035em;margin:0 0 8px;font-size:2rem}p{margin:.4em 0}.quiet{color:var(--muted);font-size:.88rem}.workspace{display:grid;grid-template-columns:310px minmax(0,1fr);gap:24px}aside,.panel{border:1px solid var(--line);border-radius:12px;background:#fffdf6;padding:18px}label{display:block;font-size:.85rem;margin:8px 0 4px}input,select,button{font:inherit;color:inherit}input,select{width:100%;background:white;border:1px solid #bbcbbd;border-radius:6px;padding:8px}button{background:#edf2e6;border:1px solid #c9d5c4;border-radius:6px;padding:6px 10px;cursor:pointer}button:hover,button:focus-visible{background:#dce8d6;outline:2px solid var(--green);outline-offset:1px}button:disabled{opacity:.45;cursor:default}#results{list-style:none;padding:0;margin:12px 0;max-height:53vh;overflow:auto}#results button{display:block;text-align:left;width:100%;margin:4px 0;background:transparent}#results .kind{font-size:.72rem;color:var(--muted);display:block}.pager{display:flex;gap:8px;align-items:center;justify-content:space-between}.graph-head{display:flex;align-items:center;justify-content:space-between;gap:12px}h2{font-size:1.2rem;font-weight:400;margin:0}#drawing{display:block;width:100%;height:auto;min-height:330px;background:#fbfcf7;border-radius:8px;margin-top:14px}svg text{font:12px Georgia,serif;fill:var(--ink)}.node{cursor:pointer}.node:focus{outline:none}.node:focus circle{stroke:#8a6725;stroke-width:4}.legend{display:flex;flex-wrap:wrap;gap:6px 15px;font-size:.75rem;margin:12px 0}.swatch{display:inline-block;width:17px;height:3px;vertical-align:middle;margin-right:5px}#detail{margin-top:18px;border-top:1px solid var(--line);padding-top:16px;overflow-wrap:anywhere}#detail h3{font-weight:400;font-size:1.2rem;margin:0 0 6px}a{color:#245e47;text-underline-offset:3px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 Consolas,monospace;background:#eef1e8;padding:12px;border-radius:6px;max-height:380px;overflow:auto}details{margin:10px 0}summary{cursor:pointer;color:var(--green)}.edge-list{padding-left:20px}.edge-list li{margin:8px 0}.error{color:#8c342f}footer{font-size:.85rem;color:var(--muted)}@media(max-width:800px){header,main,footer{padding:18px}.workspace{grid-template-columns:1fr}#results{max-height:240px}#drawing{min-height:260px}}
</style>
</head>
<body>
<header><h1>AXIOMA · Graph explorer</h1><p>A source map for reading, following a thread, and returning to its evidence.</p><p id="totals" class="quiet"></p><p class="quiet">This file works offline. Search covers every file and block; the drawing keeps one readable neighborhood in view. A connection is a reading aid, not an instruction to adopt a system.</p></header>
<main class="workspace">
<aside aria-label="Search and filters">
<label for="search">Search title, ID, path, or concept</label><input id="search" type="search" placeholder="Try AXIS, memory, or a section title" autocomplete="off">
<label for="node-kind">Node type</label><select id="node-kind"><option value="">All node types</option></select>
<label for="edge-kind">Connection type in the drawing</label><select id="edge-kind"><option value="">All connection types</option></select>
<p id="result-count" class="quiet" aria-live="polite"></p><ul id="results"></ul>
<div class="pager"><button id="previous" type="button">Previous</button><span id="page" class="quiet"></span><button id="next" type="button">Next</button></div>
</aside>
<section class="panel" aria-label="Graph and source detail">
<div class="graph-head"><h2 id="view-title">Module overview</h2><button id="overview" type="button">Module overview</button></div>
<p id="view-count" class="quiet" aria-live="polite"></p>
<svg id="drawing" viewBox="0 0 920 620" role="img" aria-label="A bounded, interactive source neighborhood"></svg>
<div id="legend" class="legend" aria-label="Connection legend"></div>
<p class="quiet">Solid green: structure or explicit links. Blue: lexical candidates, supported by a recorded term and location. Gold: editorial interpretations, to be assessed against their rationale and evidence. Arrows point from source to target. The full graph remains in the embedded data.</p>
<section id="detail" aria-live="polite"><p>Select a node to inspect its source and connections.</p></section>
</section>
</main>
<footer>An offline reading map. Source links open repository files; Markdown anchor handling depends on the reader used to open them.<p>Silentium Regit Omnia.</p></footer>
<script id="graph-data" type="application/json">__GRAPH_JSON__</script>
<script>
'use strict';
const graph = JSON.parse(document.getElementById('graph-data').textContent);
const nodes = graph.nodes, edges = graph.edges, byId = new Map(nodes.map(n => [n.id,n]));
const byEdge = new Map(nodes.map(n => [n.id,[]]));
edges.forEach(e => {byEdge.get(e.source).push(e);if(e.target!==e.source)byEdge.get(e.target).push(e);});
const $ = id => document.getElementById(id), NS='http://www.w3.org/2000/svg';
const MAX_NODES=40, MAX_EDGES=100, PAGE_SIZE=60;
let page=0, focusId=null, overviewMode=true, currentMatches=[];
const searchIndex=nodes.map(n=>({node:n,text:[n.title,n.id,n.path,n.concept,n.module].filter(Boolean).join(' ').toLocaleLowerCase('en')}));
const label=n=>String(n.title||n.id), kind=n=>String(n.kind||'file');
const human=s=>String(s).replaceAll('_',' ');
const colour=e=>e.type==='section_reading_candidate'?'#82649a':e.basis==='lexical_candidate'||e.type==='lexical_mention'?'#52728d':e.basis==='editorial_interpretation'||e.basis==='curator_interpretation'||e.type.startsWith('editorial_')?'#a48239':'#54765a';
function el(tag,text,parent){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(parent)parent.appendChild(e);return e;}
function svg(tag,attrs,parent){const e=document.createElementNS(NS,tag);Object.entries(attrs||{}).forEach(([k,v])=>e.setAttribute(k,String(v)));if(parent)parent.appendChild(e);return e;}
function allowedNode(n){return !$('node-kind').value||kind(n)===$('node-kind').value;}
function allowedEdge(e){return !$('edge-kind').value||e.type===$('edge-kind').value;}
function sourceHref(n){
 const path=String(n.path||'');
 if(!path||path.startsWith('/')||path.includes('\\')||path.includes(':')||/[\u0000-\u001f]/.test(path))return null;
 const parts=path.split('/');if(parts.some(p=>!p||p==='.'||p==='..'))return null;
 const anchor=n.source_anchor||n.anchor;
 return '../'+parts.map(encodeURIComponent).join('/')+(anchor?'#'+encodeURIComponent(String(anchor)):'');
}
function options(id,values){values.forEach(v=>{const o=el('option',human(v),$(id));o.value=v;});}
options('node-kind',[...new Set(nodes.map(kind))].sort());options('edge-kind',[...new Set(edges.map(e=>e.type))].sort());
$('totals').textContent=nodes.length.toLocaleString('en')+' nodes · '+edges.length.toLocaleString('en')+' connections · '+nodes.filter(n=>n.kind==='block').length.toLocaleString('en')+' source blocks';
function results(reset=true){
 if(reset)page=0;const query=$('search').value.trim().toLocaleLowerCase('en');
 currentMatches=searchIndex.filter(x=>allowedNode(x.node)&&(!query||x.text.includes(query))).map(x=>x.node);
 const pages=Math.max(1,Math.ceil(currentMatches.length/PAGE_SIZE));page=Math.min(page,pages-1);
 $('results').replaceChildren();currentMatches.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE).forEach(n=>{
  const li=el('li',undefined,$('results')),button=el('button',label(n),li);button.type='button';
  el('span',kind(n)+' · '+(n.path||n.id),button).className='kind';button.addEventListener('click',()=>select(n.id));
 });
 $('result-count').textContent=currentMatches.length.toLocaleString('en')+' matching nodes (all records searched)';
 $('page').textContent=(page+1)+' / '+pages;$('previous').disabled=page===0;$('next').disabled=page===pages-1;
}
function relationText(e){
 let status=e.type==='section_reading_candidate'?'Derived motif candidate · unreviewed':e.type==='curated_section_reading'?'Curator-reviewed reading · interpretation':e.basis==='lexical_candidate'||e.type==='lexical_mention'?'Lexical candidate':e.basis==='editorial_interpretation'||e.type.startsWith('editorial_')?'Editorial interpretation':'Recorded structure / explicit link';
 return status+' · '+human(e.type)+(e.relation?' · '+e.relation:'')+(e.status?' · status: '+e.status:'');
}
function inspect(id){
 const n=byId.get(id),box=$('detail');box.replaceChildren();el('h3',label(n),box);el('p',kind(n)+' · '+n.id,box).className='quiet';
 const href=sourceHref(n);if(href){const a=el('a','Open source: '+n.path+(n.anchor?' #'+n.anchor:''),box);a.setAttribute('href',href);}
 else el('p','No portable local source link is recorded for this node.',box);
 if(n.line_start!==undefined)el('p','Source lines '+n.line_start+'–'+n.line_end+' (inclusive, 1-based)',box);
 if(n.anchor_kind)el('p','Anchor kind: '+n.anchor_kind,box).className='quiet';
 if(n.block_type==='component')el('p','Whole composition: '+n.part_ids.length+' source parts, introduction and closing passages. The source link opens its real introduction heading; the exact full span is recorded above.',box);
 if(n.whole_component_id){const whole=el('button','Inspect the whole composition',box);whole.type='button';whole.addEventListener('click',()=>select(n.whole_component_id));}
 const info=el('details',undefined,box);el('summary','Node record, ranges, evidence and recorded digest',info);el('pre',JSON.stringify(n,null,2),info);
 const incident=byEdge.get(id),details=el('details',undefined,box);el('summary',incident.length+' incident connections · inspect recorded evidence',details);
 const list=el('ol',undefined,details);list.className='edge-list';
 // Bounded DOM; all incident records remain available in this searchable document's data.
 incident.slice(0,160).forEach(e=>{const li=el('li',undefined,list);el('p',relationText(e),li);const other=byId.get(e.source===id?e.target:e.source);const b=el('button',label(other),li);b.type='button';b.addEventListener('click',()=>select(other.id));const d=el('details',undefined,li);el('summary','Evidence and relation record',d);el('pre',JSON.stringify(e,null,2),d);});
 if(incident.length>160)el('p','First 160 connection records shown here; narrow the connection filter for the drawing. The complete records remain in embedded graph data.',details);
}
function paint(viewNodes,viewEdges,centreId,note){
 const drawing=$('drawing');drawing.replaceChildren();const defs=svg('defs',{},drawing),marker=svg('marker',{id:'arrow',viewBox:'0 0 10 10',refX:23,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'},defs);svg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#778b78'},marker);
 const positions=new Map(),others=viewNodes.filter(n=>n.id!==centreId);
 if(centreId)positions.set(centreId,[460,300]);
 others.forEach((n,i)=>{const angle=2*Math.PI*i/Math.max(1,others.length)-Math.PI/2;const radius=others.length>20&&i%2?200:255;positions.set(n.id,[460+radius*Math.cos(angle)*1.42,300+radius*Math.sin(angle)]);});
 if(!centreId&&viewNodes.length===1)positions.set(viewNodes[0].id,[460,300]);
 viewEdges.forEach(e=>{const a=positions.get(e.source),b=positions.get(e.target);if(!a||!b)return;const line=svg('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:colour(e),'stroke-opacity':.52,'stroke-width':e.basis==='editorial_interpretation'?1.8:1,'marker-end':'url(#arrow)'},drawing);svg('title',{},line).textContent=relationText(e);});
 viewNodes.forEach(n=>{const [x,y]=positions.get(n.id),g=svg('g',{class:'node',transform:'translate('+x+' '+y+')',tabindex:0,role:'button','aria-label':label(n)+'; inspect source'},drawing);svg('circle',{r:n.id===centreId?20:n.kind==='module'?14:9,fill:n.id===centreId?'#356b51':n.kind==='block'?'#d8e3d1':'#e9e7cf',stroke:'#356b51','stroke-width':1.5},g);const title=svg('title',{},g);title.textContent=label(n)+'\n'+n.id;const text=svg('text',{y:n.id===centreId?36:26,'text-anchor':'middle'},g);const value=label(n);text.textContent=value.length>27?value.slice(0,25)+'…':value;g.addEventListener('click',()=>select(n.id));g.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select(n.id);}});});
 $('view-count').textContent=viewNodes.length+' nodes · '+viewEdges.length+' connections shown. '+note;
 $('legend').replaceChildren();[...new Set(viewEdges.map(e=>e.type))].sort().forEach(type=>{const item=el('span',undefined,$('legend')),swatch=el('span',undefined,item);swatch.className='swatch';swatch.style.backgroundColor=colour(viewEdges.find(e=>e.type===type));el('span',human(type),item);});
 if(!viewNodes.length){const t=svg('text',{x:460,y:300,'text-anchor':'middle'},drawing);t.textContent='No nodes match this view. Change a filter or search.';}
}
function overview(){
 overviewMode=true;focusId=null;const hubs=nodes.filter(n=>n.kind==='module'&&allowedNode(n)),chosen=hubs.slice(0,MAX_NODES),ids=new Set(chosen.map(n=>n.id));
 const relations=edges.filter(e=>ids.has(e.source)&&ids.has(e.target)&&allowedEdge(e));
 $('view-title').textContent='Module overview';paint(chosen,relations.slice(0,MAX_EDGES),null,'Module hubs: '+chosen.length+' of '+hubs.length+'. Click a hub or search any file or block.');
 const axis=chosen.find(n=>String(n.concept||n.title).toUpperCase()==='AXIS');if(axis)inspect(axis.id);
}
function neighborhood(){
 const n=byId.get(focusId);if(!n)return overview();const incident=byEdge.get(focusId).filter(allowedEdge);
 const rank=e=>e.type==='curated_section_reading'||e.type.startsWith('editorial_')?0:e.type==='local_markdown_link'?1:e.type==='contains_block'||e.type==='component_contains'||e.type==='contains_component'?2:e.type==='section_reading_candidate'?3:e.type==='module_contains'?4:e.type==='project_contains'?9:5;
 const sorted=incident.map((e,i)=>({e,i})).sort((a,b)=>rank(a.e)-rank(b.e)||a.i-b.i);
 const ids=new Set([focusId]);sorted.forEach(({e})=>{const other=e.source===focusId?e.target:e.source;if(ids.size<MAX_NODES&&allowedNode(byId.get(other)))ids.add(other);});
 const links=edges.filter(e=>ids.has(e.source)&&ids.has(e.target)&&allowedEdge(e));
 $('view-title').textContent=label(n);paint([...ids].map(id=>byId.get(id)),links.slice(0,MAX_EDGES),focusId,'Focus retained across type filters. '+incident.length+' eligible incident connections; view capped at '+MAX_NODES+' nodes / '+MAX_EDGES+' connections.');
}
function select(id){focusId=id;overviewMode=false;inspect(id);neighborhood();}
$('search').addEventListener('input',()=>results());$('node-kind').addEventListener('change',()=>{results();overviewMode?overview():neighborhood();});$('edge-kind').addEventListener('change',()=>overviewMode?overview():neighborhood());$('overview').addEventListener('click',overview);$('previous').addEventListener('click',()=>{page--;results(false);});$('next').addEventListener('click',()=>{page++;results(false);});
results();overview();
</script>
</body>
</html>
'''
