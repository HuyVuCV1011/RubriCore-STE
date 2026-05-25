from scripts.smoke_phase4_http_api import run_phase4_http_smoke


def test_phase4_http_smoke_script_runs_against_local_server() -> None:
    summary = run_phase4_http_smoke()

    assert summary["transport"] in {"http_server", "dispatcher_fallback"}
    assert summary["health"] == {"status": "ok", "service": "pilot_http_api"}
    assert summary["manifest_validation"] == {"validation_errors": []}
    assert summary["baseline_summary"] == {
        "validation_errors": [],
        "case_count": 2,
        "passed_count": 2,
        "failed_count": 0,
    }
