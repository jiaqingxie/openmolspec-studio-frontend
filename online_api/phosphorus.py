"""Compute solution shifts using the validation-selected checkpoint."""

import json
import sys

from openmolspec._worker import released_shift


def predict(payload):
    payload = {"nucleus": "31P", **payload}
    return released_shift(payload)


if __name__ == "__main__":
    print("OMS_RESULT_V1:" + json.dumps(predict(json.load(sys.stdin)), allow_nan=False))
