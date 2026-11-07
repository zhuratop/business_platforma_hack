import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('journal shows unique changed applications including changed decisions and handles zero',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const response=await context.request.get('/api/runs/'+run+'/summary');expect(response.ok()).toBeTruthy();
 const summary=(await response.json()).data;
 expect(summary.changed_apps).toBeGreaterThanOrEqual(summary.decision_changed);
 await page.goto('/?run='+run+'&tab=journal');
 const result=page.getByTestId('changed-apps-count');
 await expect(result).toHaveText(summary.changed_apps.toLocaleString('ru-RU')+' из '+summary.total_apps.toLocaleString('ru-RU'));
 await expect(page.locator('.run-changed-result')).toContainText('включая заявки со сменой решения');
 await page.route('**/api/runs/'+run+'/summary',async route=>{
  await route.fulfill({json:{data:{...summary,changed_apps:0}}});
 });
 await page.reload();
 await expect(result).toHaveText('0 из '+summary.total_apps.toLocaleString('ru-RU'));
});
