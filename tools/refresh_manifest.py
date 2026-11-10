"""Refresh derived digests after an intentional, reviewed edit. Never publishes."""
from pathlib import Path
import json
from axioma_context.cli import document, digest, project_files
from axioma_context.graph import generate
from axioma_context.explorer import render

ROOT=Path(__file__).resolve().parents[1]

def save(path,data):
    text=json.dumps(data,ensure_ascii=False,indent=2,sort_keys=False)+"\n"
    path.write_text(text,encoding="utf-8",newline="\n")

def refresh(root=ROOT):
    catalog=[]
    for path in project_files(root):
        if path.suffix.casefold()!=".md": continue
        meta,_=document(path.read_text(encoding="utf-8"))
        catalog.append({"id":meta["id"],"title":meta["title"],"kind":meta["kind"],
                        "path":path.relative_to(root).as_posix(),"sha256":digest(path)})
    save(root/"catalog.json",{"edition":"2.0.0","documents":sorted(catalog,key=lambda r:r["path"])})
    provenance=root/"provenance.json"
    if provenance.exists():
        data=json.loads(provenance.read_text(encoding="utf-8"))
        for row in data["sources"]:
            row["public_sha256"]=digest(root/row["public_path"])
        save(provenance,data)
    reading=root/"reading-manifest.json"
    if reading.exists():
        data=json.loads(reading.read_text(encoding="utf-8"))
        by_id={row["id"]:row for row in catalog}
        for row in data["suggested_core_sequence"]:
            actual=by_id[row["id"]]
            for field in ["path","title","sha256"]: row[field]=actual[field]
        save(reading,data)
    graph=generate(root,catalog)
    render(root)
    files=[{"path":p.relative_to(root).as_posix(),"sha256":digest(p),"size_bytes":p.stat().st_size}
           for p in project_files(root) if p.relative_to(root).as_posix()!="manifest.json"]
    save(root/"manifest.json",{"edition":"2.0.0","profile":"English public AXIOMA edition",
        "licenses":{"code":"MIT","text_and_data":"CC-BY-4.0"},"files":sorted(files,key=lambda r:r["path"]),
        "training_performed":False,"model_improvement_measured":False})
    return {"documents":len(catalog),"files":len(files),"graph":graph}

if __name__=="__main__":
    print(json.dumps(refresh(),indent=2))
