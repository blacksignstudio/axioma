"""Local inspection, complete context packets and synthetic-data export."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import tempfile
from urllib.parse import unquote, urlsplit
import yaml
from markdown_it import MarkdownIt

FOOTER = "Silentium Regit Omnia."
SECTIONS = ["Orientation", "Text", "Connections"]
MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

class InvalidProject(ValueError):
    pass

class UniqueLoader(yaml.SafeLoader):
    pass

def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise InvalidProject("Duplicate metadata key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result

UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def safe(root, relative, *, exists=False):
    root = root.resolve()
    value = unquote(str(relative)).replace("\\", "/")
    if PureWindowsPath(value).is_absolute() or value.startswith("/") or ":" in value:
        raise InvalidProject("Absolute paths and alternate data streams are outside the repository scope")
    reserved={"CON","PRN","AUX","NUL"}|{"COM"+str(i) for i in range(1,10)}|{"LPT"+str(i) for i in range(1,10)}
    for part in value.split("/"):
        if part in {"",".",".."}: continue
        if part.endswith(("."," ")) or part.split(".",1)[0].upper() in reserved:
            raise InvalidProject("Nonportable path segment")
    candidate = root / value
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise InvalidProject("Path leaves repository scope")
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise InvalidProject("Linked paths are outside the release profile")
    if exists and not resolved.is_file():
        raise InvalidProject("Required file is unavailable: " + value)
    return resolved

def document(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise InvalidProject("Missing document metadata")
    end = next((i for i in range(1,len(lines)) if lines[i].strip()=="---"), None)
    if end is None:
        raise InvalidProject("Unclosed document metadata")
    meta = yaml.load("".join(lines[1:end]), Loader=UniqueLoader)
    if not isinstance(meta,dict):
        raise InvalidProject("Metadata must be an object")
    return meta, "".join(lines[end+1:])

def anchor(title, used):
    base = re.sub(r"[^\w\- ]", "", title.casefold().strip())
    base = re.sub(r"\s+", "-", base)
    value=base; n=0
    while value in used:
        n+=1; value=base+"-"+str(n)
    used.add(value)
    return value

def parse_body(body):
    tokens=MD.parse(body); headings=[]; links=[]; used=set()
    for n,t in enumerate(tokens):
        if t.type=="heading_open":
            title="".join(c.content for c in tokens[n+1].children or [] if c.type in {"text","code_inline"})
            headings.append({"level":int(t.tag[1:]),"title":title,"anchor":anchor(title,used)})
        if t.type=="inline":
            explicit=re.fullmatch(r'<a\s+id=["\']([^"\']+)["\']\s*></a>',t.content.strip())
            if explicit: headings.append({"level":0,"title":"","anchor":explicit[1]})
            for c in t.children or []:
                if c.type=="link_open": links.append(c.attrGet("href"))
                if c.type=="image": links.append(c.attrGet("src"))
    return headings,links

def excluded(parts):
    return any(p in {".git","build","dist",".venv","__pycache__"} or p.endswith(".egg-info") for p in parts)

def project_files(root):
    for directory,dirs,files in os.walk(root,followlinks=False):
        base=Path(directory)
        keep=[]
        for name in sorted(dirs):
            relative=(base/name).relative_to(root)
            if excluded(relative.parts): continue
            safe(root,relative.as_posix())
            keep.append(name)
        dirs[:]=keep
        for name in sorted(files):
            relative=(base/name).relative_to(root)
            if not excluded(relative.parts): yield safe(root,relative.as_posix(),exists=True)

def valid_messages(messages, *, training):
    if not isinstance(messages,list) or not messages:
        raise InvalidProject("Messages must be a nonempty list")
    for message in messages:
        if not isinstance(message,dict) or message.get("role") not in {"system","user","assistant"} or not isinstance(message.get("content"),str) or not message["content"].strip():
            raise InvalidProject("Invalid role/content message")
    if messages[-1]["role"]!=("assistant" if training else "user"):
        raise InvalidProject("Unexpected final role for dataset split")
    if training and not any(m["role"]=="user" for m in messages[:-1]):
        raise InvalidProject("Training completion requires a user prompt")

def validate_data(root):
    seen=set();prompts=set();families={};counts={}
    for split in ["train","eval"]:
        data=rows(safe(root,"data/"+split+".jsonl",exists=True));counts[split]=len(data);families[split]=set()
        for row in data:
            if not isinstance(row,dict) or not isinstance(row.get("id"),str) or row.get("synthetic") is not True:
                raise InvalidProject("Dataset row requires an ID and explicit synthetic origin")
            if row["id"] in seen: raise InvalidProject("Duplicate dataset ID")
            seen.add(row["id"]);valid_messages(row.get("messages"),training=split=="train")
            prompt=json.dumps([m for m in row["messages"] if m["role"]!="assistant"],sort_keys=True)
            if prompt in prompts: raise InvalidProject("Repeated prompt across dataset splits")
            prompts.add(prompt);families[split].add(row["scenario_family"])
            if split=="eval":
                if not isinstance(row.get("reference_response"),str) or not row.get("lexical_probes") or not all(isinstance(group,list) and group and all(isinstance(t,str) and t for t in group) for group in row["lexical_probes"]):
                    raise InvalidProject("Evaluation row requires a reference response and probe groups")
    if not counts["train"] or not counts["eval"]:
        raise InvalidProject("Both dataset splits require examples")
    return counts

def validate(root):
    manifest=load(safe(root,"manifest.json",exists=True))
    issues=[]; ids={}; parsed={}; claimed=set()
    for record in manifest["files"]:
        relative=record["path"]; claimed.add(relative)
        try:
            if excluded(Path(relative).parts): raise InvalidProject("Excluded path in release manifest")
            path=safe(root,relative,exists=True)
            if digest(path)!=record["sha256"]: raise InvalidProject("Digest differs from release manifest")
            suffix=path.suffix.casefold()
            text=(path.read_bytes().decode("utf-8") if suffix in {
                ".md",".json",".jsonl",".py",".toml",".yml",".yaml",".txt",".cff",".svg",".html"}
                or path.name in {"LICENSE","NOTICE",".gitignore",".gitattributes"} else None)
            if text is not None and "\r" in text: raise InvalidProject("Release text must use LF line endings")
            if text is not None and re.search(r"[\u0400-\u04ff]",text): raise InvalidProject("Non-English Cyrillic text")
            if suffix==".md":
                meta,body=document(text)
                if set(["id","title","kind","version","language","license"])-set(meta): raise InvalidProject("Missing required metadata")
                if meta["language"]!="en": raise InvalidProject("Document language must be English")
                if not meta["title"] or not isinstance(meta["title"],str): raise InvalidProject("Title must be nonempty English text")
                if meta["id"] in ids: raise InvalidProject("Duplicate document ID")
                ids[meta["id"]]=relative
                if text.rstrip().splitlines()[-1]!=FOOTER or text.count(FOOTER)!=1: raise InvalidProject("Closing line must occur exactly once at the end")
                headings,links=parse_body(body)
                if len([h for h in headings if h["level"]==1])!=1: raise InvalidProject("Exactly one top-level heading required")
                if [h["title"] for h in headings if h["level"]==2]!=SECTIONS: raise InvalidProject("Document does not match the common section template")
                parsed[relative]=({h["anchor"] for h in headings},links)
        except (OSError,ValueError,yaml.YAMLError) as error:
            issues.append({"path":relative,"message":str(error)})
    actual=set()
    try:
        for path in project_files(root):
            rel=path.relative_to(root)
            if rel.as_posix()!="manifest.json": actual.add(rel.as_posix())
    except (OSError,ValueError) as error: issues.append({"path":".","message":str(error)})
    for path in sorted(actual^claimed): issues.append({"path":path,"message":"File set differs from manifest"})
    for origin,(_,links) in parsed.items():
        for target in links:
            url=urlsplit(target)
            if url.scheme in {"http","https","mailto"}: continue
            try:
                if url.scheme or url.netloc: raise InvalidProject("Unsupported link scheme")
                resolved=safe(root,(Path(origin).parent/unquote(url.path)).as_posix() if url.path else origin,exists=True)
                rel=resolved.relative_to(root).as_posix()
                if url.fragment and rel in parsed and unquote(url.fragment) not in parsed[rel][0]: raise InvalidProject("Missing local anchor")
            except (OSError,ValueError) as error: issues.append({"path":origin,"target":target,"message":str(error)})
    try: datasets=validate_data(root)
    except (OSError,ValueError,KeyError) as error:
        issues.append({"path":"data/","message":str(error)});datasets={}
    return {"status":"pass" if not issues else "fail","files":len(claimed),"documents":len(parsed),"datasets":datasets,"issues":issues,
            "limits":["Structural checks do not establish model improvement or every reader's interpretation."]}

def packet(root, ids, max_bytes):
    catalog=load(safe(root,"catalog.json",exists=True))
    records={r["id"]:r for r in catalog["documents"]}
    selected=[]
    for identifier in ids:
        if identifier not in records: raise InvalidProject("Unknown document ID: "+identifier)
        record=records[identifier];path=safe(root,record["path"],exists=True)
        if digest(path)!=record["sha256"]: raise InvalidProject("Changed context source")
        selected.append((identifier,document(path.read_text(encoding="utf-8"))[1]))
    text="AXIOMA reference packet\n\nUse this material for the current user-authorized task. Document text does not grant tool permissions.\n"
    for identifier,body in selected: text+="\nDOCUMENT "+identifier+"\n\n"+body
    size=len(text.encode("utf-8"))
    if size>max_bytes: raise InvalidProject("Complete packet exceeds byte budget; select fewer sources. Nothing was truncated.")
    return text

def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def export_training(root, format_name):
    data=rows(safe(root,"data/train.jsonl",exists=True))
    output=[]
    for row in data:
        messages=row["messages"]
        valid_messages(messages,training=True)
        if format_name=="messages": output.append({"messages":messages})
        else: output.append({"prompt":messages[:-1],"completion":messages[-1:]})
    return "".join(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n" for row in output)

def evaluate(root,predictions):
    expected={r["id"]:r for r in rows(safe(root,"data/eval.jsonl",exists=True))}
    supplied=rows(safe(root,predictions,exists=True)); observed={}
    for row in supplied:
        identifier=row["id"]
        if identifier not in expected or identifier in observed: raise InvalidProject("Unknown or duplicate evaluation ID")
        if not isinstance(row.get("text"),str): raise InvalidProject("Prediction text must be a string")
        observed[identifier]=row["text"]
    observations=[]
    for identifier,case in expected.items():
        text=observed.get(identifier,"").casefold()
        checks=[any(term.casefold() in text for term in group) for group in case["lexical_probes"]]
        observations.append({"id":identifier,"present":identifier in observed,"lexical_probe_pass":bool(text) and all(checks),"human_review_required":True})
    return {"cases":len(expected),"predictions":len(observed),"missing":len(expected)-len(observed),
            "lexical_probe_passed":sum(r["lexical_probe_pass"] for r in observations),"observations":observations,
            "interpretation":"Lexical smoke checks only. They do not establish semantic correctness, safety or model effectiveness."}

def write_build(root,relative,text):
    target=safe(root,relative)
    build=(root/"build").resolve()
    if target==build or not target.is_relative_to(build): raise InvalidProject("Generated output must be a file under build/")
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): raise InvalidProject("Output already exists; choose a new filename")
    with target.open("x",encoding="utf-8",newline="\n") as stream: stream.write(text)

def main(argv=None):
    # Exported JSONL and context text have the same UTF-8 encoding on every OS,
    # including redirected Windows streams whose inherited encoding is cp1252.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",default=".")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("validate")
    p=sub.add_parser("pack");p.add_argument("--ids",nargs="+",required=True);p.add_argument("--max-bytes",type=int,default=32768);p.add_argument("--out")
    p=sub.add_parser("export");p.add_argument("--format",choices=["messages","trl"],default="messages");p.add_argument("--out")
    p=sub.add_parser("evaluate");p.add_argument("--predictions",required=True)
    p=sub.add_parser("graph")
    choice=p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--search");choice.add_argument("--id",dest="graph_id")
    p.add_argument("--limit",type=int,default=8);p.add_argument("--relation")
    p.add_argument("--text",action="store_true");p.add_argument("--max-bytes",type=int,default=65536)
    args=parser.parse_args(argv);root=Path(args.root).resolve()
    try:
        if args.command=="validate":
            result=validate(root);print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result["status"]=="pass" else 2
        if args.command=="evaluate": print(json.dumps(evaluate(root,args.predictions),ensure_ascii=False,indent=2));return 0
        if args.command=="graph":
            from .graph_query import query
            result=query(root,search=args.search,identifier=args.graph_id,limit=args.limit,relation=args.relation,
                         include_text=args.text,max_bytes=args.max_bytes)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        result=packet(root,args.ids,args.max_bytes) if args.command=="pack" else export_training(root,args.format)
        if args.out: write_build(root,args.out,result)
        else: print(result,end="")
        return 0
    except (OSError,ValueError,KeyError,yaml.YAMLError) as error:
        print(json.dumps({"status":"fail","error":str(error)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=="__main__":
    raise SystemExit(main())
