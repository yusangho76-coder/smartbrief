#!/usr/bin/env python3
"""
SIGWX 웹페이지 상세 분석
"""

import requests
from bs4 import BeautifulSoup
import re

def analyze_sigwx_webpage():
    """SIGWX 웹페이지를 상세히 분석"""
    url = 'https://aviationweather.gov/sigwx/'
    
    print("=" * 80)
    print("SIGWX 웹페이지 상세 분석")
    print("=" * 80)
    print(f"URL: {url}\n")
    
    try:
        response = requests.get(url, timeout=15)
        print(f"상태 코드: {response.status_code}\n")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 페이지 제목
            title = soup.find('title')
            if title:
                print(f"페이지 제목: {title.text}\n")
            
            # 모든 링크 찾기
            print("=" * 80)
            print("모든 링크 분석")
            print("=" * 80)
            links = soup.find_all('a', href=True)
            sigwx_related = []
            
            for link in links:
                href = link.get('href', '')
                text = link.text.strip()
                
                # SIGWX 관련 키워드 찾기
                if any(keyword in href.lower() or keyword in text.lower() 
                       for keyword in ['sigwx', 'sigwx', 'wafs', 'significant', 'weather', 'chart']):
                    sigwx_related.append({
                        'href': href,
                        'text': text[:50],
                        'full_url': f"https://aviationweather.gov{href}" if href.startswith('/') else href
                    })
            
            print(f"SIGWX 관련 링크: {len(sigwx_related)}개\n")
            for item in sigwx_related[:20]:  # 처음 20개만
                print(f"  텍스트: {item['text']}")
                print(f"  링크: {item['href']}")
                print(f"  전체 URL: {item['full_url']}")
                print()
            
            # 모든 이미지 찾기
            print("=" * 80)
            print("모든 이미지 분석")
            print("=" * 80)
            images = soup.find_all('img')
            
            print(f"이미지 태그 수: {len(images)}\n")
            for img in images:
                src = img.get('src', '')
                alt = img.get('alt', '')
                if src:
                    full_url = f"https://aviationweather.gov{src}" if src.startswith('/') else src
                    print(f"  src: {src}")
                    print(f"  alt: {alt}")
                    print(f"  전체 URL: {full_url}")
                    print()
            
            # JavaScript 코드에서 URL 찾기
            print("=" * 80)
            print("JavaScript 코드 분석")
            print("=" * 80)
            scripts = soup.find_all('script')
            
            for script in scripts:
                if script.string:
                    # URL 패턴 찾기
                    urls = re.findall(r'https?://[^\s"\'<>]+', script.string)
                    sigwx_urls = [url for url in urls if 'sigwx' in url.lower() or 'wafs' in url.lower()]
                    if sigwx_urls:
                        print(f"발견된 URL:")
                        for url in sigwx_urls:
                            print(f"  {url}")
                        print()
            
            # iframe 찾기
            print("=" * 80)
            print("iframe 분석")
            print("=" * 80)
            iframes = soup.find_all('iframe')
            print(f"iframe 수: {len(iframes)}\n")
            for iframe in iframes:
                src = iframe.get('src', '')
                if src:
                    full_url = f"https://aviationweather.gov{src}" if src.startswith('/') else src
                    print(f"  src: {src}")
                    print(f"  전체 URL: {full_url}\n")
            
            # API 엔드포인트 찾기
            print("=" * 80)
            print("API 엔드포인트 패턴 찾기")
            print("=" * 80)
            api_patterns = re.findall(r'/api/[^\s"\'<>]+', response.text)
            unique_apis = list(set(api_patterns))
            print(f"발견된 API 패턴: {len(unique_apis)}개\n")
            for api in unique_apis[:20]:
                print(f"  {api}")
            
            # HTML 전체 텍스트에서 SIGWX 관련 키워드 찾기
            print("\n" + "=" * 80)
            print("페이지 텍스트에서 SIGWX 관련 키워드")
            print("=" * 80)
            page_text = soup.get_text()
            sigwx_keywords = re.findall(r'(?i)(sigwx|wafs|significant\s+weather|chart)[^\s]{0,50}', page_text)
            if sigwx_keywords:
                print(f"발견된 키워드: {len(sigwx_keywords)}개\n")
                for keyword in sigwx_keywords[:20]:
                    print(f"  {keyword}")
            
            return {
                'links': sigwx_related,
                'images': [img.get('src', '') for img in images if img.get('src')],
                'apis': unique_apis
            }
        else:
            print(f"❌ 웹페이지 접속 실패: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_api_endpoints_from_page(apis):
    """페이지에서 찾은 API 엔드포인트 테스트"""
    if not apis:
        return
    
    print("\n" + "=" * 80)
    print("발견된 API 엔드포인트 테스트")
    print("=" * 80)
    
    for api_path in apis[:10]:  # 처음 10개만 테스트
        if 'sigwx' in api_path.lower() or 'wafs' in api_path.lower():
            full_url = f"https://aviationweather.gov{api_path}"
            print(f"\n테스트: {full_url}")
            try:
                response = requests.get(full_url, timeout=10)
                print(f"  상태 코드: {response.status_code}")
                if response.status_code == 200:
                    print(f"  ✅ 성공!")
                    print(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            except Exception as e:
                print(f"  ❌ 실패: {e}")


if __name__ == "__main__":
    result = analyze_sigwx_webpage()
    if result and result.get('apis'):
        test_api_endpoints_from_page(result['apis'])

