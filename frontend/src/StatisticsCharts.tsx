import {useEffect,useState} from 'react';
import type {ReactNode} from 'react';
import {api} from './api';
import {formatNumber,formatPercent,formatPoints,formatInterval} from './statFormat';
import './statisticsCharts.css';

type Transition={before:string|null;after:string|null;count:number;share:number|null};
type Bin={lower:number;upper:number;before:number;after:number;before_share:number|null;after_share:number|null};
type Charts={total_apps:number;transitions:Transition[];approvals:{lost:number;gained:number;net:number};
 probability:{n:number;total_apps:number;no_matched_score:number;invalid_score:number;bins:Bin[];mean_before:number|null;mean_after:number|null}};
type Family={group:string;group_name?:string;name_available?:boolean;n:number;before:number;after:number;delta:number|null;ci:number[]|null;information:string};
const BEFORE='#6884a6',AFTER='#538461';
const count=(v:number)=>v.toLocaleString('ru-RU');
const pct=(v:number|null)=>v==null?'недоступно':(v*100).toLocaleString('ru-RU',{maximumFractionDigits:1})+'%';
const pp=(v:number|null)=>v==null?'недоступно':(v>0?'+':'')+(v*100).toLocaleString('ru-RU',{maximumFractionDigits:1})+' п.п.';
const decision=(v:string|null)=>v==null?'Нет решения':({APPROVE:'Одобрено',REJECT:'Отказ',VERIFICATION:'Проверка'} as Record<string,string>)[v]||v;
const order=(v:string|null)=>v==='APPROVE'?0:v==='REJECT'?1:v==='VERIFICATION'?2:3;
const exactShare=(n:number,total:number)=>`${count(n)} / ${count(total)} заявок · ${total?formatPercent(n/total):'недоступно'}`;

function Legend(){return <div className="chart-legend"><span><i style={{background:BEFORE}}/>BEFORE (MASTER)</span><span><i style={{background:AFTER}}/>AFTER (BETA)</span></div>}
function Tip({text}:{text:string}){return <div className="chart-tip" role="status">{text||'Наведите указатель или перейдите к элементу клавишей Tab — появятся точные значения.'}</div>}
function Mark({label,setTip,children}:{label:string;setTip:(v:string)=>void;children:ReactNode}){
 return <g className="chart-mark" tabIndex={0} role="img" aria-label={label} onMouseEnter={()=>setTip(label)} onFocus={()=>setTip(label)}><title>{label}</title>{children}</g>;
}

export function StatisticsCharts({runId,stats}:{runId:string;stats:any}){
 const [result,setResult]=useState<{runId:string;data?:Charts;error?:string}|null>(null);
 const [retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;setResult(null);api<Charts>('/runs/'+encodeURIComponent(runId)+'/stats/charts').then(data=>{if(active)setResult({runId,data})}).catch(e=>{if(active)setResult({runId,error:String(e.message||e)})});return()=>{active=false}},[runId,retry]);
 const current=result?.runId===runId?result:null;
 if(!current)return <section className="panel statistics-charts" aria-busy="true"><h2>Сравнение стратегий на графиках</h2><p className="chart-state" role="status">Загружаем парные наблюдения…</p></section>;
 if(current.error)return <section className="panel statistics-charts"><h2>Сравнение стратегий на графиках</h2><p role="alert">Не удалось загрузить графики: {current.error}</p><button className="secondary" onClick={()=>setRetry(v=>v+1)}>Повторить загрузку графиков</button></section>;
 const data=current.data!;
 return <div className="statistics-charts" aria-label="Графики статистики">
  <DecisionMatrix key={'decisions-'+runId} data={data}/>
  <FamilyComparison key={'families-'+runId} stats={stats}/>
  <ScoreDistribution key={'scores-'+runId} data={data.probability}/>
 </div>;
}

