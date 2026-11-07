export function percentNumber(value:unknown):number|null{
 return typeof value==='number'&&Number.isFinite(value)?Number((value*100).toFixed(1)):null;
}
export function percent(value:unknown):string{
 const n=percentNumber(value);return n===null?'—':n.toFixed(1)+'%';
}
export function rangeFilter(minimum:string,maximum:string):{valid:boolean;matches:(value:number|null)=>boolean}{
 function bound(text:string){
  const value=text.trim().replaceAll('%','').replaceAll(',','.').replace(/\s/g,'');
  if(!value)return null;
  return /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/.test(value)&&Number.isFinite(Number(value))?Number(value):NaN;
 }
 const low=bound(minimum),high=bound(maximum);
 if(low===null&&high===null)return {valid:true,matches:()=>true};
 const valid=(low===null||Number.isFinite(low))&&(high===null||Number.isFinite(high))&&(low===null||high===null||low<=high);
 return {valid,matches:value=>valid&&value!==null&&(low===null||value>=low)&&(high===null||value<=high)};
}
