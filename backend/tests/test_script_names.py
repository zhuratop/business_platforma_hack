from backend.app.core.script_names import named_scripts


def test_names_describe_logic_and_identical_copies_without_executing_code():
    code='raise RuntimeError("must not execute")\nCHECK={"id":"my_changes","label":"Моя проверка изменений","entrypoint":run}'
    scripts=[{'id':str(i),'kind':'check','name':f'Моя проверка {i}.py','code':code,'created':str(i)} for i in range(2)]
    result=named_scripts(scripts)
    assert [r['display_name'] for r in result] == ['Наличие изменений в ответах · копия 1','Наличие изменений в ответах · копия 2']
    assert all('FAIL' in r['description'] for r in result)
    assert all('display_name' not in r for r in scripts)
    assert all(r['code']==code for r in result)


def test_known_check_names_and_custom_names_are_preserved():
    result=named_scripts([
        {'id':'1','kind':'check','name':'check_attribute_new_loss.py','code':'CHECK={"id":"attribute_new_loss"}'},
        {'id':'2','kind':'check','name':'Особое условие','code':'CHECK={"id":"my_changes"}'},
        {'id':'3','kind':'normalize','name':'normalize.py','code':''},
    ])
    assert result[0]['display_name']=='Появление и исчезновение атрибутов'
    assert result[1]['display_name']=='Особое условие'
    assert 'display_name' not in result[2]
