#!/usr/bin/env python3
"""
cross 섹션 차트 이미지에서 항로(마젠타 선)를 따라가며,
어느 waypoint~waypoint 구간에 Light / Moderate / Severe turbulence 후보가 있는지
대략적으로 요약해 보는 테스트 스크립트.

대상:
- 이미지: uploads/20260305_170034_4726e704_ImportantFile_15_cross.jpg
- OFP PDF: uploads/20260305_170034_4726e704_ImportantFile_15.pdf

주의:
- 색상 기준/임계값을 이용한 **실험용 코드**이며, 실제 운항 판단용이 아님.
"""

from pathlib import Path
from typing import Dict, List, Tuple
import re

import numpy as np
from PIL import Image
from google.cloud import vision

from find_and_analyze_cross_section import detect_path_line, extract_waypoints_from_pdf


ROOT = Path(__file__).resolve().parent
IMG_PATH = ROOT / "uploads/20260305_170034_4726e704_ImportantFile_15_cross.jpg"
PDF_PATH = ROOT / "uploads/20260305_170034_4726e704_ImportantFile_15.pdf"


def load_image_rgb(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    return np.array(img)


def extract_waypoints_from_image_with_vision(path: Path) -> List[Tuple[str, int]]:
    """
    cross 차트 하단의 waypoint 라벨을 Vision OCR로 추출.
    반환: [(wp_name, x_center), ...] (좌→우 정렬)
    """
    # Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS) 사용
    client = vision.ImageAnnotatorClient()
    content = path.read_bytes()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    if response.error.message:
        raise RuntimeError(f"Vision OCR 오류: {response.error.message}")

    texts = list(response.text_annotations)[1:]  # 첫 번째는 전체 텍스트
    arr = load_image_rgb(path)
    h, w, _ = arr.shape

    candidates: List[Tuple[str, int, int]] = []
    for t in texts:
        desc = t.description.strip().upper()
        # 알파벳/숫자 3~7자리 정도를 waypoint 후보로 사용
        if not re.fullmatch(r"[A-Z0-9]{3,7}", desc):
            continue
        vs = t.bounding_poly.vertices
        xs = [v.x for v in vs]
        ys = [v.y for v in vs]
        cx = int(sum(xs) / len(xs))
        cy = int(sum(ys) / len(ys))
        # 차트 하단부 텍스트만 사용 (높이의 70% 이후)
        if cy < int(h * 0.7):
            continue
        candidates.append((desc, cx, cy))

    # PDF에서 추출한 실제 경로 waypoint 목록과 교차시켜, 의미 없는 텍스트 필터링
    pdf_waypoints: List[str] = []
    if PDF_PATH.exists():
        try:
            pdf_waypoints = extract_waypoints_from_pdf(str(PDF_PATH))
        except Exception:
            pdf_waypoints = []
    pdf_wp_set = set(pdf_waypoints)

    # x 기준 정렬, 같은 이름은 한 번만 사용하며:
    # - 전부 숫자인 것(예: 1000 hPa) 제외
    # - "PAGE" 등 PDF waypoint 목록에 없는 이름은 가급적 제외
    candidates.sort(key=lambda x: x[1])
    seen = set()
    waypoints: List[Tuple[str, int]] = []
    for name, cx, _ in candidates:
        if name in seen:
            continue
        if re.fullmatch(r"\d+", name):
            continue
        if pdf_wp_set and name not in pdf_wp_set:
            continue
        seen.add(name)
        waypoints.append((name, cx))

    return waypoints


# Photoshop color picker로 찍은 색상들 기반 대표값 (대략)
LIGHT_GREENS = [
    (69, 209, 60),   # #45d13c 근처
    (123, 255, 122), # #7bff7a 근처
]
MODERATE_YELLOWS = [
    (243, 243, 93),  # #f3f35d 근처
    (253, 254, 101), # #fdfe65 근처
]
SEVERE_REDS = [
    (174, 37, 31),   # #ae251f 근처
    (255, 137, 135), # #ff8987 근처
]


def _nearest_color_distance(r: int, g: int, b: int, palette: List[Tuple[int, int, int]]) -> float:
    """RGB와 팔레트 색들 사이의 최소 거리(제곱거리)를 계산."""
    dmins = []
    for pr, pg, pb in palette:
        dr = r - pr
        dg = g - pg
        db = b - pb
        dmins.append(dr * dr + dg * dg + db * db)
    return float(min(dmins)) if dmins else float("inf")


def classify_pixel_turbulence(r: int, g: int, b: int) -> str:
    """
    픽셀 RGB 값을 Photoshop에서 찍은 기준색과의 거리로 분류.
    - Light : 밝은 초록 (VWS 외곽)
    - Moderate : 노란 계열
    - Severe : 붉은 계열
    """
    d_light = _nearest_color_distance(r, g, b, LIGHT_GREENS)
    d_mod = _nearest_color_distance(r, g, b, MODERATE_YELLOWS)
    d_sev = _nearest_color_distance(r, g, b, SEVERE_REDS)

    # 너무 멀면 아무것도 아닌 것으로 간주
    d_min = min(d_light, d_mod, d_sev)
    if d_min > 80**2:
        return "None"

    if d_min == d_sev and d_sev <= 70**2:
        return "Severe"
    if d_min == d_mod and d_mod <= 70**2:
        return "Moderate"
    if d_min == d_light and d_light <= 70**2:
        return "Light"
    return "None"


def analyze_turbulence_along_route() -> List[Dict[str, str]]:
    if not IMG_PATH.exists():
        raise FileNotFoundError(f"이미지 없음: {IMG_PATH}")

    # 1) cross 차트 하단에서 waypoint 라벨+위치 추출
    wp_with_x = extract_waypoints_from_image_with_vision(IMG_PATH)
    if len(wp_with_x) < 2:
        raise RuntimeError("이미지에서 waypoint 라벨을 2개 이상 추출하지 못했습니다.")
    waypoints = [name for (name, _x) in wp_with_x]
    wp_x = [x for (_name, x) in wp_with_x]

    # 2) cross 차트에서 항로(마젠타 선) 픽셀 좌표 추출
    img = Image.open(IMG_PATH)
    path_points: List[Tuple[int, int]] = detect_path_line(img)
    if not path_points:
        raise RuntimeError("cross 차트에서 항로 선을 찾지 못했습니다.")

    # 3) 이미지 전체 RGB 배열
    arr = np.array(img.convert("RGB"))
    h, w, _ = arr.shape

    # 4) path_points를 x좌표 기준으로 정렬 (좌→우)
    path_points_sorted = sorted(path_points, key=lambda p: p[0])
    xs = [p[0] for p in path_points_sorted]
    x_min, x_max = min(xs), max(xs)
    span = max(1, x_max - x_min)

    n_wp = len(waypoints)

    # 구간별 난기류 카운트
    seg_counts: List[Dict[str, int]] = [
        {"Light": 0, "Moderate": 0, "Severe": 0} for _ in range(n_wp - 1)
    ]

    # 5) 각 path 픽셀의 난기류 레벨을 구하고, 해당 x 위치를
    #    가장 가까운 waypoint~waypoint 구간에 매핑
    for x, y in path_points_sorted:
        if not (0 <= x < w and 0 <= y < h):
            continue
        r, g, b = [int(v) for v in arr[y, x]]
        level = classify_pixel_turbulence(r, g, b)
        if level == "None":
            continue

        # x 위치에 해당하는 waypoint 구간 찾기: wp_x[i] ~ wp_x[i+1]
        seg_idx = None
        for i in range(n_wp - 1):
            left = wp_x[i]
            right = wp_x[i + 1]
            if left <= x <= right or right <= x <= left:
                seg_idx = i
                break
        if seg_idx is None:
            # 범위를 조금 벗어난 경우 가장 가까운 구간에 할당
            if x < wp_x[0]:
                seg_idx = 0
            elif x > wp_x[-1]:
                seg_idx = n_wp - 2
            else:
                best_i = 0
                best_d = float("inf")
                for i in range(n_wp - 1):
                    mid = (wp_x[i] + wp_x[i + 1]) / 2
                    d = abs(x - mid)
                    if d < best_d:
                        best_d = d
                        best_i = i
                seg_idx = best_i

        seg_counts[seg_idx][level] += 1

    # 6) 카운트 기반으로 구간 레벨 결정 (임계값은 다소 느슨하게)
    results: List[Dict[str, str]] = []
    for i in range(n_wp - 1):
        c = seg_counts[i]
        total = c["Light"] + c["Moderate"] + c["Severe"]
        if total == 0:
            continue

        if c["Severe"] >= 3:
            level = "Severe"
        elif c["Moderate"] >= 8:
            level = "Moderate"
        elif c["Light"] >= 8:
            level = "Light"
        else:
            # 너무 약하면 스킵
            continue

        results.append(
            {
                "from": waypoints[i],
                "to": waypoints[i + 1],
                "level": level,
                "detail": f"Light={c['Light']}, Moderate={c['Moderate']}, Severe={c['Severe']}",
            }
        )

    return results


def main() -> None:
    print(f"이미지: {IMG_PATH}")
    print()

    try:
        segments = analyze_turbulence_along_route()
    except Exception as e:
        print(f"❌ 분석 오류: {e}")
        return

    if not segments:
        print("경로상에서 유의미한 난기류 구간을 찾지 못했습니다.")
        return

    print("Waypoint 구간별 난기류 후보 (이미지 하단 waypoint 기준):")
    for seg in segments:
        print(f"- {seg['from']} → {seg['to']}: {seg['level']} TURBULENCE ({seg['detail']})")


if __name__ == "__main__":
    main()

