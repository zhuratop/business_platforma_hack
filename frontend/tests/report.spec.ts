import {test,expect} from '@playwright/test';
import fs from 'node:fs';

async function login(page:any,context:any){
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 await page.goto('/?run='+run+'&tab=pivot');
 await expect(page.locator('.report-table')).toBeVisible();
 return run;
}

test('assignment-style default report and exact cell drilldown',async({page,context})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await login(page,context);
 await expect(page.getByRole('combobox',{name:'Представление сводной'})).toHaveValue('strategy');
 await expect(page.locator('.report-table thead tr')).toHaveCount(2);
 await expect(page.locator('.report-table thead th[colspan="2"]')).toHaveCount(1);
 await expect(page.locator('.report-table thead')).toContainText('DIFF_FLAG = 0');
 await expect(page.locator('.report-table thead')).toContainText('DIFF_FLAG = 1');
 const width=await page.locator('.report-table-scroll').evaluate(el=>({content:el.scrollWidth,viewport:el.clientWidth}));
 expect(width.content).toBeLessThanOrEqual(width.viewport+1);
 const first=page.locator('.report-table tbody tr').first();
 await expect(first).toContainText('APPROVE');
 await expect(first.locator('td.numeric button span')).toHaveText(['384','273','112','769']);
 await first.getByRole('button',{name:'273',exact:true}).click();
 await expect(page.locator('.drawer h2')).toContainText('273');
 await page.locator('.app-list button').first().click();
 await expect(page.locator('.highlight-row')).toHaveCount(1);
 await expect(page.locator('.highlight-row')).toContainText('decisionResult.decision');
 await page.getByRole('button',{name:'Закрыть заявку',exact:true}).click();
 await page.getByRole('button',{name:'Закрыть заявки',exact:true}).click();
 await page.screenshot({path:'../runtime/pivot-report.png',fullPage:true});
 expect(errors).toEqual([]);
});

test('full JSON hierarchy pages preserve exact totals and every column',async({page,context})=>{
 await login(page,context);
 await page.getByRole('combobox',{name:'Представление сводной'}).selectOption('custom');
 await page.getByRole('button',{name:'Сбросить фильтры',exact:true}).click();
 await page.getByRole('button',{name:'Перестроить',exact:true}).click();
 await expect(page.locator('.report-pagination')).toContainText('1–100');
 const before=await page.locator('.report-table tbody tr').first().innerText();
 const totals=await page.locator('.report-table tfoot').innerText();
 const grand=await page.locator('.report-selection button').innerText();
 await page.getByRole('button',{name:'Следующая страница сводной',exact:true}).click();
 await expect(page.locator('.report-pagination')).toContainText('101–200');
 expect(await page.locator('.report-table tbody tr').first().innerText()).not.toBe(before);
 expect(await page.locator('.report-table tfoot').innerText()).toBe(totals);
 expect(await page.locator('.report-selection button').innerText()).toBe(grand);
 await expect(page.locator('.report-table tbody tr').first().locator('td.numeric')).toHaveCount(4);
});

test('paired bucket view and product cohort with unchanged and changed counts',async({page,context})=>{
 await login(page,context);
 await page.getByRole('combobox',{name:'Представление сводной'}).selectOption('decisions');
 await expect(page.locator('.report-table tbody tr')).toHaveCount(2);
 await page.locator('.report-settings summary').click();
 const rows=page.getByRole('combobox',{name:'Строки сводной',exact:true});
 await expect(rows.locator('optgroup[label="Технические"] option')).toHaveCount(5);
 await expect(rows.locator('option[value="DECISION_CHANGED"]')).toHaveCount(0);
 const filter=page.getByRole('combobox',{name:'Filter dimension',exact:true});
 await expect(filter.locator('option[value="DECISION_CHANGED"]')).toHaveCount(1);
 await filter.selectOption('product_id');await page.getByRole('textbox',{name:'Значения фильтра',exact:true}).fill('15210');
 await page.getByRole('button',{name:'Добавить фильтр',exact:true}).click();
 await expect(page.locator('.report-pending')).toBeVisible();
 await page.getByRole('button',{name:'Перестроить',exact:true}).click();
 await expect(page.locator('.report-selection button')).toContainText('927');
 await expect(page.locator('.report-table tbody tr').first().locator('td.numeric button span')).toHaveText(['186','186','125','52']);
 await page.getByRole('combobox',{name:'Представление сводной'}).selectOption('buckets');
 await expect(page.getByRole('columnheader').filter({hasText:'ADJUSTED_BEFORE'})).toBeVisible();
 await expect(page.locator('.report-table')).toContainText('564');
 await expect(page.locator('.report-selection button')).toContainText('927');
});
