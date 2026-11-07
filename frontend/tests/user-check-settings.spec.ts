import {test,expect} from '@playwright/test';

test('custom check passes within its visible threshold and duplicate copies cannot be selected',async({page,context})=>{
 test.setTimeout(30000);
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const boot=(await (await context.request.get('/api/bootstrap')).json()).data;
 const run=boot.runs.find((r:any)=>r.status==='READY');expect(run).toBeTruthy();
 const result=(await (await context.request.get('/api/runs/'+run.id+'/checks')).json()).data;
 const ar=result.rows.filter((r:any)=>r.check_id==='ar_drop_by_product');
 expect(ar.length).toBeGreaterThan(0);expect(ar.every((r:any)=>r.RESULT==='PASS'&&r.threshold.value===.3)).toBeTruthy();
 const attributes=result.rows.filter((r:any)=>r.check_id==='attribute_new_loss');
 expect(attributes.every((r:any)=>r.threshold.value===.1&&r.METRIC>=.1)).toBeTruthy();
 expect((await context.request.get('/api/checks/demo')).status()).toBe(404);
 await page.goto('/?run='+run.id+'&tab=checks');
 await expect(page.getByRole('button',{name:'Демонстрационный набор',exact:true})).toHaveCount(0);
 await expect(page.locator('.checks-mode-toggle')).toHaveCount(0);
 const row=page.locator('.checks-table tbody tr').filter({hasText:'Доля изменений в пределах порога'});
 await expect(row).toHaveCount(1);await expect(row).toContainText('PASS');await expect(row).toContainText('30.0%');
 await page.getByRole('button',{name:'Конфигурация',exact:true}).click();
 const duplicates=page.locator('.check-options label').filter({hasText:'Доля изменений в пределах порога'});
 expect(await duplicates.count()).toBeGreaterThan(1);
 await expect(duplicates.locator('input:checked')).toHaveCount(1);
 await expect(duplicates.locator('input:not(:checked):not(:disabled)')).toHaveCount(0);
 await expect(page.getByRole('textbox',{name:'Параметры конфигурации JSON'})).toHaveValue(/"max_share": 0.3/);
 await expect(page.getByRole('textbox',{name:'Параметры конфигурации JSON'})).toHaveValue(/"max_drop_rel": 0.3/);
 await expect(page.getByRole('textbox',{name:'Параметры конфигурации JSON'})).toHaveValue(/"min_share": 0.1/);
});
