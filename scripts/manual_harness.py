"""Agent-facing guides and examples for Spectra Harness."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def code(value,language='python'):
    return f'```{language}\n{value.rstrip()}\n```\n\n'


def assets():
    full=json.loads((ROOT/'documentation/assets/examples/vibrational-gap-ir_raman_hc.json').read_text())['examples'][0]['input']
    ms=json.loads((ROOT/'documentation/assets/examples/ms-forward-glacier.json').read_text())['examples'][0]['input']
    requests={
        'nmr-request':{'task':'nmr.forward.13C','inputs':{'smiles':'CCO'},'model_config':{'root':'/path/to/models','python':'/path/to/nmr-env/bin/python'},'repeats':2},
        'ms-request':{'task':'ms.forward.glacier','inputs':ms,'model_config':{'source':'/path/to/ms-pred','weights':'/path/to/glacier-weights','python':'/path/to/ms-env/bin/python'},'repeats':2},
        'vibrational-request':{'task':'vibrational.gap.ir_raman_hc','inputs':{'ir':full['ir'],'raman':full['raman'],'nmr_h':full['nmr_h_shifts_ppm'],'nmr_c':full['nmr_c_shifts_ppm']},
                               'model_config':{'root':'/path/to/openspec-models','python':'/path/to/openspec-env/bin/python'},'repeats':2}}
    return {f'assets/harness/{name}.json':json.dumps(value,ensure_ascii=False,indent=2)+'\n' for name,value in requests.items()}


def pages(en):
    suffix='' if en else '.zh';out=assets();runs=json.loads((ROOT/'results/spectra_harness_stability_20261117.json').read_text())['runs']
    text='# Agent Harness\n\n'
    text+=('Spectra Harness gives an agent a common interface to NMR, MS and vibrational models. A request identifies the task, supplies molecular or spectral inputs, and selects a model environment. The response contains the prediction and a record of the calls. The same request can be used from Python, the command line or MCP.\n\n' if en else
           'Spectra Harness 为 Agent 提供统一的 NMR、MS 和振动谱模型接口。一个请求包含任务名称、分子或谱学输入，以及模型运行环境；响应返回预测结果和调用记录。同一份请求可以通过 Python、命令行或 MCP 使用。\n\n')
    text+='## '+('Workflow' if en else '使用流程')+'\n\n'
    text+=('1. Discover available tasks with `catalog()` or `spectra_tasks`.\n2. Prepare the fields for your task and configure model paths.\n3. Check the request with `validate()` or `spectra_validate`.\n4. Run the model with `run()` or `spectra_predict`.\n5. Read `result`; inspect `calls` when measuring latency or repeating a prediction.\n\n' if en else
           '1. 使用 `catalog()` 或 `spectra_tasks` 选择任务。\n2. 按任务准备输入，配置模型路径。\n3. 使用 `validate()` 或 `spectra_validate` 检查字段与数组形状。\n4. 使用 `run()` 或 `spectra_predict` 执行模型。\n5. 从 `result` 读取结果，从 `calls` 查看每次调用的耗时和状态。\n\n')
    text+=code("from openmolspec.harness import SpectraHarness\n\nharness = SpectraHarness()\nfor task in harness.catalog():\n    print(task['task'], task['harness'])")
    text+='## '+('Guides' if en else '使用指南')+'\n\n'
    for name,a,z,description,description_zh in [
        ('quickstart','Quick start','快速开始','Make an NMR request and read its output.','完成一次 NMR 请求并读取输出。'),
        ('python','Python interface','Python 接口','Configure a Harness and call it from a script.','在 Python 脚本中配置并调用 Harness。'),
        ('cli','Command line','命令行','Run reusable JSON request files.','通过 JSON 请求文件运行模型。'),
        ('mcp','MCP tools','MCP 工具','Connect an agent and use discovery, validation and prediction tools.','连接 Agent，使用发现、验证和预测工具。'),
        ('nmr','NMR Spectra Harness','NMR Spectra Harness','Predict shifts, assign peaks and identify structures.','预测位移、指认峰并解析结构。'),
        ('ms','MS Spectra Harness','MS Spectra Harness','Predict MS/MS spectra with acquisition conditions.','在指定采集条件下预测 MS/MS。'),
        ('vibrational','Vibrational Spectra Harness','Vibrational Spectra Harness','Predict gaps and identify structures from multiple spectral channels.','用多谱输入预测能隙、检索或生成结构。'),
        ('examples','Examples','Examples','Inspect inputs and outputs for three model families.','查看三类模型的输入与输出。')]:
        text+=f'- [{a if en else z}](harness/{name}.md): {description if en else description_zh}\n'
    out[f'harness{suffix}.md']=text
    settings="settings = {'root': '/path/to/models',\n            'python': '/path/to/nmr-env/bin/python'}"
    first="from openmolspec.harness import SpectraHarness\n\nharness = SpectraHarness()\ninputs = {'smiles': 'CCO'}\n"+settings+"\n\nharness.validate('nmr.forward.13C', inputs, settings)\nreport = harness.run('nmr.forward.13C', inputs, settings, repeats=2)\nprint(report['result']['records'])\nprint(report['repeat_predictions_equal'])"
    result=runs['nmr.forward.13C']['result']['records']
    quick='# '+('Quick start' if en else '快速开始')+'\n\n'
    quick+=('This example predicts the carbon shifts of ethanol. Install the package, point `root` to the NMRNet model directory and select the Python interpreter of the NMR environment.\n\n' if en else
            '这个例子预测乙醇的碳谱。安装包后，将 `root` 指向 NMRNet 模型目录，并填写 NMR 环境的 Python 路径。\n\n')
    quick+=code(first)+('The returned atom indices identify the carbon atoms in the input structure. `prediction_ppm` contains their chemical shifts.\n\n' if en else
                           '返回的原子编号对应输入结构中的碳原子，`prediction_ppm` 是对应的化学位移。\n\n')
    quick+=code(json.dumps(result,indent=2), 'json')
    quick+=('Setting `repeats=2` runs the same request twice. The example returns `True` for `repeat_predictions_equal`. Continue with the [Python guide](python.md) or [MCP tools](mcp.md).\n' if en else
            '设置 `repeats=2` 会重复运行同一请求。此例的 `repeat_predictions_equal` 为 `True`。接着可以查看 [Python 指南](python.md)或 [MCP 工具](mcp.md)。\n')
    out[f'harness/quickstart{suffix}.md']=quick
    python='# Python interface\n\n'+('Create a Harness once, then use it for discovery, input validation and prediction. Each family plugin translates its task request into the corresponding model call.\n\n' if en else
            '创建一个 Harness 后，即可用它发现任务、验证输入和执行预测。各谱型插件将请求转换为相应的模型调用。\n\n')+code(first)
    python+='## '+('Read the response' if en else '读取响应')+'\n\n| Field | Meaning |\n| --- | --- |\n| `completed` | Whether all requested calls finished successfully. |\n| `result` | Prediction returned by the last call. |\n| `calls` | Per-call index, status, elapsed seconds and output hashes. |\n| `repeat_predictions_equal` | Equality of the prediction fields across repeated calls. |\n| `repeat_results` | Complete outputs when repeating a request. |\n\n'
    python+=code("prediction = report['result']\nfor call in report['calls']:\n    print(call['index'], call['status'], call['elapsed_seconds'])")
    python+='## '+('Custom backends' if en else '自定义后端')+'\n\n'
    python+=('Provide a validation function and an execution function to replace the backend of a registered task.\n\n' if en else '提供验证函数和执行函数，即可为已注册任务接入自己的模型后端。\n\n')
    python+=code("from openmolspec.harness import HarnessPlugin, SpectraHarness\n\ndef validate(task, inputs, settings):\n    if not inputs.get('smiles'):\n        raise ValueError('Supply smiles')\n\ndef execute(task, inputs, settings):\n    return my_model.predict(inputs['smiles'])\n\nplugin = HarnessPlugin('My NMR model', ('nmr.forward.13C',),\n                       validate, execute)\nharness = SpectraHarness(plugins=[plugin])")
    out[f'harness/python{suffix}.md']=python
    cli='# Command line\n\n'+('Store a request as JSON to reuse it in scripts and batch workflows. Download an example, edit `model_config` for your environment, then validate and run it.\n\n' if en else
        '将请求保存为 JSON，可以在脚本和批量流程中重复使用。先下载示例，修改 `model_config` 中的环境路径，再验证并执行。\n\n')
    cli+='[NMR request](../assets/harness/nmr-request.json) · [MS request](../assets/harness/ms-request.json) · [Vibrational request](../assets/harness/vibrational-request.json)\n\n'
    cli+=code('spectra-harness catalog\nspectra-harness validate --request nmr-request.json\nspectra-harness run --request nmr-request.json --output nmr-result.json','bash')
    cli+=('The JSON request has four fields: `task`, `inputs`, `model_config` and `repeats`. The output file contains the same report returned by the Python API.\n\n' if en else
          'JSON 请求包含 `task`、`inputs`、`model_config` 和 `repeats`。输出文件与 Python API 返回的报告结构相同。\n\n')
    cli+=code(assets()['assets/harness/nmr-request.json'],'json')
    out[f'harness/cli{suffix}.md']=cli
    mcp='# MCP tools\n\n'+('Connect Spectra Harness to an MCP-compatible agent with the stdio server. Install the MCP extra in the environment used to start the server.\n\n' if en else
        '通过 stdio 服务，可以把 Spectra Harness 接入支持 MCP 的 Agent。先在启动服务的环境中安装 MCP 扩展。\n\n')+code('python -m pip install ".[mcp]"\npython -m openmolspec.mcp','bash')
    mcp+=('![Agent tool execution through MCP](../assets/harness/mcp-workflow.svg)\n\n' if en else '![Agent 通过 MCP 调用谱学工具](../assets/harness/mcp-workflow.svg)\n\n')
    mcp+=code(json.dumps({'mcpServers':{'openmolspec':{'command':'/path/to/environment/bin/python','args':['-m','openmolspec.mcp']}}},indent=2),'json')
    mcp+='## Tools\n\n| Tool | Purpose | Arguments |\n| --- | --- | --- |\n| `spectra_tasks` | Discover model tasks and spectral channels. | None |\n| `spectra_datasets` | Read dataset cards. | Optional `name` |\n| `spectra_validate` | Check input fields and shapes. | `task`, `inputs`, `model_settings` |\n| `spectra_predict` | Run a model and return its prediction. | `task`, `inputs`, `model_settings`, `repeats` |\n\n'
    mcp+='## '+('Example tool call' if en else '工具调用示例')+'\n\n'
    request=json.loads(assets()['assets/harness/nmr-request.json']);request['model_settings']=request.pop('model_config')
    mcp+=code(json.dumps({'tool':'spectra_predict','arguments':request},indent=2),'json')
    mcp+=('The agent reads the predicted shifts from `result.records`. Use `spectra_validate` with the same task, inputs and settings before prediction.\n\n' if en else
          'Agent 从 `result.records` 读取预测位移。预测前，使用相同的任务、输入和设置调用 `spectra_validate`。\n\n')
    mcp+=code(json.dumps({'completed':True,'result':{'records':result},'repeat_predictions_equal':True},indent=2),'json')
    out[f'harness/mcp{suffix}.md']=mcp
    descriptions={
        'nmr':('NMR Spectra Harness','Use a structure for chemical-shift prediction, add measured peaks for assignment, or provide H/C peak records for retrieval and generation.','结构输入用于化学位移预测；加入实测峰后可以做指认；输入 H/C 峰表则可以做检索与结构生成。','nmr-request','nmr.forward.13C'),
        'ms':('MS Spectra Harness','Supply the molecule, adduct, collision energy and instrument to predict MS/MS peaks with GLACIER or ICEBERG.','提供分子结构、加合物、碰撞能和仪器类型，使用 GLACIER 或 ICEBERG 预测 MS/MS 峰。','ms-request','ms.forward.glacier'),
        'vibrational':('Vibrational Spectra Harness','Use IR/Raman intensity arrays and H/C peaks to predict the HOMO–LUMO gap or identify molecular structures.','提供 IR/Raman 强度数组和 H/C 峰，预测 HOMO–LUMO 能隙，或检索与生成分子结构。','vibrational-request','vibrational.gap.ir_raman_hc')}
    for family,(title,desc,desc_zh,fixture,task) in descriptions.items():
        text=f'# {title}\n\n{desc if en else desc_zh}\n\n'
        text+=f'[Download the complete request / 下载完整请求](../assets/harness/{fixture}.json)\n\n'
        text+=code(f"import json\nfrom pathlib import Path\nfrom openmolspec.harness import SpectraHarness\n\nrequest = json.loads(Path('{fixture}.json').read_text())\nharness = SpectraHarness()\nharness.validate(request['task'], request['inputs'], request['model_config'])\nreport = harness.run(request['task'], request['inputs'],\n                     request['model_config'], repeats=request['repeats'])\nresult = report['result']")
        if family == 'nmr':
            text += '\n' + (ROOT / 'scripts' / 'doc_templates' / f'nmr-harness{suffix}.md').read_text() + '\n'
        observed=runs[task]['result']
        if family=='nmr':shown={'records':observed['records'],'unit':observed['unit']}
        elif family=='ms':
            shown={k:observed[k] for k in ['model','smiles','adduct','collision_energy','instrument']}
            shown['predicted_peaks_top8']=sorted(observed['predicted_peaks'],key=lambda peak:peak[1],reverse=True)[:8]
        else:shown={k:observed[k] for k in ['gap_ev','unit','input_modalities']}
        text+='## '+('Output' if en else '输出')+'\n\n'+code(json.dumps(shown,indent=2),'json')
        text+=f'[Task guide / 任务指南](../tasks/{task.replace(".","-")}.md) · [Python API](../api-reference/module-harness.md)\n'
        out[f'harness/{family}{suffix}.md']=text
    text='# Examples\n\n'+('These examples show requests and predictions for the three model families. Download the JSON files to reuse the inputs and configure the model paths for your environment.\n\n' if en else
         '这里展示三类模型的请求与预测结果。可以下载 JSON 复用输入，并配置本地模型路径。\n\n')
    for family,(title,_,_,_,task) in descriptions.items():
        row=runs[task];text+=f'## [{title}]({family}.md)\n\n'
        text+=f'`{task}`\n\n'
        if family=='nmr':text+=code(json.dumps(row['result']['records'],indent=2),'json')
        elif family=='vibrational':text+=code(json.dumps({'gap_ev':row['result']['gap_ev'],'unit':'eV'},indent=2),'json')
        else:text+='![GLACIER spectrum prediction](../assets/gallery/ms-forward-glacier.png)\n\n'
    out[f'harness/examples{suffix}.md']=text
    if not en:
        out['harness/vibrational.zh.md'] += '\n\n## 显式候选库\n\n给定 IR 和 Raman 时，`vibrational.retrieval` 默认从两种实测输入估计 H/C 位移。`spectroscopy.reranking` 可通过 `shortlist` 指定先用嵌入选多少候选，再用 ITM 排序。`vibrational.retrieval.ir` 和 `vibrational.retrieval.raman` 分别接收单一通道。以下离线命令可复现跨候选全库的参考谱方法。它从安装包读取拟合集索引。\n\n```bash\npython -m openmolspec_bench.vib_reference_library --portable /path/to/vib-assets   --pool 4096 --queries 128 --seed 1123 --output reference4096.json\n```\n'
    return out
