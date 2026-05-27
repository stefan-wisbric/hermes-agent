"""Heuristics for identifying context and cache pressure in sessions.

This module centralizes the logic used by insights and cron watchdogs so the
same thresholds are used everywhere context pressure is reported.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ContextPressureAssessment:
    status: str
    prompt_tokens: int
    fresh_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    cache_reuse_pct: float
    fresh_pct: float
    prompt_tokens_total: int
    context_length: Optional[int] = None
    context_used_tokens: Optional[int] = None
    context_used_pct: Optional[float] = None
    warnings: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        payload["recommendations"] = list(self.recommendations)
        return payload


def _pct(part: int, total: int) -> float:
    return (part / total * 100.0) if total > 0 else 0.0


def assess_context_pressure(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    context_length: int | None = None,
    context_used_tokens: int | None = None,
    label: str | None = None,
) -> Dict[str, Any]:
    """Return a conservative cache/window pressure assessment."""

    del label

    fresh_tokens = max(0, int(input_tokens))
    cache_read_tokens = max(0, int(cache_read_tokens))
    cache_write_tokens = max(0, int(cache_write_tokens))
    output_tokens = max(0, int(output_tokens))

    prompt_tokens = fresh_tokens + cache_read_tokens
    prompt_tokens_total = prompt_tokens + cache_write_tokens + output_tokens

    cache_reuse_pct = _pct(cache_read_tokens, prompt_tokens)
    fresh_pct = _pct(fresh_tokens, prompt_tokens)

    warnings: list[str] = []
    recommendations: list[str] = []
    status = "ok"

    context_used_pct: float | None = None
    if context_length and context_used_tokens:
        context_used_pct = _pct(context_used_tokens, context_length)
        if context_used_pct >= 92:
            status = "critical"
            warnings.append(
                f"Context window is at {context_used_pct:.0f}% - compress now or start a fresh session."
            )
        elif context_used_pct >= 80:
            status = "warn"
            warnings.append(
                f"Context window is at {context_used_pct:.0f}% - you are close to the limit."
            )
            recommendations.append("Use /compress to shrink old turns and keep the useful prefix.")

    if prompt_tokens >= 140_000 and status != "critical":
        status = "critical"
        warnings.append(
            f"Very large prompt footprint ({prompt_tokens:,} prompt tokens) - start a new session soon."
        )
        recommendations.append("Move stable instructions into a skill or pinned project context.")
    elif prompt_tokens >= 80_000 and status == "ok":
        status = "warn"
        warnings.append(
            f"Large prompt footprint ({prompt_tokens:,} prompt tokens) - compression will help keep things manageable."
        )
        recommendations.append("Use /compress or split the task into a fresh session.")

    if prompt_tokens >= 12_000:
        if fresh_pct >= 70:
            if status == "ok":
                status = "warn"
            warnings.append(
                f"Most of the prompt is fresh ({fresh_pct:.0f}% fresh, {cache_reuse_pct:.0f}% cached) - repeated context is not being reused much."
            )
            recommendations.append("Move stable instructions into a skill or project note to improve reuse.")
        elif cache_reuse_pct >= 85:
            recommendations.append(
                f"Strong cache reuse ({cache_reuse_pct:.0f}% cached) - this session is efficient."
            )
        elif fresh_pct >= 55 and prompt_tokens >= 30_000 and status == "ok":
            status = "watch"
            warnings.append(
                f"Prompt is leaning fresh ({fresh_pct:.0f}% fresh) - watch for avoidable context growth."
            )
            recommendations.append("Consider trimming repeated instructions or using /compress.")

    if prompt_tokens >= 25_000 and cache_read_tokens == 0 and status == "ok":
        status = "watch"
        warnings.append("No cache reuse detected in a large session - repeated context may be accumulating.")
        recommendations.append("If this repeats, move the stable prefix into a skill.")

    seen: set[str] = set()
    deduped_warnings: list[str] = []
    for msg in warnings:
        if msg not in seen:
            seen.add(msg)
            deduped_warnings.append(msg)

    seen.clear()
    deduped_recs: list[str] = []
    for msg in recommendations:
        if msg not in seen:
            seen.add(msg)
            deduped_recs.append(msg)

    assessment = ContextPressureAssessment(
        status=status,
        prompt_tokens=prompt_tokens,
        fresh_tokens=fresh_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        cache_reuse_pct=cache_reuse_pct,
        fresh_pct=fresh_pct,
        prompt_tokens_total=prompt_tokens_total,
        context_length=context_length,
        context_used_tokens=context_used_tokens,
        context_used_pct=context_used_pct,
        warnings=tuple(deduped_warnings),
        recommendations=tuple(deduped_recs),
    )
    return assessment.as_dict()


def format_context_pressure_lines(
    assessment: Dict[str, Any],
    *,
    markdown: bool = False,
    include_summary: bool = True,
) -> List[str]:
    """Format an assessment into human-readable warning lines."""

    if not assessment:
        return []

    prefix = "Warning: " if markdown else ""
    lines: list[str] = []
    status = assessment.get("status", "ok")
    cache_reuse_pct = assessment.get("cache_reuse_pct", 0.0)
    fresh_pct = assessment.get("fresh_pct", 0.0)
    prompt_tokens = assessment.get("prompt_tokens", 0)
    context_used_pct = assessment.get("context_used_pct")

    if include_summary and prompt_tokens:
        summary = f"Cache split: {cache_reuse_pct:.0f}% cached / {fresh_pct:.0f}% fresh"
        if context_used_pct is not None:
            summary += f" | Context window: {context_used_pct:.0f}%"
        lines.append(summary)

    for warning in assessment.get("warnings", []) or []:
        lines.append(f"{prefix}{warning}")

    recs = assessment.get("recommendations", []) or []
    if recs and status in {"warn", "critical"}:
        for rec in recs:
            lines.append(f"{prefix}{rec}")
    elif recs and status == "watch":
        lines.append(f"{prefix}{recs[0]}")

    return lines


def summarize_sessions_for_pressure(sessions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate session rows and rank concerning individual sessions."""

    sessions = list(sessions)
    total_input = sum(int(s.get("input_tokens") or 0) for s in sessions)
    total_output = sum(int(s.get("output_tokens") or 0) for s in sessions)
    total_cache_read = sum(int(s.get("cache_read_tokens") or 0) for s in sessions)
    total_cache_write = sum(int(s.get("cache_write_tokens") or 0) for s in sessions)

    aggregate = assess_context_pressure(
        input_tokens=total_input,
        output_tokens=total_output,
        cache_read_tokens=total_cache_read,
        cache_write_tokens=total_cache_write,
    )

    ranked_sessions: list[dict[str, Any]] = []
    for session in sessions:
        prompt_tokens = int(session.get("input_tokens") or 0) + int(session.get("cache_read_tokens") or 0)
        assessment = assess_context_pressure(
            input_tokens=session.get("input_tokens") or 0,
            output_tokens=session.get("output_tokens") or 0,
            cache_read_tokens=session.get("cache_read_tokens") or 0,
            cache_write_tokens=session.get("cache_write_tokens") or 0,
            context_length=session.get("context_length"),
            context_used_tokens=session.get("last_prompt_tokens"),
        )
        severity_rank = {"ok": 0, "watch": 1, "warn": 2, "critical": 3}.get(assessment["status"], 0)
        score = (
            severity_rank,
            assessment.get("context_used_pct") or 0,
            prompt_tokens,
            int(session.get("message_count") or 0),
            int(session.get("tool_call_count") or 0),
        )
        if assessment.get("warnings"):
            ranked_sessions.append({"session": session, "assessment": assessment, "score": score})

    ranked_sessions.sort(key=lambda item: item["score"], reverse=True)

    return {
        "aggregate": aggregate,
        "sessions": ranked_sessions,
    }
