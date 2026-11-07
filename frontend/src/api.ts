import type {Envelope} from './types';
export async function api<T=any>(path:string,body?:unknown):Promise<T> {
  const response=await fetch('/api'+path,{credentials:'same-origin',headers:body instanceof FormData?{}:body===undefined?{}:{'Content-Type':'application/json'},method:body===undefined?'GET':'POST',body:body instanceof FormData?body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json() as Envelope<T>;
  if(!response.ok) throw new Error(result.error?.message||`Ошибка ${response.status}`);
  return result.data;
}

export function uploadWithProgress(path:string,body:FormData,onProgress:(percent:number)=>void):Promise<any>{
 return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api'+path);xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100))};xhr.onerror=()=>reject(new Error('Ошибка сети при загрузке'));xhr.onload=()=>{try{const result=JSON.parse(xhr.responseText);if(xhr.status>=200&&xhr.status<300)resolve(result.data);else reject(new Error(result.error?.message||'Ошибка загрузки'))}catch{reject(new Error('Некорректный ответ сервера'))}};xhr.send(body)});
}
