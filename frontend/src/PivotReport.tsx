import {useEffect,useState} from 'react';
import {ArrowDownRight,ChevronLeft,ChevronRight,ChevronsLeft,Filter,RefreshCw,Settings2,Table2,X} from 'lucide-react';
import type {PivotCell} from './types';
import {dimensionOptions} from './pivotDimensions';
import type {DimensionGroups,DimensionNames} from './pivotDimensions';
import './pivotReport.css';

export type Layout={rows:string[];columns:string[];filters:Record<string,unknown[]>};
export type ReportView=Layout&{id:string;label:string;description:string};
export type ReportData={cells:PivotCell[];column_totals?:PivotCell[];grand_total?:PivotCell;truncated:boolean;
 pagination:{page:number;page_size:number;total_rows:number};layoutRows:string[];layoutColumns:string[];appliedFilters:Record<string,unknown[]>};
type Props={runId:string;totalApps:number;views:ReportView[];dimensions:string[];groups:DimensionGroups;names:DimensionNames;
 rows:string[];columns:string[];filters:Record<string,unknown[]>;filterDim:string;filterValue:string;
 data:ReportData|null;elapsed:number;busy:boolean;
 onRows:(v:string[])=>void;onColumns:(v:string[])=>void;onFilters:(v:Record<string,unknown[]>)=>void;
 onFilterDim:(v:string)=>void;onFilterValue:(v:string)=>void;onBuild:()=>void;onView:(v:ReportView)=>void;onPage:(p:number)=>void;onCell:(c:PivotCell)=>void};

const number=(v:number)=>v.toLocaleString('ru-RU');
const stringify=(v:unknown)=>JSON.stringify(v);
const label=(d:string,names:DimensionNames)=>names[d]||d;
function shown(value:unknown){return value===''||value==null?'∅':String(value)}

