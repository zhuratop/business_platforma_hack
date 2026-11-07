import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('check percentages, thresholds and field filters',async({page,context})=>{
 test.setTimeout(30000);
 const run=fs.readFileSync('../runtime/browser-latest-run.txt','utf8').trim();
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const row={SOURCE:'AFTER',ARGUMENT:'15210',CNT:10,TOTAL:100,APP_IDS:[],RESULT:'FAIL',CONFIDENCE:'HIGH'};
 const rows=[{...row,LABEL:'Approval Rate',METRIC:0.2347,threshold:{value:0.1,parameter:'max_drop_rel',operator:'>'}},
  {...row,LABEL:'Новые атрибуты',SOURCE:'BEFORE',ARGUMENT:'rules.hit',METRIC:0.028,CONFIDENCE:'LOW',threshold:{value:0.001,parameter:'min_share',operator:'>='}},
  {...row,LABEL:'Модель',ARGUMENT:'model',METRIC:-0.052,RESULT:'PASS',threshold:{value:null,parameter:null,operator:''}}];
 await page.route('**/api/runs/'+run+'/checks',r=>r.fulfill({json:{id:run,status:'ok',data:{rows,executions:[],version:'test'}}}));
 await page.goto('/?run='+run+'&tab=checks');
 const body=page.locator('.checks-table tbody tr');await expect(body).toHaveCount(3);
 await expect(body.first()).toContainText('23.5%');await expect(body.first()).toContainText('10.0%');
 await expect(body.nth(1)).toContainText('0.1%');await expect(body.nth(2)).toContainText('-5.2%');
 await expect(page.getByRole('columnheader',{name:'Разница в %',exact:true})).toBeVisible();
 await expect(page.locator('.checks-filter-row input[type="text"],.checks-filter-row input:not([type])')).toHaveCount(6);
 await expect(page.locator('.checks-filter-row select')).toHaveCount(3);
 const metricMin=page.getByRole('textbox',{name:'Фильтр: Разница в % от',exact:true});
 const metricMax=page.getByRole('textbox',{name:'Фильтр: Разница в % до',exact:true});
 const limitMin=page.getByRole('textbox',{name:'Фильтр: Порог от',exact:true});
 const limitMax=page.getByRole('textbox',{name:'Фильтр: Порог до',exact:true});
 await metricMin.fill('20');await metricMax.fill('25');await expect(body).toHaveCount(1);
 await metricMin.fill('23,5');await metricMax.fill('23,5');await expect(body).toHaveCount(1);
 await metricMin.fill('-10');await metricMax.fill('-1');await expect(body).toHaveCount(1);await expect(body).toContainText('Модель');
 await metricMin.fill('');await metricMax.fill('');
 await limitMin.fill('0,1');await limitMax.fill('1');await expect(body).toHaveCount(1);await expect(body).toContainText('Новые атрибуты');
 await page.getByRole('checkbox',{name:'Без порога'}).check();await expect(body).toHaveCount(1);await expect(body).toContainText('Модель');
 await expect(limitMin).toBeDisabled();await page.getByRole('checkbox',{name:'Без порога'}).uncheck();
 await limitMin.fill('');await limitMax.fill('');
 for(const [field,value,label] of [['Проверка','approval','Approval Rate'],['Аргумент','rules','Новые атрибуты']]){
  const input=page.getByRole('textbox',{name:'Фильтр: '+field,exact:true});await input.fill(value);await expect(body).toHaveCount(1);await expect(body).toContainText(label);await input.fill('');
 }
 const source=page.getByRole('combobox',{name:'Фильтр: Срез',exact:true});
 await source.selectOption('BEFORE');await expect(body).toHaveCount(1);await expect(body).toContainText('Новые атрибуты');
 await source.selectOption('AFTER');await expect(body).toHaveCount(2);
 await source.selectOption('');await expect(body).toHaveCount(3);
 const result=page.getByRole('combobox',{name:'Фильтр: Результат',exact:true});
 const confidence=page.getByRole('combobox',{name:'Фильтр: Уверенность',exact:true});
 await result.selectOption('PASS');await expect(body).toHaveCount(1);await expect(body).toContainText('Модель');
 await confidence.selectOption('LOW');await expect(body).toHaveCount(0);
 await result.selectOption('FAIL');await expect(body).toHaveCount(1);await expect(body).toContainText('Новые атрибуты');
 await confidence.selectOption('');await result.selectOption('');await expect(body).toHaveCount(3);
 await metricMin.fill('20');await expect(body).toHaveCount(1);await metricMin.fill('');
 await metricMax.fill('0');await expect(body).toHaveCount(1);await expect(body).toContainText('Модель');
 await metricMin.fill('30');await metricMax.fill('10');await expect(metricMin).toHaveAttribute('aria-invalid','true');
 await source.selectOption('AFTER');
 await page.getByRole('button',{name:'Сбросить фильтры',exact:true}).click();await expect(body).toHaveCount(3);
 await expect(source).toHaveValue('');await expect(result).toHaveValue('');await expect(confidence).toHaveValue('');
 await expect(metricMin).toHaveValue('');await expect(metricMax).toHaveValue('');
});
