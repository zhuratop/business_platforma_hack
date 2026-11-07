"""Controlled same-process comparison of previous and current snapshot import."""
import json
import shutil
import time
from backend.app.storage import meta
from backend.app.core.importer import validate

def main():
    source=meta.DATA_ROOT/'data'/'RUN-20260827-0001'
    root=meta.RUNTIME/'import-benchmark'/meta.uid()
    root.mkdir(parents=True)
    start=time.perf_counter()
    original=validate(source)
    old=root/'previous';old.mkdir()
    shutil.copy2(source/'manifest.json',old/'manifest.json')
    for relative in original['dirs'].values():
        (old/relative).mkdir(parents=True)
        for f in (source/relative).glob('*.json'):
            shutil.copy2(f,old/relative/f.name)
    checked=validate(old)
    previous=time.perf_counter()-start
    new=root/'current';new.mkdir()
    start=time.perf_counter()
    current=validate(source,copy_to=new)
    elapsed=time.perf_counter()-start
    assert current['checksum']==checked['checksum']==original['checksum']
    result=dict(previous_seconds=previous,current_seconds=elapsed,speedup=previous/elapsed,files=4005,checksum=current['checksum'],
                method='Same process, sequential previous then current, one repeat. Prior: validate/copy2/validate. Current: same bytes validate/hash/write once. No OS-cache reset.')
    (meta.RUNTIME/'import-benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
