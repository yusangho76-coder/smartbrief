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
    """
    if not HERBIE_AVAILABLE:
        return "", "Herbie 미설치"

    selected = [wp for wp in waypoints if wp.lat is not None and wp.lon is not None][:max_points]
    if not selected:
        return "", "Waypoint 없음"

    cache: Dict[Tuple[datetime, int], Optional[object]] = {}
    # Herbie 저장 경로를 프로젝트 내부로 고정 (권한/경로 문제 방지)
    save_dir = os.path.join(os.getcwd(), ".herbie")
    os.makedirs(save_dir, exist_ok=True)
    rows: List[str] = []
    search = "UGRD:.* mb|VGRD:.* mb|TMP:.* mb|RH:.* mb|HGT:.* mb"

    for wp in selected:
        if not wp.eta_dt:
            continue
        target_hpa = _fl_to_pressure_hpa(wp.fl)
        ds = None
        last_error = None

        for cycle, fxx in _cycle_candidates(wp.eta_dt):
            key = (cycle, fxx)
            if key in cache:
                ds = cache[key]
            else:
                try:
                    print(
                        f"[GFS] try cycle={cycle:%Y-%m-%d %H:%MZ} "
                        f"fxx={fxx:03d} product={product} priority=nomads search={search}"
                    )
                    H = Herbie(
                        cycle,
                        model=model,
                        product=product,
                        fxx=fxx,
                        save_dir=save_dir,
                        priority="nomads",
                    )
                    subset_path = H.download(search=search, overwrite=False, errors="raise")
                    if subset_path and os.path.exists(subset_path):
                        ds = H.xarray(search)
                        # cfgrib가 여러 하이퍼큐브를 반환하는 경우 처리
                        if isinstance(ds, list):
                            ds = next((d for d in ds if "isobaricInhPa" in d.coords), ds[0] if ds else None)
                    cache[key] = ds
                except Exception as e:
                    last_error = e
                    cache[key] = None
                    ds = None

            if ds is not None:
                break

        if ds is None:
            if last_error:
                print(f"[GFS] data not found for {wp.name}: {last_error}")
            continue

        lat_name = _coord_name(ds, ["latitude", "lat"])
        lon_name = _coord_name(ds, ["longitude", "lon"])
        if not lat_name or not lon_name:
            continue

        level = _select_level(ds, target_hpa)
        if level is None:
            continue

        try:
            interp_ds = ds.interp({lat_name: wp.lat, lon_name: wp.lon})
            interp_ds = interp_ds.sel(isobaricInhPa=level, method="nearest")

            u = _get_var(interp_ds, ["u", "UGRD"])
            v = _get_var(interp_ds, ["v", "VGRD"])
            t = _get_var(interp_ds, ["t", "TMP"])
            rh = _get_var(interp_ds, ["r", "rh", "RH"])
            hgt = _get_var(interp_ds, ["gh", "HGT", "z"])

            if u is None or v is None or t is None or rh is None:
                continue

            u_ms = float(u.values)
            v_ms = float(v.values)
            wind_kt = _ms_to_kt((u_ms ** 2 + v_ms ** 2) ** 0.5)
            temp_c = float(t.values) - 273.15
            rh_pct = float(rh.values)

            # 간단한 전단 계산 (인접 상/하층)
            shear_val = "N/A"
            if "isobaricInhPa" in ds.coords:
                levels = [float(x) for x in ds.coords["isobaricInhPa"].values]
                lower, upper = _get_bracketing_levels(levels, level)
                if lower and upper:
                    ds_low = ds.sel(isobaricInhPa=lower, method="nearest").interp({lat_name: wp.lat, lon_name: wp.lon})
                    ds_up = ds.sel(isobaricInhPa=upper, method="nearest").interp({lat_name: wp.lat, lon_name: wp.lon})
                    u_low = _get_var(ds_low, ["u", "UGRD"])
                    v_low = _get_var(ds_low, ["v", "VGRD"])
                    u_up = _get_var(ds_up, ["u", "UGRD"])
                    v_up = _get_var(ds_up, ["v", "VGRD"])
                    hgt_low = _get_var(ds_low, ["gh", "HGT", "z"])
                    hgt_up = _get_var(ds_up, ["gh", "HGT", "z"])
                    if u_low is not None and v_low is not None and u_up is not None and v_up is not None:
                        du = float(u_up.values) - float(u_low.values)
                        dv = float(v_up.values) - float(v_low.values)
                        wind_diff_kt = _ms_to_kt((du ** 2 + dv ** 2) ** 0.5)
                        if hgt_low is not None and hgt_up is not None:
                            dz_m = abs(float(hgt_up.values) - float(hgt_low.values))
                            if dz_m > 0:
                                dz_ft = dz_m * 3.28084
                                shear_val = f"{wind_diff_kt / (dz_ft / 1000):.1f}"

            icing = "가능" if (-20 <= temp_c <= 0 and rh_pct >= 80) else "낮음"

            eta_str = wp.eta_dt.strftime("%H:%MZ")
            rows.append(
                f"| {eta_str} | {wp.name} | FL{wp.fl or 'N/A'} | {wind_kt:.0f} | {shear_val} | {icing} | T={temp_c:.1f}°C, RH={rh_pct:.0f}% |"
            )
        except Exception:
            continue

    if not rows:
        return "", "GFS 데이터 없음"

    header = "| 예상 시간 (UTC) | Waypoint | 고도(FL) | 풍속(kt) | 전단(kt/1000ft) | 착빙 가능성 | 참고 |"
    sep = "|---|---|---|---|---|---|---|"
    return "\n".join([header, sep] + rows), "OK"
