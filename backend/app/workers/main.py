"""Bounded parallel queue supervisor; each task has a separate process and mart."""
import argparse
import os
import sys
import time
from pathlib import Path

from backend.app.storage import meta
from backend.app.workers.processes import JobProcess


def recover():
    with meta.db() as con:
        stale = [(table, row['id']) for table in ['runs', 'check_executions']
            for row in con.execute(f"SELECT id FROM {table} WHERE status NOT IN ('QUEUED','PAUSED','READY','FAILED')")]
    for table, id in stale:
        obj = meta.get(table, id)
        if table == 'runs' and obj.get('completed_stage') == 'REPORTING' and Path(obj.get('mart_path', '')).is_file():
            meta.update(table, id, status='READY')
        else:
            message = 'Worker перезапущен. Сохранённые этапы доступны; продолжите прогон.'
            meta.update(table, id, status='FAILED', error=message)
            meta.event(id if table == 'runs' else obj['run_id'], 'FAILED', message)


def supervise(workers, stop=None):
    """stop is an optional test/shutdown callback; slot occupancy is bounded."""
    running = {}
    timeout = int(os.environ.get('SPR_JOB_TIMEOUT', '600'))
    try:
        while stop is None or not stop():
            for key, (child, started) in list(running.items()):
                table, id = key
                code = child.process.poll()
                expired = code is None and time.monotonic() - started > timeout
                if code is None and not expired:
                    meta.update(table, id, heartbeat=meta.now())
                    continue
                child.close()
                if code or expired:
                    obj = meta.get(table, id)
                    message = 'Python job timeout' if expired else f'Worker process exit code {code}'
                    meta.update(table, id, status='FAILED', error=message)
                    meta.event(id if table == 'runs' else obj['run_id'], 'FAILED', message)
                del running[key]
            while len(running) < workers:
                job = meta.claim()
                if job is None:
                    break
                table, id = job
                try:
                    child = JobProcess([sys.executable, '-m', 'backend.app.workers.main', '--job', table, id], meta.ROOT)
                    meta.update(table, id, process_id=child.process.pid)
                    running[job] = child, time.monotonic()
                except Exception as exc:
                    meta.update(table, id, status='FAILED', error=f'Не удалось запустить worker: {exc}')
            time.sleep(.25)
    finally:
        for (table, id), (child, _) in running.items():
            child.close()
            obj = meta.get(table, id)
            if obj['status'] not in ['PAUSED', 'READY', 'FAILED']:
                meta.update(table, id, status='FAILED', error='Worker остановлен. Продолжите с сохранённого этапа.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', nargs=2)
    parser.add_argument('--workers', type=int, default=int(os.environ.get('SPR_WORKERS', '10')))
    args = parser.parse_args()
    if not 1 <= args.workers <= 10:
        parser.error('--workers must be between 1 and 10')
    meta.init()
    if args.job:
        from backend.app.workers.jobs import execute
        execute(*args.job)
        return
    lock = (meta.RUNTIME / 'worker.lock').open('a+b')
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        recover()
        print(f'SPR worker ready: {args.workers} parallel jobs', flush=True)
        supervise(args.workers)
    except KeyboardInterrupt:
        pass
    finally:
        lock.close()


if __name__ == '__main__':
    main()
