"""
GFS GRIB2 기반 Ellrod CAT(Clear Air Turbulence) 추정 모듈
─────────────────────────────────────────────────────────────────────────────
NOMADS에서 GFS U/V 바람을 받아 Ellrod Index를 직접 계산합니다.
(WAFS 가이드 3.1 Ellrod Index 방식과 동일 알고리즘)

알고리즘 (WAFS 가이드 3.1 준거):
  Ellrod TI1 = DEF × VWS × 1e8
  DEF = sqrt(ST² + SH²)  [s⁻¹]
    ST = ∂u/∂x − ∂v/∂y  (stretching deformation)
    SH = ∂v/∂x + ∂u/∂y  (shearing deformation)
  VWS = |ΔV| / Δz        [s⁻¹]  (인접 레벨 간 수직 바람 변화율)
  임계값 (WAFS 가이드 7.2): LGT ≥ 4 / MOD ≥ 6 / SEV ≥ 12

WAFS 표준 CAT 레이어 (가이드 Table 1, 50 hPa 두께):
  FL240=400hPa, FL270=350hPa, FL300=300hPa, FL340=250hPa, FL390=200hPa

• NOMADS filter_gfs_0p25.pl로 경로 bbox만 다운로드 (~700 KB)
  - 변수: UGRD, VGRD (200/250/300/350/400 hPa)
  - 전체 GFS 파일 크기 ~280 MB 대비 ~99.7% 절감
• GCS 또는 /tmp 로컬 캐시 (6h TTL)
• 결과:
  - GeoJSON FeatureCollection (지도 폴리곤)
  - 경로 WP별 매칭 테이블 (결과 화면 텍스트)
─────────────────────────────────────────────────────────────────────────────
필요: cfgrib (pip install cfgrib), eccodes C lib (apt install libeccodes-dev)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests as _req

logger = logging.getLogger(__name__)

# ── 상수 ───────────────────────────────────────────────────────────────────
NOMADS_FILTER   = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
NOMADS_IDX_BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"

CACHE_TTL_SEC  = 6 * 3600          # 6시간 캐시
GCS_ENABLED    = bool(os.environ.get("GCS_WAFS_BUCKET"))
GCS_BUCKET     = os.environ.get("GCS_WAFS_BUCKET", "")

# ── WAFS 표준 CAT 레이어 (가이드 Table 1, 50 hPa 두께) ─────────────────────
# hPa → (WAFS FL, FL 커버 범위, 레이어 두께 m)
WAFS_CAT_LAYERS: Dict[int, Tuple[int, str, int]] = {
    400: (240, "FL220~FL260", 1200),
    350: (270, "FL250~FL290", 1350),
    300: (300, "FL275~FL325", 1550),
    250: (340, "FL315~FL365", 1800),
    200: (390, "FL365~FL415", 2100),
}
# 다운로드할 레벨 (낮은 레벨부터)
WAFS_LEVELS_HPA = sorted(WAFS_CAT_LAYERS.keys(), reverse=True)  # [400,350,300,250,200]

# WP의 FL → 해당 WAFS CAT 레이어 hPa
def _fl_to_wafs_hpa(fl: int) -> int:
    if fl < 255: return 400   # FL240 레이어
    if fl < 285: return 350   # FL270 레이어
    if fl < 320: return 300   # FL300 레이어
    if fl < 365: return 250   # FL340 레이어
    return 200                 # FL390 레이어

# ── Ellrod Index 임계값 (WAFS 가이드 7.2, 0-99 스케일) ─────────────────────
# TI ≥6 = MOD (가이드 권장), TI ≥12 = SEV (경험적)
CAT_THRESHOLDS = [
    ("SEV", 12.0, "#CC0000", 4),   # Ellrod TI ≥ 12
    ("MOD",  6.0, "#FF6600", 3),   # Ellrod TI ≥ 6
    ("LGT",  4.0, "#FFB300", 2),   # Ellrod TI ≥ 4
]
CAT_LABEL_KO = {"SEV": "심한 터뷸런스", "MOD": "보통 터뷸런스",
                "LGT": "약한 터뷸런스", "NIL": "터뷸런스 없음"}


# ── bbox / 파일 선택 ────────────────────────────────────────────────────────

def _bbox_from_route(waypoints: List[Dict], pad: float = 4.0
                     ) -> Tuple[float, float, float, float]:
    """(south, north, west, east) 계산, 경도 0-360 정규화 안 함."""
    lats = [w["lat"] for w in waypoints if w.get("lat") is not None]
    lons = [w.get("lng", w.get("lon", 0)) for w in waypoints]
    return (round(max(-90, min(lats) - pad), 2),
            round(min( 90, max(lats) + pad), 2),
            round(min(lons) - pad, 2),
            round(max(lons) + pad, 2))


def _select_gfs_cycle(etd_utc: datetime) -> Tuple[str, int, int]:
    """
    ETD 기준으로 가장 가까운 사용 가능한 GFS 사이클과 예보 시간 선택.
    Returns: (date_str "YYYYMMDD", cycle_hour 0/6/12/18, fhour 0-384)
    """
    now_utc = datetime.now(timezone.utc)

    candidates = []
    for delta_day in range(3):
        d = now_utc - timedelta(days=delta_day)
        for cyc in [18, 12, 6, 0]:
            avail = d.replace(hour=cyc, minute=0, second=0, microsecond=0)
            if avail <= now_utc - timedelta(hours=5):   # 발행 후 최소 5h 대기
                candidates.append(avail)

    if not candidates:
        candidates = [now_utc.replace(hour=0, minute=0, second=0, microsecond=0)]

    best = candidates[0]
    diff_h = max(0, (etd_utc - best).total_seconds() / 3600)
    # GFS 예보 시간 후보 (3h 간격)
    fhour = int(round(diff_h / 3) * 3)
    fhour = max(0, min(fhour, 120))   # 0~120h

    return best.strftime("%Y%m%d"), best.hour, fhour


# ── 캐시 ────────────────────────────────────────────────────────────────────

def _cache_key(date_str: str, cycle: int, fhour: int,
               bbox: tuple) -> str:
    raw = f"gfscat_{date_str}_{cycle:02d}_{fhour:03d}_{bbox}"
    return hashlib.md5(raw.encode()).hexdigest()[:14]


def _local_cache_path(key: str) -> Path:
    return Path(tempfile.gettempdir()) / f"wafs_{key}.json"


def _cache_load(key: str) -> Optional[Dict]:
    p = _local_cache_path(key)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > CACHE_TTL_SEC:
        p.unlink(missing_ok=True)
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _cache_save(key: str, data: Dict) -> None:
    try:
        _local_cache_path(key).write_text(
            json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"WAFS 캐시 저장 실패: {e}")


def _gcs_load(key: str) -> Optional[Dict]:
    if not GCS_ENABLED:
        return None
    try:
        from google.cloud import storage as gcs
        blob = gcs.Client().bucket(GCS_BUCKET).blob(f"wafs_cache/{key}.json")
        if not blob.exists():
            return None
        if time.time() - float((blob.metadata or {}).get("saved_at", 0)) > CACHE_TTL_SEC:
            return None
        return json.loads(blob.download_as_text())
    except Exception as e:
        logger.warning(f"GCS WAFS 캐시 읽기 실패: {e}")
        return None


def _gcs_save(key: str, data: Dict) -> None:
    if not GCS_ENABLED:
        return
    try:
        from google.cloud import storage as gcs
        blob = gcs.Client().bucket(GCS_BUCKET).blob(f"wafs_cache/{key}.json")
        blob.metadata = {"saved_at": str(time.time())}
        blob.upload_from_string(json.dumps(data, ensure_ascii=False),
                                content_type="application/json")
    except Exception as e:
        logger.warning(f"GCS WAFS 캐시 저장 실패: {e}")


# ── NOMADS 다운로드 ─────────────────────────────────────────────────────────

def _build_filter_url(date_str: str, cycle: int, fhour: int,
                      bbox: Tuple[float, float, float, float]) -> str:
    """
    NOMADS filter_gfs_0p25.pl URL 생성.
    - 변수: UGRD, VGRD (200/250/300/350/400 mb) — WAFS 표준 5개 레이어
    - bbox 지정으로 경로 주변만 다운로드
    """
    s, n, w, e = bbox
    # 경도를 0~360 범위로 변환 (NOMADS 요구사항)
    w360 = w + 360 if w < 0 else w
    e360 = e + 360 if e < 0 else e

    file_name = f"gfs.t{cycle:02d}z.pgrb2.0p25.f{fhour:03d}"
    dir_path  = f"%2Fgfs.{date_str}%2F{cycle:02d}%2Fatmos"

    # WAFS Table 1 기준 CAT 레이어: 200/250/300/350/400 hPa
    params = (
        f"file={file_name}"
        f"&lev_200_mb=on&lev_250_mb=on&lev_300_mb=on&lev_350_mb=on&lev_400_mb=on"
        f"&var_UGRD=on&var_VGRD=on"
        f"&subregion=&leftlon={w360:.2f}&rightlon={e360:.2f}"
        f"&toplat={n:.2f}&bottomlat={s:.2f}"
        f"&dir={dir_path}"
    )
    return f"{NOMADS_FILTER}?{params}"


def _download_grib2(url: str, timeout: int = 30) -> Optional[bytes]:
    logger.info(f"NOMADS GFS 다운로드: {url[:110]}...")
    try:
        resp = _req.get(url, timeout=timeout)
        if resp.status_code != 200:
            logger.warning(f"NOMADS 응답 {resp.status_code}")
            return None
        if not resp.content[:4] == b'GRIB':
            logger.warning(f"GRIB2 magic 불일치: {resp.content[:20]}")
            return None
        logger.info(f"다운로드 완료: {len(resp.content)/1024:.1f} KB")
        return resp.content
    except Exception as e:
        logger.warning(f"NOMADS 다운로드 실패: {e}")
        return None


# ── GRIB2 파싱 + Ellrod Index 계산 ──────────────────────────────────────────

def _parse_wind_shear_grid(grib2_bytes: bytes) -> Optional[Dict]:
    """
    cfgrib으로 GRIB2 파싱 → 200/250/300/350/400 hPa U/V 추출
    → Ellrod TI1 (WAFS 가이드 3.1 알고리즘) 계산

    Ellrod TI1 = DEF × VWS × 1e8  (WAFS 0-99 스케일)
      DEF = sqrt(ST² + SH²)  [s⁻¹]  — 수평 변형률
        ST = ∂u/∂x − ∂v/∂y  (stretching deformation)
        SH = ∂v/∂x + ∂u/∂y  (shearing deformation)
      VWS = |ΔV| / Δz        [s⁻¹]  — 레이어당 수직 바람 변화율

    Returns:
        {
          "lats": 1D array,
          "lons": 1D array,
          "shear_2d": np.ndarray  # shape (n_lat, n_lon), Ellrod TI 최댓값
          "wind": {...}           # 레벨별 wind dict (디버그용)
        }
    """
    try:
        import cfgrib
    except ImportError:
        logger.error("cfgrib 미설치. pip install cfgrib 필요.")
        return None

    tmp = Path(tempfile.gettempdir()) / f"gfs_wind_{os.getpid()}.grib2"
    tmp.write_bytes(grib2_bytes)

    try:
        datasets = cfgrib.open_datasets(str(tmp))
        wind_data: Dict[int, Dict] = {}  # {pressure_mb: {"u": m/s, "v": m/s, ...}}

        for ds in datasets:
            u_var = v_var = None
            for var in ds.data_vars:
                sn = ds[var].attrs.get("GRIB_shortName", "")
                if sn in ("u", "10u") or "UGRD" in ds[var].attrs.get("GRIB_name", ""):
                    u_var = var
                if sn in ("v", "10v") or "VGRD" in ds[var].attrs.get("GRIB_name", ""):
                    v_var = var
            if not (u_var and v_var):
                continue

            u_da = ds[u_var]
            v_da = ds[v_var]
            level_coord = None
            for c in ["pressure", "isobaricInhPa", "level"]:
                if c in u_da.coords:
                    level_coord = c
                    break
            if level_coord is None:
                continue

            lats_da = u_da.coords.get("latitude",  u_da.coords.get("lat",  None))
            lons_da = u_da.coords.get("longitude", u_da.coords.get("lon", None))
            if lats_da is None or lons_da is None:
                continue

            lat_vals = lats_da.values
            lon_vals = lons_da.values
            lon_vals = np.where(lon_vals > 180, lon_vals - 360, lon_vals)

            for p_val in u_da[level_coord].values:
                p_mb = int(p_val)
                if p_mb not in WAFS_CAT_LAYERS:   # 200/250/300/350/400 hPa만
                    continue
                u_ms = u_da.sel({level_coord: p_val}).values  # m/s (GRIB2 원본)
                v_ms = v_da.sel({level_coord: p_val}).values
                wind_data[p_mb] = {
                    "u": u_ms, "v": v_ms,
                    "lats": lat_vals, "lons": lon_vals,
                }

        if not wind_data:
            logger.warning("파싱된 바람 데이터 없음")
            return None

        ref_lev = sorted(wind_data.keys())[0]
        lats = wind_data[ref_lev]["lats"]
        lons = wind_data[ref_lev]["lons"]

        # ── Ellrod TI1 계산 ────────────────────────────────────────────────
        # 레이어 쌍: (상층 hPa, 하층 hPa)  WAFS 인접 레이어
        layer_pairs = [(p, q) for p, q in zip(
            sorted(WAFS_CAT_LAYERS.keys()),          # [200,250,300,350,400]
            sorted(WAFS_CAT_LAYERS.keys())[1:],      # [250,300,350,400]
        )]  # → [(200,250),(250,300),(300,350),(350,400)]

        # 격자 간격 (m)
        dlat_deg = abs(float(lats[1]) - float(lats[0])) if len(lats) > 1 else 0.25
        dlon_deg = abs(float(lons[1]) - float(lons[0])) if len(lons) > 1 else 0.25
        R_EARTH  = 6_371_000.0
        dy       = dlat_deg * (math.pi / 180) * R_EARTH  # m (일정)

        # 위도별 dx (m) — 2D
        lat2d    = lats[:, np.newaxis] * np.ones((1, len(lons)))
        dx2d     = dlon_deg * (math.pi / 180) * R_EARTH * np.cos(np.radians(lat2d))
        dx2d     = np.where(dx2d < 1.0, 1.0, dx2d)  # 극 근처 0 방지

        ti_layers = []
        for upper_hpa, lower_hpa in layer_pairs:
            if upper_hpa not in wind_data or lower_hpa not in wind_data:
                continue

            u_up = wind_data[upper_hpa]["u"]   # m/s
            v_up = wind_data[upper_hpa]["v"]
            u_lo = wind_data[lower_hpa]["u"]
            v_lo = wind_data[lower_hpa]["v"]

            # 레이어 두께 (m): WAFS_CAT_LAYERS에서 하층 레이어 두께 사용
            dz_m = float(WAFS_CAT_LAYERS[lower_hpa][2])

            # 레이어 평균 바람
            u_avg = (u_up + u_lo) / 2.0
            v_avg = (v_up + v_lo) / 2.0

            # 수평 변형률 DEF [s⁻¹] — numpy.gradient로 유한 차분
            # axis=1: 경도 방향(x), axis=0: 위도 방향(y)
            du_dx = np.gradient(u_avg, axis=1) / dx2d
            du_dy = np.gradient(u_avg, axis=0) / dy
            dv_dx = np.gradient(v_avg, axis=1) / dx2d
            dv_dy = np.gradient(v_avg, axis=0) / dy

            ST  = du_dx - dv_dy          # stretching deformation [s⁻¹]
            SH  = dv_dx + du_dy          # shearing deformation   [s⁻¹]
            DEF = np.sqrt(ST**2 + SH**2) # total deformation      [s⁻¹]

            # 수직 바람 변화율 VWS [s⁻¹]
            du  = u_up - u_lo
            dv  = v_up - v_lo
            VWS = np.sqrt(du**2 + dv**2) / dz_m

            # Ellrod TI1 × 1e8 → WAFS 0-99 스케일
            ti = DEF * VWS * 1e8
            ti = np.where(np.isfinite(ti), ti, 0.0)
            ti_layers.append(ti)
            logger.debug(f"Ellrod TI layer {upper_hpa}-{lower_hpa}hPa: "
                         f"max={np.nanmax(ti):.2f}, p99={np.nanpercentile(ti,99):.2f}")

        if not ti_layers:
            return None

        # WAFS Max grid 권장 (가이드 7.2.1)
        ellrod_max = np.maximum.reduce(ti_layers)

        logger.info(f"Ellrod TI max={np.nanmax(ellrod_max):.2f}, "
                    f"MOD(≥6) 격자: {np.sum(ellrod_max >= 6)}, "
                    f"SEV(≥12) 격자: {np.sum(ellrod_max >= 12)}")

        return {
            "lats":     lats,
            "lons":     lons,
            "shear_2d": ellrod_max,   # 키 이름 유지 (하위 호환)
            "wind":     wind_data,
        }

    except Exception as e:
        logger.error(f"GRIB2 파싱/Ellrod 계산 오류: {e}", exc_info=True)
        return None
    finally:
        tmp.unlink(missing_ok=True)


# ── Shear 격자 → GeoJSON 폴리곤 ─────────────────────────────────────────────

def _shear_to_geojson(grid: Dict) -> List[Dict]:
    """
    수직 Wind Shear 2D 격자에서 CAT 레벨별 등치선 폴리곤 추출.
    scikit-image find_contours 사용. 없으면 마스크 사각형 방식.
    """
    lats     = grid["lats"]
    lons     = grid["lons"]
    shear_2d = np.array(grid["shear_2d"], dtype=float)

    # NaN 처리
    shear_2d = np.where(np.isfinite(shear_2d), shear_2d, 0.0)

    if lats.ndim == 1 and lons.ndim == 1:
        lon2d, lat2d = np.meshgrid(lons, lats)
    else:
        lon2d, lat2d = lons, lats

    from scipy.ndimage import gaussian_filter
    shear_smooth = gaussian_filter(shear_2d, sigma=1.5)

    features = []

    # dlat/dlon 추정
    dlat = abs(float(lat2d[1, 0]) - float(lat2d[0, 0])) / 2 if lat2d.shape[0] > 1 else 0.25
    dlon = abs(float(lon2d[0, 1]) - float(lon2d[0, 0])) / 2 if lat2d.shape[1] > 1 else 0.25

    try:
        from skimage.measure import find_contours
        use_contour = True
    except ImportError:
        use_contour = False

    for lvl, thr, color, sev in CAT_THRESHOLDS:
        if use_contour:
            contours = find_contours(shear_smooth, thr)
            for contour in contours:
                if len(contour) < 4:
                    continue
                coords = []
                for row_f, col_f in contour:
                    ri = int(np.clip(row_f, 0, lat2d.shape[0] - 1))
                    ci = int(np.clip(col_f, 0, lat2d.shape[1] - 1))
                    coords.append([round(float(lon2d[ri, ci]), 3),
                                   round(float(lat2d[ri, ci]), 3)])
                if len(coords) < 3:
                    continue
                coords.append(coords[0])
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {"cat_level": lvl, "color": color,
                                   "severity": sev,
                                   "ellrod_ti_threshold": thr,
                                   "algorithm": "Ellrod TI1 (GFS-based)"},
                })
        else:
            # 마스크 → 격자 사각형
            mask = shear_smooth >= thr
            rows, cols = np.where(mask)
            for r, c in zip(rows.tolist(), cols.tolist()):
                la = float(lat2d[r, c])
                lo = float(lon2d[r, c])
                ti_val = float(shear_2d[r, c])
                coords = [
                    [lo - dlon, la - dlat], [lo + dlon, la - dlat],
                    [lo + dlon, la + dlat], [lo - dlon, la + dlat],
                    [lo - dlon, la - dlat],
                ]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {"cat_level": lvl, "color": color,
                                   "severity": sev,
                                   "ellrod_ti": round(ti_val, 2),
                                   "algorithm": "Ellrod TI1 (GFS-based)"},
                })

    return features


# ── 공개 API 1: GeoJSON 폴리곤 (지도용) ─────────────────────────────────────

def fetch_wafs_turbulence(
    waypoints: List[Dict],
    etd_utc: Optional[datetime] = None,
    cruise_fls: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    경로 주변 GFS GRIB2 바람 데이터를 다운로드·파싱해
    CAT 수직 Wind Shear 폴리곤 GeoJSON 반환.

    Returns:
        { "geojson": FeatureCollection, "source": str,
          "valid_utc": str, "cache_hit": bool, "error": str|None }
    """
    if len(waypoints) < 2:
        return {"error": "waypoint 2개 이상 필요", "geojson": None}

    if etd_utc is None:
        etd_utc = datetime.now(timezone.utc)

    bbox = _bbox_from_route(waypoints)
    date_str, cycle, fhour = _select_gfs_cycle(etd_utc)
    valid_dt = (datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
                         cycle, 0, 0, tzinfo=timezone.utc)
                + timedelta(hours=fhour))
    key = _cache_key(date_str, cycle, fhour, bbox)

    # 캐시 확인
    cached = _gcs_load(key) or _cache_load(key)
    if cached:
        cached["cache_hit"] = True
        logger.info(f"WAFS 캐시 HIT: {key}")
        return cached

    # 다운로드
    url = _build_filter_url(date_str, cycle, fhour, bbox)
    grib2 = _download_grib2(url)
    if not grib2:
        return {"error": "GFS GRIB2 다운로드 실패 (NOMADS)", "geojson": None,
                "cache_hit": False}

    # 파싱
    grid = _parse_wind_shear_grid(grib2)
    if grid is None:
        return {
            "error": None,
            "geojson": {"type": "FeatureCollection", "features": []},
            "source":  f"NOMADS GFS {date_str}/{cycle:02d}Z +{fhour}h",
            "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:%MZ"),
            "cache_hit": False,
            "warn": "cfgrib 파싱 실패 (eccodes 미설치 또는 변수 없음)",
        }

    # 폴리곤 추출
    features = _shear_to_geojson(grid)
    logger.info(f"GFS CAT 폴리곤: {len(features)}개")

    source_str = (f"NOMADS GFS {date_str} {cycle:02d}Z +{fhour}h "
                  f"(valid {valid_dt.strftime('%Y-%m-%d %H:%M')}Z) · "
                  f"Ellrod TI1 (WAFS 가이드 3.1) · 200~400 hPa")
    result = {
        "error":     None,
        "geojson":   {"type": "FeatureCollection", "features": features},
        "source":    source_str,
        "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:%MZ"),
        "bbox":      list(bbox),
        "cache_hit": False,
    }

    _cache_save(key, result)
    _gcs_save(key, result)
    return result


