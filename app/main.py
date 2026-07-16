from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .martingale import build_martingale_filter, load_martingale_snapshot, snapshot_path
from .book_analytics import build_book_analytics
from .exports import render_abook_csv
from .models import AnalysisRequest, BookAnalyticsRequest, FilterOptions, SweepRequest
from .personal_candidates import load_personal_candidates
from .repository import ClickHouseRepository, RepositoryConfigurationError
from .risk import build_local_risk_filter
from .service import (
    build_account_detail_payload,
    build_analysis_payload,
    build_two_stage_payload,
    prepare_analysis_context,
)
from .sweep import evaluate_sweep


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="A-Book Backtest Dashboard", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_repository() -> ClickHouseRepository:
    try:
        return ClickHouseRepository()
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _fetch_daily_rows(
    repository: ClickHouseRepository,
    request: AnalysisRequest,
    excluded_logins: set[tuple[str, int]] | None = None,
) -> list[dict]:
    method = getattr(repository, "fetch_daily_pnl", None)
    if not callable(method):
        return []
    return method(request, excluded_logins=excluded_logins)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "abook-dashboard"}


@app.get("/api/abook/filters", response_model=FilterOptions)
def filter_options(repository: ClickHouseRepository = Depends(get_repository)) -> dict[str, list[str]]:
    try:
        return repository.fetch_filter_options()
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ClickHouse filter query failed") from exc


@app.post("/api/abook/analysis")
def analysis(request: AnalysisRequest, repository: ClickHouseRepository = Depends(get_repository)) -> dict:
    try:
        personal_candidates = load_personal_candidates()
        personal_candidates_enabled = request.personal_candidate_list and personal_candidates.status == "ready"
        personal_candidate_logins = personal_candidates.login_ids if personal_candidates_enabled else frozenset()
        risk_filter = build_local_risk_filter(request)
        martingale_snapshot = build_martingale_filter(request)
        effective_request = risk_filter.apply(request)
        overview_rows = None
        overview_daily_rows = None
        if personal_candidates_enabled or risk_filter.allowed_logins is not None or risk_filter.excluded_logins:
            # Company-profit overview must remain population-level. Do not let
            # the Abook leverage rule remove users from the monthly baseline.
            overview_rows = repository.fetch_analysis(request)
            overview_daily_rows = _fetch_daily_rows(repository, request)
        if personal_candidates_enabled:
            # Personal candidates are an explicit Abook override. Keep the
            # normal platform/group/login/test-demo query boundaries, but do
            # not let the local leverage snapshot remove them.
            rows = overview_rows or []
        elif risk_filter.is_empty_for(request):
            rows = []
        else:
            excluded_logins = risk_filter.excluded_logins
            rows = repository.fetch_analysis(effective_request, excluded_logins=excluded_logins) if excluded_logins else repository.fetch_analysis(effective_request)
        rows = martingale_snapshot.enrich_rows(risk_filter.snapshot.enrich_rows(rows))
        if overview_rows is not None:
            overview_rows = martingale_snapshot.enrich_rows(risk_filter.snapshot.enrich_rows(overview_rows))
        if request.lookback_months is not None:
            payload = build_analysis_payload(
                rows,
                request.lookback_months,
                min_profit_factor=request.min_profit_factor if request.min_profit_factor is not None else request.rules.min_profit_factor,
                min_avg_daily_profit=request.min_avg_daily_profit if request.min_avg_daily_profit is not None else request.rules.min_avg_daily_profit,
            )
            payload["risk_management"] = risk_filter.summary()
            payload["martingale"] = martingale_snapshot.summary(request.rules.excluded_martingale_levels)
            return payload
        if personal_candidates_enabled:
            daily_rows = overview_daily_rows or []
        elif risk_filter.is_empty_for(request):
            daily_rows = []
        else:
            excluded_logins = risk_filter.excluded_logins
            daily_rows = (
                _fetch_daily_rows(repository, effective_request, excluded_logins=excluded_logins)
                if excluded_logins
                else _fetch_daily_rows(repository, effective_request)
            )
        rules = request.rules
        payload = build_two_stage_payload(
            rows,
            overview_rows=overview_rows,
            daily_rows=daily_rows,
            overview_daily_rows=overview_daily_rows,
            selection_start=request.selection.start.isoformat(),
            selection_end=request.selection.end.isoformat(),
            validation_start=request.validation.start.isoformat(),
            validation_end=request.validation.end.isoformat(),
            min_trades=rules.min_trades,
            min_active_days=rules.min_active_days,
            min_win_rate=rules.min_win_rate,
            min_profit_factor=rules.min_profit_factor,
            min_payoff_ratio=rules.min_payoff_ratio,
            min_avg_daily_profit=rules.min_avg_daily_profit,
            min_selection_monthly_consistency=rules.min_selection_monthly_consistency,
            min_positive_month_rate=rules.min_positive_month_rate,
            max_top1_day_profit_contribution=rules.max_top1_day_profit_contribution,
            max_peak_leverage_ratio=rules.max_peak_leverage_ratio,
            max_high_leverage_holding_seconds=rules.max_high_leverage_holding_seconds,
            risk_snapshot_status=risk_filter.status,
            min_direction_day_rate_lower_bound=rules.min_direction_day_rate_lower_bound,
            min_stability_score=rules.min_stability_score,
            high_confidence_trades=rules.high_confidence_trades,
            high_confidence_days=rules.high_confidence_days,
            personal_candidate_logins=set(personal_candidate_logins),
            personal_candidate_info=(
                personal_candidates.summary(enabled=request.personal_candidate_list)
            ),
            martingale_snapshot=martingale_snapshot,
            excluded_martingale_levels=request.rules.excluded_martingale_levels,
        )
        payload["risk_management"] = risk_filter.summary()
        payload["martingale"] = martingale_snapshot.summary(request.rules.excluded_martingale_levels)
        return payload
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ClickHouse analysis query failed") from exc


