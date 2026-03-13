#!/usr/bin/env python3
"""
Aviation Weather API - SIGMET 테스트 스크립트
"""

import requests
from datetime import datetime, timedelta
import json


def test_sigmet_api():
    """SIGMET API 테스트"""
    print("=" * 80)
    print("Aviation Weather API - SIGMET 테스트")
    print("=" * 80)
    print()
    
    # API 엔드포인트
    base_url = 'https://aviationweather.gov/api/data/isigmet'
    
    # 테스트 케이스들
    test_cases = [
        {
            "name": "오늘 날짜 (현재 시간)",
            "params": {
                'format': 'raw',
                'hazard': 'turb',
                'level': 34000,
                'date': datetime.now().strftime('%Y%m%d%H%M')
            }
        },
        {
            "name": "어제 날짜",
            "params": {
                'format': 'raw',
                'hazard': 'turb',
                'level': 34000,
                'date': (datetime.now() - timedelta(days=1)).strftime('%Y%m%d%H%M')
            }
        },
        {
            "name": "일주일 전 날짜",
            "params": {
                'format': 'raw',
                'hazard': 'turb',
                'level': 34000,
                'date': (datetime.now() - timedelta(days=7)).strftime('%Y%m%d%H%M')
            }
        },
        {
            "name": "JSON 형식",
            "params": {
                'format': 'json',
                'hazard': 'turb',
                'level': 34000,
                'date': (datetime.now() - timedelta(days=1)).strftime('%Y%m%d%H%M')
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[{i}] {test_case['name']}")
        print("-" * 80)
        print(f"파라미터: {test_case['params']}")
        
        try:
            response = requests.get(base_url, params=test_case['params'], timeout=10)
            print(f"응답 상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ 성공!")
                content = response.text
                print(f"응답 길이: {len(content)} 문자")
                
                if test_case['params']['format'] == 'json':
                    try:
                        data = response.json()
                        print(f"SIGMET 항목 수: {len(data) if isinstance(data, list) else 1}")
                        if isinstance(data, list) and len(data) > 0:
                            print(f"첫 번째 항목 샘플:")
                            print(json.dumps(data[0], indent=2, ensure_ascii=False)[:500])
                    except:
                        print("JSON 파싱 실패")
                else:
                    sigmet_count = content.count('SIGMET')
                    print(f"SIGMET 항목 수: {sigmet_count}")
                    if len(content) > 0:
                        print(f"\n응답 내용 (처음 500자):")
                        print(content[:500])
                        if len(content) > 500:
                            print("...")
                            
            elif response.status_code == 204:
                print("⚠️ 응답 없음 (No Content) - 해당 날짜/시간에 데이터가 없을 수 있습니다.")
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    print(f"❌ 오류: {error_data.get('error', 'Unknown error')}")
                except:
                    print(f"❌ 오류: {response.text}")
            else:
                print(f"❌ 예상치 못한 상태 코드: {response.status_code}")
                print(f"응답: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 요청 오류: {e}")
        except Exception as e:
            print(f"❌ 오류: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("테스트 완료")
    print("=" * 80)


if __name__ == "__main__":
    test_sigmet_api()

