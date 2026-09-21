"""Eval regression gate.

uv run python -m pwm_eval.check            # fail if any score fell below the committed baseline
uv run python -m pwm_eval.check --update   # accept the current scores as the new baseline

The baseline is committed, so lowering it is a visible, reviewable change.
"""

import argparse
import json
from pathlib import Path

from pwm.pipeline.heuristic import HeuristicExtractor, HeuristicTriager
from pwm_eval.fixture import load_fixture
from pwm_eval.metrics import PrecisionRecall, Report, evaluate
from pwm_eval.pipeline_system import PipelineSystem

BASELINE = Path(__file__).resolve().parents[1] / "baselines" / "heuristic.json"
# Lower is better for these; everything else numeric is higher-is-better.
LOWER_IS_BETTER = {
    "noise_reaching_model_rate",
    "noise_producing_candidates_rate",
    "signal_emails_dropped_rate",
    "injection_violations",
    "cost_usd_per_100_sources",
}
TOLERANCE = 0.001


def flatten(report: Report) -> dict[str, float]:
    scores: dict[str, float] = {}
    for name in Report.model_fields:
        value = getattr(report, name)
        if isinstance(value, PrecisionRecall):
            for part in ("precision", "recall"):
                if (score := getattr(value, part)) is not None:
                    scores[f"{name}.{part}"] = score
        elif isinstance(value, bool):
            scores[name] = float(value)
        elif isinstance(value, int | float) and name != "sources":
            scores[name] = float(value)
    return scores


def regressions(current: dict[str, float], baseline: dict[str, float]) -> list[str]:
    problems = []
    for name, expected in baseline.items():
        actual = current.get(name)
        if actual is None:
            problems.append(f"{name}: was {expected}, now missing")
        elif name in LOWER_IS_BETTER and actual > expected + TOLERANCE:
            problems.append(f"{name}: rose from {expected} to {actual}")
        elif name not in LOWER_IS_BETTER and actual < expected - TOLERANCE:
            problems.append(f"{name}: fell from {expected} to {actual}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    system = PipelineSystem("pipeline-heuristic", HeuristicTriager(), HeuristicExtractor())
    current = flatten(evaluate(system, load_fixture()))
    if args.update or not BASELINE.exists():
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"baseline written: {BASELINE}")
        return
    problems = regressions(current, json.loads(BASELINE.read_text()))
    if problems:
        raise SystemExit("eval regression:\n  " + "\n  ".join(problems))
    print(f"eval: no regression across {len(current)} scores")


if __name__ == "__main__":
    main()
