"""Run the released experimental H/C peak predictor in its model interpreter."""

import json
import sys

from openmolspec._worker import released_shift


def predict(payload):
    return released_shift(payload)


if __name__ == "__main__":
    print("OMS_RESULT_V1:" + json.dumps(predict(json.load(sys.stdin)), allow_nan=False))
