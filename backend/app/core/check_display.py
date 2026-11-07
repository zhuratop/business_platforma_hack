"""Presentation metadata; never execute a check in an HTTP request."""
import ast
import math

# Meaning of thresholds in the provided checks; the check files stay unchanged.
THRESHOLDS = {
    'ar_drop_by_product': {'parameter':'max_drop_rel','operator':'>'},
    'attribute_new_loss': {'parameter':'min_share','operator':'>='},
}

def threshold(check_id,params,definition=None):
    specification=(definition or {}).get('threshold') or THRESHOLDS.get(check_id,{})
    parameter=specification.get('parameter') if isinstance(specification,dict) else None
    value=params.get(parameter) if isinstance(parameter,str) else None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        value=None
    return {'value':value,'parameter':parameter,'operator':specification.get('operator','') if isinstance(specification,dict) else ''}

def static_definition(code):
    """Recover literal CHECK defaults from old snapshots, without exec/import."""
    environment={}
    definition={}
    def literal(node):
        if isinstance(node,ast.Name):
            return environment[node.id]
        return ast.literal_eval(node)
    try:
        tree=ast.parse(code)
    except SyntaxError:
        return definition
    for statement in tree.body:
        if not isinstance(statement,ast.Assign):
            continue
        for target in statement.targets:
            if not isinstance(target,ast.Name):
                continue
            if target.id!='CHECK':
                try:
                    environment[target.id]=literal(statement.value)
                except (ValueError,TypeError,KeyError):
                    pass
                continue
            node=statement.value
            fields=[]
            if isinstance(node,ast.Dict):
                fields=[(k.value,v) for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant)]
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='dict':
                fields=[(k.arg,k.value) for k in node.keywords]
            for key,value in fields:
                if key in ['params','threshold']:
                    try:
                        result=literal(value)
                        if isinstance(result,dict):
                            definition[key]=result
                    except (ValueError,TypeError,KeyError):
                        pass
    return definition

def with_thresholds(rows,snapshots,overrides):
    result=[]
    definitions={}
    for row in rows:
        if 'threshold' in row:
            result.append(dict(row))
            continue
        sid=row.get('snapshot_id')
        script=snapshots.get(sid,{})
        if sid not in definitions:
            definitions[sid]=static_definition(script.get('code',''))
        definition=definitions[sid]
        params={**definition.get('params',{}),**script.get('params',{}),**overrides.get(row.get('check_id'),{})}
        result.append({**row,'threshold':threshold(row.get('check_id'),params,definition)})
    return result
