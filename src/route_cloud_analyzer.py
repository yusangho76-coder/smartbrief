"""
경로 구름 걸림 + CAPE(대류/CB 가능성) 분석 — Open-Meteo 무료 API 사용.

- waypoint별 cloud_cover_low/mid/high, cape 조회
- FL → 고도대 매핑 후 해당 층 cloud cover로 "구름 걸림" 여부 판단
- CAPE로 "대류 활발(CB 가능성)" 참고용 표시

참고: md/CLOUD_HEIGHT_CB_ST_API_REVIEW.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 15

# 고도대 경계 (m): low 0~3km, mid 3~8km, high 8km~
ALT_LOW_MAX_M = 3000.0
ALT_MID_MAX_M = 8000.0


def fl_to_altitude_m(fl: int) -> float:
    """FL(백피트) → 고도(m). FL350 → 35000 ft → 10668 m."""
    return fl * 100 * 0.3048


def altitude_to_layer(altitude_m: float) -> str:
    """고도(m) → Open-Meteo 층 이름."""
    if altitude_m < ALT_LOW_MAX_M:
        return "low"
    if altitude_m < ALT_MID_MAX_M:
        return "mid"
    return "high"


def _get_fl(row: Dict) -> Optional[int]:
    for key in ("fl", "FL (Flight Level)", "FL", "flight_level"):
        v = row.get(key)
        if v is None:
            continue
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            pass
    return None


def _get_actm(row: Dict) -> str:
    for key in ("actm", "ACTM (Accumulated Time)", "ACTM", "time_utc", "Estimated Time (Z)"):
        v = row.get(key)
        if v:
            return str(v).strip()
    return "—"


def _interpret_hourly(
    fl: Optional[int],
    cloud_low: Optional[float],
    cloud_mid: Optional[float],
    cloud_high: Optional[float],
    cape: Optional[float],
    *,
    cloud_threshold: float = 50.0,
    cape_threshold: float = 1000.0,
) -> Dict[str, Any]:
    """
    Open-Meteo hourly 한 시점 값으로 구름 걸림 여부 + CB 위험도 해석.
    Returns dict: cloud_on_route, cloud_layer, cloud_cover_pct, cb_risk.
    """
    layer = "high"
    cover_raw: Optional[float] = cloud_high
    if fl is not None:
        alt_m = fl_to_altitude_m(fl)
        layer = altitude_to_layer(alt_m)
        if layer == "low":
            cover_raw = cloud_low
        elif layer == "mid":
            cover_raw = cloud_mid
        else:
            cover_raw = cloud_high

    cover_pct: Optional[int] = None
    if cover_raw is not None:
        try:
            cover_pct = int(round(float(cover_raw)))
        except (TypeError, ValueError):
            pass

    cloud_on_route = (cover_pct is not None and cover_pct >= int(cloud_threshold))

    # CB 위험: CAPE 기준
    cb_risk = "—"
    if cape is not None:
        try:
            c = float(cape)
            if c > cape_threshold:
                cb_risk = "높음"
            elif c > 500:
                cb_risk = "보통"
            elif c >= 0:
                cb_risk = "낮음"
        except (TypeError, ValueError):
            pass

    return {
        "cloud_on_route": cloud_on_route,
        "cloud_layer": layer,
        "cloud_cover_pct": cover_pct,
        "cb_risk": cb_risk,
    }


def fetch_route_cloud_cape(
    flight_data: List[Dict],
    etd_utc: Optional[datetime] = None,
    *,
    cloud_threshold: float = 50.0,
    cape_threshold: float = 1000.0,
    max_waypoints: int = 50,
) -> List[Dict]:
    """
    경로 waypoint별 Open-Meteo 구름층 + CAPE 조회 후 테이블용 행 리스트 반환.

    flight_data: OFP 추출 리스트 (lat, lon/lng, fl, actm, Waypoint/ident 등).
    etd_utc: OFP ETD (UTC). None이면 현재 시각.
    Returns: 각 행은 waypoint, lat, lon, fl, fl_label, actm, cloud_on_route,
             cloud_layer, cloud_cover_pct, cape, cb_risk, source, valid_utc.
             실패 시 [{"_warning_row": True, "warn_msg": "..."}].
    """
    if not flight_data:
        return []

    now = datetime.now(timezone.utc)
    ref_dt = etd_utc if etd_utc is not None else now
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    ref_hour = ref_dt.hour

    # waypoint 정규화 (wafs_analyzer와 동일 패턴)
    wps: List[Dict] = []
    for row in flight_data:
        lat = row.get("lat")
        lon = row.get("lon") or row.get("lng")
        if lat is None or lon is None:
            continue
        name = (row.get("Waypoint") or row.get("ident") or "").strip()
        wps.append({
            "lat": float(lat),
            "lng": float(lon),
            "name": name or f"WP{len(wps)+1}",
            "fl": _get_fl(row),
            "actm": _get_actm(row),
        })

    if len(wps) < 1:
        return []

    # 샘플링
    if len(wps) > max_waypoints:
        step = max(1, len(wps) // max_waypoints)
        wps = wps[::step]
        if flight_data and wps[-1] != flight_data[-1]:
            last = flight_data[-1]
            lat = last.get("lat")
            lon = last.get("lon") or last.get("lng")
            if lat is not None and lon is not None:
                wps.append({
                    "lat": float(lat),
                    "lng": float(lon),
                    "name": (last.get("Waypoint") or last.get("ident") or "END").strip(),
                    "fl": _get_fl(last),
                    "actm": _get_actm(last),
                })

    lats = ",".join(str(w["lat"]) for w in wps)
    lons = ",".join(str(w.get("lng", w.get("lon", 0))) for w in wps)

    url = (
        f"{OPENMETEO_URL}?"
        f"latitude={lats}&longitude={lons}"
        "&hourly=cloud_cover_low,cloud_cover_mid,cloud_cover_high,cape"
        "&forecast_days=2"
        "&models=gfs_seamless"
    )

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("Open-Meteo 요청 실패: %s", e)
        return [{"_warning_row": True, "warn_msg": f"Open-Meteo 연결 실패: {e}"}]

    if resp.status_code != 200:
        logger.warning("Open-Meteo HTTP %s", resp.status_code)
        return [{"_warning_row": True, "warn_msg": f"Open-Meteo API 오류: HTTP {resp.status_code}"}]

    try:
        data = resp.json()
    except Exception as e:
        return [{"_warning_row": True, "warn_msg": f"Open-Meteo 응답 파싱 실패: {e}"}]

    if not isinstance(data, list):
        data = [data]

    valid_utc = ref_dt.strftime("%Y-%m-%d %H:%M") + " UTC"
    rows: List[Dict] = []

    for i, wp in enumerate(wps):
        om = data[i] if i < len(data) else (data[0] if data else {})
        hourly = om.get("hourly") or {}

        # 시간 인덱스: ACTM 있으면 hour 오프셋 적용, 없으면 ref_hour
        idx = ref_hour
        actm = wp.get("actm") or "—"
        if actm and actm != "—":
            try:
                parts = str(actm).replace(".", ":").split(":")
                hh = int(parts[0]) if parts else 0
                idx = (ref_hour + hh) % 24
            except (ValueError, IndexError):
                pass

        cl = (hourly.get("cloud_cover_low") or [None])[idx] if idx < 24 else None
        cm = (hourly.get("cloud_cover_mid") or [None])[idx] if idx < 24 else None
        ch = (hourly.get("cloud_cover_high") or [None])[idx] if idx < 24 else None
        cape_val = (hourly.get("cape") or [None])[idx] if idx < 24 else None

        interp = _interpret_hourly(
            wp.get("fl"),
            cl, cm, ch,
            cape_val,
            cloud_threshold=cloud_threshold,
            cape_threshold=cape_threshold,
        )

        fl = wp.get("fl")
        fl_label = f"FL{fl}" if fl is not None else "FL?"

        rows.append({
            "waypoint": wp["name"],
            "lat": wp["lat"],
            "lon": wp.get("lng", wp.get("lon", 0)),
            "fl": fl,
            "fl_label": fl_label,
            "actm": actm,
            "cloud_on_route": interp["cloud_on_route"],
            "cloud_layer": interp["cloud_layer"],
            "cloud_cover_pct": interp["cloud_cover_pct"],
            "cape": float(cape_val) if cape_val is not None else None,
            "cb_risk": interp["cb_risk"],
            "source": "Open-Meteo",
            "valid_utc": valid_utc,
        })

    return rows