function DecisionMatrix({data}:{data:Charts}){
 const [tip,setTip]=useState('');
 const decisions=Array.from(new Set(data.transitions.flatMap(r=>[r.before,r.after]))).sort((a,b)=>order(a)-order(b)||String(a).localeCompare(String(b)));
 const max=Math.max(1,...data.transitions.map(r=>r.count));
 return <section className="panel chart-panel" data-chart="decisions"><div className="chart-heading"><div><h2>Как изменились итоговые решения</h2><p>Строки — BEFORE (MASTER), столбцы — AFTER (BETA). В ячейке: заявки и доля от всех {count(data.total_apps)} пар.</p></div><span className="tag">ЕДИНИЦА · ЗАЯВКА</span></div>
  {data.total_apps?<><div className="chart-scroll"><table className="decision-matrix"><caption>Матрица переходов итоговых решений BEFORE → AFTER</caption><thead><tr><th>BEFORE ↓ / AFTER →</th>{decisions.map(d=><th key={String(d)} scope="col">{decision(d)}<small>{d??'Отсутствует'}</small></th>)}<th scope="col">Всего BEFORE</th></tr></thead><tbody>{decisions.map(b=><tr key={String(b)}><th scope="row">{decision(b)}<small>{b??'Отсутствует'}</small></th>{decisions.map(a=>{
   const n=data.transitions.find(r=>r.before===b&&r.after===a)?.count||0;
   const label=`${decision(b)} → ${decision(a)}: ${exactShare(n,data.total_apps)}`;
   return <td key={String(a)} tabIndex={0} aria-label={label} title={label} className={'matrix-cell '+(a===b?'matrix-same':'matrix-changed')} style={{backgroundColor:n?(a===b?`rgba(83,132,97,${.08+.3*Math.sqrt(n/max)})`:`rgba(202,133,67,${.08+.3*Math.sqrt(n/max)})`):undefined}} onFocus={()=>setTip(label)} onMouseEnter={()=>setTip(label)}><b>{count(n)}</b><small>{pct(n/data.total_apps)}</small></td>;
  })}<td className="matrix-total">{count(data.transitions.filter(r=>r.before===b).reduce((s,r)=>s+r.count,0))}</td></tr>)}</tbody><tfoot><tr><th>Всего AFTER</th>{decisions.map(a=><td key={String(a)}>{count(data.transitions.filter(r=>r.after===a).reduce((s,r)=>s+r.count,0))}</td>)}<td>{count(data.total_apps)}</td></tr></tfoot></table></div><div className="decision-flow">
   <div className="flow-lost"><span>Потеряли одобрение</span><b>{count(data.approvals.lost)}</b><small>{pct(data.approvals.lost/data.total_apps)} всех пар · APPROVE → другое решение</small></div>
   <div className="flow-gained"><span>Получили одобрение</span><b>{count(data.approvals.gained)}</b><small>{pct(data.approvals.gained/data.total_apps)} всех пар · другое решение → APPROVE</small></div>
   <div><span>Баланс одобрений</span><b>{data.approvals.net>0?'+':''}{count(data.approvals.net)}</b><small>{pp(data.approvals.net/data.total_apps)} от всех пар</small></div>
  </div><Tip text={tip}/><p className="chart-note">Диагональ — решение сохранилось; оранжевые ячейки — решение изменилось. Каждая заявка входит ровно в одну ячейку. Потери и приобретения учитывают все переходы в APPROVE и из APPROVE.</p></>:<p className="chart-state">Нет парных заявок для матрицы решений.</p>}
 </section>;
}

