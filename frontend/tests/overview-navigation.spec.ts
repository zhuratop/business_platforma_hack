import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('statistics replace the old overview, keep first menu position and support old links',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 await page.goto('/?run='+run+'&tab=overview');
 await expect(page.getByRole('heading',{name:'Обзор изменений',exact:true,level:1})).toBeVisible();
 await expect(page.locator('.statistics-page')).toBeVisible();
 await expect(page.locator('[data-chart="decisions"]')).toBeVisible();
 await expect(page.locator('.overview-banner')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Статистика и решение',exact:true})).toHaveCount(0);
 await expect(page.locator('.sidebar nav').nth(1).locator('button')).toHaveText(['Обзор изменений','Сводная','Автопроверки']);
 await page.getByRole('button',{name:'Журнал',exact:true}).click();
 await page.getByRole('button',{name:'Открыть результат',exact:true}).click();
 await expect(page.locator('.statistics-page')).toBeVisible();
 await expect(page).toHaveURL(/tab=overview/);
 await page.goto('/?run='+run+'&tab=stats');
 await expect(page.getByRole('heading',{name:'Обзор изменений',exact:true,level:1})).toBeVisible();
 await expect(page.locator('.stat-grid')).toBeVisible();
 await expect(page).toHaveURL(/tab=overview/);
 await page.getByRole('button',{name:'Сводная',exact:true}).click();
 await page.locator('.brand').click();
 await expect(page.getByRole('heading',{name:'Обзор изменений',exact:true,level:1})).toBeVisible();
});
