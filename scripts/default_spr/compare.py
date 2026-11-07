from backend.app.core.normalize import compare_rows


def compare(before_rows, after_rows, params):
    yield from compare_rows(before_rows, after_rows, params)
