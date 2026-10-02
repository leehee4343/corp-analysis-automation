"""기업목록/영업 대상 분류가 공통으로 받는 최근 지표 범위 검색 파라미터 (양 끝 포함).
매출액·영업이익·당기순이익은 백만원, 부채비율은 %."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricRanges:
    revenue_from: float | None = None
    revenue_to: float | None = None
    operating_profit_from: float | None = None
    operating_profit_to: float | None = None
    net_income_from: float | None = None
    net_income_to: float | None = None
    debt_ratio_from: float | None = None
    debt_ratio_to: float | None = None

    def as_dict(self) -> dict[str, tuple[float | None, float | None]]:
        return {
            "revenue": (self.revenue_from, self.revenue_to),
            "operating_profit": (self.operating_profit_from, self.operating_profit_to),
            "net_income": (self.net_income_from, self.net_income_to),
            "debt_ratio": (self.debt_ratio_from, self.debt_ratio_to),
        }
