import {test,expect} from '@playwright/test';

test('procedure editor shows complete executable implementations',async({page,context})=>{
 test.setTimeout(30000);
 await context.request.post('/api/auth/login',{data:{username:'alice',password:'demo'}});
 const scripts=(await (await context.request.get('/api/scripts')).json()).data;
 await page.goto('/?tab=code');
 for(const name of ['normalize.py','compare.py','facts.py']){
  const script=scripts.find((s:any)=>s.name===name&&s.source==='file');expect(script).toBeTruthy();
  expect(script.code).not.toContain('from backend.');
  await page.locator('.script-list .script-item').filter({hasText:name}).first().click();
  const editor=page.getByRole('textbox',{name:'Редактор Python',exact:true});
  await expect(editor).toHaveValue(script.code);
  if(name==='compare.py'){
   await expect(editor).toHaveValue(/Duplicate comparison input/);
   await expect(editor).toHaveValue(/PRESENT_BEFORE/);
   await expect(editor).not.toHaveValue(/yield from compare_rows/);
  }
  if(name==='normalize.py')await expect(editor).toHaveValue(/Duplicate or invalid array key/);
  if(name==='facts.py')await expect(editor).toHaveValue(/count\(DISTINCT APP_ID\)/);
 }
 await page.getByRole('button',{name:'Копия в редактор',exact:true}).click();
 await expect(page.getByRole('textbox',{name:'Редактор Python',exact:true})).toBeEditable();
 await expect(page.getByRole('textbox',{name:'Редактор Python',exact:true})).toHaveValue(/CREATE TEMP TABLE enriched/);
});
