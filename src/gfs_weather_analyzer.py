"""
GFS 기반 항공기상 파생지표 분석 (Herbie 활용)
한국/동아시아 커버를 위한 전지구 GFS 모델을 사용합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
import os


try:
    from herbie import Herbie  # type: ignore
    HERBIE_AVAILABLE = True
except Exception:
    HERBIE_AVAILABLE = False
    Herbie = None  # type: ignore


@dataclass
class GfsWaypoint:
    name: str
    lat: float
    lon: float
    fl: Optional[int]  # Flight Level (e.g., 370)
    eta_dt: Optional[datetime]  # UTC datetime for waypoint passage


def _fl_to_pressure_hpa(fl: Optional[int]) -> Optional[float]:
    """FL(Flight Level) -> pressure (hPa) 변환 (표준대기 근사)."""
    if fl is None:
        return None
    try:
        alt_ft = int(fl) * 100
        alt_m = alt_ft * 0.3048
        # 표준대기 근사식
        p = 1013.25 * (1 - 2.25577e-5 * alt_m) ** 5.25588
        return p
    except Exception:
        return None


def _nearest_cycle_and_fxx(target: datetime) -> Tuple[datetime, int]:
    """
    GFS 6시간 주기(00/06/12/18)로 cycle을 맞추고 fxx 계산.
    """
    cycle_hour = (target.hour // 6) * 6
    cycle = target.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)
    if target < cycle:
        cycle -= timedelta(hours=6)
    fxx = int(round((target - cycle).total_seconds() / 3600))
    if fxx < 0:
        fxx = 0
    return cycle, fxx


def _cycle_candidates(target: datetime) -> List[Tuple[datetime, int]]:
    """
    최신 cycle 우선, 없으면 직전 cycle 1회만 fallback.
    (예: 06Z 미발행이면 00Z 사용)
    """
    base_cycle, _ = _nearest_cycle_and_fxx(target)
    candidates: List[Tuple[datetime, int]] = []
    for back_steps in range(0, 2):
        cycle = base_cycle - timedelta(hours=6 * back_steps)
        fxx = int(round((target - cycle).total_seconds() / 3600))
        if fxx < 0:
            continue
        candidates.append((cycle, fxx))
    return candidates


def _coord_name(ds, candidates: Iterable[str]) -> Optional[str]:
    for name in candidates:
        if name in ds.coords:
            return name
    for name in candidates:
        for coord in ds.coords:
            if coord.lower() == name.lower():
                return coord
    return None


def _get_var(ds, candidates: Iterable[str]):
    for name in candidates:
        if name in ds.data_vars:
            return ds[name]
    for name in candidates:
        for var in ds.data_vars:
            if var.lower() == name.lower():
                return ds[var]
    return None


def _select_level(ds, target_hpa: Optional[float]) -> Optional[float]:
    if target_hpa is None:
        return None
    if "isobaricInhPa" in ds.coords:
        levels = list(ds.coords["isobaricInhPa"].values)
        if not levels:
            return None
        return float(min(levels, key=lambda x: abs(float(x) - target_hpa)))
    return None


def _get_bracketing_levels(levels: List[float], target: float) -> Tuple[Optional[float], Optional[float]]:
    if not levels:
        return None, None
    levels_sorted = sorted(levels, reverse=True)  # hPa는 낮을수록 상층
    lower = None
    upper = None
    for lv in levels_sorted:
        if lv >= target:
            lower = lv
        if lv <= target and upper is None:
            upper = lv
    if lower == upper:
        return None, None
    return lower, upper


def _ms_to_kt(ms: float) -> float:
    return ms * 1.94384


def build_gfs_summary_markdown(
    waypoints: List[GfsWaypoint],
    model: str = "gfs",
    product: str = "pgrb2.0p25",
    max_points: int = 20,
) -> Tuple[str, str]:
    """
    GFS 기반 파생지표 요약 테이블(마크다운) 생성.
    ※ Herbie GFS 분석은 비활성화됨 (정확도·속도·용량 이슈).
    """
    # Herbie GFS 분석 비활성화 — 앱 속도·용량·정확도 이슈
    return "", "GFS(Herbie) 분석은 비활성화되었습니다."
