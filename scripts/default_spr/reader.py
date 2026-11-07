"""Standalone input decoder. Return one JSON-compatible object per application.

CSV: path,value,value_kind (paths are JSON Pointers, array indexes are numeric).
XML: object children, arrays with type="array" and <item>, explicit scalar type.
Untyped XML/CSV values remain strings; never guess identifiers or nulls.
"""
import csv
import io
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import PurePath


def scalar(value, kind):
    if kind == 'string':
        return value
    if kind == 'null':
        if value.strip() not in ('', 'null'):
            raise ValueError('Nonempty null value')
        return None
    if kind == 'boolean':
        if value.strip() not in ('true', 'false'):
            raise ValueError('Boolean must be true or false')
        return value.strip() == 'true'
    if kind == 'number':
        result = json.loads(value)
        if isinstance(result, bool) or not isinstance(result, (int, float)) or (isinstance(result,float) and not math.isfinite(result)):
            raise ValueError('Expected finite JSON number')
        return result
    if kind in ('object', 'array'):
        result = json.loads(value)
        if not isinstance(result, dict if kind == 'object' else list):
            raise ValueError('Wrong container type')
        return result
    raise ValueError(f'Unknown value_kind: {kind}')


def csv_object(text, params):
    delimiter = params.get('csv_delimiter', ',')
    rows = csv.DictReader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    if rows.fieldnames != ['path', 'value', 'value_kind']:
        raise ValueError('CSV header must be path,value,value_kind; use a custom reader for another layout')
    entries = {}
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('CSV column count mismatch')
        pointer = row['path']
        if not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
            raise ValueError('CSV path must be a JSON Pointer, e.g. /decisionResult/decision')
        parts = tuple(p.replace('~1', '/').replace('~0', '~') for p in pointer[1:].split('/'))
        if parts in entries:
            raise ValueError(f'Duplicate CSV path: {pointer}')
        entries[parts] = scalar(row['value'], row['value_kind'])
    if not entries:
        raise ValueError('CSV contains no attributes')

    def build(prefix, root=False):
        if prefix in entries:
            if any(len(p) > len(prefix) and p[:len(prefix)] == prefix for p in entries):
                raise ValueError('CSV path is both a value and a parent')
            return entries[prefix]
        keys = sorted({p[len(prefix)] for p in entries if len(p) > len(prefix) and p[:len(prefix)] == prefix})
        if not root and keys and all(re.fullmatch(r'0|[1-9][0-9]*', k) for k in keys):
            ordered = sorted(keys, key=int)
            if [int(k) for k in ordered] != list(range(len(ordered))):
                raise ValueError('CSV array indexes must be contiguous from zero')
            return [build(prefix + (k,)) for k in ordered]
        return {k: build(prefix + (k,)) for k in keys}
    return build((), root=True)


def xml_object(text, params):
    # DTDs/entities are unnecessary for input data. Reject before parsing.
    if re.search(r'<!\s*(DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('XML DTD and entities are not allowed')
    root = ET.fromstring(text)
    types = params.get('xml_types', {})
    arrays = set(params.get('xml_arrays', []))
    def name(tag):
        return tag.rsplit('}', 1)[-1]
    def convert(node, path):
        children = list(node)
        attrs = {name(k): v for k, v in node.attrib.items()}
        if set(attrs) - {'type', 'nil'}:
            raise ValueError(f'XML attributes require a custom reader: {path}')
        kind = attrs.get('type', types.get(path, 'string')).split(':')[-1]
        kind = {'int':'number', 'integer':'number', 'double':'number', 'decimal':'number', 'bool':'boolean'}.get(kind, kind)
        if attrs.get('nil') in ('true', '1'):
            kind = 'null'
        if children and ((node.text or '').strip() or any((c.tail or '').strip() for c in children)):
            raise ValueError(f'XML mixed content requires a custom reader: {path}')
        if kind == 'array' or path in arrays:
            if (node.text or '').strip():
                raise ValueError(f'XML array has scalar content: {path}')
            return [convert(c, path + '[]') for c in children]
        if children or kind == 'object':
            if kind not in ('string', 'object'):
                raise ValueError(f'XML scalar has children: {path}')
            grouped = {}
            for c in children:
                key = name(c.tag)
                grouped.setdefault(key, []).append(c)
            return {k: ([convert(c, f'{path}.{k}'.strip('.')) for c in group] if len(group) > 1 else
                        convert(group[0], f'{path}.{k}'.strip('.'))) for k, group in grouped.items()}
        return scalar(node.text or '', kind)
    # Root is a transport envelope by default. keep_root supports <company>.
    result = convert(root, name(root.tag) if params.get('xml_keep_root') else '')
    return {name(root.tag): result} if params.get('xml_keep_root') else result


def read_input(raw, filename, app_id, source, params):
    """raw: bytes; filename: relative path; source: BEFORE/AFTER; return dict."""
    text = raw.decode(params.get('encoding', 'utf-8-sig'))
    suffix = PurePath(filename).suffix.lower()
    if suffix == '.json':
        result = json.loads(text)
    elif suffix == '.xml':
        result = xml_object(text, params)
    elif suffix == '.csv':
        result = csv_object(text, params)
    else:
        raise ValueError(f'Unsupported input extension: {suffix}')
    if not isinstance(result, dict):
        raise ValueError('Input reader must return an object')
    return result
