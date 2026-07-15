from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import AnalysisRequest, FilterOptions
from .repository import ClickHouseRepository, RepositoryConfigurationError
from .risk import build_local_risk_filter
from .service import build_account_detail_payload, build_analysis_payload, build_two_stage_payload


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
        risk_filter = build_local_risk_filter(request)
        effective_request = risk_filter.apply(request)
        if risk_filter.is_empty_for(request):
            rows = []
        else:
            excluded_logins = risk_filter.excluded_logins
            rows = repository.fetch_analysis(effective_request, excluded_logins=excluded_logins) if excluded_logins else repository.fetch_analysis(effective_request)
        rows = risk_filter.snapshot.enrich_rows(rows)
        if request.lookback_months is not None:
            payload = build_analysis_payload(
                rows,
                request.lookback_months,
                min_profit_factor=request.min_profit_factor if request.min_profit_factor is not None else request.rules.min_profit_factor,
                min_avg_daily_profit=request.min_avg_daily_profit if request.min_avg_daily_profit is not None else request.rules.min_avg_daily_profit,
            )
            payload["risk_management"] = risk_filter.summary()
            return payload
        rules = request.rules
        payload = build_two_stage_payload(
            rows,
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
            neutral_band_usd=rules.neutral_band_usd,
            min_positive_month_rate=rules.min_positive_month_rate,
            max_top1_day_profit_contribution=rules.max_top1_day_profit_contribution,
            max_peak_leverage_ratio=rules.max_peak_leverage_ratio,
            max_high_leverage_holding_seconds=rules.max_high_leverage_holding_seconds,
            risk_snapshot_status=risk_filter.status,
            min_direction_day_rate_lower_bound=rules.min_direction_day_rate_lower_bound,
            min_stability_score=rules.min_stability_score,
            high_confidence_trades=rules.high_confidence_trades,
            high_confidence_days=rules.high_confidence_days,
            exclude_test_accounts=request.exclude_test_accounts,
        )
        payload["risk_management"] = risk_filter.summary()
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
    repository: ClickHouseRepository = Depends(get_repository),
) -> dict:
    try:
        rows = repository.fetch_account_detail(platform, login, start, end)
        return build_account_detail_payload(rows)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ClickHouse account query failed") from exc


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
