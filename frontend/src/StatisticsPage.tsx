import {formatNumber,formatP,formatPercent,formatPoints,formatInterval} from './statFormat';
import './statistics.css';
import {StatisticsCharts} from './StatisticsCharts';

const count=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ru-RU',{maximumFractionDigits:4}):'—';
type FamilyRow={group:string;group_name?:string;name_available?:boolean;n:number;before:number;after:number;
 delta:number|null;ci:number[]|null;p:number;p_adjusted:number;information:string;coverage?:Record<string,number>;appeared?:number;disappeared?:number};
export function StatisticsPage({stats,runId}:{stats:any;runId:string}){
 const confidence=formatNumber((1-(stats.alpha??0.05))*100);
 return <div className="statistics-page"><section className="panel"><div className="panel-heading"><h2>Парное сравнение заявок</h2><span className="tag">ДОВЕРИТЕЛЬНЫЙ ИНТЕРВАЛ {confidence}%</span></div><p className="muted">{stats.interpretation}</p>
 <div className="stat-grid"><StatCard title="Одобрение заявок" stat={stats.app_approval_rate} percentage confidence={confidence}/><StatCard title="Одобрено продуктов на заявку" stat={stats.approved_products} percentage={false} confidence={confidence}/><StatCard title="Вероятность одобрения" stat={stats.target_score} percentage confidence={confidence}/></div>
 <div className="bureau-grid">{(['score_equ','score_okb'] as const).map(field=><BureauCard key={field} field={field} stat={stats.bureau_scores?.[field]}/>)}</div>
 <p className="statistics-units">Скоры Эквифакс и ОКБ и их изменения — в баллах соответствующего бюро. Чем выше скор, тем выше благонадёжность по оценке этого бюро. T-тест сравнивает средние всех одобренных в каждом срезе, учитывая общие APP_ID; p-value скорректированы по Холму для двух скоров. Разница может отражать отбор и изменение входных данных; значимость не доказывает причинность. Нулевой скор учитывается; отсутствие значения не заменяется нулём.</p>
 <p className="statistics-units">Для долей и вероятности: BEFORE и AFTER — в процентах; изменение AFTER − BEFORE и его CI — в процентных пунктах (п.п.). Например: 50% → 40% означает −10 п.п. Уровень доверия CI — в процентах. Вероятность сравнивается на сопоставимых продуктах с одинаковым названием и типом модели. Для количества продуктов на заявку сохранена единица «продукта / заявку».</p>
 <details className="statistics-method"><summary>Как рассчитана статистика</summary><p>Парный bootstrap по APP_ID: {count(stats.bootstrap)} повторений, seed {stats.seed}, α = {formatNumber(stats.alpha)}. Для бинарных исходов — точный тест Мак-Немара; для семейств — поправка Холма. Отсутствие значимости не доказывает сохранение метрики.</p></details></section>
 <StatisticsCharts runId={runId} stats={stats}/>
 <section className="panel"><div className="panel-heading"><h2>Сравнение по продуктам (компаниям)</h2><span className="tag">ПАРНЫЕ НАБЛЮДЕНИЯ</span></div><p className="muted">Продукт (компания) сравнивается на заявках, где продукт присутствует в обоих срезах. Поправка Холма применяется внутри заранее заданного семейства продуктов.</p>
 <FamilyTable rows={stats.families?.products||[]} confidence={confidence}/>
 <p className="hint">Названия взяты из ответов этого прогона. Если название отсутствует, показан идентификатор с пояснением. p-value округляется максимум до четырёх знаков; очень малые значения сохраняются в научной записи. Подгруппы служат диагностике и не разрешают выпуск стратегии автоматически.</p></section>
 <p className="muted statistics-availability">Риск дефолта, лимиты и денежный эффект недоступны без дополнительных данных.</p></div>
}

function StatCard({title,stat,percentage,confidence}:{title:string;stat:any;percentage:boolean;confidence:string}){
 const baseline=percentage?(stat.baseline||{}):stat;
 const delta=percentage?formatPoints(stat.delta,true):formatNumber(stat.delta);
 return <div className="stat"><h3>{title}</h3><b className={stat.delta<0?'stat-negative':''}>{delta}</b><span className="stat-unit">{percentage?' изменение AFTER − BEFORE':' продукта / заявку'}</span>
 <p className="stat-ci">CI {confidence}%: <strong>{formatInterval(stat.ci,percentage)}</strong></p>
 {typeof baseline.before==='number'&&typeof baseline.after==='number'&&<div className="stat-before-after"><span>BEFORE <b>{percentage?formatPercent(baseline.before):count(baseline.before)}</b></span><span>→</span><span>AFTER <b>{percentage?formatPercent(baseline.after):count(baseline.after)}</b></span></div>}
 <small>Пар заявок: {count(stat.n)}{stat.p!==undefined&&<> · p = <span title={String(stat.p)}>{formatP(stat.p)}</span></>}<br/>{stat.lost!==undefined&&<>Потеряно одобрений: {count(stat.lost)} · новых: {count(stat.gained)}</>}{stat.information==='insufficient'&&<span className="stat-insufficient">Недостаточно информации для вывода</span>}</small></div>
}

