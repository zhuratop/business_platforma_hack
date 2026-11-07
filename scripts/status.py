"""Read-only local queue diagnostics."""
from backend.app.storage import meta

with meta.db() as c:
    for table in ['datasets','configs','runs','check_executions']:
        print(table,[(r['id'],r['status']) for r in c.execute(f'SELECT id,status FROM {table} ORDER BY created DESC LIMIT 8')])
    print('last events',[dict(r) for r in c.execute('SELECT run_id,stage,message FROM run_events ORDER BY id DESC LIMIT 5')])
