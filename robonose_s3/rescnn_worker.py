"""Run the existing ResCNN64 adapter with an explicitly selected Python."""

import json
from pathlib import Path
import subprocess
import sys


class ResCNNWorker:
    def __init__(self, python, model_dir, sample_roots, **thresholds):
        self.python = Path(python).resolve(strict=True)
        self.options = {"model_dir": str(model_dir),
                        "sample_roots": list(map(str, sample_roots)), **thresholds}
        self.description = self._call("describe")

    def _call(self, method, *args):
        result = subprocess.run(
            [str(self.python), "-B", "-m", "robonose_s3.rescnn_worker"],
            cwd=Path(__file__).resolve().parents[1],
            input=json.dumps([self.options, method, args]), encoding="utf-8",
            capture_output=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError(result.stderr.strip().splitlines()[-1] if result.stderr.strip()
                             else "ResCNN64 worker failed")
        return json.loads(result.stdout)

    def describe(self):
        return self.description

    def predict_identity(self, sample_id):
        return self._call("predict_identity", sample_id)

    def compare(self, reference_id, candidate_ids):
        return self._call("compare", reference_id, candidate_ids)


def main():
    from .rescnn64 import ResCNN64Predictor

    options, method, args = json.load(sys.stdin)
    predictor = ResCNN64Predictor(**options)
    methods = {"describe": predictor.describe, "predict_identity": predictor.predict_identity,
               "compare": predictor.compare}
    print(json.dumps(methods[method](*args), allow_nan=False))


if __name__ == "__main__":
    main()
