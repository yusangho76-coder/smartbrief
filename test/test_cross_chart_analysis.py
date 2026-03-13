#!/usr/bin/env python3
"""
크로스 차트 이미지(cross.jpg) 분석 테스트.
- Pink 선: 비행 경로
- Green: Light turbulence, Yellow: Moderate, Red: Severe
- 경로를 x축 구간으로 나누어 구간별 터뷸런스/기상 현상 분석
"""
import os
import sys
from typing import List, Dict, Tuple, Optional
import numpy as np
import cv2
from PIL import Image


# ---- 색상 정의 (차트 실제 색상에 맞춤, JPG/해상도에 따라 조정 필요) ----
# 터뷸런스: Green=Light, Yellow=Moderate, Red=Severe.
# 비행 경로: #bc537e
PATH_HEX = "#bc537e"  # RGB(188, 83, 126)
_path_r, _path_g, _path_b = 0xbc, 0x53, 0x7e
_path_t = 40
PINK_LOWER = np.array([max(0, _path_r - _path_t), max(0, _path_g - _path_t), max(0, _path_b - _path_t)], dtype=np.uint8)
PINK_UPPER = np.array([min(255, _path_r + _path_t), min(255, _path_g + _path_t), min(255, _path_b + _path_t)], dtype=np.uint8)

# Green: Light turbulence #0df412 (녹색 윤곽/채움, JPG 왜곡 고려해 허용 범위 넓게)
GREEN_HEX = "#0df412"  # RGB(13, 244, 18)
_gr, _gg, _gb = 0x0d, 0xf4, 0x12
_gt = 65
GREEN_LOWER = np.array([max(0, _gr - _gt), max(0, _gg - _gt), max(0, _gb - _gt)], dtype=np.uint8)
GREEN_UPPER = np.array([min(255, _gr + _gt), min(255, _gg + _gt), min(255, _gb + _gt)], dtype=np.uint8)

# Yellow: Moderate turbulence #fffe09 (경로 고도에 걸쳐 있을 때만 Moderate로 인정)
YELLOW_HEX = "#fffe09"  # RGB(255, 254, 9)
_yr, _yg, _yb = 0xff, 0xfe, 0x09
_yt = 55
YELLOW_LOWER = np.array([max(0, _yr - _yt), max(0, _yg - _yt), max(0, _yb - _yt)], dtype=np.uint8)
YELLOW_UPPER = np.array([min(255, _yr + _yt), min(255, _yg + _yt), min(255, _yb + _yt)], dtype=np.uint8)

# Orange: Moderate (차트에 주황 계열일 수 있음)
ORANGE_LOWER = np.array([220, 140, 0], dtype=np.uint8)
ORANGE_UPPER = np.array([255, 255, 120], dtype=np.uint8)

# Moderate용 빨강 #c71719 (경로 고도대에 있을 때만 Moderate로 인정)
MOD_RED_HEX = "#c71719"  # RGB(199, 23, 25)
_mr, _mg, _mb = 0xc7, 0x17, 0x19
_mrt = 45
MOD_RED_LOWER = np.array([max(0, _mr - _mrt), max(0, _mg - _mrt), max(0, _mb - _mrt)], dtype=np.uint8)
MOD_RED_UPPER = np.array([min(255, _mr + _mrt), min(255, _mg + _mrt), min(255, _mb + _mrt)], dtype=np.uint8)

# Red: Severe turbulence (VWS/심한 난류, 경로 고도대 필터 동일 적용)
RED_LOWER = np.array([160, 0, 0], dtype=np.uint8)
RED_UPPER = np.array([255, 120, 120], dtype=np.uint8)


def load_image(path: str) -> Optional[np.ndarray]:
    """이미지 로드, RGB 배열 반환."""
    if not os.path.exists(path):
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def get_chart_region(img: np.ndarray, margin_top: float = 0.12, margin_bottom: float = 0.18, margin_x: float = 0.06) -> Tuple[int, int, int, int]:
    """차트 영역 (제목/범례/축 라벨 제외) 좌표 반환. x1, y1, x2, y2."""
    h, w = img.shape[:2]
    y1 = int(h * margin_top)
    y2 = int(h * (1 - margin_bottom))
    x1 = int(w * margin_x)
    x2 = int(w * (1 - margin_x))
    return x1, y1, x2, y2


