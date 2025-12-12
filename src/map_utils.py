"""
지도 생성 및 시각화 유틸리티 모듈
참조: SmartNOTAMgemini_GCR/map_utils.py
"""

import folium
from folium import plugins
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional

class NOTAMMapGenerator:
    """NOTAM 데이터를 지도에 시각화하는 클래스"""
    
    def __init__(self):
        self.map_output_dir = 'static/maps'
        self.ensure_output_dir()
    
    def ensure_output_dir(self):
        """출력 디렉토리가 없으면 생성"""
        os.makedirs(self.map_output_dir, exist_ok=True)
    
    def create_notam_map(self, notams: List[Dict], center: Tuple[float, float] = (37.5665, 126.9780)) -> str:
        """
        NOTAM 데이터를 기반으로 지도를 생성합니다.
        
        Args:
            notams (list): NOTAM 데이터 리스트
            center (tuple): 지도 중심 좌표 (위도, 경도) - 기본값은 서울
            
        Returns:
            str: 생성된 지도 HTML 파일의 상대 경로
        """
        try:
            # 지도 생성 (기본 중심은 서울)
            m = folium.Map(
                location=center, 
                zoom_start=8,
                tiles='OpenStreetMap'
            )
            
            # NOTAM별로 마커 추가
            marker_colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen']
            
            for i, notam in enumerate(notams):
                if notam.get('coordinates'):
                    lat, lon = notam['coordinates']
                    color = marker_colors[i % len(marker_colors)]
                    
                    # 팝업 내용 구성
                    popup_content = self._create_popup_content(notam)
                    
                    # 마커 추가
                    folium.Marker(
                        [lat, lon],
                        popup=folium.Popup(popup_content, max_width=400),
                        tooltip=f"NOTAM {notam.get('id', 'N/A')}",
                        icon=folium.Icon(color=color, icon='plane', prefix='fa')
                    ).add_to(m)
                    
                    # 영향 반경이 있는 경우 원 추가
                    if notam.get('radius'):
                        folium.Circle(
                            [lat, lon],
                            radius=notam['radius'],
                            color=color,
                            fill=True,
                            fillColor=color,
                            fillOpacity=0.2,
                            weight=2,
                            popup=f"영향반경: {notam['radius']}m"
                        ).add_to(m)
            
            # 한국 주요 공항 표시
            self._add_major_airports(m)
            
            # 지도 저장
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'notam_map_{timestamp}.html'
            filepath = os.path.join(self.map_output_dir, filename)
            m.save(filepath)
            
            # 상대 경로 반환
            return f'maps/{filename}'
            
        except Exception as e:
            print(f"지도 생성 중 오류 발생: {str(e)}")
            return None
    
    def _create_popup_content(self, notam: Dict) -> str:
        """NOTAM 정보를 담은 팝업 내용 생성"""
        content = f"""
        <div style="width: 350px;">
            <h5><strong>NOTAM {notam.get('id', 'N/A')}</strong></h5>
            <hr>
            <p><strong>공항:</strong> {', '.join(notam.get('airport_codes', ['N/A']))}</p>
            <p><strong>유효기간:</strong> {notam.get('effective_time', 'N/A')} ~ {notam.get('expiry_time', 'N/A')}</p>
            <p><strong>위치:</strong> {notam.get('coordinates', ['N/A', 'N/A'])[0]:.4f}, {notam.get('coordinates', ['N/A', 'N/A'])[1]:.4f}</p>
            <hr>
            <p><strong>내용:</strong></p>
            <p style="font-size: 12px; max-height: 100px; overflow-y: auto;">
                {notam.get('description', 'N/A')[:200]}...
            </p>
        """
        
        if notam.get('translated_description'):
            content += f"""
            <hr>
            <p><strong>번역:</strong></p>
            <p style="font-size: 12px; max-height: 100px; overflow-y: auto;">
                {notam.get('translated_description', '')[:200]}...
            </p>
            """
        
        content += "</div>"
        return content
    
    def _add_major_airports(self, map_obj):
        """한국 주요 공항을 지도에 추가"""
        airports = {
            'RKSI': {'name': '인천국제공항', 'coords': [37.4691, 126.4505]},
            'RKSS': {'name': '김포국제공항', 'coords': [37.5583, 126.7906]},
            'RKPC': {'name': '제주국제공항', 'coords': [33.5097, 126.4919]},
            'RKPK': {'name': '김해국제공항', 'coords': [35.1736, 128.9386]},
            'RKTU': {'name': '청주국제공항', 'coords': [36.7167, 127.4997]},
            'RKNY': {'name': '양양국제공항', 'coords': [38.0614, 128.6719]},
            'RKJJ': {'name': '광주공항', 'coords': [35.1264, 126.8089]}
        }
        
        for code, info in airports.items():
            folium.Marker(
                info['coords'],
                popup=f"{code} - {info['name']}",
                tooltip=info['name'],
                icon=folium.Icon(color='gray', icon='home', prefix='fa')
            ).add_to(map_obj)
    
    def create_coordinates_map(self, coordinates: List[Tuple[float, float]], 
                             center: Optional[Tuple[float, float]] = None, 
                             radius: Optional[float] = None) -> str:
        """
        좌표들을 이용하여 간단한 지도를 생성합니다.
        
        Args:
            coordinates (list): 좌표 리스트 [(lat1, lon1), (lat2, lon2), ...]
            center (tuple): 중심 좌표 (lat, lon)
            radius (float): 반경 (미터)
            
        Returns:
            str: 생성된 지도의 HTML 파일 경로
        """
        try:
            if not coordinates:
                return None
                
            # 중심 좌표 계산 (제공되지 않은 경우)
            if center is None:
                center_lat = sum(coord[0] for coord in coordinates) / len(coordinates)
                center_lon = sum(coord[1] for coord in coordinates) / len(coordinates)
                center = (center_lat, center_lon)
            
            # 지도 생성
            m = folium.Map(location=center, zoom_start=14)
            
            # 각 좌표에 마커 추가
            for i, coord in enumerate(coordinates, 1):
                folium.Marker(
                    coord,
                    popup=f'Point {i}: {coord[0]:.4f}, {coord[1]:.4f}',
                    icon=folium.Icon(color='red', icon='info-sign')
                ).add_to(m)
            
            # 좌표들을 연결하는 폴리곤 추가 (3개 이상의 점이 있는 경우)
            if len(coordinates) > 2:
                folium.Polygon(
                    locations=coordinates,
                    color='red',
                    fill=True,
                    fillColor='red',
                    fillOpacity=0.2,
                    weight=2
                ).add_to(m)
            
            # 반경 원 추가
            if radius:
                folium.Circle(
                    center,
                    radius=radius,
                    color='blue',
                    fill=True,
                    fillColor='blue',
                    fillOpacity=0.1
                ).add_to(m)
            
            # 지도 저장
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'coordinates_map_{timestamp}.html'
            filepath = os.path.join(self.map_output_dir, filename)
            m.save(filepath)
            
            return f'maps/{filename}'
            
        except Exception as e:
            print(f"지도 생성 중 오류 발생: {str(e)}")
            return None