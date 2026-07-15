from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalysisFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: List[str] = Field(default_factory=list)
    logins: List[int] = Field(default_factory=list)


class AnalysisPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def validate_range(self) -> "AnalysisPeriod":
        if self.end < self.start:
            raise ValueError("period end must be on or after start")
        return self


class AnalysisRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_trades: int = Field(default=20, ge=0)
    min_active_days: int = Field(default=5, ge=0)
    min_win_rate: float = Field(default=0.5, ge=0, le=1)
    min_profit_factor: float = Field(default=1.0, ge=0)
    min_payoff_ratio: float = Field(default=1.0, ge=0)
    min_avg_daily_profit: float = Field(default=10.0, ge=0)
    min_selection_monthly_consistency: float = Field(default=0.5, ge=0, le=1)
    neutral_band_usd: float = Field(default=10.0, ge=0)
    min_positive_month_rate: float = Field(default=1.0, ge=0, le=1)
    max_top_day_concentration: float = Field(default=0.5, ge=0, le=1)
    min_direction_day_rate_lower_bound: float = Field(default=0.55, ge=0, le=1)
    min_stability_score: float = Field(default=70.0, ge=0, le=100)
    high_confidence_trades: int = Field(default=100, ge=0)
    high_confidence_days: int = Field(default=30, ge=0)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection: AnalysisPeriod = Field(
        default_factory=lambda: AnalysisPeriod(start=date(2026, 5, 1), end=date(2026, 6, 30))
    )
    validation: AnalysisPeriod = Field(
        default_factory=lambda: AnalysisPeriod(start=date(2026, 7, 1), end=date(2026, 7, 13))
    )
    platforms: List[str] = Field(default_factory=lambda: ["mt5", "hh_mt5"])
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    rules: AnalysisRules = Field(default_factory=AnalysisRules)
    exclude_test_accounts: bool = True

    # Backward-compatible fields for old callers. New callers should use the
    # explicit selection/validation/rules structure.
    start: Optional[date] = None
    end: Optional[date] = None
    lookback_months: Optional[Literal[1, 2, 3]] = None
    min_profit_factor: Optional[float] = Field(default=None, ge=0)
    min_avg_daily_profit: Optional[float] = None

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: List[str]) -> List[str]:
        allowed = {"mt5", "hh_mt5"}
        invalid = set(value) - allowed
        if invalid:
            raise ValueError(f"unsupported platform: {sorted(invalid)}")
        return value or sorted(allowed)

    @model_validator(mode="after")
    def validate_range(self) -> "AnalysisRequest":
        if self.min_profit_factor is not None:
            self.rules.min_profit_factor = self.min_profit_factor
        if self.min_avg_daily_profit is not None:
            self.rules.min_avg_daily_profit = self.min_avg_daily_profit
        if self.selection.end >= self.validation.start:
            raise ValueError("selection must end before validation starts")
        return self


class FilterOptions(BaseModel):
    platforms: List[str]
    groups: List[str]
