#!/usr/bin/env python3
"""
SigWx 차트 분석 정확도 테스트: 좌표 기반 경로 + 경로 상 픽셀 색상 샘플링만 사용.
(Vision/OCR/OpenCV 경로 추출 없음)

실행: python test/test_sigwx_color_sampling.py [PDF경로]

테스트 결과: 경로→픽셀 매핑이 차트 여백/레이아웃과 맞지 않아 경로 상 샘플이 전부
배경으로 나옴. 차트 이미지 자동 분석은 정확도 확보 불가 → API 기반만 사용 권장.
"""

import os
import sys
import re

# 프로젝트 루트
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# WAFS/SigWx 표준 색상 (RGB) - aviationweather.gov 기준
COLOR_RANGES = {
    "SEV_turb": ((200, 0, 0), (255, 60, 60)),      # 빨강
    "MOD_turb": ((200, 150, 0), (255, 255, 100)),  # 노랑/주황
    "LGT_turb": ((0, 200, 255), (80, 255, 255)),  # 시안
    "CB":       ((0, 180, 0), (100, 255, 100)),   # 초록
    "Jet":      ((0, 100, 200), (100, 200, 255)), # 파랑
}


def _in_range(rgb, lo, hi):
    return all(lo[i] <= rgb[i] <= hi[i] for i in range(3))


def classify_pixel(rgb):
    for name, (lo, hi) in COLOR_RANGES.items():
        if _in_range(rgb, lo, hi):
            return name
    return "background"


def extract_image_bounds_from_sigwx(page_text: str):
    lat_pattern = r"([NS])(\d{2})"
    lon_pattern = r"(\d{3})([EW])"
    lat_values = []
    for m in re.findall(lat_pattern, page_text):
        v = int(m[1])
        lat_values.append(v if m[0] == "N" else -v)
    lon_values = []
    for m in re.findall(lon_pattern, page_text):
        v = int(m[0])
        lon_values.append(v if m[1] == "E" else -v)
    return {
        "min_lat": min(lat_values) if lat_values else -40,
        "max_lat": max(lat_values) if lat_values else 40,
        "min_lon": min(lon_values) if lon_values else 100,
        "max_lon": max(lon_values) if lon_values else 180,
    }


def geo_to_pixel(lat, lon, bounds, w, h):
    """날짜선 보정: 경도 -180~-120 등 서반구는 180 연속으로 취급 (100~180 다음 180~240→-120)."""
    lat_range = bounds["max_lat"] - bounds["min_lat"] or 1
    lon_min, lon_max = bounds["min_lon"], bounds["max_lon"]
    # 서반구 경도(-180~0)를 180~360 스타일로 취급해 동반구와 이어 붙일 수 있음
    lon_eff = lon if lon >= 0 else lon + 360
    lon_min_eff = lon_min if lon_min >= 0 else lon_min + 360
    lon_max_eff = lon_max if lon_max >= 0 else lon_max + 360
    if lon_eff < lon_min_eff:
        lon_eff += 360  # 100E~180 + 180~240(-120W) 구간
    lon_range = (lon_max_eff - lon_min_eff) or 1
    x = int(w * (lon_eff - lon_min_eff) / lon_range)
    y = int(h * (1 - (lat - bounds["min_lat"]) / lat_range))
    return (max(0, min(x, w - 1)), max(0, min(y, h - 1)))