@app.get("/api/abook/accounts/{platform}/{login}")
def account_detail(
    platform: str,
    login: int,
    start: str = "2026-05-01",
    end: str = "2026-07-13",
    selection_start: str = "2026-05-01",
    selection_end: str = "2026-06-30",
    repository: ClickHouseRepository = Depends(get_repository),
) -> dict:
    try:
        rows = repository.fetch_account_detail(platform, login, start, end)
        payload = build_account_detail_payload(rows)
        snapshot = load_martingale_snapshot(snapshot_path(), selection_start, selection_end, [platform])
        payload["martingale"] = {
            **snapshot.summary(),
            "record": snapshot.indexed_records().get((platform, int(login))) if snapshot.status == "ready" else None,
        }
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ClickHouse account query failed") from exc


@app.post("/api/abook/sweep")
def sweep(request: SweepRequest, repository: ClickHouseRepository = Depends(get_repository)) -> dict:
    try:
        analysis_request = request.analysis
        personal_candidates = load_personal_candidates()
        personal_candidates_enabled = analysis_request.personal_candidate_list and personal_candidates.status == "ready"
        personal_candidate_logins = personal_candidates.login_ids if personal_candidates_enabled else frozenset()
        risk_filter = build_local_risk_filter(analysis_request)
        martingale_snapshot = build_martingale_filter(analysis_request)
        effective_request = risk_filter.apply(analysis_request)
        overview_rows = None
        overview_daily_rows = None
        if personal_candidates_enabled or risk_filter.allowed_logins is not None or risk_filter.excluded_logins:
            overview_rows = repository.fetch_analysis(analysis_request)
            overview_daily_rows = _fetch_daily_rows(repository, analysis_request)
        if personal_candidates_enabled:
            rows = overview_rows or []
            daily_rows = overview_daily_rows or []
        elif risk_filter.is_empty_for(analysis_request):
            rows = []
            daily_rows = []
        else:
            excluded_logins = risk_filter.excluded_logins
            rows = repository.fetch_analysis(effective_request, excluded_logins=excluded_logins) if excluded_logins else repository.fetch_analysis(effective_request)
            daily_rows = (
                _fetch_daily_rows(repository, effective_request, excluded_logins=excluded_logins)
                if excluded_logins else _fetch_daily_rows(repository, effective_request)
            )
        rows = martingale_snapshot.enrich_rows(risk_filter.snapshot.enrich_rows(rows))
        if overview_rows is not None:
            overview_rows = martingale_snapshot.enrich_rows(risk_filter.snapshot.enrich_rows(overview_rows))
        context = prepare_analysis_context(
            rows,
            daily_rows=daily_rows,
            overview_rows=overview_rows,
            overview_daily_rows=overview_daily_rows,
            selection_start=analysis_request.selection.start.isoformat(),
            selection_end=analysis_request.selection.end.isoformat(),
            validation_start=analysis_request.validation.start.isoformat(),
            validation_end=analysis_request.validation.end.isoformat(),
        )
        result = evaluate_sweep(
            context,
            analysis_request.rules,
            request.grid,
            request.objective,
            request.max_misjudge_cost,
            personal_candidate_logins=set(personal_candidate_logins),
            martingale_snapshot=martingale_snapshot,
        )
        result["martingale"] = martingale_snapshot.summary(analysis_request.rules.excluded_martingale_levels)
        result["risk_management"] = risk_filter.summary()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ClickHouse sweep query failed") from exc


