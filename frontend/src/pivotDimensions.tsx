export type DimensionGroups = Record<string,string[]>;
export type DimensionNames = Record<string,string>;

export function dimensionOptions(dimensions:string[],groups:DimensionGroups,names:DimensionNames,forAxes=false){
 const available=new Set(dimensions);
 const ordered=Object.entries(groups||{});
 if(!ordered.length)return dimensions.map(d=><option key={d} value={d}>{d}</option>);
 return ordered.filter(([group])=>!forAxes||group!=='Признаки для фильтрации').map(([group,fields])=>{
  const entries=fields.filter(d=>available.has(d));
  return entries.length?<optgroup key={group} label={group}>{entries.map(d=><option key={d} value={d}>{names?.[d]?`${names[d]} (${d})`:d}</option>)}</optgroup>:null;
 });
}
