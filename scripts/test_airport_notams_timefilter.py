import json
from datetime import datetime
import os
import sys

# 프로젝트 루트(상위 디렉터리)를 모듈 경로에 추가
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app


def run():
    client = app.test_client()

    # 1) 캐시 주입: RKSS CLSD 노탐 2개 (서로 다른 일일 시간대)
    # - A1412/25: 2300-0500
    # - A1157/25: 2300-0600
    notams = [
        {
            "id": "A1412/25",
            "airport_code": "RKSS",
            "text": "",
            "description": "TWY C1,C3 CLSD DUE TO WIP 시간대: 2300-0500",
            "effective_time": "2025-10-31T14:00:00Z",
            "expiry_time": "2025-11-22T20:00:00Z",
            # 분석 파이프라인에서 생성되는 필드가 아니라도, 서버가 재생성하므로 없어도 됨
        },
        {
            "id": "A1157/25",
            "airport_code": "RKSS",
            "text": "",
            "description": "TWY D2, D3 CLSD DUE TO WIP 시간대: 2300-0600",
            "effective_time": "2025-09-15T14:00:00Z",
            "expiry_time": "2025-12-02T21:00:00Z",
        },
    ]

    # 캐시 주입
    resp = client.post(
        "/api/airport-notams/override",
        data=json.dumps({"notams": notams, "source": "unit_test"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, f"override failed: {resp.data!r}"

    # 2) 야간 창 밖(12:00-13:00 KST): 둘 다 제외되어야 함 → filtered_count == 0
    resp = client.get(
        "/api/airport-notams",
        query_string={
            "airport": "RKSS",
            "from_local": "2025-11-16T12:00",
            "to_local": "2025-11-16T13:00",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    print("Noon window response:", data)
    assert data["debug"]["airport_for_local"] == "RKSS"
    assert data["filtered_count"] == 0, "Expected 0 during daytime window"

    # 3) 야간 창 안(23:30-00:30 KST): 둘 다 포함되어야 함 → filtered_count >= 2
    resp = client.get(
        "/api/airport-notams",
        query_string={
            "airport": "RKSS",
            "from_local": "2025-11-16T23:30",
            "to_local": "2025-11-17T00:30",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    print("Night window response:", data)
    assert data["debug"]["airport_for_local"] == "RKSS"
    assert data["filtered_count"] >= 2, "Expected >=2 during night window"

    print("OK: time filter behaves as expected.")


if __name__ == "__main__":
    run()

