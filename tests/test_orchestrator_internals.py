"""Tests for orchestrator internals: scheduler, lifespan and helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException

from orchestrator import main as orchestrator_main
from orchestrator.pipeline import (
    CycleResult,
    _EquityTracker,
    _mean_true_range,
    _neutral_assessment,
    _select_primary,
)
from shared.config import Settings
from shared.schemas.enums import Decision, Direction, Timeframe
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
)


def _technical(timeframe: Timeframe = Timeframe.H1) -> TechnicalSignal:
    return TechnicalSignal(
        symbol="XAUUSD", timeframe=timeframe, signal=Direction.BULLISH, confidence=0.7
    )


def _cycle_result() -> CycleResult:
    return CycleResult(
        symbol="XAUUSD",
        correlation_id="c1",
        technical_signals={Timeframe.H1: _technical()},
        primary=_technical(),
        news=NewsSignal(event="NFP"),
        risk=RiskAssessment(symbol="XAUUSD", approved=True),
        decision=TradeDecision(
            symbol="XAUUSD",
            decision=Decision.BUY,
            final_score=0.8,
            technical_score=0.7,
            news_score=0.5,
            risk_score=1.0,
            risk_approved=True,
        ),
    )


def test_select_primary_prefers_configured_timeframe() -> None:
    signals = {Timeframe.H1: _technical(Timeframe.H1), Timeframe.H4: _technical(Timeframe.H4)}
    assert _select_primary(signals, Timeframe.H4).timeframe is Timeframe.H4
    assert _select_primary(signals, Timeframe.D1).timeframe is Timeframe.H1


def test_neutral_assessment_has_zero_size() -> None:
    assessment = _neutral_assessment("XAUUSD")
    assert assessment.approved is True
    assert assessment.position_size == 0.0


def test_equity_tracker_high_water_mark() -> None:
    tracker = _EquityTracker()
    tracker.update(100.0)
    tracker.update(90.0)
    tracker.update(120.0)
    assert tracker.peak == 120.0


def test_mean_true_range() -> None:
    frame = pd.DataFrame(
        {"high": [2.0, 3.0, 4.0], "low": [1.0, 1.5, 2.0], "close": [1.5, 2.5, 3.5]}
    )
    assert _mean_true_range(frame, 10) is not None
    assert _mean_true_range(pd.DataFrame({"high": [1.0], "low": [0.5], "close": [0.7]}), 5) is None


def test_parse_timeframes() -> None:
    assert orchestrator_main._parse_timeframes(None) is None
    assert orchestrator_main._parse_timeframes("m5, h1") == [Timeframe.M5, Timeframe.H1]
    with pytest.raises(HTTPException):
        orchestrator_main._parse_timeframes("bad")


def test_to_response_maps_primary() -> None:
    response = orchestrator_main._to_response(_cycle_result())
    assert response.symbol == "XAUUSD"
    assert response.technical.timeframe is Timeframe.H1


def test_get_pipeline_raises_when_missing() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(HTTPException) as excinfo:
        orchestrator_main.get_pipeline(request)  # type: ignore[arg-type]
    assert excinfo.value.status_code == 503


def test_get_app_settings_falls_back() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert isinstance(orchestrator_main.get_app_settings(request), Settings)  # type: ignore[arg-type]


async def test_lifespan_builds_and_closes_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Pipeline:
        closed = False

        async def close(self) -> None:
            self.closed = True

    pipeline = _Pipeline()
    monkeypatch.setattr(
        orchestrator_main.AnalysisPipeline, "build", AsyncMock(return_value=pipeline)
    )
    app = FastAPI()
    async with orchestrator_main.lifespan(app):
        assert app.state.pipeline is pipeline
    assert pipeline.closed


def test_scheduler_serialise() -> None:
    from orchestrator.scheduler import _serialise

    payload = _serialise(_cycle_result())
    assert payload["symbol"] == "XAUUSD"
    assert payload["decision"]["decision"] == "BUY"


def test_scheduler_run_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator import scheduler

    monkeypatch.setattr(scheduler, "_run_symbol", AsyncMock(return_value={"symbol": "XAUUSD"}))
    assert scheduler.analyze_symbol.run("XAUUSD") == {"symbol": "XAUUSD"}


async def test_scheduler_run_all(monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator import pipeline as pipeline_module
    from orchestrator import scheduler

    class _Pipeline:
        async def run_all(self) -> list[CycleResult]:
            return [_cycle_result()]

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        pipeline_module.AnalysisPipeline, "build", AsyncMock(return_value=_Pipeline())
    )
    results = await scheduler._run_all()
    assert results[0]["symbol"] == "XAUUSD"
