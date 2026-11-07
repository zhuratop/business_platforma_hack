import {test,expect} from '@playwright/test';
import fs from 'node:fs';

const run=()=>fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();

test('real charts preserve paired counts, show names and accessible precise tooltips',async({page,context,browser})=>{
 test.setTimeout(30000);
 const id=run();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const response=await context.request.get('/api/runs/'+id+'/stats/charts');expect(response.ok()).toBeTruthy();
 const data=(await response.json()).data;
 expect(data.transitions.reduce((s:number,r:any)=>s+r.count,0)).toBe(data.total_apps);
 expect(data.probability.bins.reduce((s:number,b:any)=>s+b.before,0)).toBe(data.probability.n);
 expect(data.probability.bins.reduce((s:number,b:any)=>s+b.after,0)).toBe(data.probability.n);
 const stats=(await (await context.request.get('/api/runs/'+id+'/stats')).json()).data;
 expect(data.approvals.lost).toBe(stats.app_approval_rate.lost);
 expect(data.approvals.gained).toBe(stats.app_approval_rate.gained);
 expect(data.probability.n).toBe(stats.target_score.n);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/?run='+id+'&tab=stats');
 await expect(page.locator('[data-chart]')).toHaveCount(3);
 const matrix=page.locator('[data-chart="decisions"]');
 await expect(matrix.locator('.flow-lost b')).toHaveText(data.approvals.lost.toLocaleString('ru-RU'));
 await matrix.locator('.matrix-cell').first().focus();await expect(matrix.locator('.chart-tip')).toContainText('заявок');
 const family=page.locator('[data-chart="families"]');
 await expect(family.locator('.family-chart-row')).toHaveCount(stats.families.products.length);
 await family.locator('.chart-mark').first().focus();await expect(family.locator('.chart-tip')).toContainText('CI 95%');
 await expect(family.locator('.chart-tip')).toContainText('п.п.');
 await expect(family.locator('.chart-tabs')).toHaveCount(0);
 await expect(family).toContainText('Продукт (компания)');
 for(const row of stats.families.products){await expect(family.getByText(row.group_name,{exact:true})).toBeVisible()}
 await expect(family.locator('.chart-unavailable')).toHaveCount(stats.families.products.filter((r:any)=>!r.n).length);
 const scores=page.locator('[data-chart="probability"]');
 const binIndex=data.probability.bins.findIndex((bin:any)=>bin.before>0);
 await scores.locator('.distribution-bin').nth(binIndex).hover();
 const tooltip=scores.getByRole('tooltip');
 await expect(tooltip).toBeVisible();
 await expect(tooltip).toContainText('BEFORE (MASTER)');await expect(tooltip).toContainText('AFTER (BETA)');
 const bin=data.probability.bins[binIndex];
 await expect(tooltip.locator('strong').nth(0)).toHaveText(Number((bin.before_share*100).toFixed(4))+'%');
 await expect(tooltip.locator('strong').nth(1)).toHaveText(Number((bin.after_share*100).toFixed(4))+'%');
 expect(await scores.locator('.distribution-bin').nth(binIndex).evaluate(e=>getComputedStyle(e).cursor)).toBe('default');
 expect(await family.locator('.chart-mark').first().evaluate(e=>getComputedStyle(e).cursor)).toBe('default');
 await scores.locator('.chart-mark').last().focus();await expect(scores.locator('.chart-tip')).toContainText('включая 100%');
 await expect(scores.locator('.chart-tip')).toContainText('AFTER (BETA)');
 await expect(page.locator('.statistics-page')).not.toContainText('Целевая модель не менялась');
 await matrix.screenshot({path:'../runtime/stat-charts-matrix.png'});
 await scores.screenshot({path:'../runtime/stat-charts-distribution.png'});
 await page.setViewportSize({width:420,height:900});
 await expect(scores).toBeVisible();
 expect(await scores.evaluate(e=>e.scrollWidth<=e.clientWidth+2)).toBeTruthy();
 await family.screenshot({path:'../runtime/stat-charts-mobile.png'});
 expect(errors).toEqual([]);
 const other=await browser.newContext();await other.request.post('/api/auth/login',{data:{username:'bob',password:'demo'}});
 expect((await other.request.get('/api/runs/'+id+'/stats/charts')).status()).toBe(404);await other.close();
});

test('charts handle loading, errors, retry and an empty run',async({page,context})=>{
 test.setTimeout(30000);
 const id=run();await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);let calls=0;
 await page.route('**/api/runs/'+id+'/stats/charts',async route=>{
  if(++calls===1){await gate;await route.fulfill({status:500,json:{error:{message:'Тестовая ошибка графиков'}}})}
  else await route.fulfill({json:{status:'ok',data:{total_apps:0,transitions:[],approvals:{lost:0,gained:0,net:0},probability:{n:0,total_apps:0,no_matched_score:0,invalid_score:0,bins:[],mean_before:null,mean_after:null}}}});
 });
 await page.goto('/?run='+id+'&tab=stats');
 await expect(page.getByText('Загружаем парные наблюдения…',{exact:true})).toBeVisible();release();
 await expect(page.getByRole('alert')).toContainText('Тестовая ошибка графиков');
 await page.getByRole('button',{name:'Повторить загрузку графиков'}).click();
 await expect(page.getByText('Нет парных заявок для матрицы решений.',{exact:true})).toBeVisible();
 await expect(page.getByText('Нет сопоставимых пар с вероятностью одобрения в диапазоне 0–100%.',{exact:true})).toBeVisible();
});