# ── 공개 API 2: 경로 WP별 매칭 테이블 (결과 화면용) ────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


def _point_in_polygon(lat: float, lon: float,
                      ring: List[List[float]]) -> bool:
    """Ray-casting."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
                (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _wp_cat_from_features(lat: float, lon: float,
                           features: List[Dict],
                           near_km: float = 100.0
                           ) -> Optional[Tuple[str, str, int, bool]]:
    """
    (cat_level, color, severity, inside) 반환. 없으면 None.
    SEV(심한 터뷸런스)는 폴리곤 내부만 인정하고, 근처(100km)는 적용하지 않음.
    → 차트(SigWx/ASC)와 일치: 심한 구간은 중국 등 일부 지역으로 한정.
    """
    sev_order = {"SEV": 4, "MOD": 3, "LGT": 2}
    best = None
    best_sev = 0

    for feat in features:
        geom  = feat.get("geometry", {})
        props = feat.get("properties", {})
        lvl   = props.get("cat_level", "LGT")
        sev   = sev_order.get(lvl, 1)
        if sev <= best_sev:
            continue

        if geom["type"] != "Polygon":
            continue
        ring = geom["coordinates"][0]

        # 폴리곤 중심
        c_lats = [c[1] for c in ring]
        c_lons = [c[0] for c in ring]
        c_lat  = sum(c_lats) / len(c_lats)
        c_lon  = sum(c_lons) / len(c_lons)

        inside = _point_in_polygon(lat, lon, ring)
        dist   = _haversine_km(lat, lon, c_lat, c_lon)

        # SEV는 폴리곤 내부만 인정(근처 100km 미적용) — 전 구간 SEV 오표기 방지
        if lvl == "SEV":
            accept = inside
        else:
            accept = inside or dist <= near_km

        if accept:
            best_sev = sev
            best = (lvl, props.get("color", "#FF6600"), sev, inside)

    return best


def match_wafs_to_route(
    flight_data: List[Dict],
    etd_utc: Optional[datetime] = None,
    cruise_fls: Optional[List[int]] = None,
) -> List[Dict]:
    """
    OFP 경로(flight_data) WP에 대해 터뷸런스 폴리곤 매칭.
    NOMADS GFS U/V 기반 Ellrod Index 사용 (WAFS 가이드 3.1).
    Returns 결과 테이블 (grouped) 또는 경고 행.
    """
    if not flight_data:
        return []

    def _get_fl(row: Dict) -> Optional[int]:
        """fl 키를 여러 형식에서 추출 (int 반환)."""
        for key in ("fl", "FL (Flight Level)", "FL", "flight_level"):
            val = row.get(key)
            if val is None:
                continue
            try:
                return int(str(val).strip())
            except (ValueError, TypeError):
                pass
        return None

    def _get_actm(row: Dict) -> str:
        """actm 키를 여러 형식에서 추출."""
        for key in ("actm", "ACTM (Accumulated Time)", "ACTM", "time_utc",
                    "Estimated Time (Z)"):
            val = row.get(key)
            if val:
                return str(val).strip()
        return "—"

    wps = []
    for row in flight_data:
        lat = row.get("lat")
        lon = row.get("lon") or row.get("lng")
        if lat is None or lon is None:
            continue
        wps.append({
            "lat":  float(lat),
            "lng":  float(lon),
            "name": (row.get("Waypoint") or row.get("ident") or "").strip(),
            "fl":   _get_fl(row),
            "actm": _get_actm(row),
        })

    if len(wps) < 2:
        return []

    # WAFS/GFS 데이터 가져오기
    wafs = fetch_wafs_turbulence(wps, etd_utc=etd_utc, cruise_fls=cruise_fls)

    if wafs.get("error"):
        return [{"_warning_row": True,
                 "warn_msg": f"GFS CAT 다운로드 실패: {wafs['error']}"}]

    warn = wafs.get("warn")
    if warn:
        return [{"_warning_row": True, "warn_msg": f"GFS CAT 파싱 경고: {warn}"}]

    features  = (wafs.get("geojson") or {}).get("features", [])
    source    = wafs.get("source", "NOMADS GFS GRIB2")
    valid_utc = wafs.get("valid_utc", "")

    if not features:
        return []   # CAT 없음 (정상)

    # WP별 매칭
    matched = []
    for wp in wps:
        result = _wp_cat_from_features(wp["lat"], wp["lng"], features)
        if result is None:
            continue
        lvl, color, sev, inside = result
        matched.append({
            "waypoint":     wp["name"],
            "lat":          wp["lat"],
            "lon":          wp["lng"],
            "fl":           wp.get("fl"),
            "fl_label":     f"FL{wp['fl']}" if wp.get("fl") else "FL?",
            "actm":         wp.get("actm") or "—",
            "cat_level":    lvl,
            "cat_label_ko": CAT_LABEL_KO.get(lvl, lvl),
            "color":        color,
            "severity":     sev,
            "inside":       inside,
            "affect_type":  "경로 내부" if inside else "근처(100km)",
            "valid_utc":    valid_utc,
            "source":       source,
        })

    if not matched:
        return []

    # 연속 구간 그룹화 (같은 레벨 연속 WP 합치기)
    grouped_rows = []
    grp = [matched[0]]
    for r in matched[1:]:
        if r["cat_level"] == grp[-1]["cat_level"]:
            grp.append(r)
        else:
            grouped_rows.append(grp)
            grp = [r]
    grouped_rows.append(grp)

    table = []
    for grp in grouped_rows:
        first, last = grp[0], grp[-1]
        wp_range   = (first["waypoint"] if first["waypoint"] == last["waypoint"]
                      else f"{first['waypoint']} ~ {last['waypoint']}")
        actm_range = (first["actm"] if first["actm"] == last["actm"]
                      else f"{first['actm']} ~ {last['actm']}")
        fl_vals    = sorted({g["fl"] for g in grp if g.get("fl")})
        fl_label   = (" / ".join(f"FL{f}" for f in fl_vals)
                      if fl_vals else "FL?")
        table.append({
            "waypoint":     wp_range,
            "actm":         actm_range,
            "fl_label":     fl_label,
            "cat_level":    first["cat_level"],
            "cat_label_ko": first["cat_label_ko"],
            "color":        first["color"],
            "wp_count":     len(grp),
            "affect_type":  first["affect_type"],
            "valid_utc":    valid_utc,
            "source":       source,
        })

    return table