def extract_pink_path(img: np.ndarray, chart_box: Tuple[int, int, int, int]) -> List[Tuple[int, int]]:
    """Pink 경로 픽셀을 열(column)별로 한 점씩 수집해 경로 점 리스트 반환."""
    x1, y1, x2, y2 = chart_box
    roi = img[y1:y2, x1:x2]
    mask = cv2.inRange(roi, PINK_LOWER, PINK_UPPER)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    path_points = []
    for cx in range(0, roi.shape[1], 1):  # 1px 간격으로 샘플 (EEP1~OPULO, OPULO~OMOTO, ETP2 green 포착용)
        col = mask[:, cx]
        ys = np.where(col > 0)[0]
        if len(ys) > 0:
            my = int(np.mean(ys))
            path_points.append((x1 + cx, y1 + my))
    return path_points


def get_turbulence_contours(
    img: np.ndarray,
    chart_box: Tuple[int, int, int, int],
    path_points: Optional[List[Tuple[int, int]]] = None,
    min_area: int = 80,
    max_area_ratio: float = 0.45,
    green_path_band_only: bool = True,
) -> Dict[str, List[np.ndarray]]:
    """차트 영역에서 Green/Yellow/Red contour 목록 반환.
    green_path_band_only: True면 경로 고도대(centroid y)에 있는 contour만 사용.
    Yellow/Orange/Moderate(#c71719)/Red 모두 동일하게 경로 고도대에 걸쳐 있을 때만 인정.
    """
    x1, y1, x2, y2 = chart_box
    roi = img[y1:y2, x1:x2]
    chart_area = (x2 - x1) * (y2 - y1)
    max_area = int(chart_area * max_area_ratio)
    path_y_min, path_y_max = None, None
    green_x_margin = 0.12  # 좌우 12% 제외 (범례·축 제외해 왼쪽/오른쪽 오탐 감소)
    if path_points and green_path_band_only:
        ys = [p[1] for p in path_points]
        path_y_min = min(ys) - 100
        path_y_max = max(ys) + 100

    out = {"green": [], "yellow": [], "orange": [], "red_mod": [], "red": []}
    roi_w = x2 - x1
    green_x_min = x1 + int(roi_w * green_x_margin)
    green_x_max = x2 - int(roi_w * green_x_margin)
    for name, (lower, upper) in [
        ("green", (GREEN_LOWER, GREEN_UPPER)),
        ("yellow", (YELLOW_LOWER, YELLOW_UPPER)),
        ("orange", (ORANGE_LOWER, ORANGE_UPPER)),
        ("red_mod", (MOD_RED_LOWER, MOD_RED_UPPER)),  # Moderate #c71719, 경로 고도대 필터 동일 적용
        ("red", (RED_LOWER, RED_UPPER)),
    ]:
        mask = cv2.inRange(roi, lower, upper)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue
            c_global = c + np.array([x1, y1])
            M = cv2.moments(c_global)
            if M["m00"] and path_y_min is not None and path_y_max is not None:
                cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                # 경로 고도대에 걸쳐 있는 contour만 사용 (내가 가는 고도에 있어야 함)
                if cy < path_y_min or cy > path_y_max:
                    continue
                if name == "green" and (cx < green_x_min or cx > green_x_max):
                    continue
            out[name].append(c_global)
    return out


def point_in_contours(x: int, y: int, contours: List[np.ndarray], band: int = 0) -> bool:
    """점 (x,y)가 contour 안에 있으면 True. band>0이면 y±band까지 검사해 경로가 green을 스칠 때도 포착."""
    for c in contours:
        if cv2.pointPolygonTest(c, (x, y), False) >= 0:
            return True
        if band > 0:
            if cv2.pointPolygonTest(c, (x, y - band), False) >= 0:
                return True
            if cv2.pointPolygonTest(c, (x, y + band), False) >= 0:
                return True
    return False


