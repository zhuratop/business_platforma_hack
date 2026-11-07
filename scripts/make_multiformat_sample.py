"""Create a small importable ZIP from real repository fixtures in three formats."""
import argparse
import csv
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def kind(value):
    return ('null' if value is None else 'boolean' if isinstance(value,bool) else
            'number' if isinstance(value,(int,float)) else 'object' if isinstance(value,dict) else
            'array' if isinstance(value,list) else 'string')


def encode(value, fmt):
    if fmt=='json':
        return json.dumps(value,ensure_ascii=False).encode()
    if fmt=='xml':
        def element(name,value):
            node=ET.Element(name,{'type':kind(value)})
            if isinstance(value,dict):
                node.extend(element(k,v) for k,v in value.items())
            elif isinstance(value,list):
                node.extend(element('item',v) for v in value)
            elif value is not None:
                node.text=json.dumps(value) if not isinstance(value,str) else value
            return node
        return ET.tostring(element('response',value),encoding='utf-8')
    buffer=io.StringIO(newline='')
    writer=csv.writer(buffer)
    writer.writerow(['path','value','value_kind'])
    def walk(value,path):
        if isinstance(value,(dict,list)) and value:
            for k,v in (value.items() if isinstance(value,dict) else enumerate(value)):
                walk(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))
        else:
            writer.writerow([path,value if isinstance(value,str) else json.dumps(value),kind(value)])
    walk(value,'')
    return buffer.getvalue().encode()


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=root/'examples'/'multiformat-4-pairs.zip')
    args=parser.parse_args()
    source=root/'backend'/'tests'/'fixtures'/'spr'
    files=sorted((source/'BEFORE').glob('*.json'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps({'applications':len(files),'srez':{s:{'dir':s} for s in ['BEFORE','AFTER']}}))
        for i,file in enumerate(files):
            for j,slice in enumerate(['BEFORE','AFTER']):
                fmt=['json','xml','csv'][(i+j)%3]
                value=json.loads((source/slice/file.name).read_bytes())
                archive.writestr(f'{slice}/{file.stem}.{fmt}',encode(value,fmt))
    print(f'{args.output}: {len(files)} paired applications, JSON/XML/CSV')


if __name__=='__main__':
    main()
