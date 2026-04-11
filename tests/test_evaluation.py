from app.evaluation import compare_runs, materialize_run, replay_run
from app.schemas import BenchmarkScenario, RunCreate


def build_payload() -> RunCreate:
    return RunCreate(
        benchmark_name="audio_robustness_suite",
        model_name="demo-audio-model-v1",
        seed=11,
        scenarios=[
            BenchmarkScenario(name="reverb_shift", difficulty="medium"),
            BenchmarkScenario(name="background_noise", difficulty="hard"),
        ],
    )


def test_materialize_run_produces_aggregate_score():
    run = materialize_run(build_payload())

    assert run.status == "completed"
    assert len(run.results) == 2
    assert 0.0 <= run.aggregate_score <= 1.0


def test_replay_creates_new_identifier():
    run = materialize_run(build_payload())
    replay = replay_run(run)

    assert replay.run_id != run.run_id
    assert replay.status == "replayed"
    assert replay.aggregate_score == run.aggregate_score


def test_compare_runs_returns_verdict():
    left = materialize_run(build_payload())
    right = materialize_run(
        RunCreate(
            benchmark_name="audio_robustness_suite",
            model_name="demo-audio-model-v2",
            seed=11,
            scenarios=build_payload().scenarios,
        )
    )

    comparison = compare_runs(left, right)

    assert comparison.left_run_id == left.run_id
    assert comparison.right_run_id == right.run_id
    assert isinstance(comparison.verdict, str)
