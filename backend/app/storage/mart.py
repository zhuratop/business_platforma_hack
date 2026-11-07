import json
from collections import defaultdict
from contextlib import contextmanager
import duckdb
import pandas as pd
from backend.app.domain.contracts import DIMENSIONS

NORMALIZED = dict(APP_ID='VARCHAR',SOURCE='VARCHAR',PREFIX='VARCHAR',CLASS='VARCHAR',SUFFIX='VARCHAR',ARRAY_KEY='VARCHAR',KEY='VARCHAR',PATH='VARCHAR',VALUE='VARCHAR',ADJUSTED_VALUE='VARCHAR',VALUE_KIND='VARCHAR')
COMPARISON = {**{k:v for k,v in NORMALIZED.items() if k not in ['SOURCE','VALUE','ADJUSTED_VALUE','VALUE_KIND']},
              **{k:'VARCHAR' for k in ['VALUE_BEFORE','VALUE_AFTER','ADJUSTED_BEFORE','ADJUSTED_AFTER','CHANGE_TYPE','KIND_BEFORE','KIND_AFTER']},
              'DIFF_FLAG':'INTEGER','PRESENT_BEFORE':'BOOLEAN','PRESENT_AFTER':'BOOLEAN'}
SEGMENTS = {k:'VARCHAR' for k in ['APP_ID','DECISION_BEFORE','DECISION_AFTER','PRODUCTS','TOP_OFFER_BEFORE','TOP_OFFER_AFTER','PARTNER_TYPE','ROUTING_METHOD','PD_MODEL_BEFORE','PD_MODEL_AFTER','CUTOFF_BEFORE','CUTOFF_AFTER','REJECT_REASON_BEFORE','REJECT_REASON_AFTER','SCORE_OKB_BEFORE','SCORE_OKB_AFTER']}
SEGMENTS['DECISION_CHANGED'] = 'INTEGER'
TRIALS = {k:'VARCHAR' for k in ['APP_ID','SOURCE','product_id','decision','partner_id','partner_type','pd_model','target_score_type','cutoff_name']}
TRIALS.update(target_score='DOUBLE',cutoff_value='DOUBLE',epr='DOUBLE')
OFFERS = dict(APP_ID='VARCHAR',SOURCE='VARCHAR',product_id='VARCHAR',type='VARCHAR',rank='INTEGER')
FACTS = {k:('INTEGER' if k in ['DIFF_FLAG','DECISION_CHANGED'] else 'VARCHAR') for k in DIMENSIONS}
FACTS.update(fact_id='BIGINT',CNT='INTEGER')
SCHEMAS = dict(normalized_union=NORMALIZED,comparison_mart=COMPARISON,app_segments=SEGMENTS,product_trials=TRIALS,offers=OFFERS,pivot_facts=FACTS,fact_memberships={'fact_id':'BIGINT','APP_ID':'VARCHAR'})
KEYS = dict(normalized_union=['APP_ID','SOURCE','PATH','ARRAY_KEY'],comparison_mart=['APP_ID','PATH','ARRAY_KEY'],app_segments=['APP_ID'],product_trials=['APP_ID','SOURCE','product_id'],offers=['APP_ID','SOURCE','product_id','type'],fact_memberships=['fact_id','APP_ID'])

def initialize(con):
    for table, schema in SCHEMAS.items():
        con.execute(f'CREATE TABLE "{table}" ('+','.join(f'"{k}" {t} NOT NULL' if k in KEYS.get(table,[]) else f'"{k}" {t}' for k,t in schema.items())+')')

def write(con,table,rows,batch_size=10000):
    schema = SCHEMAS[table]
    batch = []
    count = 0
    def flush():
        nonlocal count
        if not batch:
            return
        frame = pd.DataFrame(batch,columns=list(schema))
        con.register('_batch',frame)
        columns = ','.join(f'"{k}"' for k in schema)
        con.execute(f'INSERT INTO "{table}" ({columns}) SELECT {columns} FROM _batch')
        con.unregister('_batch')
        count += len(batch)
        batch.clear()
    for row in rows:
        missing = schema.keys() - row.keys()
        if missing:
            raise ValueError(f'{table}: missing contract fields {sorted(missing)}')
        batch.append(row)
        if len(batch)>=batch_size:
            flush()
    flush()
    return count

