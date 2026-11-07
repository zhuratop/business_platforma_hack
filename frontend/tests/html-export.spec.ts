import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('downloaded HTML contains complete statistics and strategy table',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const response=await context.request.get('/api/runs/'+run+'/report.html?download=true');
 expect(response.ok()).toBeTruthy();
 expect(response.headers()['content-disposition']).toContain('attachment');
 const html=await response.text();
 await page.setContent(html);
 await expect(page.locator('#statistics .metric')).toHaveCount(5);
 await expect(page.locator('[data-bureau="score_equ"]')).toContainText('Средний скор Эквифакс у одобренных');
 await expect(page.locator('[data-bureau="score_okb"]')).toContainText('Средний скор ОКБ у одобренных');
 for(const field of ['score_equ','score_okb']){
  const card=page.locator('[data-bureau="'+field+'"]');
  await expect(card).toContainText('T-тест:');await expect(card).toContainText('p-value (Холм)');
  await expect(card).not.toContainText('Одобрены в обоих срезах');await expect(card).not.toContainText('Парное изменение');
 }
 await expect(page.locator('.family-table')).toHaveCount(1);
 await expect(page.locator('.family-table thead')).toContainText('Продукт (компания)');
 await expect(page.locator('#families')).not.toContainText('Партнёр');
 await expect(page.locator('#comparability .metric')).toHaveCount(1);
 await expect(page.locator('body')).not.toContainText('Целевая модель не менялась');
 await expect(page.locator('#statistics .metric').nth(2)).toContainText('Вероятность одобрения');
 const stats=(await (await context.request.get('/api/runs/'+run+'/stats')).json()).data;
 const cards=[page.locator('#statistics .metric').first(),page.locator('#statistics .metric').nth(2),page.locator('#comparability .metric')];
 for(const [i,row] of [stats.app_approval_rate,stats.target_score,stats.strata.external_unchanged].entries()){
  await expect(cards[i].locator('.delta')).toHaveText(Number((row.delta*100).toFixed(4))+' п.п.');
  await expect(cards[i].locator('strong')).toHaveText(row.ci.map((v:number)=>Number((v*100).toFixed(4))+' п.п.').join(' … '));
  await expect(cards[i].locator('.before-after')).toContainText(Number((row.baseline.before*100).toFixed(4))+'%');
 }
 await expect(page.locator('.family-table').first().locator('thead')).toContainText('Разница, п.п.');
 await expect(page.locator('.family-table').first().locator('thead')).toContainText('CI 95%, п.п.');
 await expect(page.locator('.family-table').first().locator('tbody tr').first().locator('td').nth(4)).toContainText('п.п.');
 await expect(page.locator('.family-table').first().locator('tbody tr').first().locator('td').nth(5)).toContainText('п.п.');
 await expect(page.locator('.strategy-table tbody tr')).not.toHaveCount(0);
 await expect(page.locator('.strategy-table thead')).toContainText('DIFF_FLAG = 1');
 await expect(page.locator('.strategy-table thead th[colspan="2"]')).toHaveCount(1);
 await expect(page.locator('body')).not.toContainText('Оценка готовности стратегии');
 await expect(page.locator('pre')).toHaveCount(0);
 await expect(page.locator('.family-table').first()).toContainText('KUPI_KUPI');
 const view=(await (await context.request.get('/api/bootstrap')).json()).data.pivot_views.find((v:any)=>v.id==='strategy');
 const pivot=await context.request.post('/api/runs/'+run+'/pivot',{data:{rows:view.rows,columns:view.columns,filters:view.filters,collapse_unchanged:true,page:1,page_size:250,include_totals:true}});
 expect(pivot.ok()).toBeTruthy();
 const data=(await pivot.json()).data;
 await expect(page.locator('.strategy-table tbody tr')).toHaveCount(data.pagination.total_rows);
 const matrix=await page.locator('.strategy-table tbody tr').evaluateAll(rows=>rows.map(r=>({path:r.getAttribute('data-path'),value:r.getAttribute('data-value'),counts:Array.from(r.querySelectorAll('td.num')).map(c=>c.textContent)})));
 for(const total of data.row_totals){
  const d=total.dimensions,row=matrix.find(r=>r.path===d.PATH&&r.value===d.VALUE_ADJUSTED);
  expect(row).toBeTruthy();
  const stable=data.unchanged_cells.find((c:any)=>c.dimensions.PATH===d.PATH&&c.dimensions.VALUE_ADJUSTED===d.VALUE_ADJUSTED);
  const changed=(source:string)=>data.cells.find((c:any)=>c.dimensions.PATH===d.PATH&&c.dimensions.VALUE_ADJUSTED===d.VALUE_ADJUSTED&&c.dimensions.DIFF_FLAG===1&&c.dimensions.SOURCE===source)?.count||0;
  expect(row!.counts).toEqual([stable.count,changed('BEFORE'),changed('AFTER'),total.count].map(n=>n?String(n):'—'));
 }
 await page.screenshot({path:'../runtime/report-preview.png',fullPage:true});
 await page.emulateMedia({media:'print'});
 expect(await page.locator('.pivot-scroll').evaluate(e=>getComputedStyle(e).maxHeight)).toBe('none');
});
