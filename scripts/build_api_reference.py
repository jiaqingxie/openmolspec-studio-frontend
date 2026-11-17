"""Build Sphinx Python-domain API pages directly from package source.

Static signatures keep optional model/production dependencies out of the
documentation build. Every public definition gets a stable Python-domain ID,
a source link and a module summary entry.
"""
import argparse
import ast
import copy
from collections import defaultdict
import json
from pathlib import Path
import pprint
import re
import textwrap

ROOT=Path(__file__).resolve().parents[1]
ALIASES={'dataset':'datasets','model':'models','training':'training','benchmark':'benchmarks',
         'task':'tasks','split':'splits','inversion':'inversion','harness':'harness','mcp':'mcp','plotting':'plotting'}
GROUPS=[('data','Data access','数据访问'),('models','Models','模型'),('learning','Training and evaluation','训练与评测'),
        ('spectroscopy','Spectroscopy and record schema','谱学与数据结构'),('processing','Data processing and releases','数据处理与发布'),
        ('agents','Agent tools','Agent 工具'),('utilities','Utilities','工具函数')]


def category(module):
    name=module.removeprefix('openmolspec.')
    if name in ('dataset','split') or name.startswith('datasets.'):return 'data'
    if name=='model':return 'models'
    if name in ('training','benchmark','task'):return 'learning'
    if name=='inversion' or name.startswith('parsing.') or name in ('parsing','core','core.schema','core.constants'):return 'spectroscopy'
    if name in ('harness','mcp'):return 'agents'
    if name.startswith(('workflows.','quality.','release.','io.')) or name=='release':return 'processing'
    return 'utilities'


def slug(module):
    local=module.removeprefix('openmolspec.')
    return 'module-'+ALIASES.get(local,local.replace('.','-'))


def public_method(node):
    return isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and (not node.name.startswith('_') or node.name in ('__iter__','__getitem__','__len__','__enter__','__exit__'))


def signature(node,method=False):
    arguments=ast.parse('def f('+ast.unparse(node.args)+'):pass').body[0].args
    if method:
        if arguments.posonlyargs and arguments.posonlyargs[0].arg in ('self','cls'):arguments.posonlyargs.pop(0)
        elif arguments.args and arguments.args[0].arg in ('self','cls'):arguments.args.pop(0)
    result=node.name+'('+ast.unparse(arguments)+')'
    if node.returns is not None:result+=' -> '+ast.unparse(node.returns)
    return result


def doc_rst(node):
    from sphinx.ext.napoleon.docstring import NumpyDocstring,GoogleDocstring
    text=ast.get_docstring(node) or ''
    converter=NumpyDocstring if '\n----------' in text or '\n-------' in text else GoogleDocstring
    return str(converter(text)).strip()


def inventory():
    result=[]
    for path in sorted((ROOT/'src/openmolspec').rglob('*.py')):
        relative=path.relative_to(ROOT/'src').with_suffix('');parts=relative.parts
        if any(part.startswith('_') for part in parts[1:]):continue
        module='.'.join(parts);tree=ast.parse(path.read_text())
        members=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not n.name.startswith('_')]
        constants=[]
        for node in tree.body:
            targets=node.targets if isinstance(node,ast.Assign) else [node.target] if isinstance(node,ast.AnnAssign) else []
            constants.extend((target.id,node) for target in targets if isinstance(target,ast.Name) and target.id.isupper() and not target.id.startswith('_'))
        if members or constants:result.append({'path':path,'module':module,'tree':tree,'members':members,'constants':constants})
    # Document the public import paths exposed by package __all__ lists too.
    for path in sorted((ROOT/'src/openmolspec').rglob('__init__.py')):
        tree=ast.parse(path.read_text());exports=[]
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__all__' for t in node.targets):
                exports=ast.literal_eval(node.value)
        if not exports:continue
        module='.'.join(path.parent.relative_to(ROOT/'src').parts)
        members=[];constants=[];class_nodes=[]
        for node in tree.body:
            if not isinstance(node,ast.ImportFrom) or node.level!=1:continue
            target=path.parent/((node.module or '').replace('.','/')+'.py')
            if not target.is_file():continue
            target_tree=ast.parse(target.read_text());class_nodes.extend(n for n in target_tree.body if isinstance(n,ast.ClassDef))
            for alias in node.names:
                public_name=alias.asname or alias.name
                if public_name not in exports:continue
                definition=next((n for n in target_tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==alias.name),None)
                if definition is not None:
                    definition=copy.deepcopy(definition);definition.name=public_name
                    for item in ast.walk(definition):item._oms_source_path=target
                    members.append(definition)
                else:
                    value=next((n for n in target_tree.body if
                        (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==alias.name for t in n.targets)) or
                        (isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id==alias.name)),None)
                    if value is not None:
                        value._oms_source_path=target;constants.append((public_name,value))
        if module=='openmolspec':
            constants.extend(('__version__',n) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))
        combined=ast.Module(body=[*tree.body,*class_nodes],type_ignores=[])
        result.append({'path':path,'module':module,'tree':combined,'members':members,'constants':constants})
    return result


