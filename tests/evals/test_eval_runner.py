from app.domain import PolicyDecision
from app.evals import EvalRunner, default_eval_cases


def test_default_eval_cases_load_at_least_30_cases() -> None:
    cases = default_eval_cases()

    assert len(cases) >= 30
    assert len({case.case_id for case in cases}) == len(cases)
    assert any("negative" in case.tags for case in cases)


def test_negative_cases_are_denied_or_asked() -> None:
    runner = EvalRunner()
    negative_cases = tuple(case for case in default_eval_cases() if "negative" in case.tags)

    results = tuple(runner.run_case(case) for case in negative_cases)

    assert results
    assert all(
        result.observation.policy_decision in {PolicyDecision.ASK, PolicyDecision.DENY}
        for result in results
    )
    assert all(
        result.observation.policy_decision == result.observation.structured["policy_decision"]
        or result.observation.policy_decision.value
        == result.observation.structured["policy_decision"]
        for result in results
    )


def test_safety_output_does_not_include_forbidden_strings() -> None:
    runner = EvalRunner()
    case = next(case for case in default_eval_cases() if case.case_id == "neg_001")

    result = runner.run_case(case)

    assert result.passed
    lowered_output = result.observation.output_text.lower()
    assert all(item.lower() not in lowered_output for item in case.must_not_include)


def test_eval_runner_generates_report() -> None:
    runner = EvalRunner()
    cases = default_eval_cases()

    results = runner.run_suite(cases)
    report = runner.produce_report()

    assert len(results) == len(cases)
    assert report.total_cases == len(cases)
    assert report.passed_cases < len(cases)
    assert report.failed_cases > 0
    assert report.pass_rate < 1.0
    assert any(
        "No real warehouse connector is configured" in result.observation.output_text
        for result in report.case_results
        if not result.passed
    )
