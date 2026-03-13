#!/usr/bin/env python3
"""
Aviation Weather Center SIGWX/WAFS API 테스트 스크립트
"""

import requests
import json
from datetime import datetime
from typing import Dict, Optional, List

def test_wafs_api(region: str = 'asia', level: str = 'high', fcst: str = '24'):
    """WAFS API 테스트"""
    print("=" * 80)
    print(f"WAFS API 테스트 (region={region}, level={level}, fcst={fcst})")
    print("=" * 80)
    
    base_url = 'https://aviationweather.gov/api/data/wafs'
    
    params = {
        'region': region,
        'level': level,
        'fcst': fcst,
        'format': 'json'
    }
    
    print(f"\n요청 URL: {base_url}")
    print(f"파라미터: {params}")
    print("\nAPI 호출 중...")
    
    try:
        response = requests.get(base_url, params=params, timeout=30)
        
        print(f"응답 상태 코드: {response.status_code}")
        print(f"응답 헤더: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"\n✅ WAFS 데이터 수신 성공!")
                print(f"데이터 타입: {type(data)}")
                
                if isinstance(data, dict):
                    print(f"키 목록: {list(data.keys())}")
                    print(f"\n데이터 샘플 (처음 500자):")
                    print(json.dumps(data, indent=2)[:500])
                elif isinstance(data, list):
                    print(f"리스트 길이: {len(data)}")
                    if len(data) > 0:
                        print(f"\n첫 번째 항목 샘플:")
                        print(json.dumps(data[0], indent=2)[:500])
                else:
                    print(f"데이터: {str(data)[:500]}")
                
                return data
            except json.JSONDecodeError as e:
                print(f"\n⚠️ JSON 파싱 실패: {e}")
                print(f"응답 텍스트 (처음 500자): {response.text[:500]}")
                return None
        else:
            print(f"\n❌ API 오류: {response.status_code}")
            print(f"응답 텍스트: {response.text[:500]}")
            return None
            
    except requests.exceptions.Timeout:
        print("\n❌ 요청 타임아웃 (30초 초과)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"\n❌ 요청 실패: {e}")
        return None
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_sigwx_image_urls():
    """SIGWX 차트 이미지 URL 테스트"""
    print("\n" + "=" * 80)
    print("SIGWX 차트 이미지 URL 테스트")
    print("=" * 80)
    
    # 다양한 URL 패턴 시도
    date_str = datetime.now().strftime('%Y%m%d_%H%M')
    date_str_short = datetime.now().strftime('%Y%m%d')
    
    url_patterns = [
        f"https://aviationweather.gov/data/sigwx/sigwx_asia_high_{date_str}.png",
        f"https://aviationweather.gov/data/sigwx/sigwx_asia_high_{date_str_short}.png",
        f"https://aviationweather.gov/data/sigwx/sigwx_asia_high.png",
        f"https://aviationweather.gov/data/sigwx/asia_high_{date_str}.gif",
        f"https://aviationweather.gov/data/sigwx/asia_high.gif",
        f"https://aviationweather.gov/data/sigwx/sigwx_high_asia.png",
    ]
    
    for url in url_patterns:
        print(f"\n테스트 URL: {url}")
        try:
            response = requests.head(url, timeout=10, allow_redirects=True)
            print(f"  상태 코드: {response.status_code}")
            if response.status_code == 200:
                print(f"  ✅ 이미지 발견!")
                print(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")
                print(f"  Content-Length: {response.headers.get('Content-Length', 'N/A')} bytes")
                return url
        except Exception as e:
            print(f"  ❌ 실패: {e}")
    
    print("\n⚠️ 모든 URL 패턴 실패")
    return None


def test_aviation_weather_api_endpoints():
    """Aviation Weather Center의 다른 API 엔드포인트 테스트"""
    print("\n" + "=" * 80)
    print("Aviation Weather Center API 엔드포인트 목록 테스트")
    print("=" * 80)
    
    # 알려진 API 엔드포인트들
    endpoints = [
        {
            'name': 'METAR',
            'url': 'https://aviationweather.gov/api/data/metar',
            'params': {'ids': 'RKSI', 'format': 'json'}
        },
        {
            'name': 'TAF',
            'url': 'https://aviationweather.gov/api/data/taf',
            'params': {'ids': 'RKSI', 'format': 'json'}
        },
        {
            'name': 'ISIGMET',
            'url': 'https://aviationweather.gov/api/data/isigmet',
            'params': {'format': 'json', 'bbox': '35,125,40,130'}
        },
        {
            'name': 'PIREP',
            'url': 'https://aviationweather.gov/api/data/pirep',
            'params': {'format': 'json', 'id': 'RKSI', 'distance': '50', 'age': '3'}
        },
        {
            'name': 'WAFS (High)',
            'url': 'https://aviationweather.gov/api/data/wafs',
            'params': {'region': 'asia', 'level': 'high', 'fcst': '24', 'format': 'json'}
        },
        {
            'name': 'WAFS (Low)',
            'url': 'https://aviationweather.gov/api/data/wafs',
            'params': {'region': 'asia', 'level': 'low', 'fcst': '24', 'format': 'json'}
        },
    ]
    
    results = {}
    
    for endpoint in endpoints:
        print(f"\n[{endpoint['name']}]")
        print(f"  URL: {endpoint['url']}")
        print(f"  파라미터: {endpoint['params']}")
        
        try:
            response = requests.get(
                endpoint['url'], 
                params=endpoint['params'], 
                timeout=15
            )
            
            print(f"  상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        print(f"  ✅ 성공: 리스트 {len(data)}개 항목")
                    elif isinstance(data, dict):
                        print(f"  ✅ 성공: 딕셔너리 (키: {list(data.keys())[:5]})")
                    else:
                        print(f"  ✅ 성공: {type(data)}")
                    
                    results[endpoint['name']] = {
                        'status': 'success',
                        'data_type': type(data).__name__,
                        'data_length': len(data) if isinstance(data, (list, dict)) else None
                    }
                except:
                    print(f"  ⚠️ JSON 파싱 실패 (텍스트 응답일 수 있음)")
                    print(f"  응답 길이: {len(response.text)} bytes")
                    results[endpoint['name']] = {
                        'status': 'success (non-json)',
                        'response_length': len(response.text)
                    }
            elif response.status_code == 204:
                print(f"  ⚠️ 데이터 없음 (204 No Content)")
                results[endpoint['name']] = {'status': 'no_content'}
            else:
                print(f"  ❌ 실패: {response.status_code}")
                print(f"  응답: {response.text[:200]}")
                results[endpoint['name']] = {
                    'status': 'error',
                    'status_code': response.status_code
                }
                
        except requests.exceptions.Timeout:
            print(f"  ❌ 타임아웃")
            results[endpoint['name']] = {'status': 'timeout'}
        except Exception as e:
            print(f"  ❌ 오류: {e}")
            results[endpoint['name']] = {'status': 'error', 'error': str(e)}
    
    return results


def test_sigwx_webpage_scraping():
    """SIGWX 웹페이지에서 차트 링크 찾기"""
    print("\n" + "=" * 80)
    print("SIGWX 웹페이지 스크래핑 테스트")
    print("=" * 80)
    
    url = 'https://aviationweather.gov/sigwx/'
    
    print(f"웹페이지 접속: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        print(f"상태 코드: {response.status_code}")
        
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 이미지 태그 찾기
            images = soup.find_all('img')
            print(f"\n이미지 태그 수: {len(images)}")
            
            sigwx_images = []
            for img in images:
                src = img.get('src', '')
                if 'sigwx' in src.lower():
                    sigwx_images.append(src)
                    print(f"  발견: {src}")
            
            # 링크 태그 찾기
            links = soup.find_all('a', href=True)
            print(f"\n링크 태그 수: {len(links)}")
            
            sigwx_links = []
            for link in links:
                href = link.get('href', '')
                if 'sigwx' in href.lower():
                    sigwx_links.append(href)
                    print(f"  발견: {href}")
            
            return {
                'images': sigwx_images,
                'links': sigwx_links
            }
        else:
            print(f"❌ 웹페이지 접속 실패: {response.status_code}")
            return None
            
    except ImportError:
        print("⚠️ BeautifulSoup4가 설치되지 않았습니다. pip install beautifulsoup4")
        return None
    except Exception as e:
        print(f"❌ 스크래핑 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """메인 함수"""
    print("Aviation Weather Center SIGWX/WAFS API 테스트")
    print("=" * 80)
    
    # 1. WAFS API 테스트
    wafs_data = test_wafs_api(region='asia', level='high', fcst='24')
    
    # 2. SIGWX 이미지 URL 테스트
    image_url = test_sigwx_image_urls()
    
    # 3. 다른 API 엔드포인트 테스트
    api_results = test_aviation_weather_api_endpoints()
    
    # 4. 웹페이지 스크래핑 테스트
    scraping_results = test_sigwx_webpage_scraping()
    
    # 결과 요약
    print("\n" + "=" * 80)
    print("테스트 결과 요약")
    print("=" * 80)
    print(f"WAFS API: {'✅ 성공' if wafs_data else '❌ 실패'}")
    print(f"SIGWX 이미지 URL: {'✅ 발견' if image_url else '❌ 없음'}")
    if image_url:
        print(f"  URL: {image_url}")
    
    print(f"\nAPI 엔드포인트 테스트 결과:")
    for name, result in api_results.items():
        status = result.get('status', 'unknown')
        print(f"  {name}: {status}")
    
    if scraping_results:
        print(f"\n웹페이지 스크래핑:")
        print(f"  SIGWX 이미지: {len(scraping_results.get('images', []))}개")
        print(f"  SIGWX 링크: {len(scraping_results.get('links', []))}개")


if __name__ == "__main__":
    main()

