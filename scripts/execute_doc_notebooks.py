"""Execute documentation examples; record the execution engine and source hashes."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import contextlib
import io

import nbformat
from nbclient import NotebookClient
from jupyter_client import AsyncKernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[1]


def execute_python(notebook):
    """Run our plain-Python demonstration cells without a Jupyter socket/kernel."""
    namespace = {"__name__": "__main__"}
    previous = Path.cwd()
    try:
        os.chdir(ROOT)
        count = 0
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            count += 1
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(cell.source, f"<notebook-cell-{count}>", "exec"), namespace)
            cell.execution_count = count
            cell.outputs = [nbformat.v4.new_output("stream", name=name, text=stream.getvalue())
                            for name, stream in [("stdout", stdout), ("stderr", stderr)] if stream.getvalue()]
    finally:
        os.chdir(previous)


async def execute_notebook(notebook, runtime):
    with tempfile.TemporaryDirectory(prefix="oms-nb-") as temporary:
        specifications = KernelSpecManager(kernel_dirs=[str(runtime / "kernels")], ensure_native_kernel=False)
        manager = AsyncKernelManager(kernel_name="openmolspec-docs", kernel_spec_manager=specifications,
                                     transport="ipc", cache_ports=False, ip=str(Path(temporary) / "ipc"),
                                     connection_file=str(Path(temporary) / "connection.json"))
        client = NotebookClient(notebook, km=manager, timeout=60, startup_timeout=30,
                                resources={"metadata": {"path": str(ROOT)}})
        try:
            await asyncio.wait_for(client.async_execute(), timeout=120)
        finally:
            if manager.has_kernel:
                await manager.shutdown_kernel(now=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--engine", choices=["jupyter", "python"], default="jupyter",
                        help="python executes plain-Python cells in process; no Jupyter kernel validation")
    parser.add_argument("--output-dir", type=Path, help="Write executed notebooks separately from source previews")
    args = parser.parse_args()
    runtime = ROOT / ".runtime/doc-notebook-kernels"
    spec_dir = runtime / "kernels/openmolspec-docs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "kernel.json").write_text(json.dumps({"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                                                    "display_name": "OpenMolSpec docs", "language": "python"}))
    os.environ["JUPYTER_PATH"] = str(runtime)
    os.environ["IPYTHONDIR"] = str(runtime / "ipython")
    os.environ["JUPYTER_RUNTIME_DIR"] = str(runtime / "runtime")
    os.environ["MPLCONFIGDIR"] = str(runtime / "matplotlib")
    os.environ["OPENMOLSPEC_RUN_NOTEBOOK_INFERENCE"] = "0"
    index_sha = hashlib.sha256((ROOT / "documentation/assets/evaluation_index.json").read_bytes()).hexdigest()
    files = sorted((ROOT / "documentation/notebooks").glob("*.ipynb"))
    if args.limit:
        files = files[:args.limit]
    proof = []
    for path in files:
        destination_path = args.output_dir / path.name if args.output_dir else path
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        source_sha = hashlib.sha256(json.dumps([cell.source for cell in notebook.cells]).encode()).hexdigest()
        expected = {"evaluation_index_sha256": index_sha, "source_sha256": source_sha, "engine": args.engine}
        if any(notebook.metadata.get("openmolspec_execution", {}).get(key) != value for key, value in expected.items()):
            print("EXECUTING", path.name, flush=True)
            if args.engine == "python":
                execute_python(notebook)
            else:
                asyncio.run(execute_notebook(notebook, runtime))
            notebook.metadata["openmolspec_execution"] = {**expected,
                                                         "model_execution_enabled": False, "training_performed": False,
                                                         "scope": "example_schema_and_recorded_real_evaluation_results"}
            nbformat.validate(notebook)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(notebook, destination_path)
        elif destination_path != path:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(notebook, destination_path)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                assert cell.execution_count is not None, path
                assert not any(item.output_type == "error" for item in cell.outputs), path
        proof.append({"notebook": str(path.relative_to(ROOT)), "executed_file": str(destination_path),
                      "sha256": hashlib.sha256(destination_path.read_bytes()).hexdigest()})
        print("EXECUTED", path.name, flush=True)
    destination = ROOT / "results/doc_notebook_execution.json"
    destination.write_text(json.dumps({"executed_notebooks": len(proof), "evaluation_index_sha256": index_sha, "engine": args.engine,
                                       "scope": "recorded_results_not_retraining_or_model_reruns", "notebooks": proof}, indent=2) + "\n")
    print(f"Notebook demonstrations verified: {len(proof)}", flush=True)


if __name__ == "__main__":
    main()