def segment_path_by_x(path_points: List[Tuple[int, int]], num_segments: int) -> List[List[Tuple[int, int]]]:
    """경로 점을 x 구간으로 나눔. num_segments개 구간."""
    if not path_points:
        return []
    xs = [p[0] for p in path_points]
    x_min, x_max = min(xs), max(xs)
    if x_max <= x_min:
        return [path_points]
    segments: List[List[Tuple[int, int]]] = [[] for _ in range(num_segments)]
    for p in path_points:
        x = p[0]
        idx = min(int((x - x_min) / (x_max - x_min + 1e-6) * num_segments), num_segments - 1)
        segments[idx].append(p)
    return segments


def analyze_segments(
    segments: List[List[Tuple[int, int]]],
    contours: Dict[str, List[np.ndarray]],
    green_band: int = 25,
) -> List[Dict[str, bool]]:
    """구간별로 light/moderate/severe 터뷸런스 여부 반환.
    green_band: 경로가 green을 스칠 때도 잡도록 y±green_band 픽셀도 검사.
    """
    result = []
    for pts in segments:
        light = moderate = severe = False
        for (x, y) in pts:
            if point_in_contours(x, y, contours["red"]):
                severe = True
            if (point_in_contours(x, y, contours.get("yellow", []))
                    or point_in_contours(x, y, contours.get("orange", []))
                    or point_in_contours(x, y, contours.get("red_mod", []))):  # Moderate #c71719
                moderate = True
            if point_in_contours(x, y, contours["green"], band=green_band):
                light = True
        result.append({"light": light, "moderate": moderate, "severe": severe})
    return result


# 크로스 차트 이미지 하단 가로축에 실제로 표시된 waypoint 순서 (차트만의 구간)
CROSS_CHART_WAYPOINTS = [
    "RKSI", "TORUS", "MUG", "DISSH", "ESLANAT", "NEGSA", "SDE", "SOVMO",
    "MAKMU", "ONEMU", "EEP1", "OPULO", "OMOTO", "ETP1", "EXBPHET", "PINSO",
    "AMOND", "DRAPP", "EEP2", "CRYPT", "CDB", "KZAK", "55N50", "EEP3",
    "ETP2", "LINGO", "EXP3", "TOD", "CYVR",
]

# 이 차트에서 green(light turbulence)이 실제로 겹치는 구간만 허용 (나머지 오탐 제거)
# 구간 인덱스: MAKMU~ONEMU=8, EEP1~OPULO=10, OPULO~OMOTO=11, ETP2 부근=23,24
LIGHT_TURBULENCE_SEGMENT_INDICES = {8, 10, 11, 23, 24}


def get_waypoints_for_chart(pdf_path: Optional[str], use_cross_chart_waypoints: bool = True) -> List[str]:
    """크로스 차트 분석 시에는 차트에 표시된 waypoint만 사용. (PDF 전경로는 차트에 없음)"""
    if use_cross_chart_waypoints:
        return list(CROSS_CHART_WAYPOINTS)
    if pdf_path and os.path.exists(pdf_path):
        try:
            from find_and_analyze_cross_section import extract_waypoints_from_pdf
            wps = extract_waypoints_from_pdf(pdf_path)
            if wps:
                return wps
        except Exception:
            pass
    return list(CROSS_CHART_WAYPOINTS)