export function PivotReport(p:Props){
 const views=p.views.filter(v=>!['all','external'].includes(v.id));
 const [customMode,setCustomMode]=useState(false);
 const [settingsOpen,setSettingsOpen]=useState(false);
 useEffect(()=>{if(!p.data)p.onBuild()},[p.runId]);
 const current={rows:p.rows,columns:p.columns,filters:p.filters};
 const withoutScope=Object.fromEntries(Object.entries(p.filters).filter(([key])=>!['product_id','partner_id'].includes(key)));
 const selected=customMode?undefined:views.find(v=>stringify({rows:v.rows,columns:v.columns,filters:v.filters})===stringify({...current,filters:withoutScope}));
 function selectView(id:string){
  if(id==='custom'){setCustomMode(true);setSettingsOpen(true);return}
  const view=views.find(v=>v.id===id);
  if(view){setCustomMode(false);p.onView(view)}
 }
 const pending=p.data&&stringify(current)!==stringify({rows:p.data.layoutRows,columns:p.data.layoutColumns,filters:p.data.appliedFilters});
 function addFilter(){p.onFilters({...p.filters,[p.filterDim]:p.filterValue.split(';').map(v=>['DIFF_FLAG','DECISION_CHANGED'].includes(p.filterDim)?Number(v):v)})}
 const pages=p.data?Math.max(1,Math.ceil(p.data.pagination.total_rows/p.data.pagination.page_size)):1;
 return <div className="pivot-report">
  <section className="report-toolbar panel">
   <div className="report-toolbar-top"><div className="report-identity"><span className="report-icon"><Table2 size={22}/></span><div><h2>BEFORE <span>MASTER</span><span className="report-versus">vs</span> AFTER <span>BETA</span></h2><p>Один набор заявок · две версии стратегии · проверяемые изменения</p></div></div><span className="report-population">{number(p.totalApps)}<small>пар заявок в прогоне</small></span></div>
   <div className="report-preset-row"><label>Представление<select aria-label="Представление сводной" disabled={p.busy} value={selected?.id||'custom'} onChange={e=>selectView(e.target.value)}>{views.map(v=><option key={v.id} value={v.id}>{v.label}</option>)}<option value="custom">Своя раскладка</option></select></label><p>{selected?.description||'Настройте строки, колонки и фильтры, затем нажмите «Перестроить». Текущие настройки сохранены.'}</p><button className="primary" disabled={p.busy} onClick={p.onBuild}><RefreshCw size={15}/> Перестроить</button></div>
   <details className="report-settings" open={settingsOpen} onToggle={e=>setSettingsOpen(e.currentTarget.open)}><summary><Settings2 size={15}/> Фильтры и раскладка <span>{Object.keys(p.filters).length} фильтров · {p.rows.length} измерений строк · {p.columns.length} колонок</span></summary>
    {!selected&&<div className="button-row"><button className="secondary" onClick={()=>p.onRows([])}>Очистить строки</button><button className="secondary" onClick={()=>p.onColumns([])}>Очистить колонки</button><button className="secondary" onClick={()=>p.onFilters({})}>Сбросить фильтры</button></div>}
    <div className="pivot-controls"><DimensionSelect title="Строки" dimensions={p.dimensions.filter(d=>!p.columns.includes(d))} groups={p.groups} names={p.names} selected={p.rows} canAdd={p.rows.length+p.columns.length<8} onChange={p.onRows}/><DimensionSelect title="Колонки" dimensions={p.dimensions.filter(d=>!p.rows.includes(d))} groups={p.groups} names={p.names} selected={p.columns} canAdd={p.rows.length+p.columns.length<8} onChange={p.onColumns}/><div><label>Добавить фильтр<select aria-label="Filter dimension" value={p.filterDim} onChange={e=>p.onFilterDim(e.target.value)}>{dimensionOptions(p.dimensions,p.groups,p.names)}</select></label><div className="button-row"><input aria-label="Значения фильтра" placeholder="Несколько значений через ;" value={p.filterValue} onChange={e=>p.onFilterValue(e.target.value)}/><button className="secondary" title="Добавить фильтр" onClick={addFilter}><Filter size={15}/></button></div></div></div>
    <p className="hint">Общие атрибуты заявки доступны при выборе любого участвовавшего продукта. Продуктовые атрибуты сохраняют собственную привязку. Для матрицы переходов выберите один PATH. Порядок измерений можно менять стрелками. В строках и колонках вместе — до 8 измерений; чтобы добавить новое при достижении лимита, удалите одно из выбранных.</p>
   </details>
   <div className="filter-chips report-filter-chips">{Object.entries(p.filters).map(([k,v])=><span key={k} title={v.map(String).join('; ')}><b>{label(k,p.names)}</b><span>{v.length>2?`${v.slice(0,2).join(', ')} и ещё ${v.length-2}`:v.map(shown).join(', ')}</span><button title={'Удалить фильтр '+k} onClick={()=>{const f={...p.filters};delete f[k];p.onFilters(f)}}><X size={12}/></button></span>)}</div>
   {pending&&<div className="report-pending">Настройки изменены. Нажмите «Перестроить», чтобы применить их к таблице.</div>}
  </section>
  {p.data?<section className="panel report-result"><div className="report-result-heading"><div><h2>Сводный отчёт по прогону</h2><p>Значения — уникальные APP_ID в каждой ячейке. Нажмите число для перехода к заявкам.</p></div><div className="report-selection"><button disabled={!p.data.grand_total?.count} onClick={()=>p.data?.grand_total&&p.onCell(p.data.grand_total)}>{number(p.data.grand_total?.count||0)}<ArrowDownRight size={14}/></button><small>заявок в текущей выборке</small></div></div>
   <div className="report-legend"><span><i className="legend-stable"/> Без изменений · DIFF_FLAG = 0</span><span><i className="legend-changed"/> Есть изменения · DIFF_FLAG = 1</span><small>Различия считаются по исходным значениям, а не по бакету</small></div>
   <ReportTable data={p.data} names={p.names} onSelect={p.onCell}/>
   {!p.data.cells.length&&<div className="empty">В выбранных фильтрах нет данных.</div>}
   {p.data.truncated&&<p className="notice">Показана только часть ячеек. Уточните фильтры.</p>}
   <div className="report-pagination"><span>{p.data.pagination.total_rows?`${number((p.data.pagination.page-1)*p.data.pagination.page_size+1)}–${number(Math.min(p.data.pagination.page*p.data.pagination.page_size,p.data.pagination.total_rows))} из ${number(p.data.pagination.total_rows)} строк`:'0 строк'}<small> · {(p.elapsed/1000).toFixed(3)} с</small></span><div><button className="secondary" title="Первая страница сводной" disabled={p.busy||p.data.pagination.page===1} onClick={()=>p.onPage(1)}><ChevronsLeft size={15}/></button><button className="secondary" title="Предыдущая страница сводной" disabled={p.busy||p.data.pagination.page===1} onClick={()=>p.onPage(p.data!.pagination.page-1)}><ChevronLeft size={15}/></button><span>Страница {p.data.pagination.page} из {pages}</span><button className="secondary" title="Следующая страница сводной" disabled={p.busy||p.data.pagination.page>=pages} onClick={()=>p.onPage(p.data!.pagination.page+1)}><ChevronRight size={15}/></button></div></div>
   <div className="report-reading"><b>Как читать отчёт</b><p>Строки — иерархия атрибута и его значения. Колонки — выбранные признаки и срезы. Оранжевые ячейки выделяют изменения. Прочерк означает отсутствие наблюдений в текущей выборке; причины появления или исчезновения поля видны в деталях заявки.</p><p>Итог внизу — объединение уникальных APP_ID по всем строкам выборки, а не сумма чисел. Одна заявка может встречаться у нескольких атрибутов и в обеих группах DIFF_FLAG; складывать эти группы нельзя.</p></div>
  </section>:<section className="panel"><div className="empty"><Table2 size={28}/><p>{p.busy?'Строим сводный отчёт…':'Выберите представление и постройте отчёт.'}</p></div></section>}
 </div>
}

