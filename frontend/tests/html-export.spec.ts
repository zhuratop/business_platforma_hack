import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('download is limited to pivot/checks and offline HTML contains the full tree and checks',async({page,context})=>{
 test.setTimeout(60000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const checks=(await (await context.request.get('/api/runs/'+run+'/checks')).json()).data.rows;
 const roots=(await (await context.request.post('/api/runs/'+run+'/pivot/tree',{data:{}})).json()).data;
 await page.goto('/?run='+run+'&tab=journal');
 await expect(page.locator('.run-selector .badge')).toContainText('READY');
 for(const label of ['Журнал','Конфигурация','Python-процедуры','Датасеты']){
  await page.locator('.sidebar').getByRole('button',{name:label,exact:true}).click();
  await expect(page.getByRole('link',{name:'HTML-отчёт',exact:true})).toHaveCount(0);
 }
 for(const label of ['Автопроверки','Сводная таблица']){
  await page.locator('.sidebar').getByRole('button',{name:label,exact:true}).click();
  await expect(page.getByRole('link',{name:'HTML-отчёт',exact:true})).toBeVisible();
 }
 const downloadPromise=page.waitForEvent('download');
 await page.getByRole('link',{name:'HTML-отчёт',exact:true}).click();
 const download=await downloadPromise;
 expect(download.suggestedFilename()).toBe('spr-'+run+'.html');
 await download.saveAs('../runtime/export-pivot-checks.html');
 const html=fs.readFileSync('../runtime/export-pivot-checks.html','utf8');
 await page.route('**/*',route=>route.abort());
 await page.setContent(html);
 await expect(page.locator('#pivot h2')).toHaveText('Сводная таблица · все атрибуты');
 await expect(page.locator('#checks tbody tr')).toHaveCount(checks.length);
 await expect(page.locator('#statistics,#comparability,#families')).toHaveCount(0);
 const rootRows=page.locator('.attribute-table tbody tr[data-parent=""]');
 await expect(rootRows).toHaveCount(roots.nodes.length);
 for(const node of roots.nodes){
  const row=rootRows.filter({has:page.locator('[title="'+node.path+'"]')});
  await expect(row.locator('td')).toHaveText(['BEFORE_0','BEFORE_1','AFTER_0','AFTER_1','TOTAL'].map(s=>String(node.cells[s].count)));
 }
 const first=rootRows.first();
 await first.getByRole('button').click();
 await expect(first.getByRole('button')).toHaveAttribute('aria-expanded','true');
 const id=await first.getAttribute('data-id');
 const children=page.locator('.attribute-table tbody tr[data-parent="'+id+'"]');
 await expect(children.first()).toBeVisible();
 await first.getByRole('button').click();
 await expect(children.first()).toBeHidden();
 await expect(page.locator('.checks-table thead')).toContainText('Порог, %');
 await expect(page.locator('.checks-table thead')).toContainText('Разница в %');
 const check=checks.find((r:any)=>r.threshold?.value!=null);
 const checkRow=page.locator('.checks-table tbody tr').filter({hasText:check.LABEL}).filter({hasText:check.ARGUMENT}).first();
 await expect(checkRow.locator('td').nth(3)).toHaveText((check.threshold.value*100).toFixed(1)+'%');
 await expect(checkRow.locator('td').nth(4)).toHaveText((check.METRIC*100).toFixed(1)+'%');
});
