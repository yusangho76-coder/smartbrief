# Aviation Weather Center SIGWX 차트 데이터 수집 방안

## 개요

[Aviation Weather Center](https://aviationweather.gov/sigwx/)에서 제공하는 SIGWX (Significant Weather) 차트 데이터를 수집하는 방법을 정리합니다.

## 방법 1: WAFS (World Area Forecast System) 그리드 데이터 API ⭐ 추천

Aviation Weather Center는 WAFS 그리드 데이터를 API로 제공합니다. SIGWX 차트의 기상 정보를 구조화된 데이터로 가져올 수 있습니다.

### API 엔드포인트

```
https://aviationweather.gov/api/data/wafs
```

### 파라미터

```python
{
    'region': 'us',           # us, pacific, atlantic, asia 등
    'level': 'high',          # high (FL250-630), low (FL100-240)
    'fcst': '24',             # 06, 12, 24 (forecast cycle)
    'format': 'json',         # json, geojson
    'date': '20231220_0000'   # 선택적: 특정 날짜/시간
}
```

### 구현 예시

```python
import requests
from datetime import datetime
from typing import Dict, Optional

def fetch_wafs_sigwx_data(
    region: str = 'asia',
    level: str = 'high',
    fcst: str = '24'
) -> Optional[Dict]:
    """
    WAFS 그리드 데이터에서 SIGWX 정보 가져오기
    
    Args:
        region: 지역 ('us', 'pacific', 'atlantic', 'asia')
        level: 고도 레벨 ('high' for FL250-630, 'low' for FL100-240)
        fcst: 예보 주기 ('06', '12', '24')
    
    Returns:
        WAFS 그리드 데이터 (JSON)
    """
    base_url = 'https://aviationweather.gov/api/data/wafs'
    
    params = {
        'region': region,
        'level': level,
        'fcst': fcst,
        'format': 'json'
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"⚠️ WAFS API 오류: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ WAFS API 호출 실패: {e}")
        return None

# 사용 예시
wafs_data = fetch_wafs_sigwx_data(region='asia', level='high', fcst='24')
if wafs_data:
    # 터뷸런스, CB 구름, 제트기류 정보 추출
    print(f"WAFS 데이터 수신: {len(wafs_data)}개 그리드 포인트")
```

### WAFS 데이터 구조

WAFS 그리드는 위도/경도 그리드 포인트별로 다음 정보를 제공합니다:
- **Turbulence**: 난류 강도 및 고도
- **Icing**: 착빙 강도 및 고도
- **CB Clouds**: 적란운 위치 및 고도
- **Jet Streams**: 제트기류 위치 및 풍속
- **Wind/Temperature**: 고도별 바람 및 온도

## 방법 2: SIGWX 차트 이미지 URL 직접 접근

SIGWX 차트는 정기적으로 업데이트되며, 각 차트는 고유한 URL을 가집니다.

### 이미지 URL 패턴

```
https://aviationweather.gov/data/sigwx/{region}_{level}_{date}_{time}.png
```

또는

```
https://aviationweather.gov/data/sigwx/sigwx_{region}_{level}_{date}_{time}.gif
```

### 구현 예시

```python
from datetime import datetime
import requests
from PIL import Image
import io

def fetch_sigwx_chart_image(
    region: str = 'asia',
    level: str = 'high',
    date: Optional[datetime] = None
) -> Optional[Image.Image]:
    """
    SIGWX 차트 이미지 직접 다운로드
    
    Args:
        region: 지역 ('us', 'pacific', 'atlantic', 'asia')
        level: 고도 레벨 ('high', 'low')
        date: 날짜/시간 (None이면 최신)
    
    Returns:
        PIL Image 객체
    """
    if date is None:
        date = datetime.now()
    
    # 날짜 형식: YYYYMMDD_HHMM
    date_str = date.strftime('%Y%m%d_%H%M')
    
    # URL 패턴 시도 (실제 URL은 확인 필요)
    url_patterns = [
        f"https://aviationweather.gov/data/sigwx/sigwx_{region}_{level}_{date_str}.png",
        f"https://aviationweather.gov/data/sigwx/{region}_{level}_{date_str}.gif",
        f"https://aviationweather.gov/data/sigwx/sigwx_{region}_{level}.png",  # 최신 버전
    ]
    
    for url in url_patterns:
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                print(f"✅ SIGWX 차트 다운로드 성공: {url}")
                return image
        except Exception as e:
            continue
    
    print(f"❌ SIGWX 차트 다운로드 실패: 모든 URL 패턴 시도 실패")
    return None

# 사용 예시
sigwx_image = fetch_sigwx_chart_image(region='asia', level='high')
if sigwx_image:
    # 이미지 분석 (이전에 작성한 analyze_sigwx_chart_enhanced 함수 사용)
    pass
```

## 방법 3: 웹 스크래핑 (Fallback)

API나 직접 URL이 작동하지 않는 경우, 웹 페이지를 스크래핑하여 차트 링크를 추출할 수 있습니다.

### 구현 예시

```python
from bs4 import BeautifulSoup
import requests
import re

def scrape_sigwx_chart_urls(
    region: str = 'asia',
    level: str = 'high'
) -> List[str]:
    """
    Aviation Weather Center 웹사이트에서 SIGWX 차트 URL 스크래핑
    
    Args:
        region: 지역
        level: 고도 레벨
    
    Returns:
        차트 URL 리스트
    """
    base_url = 'https://aviationweather.gov/sigwx/'
    
    try:
        response = requests.get(base_url, timeout=30)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # SIGWX 차트 링크 찾기
        chart_urls = []
        
        # 이미지 태그에서 SIGWX 차트 찾기
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if 'sigwx' in src.lower() or 'sigwx' in src.lower():
                if region in src.lower() and level in src.lower():
                    # 상대 경로를 절대 경로로 변환
                    if src.startswith('/'):
                        full_url = f"https://aviationweather.gov{src}"
                    elif src.startswith('http'):
                        full_url = src
                    else:
                        full_url = f"{base_url}{src}"
                    
                    chart_urls.append(full_url)
        
        # 링크 태그에서도 찾기
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if 'sigwx' in href.lower():
                if region in href.lower() and level in href.lower():
                    if href.startswith('/'):
                        full_url = f"https://aviationweather.gov{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{base_url}{href}"
                    
                    chart_urls.append(full_url)
        
        return list(set(chart_urls))  # 중복 제거
    
    except Exception as e:
        print(f"❌ 웹 스크래핑 실패: {e}")
        return []
```

## 방법 4: 통합 함수 (권장)

위 세 가지 방법을 조합하여 가장 안정적으로 데이터를 가져오는 통합 함수를 만들 수 있습니다.

### 구현 예시

```python
from typing import Optional, Dict, List
import requests
from datetime import datetime
from PIL import Image
import io

def fetch_sigwx_data(
    region: str = 'asia',
    level: str = 'high',
    method: str = 'auto'  # 'wafs', 'image', 'scrape', 'auto'
) -> Dict:
    """
    SIGWX 차트 데이터를 가져오는 통합 함수
    
    Args:
        region: 지역 ('us', 'pacific', 'atlantic', 'asia')
        level: 고도 레벨 ('high', 'low')
        method: 수집 방법 ('wafs', 'image', 'scrape', 'auto')
    
    Returns:
        {
            'method': str,           # 사용된 방법
            'wafs_data': Dict,       # WAFS 그리드 데이터 (있는 경우)
            'image': Image.Image,    # SIGWX 차트 이미지 (있는 경우)
            'image_url': str,        # 이미지 URL (있는 경우)
            'timestamp': datetime    # 데이터 타임스탬프
        }
    """
    result = {
        'method': None,
        'wafs_data': None,
        'image': None,
        'image_url': None,
        'timestamp': datetime.now()
    }
    
    # 방법 1: WAFS API 시도 (구조화된 데이터)
    if method in ('wafs', 'auto'):
        try:
            wafs_data = fetch_wafs_sigwx_data(region, level)
            if wafs_data:
                result['method'] = 'wafs'
                result['wafs_data'] = wafs_data
                print("✅ WAFS API로 데이터 수신 성공")
                return result
        except Exception as e:
            print(f"⚠️ WAFS API 실패: {e}")
    
    # 방법 2: 이미지 URL 직접 접근
    if method in ('image', 'auto'):
        try:
            image = fetch_sigwx_chart_image(region, level)
            if image:
                result['method'] = 'image'
                result['image'] = image
                print("✅ SIGWX 차트 이미지 다운로드 성공")
                return result
        except Exception as e:
            print(f"⚠️ 이미지 다운로드 실패: {e}")
    
    # 방법 3: 웹 스크래핑
    if method in ('scrape', 'auto'):
        try:
            urls = scrape_sigwx_chart_urls(region, level)
            if urls:
                # 첫 번째 URL로 이미지 다운로드 시도
                for url in urls:
                    try:
                        response = requests.get(url, timeout=30)
                        if response.status_code == 200:
                            image = Image.open(io.BytesIO(response.content))
                            result['method'] = 'scrape'
                            result['image'] = image
                            result['image_url'] = url
                            print(f"✅ 웹 스크래핑으로 이미지 다운로드 성공: {url}")
                            return result
                    except Exception as e:
                        continue
        except Exception as e:
            print(f"⚠️ 웹 스크래핑 실패: {e}")
    
    print("❌ 모든 방법 실패: SIGWX 데이터를 가져올 수 없습니다")
    return result

# 사용 예시
sigwx_data = fetch_sigwx_data(region='asia', level='high', method='auto')

if sigwx_data['wafs_data']:
    # WAFS 그리드 데이터 분석
    print("WAFS 그리드 데이터로 분석")
    # TODO: WAFS 데이터 파싱 및 waypoint 매핑
elif sigwx_data['image']:
    # 이미지 분석
    print("SIGWX 차트 이미지로 분석")
    # TODO: 이미지 분석 (analyze_sigwx_chart_enhanced 함수 사용)
```

## API 라우트 통합

기존 `src/api_routes.py`에 SIGWX 데이터 가져오기 엔드포인트 추가:

```python
@api_bp.route("/api/aviation-weather/sigwx", methods=["POST"])
def api_sigwx():
    """SIGWX 차트 데이터를 가져옵니다"""
    import requests
    from PIL import Image
    import io
    
    payload = request.get_json(silent=True) or {}
    region = payload.get("region", "asia")  # us, pacific, atlantic, asia
    level = payload.get("level", "high")    # high, low
    method = payload.get("method", "auto")  # wafs, image, scrape, auto
    
    try:
        result = fetch_sigwx_data(region=region, level=level, method=method)
        
        response_data = {
            "region": region,
            "level": level,
            "method": result['method'],
            "timestamp": result['timestamp'].isoformat() if result['timestamp'] else None
        }
        
        # WAFS 데이터가 있으면 포함
        if result['wafs_data']:
            response_data['wafs_data'] = result['wafs_data']
        
        # 이미지가 있으면 base64로 인코딩
        if result['image']:
            img_byte_arr = io.BytesIO()
            result['image'].save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            import base64
            response_data['image_base64'] = base64.b64encode(img_byte_arr.read()).decode('utf-8')
            response_data['image_url'] = result.get('image_url')
        
        return jsonify(response_data)
        
    except Exception as exc:
        logger.error(f"SIGWX API error: {exc}", exc_info=True)
        return jsonify({"error": f"SIGWX 데이터 가져오기 실패: {exc}"}), 500
```

## 주의사항

1. **저작권 및 이용 약관**: SIGWX 차트 데이터는 Aviation Weather Center의 저작권 보호를 받을 수 있으므로, 사용 전에 이용 약관을 확인해야 합니다.

2. **데이터 업데이트 주기**: 
   - SIGWX 차트는 보통 6시간마다 업데이트됩니다
   - WAFS 그리드 데이터는 예보 주기(06, 12, 24시간)에 따라 업데이트됩니다

3. **API Rate Limit**: 
   - Aviation Weather Center API는 무료이지만, 과도한 요청은 제한될 수 있습니다
   - 적절한 캐싱 전략 필요

4. **지역별 차이**: 
   - 지역별로 제공되는 데이터 형식이 다를 수 있습니다
   - 'asia' 지역의 경우 WAFS 데이터가 제한적일 수 있습니다

## 권장 구현 순서

1. **Phase 1**: WAFS API 테스트 및 데이터 구조 파악
2. **Phase 2**: 이미지 URL 직접 접근 방법 테스트
3. **Phase 3**: 웹 스크래핑 Fallback 구현
4. **Phase 4**: 통합 함수 및 API 라우트 구현
5. **Phase 5**: 기존 SIGWX 분석 로직과 통합

## 참고 자료

- [Aviation Weather Center SIGWX 페이지](https://aviationweather.gov/sigwx/)
- [Aviation Weather Center API 문서](https://aviationweather.gov/data/api/)
- [WAFS (World Area Forecast System) 정보](https://www.icao.int/airnavigation/Pages/WAFS.aspx)

