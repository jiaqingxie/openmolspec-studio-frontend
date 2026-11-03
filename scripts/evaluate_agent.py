"""Evaluate a configured deployment through its normal HTTP/SSE entry points."""

from __future__ import annotations

import argparse
import json
import time
import unicodedata
import uuid
from pathlib import Path

import httpx

CASES = Path(__file__).resolve().parents[1] / "tests/evals/molspec.json"
CALCULATIONS = {"predict_spectra", "retrieve_candidates", "generate_candidates", "predict_gap"}


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def upload(client, data):
    return request(client, "POST", "/api/uploads",
                   files={"file": ("evaluation-ir.csv", data["content"], "text/csv")},
                   data={"modality": "ir", "intensity_unit": "a.u.",
                         "axis_unit": data["axis_unit"], "domain": data["domain"]})


def observe(client, conversation, prompt, attachment):
    calls = {}
    terminal = None
    with client.stream("POST", f"/api/conversations/{conversation}/messages", json={
        "content": prompt, "mode": "deep", "request_id": uuid.uuid4().hex,
        "attachment_ids": [attachment["id"]] if attachment else [],
    }) as stream:
        stream.raise_for_status()
        event = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
                if event in {"tool_start", "tool_end"}:
                    calls.setdefault(data["id"], {}).update(data)
                elif event in {"done", "error"}:
                    terminal = (event, data)
    return calls.values(), terminal


def grade(case, calls, reply, source_id):
    matching = [call for call in calls if call["name"] == case.get("tool")]
    if source_id:
        matching = [call for call in matching if call.get("args", {}).get("ir_id") == source_id
                    and call.get("result", {}).get("input_refs", {}).get("ir_id") == source_id]
    results = [call.get("result", {}) for call in matching]
    if case.get("tool") and not results:
        return False
    if case.get("job") and not any(result.get("status") == "succeeded" for result in results):
        return False
    if case.get("formula") and not any(result.get("formula") == case["formula"] and result.get("molecule_id") for result in results):
        return False
    if case.get("formula") and case["formula"] not in unicodedata.normalize("NFKC", reply):
        return False
    if case.get("tool_error") and not any(result.get("error") for result in results):
        return False
    if case.get("ineligible") and not any(result.get("quality", {}).get("model_eligible") is False for result in results):
        return False
    if case.get("no_calculation") and any(call["name"] in CALCULATIONS for call in calls):
        return False
    return not case.get("reply_terms") or any(term in reply for term in case["reply_terms"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mock-identity", choices=("researcher", "analyst"), required=True,
                        help="Development-only account for evaluation")
    args = parser.parse_args()
    rows = []
    with httpx.Client(base_url=args.url, timeout=httpx.Timeout(1900, connect=10)) as client:
        request(client, "POST", "/api/auth/mock", json={"identity": args.mock_identity})
        status = request(client, "GET", "/api/status")
        capabilities = (status.get("chemistry") or {}).get("capabilities", {})
        prediction_conversation = None
        predicted_id = None
        for case in json.loads(CASES.read_text()):
            row = {"id": case["id"]}
            rows.append(row)
            if not status["agent"]["configured"]:
                row.update(status="blocked", reason="dialogue provider not configured")
                continue
            required = case.get("capability")
            if required and not capabilities.get(required, {}).get("available"):
                row.update(status="blocked", reason=capabilities.get(required, {}).get("detail", "chemistry unavailable"))
                continue
            if case.get("missing_capability") and capabilities.get(case["missing_capability"], {}).get("available"):
                row.update(status="skipped", reason="the capability is available")
                continue
            if (case.get("followup") or case.get("upload_prediction")) and not predicted_id:
                row.update(status="blocked", reason="prior prediction did not produce a reusable IR spectrum")
                continue
            start = time.monotonic()
            try:
                conversation = prediction_conversation if case.get("followup") else request(client, "POST", "/api/conversations", json={"title": f"Eval · {case['id']}"})["id"]
                attachment = upload(client, case["input"]) if case.get("input") else None
                source_id = predicted_id if case.get("followup") else None
                if case.get("upload_prediction"):
                    spectrum = request(client, "GET", f"/api/spectra/{predicted_id}")
                    attachment = upload(client, {
                        "content": "\n".join(f"{x},{y}" for x, y in zip(spectrum["wavenumber"], spectrum["intensity"])),
                        "axis_unit": spectrum["axis_unit"], "domain": spectrum["domain"],
                    })
                    source_id = attachment["spectrum_id"]
                calls, terminal = observe(client, conversation, case["prompt"], attachment)
                event, result = terminal or ("error", {"code": "stream_incomplete"})
                reply = result.get("message", {}) if event == "done" else {}
                reply = reply.get("content", "")
                passed = event == "done" and grade(case, calls, reply, source_id)
                if case["id"] == "predict" and passed:
                    predicted_id = next((call.get("result", {}).get("ir_id") for call in calls
                                         if call.get("result", {}).get("ir_id")), None)
                    prediction_conversation = conversation
                    passed = bool(predicted_id)
                row.update(status="passed" if passed else "failed", reply=reply, usage=result.get("usage"),
                           tools=[{"name": call["name"], "status": call.get("result", {}).get("status"),
                                   "error": call.get("result", {}).get("error", {}).get("code")} for call in calls])
                if event == "error":
                    row["error"] = result.get("code")
            except httpx.HTTPStatusError as error:
                row.update(status="failed", error=f"HTTP {error.response.status_code}")
            except httpx.RequestError as error:
                row.update(status="failed", error=type(error).__name__)
            row["seconds"] = round(time.monotonic() - start, 3)
    executed = [row for row in rows if row["status"] in {"passed", "failed"}]
    passed = sum(row["status"] == "passed" for row in executed)
    report = {"model": status["agent"]["model"], "executed": len(executed), "passed": passed,
              "success_rate": passed / len(executed) if executed else None, "cases": rows}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n")
    print(output)
    return 0 if all(row["status"] in {"passed", "skipped"} for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
