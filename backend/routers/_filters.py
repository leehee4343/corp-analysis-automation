"""기업목록/영업 대상 분류가 공통으로 받는 최근 지표 범위 검색 파라미터 (양 끝 포함).
매출액·영업이익·당기순이익은 백만원, 부채비율은 %."""
from __future__ import annotations

from dataclasses import dataclass
import math

from fastapi import HTTPException


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


METRIC_LABELS = {
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
    "debt_ratio": "부채비율",
}


def validate_metric_ranges(
    ranges: MetricRanges,
    *,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
) -> dict[str, tuple[float | None, float | None]]:
    """목록 API가 받는 모든 숫자 범위를 같은 규칙으로 검증한다.

    빈 값은 제한 없음으로 두고 0과 음수는 유효한 숫자로 보존한다. 구형
    revenue_min/revenue_max 쿼리도 외부 호출 호환성을 위해 같은 검증을 적용한다.
    """
    pairs = [("매출액", revenue_min, revenue_max)]
    pairs.extend((METRIC_LABELS[key], lo, hi) for key, (lo, hi) in ranges.as_dict().items())
    for label, minimum, maximum in pairs:
        for value in (minimum, maximum):
            if value is not None and not math.isfinite(value):
                raise HTTPException(status_code=422, detail=f"{label}에는 유효한 숫자를 입력해 주세요.")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise HTTPException(status_code=422, detail=f"{label} 최소값은 최대값보다 클 수 없습니다.")
    return ranges.as_dict()
