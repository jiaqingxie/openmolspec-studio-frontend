"""Exercise the real MCP stdio handshake, discovery and validation tools."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys


async def verify(output, request=None):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    root=Path(__file__).resolve().parents[1]
    params=StdioServerParameters(command=sys.executable,args=['-m','openmolspec.mcp'],
        env={**os.environ,'PYTHONPATH':str(root/'src')})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write,read_timeout_seconds=300 if request else 30) as session:
            info=await session.initialize();response=await session.list_tools();names=[t.name for t in response.tools]
            assert set(names)=={'spectra_tasks','spectra_datasets','spectra_validate','spectra_predict'}
            assert info.server_info.version=='1.0'
            tasks=await session.call_tool('spectra_tasks',{});assert not tasks.is_error
            valid=await session.call_tool('spectra_validate',{'task':'nmr.forward.13C','inputs':{'smiles':'CCO'},'model_settings':{'root':'example-model-root'}})
            invalid=await session.call_tool('spectra_validate',{'task':'ms.forward.glacier','inputs':{},'model_settings':{}})
            def value(result):
                return result.structured_content or json.loads(next(block.text for block in result.content if block.type=='text'))
            assert not valid.is_error and value(valid)['valid'] is True
            assert not invalid.is_error and value(invalid)['valid'] is False
            report={'completed':True,'transport':'stdio','server':info.server_info.model_dump(),'tools':names,
                    'discovery_call':True,'valid_request_call':True,'invalid_request_rejected':True,'model_inference_performed':False}
            if request:
                payload=json.loads(request.read_text())
                result=await session.call_tool('spectra_predict',{'task':payload['task'],'inputs':payload['inputs'],
                    'model_settings':payload['model_config'],'repeats':payload.get('repeats',2)})
                actual=value(result)
                assert not result.is_error and actual['completed'], actual
                if payload.get('repeats',2)>1:assert actual['repeat_predictions_equal'] is True
                report['model_inference_performed']=True
                report['inference']=actual
            output.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({key:val for key,val in report.items() if key!='inference'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--request',type=Path,help='Optional real inference request; model assets must be supplied')
    args=parser.parse_args()
    asyncio.run(verify(args.output,args.request))
