from agent.context_pressure import (
    assess_context_pressure,
    format_context_pressure_lines,
    summarize_sessions_for_pressure,
)


def test_context_pressure_is_quiet_for_healthy_reuse():
    assessment = assess_context_pressure(
        input_tokens=2_000,
        output_tokens=1_000,
        cache_read_tokens=8_000,
        cache_write_tokens=0,
        context_length=200_000,
        context_used_tokens=25_000,
    )

    assert assessment["status"] == "ok"
    assert assessment["warnings"] == []
    assert any("Cache split" in line for line in format_context_pressure_lines(assessment))


def test_context_pressure_warns_on_fresh_heavy_large_session():
    assessment = assess_context_pressure(
        input_tokens=55_000,
        output_tokens=2_000,
        cache_read_tokens=5_000,
        cache_write_tokens=0,
        context_length=200_000,
        context_used_tokens=70_000,
    )

    assert assessment["status"] in {"warn", "critical"}
    assert any("fresh" in warning.lower() for warning in assessment["warnings"])
    lines = format_context_pressure_lines(assessment)
    assert any("Cache split" in line for line in lines)
    assert any("compress" in line.lower() or "skill" in line.lower() for line in lines)


def test_summarize_sessions_for_pressure_ranks_problem_sessions():
    sessions = [
        {
            "id": "sess-ok",
            "input_tokens": 1_000,
            "output_tokens": 500,
            "cache_read_tokens": 9_000,
            "cache_write_tokens": 0,
        },
        {
            "id": "sess-risk",
            "input_tokens": 60_000,
            "output_tokens": 3_000,
            "cache_read_tokens": 1_000,
            "cache_write_tokens": 0,
            "last_prompt_tokens": 180_000,
            "context_length": 200_000,
        },
    ]

    summary = summarize_sessions_for_pressure(sessions)
    assert summary["aggregate"]["prompt_tokens"] == 71_000
    assert summary["sessions"]
    assert summary["sessions"][0]["session"]["id"] == "sess-risk"
