"""Complete comparison procedure for one APP_ID.

Presence, JSON type and original value determine differences, never the bucket.
No application-module imports: this file can be copied into the Python editor.
"""


def compare(before_rows, after_rows, params):
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
