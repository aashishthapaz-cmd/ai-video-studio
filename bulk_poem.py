from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from artwork_prompts import generate_plan

ENTRY = re.compile(r'^\s*(\d+)\.\s*(\S.*)\s*$')

def parse_bulk(text: str):
    text = str(text or '').replace('\r\n','\n').replace('\r','\n').lstrip('\ufeff')
    rows=[]; current=None
    for raw in text.split('\n'):
        line=raw.strip()
        if not line:
            if current and current['lines']: current['lines'].append('')
            continue
        m=ENTRY.match(raw)
        if m:
            if current:
                poem='\n'.join(current['lines']).strip()
                if poem: rows.append({'number':current['number'],'title':current['title'],'poem':poem})
            current={'number':int(m.group(1)),'title':m.group(2).strip(),'lines':[]}
        elif current is not None:
            current['lines'].append(line)
    if current:
        poem='\n'.join(current['lines']).strip()
        if poem: rows.append({'number':current['number'],'title':current['title'],'poem':poem})
    if not rows: raise ValueError('Expected entries such as: 1. Title followed by the poem')
    return rows

def make_project(entry, out_root: Path):
    nepali=any('\u0900' <= ch <= '\u097f' for ch in entry['title']+' '+entry['poem'])
    content_type='poetry_nepali' if nepali else 'poetry'
    base_slug=re.sub(r'[^a-z0-9]+','_',entry['title'].lower()).strip('_') or f"poem_{entry['number']:03d}"
    slug=base_slug
    suffix=2
    while (Path(out_root)/slug).exists():
        slug=f"{base_slug}_{suffix:02d}"
        suffix+=1
    project_dir=Path(out_root)/slug
    for folder in ('assets','audio','frames','outputs','sources'):
        (project_dir/folder).mkdir(parents=True,exist_ok=True)
    base={'title':entry['title'],'name':slug,'script':entry['poem'],'content_type':content_type,'language':'ne' if nepali else 'en'}
    try: plan=generate_plan(base)
    except Exception:
        plan={'title':entry['title'],'language':base['language'],'content_type':content_type,'scenes':[{'id':f'scene_{i:03d}','narration':line,'duration':5} for i,line in enumerate(entry['poem'].splitlines(),1) if line.strip()]}
    plan.update({'source_number':entry['number'],'caption_style':'hidden_nepali' if nepali else 'english_exact_source','use_i2v':False,'bypass_i2v':True,'reference_25d_parallax':True,'language':base['language'],'content_type':content_type})
    (project_dir/'project.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    return project_dir

def main():
    if len(sys.argv)<3: raise SystemExit('Usage: python bulk_poem.py input.txt output_projects_dir')
    text=Path(sys.argv[1]).read_text(encoding='utf-8-sig'); output=Path(sys.argv[2]); output.mkdir(parents=True,exist_ok=True)
    made=[str(make_project(entry,output)) for entry in parse_bulk(text)]
    print(json.dumps({'projects':made},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
