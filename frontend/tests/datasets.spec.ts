import {test,expect} from '@playwright/test';

test('dataset page and configuration show one row per checksum',async({page,context})=>{
 test.setTimeout(30000);
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const response=await context.request.get('/api/datasets');
 expect(response.ok()).toBeTruthy();
 const datasets=(await response.json()).data;
 expect(new Set(datasets.map((d:any)=>d.checksum)).size).toBe(datasets.length);
 const boot=(await (await context.request.get('/api/bootstrap')).json()).data;
 expect(boot.datasets.map((d:any)=>d.id)).toEqual(datasets.map((d:any)=>d.id));
 await page.goto('/?tab=datasets');
 const panel=page.locator('section.panel').filter({has:page.getByRole('heading',{name:'Ваши датасеты',exact:true})});
 await expect(panel.locator('tbody tr')).toHaveCount(datasets.length);
 await expect(panel.locator('.count-label')).toHaveText(String(datasets.length));
 if(datasets.length){
  await panel.getByRole('button',{name:'Настроить'}).first().click();
  const select=page.getByRole('combobox',{name:'Датасет',exact:true});
  await expect(select).toHaveValue(datasets[0].id);
  await expect(select.locator('option')).toHaveCount(datasets.length+1);
 }
});