def class_signature(node,classes):
    constructor=next((n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='__init__'),None)
    if constructor:return node.name+signature(constructor,True)[len('__init__'):]
    if any((isinstance(d,ast.Name) and d.id=='dataclass') or (isinstance(d,ast.Call) and isinstance(d.func,ast.Name) and d.func.id=='dataclass') for d in node.decorator_list):
        fields=[]
        for field in node.body:
            if isinstance(field,ast.AnnAssign) and isinstance(field.target,ast.Name) and not field.target.id.startswith('_'):
                value=' = '+ast.unparse(field.value) if field.value else ''
                fields.append(field.target.id+': '+ast.unparse(field.annotation)+value)
        return node.name+'('+', '.join(fields)+')'
    for base in node.bases:
        if isinstance(base,ast.Name) and base.id in classes:
            inherited=class_signature(classes[base.id],classes)
            return node.name+inherited[len(base.id):]
    return node.name+'()'


def class_methods(node,classes,seen=None):
    methods={n.name:n for n in node.body if public_method(n)}
    seen=set() if seen is None else seen
    if node.name in seen:return methods
    seen.add(node.name)
    for base in node.bases:
        if isinstance(base,ast.Name) and base.id in classes:
            for name,method in class_methods(classes[base.id],classes,seen).items():methods.setdefault(name,method)
    return methods


