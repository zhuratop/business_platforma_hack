import {Fragment,useEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {ChevronDown,ChevronRight,ArrowDownRight,FolderTree} from 'lucide-react';
import type {PivotCell} from './types';
import {api} from './api';
import './attributeTree.css';

type Query={path:string;stage:'path'|'keys'|'values';array_key?:string|null};
type TreeNode={id:string;path:string;label:string;kind:'path'|'array'|'value';value_kind?:string;has_children:boolean;
 request:Query|null;cells:Record<'BEFORE'|'AFTER'|'TOTAL',PivotCell>};
type Data={nodes:TreeNode[];totals:Record<'BEFORE'|'AFTER'|'TOTAL',PivotCell>;pagination:{page:number;page_size:number;total_nodes:number;has_more:boolean}};
type State={loading:boolean;data?:Data;error?:string};
const ROOT='$root',rootQuery:Query={path:'',stage:'path'};
const number=(n:number)=>n.toLocaleString('ru-RU');
const types:Record<string,string>={null:'null',boolean:'boolean',number:'число / бакет',string:'строка'};

export function AttributeTree({runId,refresh,onCell}:{runId:string;refresh:number;onCell:(cell:PivotCell)=>void}){
 const [source,setSource]=useState(''),[diff,setDiff]=useState('');
 const [cache,setCache]=useState<Record<string,State>>({}),[opened,setOpened]=useState<Set<string>>(new Set());
 const generation=useRef(0);
 const filters={...(source?{SOURCE:[source]}:{}),...(diff!==''?{DIFF_FLAG:[Number(diff)]}:{})};
 async function load(id:string,query:Query,page=1,version=generation.current){
  setCache(old=>({...old,[id]:{...old[id],loading:true,error:undefined}}));
  try{
   const data=await api<Data>('/runs/'+encodeURIComponent(runId)+'/pivot/tree',{...query,filters,page,page_size:50});
   if(generation.current!==version)return;
   setCache(old=>({...old,[id]:{loading:false,data:{...data,nodes:page===1?data.nodes:[...(old[id]?.data?.nodes||[]),...data.nodes]}}}));
  }catch(e){if(generation.current===version)setCache(old=>({...old,[id]:{...old[id],loading:false,error:String((e as Error).message)}}))}
 }
 useEffect(()=>{
  const version=++generation.current;setCache({});setOpened(new Set());void load(ROOT,rootQuery,1,version);
  return()=>{generation.current++};
 },[runId,source,diff,refresh]);
 function toggle(node:TreeNode){
  if(opened.has(node.id)){
   const next=new Set(opened);
   function close(id:string){next.delete(id);for(const child of cache[id]?.data?.nodes||[])close(child.id)}
   close(node.id);setOpened(next);
  }else{
   setOpened(old=>new Set(old).add(node.id));
   if(node.request&&!cache[node.id]?.data&&!cache[node.id]?.loading)void load(node.id,node.request);
  }
 }
 const showBefore=source!=='AFTER',showAfter=source!=='BEFORE';
 const columns=2+Number(showBefore)+Number(showAfter),root=cache[ROOT];
 function cell(value:PivotCell){return <td className="tree-number">{value.count?<button onClick={()=>onCell(value)} title="Открыть уникальные заявки">{number(value.count)}<ArrowDownRight size={12}/></button>:<span className="tree-zero">—</span>}</td>}
 function status(id:string,query:Query,depth:number){
  const state=cache[id];if(!state)return null;
  return <>{state.loading&&<tr><td colSpan={columns} className="tree-load" style={{paddingLeft:20+depth*20}} role="status">Загружаем узлы…</td></tr>}
   {state.error&&<tr><td colSpan={columns} className="tree-load" role="alert">{state.error} <button className="link" onClick={()=>void load(id,query,state.data?.pagination.has_more?state.data.pagination.page+1:1)}>Повторить загрузку узла</button></td></tr>}
   {state.data?.pagination.has_more&&!state.loading&&!state.error&&<tr><td colSpan={columns} className="tree-more" style={{paddingLeft:20+depth*20}}><button className="link" onClick={()=>void load(id,query,state.data!.pagination.page+1)}>Показать ещё узлы · {number(state.data.nodes.length)} из {number(state.data.pagination.total_nodes)}</button></td></tr>}
  </>;
 }
 function renderNodes(nodes:TreeNode[],depth:number):ReactNode{
  return nodes.map(node=>{
  const expanded=opened.has(node.id),children=cache[node.id]?.data?.nodes||[];
  return <Fragment key={node.id}><tr data-path={node.path} data-kind={node.kind} className={node.kind==='value'?'tree-value-row':'tree-branch-row'}>
   <th scope="row" className="tree-name"><div style={{paddingLeft:depth*20}}>
    {node.has_children?<button className="tree-toggle" onClick={()=>toggle(node)} aria-expanded={expanded} aria-label={(expanded?'Свернуть ':'Раскрыть ')+node.label}>{expanded?<ChevronDown size={15}/>:<ChevronRight size={15}/>}<span title={node.kind==='array'?'Ключ массива: '+node.label:node.path}>{node.label}</span></button>:<span className="tree-leaf" title={node.path}>{node.label}</span>}
    {node.kind==='array'&&<small>ключ массива</small>}{node.kind==='value'&&<small>{types[node.value_kind||'']||node.value_kind}</small>}
   </div></th>{showBefore&&cell(node.cells.BEFORE)}{showAfter&&cell(node.cells.AFTER)}{cell(node.cells.TOTAL)}</tr>
   {expanded&&<>{renderNodes(children,depth+1)}{node.request&&status(node.id,node.request,depth+1)}</>}
  </Fragment>;
  });
 }
 return <section className="panel attribute-tree"><div className="tree-heading"><div><h2><FolderTree size={21}/> Все атрибуты · дерево JSON</h2><p>Раскрывайте пути → ключи массивов → значения. Каждая ячейка считает уникальные APP_ID, включая все скрытые дочерние узлы.</p></div><button className="secondary" onClick={()=>setOpened(new Set())} disabled={!opened.size}>Свернуть всё</button></div>
  <div className="tree-filters"><label>Срез<select aria-label="Дерево: срез" value={source} onChange={e=>setSource(e.target.value)}><option value="">BEFORE и AFTER</option><option value="BEFORE">BEFORE (MASTER)</option><option value="AFTER">AFTER (BETA)</option></select></label><label>DIFF_FLAG<select aria-label="Дерево: DIFF_FLAG" value={diff} onChange={e=>setDiff(e.target.value)}><option value="">Все значения</option><option value="0">0 — без изменений</option><option value="1">1 — есть изменения</option></select></label><span>Считаются заявки, не сумма атрибутов или продуктов.</span></div>
  <div className="tree-table-wrap"><table className="attribute-tree-table"><thead><tr><th>Атрибут / ключ / значение</th>{showBefore&&<th>BEFORE (MASTER)</th>}{showAfter&&<th>AFTER (BETA)</th>}<th>Уникальный итог</th></tr></thead><tbody>
   {renderNodes(root?.data?.nodes||[],0)}{status(ROOT,rootQuery,0)}
   {root?.data&&!root.loading&&!root.data.nodes.length&&<tr><td colSpan={columns} className="tree-empty">В выбранных фильтрах атрибутов нет.</td></tr>}
  </tbody>{root?.data&&<tfoot><tr><th>Заявок хотя бы с одним атрибутом<small>Объединение APP_ID, не сумма узлов</small></th>{showBefore&&cell(root.data.totals.BEFORE)}{showAfter&&cell(root.data.totals.AFTER)}{cell(root.data.totals.TOTAL)}</tr></tfoot>}</table></div>
  <p className="tree-explanation">Дерево строится по всем атрибутам сохранённой нормализации; исключённые при подготовке технические поля в неё не входят. null, false, пустая строка и строковые значения различаются. Исчезнувшие поля видны в BEFORE при DIFF_FLAG=1, новые — в AFTER. Различия считаются по исходным значениям, даже внутри одного бакета. Нажмите число для перехода к заявкам и атрибутам.</p>
 </section>;
}
