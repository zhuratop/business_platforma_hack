"""SPR adapter: configurable arrays, exclusions and common bucket boundaries."""
from backend.app.core.normalize import flatten


def normalize(response, app_id, source, params):
    embedded = response.get('appData', {}).get('application_id')
    if embedded != app_id:
        raise ValueError(f'APP_ID mismatch: filename={app_id}, response={embedded}')
    yield from flatten(response, app_id, source, params)
