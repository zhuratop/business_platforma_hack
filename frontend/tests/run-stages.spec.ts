import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('two users, staged start, saved preview and completion through UI',async({page,context,browser})=>{
 test.setTimeout(45000);
 const bob=await browser.newContext();
 try{
  const clients=[context.request,bob.request];
  const objects:any[]=[];
  for(const [i,client] of clients.entries()){
   expect((await client.post('/api/auth/login',{data:{username:i?'bob':'alice',password:'demo'}})).ok()).toBeTruthy();
   const bootstrap=(await (await client.get('/api/bootstrap')).json()).data;
   const ds=(await (await client.post('/api/datasets/upload',{multipart:{file:{name:'small.zip',mimeType:'application/zip',buffer:fs.readFileSync('../runtime/qa-stages-small.zip')}}})).json()).data;
   const cfg=bootstrap.configs[0];cfg.params.stats.bootstrap=100;
   await client.post('/api/configs',{data:cfg});objects.push({ds,cfg});
  }
  const other=(await (await bob.request.post('/api/runs',{data:{dataset_id:objects[1].ds.id,config_id:objects[1].cfg.id,stop_after:'READING'}})).json()).data;
  await page.goto('/?tab=config');
  await page.getByRole('combobox',{name:'Выполнить до этапа',exact:true}).selectOption('READING');
  await page.getByRole('button',{name:'Сохранить и запустить',exact:true}).click();
  await expect(page.locator('.run-stages')).toContainText('Сохранён, ожидает продолжения',{timeout:15000});
  const run=new URL(page.url()).searchParams.get('run')!;
  expect(run).toBeTruthy();
  await expect(page.locator('.stage-preview')).toContainText('4 строк');
  await expect(page.locator('.stage-track .complete')).toHaveCount(1);
  expect((await bob.request.get('/api/runs/'+run)).status()).toBe(404);
  expect((await context.request.post('/api/runs/'+other.id+'/resume',{data:{}})).status()).toBe(404);
  await page.getByRole('combobox',{name:'Выполнить до этапа',exact:true}).selectOption('NORMALIZING');
  await page.getByRole('button',{name:'Продолжить прогон',exact:true}).click();
  await expect(page.locator('.stage-track .complete')).toHaveCount(2,{timeout:15000});
  await expect(page.getByRole('combobox',{name:'Выполнить до этапа',exact:true})).toHaveValue('REPORTING');
  await page.getByRole('combobox',{name:'Таблица сохранённого этапа',exact:true}).selectOption('normalized_union');
  await expect(page.locator('.stage-preview table')).toContainText('APP_ID');
  await expect(page.locator('.stage-preview table')).toContainText('VALUE_KIND');
  await page.screenshot({path:'../runtime/staged-run-preview.png',fullPage:true});
  await page.getByRole('combobox',{name:'Выполнить до этапа',exact:true}).selectOption('REPORTING');
  await page.getByRole('button',{name:'Продолжить прогон',exact:true}).click();
  await expect(page.locator('.stage-track .complete')).toHaveCount(7,{timeout:15000});
  await expect(page.getByRole('link',{name:'HTML-отчёт',exact:true})).toBeVisible();
  expect((await context.request.get('/api/runs/'+run+'/report.html')).ok()).toBeTruthy();
 }finally{await bob.close()}
});

test('next target stays valid after the selected stage completes',async({page,context})=>{
 test.setTimeout(15000);
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const boot=(await (await context.request.get('/api/bootstrap')).json()).data;
 const original=boot.runs[0];expect(original).toBeTruthy();
 let completed='READING';
 const point=(stage:string)=>({stage,label:stage,seconds:1,completed_at:new Date().toISOString(),counts:{raw_inputs:4}});
 await page.route('**/api/runs/'+original.id,route=>route.fulfill({json:{status:'ok',data:{...original,status:'PAUSED',completed_stage:completed,checkpoints:completed==='READING'?[point('READING')]:[point('READING'),point('NORMALIZING')]}}}));
 await page.route('**/api/runs/'+original.id+'/preview?*',route=>route.fulfill({json:{status:'ok',data:{table:'raw_inputs',tables:['raw_inputs'],total:4,rows:[]}}}));
 await page.goto('/?tab=journal&run='+original.id);
 const select=page.getByRole('combobox',{name:'Выполнить до этапа',exact:true});
 await select.selectOption('NORMALIZING');
 completed='NORMALIZING';
 await expect(page.locator('.stage-track .complete')).toHaveCount(2);
 await expect(select).toHaveValue('REPORTING');
});