def module_page(record):
    module=record['module'];path=record['path'];classes={n.name:n for n in record['tree'].body if isinstance(n,ast.ClassDef)}
    intro=(ast.get_docstring(record['tree']) or '').split('\n\n')[0]
    text=f'# {module}\n\n{intro}\n\n| Name | Description |\n| --- | --- |\n'
    names=[]
    for node in record['members']:
        summary=(ast.get_docstring(node) or '').split('\n')[0].replace('|','\\|')
        summary=re.sub(r':[A-Za-z:]+:`([^`]+)`',r'``\1``',summary)
        text+=f'| {{py:{"class" if isinstance(node,ast.ClassDef) else "func"}}}`{module}.{node.name}` | {summary} |\n'
    for name,node in record['constants']:
        text+=f'| {{py:data}}`{module}.{name}` | Module constant or schema value. |\n'
    rst=f'.. py:module:: {module}\n\n'
    def description(node,indent):
        body=doc_rst(node)
        actual_path=getattr(node,'_oms_source_path',path)
        url=f'https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/{actual_path.relative_to(ROOT).as_posix()}#L{node.lineno}'
        return textwrap.indent(body+f'\n\n`Source code <{url}>`__\n',indent)+'\n'
    for node in record['members']:
        qualified=module+'.'+node.name;names.append(qualified)
        if isinstance(node,ast.ClassDef):
            rst+='.. py:class:: '+class_signature(node,classes)+'\n\n'+description(node,'   ')
            for name,method in class_methods(node,classes).items():
                is_property=any(isinstance(d,ast.Name) and d.id=='property' for d in method.decorator_list)
                directive='property' if is_property else 'method'
                rst+='   .. py:'+directive+':: '+(name if is_property else signature(method,True))+'\n'
                if any(isinstance(d,ast.Name) and d.id=='classmethod' for d in method.decorator_list):rst+='      :classmethod:\n'
                rst+='\n'+description(method,'      ');names.append(qualified+'.'+name)
            for attribute in node.body:
                targets=attribute.targets if isinstance(attribute,ast.Assign) else [attribute.target] if isinstance(attribute,ast.AnnAssign) else []
                for target in targets:
                    if not isinstance(target,ast.Name) or target.id.startswith('_'):continue
                    rst+='   .. py:attribute:: '+target.id+'\n'
                    if isinstance(attribute,ast.AnnAssign):rst+='      :type: '+ast.unparse(attribute.annotation)+'\n'
                    elif target.id=='capabilities':rst+='      :type: dict\n'
                    rst+='\n      '+('Supported model operations, nuclei and input domain.' if target.id=='capabilities' else f'The ``{target.id}`` field; see the constructor parameter description.')+'\n\n'
                    names.append(qualified+'.'+target.id)
        else:rst+='.. py:function:: '+signature(node)+'\n\n'+description(node,'   ')
    for name,node in record['constants']:
        rst+='.. py:data:: '+name+'\n\n'
        try:value=ast.literal_eval(node.value)
        except (ValueError,TypeError):value=None
        if value is not None:
            # Source order is stable for set literals, whose repr varies with hash seeds.
            rendered=ast.unparse(node.value) if any(isinstance(n,ast.Set) for n in ast.walk(node.value)) else pprint.pformat(value,sort_dicts=False,width=90)
            rst+='   ::\n\n'+textwrap.indent(rendered,'      ')+'\n\n'
        actual_path=getattr(node,'_oms_source_path',path)
        url=f'https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/{actual_path.relative_to(ROOT).as_posix()}#L{node.lineno}'
        rst+=f'   `Source code <{url}>`__\n\n'
        names.append(module+'.'+name)
    text+='\n```{eval-rst}\n'+rst.rstrip()+'\n```\n'
    if module in ['openmolspec.model','openmolspec.dataset','openmolspec.harness','openmolspec.inversion']:
        from manual_citations import markdown
        keys=['nmrnet','openspec','glacier','iceberg'] if module.endswith('.model') else ['inversions'] if module.endswith('.inversion') else ['openmolspec','nmrexp','massspecgym','qme14s'] if module.endswith('.dataset') else ['deepseek_harness','nmrnet','glacier','openspec']
        text+=markdown(keys)
    return text,names


def build():
    pages={};objects={};records=inventory();grouped=defaultdict(list)
    for record in records:
        text,names=module_page(record);module=record['module'];grouped[category(module)].append(module)
        for suffix in ['','.zh']:pages[f'api-reference/{slug(module)}{suffix}.md']=text
        objects[module]=names
    for en in [True,False]:
        suffix='' if en else '.zh';index='# '+('API reference' if en else 'API 参考')+'\n\n'
        index+=('The reference is organized by package module. Each entry documents its signature, parameters, return values and source code. Start with the dataset and model interfaces, then use the processing modules to prepare new data.\n\n' if en else
                'API 按包模块组织。每项接口提供函数签名、参数、返回值和源代码入口。数据加载与模型调用从前两项开始；处理新的计算数据可使用后面的解析、清洗与发布模块。\n\n')
        for key,title,title_zh in GROUPS:
            index+=f'- [{title if en else title_zh}](category-{key}.md)\n'
            body='# '+(title if en else title_zh)+'\n\n| Module | Description |\n| --- | --- |\n'
            for module in grouped[key]:
                record=next(r for r in records if r['module']==module)
                intro=(ast.get_docstring(record['tree']) or '').split('\n')[0]
                body+=f'| [{module}]({slug(module)}.md) | {intro} |\n'
            pages[f'api-reference/category-{key}{suffix}.md']=body
        pages[f'api-reference/index{suffix}.md']=index
    pages['assets/api-reference-index.json']=json.dumps({'modules':objects,'module_count':len(objects),'object_count':sum(map(len,objects.values()))},indent=2)+'\n'
    return pages


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for name,text in build().items():
        path=ROOT/'documentation'/name
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('Regenerate API reference: '+name)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print('Complete source-derived API reference verified' if args.check else 'Complete source-derived API reference generated')