def indexes(con):
    for table,keys in KEYS.items():
        con.execute(f'CREATE UNIQUE INDEX "{table}_pk" ON "{table}" ('+','.join(f'"{k}"' for k in keys)+')')
    for key in ['PATH','DIFF_FLAG','CHANGE_TYPE']:
        con.execute(f'CREATE INDEX "mart_{key}" ON comparison_mart("{key}")')
    con.execute('CREATE INDEX memberships_fact ON fact_memberships(fact_id)')

def records(con,sql,args=None):
    cursor = con.execute(sql,args or [])
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols,r)) for r in cursor.fetchall()]

class MartAPI:
    def __init__(self,con):
        self.con = con

    def _where(self,filters):
        clauses,args = [],[]
        mapping = dict(path='PATH',key='KEY',array_key='ARRAY_KEY',diff_flag='DIFF_FLAG',change_type='CHANGE_TYPE',value_before='VALUE_BEFORE',value_after='VALUE_AFTER',app_ids='APP_ID')
        for k,v in filters.items():
            if k=='path_prefix':
                clauses.append('starts_with("PATH", ?)')
                args.append(v)
                continue
            if k not in mapping:
                raise ValueError(f'Unknown MartAPI filter: {k}')
            col = '"'+mapping[k]+'"'
            if isinstance(v,(list,tuple,set)):
                values = list(v)
                clauses.append(col+' IN ('+','.join('?' for _ in values)+')' if values else 'FALSE')
                args.extend(values)
            else:
                clauses.append(col+' = ?')
                args.append(v)
        return (' WHERE '+' AND '.join(clauses) if clauses else ''), args

    def rows(self,**filters):
        where,args = self._where(filters)
        return records(self.con,'SELECT * FROM comparison_mart'+where+' ORDER BY APP_ID,PATH,ARRAY_KEY',args)

    def count(self,**filters):
        where,args = self._where(filters)
        return self.con.execute('SELECT count(*) FROM comparison_mart'+where,args).fetchone()[0]

    def app_ids(self,**filters):
        where,args = self._where(filters)
        return [r[0] for r in self.con.execute('SELECT DISTINCT APP_ID FROM comparison_mart'+where+' ORDER BY APP_ID',args).fetchall()]

    def segments(self):
        return records(self.con,'SELECT * FROM app_segments ORDER BY APP_ID')

    def total_apps(self):
        return self.con.execute('SELECT count(*) FROM app_segments').fetchone()[0]

    def default_facts(self,product_paths=()):
        # Domain adapter supplies path associations; core only knows table contracts.
        conditions = ' OR '.join('starts_with(n.PATH, ?)' for _ in product_paths) or 'FALSE'
        sql = f'''SELECT n.*, c.DIFF_FLAG,c.CHANGE_TYPE,s.DECISION_BEFORE,s.DECISION_AFTER,s.DECISION_CHANGED,s.PARTNER_TYPE,s.ROUTING_METHOD,
            CASE WHEN ({conditions}) THEN CASE WHEN starts_with(n.ARRAY_KEY,'[') THEN json_extract_string(split_part(n.ARRAY_KEY,'|',1),'$[0]') ELSE split_part(n.ARRAY_KEY,'|',1) END ELSE '' END AS product_id
            FROM normalized_union n JOIN comparison_mart c USING(APP_ID,PATH,ARRAY_KEY) JOIN app_segments s USING(APP_ID)'''
        # Use DuckDB for aggregation; Python sees aggregate memberships, not a browser-sized raw mart.
        self.con.execute('CREATE TEMP TABLE enriched AS '+sql,list(product_paths))
        self.con.execute('ALTER TABLE enriched ADD COLUMN partner_id VARCHAR')
        self.con.execute("UPDATE enriched e SET partner_id=t.partner_id FROM product_trials t WHERE e.APP_ID=t.APP_ID AND e.SOURCE=t.SOURCE AND e.product_id=t.product_id")
        self.con.execute("UPDATE enriched SET partner_id='' WHERE partner_id IS NULL")
        dims = ','.join('"'+d+'"' for d in DIMENSIONS)
        group_dims = dims.replace('"VALUE_ADJUSTED"','"ADJUSTED_VALUE" AS "VALUE_ADJUSTED"')
        for r in records(self.con, f'SELECT {group_dims},count(DISTINCT APP_ID)::INTEGER AS CNT,list_sort(list(DISTINCT APP_ID)) AS APP_IDS FROM enriched GROUP BY ALL'):
            yield r
        self.con.execute('DROP TABLE enriched')