@app.post("/api/abook/book-analytics")
def book_analytics(
    request: BookAnalyticsRequest,
    repository: ClickHouseRepository = Depends(get_repository),
) -> dict:
    try:
        analysis_payload = analysis(request.analysis, repository)
        accounts = analysis_payload.get("accounts", [])
        abook_keys = {
            (str(account["platform"]), int(account["login"]))
            for account in accounts
            if account.get("cohort") == "abook_candidate"
        }
        if request.abook_accounts:
            abook_keys = {(item.platform, int(item.login)) for item in request.abook_accounts}
        daily_rows = _fetch_daily_rows(repository, request.analysis)
        symbol_method = getattr(repository, "fetch_book_symbol_rows", None)
        turnover_method = getattr(repository, "fetch_daily_turnover_rows", None)
        symbol_rows = {
            "population": symbol_method(request.analysis) if callable(symbol_method) else [],
            "abook": symbol_method(request.analysis, account_keys=abook_keys) if callable(symbol_method) else [],
        }
        turnover_rows = {
            "population": turnover_method(request.analysis) if callable(turnover_method) else [],
            "abook": turnover_method(request.analysis, account_keys=abook_keys) if callable(turnover_method) else [],
        }
        context = prepare_analysis_context(
            [], daily_rows=daily_rows, overview_daily_rows=daily_rows,
            selection_start=request.analysis.selection.start.isoformat(),
            selection_end=request.analysis.selection.end.isoformat(),
            validation_start=request.analysis.validation.start.isoformat(),
            validation_end=request.analysis.validation.end.isoformat(),
        )
        result = build_book_analytics(
            context, accounts, abook_keys, request.hedge_cost_bps, symbol_rows, turnover_rows,
        )
        result["coverage"] = analysis_payload.get("coverage", {})
        result["book_counts"] = {
            "population": len(accounts),
            "abook": sum(1 for account in accounts if (str(account["platform"]), int(account["login"])) in abook_keys),
            "bbook": sum(1 for account in accounts if (str(account["platform"]), int(account["login"])) not in abook_keys),
        }
        return result
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ClickHouse book analytics query failed") from exc


def _export_response(request: AnalysisRequest, repository: ClickHouseRepository) -> StreamingResponse:
    payload = analysis(request, repository)
    content = render_abook_csv(payload.get("accounts", []))
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=abook_accounts.csv"},
    )


@app.get("/api/abook/export")
def export(
    request: Optional[AnalysisRequest] = Body(default=None),
    repository: ClickHouseRepository = Depends(get_repository),
) -> StreamingResponse:
    return _export_response(request or AnalysisRequest(), repository)


@app.post("/api/abook/export")
def export_post(
    request: AnalysisRequest,
    repository: ClickHouseRepository = Depends(get_repository),
) -> StreamingResponse:
    return _export_response(request, repository)


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
