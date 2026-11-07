export function shortText(text:string,limit=90){
 const value=text.replace(/\s+/g,' ').trim();
 return value.length>limit?value.slice(0,limit-1).trimEnd()+'…':value;
}

export function shortArgument(text:string){
 const sides=text.split(/\s+(?:->|→)\s+/);
 if(sides.length===2){
  const groups=sides.map(side=>side.split(';').map(item=>item.trim()));
  if(groups.every(group=>group.length>0&&group.every(item=>/^\d+:.+$/.test(item)))){
   const models=groups.map(group=>[...new Set(group.map(item=>item.slice(item.indexOf(':')+1)))]);
   const products=new Set(groups.flat().map(item=>item.slice(0,item.indexOf(':'))));
   if(models.every(group=>group.length===1)){
    const n=products.size;
    const word=n%10===1&&n%100!==11?'продукт':n%10>=2&&n%10<=4&&!(n%100>=12&&n%100<=14)?'продукта':'продуктов';
    return `${shortText(models[0][0],36)} → ${shortText(models[1][0],36)} · ${n} ${word}`;
   }
  }
  return sides.map(side=>shortText(side,42)).join(' → ');
 }
 return shortText(text);
}
