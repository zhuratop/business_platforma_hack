import {useEffect,useState} from 'react';
import {api} from './api';
import type {Run} from './types';
import './runStages.css';

export const pipelineStages=[['READING','Чтение данных'],['NORMALIZING','Нормализация'],['COMPARING','Сравнение'],['FACTS','Факты и разрезы'],['CHECKS','Автопроверки'],['STATS','Статистика'],['REPORTING','HTML-отчёт']];
export function StopStageSelect({value,onChange,after=-1}:{value:string;onChange:(v:string)=>void;after?:number}){
 return <label>Выполнить до этапа<select aria-label="Выполнить до этапа" value={value} onChange={e=>onChange(e.target.value)}>{pipelineStages.map(([id,label],i)=>i>after&&<option key={id} value={id}>{id==='REPORTING'?'Полный расчёт и HTML-отчёт':label}</option>)}</select></label>;
}

export function RunStagesPanel({run,busy,onResume}:{run:Run|null;busy:boolean;onResume:(stage:string)=>Promise<void>}){
 const [target,setTarget]=useState('REPORTING');
 const [preview,setPreview]=useState<any>(null),[table,setTable]=useState('raw_inputs'),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const points=run?.checkpoints||[];
 const last=points.at(-1)?.stage;
 const complete=run?.status==='READY'?6:pipelineStages.findIndex(([id])=>id===run?.completed_stage);
 useEffect(()=>{setTarget('REPORTING')},[run?.id,complete]);
 useEffect(()=>{setPreview(null);setTable('raw_inputs');setError('')},[run?.id]);
 useEffect(()=>{if(!run?.id||!last)return;let active=true;setLoading(true);setError('');api('/runs/'+run.id+'/preview?table='+encodeURIComponent(table)+'&limit=10').then(data=>{if(active)setPreview(data)}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[run?.id,last,table]);
 if(!run)return <section className="panel"><h2>Выполнение прогона</h2><p>Выберите конфигурацию и запустите задачу.</p></section>;
 const resumable=['PAUSED','FAILED'].includes(run.status)&&complete<6;
 return <section className="panel run-stages"><div className="panel-heading"><h2>Выполнение прогона</h2><span className="tag">{run.status==='PAUSED'?'Сохранён, ожидает продолжения':run.status}</span><span className="muted mono">{run.id}</span></div>
 <ol className="stage-track">{pipelineStages.map(([id,label],i)=><li key={id} className={i<=complete?'complete':run.status===id?'running':''}><span>{i<=complete?'✓':i+1}</span><b>{label}</b><small>{i<=complete?'Сохранено':run.status===id?'Выполняется':'Ожидает'}</small></li>)}</ol>
 {run.error&&<p className="error">{run.error}</p>}
 <p className="muted">Этапы выполняются последовательно. Каждый завершённый этап сохраняется отдельно. Другие прогоны могут выполняться параллельно.</p>
 {resumable&&<div className="resume-controls"><StopStageSelect value={target} onChange={setTarget} after={complete}/><button className="primary" disabled={busy} onClick={()=>void onResume(target)}>{run.status==='FAILED'?'Повторить незавершённый этап и продолжить':'Продолжить прогон'}</button><small>Используются исходные код и настройки этого прогона. Для других настроек создайте новый запуск.</small></div>}
 {!!points.length&&<details className="stage-snapshots"><summary>Сохранённые этапы · {points.length}</summary><ul>{points.map(point=><li key={point.stage}><b>{point.label}</b><span>{new Date(point.completed_at).toLocaleString('ru-RU')} · {point.seconds.toFixed(2)} с</span></li>)}</ul></details>}
 {last&&<div className="stage-preview"><div className="panel-heading"><h3>Данные последнего сохранённого этапа</h3><label>Таблица<select aria-label="Таблица сохранённого этапа" value={table} onChange={e=>setTable(e.target.value)}>{(preview?.tables||['raw_inputs']).map((t:string)=><option key={t}>{t}</option>)}</select></label></div>{loading&&<p>Загрузка данных…</p>}{error&&<p className="error">{error}</p>}{preview&&<><p className="muted">{preview.total.toLocaleString('ru-RU')} строк · показаны первые {preview.rows.length}</p><div className="table-wrap"><table><thead><tr>{Object.keys(preview.rows[0]||{}).map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{preview.rows.map((row:any,i:number)=><tr key={i}>{Object.entries(row).map(([key,value])=><td key={key}>{(key.endsWith('_JSON')||(typeof value==='object'&&value!==null))?<details><summary>Открыть JSON</summary><pre>{JSON.stringify(key.endsWith('_JSON')?JSON.parse(String(value)):value,null,2)}</pre></details>:String(value??'∅')}</td>)}</tr>)}</tbody></table></div></>}</div>}
 </section>;
}
