#!/usr/bin/env python3
"""
Google Cloud Vision API + OpenCV를 사용해서
cross 섹션 차트 이미지에서 난기류(Turbulence) 색 영역을 대략적으로 감지하는 테스트 스크립트.

대상 이미지 (기본값):
    uploads/20260305_170034_4726e704_ImportantFile_15_cross.jpg

전제/준비:
1) 패키지 설치
   pip install google-cloud-vision pillow opencv-python numpy

2) 인증 설정
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account.json

역할:
- Google Cloud Vision의 image_properties를 호출해서 이미지 대표 색상 정보를 한 번 보고
- 실제 난기류 영역 검출은 OpenCV로
    - 밝은 초록색(VWS 영역)  → Light turbulence 후보
    - 노란색 영역             → Moderate/Severe turbulence 후보
- 이미지를 좌우 10구간으로 나누어, 각 구간별로 light / moderate / severe 여부를 요약 출력.

※ 실제 운항용이 아닌, Vision API 호출 및 색 기반 분석이 잘 도는지 확인하는 "테스트 코드"입니다.
"""

from pathlib import Path
import io
from typing import List, Tuple

import numpy as np
from PIL import Image
import cv2

from google.cloud import vision


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGE = ROOT / "uploads/20260305_170034_4726e704_ImportantFile_15_cross.jpg"


def call_vision_image_properties(image_path: Path) -> None:
    """Google Cloud Vision API의 image_properties를 호출해 대표 색상 몇 개를 찍어본다."""
    client = vision.ImageAnnotatorClient()

    content = image_path.read_bytes()
    image = vision.Image(content=content)

    response = client.image_properties(image=image)
    if response.error.message:
        print("❌ Vision image_properties 오류:", response.error.message)
        return

    props = response.image_properties_annotation
    print("\n[Vision image_properties] 상위 대표 색상:")
    for i, color_info in enumerate(props.dominant_colors.colors[:10], start=1):
        c = color_info.color
        score = color_info.score
        pixel_fraction = color_info.pixel_fraction
        print(
            f"  {i:02d}: RGB=({int(c.red)}, {int(c.green)}, {int(c.blue)}), "
            f"score={score:.3f}, fraction={pixel_fraction:.3f}"
        )


def load_image_array(image_path: Path) -> np.ndarray:
    """이미지를 RGB numpy 배열로 로드."""
    img = Image.open(image_path).convert("RGB")
    return np.array(img)


def detect_turbulence_masks(arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    색 기준으로 난기류 후보 영역 마스크 생성.

    반환:
        (light_mask, moderate_mask, severe_mask)  # 모두 0/255 uint8 배열
    """
    # 배열은 RGB라고 가정
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    # Light turbulence 후보: 밝은 초록색(VWS 외곽) - G 매우 크고 R/B 작음
    light_mask = np.where(
        (g > 200) & (r < 80) & (b < 80),
        255,
        0,
    ).astype("uint8")

    # Moderate turbulence 후보: 노랑/연두 톤 - R,G 모두 크고 B는 상대적으로 작음
    moderate_mask = np.where(
        (r > 200) & (g > 200) & (b < 150),
        255,
        0,
    ).astype("uint8")

    # Severe turbulence 후보: 현재 cross 차트에는 거의 없겠지만,
    # 빨간 계열이 있다면 여기에 걸리도록 설정 (R 크고, G/B 작음)
    severe_mask = np.where(
        (r > 180) & (g < 100) & (b < 100),
        255,
        0,
    ).astype("uint8")

    return light_mask, moderate_mask, severe_mask


def summarize_by_segments(
    light_mask: np.ndarray,
    moderate_mask: np.ndarray,
    severe_mask: np.ndarray,
    num_segments: int = 10,
) -> List[dict]:
    """
    이미지를 좌우 num_segments 구간으로 나누어 각 구간별 픽셀 수를 요약.
    """
    h, w = light_mask.shape
    seg_w = w // num_segments
    results: List[dict] = []

    for i in range(num_segments):
        x0 = i * seg_w
        x1 = (i + 1) * seg_w if i < num_segments - 1 else w

        lm = light_mask[:, x0:x1]
        mm = moderate_mask[:, x0:x1]
        sm = severe_mask[:, x0:x1]

        light_cnt = int(np.count_nonzero(lm))
        moderate_cnt = int(np.count_nonzero(mm))
        severe_cnt = int(np.count_nonzero(sm))

        # 아주 간단한 규칙: 픽셀 개수 기준으로 레벨 판정
        label = "None"
        if severe_cnt > 100:
            label = "Severe"
        elif moderate_cnt > 200:
            label = "Moderate"
        elif light_cnt > 200:
            label = "Light"

        results.append(
            {
                "segment": i + 1,
                "x_range": (x0, x1),
                "light_pixels": light_cnt,
                "moderate_pixels": moderate_cnt,
                "severe_pixels": severe_cnt,
                "level": label,
            }
        )

    return results


def main() -> None:
    image_path = DEFAULT_IMAGE
    print(f"Cross 차트 이미지: {image_path}")

    if not image_path.exists():
        print("❌ 이미지 파일을 찾을 수 없습니다.")
        return

    # 1) Vision API로 대표 색상 정보 한 번 확인
    try:
        call_vision_image_properties(image_path)
    except Exception as e:
        print(f"\n⚠️ Vision API 호출 중 오류 (테스트 계속 진행): {e}")

    # 2) OpenCV 색 마스크로 난기류 후보 검출
    arr = load_image_array(image_path)
    light_mask, moderate_mask, severe_mask = detect_turbulence_masks(arr)

    # 3) 좌우 10구간으로 나누어 통계
    segments = summarize_by_segments(light_mask, moderate_mask, severe_mask, num_segments=10)

    print("\n[구간별 난기류 요약] (좌→우 10등분)")
    print("Seg | x_range      | Light px | Moderate px | Severe px | Level")
    print("-" * 70)
    for seg in segments:
        print(
            f"{seg['segment']:3d} | "
            f"{seg['x_range'][0]:4d}-{seg['x_range'][1]:4d} | "
            f"{seg['light_pixels']:8d} | "
            f"{seg['moderate_pixels']:11d} | "
            f"{seg['severe_pixels']:9d} | "
            f"{seg['level']}"
        )


if __name__ == "__main__":
    main()