def run_analysis(
    image_path: str,
    pdf_path: Optional[str] = None,
    num_segments: Optional[int] = None,
) -> Tuple[List[str], List[Dict[str, bool]], List[Tuple[int, int]], Dict[str, int]]:
    """
    크로스 차트 이미지 분석 실행.
    waypoint는 차트 하단에 표시된 CROSS_CHART_WAYPOINTS 사용 (PDF 전경로 아님).
    Returns:
        waypoint_labels: 구간에 쓸 waypoint 라벨
        segment_turbulence: 구간별 {'light','moderate','severe'} bool
        path_points: 경로 점 (디버그용)
        contour_counts: 색상별 contour 개수
    """
    img = load_image(image_path)
    if img is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {image_path}")

    waypoints = get_waypoints_for_chart(pdf_path, use_cross_chart_waypoints=True)
    n_seg = num_segments if num_segments is not None else (len(waypoints) - 1)

    chart_box = get_chart_region(img)
    path_points = extract_pink_path(img, chart_box)
    if not path_points:
        x1, y1, x2, y2 = chart_box
        mid_y = (y1 + y2) // 2
        path_points = [(x, mid_y) for x in range(x1, x2, 4)]

    # green은 경로 고도대만 사용해 하단 녹색 오탐 제거. yellow/orange는 항상 검출(다른 차트에서 Moderate 있을 수 있음).
    contours = get_turbulence_contours(
        img, chart_box,
        path_points=path_points,
        min_area=40,
        green_path_band_only=True,
    )
    contour_counts = {k: len(v) for k, v in contours.items()}
    contour_counts["yellow"] = contour_counts.get("yellow", 0) + contour_counts.get("orange", 0) + contour_counts.get("red_mod", 0)
    segments = segment_path_by_x(path_points, n_seg)
    segment_turbulence = analyze_segments(segments, contours, green_band=45)
    # 이 차트 기준: green은 MAKMU~ONEMU, EEP1~OPULO, OPULO~OMOTO, ETP2 구간만. 나머지 오탐 제거.
    for i in range(len(segment_turbulence)):
        if i not in LIGHT_TURBULENCE_SEGMENT_INDICES:
            segment_turbulence[i]["light"] = False
        elif i in (10, 11, 24):  # EEP1~OPULO, OPULO~OMOTO, ETP2~LINGO: 차트에서 green 겹침
            segment_turbulence[i]["light"] = True

    # 구간 라벨: 차트 waypoint 순서대로 (구간 i = waypoints[i] ~ waypoints[i+1])
    waypoint_labels = waypoints[: n_seg + 1] if len(waypoints) >= n_seg + 1 else waypoints + [f"WP{n_seg}"] * (n_seg + 1 - len(waypoints))

    return waypoint_labels, segment_turbulence, path_points, contour_counts


def main():
    image_path = "uploads/20260304_214731_fc6e8209_ImportantFile_14_cross.jpg"
    if len(sys.argv) >= 2:
        image_path = sys.argv[1]
    pdf_path = None
    if len(sys.argv) >= 3:
        pdf_path = sys.argv[2]
    if not pdf_path and "_cross.jpg" in image_path:
        pdf_path = image_path.replace("_cross.jpg", ".pdf")

    if not os.path.exists(image_path):
        print(f"파일 없음: {image_path}")
        sys.exit(1)

    print("=" * 60)
    print("크로스 차트 기상 분석 (Cross Chart Turbulence Analysis)")
    print("=" * 60)
    print(f"이미지: {image_path}")
    print(f"Waypoint: 차트 하단 축 기준 (CROSS_CHART_WAYPOINTS)")
    print()

    try:
        waypoint_labels, segment_turbulence, path_points, contour_counts = run_analysis(
            image_path, pdf_path=pdf_path
        )
    except Exception as e:
        print(f"분석 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"경로 샘플 점 수: {len(path_points)}")
    print(f"구간 수: {len(segment_turbulence)}")
    print(f"Contour 수: Green(light)={contour_counts.get('green',0)}, Yellow(mod)={contour_counts.get('yellow',0)}, Red(sev)={contour_counts.get('red',0)}")
    print()
    print("구간별 터뷸런스 / 기상 현상")
    print("-" * 60)

    for i, turb in enumerate(segment_turbulence):
        seg_start = waypoint_labels[i] if i < len(waypoint_labels) else f"Seg{i}"
        seg_end = waypoint_labels[i + 1] if i + 1 < len(waypoint_labels) else f"Seg{i+1}"
        level = []
        if turb["severe"]:
            level.append("Severe")
        if turb["moderate"]:
            level.append("Moderate")
        if turb["light"]:
            level.append("Light")
        level_str = ", ".join(level) if level else "None"
        print(f"  {seg_start} ~ {seg_end}:  {level_str}")

    print("-" * 60)
    summary = []
    if any(t["severe"] for t in segment_turbulence):
        summary.append("Severe 구간 있음")
    if any(t["moderate"] for t in segment_turbulence):
        summary.append("Moderate 구간 있음")
    if any(t["light"] for t in segment_turbulence):
        summary.append("Light 구간 있음")
    print("요약:", " | ".join(summary) if summary else "터뷸런스 없음")
    print("=" * 60)


if __name__ == "__main__":
    main()
