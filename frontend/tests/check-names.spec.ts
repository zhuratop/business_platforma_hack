import {test,expect} from '@playwright/test';

test('configuration explains check names and distinguishes identical templates',async({page,context})=>{
 test.setTimeout(30000);
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const response=await context.request.get('/api/scripts');expect(response.ok()).toBeTruthy();
 const scripts=(await response.json()).data.filter((s:any)=>s.kind==='check');
 await page.goto('/?tab=config');
 const list=page.locator('.check-options');
 await expect(list.locator('label')).toHaveCount(scripts.length);
 await expect(list).not.toContainText('Моя проверка');
 await expect(list).toContainText('Появление и исчезновение атрибутов');
 for(const script of scripts){
  const row=list.locator('label').filter({hasText:script.display_name});
  await expect(row).toHaveCount(1);await expect(row).toContainText(script.description);
 }
 await page.getByRole('button',{name:'Python-процедуры',exact:true}).click();
 await page.getByRole('button',{name:'Новая проверка',exact:true}).last().click();
 await expect(page.getByRole('textbox',{name:'Название',exact:true})).toHaveValue('Доля изменений в пределах порога.py');
 await expect(page.getByRole('textbox',{name:'Редактор Python',exact:true})).toHaveValue(/Доля изменений в пределах порога/);
});
