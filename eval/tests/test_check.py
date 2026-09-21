from pwm_eval.check import regressions


def test_a_drop_in_recall_is_a_regression() -> None:
    assert regressions({"commitments.recall": 0.8}, {"commitments.recall": 1.0})


def test_more_noise_reaching_the_model_is_a_regression() -> None:
    assert regressions({"noise_reaching_model_rate": 0.5}, {"noise_reaching_model_rate": 0.29})


def test_improvements_and_new_scores_pass() -> None:
    current = {"commitments.recall": 1.0, "noise_reaching_model_rate": 0.1, "new_metric": 0.5}
    baseline = {"commitments.recall": 0.9, "noise_reaching_model_rate": 0.29}
    assert regressions(current, baseline) == []


def test_a_vanished_score_is_a_regression() -> None:
    assert regressions({}, {"injection_clean": 1.0})
