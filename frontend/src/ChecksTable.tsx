import {useState} from 'react';
import {X} from 'lucide-react';
import {percent,percentNumber,rangeFilter} from './checkFilters';
import './checksTable.css';

export type CheckRow={LABEL:string;SOURCE:string;ARGUMENT:string;CNT:number;TOTAL:number;METRIC:number;
 APP_IDS:string[];RESULT:string;CONFIDENCE:string;threshold?:{value:number|null;parameter:string|null;operator:string}};
type Filters=Record<string,string>;
const textMatches=(value:string,filter:string)=>value.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase());

export function ChecksTable({rows,onApp,onApps}:{rows:CheckRow[];onApp:(id:string)=>void;onApps:(row:CheckRow)=>void}){
 const [filters,setFilters]=useState<Filters>({});
 const thresholdFilter=filters.threshold_missing==='1'?{valid:true,matches:(v:number|null)=>v===null}:rangeFilter(filters.threshold_min||'',filters.threshold_max||'');
 const metricFilter=rangeFilter(filters.METRIC_min||'',filters.METRIC_max||'');
 const filtered=rows.filter(r=>['LABEL','ARGUMENT'].every(k=>textMatches(String(r[k as keyof CheckRow]||''),filters[k]||''))&&(!filters.SOURCE||r.SOURCE===filters.SOURCE)&&(!filters.RESULT||r.RESULT===filters.RESULT)&&(!filters.CONFIDENCE||r.CONFIDENCE===filters.CONFIDENCE)&&thresholdFilter.matches(percentNumber(r.threshold?.value))&&metricFilter.matches(percentNumber(r.METRIC)));
 const active=Object.values(filters).some(v=>v.trim());
 function input(key:string,name:string){return <div className="check-column-filter"><input aria-label={'Фильтр: '+name} value={filters[key]||''} onChange={e=>setFilters({...filters,[key]:e.target.value})} placeholder={name+'…'}/></div>}
 function dropdown(key:string,name:string,values:string[]){return <div className="check-column-filter"><select aria-label={'Фильтр: '+name} value={filters[key]||''} onChange={e=>setFilters({...filters,[key]:e.target.value})}><option value="">Все</option>{values.map(v=><option key={v} value={v}>{v}</option>)}</select></div>}
 function range(key:string,name:string){const valid=key==='threshold'?thresholdFilter.valid:metricFilter.valid;const missing=key==='threshold'&&filters.threshold_missing==='1';return <div className="check-column-filter check-range-filter"><div className="check-range-inputs">{[['min','от','От'],['max','до','До']].map(([suffix,aria,placeholder])=><input key={suffix} inputMode="decimal" aria-label={'Фильтр: '+name+' '+aria} disabled={missing} value={filters[key+'_'+suffix]||''} onChange={e=>setFilters({...filters,[key+'_'+suffix]:e.target.value})} placeholder={placeholder} aria-invalid={!valid}/>)}</div>{!valid&&<small className="filter-invalid">Проверьте диапазон: от ≤ до.</small>}{key==='threshold'&&<label className="checkbox check-missing-threshold"><input type="checkbox" checked={missing} onChange={e=>setFilters({...filters,threshold_missing:e.target.checked?'1':''})}/> Без порога</label>}</div>}
 return <><div className="checks-filter-status"><span>Показано {filtered.length} из {rows.length} строк</span>{active&&<button className="link" onClick={()=>setFilters({})}><X size={13}/> Сбросить фильтры</button>}<small>Диапазоны «от — до» включают обе границы. Пустая граница не ограничивает значение.</small></div>
 <div className="table-wrap"><table className="checks-table"><thead><tr>{['Проверка / аргумент','Срез','CNT / TOTAL','Порог, %','Разница в %','Результат','Уверенность','Заявки'].map(t=><th key={t}>{t}</th>)}</tr>
 <tr className="checks-filter-row"><th>{input('LABEL','Проверка')}{input('ARGUMENT','Аргумент')}</th><th>{dropdown('SOURCE','Срез',['BEFORE','AFTER'])}</th><th/><th>{range('threshold','Порог')}</th><th>{range('METRIC','Разница в %')}</th><th>{dropdown('RESULT','Результат',['PASS','FAIL'])}</th><th>{dropdown('CONFIDENCE','Уверенность',['HIGH','LOW'])}</th><th/></tr></thead>
 <tbody>{filtered.map((r,i)=><tr key={i} className={r.CONFIDENCE==='LOW'?'low-confidence':r.RESULT==='FAIL'?'check-fail':''}>
 <td><b>{r.LABEL}</b><small>{r.ARGUMENT}</small></td><td>{r.SOURCE}</td><td>{r.CNT} / {r.TOTAL}</td>
 <td className="check-percentage" title={r.threshold?.value==null?'Численный процентный порог не задан':`${r.threshold.parameter}: ${r.threshold.operator} ${percent(r.threshold.value)}`}>{percent(r.threshold?.value)}</td>
 <td className="check-percentage" title="Исходная METRIC × 100; смысл показателя определяется проверкой">{percent(r.METRIC)}</td>
 <td><span className={'badge '+(r.RESULT==='PASS'?'success':r.CONFIDENCE==='LOW'?'':'danger')}>{r.RESULT}</span></td><td>{r.CONFIDENCE}</td>
 <td><div className="app-links">{r.APP_IDS.slice(0,3).map(id=><button className="link mono" key={id} onClick={()=>onApp(id)}>{id}</button>)}{r.APP_IDS.length>3&&<button className="link" onClick={()=>onApps(r)}>Все {r.APP_IDS.length}</button>}</div>{r.CNT>r.APP_IDS.length&&<small>Первые {r.APP_IDS.length} из {r.CNT}</small>}</td></tr>)}</tbody></table></div>
 {!filtered.length&&<div className="empty">Нет строк, соответствующих фильтрам.</div>}
 <p className="hint">В выданных проверках для Approval Rate показано относительное падение, для остальных — доля затронутых заявок. Отображение: METRIC × 100. Значения и числовые фильтры указаны в процентах с точностью до одного знака. Прочерк означает отсутствие процентного порога.</p></>
}
