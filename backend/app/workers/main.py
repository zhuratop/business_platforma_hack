"""Queue supervisor; each job executes in a separate, time-limited process."""
import argparse
import json
import os
import subprocess
import sys
import time
from backend.app.storage import meta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job',nargs=2)
    args = parser.parse_args()
    meta.init()
    if args.job:
        from backend.app.workers.jobs import execute
        execute(*args.job)
        return
    lock = (meta.RUNTIME/'worker.lock').open('a+b')
    lock.seek(0)
    if os.name=='nt':
        import msvcrt
        lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with meta.db() as c:
        stale = [(t,r['id']) for t in ['runs','check_executions'] for r in c.execute(f"SELECT id FROM {t} WHERE status NOT IN ('QUEUED','READY','FAILED')")]
    for table,id in stale:
        meta.update(table,id,status='FAILED',error='Worker restarted before completion; create a new run')
    print('SPR worker ready',flush=True)
    while True:
        job = meta.claim()
        if job is None:
            time.sleep(0.5)
            continue
        table,id = job
        flags = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        process = subprocess.Popen([sys.executable,'-m','backend.app.workers.main','--job',table,id],cwd=meta.ROOT,**flags)
        start = time.monotonic()
        while process.poll() is None:
            meta.update(table,id,heartbeat=meta.now())
            if time.monotonic()-start>int(os.environ.get('SPR_JOB_TIMEOUT',600)):
                process.kill(); process.wait()
                meta.update(table,id,status='FAILED',error='Python job timeout')
                obj = meta.get(table,id)
                meta.event(id if table=='runs' else obj['run_id'],'FAILED','Python job timeout')
                break
            time.sleep(1)
        if process.returncode:
            meta.update(table,id,status='FAILED',error=f'Worker process exit code {process.returncode}')

if __name__=='__main__':
    main()