function DimensionSelect({title,dimensions,groups,names,selected,canAdd,onChange}:{title:string;dimensions:string[];groups:DimensionGroups;names:DimensionNames;selected:string[];canAdd:boolean;onChange:(v:string[])=>void}){
 return <div><label>{title}<select disabled={!canAdd} aria-label={title+' сводной'} value="" onChange={e=>{if(e.target.value)onChange([...selected,e.target.value])}}><option value="">Добавить измерение…</option>{dimensionOptions(dimensions.filter(d=>!selected.includes(d)),groups,names,true)}</select></label><div className="dimension-chips">{selected.map((d,i)=><span key={d} title={label(d,names)}>{d}<button title={'Сдвинуть '+d+' влево'} disabled={i===0} onClick={()=>{const v=[...selected];[v[i-1],v[i]]=[v[i],v[i-1]];onChange(v)}}><ChevronLeft size={12}/></button><button title={'Убрать '+d} onClick={()=>onChange(selected.filter(v=>v!==d))}><X size={12}/></button></span>)}</div></div>
}

function ReportTable({data,names,onSelect}:{data:ReportData;names:DimensionNames;onSelect:(c:PivotCell)=>void}){
 const rows=data.layoutRows,columns=data.layoutColumns;
 const tuple=(c:PivotCell,dims:string[])=>dims.map(d=>c.dimensions[d]);
 const key=(c:PivotCell,dims:string[])=>stringify(tuple(c,dims));
 const rowKeys=Array.from(new Set(data.cells.map(c=>key(c,rows))));
 const rowValues=rowKeys.map(k=>JSON.parse(k) as unknown[]);
 const standard=stringify(columns)===stringify(['DIFF_FLAG','SOURCE']);
 const hierarchy=standard&&stringify(rows)===stringify(['PREFIX','CLASS','SUFFIX','ARRAY_KEY','KEY','VALUE_ADJUSTED']);
 const colValues:unknown[][]=standard?[[0,'BEFORE'],[0,'AFTER'],[1,'BEFORE'],[1,'AFTER']]:Array.from(new Set((data.column_totals||data.cells).map(c=>key(c,columns)))).map(k=>JSON.parse(k));
 if(!colValues.length)colValues.push([]);
 const lookup=new Map(data.cells.map(c=>[key(c,rows)+'|'+key(c,columns),c]));
 const totals=new Map((data.column_totals||[]).map(c=>[key(c,columns),c]));
 const levels=Math.max(1,columns.length);
 const samePrefix=(a:unknown[],b:unknown[],length:number)=>stringify(a.slice(0,length))===stringify(b.slice(0,length));
 function spanAt(values:unknown[][],index:number,depth:number){let n=1;while(index+n<values.length&&samePrefix(values[index],values[index+n],depth+1))n++;return n}
 function columnClass(values:unknown[]){const diff=values[columns.indexOf('DIFF_FLAG')];return diff===1?'changed-column':diff===0?'stable-column':''}
 function headerValue(d:string,v:unknown){if(d==='DIFF_FLAG')return <><b>{v===1?'Есть изменения':'Без изменений'}</b><small>DIFF_FLAG = {String(v)}</small></>;if(d==='SOURCE')return <><b>{String(v)}</b><small>{v==='BEFORE'?'MASTER':v==='AFTER'?'BETA':''}</small></>;return <><b>{shown(v)}</b><small>{label(d,names)}</small></>}
 function countButton(cell:PivotCell|undefined){return cell&&cell.count>0?<button onClick={()=>onSelect(cell)} title="Открыть уникальные заявки"><span>{number(cell.count)}</span><ArrowDownRight size={12} aria-hidden="true"/></button>:<span className="report-dash" title="Нет наблюдений в текущей выборке">—</span>}
 return <div className="report-table-scroll table-wrap"><table className={'pivot-table report-table '+(standard?'standard-comparison ':'')+(hierarchy?'hierarchy-comparison':'')}>{hierarchy&&<colgroup>{[11,10,10,13,9,15,8,8,8,8].map((width,i)=><col key={i} style={{width:width+'%'}}/>)}</colgroup>}<thead>{Array.from({length:levels},(_,level)=><tr key={level}>{level===0&&(rows.length?rows.map(d=><th key={d} rowSpan={levels} className={'dimension-header dimension-'+d} title={label(d,names)}><span>{d}</span><small>{label(d,names)}</small></th>):<th rowSpan={levels} className="dimension-header">Выборка</th>)}{colValues.map((values,i)=>{if(i>0&&samePrefix(values,colValues[i-1],level+1))return null;return <th key={i} colSpan={spanAt(colValues,i,level)} className={'column-heading '+columnClass(values)} scope="colgroup">{columns.length?headerValue(columns[level],values[level]):'Уникальных заявок'}</th>})}</tr>)}</thead>
 <tbody>{rowKeys.map((rk,i)=><tr key={rk} className={i===0||!samePrefix(rowValues[i],rowValues[i-1],Math.max(1,rows.length-1))?'attribute-start':''}>{rows.length?rowValues[i].map((v,depth)=>{if(depth<rows.length-1&&i>0&&samePrefix(rowValues[i],rowValues[i-1],depth+1))return null;return <td key={depth} rowSpan={depth<rows.length-1?spanAt(rowValues,i,depth):1} className={'report-dimension '+(depth===rows.length-1?'leaf-value':'')} title={v===''?'Пустое значение. Присутствие и тип поля доступны в деталях.':String(v)}>{shown(v)}</td>}):<td>Все атрибуты</td>}{colValues.map((values,j)=><td className={'numeric '+columnClass(values)} key={j}>{countButton(lookup.get(rk+'|'+stringify(values)))}</td>)}</tr>)}</tbody>
 {data.column_totals&&<tfoot><tr><th colSpan={Math.max(1,rows.length)} scope="row">Уникальных заявок хотя бы в одной строке<small>Не сумма значений атрибутов</small></th>{colValues.map((v,i)=><td key={i} className={'numeric '+columnClass(v)}>{countButton(totals.get(stringify(v)))}</td>)}</tr></tfoot>}
 </table></div>
}
