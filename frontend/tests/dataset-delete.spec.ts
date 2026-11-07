import {test,expect} from '@playwright/test';

test('dataset removal supports cancel/confirm and cleans list and selection',async({page,context})=>{
 test.setTimeout(30000);
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const original=(await (await context.request.get('/api/bootstrap')).json()).data;
 const dataset={id:'delete-test',name:'Датасет для удаления',count:1,bytes:100,checksum:'test-checksum',created:new Date().toISOString()};
 let deleted=false,calls=0;
 await page.route('**/api/bootstrap',r=>r.fulfill({json:{status:'ok',data:{...original,datasets:deleted?[]:[dataset]}}}));
 await page.route('**/api/datasets/delete-test',route=>{
  expect(route.request().method()).toBe('DELETE');calls++;deleted=true;
  return route.fulfill({json:{status:'ok',data:{deleted:true}}});
 });
 await page.goto('/?tab=datasets');
 const panel=page.locator('section.panel').filter({has:page.getByRole('heading',{name:'Ваши датасеты',exact:true})});
 await expect(panel.locator('tbody tr')).toHaveCount(1);
 await expect(page.locator('main.content')).not.toContainText('Разрешённый корень:');
 await expect(page.locator('main.content')).not.toContainText('Несовпавшие APP_ID блокируют импорт.');
 page.once('dialog',dialog=>dialog.dismiss());await panel.getByRole('button',{name:'Удалить',exact:true}).click();
 await expect(panel.locator('tbody tr')).toHaveCount(1);expect(calls).toBe(0);
 page.once('dialog',dialog=>{expect(dialog.message()).toContain('Созданные прогоны останутся доступны');return dialog.accept()});
 await panel.getByRole('button',{name:'Удалить',exact:true}).click();
 await expect(panel.locator('.count-label')).toHaveText('0');
 await expect(panel.getByText('Загрузите первый датасет, чтобы начать анализ.')).toBeVisible();expect(calls).toBe(1);
 await page.getByRole('button',{name:'Конфигурация',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Датасет',exact:true})).toHaveValue('');
});
