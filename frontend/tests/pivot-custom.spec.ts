import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('removed views are absent and custom layout opens, builds and switches back',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 await page.goto('/?run='+run+'&tab=pivot');
 const view=page.getByRole('combobox',{name:'Представление сводной'});
 await expect(page.locator('.report-table')).toBeVisible();
 await expect(view.locator('option')).toHaveCount(4);
 await expect(view.locator('option[value="all"],option[value="external"]')).toHaveCount(0);
 await view.selectOption('custom');
 await expect(view).toHaveValue('custom');
 await expect(page.locator('.report-settings')).toHaveAttribute('open','');
 await page.getByRole('button',{name:'Очистить строки',exact:true}).click();
 await page.getByRole('combobox',{name:'Строки сводной',exact:true}).selectOption('PATH');
 await page.getByRole('button',{name:'Перестроить',exact:true}).click();
 await expect(page.getByRole('columnheader').filter({hasText:'PATH'})).toBeVisible();
 await expect(view).toHaveValue('custom');
 await expect(page.locator('.report-selection button')).toContainText('2');
 await view.selectOption('decisions');
 await expect(view).toHaveValue('decisions');
 await expect(page.locator('.report-table tbody tr')).toHaveCount(2);
});
