import hashlib
import json
import shutil
import zipfile
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from backend.app.storage import meta

MAX_FILES = 50000
MAX_BYTES = 1024*1024*1024
EXTENSIONS = {'.json', '.xml', '.csv'}


def syntax(raw, suffix):
    """Validate transport syntax, without imposing the adapter's field mapping."""
    text = raw.decode('utf-8-sig')
    try:
        if suffix == '.json':
            json.loads(text)
        elif suffix == '.xml':
            if re.search(r'<!\s*(DOCTYPE|ENTITY)\b', text, re.I):
                raise ValueError('XML DTD and entities are not allowed')
            ET.fromstring(text)
        else:
            if not text.strip():
                raise ValueError('Empty CSV')
            # CSV dialect belongs to the configurable reader. Parsing it here
            # as comma-separated would reject valid semicolon/tab files.
    except ET.ParseError as exc:
        raise ValueError(f'Invalid {suffix} syntax: {exc}') from exc


def slice_files(path, folder):
    result = {}
    names = set()
    for p in sorted(path.iterdir()):
        if p.suffix.lower() not in EXTENSIONS or not p.is_file():
            raise ValueError(f'Expected JSON, XML or CSV application file: {p.name}')
        if p.is_symlink() or not p.resolve().is_relative_to(folder):
            raise ValueError('Symlink input is not allowed')
        if p.stem.casefold() in names:
            raise ValueError(f'Duplicate APP_ID (possibly different formats): {p.stem}')
        names.add(p.stem.casefold())
        result[p.stem] = p
    return result

def validate(folder,copy_to=None):
    folder = Path(folder).resolve()
    if (folder/'manifest.json').is_symlink():
        raise ValueError('Symlink manifest is not allowed')
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    dirs = {}
    ids = {}
    files = {}
    for source in ['BEFORE','AFTER']:
        relative = manifest['srez'][source]['dir']
        path = (folder/relative).resolve()
        if not path.is_relative_to(folder) or not path.is_dir():
            raise ValueError(f'Invalid slice directory: {relative}')
        files[source] = slice_files(path, folder)
        dirs[source] = relative
        ids[source] = set(files[source])
    if ids['BEFORE'] != ids['AFTER']:
        raise ValueError(f"Unpaired applications. BEFORE only: {sorted(ids['BEFORE']-ids['AFTER'])[:20]}; AFTER only: {sorted(ids['AFTER']-ids['BEFORE'])[:20]}")
    if len(ids['BEFORE']) != manifest['applications'] or not ids['BEFORE']:
        raise ValueError(f"Manifest applications={manifest['applications']}, actual={len(ids['BEFORE'])}")
    if 2*len(ids['BEFORE']) > MAX_FILES:
        raise ValueError('Too many files')
    digest = hashlib.sha256()
    size = 0
    relative_files = [files[s][id].relative_to(folder).as_posix() for s in ['BEFORE','AFTER'] for id in sorted(ids[s])]
    for relative in ['manifest.json'] + relative_files:
        f = folder/relative
        size += f.stat().st_size
        if size > MAX_BYTES:
            raise ValueError('Dataset exceeds 1 GiB')
        raw = f.read_bytes()
        syntax(raw, f.suffix.lower())
        digest.update(relative.encode())
        digest.update(raw)
        if copy_to is not None:
            dest = Path(copy_to)/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(raw)
    return dict(count=len(ids['BEFORE']), checksum=digest.hexdigest(), dirs=dirs, bytes=size,
                formats=sorted({p.suffix.lower()[1:] for group in files.values() for p in group.values()}))

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
    keep = False
    try:
        info = validate(folder,copy_to=target)
        dataset = meta.register_dataset(owner,{**info,'name':name or folder.name,'path':str(target)},id)
        keep = dataset['id'] == id
        return dataset
    finally:
        if not keep:
            # Only this import's new directory; published snapshots stay intact.
            resolved = target.resolve()
            if resolved.parent != (meta.RUNTIME/'uploads').resolve() or resolved.name != id:
                raise ValueError('Unexpected import snapshot path')
            shutil.rmtree(resolved)

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
            if target.suffix.lower() not in EXTENSIONS or str(target).casefold() in seen:
                raise ValueError('ZIP permits unique JSON, XML and CSV files only')
            seen.add(str(target).casefold())
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(e) as src, target.open('wb') as dst:
                shutil.copyfileobj(src,dst)
    candidates = list(staging.rglob('manifest.json'))
    if len(candidates)!=1:
        raise ValueError('ZIP must contain exactly one manifest.json')
    return copy_dataset(owner,candidates[0].parent,name)

def pairs(dataset, reader=None, params=None):
    if reader is None:
        from scripts.default_spr.reader import read_input
        reader = read_input
    root = Path(dataset['path'])
    files = {s:slice_files(root/dataset['dirs'][s], root) for s in ['BEFORE','AFTER']}
    if files['BEFORE'].keys() != files['AFTER'].keys():
        raise ValueError('Unpaired application snapshot')
    for app_id in sorted(files['BEFORE']):
        responses = []
        for source in ['BEFORE','AFTER']:
            p = files[source][app_id]
            try:
                response = reader(p.read_bytes(), p.relative_to(root).as_posix(), app_id, source, params or {})
                if not isinstance(response, dict):
                    raise ValueError('read_input must return a JSON-compatible dict')
                # Freeze values and reject NaN, custom objects and invalid keys.
                encoded = json.dumps(response, ensure_ascii=False, allow_nan=False)
                response = json.loads(encoded)
            except Exception as exc:
                raise ValueError(f'{source}/{p.name}: {exc}') from exc
            responses.append(response)
        yield app_id, *responses
