export function formatNumber(value:unknown):string{
 return typeof value==='number'&&Number.isFinite(value)?String(Number(value.toFixed(4))):'—';
}
export function formatP(value:unknown):string{
 if(typeof value!=='number'||!Number.isFinite(value))return '—';
 if(value>0&&value<0.0001){const [mantissa,exponent]=value.toExponential(3).split('e');return Number(mantissa)+'e'+exponent}
 return formatNumber(value);
}
export function formatPercent(value:unknown,signed=false):string{
 if(typeof value!=='number'||!Number.isFinite(value))return '—';
 const n=Number((value*100).toFixed(4));return (signed&&n>0?'+':'')+formatNumber(n)+'%';
}
export function formatPoints(value:unknown,signed=false):string{
 const percent=formatPercent(value,signed);
 return percent==='—'?'—':percent.slice(0,-1)+' п.п.';
}
export function formatInterval(ci:unknown,percentagePoints=true):string{
 if(!Array.isArray(ci)||ci.length!==2)return '—';
 return ci.map(x=>percentagePoints?formatPoints(x):formatNumber(x)).join(' … ');
}