function FamilyComparison({stats}:{stats:any}){
 const [tip,setTip]=useState('');
 const rows:Family[]=[...(stats.families?.products||[])].sort((a,b)=>Number(b.n>0)-Number(a.n>0)||Math.abs(b.delta??0)-Math.abs(a.delta??0)||(a.group_name||a.group).localeCompare(b.group_name||b.group));
 const confidence=formatNumber((1-(stats.alpha??.05))*100);
 const x=(v:number)=>16+v*568;
 return <section className="panel chart-panel" data-chart="families"><div className="chart-heading"><div><h2>Где сильнее изменились одобрения</h2><p>Продукт (компания): доля одобрений в сопоставимой парной группе. Знаменатель — число пар заявок в строке; группы могут пересекаться.</p></div><span className="tag">ПРОДУКТ (КОМПАНИЯ)</span></div><Legend/>
  {rows.length?<><div className="family-chart-axis"><span>По убыванию |изменения|</span><div className="family-axis-scale" aria-label="0-100%">{[0,25,50,75,100].map(t=><span key={t}>{t}%</span>)}</div></div><div className="family-chart-rows">{rows.map(row=>{
   const name=row.group_name||'Продукт (компания) '+row.group;
   const before=row.n?row.before/row.n:null,after=row.n?row.after/row.n:null;
   const label=`${name}. BEFORE: ${before==null?'недоступно':exactShare(row.before,row.n)}. AFTER: ${after==null?'недоступно':exactShare(row.after,row.n)}. Изменение: ${formatPoints(row.delta,true)}. CI ${confidence}%: ${formatInterval(row.ci)}. Пар: ${count(row.n)}.${row.information==='insufficient'?' Недостаточно информации для вывода.':''}`;
   return <div className="family-chart-row" key={row.group}><div className="family-chart-label"><b title={name}>{name}</b><span>{pp(row.delta)} · пар {count(row.n)}</span>{row.information==='insufficient'&&<small>Недостаточно данных</small>}{row.name_available===false&&<small>Название отсутствует в данных</small>}</div>{before!=null&&after!=null?<svg viewBox="0 0 600 48" aria-label={'Доли одобрения: '+name}>{[0,.25,.5,.75,1].map(t=><line key={t} x1={x(t)} x2={x(t)} y1={0} y2={48} className="chart-grid"/>)}<Mark label={label} setTip={setTip}><rect x={0} y={0} width={600} height={48} fill="transparent"/><line x1={x(before)} x2={x(after)} y1={24} y2={24} stroke="#b1bcac" strokeWidth={3}/><circle cx={x(before)} cy={24} r={7} fill={BEFORE} stroke="white" strokeWidth={2}/><circle cx={x(after)} cy={24} r={5} fill={AFTER} stroke="white" strokeWidth={1.5}/></Mark></svg>:<div className="chart-unavailable">Недоступно: нет сопоставимых пар</div>}</div>;
  })}</div><p className="chart-axis-label">Доля одобрений, % · общий масштаб 0–100%</p><Tip text={tip}/></>:<p className="chart-state">Нет групп в сохранённом семействе продуктов (компаний).</p>}
  <p className="chart-note">Продукт (компания): решение продуктовой попытки на заявках, где продукт есть в обоих срезах. Внутри группы заявка учитывается один раз. Группы отсортированы по абсолютной разнице в п.п. Нулевые и малые выборки показаны явно; точные значения и CI доступны в подсказке и таблице ниже.</p>
 </section>;
}

