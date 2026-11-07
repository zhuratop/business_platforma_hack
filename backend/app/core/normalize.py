import json
import math
from decimal import Decimal


def canonical(value):
    if value is None:
        return 'NULL', 'null'
    if isinstance(value, bool):
        return str(value).lower(), 'boolean'
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite JSON number')
        return format(Decimal(str(value)).normalize(), 'f'), 'number'
    if isinstance(value, str):
        return value, 'string'
    raise ValueError(f'Unsupported leaf: {type(value)}')


def get_path(obj, path):
    for part in path.split('.'):
        if not isinstance(obj, dict) or part not in obj:
            raise ValueError(f'Missing array key: {path}')
        obj = obj[part]
    return obj


def flatten(response, app_id, source, params):
    rules = params.get('arrays', {})
    exclusions = params.get('exclude', [])
    buckets = params.get('buckets', {})
    aliases = params.get('aliases', {})
    seen = set()

    def walk(value, path, array_keys):
        if any(path == p or path.startswith(p + '.') for p in exclusions):
            return
        if isinstance(value, dict):
            for key, child in value.items():
                yield from walk(child, f'{path}.{key}' if path else key, array_keys)
        elif isinstance(value, list):
            if path not in rules:
                raise ValueError(f'Array has no configured matching mode: {path}')
            rule = rules[path]
            used = set()
            for index, child in enumerate(value):
                if rule['mode'] == 'fields':
                    components = [canonical(get_path(child, k))[0] for k in rule['keys']]
                    if any('|' in x for x in components):
                        raise ValueError(f'Invalid | in array key: {path}')
                    component = components[0] if len(components) == 1 else json.dumps(components, ensure_ascii=False, separators=(',', ':'))
                elif rule['mode'] == 'index':
                    component = str(index)
                elif rule['mode'] == 'value':
                    val, kind = canonical(child)
                    component = val if kind=='string' else json.dumps([kind,val],separators=(',',':'))
                else:
                    raise ValueError(f'Unknown mode: {rule}')
                if '|' in component or component in used:
                    raise ValueError(f'Duplicate or invalid array key at {path}: {component}')
                used.add(component)
                yield from walk(child, path, array_keys + [component])
        else:
            rendered, kind = canonical(value)
            adjusted = rendered
            for b in buckets.get(path, []):
                if kind == 'number' and (b.get('min') is None or float(value) > b['min']) and (b.get('max') is None or float(value) <= b['max']):
                    adjusted = b['label']
                    break
            mapped = aliases.get(path, path)
            parts = mapped.split('.')
            row = dict(APP_ID=app_id, SOURCE=source, PREFIX=parts[0], CLASS=parts[1] if len(parts)>2 else '',
                       SUFFIX='.'.join(parts[2:-1]), KEY=parts[-1], PATH=mapped,
                       ARRAY_KEY='|'.join(array_keys), VALUE=rendered, ADJUSTED_VALUE=adjusted, VALUE_KIND=kind)
            key = (mapped, row['ARRAY_KEY'])
            if key in seen:
                raise ValueError(f'Duplicate normalized key: {app_id} {key}')
            seen.add(key)
            yield row

    yield from walk(response, '', [])


def compare_rows(before_rows, after_rows, params):
    def index(rows):
        result = {}
        for row in rows:
            k = row['PATH'], row['ARRAY_KEY']
            if k in result:
                raise ValueError(f'Duplicate comparison input: {k}')
            result[k] = row
        return result
    before, after = index(before_rows), index(after_rows)
    for key in sorted(before.keys() | after.keys()):
        b, a = before.get(key), after.get(key)
        r = a or b
        changed = b is None or a is None or (b['VALUE_KIND'], b['VALUE']) != (a['VALUE_KIND'], a['VALUE'])
        yield {**{k: r[k] for k in ('APP_ID','PREFIX','CLASS','SUFFIX','ARRAY_KEY','KEY','PATH')},
               'VALUE_BEFORE': b['VALUE'] if b else '', 'VALUE_AFTER': a['VALUE'] if a else '',
               'ADJUSTED_BEFORE': b['ADJUSTED_VALUE'] if b else '', 'ADJUSTED_AFTER': a['ADJUSTED_VALUE'] if a else '',
               'DIFF_FLAG': int(changed), 'CHANGE_TYPE': 'ATTRIBUTE_NEW' if b is None else 'ATTRIBUTE_LOST' if a is None else 'VALUE_CHANGED' if changed else 'SAME',
               'PRESENT_BEFORE': b is not None, 'PRESENT_AFTER': a is not None,
               'KIND_BEFORE': b['VALUE_KIND'] if b else 'missing', 'KIND_AFTER': a['VALUE_KIND'] if a else 'missing'}
