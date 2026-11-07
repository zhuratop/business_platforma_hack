"""Durable immutable stage checkpoints and resumption with frozen code/config."""
import os
import shutil
import time

import duckdb

from backend.app.storage import meta
from backend.app.storage.mart import initialize, SCHEMAS, MartAPI
from backend.app.core.pipeline import STAGES, LABELS, stop_stage
from backend.app.core.execution import run_checks
from backend.app.core.report import render
from backend.app.stats.paired import calculate, decision
from backend.app.workers import stages

DB_STAGES = dict(READING=stages.reading, NORMALIZING=stages.normalizing, COMPARING=stages.comparing, FACTS=stages.facts_stage)
KINDS = dict(READING='reader', NORMALIZING='normalize', COMPARING='compare', FACTS='facts')


def full_run(id):
    run = meta.get('runs', id)
    if run['status'] not in ['QUEUED', 'READING']:
        raise ValueError('Прогон не поставлен в очередь')
    dataset = meta.get('datasets', run['dataset_id'], run['owner_id'])
    config, snaps = run['config'], run['snapshots']
    params = config.get('params', {})
    batch_pairs = params.get('processing', {}).get('batch_pairs', 25)
    if type(batch_pairs) is not int or not 1 <= batch_pairs <= 500:
        raise ValueError('processing.batch_pairs must be an integer from 1 to 500')
    target = stop_stage(run.get('stop_after', 'REPORTING'))
    folder = meta.RUNTIME / 'runs' / id
    folder.mkdir(parents=True, exist_ok=True)
    work = folder / 'mart.tmp.duckdb'
    checkpoints = list(run.get('checkpoints', []))
    completed = run.get('completed_stage')
    start_index = STAGES.index(completed) + 1 if completed else 0
    # Never modify the last successful artifact. Discard only this run's scratch file.
    work.unlink(missing_ok=True)
    work.with_suffix('.duckdb.wal').unlink(missing_ok=True)
    if checkpoints:
        shutil.copyfile(checkpoints[-1]['path'], work)
    else:
        with duckdb.connect(str(work)) as con:
            initialize(con)
            con.execute('CREATE TABLE raw_inputs(APP_ID VARCHAR PRIMARY KEY,BEFORE_JSON VARCHAR,AFTER_JSON VARCHAR)')
    timings = dict(run.get('timings', {}))
    started = time.perf_counter()
    for stage in STAGES[start_index:STAGES.index(target) + 1]:
        phase_start = time.perf_counter()
        sid = config['stages'].get(KINDS.get(stage))
        meta.update('runs', id, status=stage, progress=0, heartbeat=meta.now())
        meta.event(id, stage, LABELS[stage], snapshot_id=sid, code_hash=snaps[sid]['hash'] if sid else None)
        fields = {}
        if stage in DB_STAGES:
            with duckdb.connect(str(work)) as con:
                con.execute('SET threads=?', [int(os.environ.get('SPR_DUCKDB_THREADS', '2'))])
                DB_STAGES[stage](con, run, dataset, batch_pairs)
                con.execute('CHECKPOINT')
                counts = {table: con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in ['raw_inputs', *SCHEMAS]}
            artifact = folder / f'{stage.lower()}.duckdb'
            pending = folder / f'{stage.lower()}.pending.duckdb'
            shutil.copyfile(work, pending)
            os.replace(pending, artifact)
        else:
            artifact = checkpoints[-1]['path']
            counts = dict(checkpoints[-1]['counts'])
            with duckdb.connect(str(artifact), read_only=True) as con:
                if stage == 'CHECKS':
                    fields['checks'] = run_checks(MartAPI(con), snaps, config.get('checks', []), params.get('checks', {}),
                        lambda sid, n: meta.event(id, 'CHECKS', f'Результатов: {n}', snapshot_id=sid, code_hash=snaps[sid]['hash']))
                    counts['checks'] = len(fields['checks'])
                elif stage == 'STATS':
                    from backend.app.workers.jobs import summary
                    stats = calculate(con, params.get('stats', {}))
                    overview = summary(con)
                    overview['decision'] = decision(stats, run.get('checks', []), params.get('thresholds', {}))
                    fields.update(stats=stats, summary=overview)
                    counts['stats'] = len(stats)
                else:
                    overview = {**run['summary'], 'timings': timings,
                        'processing_seconds': round(run.get('processing_seconds', 0) + time.perf_counter() - started, 4)}
                    version = meta.uid()
                    content = render(run, overview, run['stats'], run.get('checks', []), con)
                    (folder / f'report-{version}.html').write_text(content, encoding='utf-8')
                    fields.update(summary=overview, report_version=version, mart_path=str(folder / 'mart.duckdb'))
        timings[stage] = round(time.perf_counter() - phase_start, 4)
        checkpoints.append(dict(stage=stage, label=LABELS[stage], path=str(artifact), counts=counts,
            completed_at=meta.now(), seconds=timings[stage]))
        if stage == 'REPORTING':
            # All readers continue to use the immutable published file.
            os.replace(work, folder / 'mart.duckdb')
        run = meta.update('runs', id, **fields, completed_stage=stage, checkpoints=checkpoints,
            progress=dataset['count'], timings=timings, saved_at=meta.now())
        meta.event(id, 'SAVED', f'Этап сохранён: {LABELS[stage]}', dataset['count'], dataset['count'])
    ready = target == 'REPORTING'
    meta.update('runs', id, status='READY' if ready else 'PAUSED',
        processing_seconds=round(run.get('processing_seconds', 0) + time.perf_counter() - started, 4), heartbeat=meta.now())
    meta.event(id, 'READY' if ready else 'PAUSED', 'Отчёт готов' if ready else f'Сохранено: {LABELS[target]}. Можно продолжить позже.')