function ScoreDistribution({data}:{data:Charts['probability']}){
 const [tip,setTip]=useState('');
 const [active,setActive]=useState<{index:number;x:number;y:number}|null>(null);
 function showBin(index:number,element:SVGGElement,point?:{clientX:number;clientY:number}){
  const box=element.getBoundingClientRect();
  setActive({index,x:Math.max(8,Math.min(window.innerWidth-268,(point?.clientX??box.x+box.width/2)-130)),y:Math.max(8,(point?.clientY??box.top)-130)});
 }
 const max=Math.max(.1,...data.bins.flatMap(b=>[b.before_share||0,b.after_share||0]));
 const top=Math.min(1,Math.ceil(max*10)/10),left=58,width=760,height=225,bottom=270;
 const y=(v:number)=>bottom-v/top*height;
 return <section className="panel chart-panel" data-chart="probability"><div className="chart-heading"><div><h2>Как изменилась вероятность одобрения</h2><p>Распределение среднего скора заявки на сопоставимых продуктах. Одна и та же выборка: {count(data.n)} пар из {count(data.total_apps)}.</p></div><span className="tag">APPROVAL_PROBABILITY</span></div><Legend/>
  {data.n?<><div className="distribution-wrap"><svg className="distribution-chart" viewBox="0 0 850 342" role="group" aria-label="Распределение вероятности одобрения BEFORE и AFTER на парных заявках">
   <text x={left} y={18} className="axis-title">Доля от {count(data.n)} сопоставимых заявок, %</text>
   {[0,.25,.5,.75,1].map(t=><g key={t}><line x1={left} x2={left+width} y1={y(t*top)} y2={y(t*top)} className="chart-grid"/><text x={left-10} y={y(t*top)+4} textAnchor="end">{pct(t*top)}</text></g>)}
   {data.bins.map((bin,i)=>{const group=width/10,start=left+i*group;
    const label=`Вероятность ${formatPercent(bin.lower)}–${formatPercent(bin.upper)}${i===9?' (включая 100%)':' (верхняя граница не включена)'}. BEFORE (MASTER): ${exactShare(bin.before,data.n)}. AFTER (BETA): ${exactShare(bin.after,data.n)}.`;
    return <g key={i}><g className="chart-mark distribution-bin" tabIndex={0} role="img" aria-label={label} aria-describedby={active?.index===i?'probability-bin-tooltip':undefined}
     onMouseEnter={event=>{setTip(label);showBin(i,event.currentTarget,event)}} onMouseLeave={()=>setActive(null)}
     onFocus={event=>{setTip(label);showBin(i,event.currentTarget)}} onBlur={()=>setActive(null)} onKeyDown={event=>{if(event.key==='Escape')setActive(null)}}>
     <rect className="bin-hit-area" x={start+2} y={bottom-height} width={group-4} height={height} fill="transparent"/>
     {(['before','after'] as const).map((source,j)=>{const share=source==='before'?bin.before_share:bin.after_share;return <rect key={source} x={start+8+j*28} y={y(share||0)} width={25} height={bottom-y(share||0)} fill={source==='before'?BEFORE:AFTER} rx={2}/>})}
    </g><text x={start+group/2} y={bottom+22} textAnchor="middle">{i*10}–{(i+1)*10}</text></g>})}
   <text x={left+width/2} y={bottom+53} textAnchor="middle" className="axis-title">Средняя вероятность одобрения заявки, %</text>
  </svg>{active&&<div id="probability-bin-tooltip" role="tooltip" className="distribution-tooltip" style={{left:active.x,top:active.y}}><b>Вероятность {pct(data.bins[active.index].lower)}–{pct(data.bins[active.index].upper)}</b><div><i style={{background:BEFORE}}/>BEFORE (MASTER) <strong>{formatPercent(data.bins[active.index].before_share)}</strong></div><div><i style={{background:AFTER}}/>AFTER (BETA) <strong>{formatPercent(data.bins[active.index].after_share)}</strong></div><small>Заявок: {count(data.bins[active.index].before)} → {count(data.bins[active.index].after)} · пар {count(data.n)}</small></div>}</div><div className="distribution-summary"><span>Среднее BEFORE <b>{pct(data.mean_before)}</b></span><span>Среднее AFTER <b>{pct(data.mean_after)}</b></span><span>Изменение <b>{data.mean_before!=null&&data.mean_after!=null?pp(data.mean_after-data.mean_before):'недоступно'}</b></span></div><Tip text={tip}/></>:<p className="chart-state">Нет сопоставимых пар с вероятностью одобрения в диапазоне 0–100%.</p>}
  <p className="chart-note">Сопоставление по APP_ID, product_id, названию модели и типу APPROVAL_PROBABILITY. Сначала усредняем скоры сопоставимых продуктов внутри заявки, затем считаем заявки в общих интервалах [0; 10%), …, [90; 100%]. Поэтому несколько продуктов не увеличивают вес заявки. Без сопоставимого скора: {count(data.no_matched_score)} заявок; с некорректной вероятностью: {count(data.invalid_score)}. Это вероятность одобрения, не дефолта.</p>
 </section>;
}
