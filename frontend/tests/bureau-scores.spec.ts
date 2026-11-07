import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('approved bureau means show t-test significance without the removed paired block',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const response=await context.request.get('/api/runs/'+run+'/stats');expect(response.ok()).toBeTruthy();
 const data=(await response.json()).data;
 await page.goto('/?run='+run+'&tab=overview');
 const score=(v:number)=>v.toLocaleString('ru-RU',{maximumFractionDigits:1});
 for(const field of ['score_equ','score_okb']){
  const row=data.bureau_scores[field],card=page.locator('[data-bureau="'+field+'"]');
  await expect(card).toBeVisible();
  await expect(card.locator('.bureau-means b')).toHaveText([score(row.before.mean),score(row.after.mean)]);
  await expect(card.locator('.bureau-population-delta')).toContainText(score(row.delta));
  await expect(card.locator('.bureau-population-delta')).not.toContainText('п.п.');
  await expect(card.locator('.bureau-paired')).toHaveCount(0);
  await expect(card).not.toContainText('Одобрены в обоих срезах');
  await expect(card).not.toContainText('Парное изменение');
  await expect(card).not.toContainText('CI 95%');
  await expect(card.locator('.bureau-significance')).toContainText('T-тест:');
  await expect(card.locator('.bureau-significance')).toContainText('p-value (Холм)');
  await expect(card.locator('.bureau-significance')).toContainText(row.t_test.significant?'различие статистически значимо':'статистическая значимость не выявлена');
 }
 await expect(page.locator('.stat-grid .stat')).toHaveCount(3);
});
