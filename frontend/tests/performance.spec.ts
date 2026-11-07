import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('measure overview, full attribute tree and application drilldown',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const times:Record<string,number>={};
 let start=performance.now();await page.goto('/?run='+run+'&tab=overview');
 await expect(page.locator('.stat-grid')).toBeVisible();times.report_open_ms=performance.now()-start;
 start=performance.now();await page.getByRole('button',{name:'Сводная таблица',exact:true}).click();
 await expect(page.locator('.attribute-tree tbody tr[data-kind="path"]').first()).toBeVisible();times.first_tree_ms=performance.now()-start;
 start=performance.now();await page.getByRole('combobox',{name:'Дерево: DIFF_FLAG'}).selectOption('1');
 await page.getByRole('button',{name:'Раскрыть characteristics',exact:true}).click();
 const row=page.locator('.attribute-tree tr[data-path="characteristics.score_okb"][data-kind="path"]');
 await expect(row).toBeVisible();times.filter_and_expand_ms=performance.now()-start;
 await row.locator('.tree-number button').first().click();await expect(page.locator('.app-list button').first()).toBeVisible();
 start=performance.now();await page.locator('.app-list button').first().click();
 await expect(page.locator('.highlight-row')).toBeVisible();times.application_ms=performance.now()-start;
 fs.writeFileSync('../runtime/browser-performance.json',JSON.stringify({run_id:run,times,date:new Date().toISOString(),method:'Edge headless, one repetition, UI + HTTP'},null,2));
});
