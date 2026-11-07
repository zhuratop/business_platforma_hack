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
 await expect(page.locator('#statistics .metric')).toHaveCount(3);
 await expect(page.locator('.family-table')).toHaveCount(2);
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
 await expect(page.locator('.strategy-table thead th[colspan="2"]')).toHaveCount(2);
 await expect(page.locator('body')).not.toContainText('Оценка готовности стратегии');
 await expect(page.locator('pre')).toHaveCount(0);
 await expect(page.locator('.family-table').first()).toContainText('KUPI_KUPI');
 const pivot=await context.request.post('/api/runs/'+run+'/pivot',{data:{rows:['PREFIX','CLASS','SUFFIX','ARRAY_KEY','KEY','VALUE_ADJUSTED'],columns:['DIFF_FLAG','SOURCE'],filters:{PATH:['decisionResult.decision','decisionResult.product_trials.decision','decisionResult.product_trials.rules.hit','decisionResult.product_trials.scoring.pd.modelName','decisionResult.product_trials.scoring.pd.value','decisionResult.product_trials.cutOff.name','decisionResult.product_trials.cutOff.value']},page:1,page_size:200,include_totals:true}});
 expect(pivot.ok()).toBeTruthy();
 const data=(await pivot.json()).data;
 await expect(page.locator('.strategy-table tbody tr')).toHaveCount(data.pagination.total_rows);
 const matrix=await page.locator('.strategy-table tbody tr').evaluateAll(rows=>rows.map(r=>Array.from(r.querySelectorAll('td')).map(c=>c.textContent)));
 for(const cell of data.cells){
  const key=['PREFIX','CLASS','SUFFIX','ARRAY_KEY','KEY','VALUE_ADJUSTED'].map(k=>cell.dimensions[k]===''||cell.dimensions[k]==null?'∅':String(cell.dimensions[k]));
  const row=matrix.find(r=>r.slice(0,6).every((v,i)=>v===key[i]));
  expect(row).toBeTruthy();
  const offset=6+Number(cell.dimensions.DIFF_FLAG)*2+(cell.dimensions.SOURCE==='AFTER'?1:0);
  expect(row![offset]).toBe(String(cell.count));
 }
 await page.screenshot({path:'../runtime/report-preview.png',fullPage:true});
 await page.emulateMedia({media:'print'});
 expect(await page.locator('.pivot-scroll').evaluate(e=>getComputedStyle(e).maxHeight)).toBe('none');
});
