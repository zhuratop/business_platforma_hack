import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('grouped dimensions, paired buckets and global attributes in a product cohort',async({page,context})=>{
 test.setTimeout(60000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 await page.goto('/?run='+run+'&tab=pivot');
 await page.getByRole('combobox',{name:'Представление сводной'}).selectOption('decisions');await expect(page.locator('.report-table tbody tr')).toHaveCount(2);await page.locator('.report-settings summary').click();
 const rows=page.getByRole('combobox',{name:'Строки сводной',exact:true});
 await expect(rows.locator('optgroup[label="Технические"] option')).toHaveCount(5);
 await expect(rows.locator('option[value="DIFF_FLAG"]')).toHaveCount(0);
 await expect(rows.locator('option[value="DECISION_CHANGED"]')).toHaveCount(0);
 const filter=page.getByRole('combobox',{name:'Filter dimension',exact:true});
 await expect(filter.locator('option[value="DIFF_FLAG"]')).toHaveCount(1);
 await expect(filter.locator('option[value="DECISION_CHANGED"]')).toHaveCount(1);

 async function addFilter(dimension:string,value:string){
  await filter.selectOption(dimension);await page.getByRole('textbox',{name:'Значения фильтра',exact:true}).fill(value);await page.getByRole('button',{name:'Добавить фильтр',exact:true}).click();
 }
 async function rebuild(){const response=page.waitForResponse(r=>r.url().endsWith('/pivot')&&r.request().method()==='POST');await page.getByRole('button',{name:'Перестроить',exact:true}).click();expect((await response).ok()).toBe(true)}
 await addFilter('PATH','decisionResult.decision');await addFilter('product_id','15210');
 await page.getByRole('button',{name:'Убрать VALUE_ADJUSTED',exact:true}).click();await page.getByRole('button',{name:'Убрать DIFF_FLAG',exact:true}).click();await page.getByRole('button',{name:'Убрать SOURCE',exact:true}).click();
 await rows.selectOption('DECISION_BEFORE');await page.getByRole('combobox',{name:'Колонки сводной',exact:true}).selectOption('DECISION_AFTER');
 await rebuild();await expect(page.locator('.pivot-table')).toContainText('125');
 const row=page.locator('.pivot-table tbody tr').filter({has:page.getByRole('cell',{name:'APPROVE',exact:true})});
 await row.getByRole('button',{name:'125',exact:true}).click();await expect(page.locator('.drawer h2')).toContainText('125');
 await page.locator('.app-list button').first().click();await expect(page.locator('.highlight-row')).toHaveCount(1);await expect(page.locator('.highlight-row')).toContainText('decisionResult.decision');
 await page.getByRole('button',{name:'Закрыть заявку',exact:true}).click();await page.getByRole('button',{name:'Закрыть заявки',exact:true}).click();
 await page.getByRole('button',{name:'Убрать DECISION_BEFORE',exact:true}).click();await page.getByRole('button',{name:'Убрать DECISION_AFTER',exact:true}).click();
 await rows.selectOption('ADJUSTED_BEFORE');await page.getByRole('combobox',{name:'Колонки сводной',exact:true}).selectOption('ADJUSTED_AFTER');
 await rebuild();await expect(page.getByRole('columnheader').filter({hasText:'ADJUSTED_BEFORE'})).toBeVisible();
 await expect(page.locator('.pivot-table')).toContainText('564');
 await page.screenshot({path:'../runtime/pivot-updated.png',fullPage:true});
 // Product and bucket filters also work together through the public API.
 const res=await context.request.post('/api/runs/'+run+'/pivot',{data:{rows:[],columns:['SOURCE'],filters:{PATH:['decisionResult.decision'],product_id:['15210']}}});
 expect(res.ok()).toBe(true);expect((await res.json()).data.cells.map((c:any)=>c.count)).toEqual([927,927]);
});
