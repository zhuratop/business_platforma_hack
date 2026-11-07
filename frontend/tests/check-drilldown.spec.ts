import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('check title opens its application sample and BEFORE/AFTER details',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const data=(await (await context.request.get('/api/runs/'+run+'/checks')).json()).data;
 const row=data.rows.find((r:any)=>r.check_id==='ar_drop_by_product'&&r.APP_IDS.length>0&&r.CNT>r.APP_IDS.length);
 expect(row).toBeTruthy();
 await page.goto('/?run='+run+'&tab=checks');
 await page.getByRole('button',{name:`Заявки проверки: ${row.LABEL}; ${row.ARGUMENT}; ${row.SOURCE}`,exact:true}).click();
 const drawer=page.locator('.drawer');
 await expect(drawer).toContainText(row.LABEL);
 await expect(drawer).toContainText(row.ARGUMENT);
 await expect(drawer).toContainText('это не полный список');
 await expect(drawer.locator('.app-list button')).toHaveCount(new Set(row.APP_IDS).size);
 const id=row.APP_IDS[0];
 const details=(await (await context.request.get('/api/runs/'+run+'/apps/'+id)).json()).data;
 await drawer.locator('.app-list button').filter({hasText:id}).click();
 const modal=page.locator('.detail-modal');
 await expect(modal.getByRole('heading',{name:id,exact:true})).toBeVisible();
 await expect(modal.getByRole('columnheader',{name:'BEFORE',exact:true})).toBeVisible();
 await expect(modal.getByRole('columnheader',{name:'AFTER',exact:true})).toBeVisible();
 const decision=modal.locator('tbody tr').filter({hasText:'decisionResult.decision'});
 const expected=details.rows.find((r:any)=>r.PATH==='decisionResult.decision');
 await expect(decision.locator('td').nth(1)).toContainText(expected.VALUE_BEFORE);
 await expect(decision.locator('td').nth(2)).toContainText(expected.VALUE_AFTER);
 await modal.getByRole('button',{name:'К списку заявок проверки'}).click();
 await expect(drawer).toBeVisible();
 await drawer.getByRole('button',{name:'Закрыть заявки'}).click();
 // Empty results are still clickable and must not open an unrelated application.
 const empty={...row,APP_IDS:[],CNT:0,LABEL:'Проверка без заявок'};
 await page.route('**/api/runs/'+run+'/checks',route=>route.fulfill({json:{data:{rows:[empty],executions:[]}}}));
 await page.reload();
 await page.getByRole('button',{name:`Заявки проверки: ${empty.LABEL}; ${empty.ARGUMENT}; ${empty.SOURCE}`,exact:true}).click();
 await expect(drawer).toContainText('В этой строке проверки нет затронутых заявок.');
 await expect(drawer.locator('.app-list button')).toHaveCount(0);
});
