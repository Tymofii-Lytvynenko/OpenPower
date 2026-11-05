"""Run UI journeys serially and retain a resumable suite with fresh evidence."""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _replace_with_retry(temporary: Path, destination: Path, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            temporary.replace(destination)
            return
        except PermissionError:
            # Retry transient Windows access-denied errors so completed journeys stay resumable.
            if attempt + 1 >= attempts:
                raise
            time.sleep(0.1 * (attempt + 1))


def _suite_payload(results: list[dict], width: int, height: int, total: int) -> dict:
    return {
        "schema_version": 1,
        "viewport": {"width": width, "height": height},
        "journeys": total,
        "completed": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "results": results,
    }


def run_suite(manifest: Path, output: Path, width: int, height: int, rerun_failed=False, refresh=()):
    source = json.loads(manifest.read_text(encoding="utf-8-sig"))
    previous_path = output / "suite.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    completed = {r["journey"]: r for r in previous.get("results", [])}
    results = []
    output.mkdir(parents=True, exist_ok=True)
    for item in source["results"]:
        journey, surface = item["journey"], item["surface"]
        reused = (
            rerun_failed
            and completed.get(journey, {}).get("passed")
            and not any(fnmatch.fnmatchcase(Path(journey).stem, pattern) for pattern in refresh)
        )
        if reused:
            result = completed[journey]
        else:
            destination = output / Path(journey).stem
            command = [sys.executable, str(ROOT / "main.py"), "ui-test", "run", surface,
                       "--journey", journey, "--width", str(width), "--height", str(height),
                       "--output", str(destination)]
            try:
                process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                         encoding="utf-8", errors="replace", timeout=90)
                code, log = process.returncode, process.stdout + process.stderr
            except subprocess.TimeoutExpired:
                code, log = 124, "Journey process exceeded 90 seconds."
            report_path = destination / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            result = {"journey": journey, "surface": surface,
                      "passed": code == 0 and report.get("result") == "passed",
                      "exit_code": code, "report": str(report_path.resolve()), "log": log}
        results.append(result)
        if not reused:
            suite = _suite_payload(results, width, height, len(source["results"]))
            temporary = previous_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(suite, indent=2), encoding="utf-8")
            _replace_with_retry(temporary, previous_path)
        print(f"{len(results)}/{len(source['results'])} {'PASS' if result['passed'] else 'FAIL'} {journey}", flush=True)
    suite = _suite_payload(results, width, height, len(source["results"]))
    temporary = previous_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    _replace_with_retry(temporary, previous_path)
    return int(any(not r["passed"] for r in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--rerun-failed", action="store_true")
    parser.add_argument("--refresh", action="append", default=[], help="Always rerun this journey stem when resuming.")
    args = parser.parse_args()
    raise SystemExit(run_suite(args.manifest, args.output, args.width, args.height, args.rerun_failed, args.refresh))
