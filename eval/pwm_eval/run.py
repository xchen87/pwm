"""Run the eval suite.

uv run python -m pwm_eval.run [--system baseline|heuristic|anthropic|oracle]
                               [--fixture synthetic|golden] [--allow-spend]
"""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager
from pwm_eval.fixture import SYNTHETIC_DIR, Fixture, load_fixture
from pwm_eval.golden import GOLDEN_DIR
from pwm_eval.metrics import PrecisionRecall, Report, evaluate
from pwm_eval.pipeline_system import PipelineSystem
from pwm_eval.systems import BaselineSystem, OracleSystem, SystemUnderTest

HISTORY = Path(__file__).resolve().parents[1] / "results" / "history.jsonl"


def build_system(name: str, fixture: Fixture) -> SystemUnderTest:
    if name == "baseline":
        return BaselineSystem()
    if name == "heuristic":
        return PipelineSystem("pipeline-heuristic", HeuristicTriager(), HeuristicExtractor())
    if name == "anthropic":
        import anthropic

        from pwm.extraction.anthropic_adapter import AnthropicExtractor, AnthropicTriager

        client = anthropic.Anthropic()
        return PipelineSystem(
            "pipeline-anthropic", AnthropicTriager(client), AnthropicExtractor(client)
        )
    if name == "oracle":
        return OracleSystem(fixture.gold)
    raise SystemExit(f"unknown system: {name}")


def git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def show(value: object) -> str:
    if isinstance(value, PrecisionRecall):
        return (
            f"P={show(value.precision)} R={show(value.recall)} F1={show(value.f1)} "
            f"({value.true_positives} matched / {value.predicted} predicted"
            f" / {value.expected} expected)"
        )
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", default="baseline")
    parser.add_argument("--fixture", choices=["synthetic", "golden"], default="synthetic")
    parser.add_argument("--allow-spend", action="store_true", help="permit paid model calls")
    parser.add_argument("--no-record", action="store_true", help="do not append to results history")
    args = parser.parse_args()

    if args.system == "anthropic" and not args.allow_spend:
        raise SystemExit(
            "This run calls a paid model API for every source that passes the prefilter "
            "and sends fixture text to the provider. Re-run with --allow-spend to proceed."
        )
    fixture = load_fixture(GOLDEN_DIR if args.fixture == "golden" else SYNTHETIC_DIR)
    report: Report = evaluate(build_system(args.system, fixture), fixture)

    width = max(len(name) for name in Report.model_fields)
    for name in Report.model_fields:
        print(f"{name:<{width}}  {show(getattr(report, name))}")

    if not args.no_record:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "revision": git_revision(),
            "fixture": args.fixture,
            **report.model_dump(mode="json"),
        }
        with HISTORY.open("a", encoding="utf-8") as history:
            history.write(json.dumps(entry) + "\n")
        print(f"\nrecorded in {HISTORY}")


if __name__ == "__main__":
    main()
