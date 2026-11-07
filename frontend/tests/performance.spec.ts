import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('measure visible report interactions on the latest full dataset',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const times:Record<string,number>={};
 let start=performance.now();await page.goto('/?run='+run+'&tab=overview');
 await expect(page.getByText('657 → 496',{exact:true})).toBeVisible();times.report_open_ms=performance.now()-start;console.log('report ready');
 await page.getByRole('button',{name:'Сводная',exact:true}).click();
 start=performance.now();await page.getByRole('button',{name:'Сводная',exact:true}).click();await expect(page.locator('.pivot-table')).toBeVisible();times.first_pivot_ms=performance.now()-start;
 await page.getByRole('combobox',{name:'Представление сводной'}).selectOption('decisions');
 await expect(page.locator('.report-table tbody tr')).toHaveCount(2);
 await page.locator('.report-settings summary').click();
 await page.getByRole('button',{name:'Убрать VALUE_ADJUSTED',exact:true}).click();await page.getByRole('combobox',{name:'Строки сводной',exact:true}).selectOption('product_id');
 start=performance.now();const layout=page.waitForResponse(r=>r.url().endsWith('/pivot')&&r.request().method()==='POST');await page.getByRole('button',{name:'Перестроить',exact:true}).click();await layout;await expect(page.getByRole('columnheader').filter({hasText:'product_id'})).toBeVisible();times.change_layout_ms=performance.now()-start;
 await page.getByRole('combobox',{name:'Filter dimension',exact:true}).selectOption('product_id');await page.getByRole('textbox',{name:'Значения фильтра',exact:true}).fill('15210');await page.getByRole('button',{name:'Добавить фильтр',exact:true}).click();
 start=performance.now();const filtered=page.waitForResponse(r=>r.url().endsWith('/pivot')&&r.request().method()==='POST');await page.getByRole('button',{name:'Перестроить',exact:true}).click();await filtered;await expect(page.locator('.pivot-table tbody tr')).toHaveCount(1);times.filter_ms=performance.now()-start;
 await page.locator('.pivot-table tbody button').first().click();await expect(page.locator('.app-list button').first()).toBeVisible();
 start=performance.now();await page.locator('.app-list button').first().click();await expect(page.locator('.detail-table')).toBeVisible();times.application_ms=performance.now()-start;
 await page.getByRole('button',{name:'Закрыть заявку',exact:true}).click();await page.getByRole('button',{name:'Закрыть заявки',exact:true}).click();
 start=performance.now();await page.getByRole('button',{name:'Обзор изменений',exact:true}).click();await expect(page.getByText('657 → 496',{exact:true})).toBeVisible();times.report_reopen_ms=performance.now()-start;
 fs.writeFileSync('../runtime/browser-performance.json',JSON.stringify({run_id:run,times,date:new Date().toISOString(),method:'Edge headless 1512x1000, timings include click, HTTP where applicable and visible DOM, one repetition'},null,2));
 console.log(JSON.stringify(times));
});