function BureauCard({field,stat}:{field:'score_equ'|'score_okb';stat:any}){
 const title=field==='score_equ'?'Средний скор Эквифакс у одобренных':'Средний скор ОКБ у одобренных';
 const score=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ru-RU',{maximumFractionDigits:1}):'недоступно';
 const signed=(v:unknown)=>typeof v==='number'?(v>0?'+':'')+score(v):'недоступно';
 const test=stat?.t_test;
 const reasons:Record<string,string>={too_few_scores:'недостаточно числовых скоров',too_few_common_scores:'недостаточно общих наблюдений',constant_common_scores:'нет разброса общих наблюдений',zero_variance:'нулевая дисперсия',invalid_score:'некорректные значения'};
 return <article className="bureau-card" data-bureau={field}><h3>{title}</h3><small className="bureau-field">{field}</small>
 <div className="bureau-means">{(['before','after'] as const).map(source=><div key={source}><span>{source.toUpperCase()}</span><b>{score(stat?.[source]?.mean)}</b><small>{count(stat?.[source]?.n)} / {count(stat?.[source]?.approved_total)} одобренных со скором</small>{!!stat?.[source]?.missing&&<small>Без числового скора: {count(stat[source].missing)}</small>}</div>)}</div>
 <p className="bureau-population-delta">Разница средних одобренных: <b>{signed(stat?.delta)}{stat?.delta!=null?' балла':''}</b></p>
 <div className="bureau-significance"><b>T-тест: {test?.status==='available'?(test.significant?'различие статистически значимо':'статистическая значимость не выявлена'):'недоступно'}</b>{test?.status==='available'?<span title={'p без поправки: '+formatP(test.p)}>p-value (Холм) = {formatP(test.p_adjusted)} · α = {formatNumber(test.alpha)}</span>:<span>{reasons[test?.reason]||'нет данных для теста'}</span>}</div>
 </article>;
}

function FamilyTable({rows,confidence}:{rows:FamilyRow[];confidence:string}){
 return <div className="stats-family">{rows.length?<div className="table-wrap"><table className="stats-family-table"><thead><tr><th>Продукт (компания)</th><th title="Парные заявки, пригодные для сравнения">Пар заявок</th><th>Одобрено BEFORE, %</th><th>Одобрено AFTER, %</th><th title="Абсолютное изменение доли AFTER − BEFORE в процентных пунктах">Разница, п.п.</th><th>CI {confidence}%, п.п.</th><th>p-value</th><th>p с поправкой Холма</th><th>Данные</th></tr></thead><tbody>{rows.map(r=><tr key={r.group}><td className="stats-group-name" title={'ID: '+r.group}><b>{r.group_name||'Продукт (компания) '+r.group}</b>{r.name_available===false&&<small>Название отсутствует в данных</small>}{r.coverage&&<small>Присутствует в срезах: {count(r.coverage.BEFORE||0)} → {count(r.coverage.AFTER||0)}</small>}{!!((r.appeared||0)+(r.disappeared||0))&&<small>Появились: {count(r.appeared||0)} · исчезли: {count(r.disappeared||0)}</small>}</td><td>{count(r.n)}</td><td>{r.n?formatPercent(r.before/r.n):'—'}<small>{count(r.before)} / {count(r.n)}</small></td><td>{r.n?formatPercent(r.after/r.n):'—'}<small>{count(r.after)} / {count(r.n)}</small></td><td className={'stats-delta '+(r.delta!=null&&r.delta<0?'negative':'')}>{formatPoints(r.delta,true)}</td><td className="stats-ci">{formatInterval(r.ci)}</td><td title={String(r.p)}>{r.n?formatP(r.p):'—'}</td><td title={String(r.p_adjusted)}>{r.n?formatP(r.p_adjusted):'—'}</td><td><span className={'badge '+(r.information==='insufficient'?'':'success')}>{r.information==='insufficient'?'Недостаточно':'Достаточно'}</span></td></tr>)}</tbody></table></div>:<p className="muted">Группы не заданы в конфигурации.</p>}</div>
}
