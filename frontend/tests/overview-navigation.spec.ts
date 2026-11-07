import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('overview is removed and old links open the pivot table',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 for(const tab of ['overview','stats']){
  await page.goto('/?run='+run+'&tab='+tab);
  await expect(page.getByRole('heading',{name:'Сводная таблица',exact:true,level:1})).toBeVisible();
  await expect(page).toHaveURL(/tab=pivot/);
  await expect(page.locator('.statistics-page')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Обзор изменений',exact:true})).toHaveCount(0);
 }
 await expect(page.locator('.sidebar nav').nth(1).locator('button')).toHaveText(['Сводная таблица','Автопроверки']);
 await page.getByRole('button',{name:'Журнал',exact:true}).click();
 await page.getByRole('button',{name:'Открыть результат',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Сводная таблица',exact:true,level:1})).toBeVisible();
 await page.getByRole('button',{name:'Датасеты',exact:true}).click();
 await page.locator('.brand').click();
 await expect(page).toHaveURL(/tab=pivot/);
});