def run_test(pdf_path: str):
    print("=" * 60)
    print("SigWx 좌표+색상 샘플링 테스트")
    print("=" * 60)
    print(f"PDF: {pdf_path}\n")

    # 1) Flight data (lat/lon 있는 WP만)
    from flightplanextractor import extract_flight_data_from_pdf

    flight_data = extract_flight_data_from_pdf(pdf_path, save_temp=False)
    if not flight_data:
        print("FAIL: flight_data 추출 실패")
        return False

    wps_with_coords = [
        r for r in flight_data
        if r.get("lat") is not None and r.get("lon") is not None
    ]
    print(f"1) Waypoint (좌표 있음): {len(wps_with_coords)} / {len(flight_data)}")

    if len(wps_with_coords) < 2:
        print("FAIL: 좌표 있는 WP가 2개 미만")
        return False

    # 2) SigWx 페이지
    from find_and_analyze_cross_section import find_weather_chart_pages_before_notam

    pages = find_weather_chart_pages_before_notam(pdf_path)
    if "sigwx1" not in pages:
        print("FAIL: sigwx1 페이지 없음")
        return False

    sigwx_page = pages["sigwx1"]
    print(f"2) SigWx 페이지 (0-based): {sigwx_page}")

    # 3) 페이지 텍스트 → bounds
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[sigwx_page]
        page_text = page.extract_text() or ""

    bounds = extract_image_bounds_from_sigwx(page_text)
    print(f"3) 이미지 범위: lat {bounds['min_lat']}~{bounds['max_lat']}, lon {bounds['min_lon']}~{bounds['max_lon']}")

    # 4) 페이지 → 이미지
    try:
        from pdf2image import convert_from_path
    except ImportError:
        print("FAIL: pdf2image 없음. pip install pdf2image")
        return False

    images = convert_from_path(pdf_path, first_page=sigwx_page + 1, last_page=sigwx_page + 1, dpi=150)
    if not images:
        print("FAIL: SigWx 페이지 이미지 변환 실패")
        return False

    img = images[0]
    try:
        import numpy as np

        arr = np.array(img)
    except ImportError:
        print("FAIL: numpy 없음")
        return False

    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    h, w = arr.shape[0], arr.shape[1]
    print(f"4) 이미지 크기: {w} x {h}")

    # 5) WP → 픽셀, 구간별 샘플링 및 색상 분류
    pixels_by_wp = []
    for r in wps_with_coords:
        x, y = geo_to_pixel(float(r["lat"]), float(r["lon"]), bounds, w, h)
        pixels_by_wp.append((r.get("Waypoint", ""), x, y))

    samples_per_segment = 30
    segment_results = []

    for i in range(len(pixels_by_wp) - 1):
        x1, y1 = pixels_by_wp[i][1], pixels_by_wp[i][2]
        x2, y2 = pixels_by_wp[i + 1][1], pixels_by_wp[i + 1][2]
        wp1, wp2 = pixels_by_wp[i][0], pixels_by_wp[i + 1][0]

        counts = {"background": 0, "SEV_turb": 0, "MOD_turb": 0, "LGT_turb": 0, "CB": 0, "Jet": 0}
        for j in range(samples_per_segment + 1):
            t = j / (samples_per_segment or 1)
            x = int(x1 + t * (x2 - x1))
            y = int(y1 + t * (y2 - y1))
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            rgb = tuple(int(v) for v in arr[y, x, :3])
            cat = classify_pixel(rgb)
            counts[cat] = counts.get(cat, 0) + 1

        total = samples_per_segment + 1
        segment_results.append({
            "wp1": wp1,
            "wp2": wp2,
            "counts": counts,
            "total": total,
        })

    # 6) 결과 출력 및 정확도 지표
    print("\n5) 구간별 색상 샘플링 결과 (경로 상 픽셀 기준)")
    print("-" * 60)

    any_turb = False
    for seg in segment_results:
        c = seg["counts"]
        t = seg["total"]
        pct_bg = 100 * c["background"] / t
        pct_sev = 100 * c["SEV_turb"] / t
        pct_mod = 100 * c["MOD_turb"] / t
        pct_lgt = 100 * c["LGT_turb"] / t
        if pct_sev > 5 or pct_mod > 5 or pct_lgt > 5:
            any_turb = True
        label = f"{seg['wp1']} → {seg['wp2']}"
        print(f"  {label:<25} background={pct_bg:.0f}%  SEV={pct_sev:.0f}%  MOD={pct_mod:.0f}%  LGT={pct_lgt:.0f}%")

    print("-" * 60)
    if any_turb:
        print("  → 터뷸런스 색상이 일부 구간에서 감지됨 (차트와 비교 필요)")
    else:
        print("  → 경로 상 픽셀 대부분이 background. (범위/해상도/차트 레이아웃 점검 필요)")

    # 7) 샘플 픽셀 실제 RGB (경로 중간 몇 군데)
    print("\n6) 경로 상 샘플 픽셀 실제 RGB (검증용)")
    for idx in [0, len(pixels_by_wp) // 2, len(pixels_by_wp) - 1]:
        name, x, y = pixels_by_wp[idx][0], pixels_by_wp[idx][1], pixels_by_wp[idx][2]
        rgb = tuple(int(v) for v in arr[y, x, :3])
        print(f"  {name}: ({x},{y}) RGB={rgb} → {classify_pixel(rgb)}")

    # 7) 추출된 JPG가 있으면 해당 이미지에서 색상 분포 확인 (차트에 실제로 어떤 색이 있는지)
    jpg_path = pdf_path.replace(".pdf", "_sigwx1.jpg")
    if os.path.isfile(jpg_path):
        print("\n7) 추출된 SigWx JPG 색상 분포 (랜덤 2000픽셀)")
        try:
            from PIL import Image
            import numpy as np

            jimg = np.array(Image.open(jpg_path))
            if jimg.ndim == 2:
                jimg = np.stack([jimg, jimg, jimg], axis=-1)
            hj, wj = jimg.shape[0], jimg.shape[1]
            np.random.seed(42)
            idx = np.random.randint(0, hj * wj, size=min(2000, hj * wj))
            colors_seen = {}
            for i in idx:
                y, x = i // wj, i % wj
                rgb = tuple(int(v) for v in jimg[y, x, :3])
                cat = classify_pixel(rgb)
                colors_seen[cat] = colors_seen.get(cat, 0) + 1
            for k in sorted(colors_seen.keys()):
                print(f"  {k}: {colors_seen[k]} 픽셀 ({100*colors_seen[k]/len(idx):.1f}%)")
        except Exception as e:
            print(f"  JPG 색상 분석 실패: {e}")
    else:
        print("\n7) 추출된 JPG 없음 (색상 분포 스킵)")

    print("\n" + "=" * 60)
    return True


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_pdf = os.path.join(base, "uploads", "20260309_121300_1420be0b_ImportantFile_16.pdf")
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else default_pdf
    if not os.path.isfile(pdf_path):
        print(f"파일 없음: {pdf_path}")
        sys.exit(1)
    ok = run_test(pdf_path)
    sys.exit(0 if ok else 1)
