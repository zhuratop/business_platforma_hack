import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from backend.app.storage import meta

MAX_FILES = 50000
MAX_BYTES = 1024*1024*1024

def validate(folder,copy_to=None):
    folder = Path(folder).resolve()
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    dirs = {}
    ids = {}
    for source in ['BEFORE','AFTER']:
        relative = manifest['srez'][source]['dir']
        path = (folder/relative).resolve()
        if not path.is_relative_to(folder) or not path.is_dir():
            raise ValueError(f'Invalid slice directory: {relative}')
        files = sorted(path.glob('*.json'))
        if any(p.is_symlink() or not p.resolve().is_relative_to(folder) for p in files):
            raise ValueError('Symlink input is not allowed')
        dirs[source] = relative
        ids[source] = {p.stem for p in files}
    if ids['BEFORE'] != ids['AFTER']:
        raise ValueError(f"Unpaired applications. BEFORE only: {sorted(ids['BEFORE']-ids['AFTER'])[:20]}; AFTER only: {sorted(ids['AFTER']-ids['BEFORE'])[:20]}")
    if len(ids['BEFORE']) != manifest['applications'] or not ids['BEFORE']:
        raise ValueError(f"Manifest applications={manifest['applications']}, actual={len(ids['BEFORE'])}")
    if 2*len(ids['BEFORE']) > MAX_FILES:
        raise ValueError('Too many files')
    digest = hashlib.sha256()
    size = 0
    for relative in ['manifest.json'] + [f'{dirs[s]}/{id}.json' for s in ['BEFORE','AFTER'] for id in sorted(ids[s])]:
        f = folder/relative
        size += f.stat().st_size
        if size > MAX_BYTES:
            raise ValueError('Dataset exceeds 1 GiB')
        raw = f.read_bytes()
        # Reject malformed JSON before enqueueing.
        json.loads(raw)
        digest.update(relative.encode())
        digest.update(raw)
        if copy_to is not None:
            dest = Path(copy_to)/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(raw)
    return dict(count=len(ids['BEFORE']), checksum=digest.hexdigest(), dirs=dirs, bytes=size)

def snapshot(owner,folder,name=None):
    folder = Path(folder).resolve()
    if not folder.is_relative_to(meta.DATA_ROOT):
        raise ValueError(f'Catalog must be inside SPR_DATA_ROOT ({meta.DATA_ROOT})')
    return copy_dataset(owner,folder,name)

def copy_dataset(owner,folder,name=None):
    id = meta.uid()
    target = meta.RUNTIME/'uploads'/id
    target.mkdir(parents=True)
    # Validate, hash and snapshot exactly the same bytes in one pass. No rereads
    # of mutable source files, and no costly per-file metadata copying.
    info = validate(folder,copy_to=target)
    return meta.put('datasets',owner,{**info,'name':name or folder.name,'path':str(target)},'VALIDATED',id)

def unzip(owner,archive,name):
    staging = meta.RUNTIME/'uploads'/('staging-'+meta.uid())
    staging.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries)>MAX_FILES+100 or sum(e.file_size for e in entries)>MAX_BYTES:
            raise ValueError('ZIP exceeds file/size limits')
        seen = set()
        for e in entries:
            p = PurePosixPath(e.filename.replace('\\','/'))
            target = (staging/str(p)).resolve()
            mode = e.external_attr >> 16
            if p.is_absolute() or not target.is_relative_to(staging) or ':' in str(p) or mode & 0o170000 == 0o120000:
                raise ValueError('Unsafe ZIP path or symlink')
            if e.is_dir():
                continue
            if target.suffix != '.json' or str(target).casefold() in seen:
                raise ValueError('ZIP permits unique .json files only')
            seen.add(str(target).casefold())
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(e) as src, target.open('wb') as dst:
                shutil.copyfileobj(src,dst)
    candidates = list(staging.rglob('manifest.json'))
    if len(candidates)!=1:
        raise ValueError('ZIP must contain exactly one manifest.json')
    return copy_dataset(owner,candidates[0].parent,name)

def pairs(dataset):
    root = Path(dataset['path'])
    for p in sorted((root/dataset['dirs']['BEFORE']).glob('*.json')):
        yield p.stem,json.loads(p.read_bytes()),json.loads((root/dataset['dirs']['AFTER']/p.name).read_bytes())
