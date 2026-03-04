from __future__ import annotations

import os
import logging
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request
from datetime import datetime, timedelta

from .route_fir_mapper import route_fir_mapper
from .fir_geo_service import load_fir_geojson
from .package3_parser import get_package3_data

api_bp = Blueprint("api_routes", __name__)
logger = logging.getLogger(__name__)


@api_bp.route("/api/route-path", methods=["POST"])
def api_route_path():
    payload = request.get_json(silent=True) or {}
    route_text = payload.get("route", "")
    if not route_text:
        return jsonify({"error": "route parameter is required"}), 400

    # Flight plan에서 추출한 waypoint 좌표 (있으면 NavData 대신 사용)
    waypoints_from_plan = payload.get("waypoints") or []
    coord_by_ident = {}
    for w in waypoints_from_plan:
        ident = (w.get("ident") or "").strip().upper()
        lat, lon = w.get("lat"), w.get("lon")
        if ident and lat is not None and lon is not None:
            try:
                coord_by_ident[ident] = (float(lat), float(lon))
            except (TypeError, ValueError):
                pass
    if coord_by_ident:
        logger.info(f"Flight plan waypoint 좌표 사용: {len(coord_by_ident)}개")

    try:
        result = route_fir_mapper.analyze_route(route_text)
    except Exception as exc:  # pragma: no cover - logging only
        return jsonify({"error": f"route analysis failed: {exc}"}), 500

    coordinates = []
    for point in result.get("points", []):
        ident = point.get("ident") or ""
        lat = point.get("lat")
        lon = point.get("lon")
        # Flight plan 좌표가 있으면 우선 사용 (NavData 중복 이름 오류 방지)
        if ident and ident.upper() in coord_by_ident:
            lat, lon = coord_by_ident[ident.upper()]
        if lat is None or lon is None:
            continue
        coordinates.append(
            {
                "lat": float(lat),
                "lng": float(lon),
                "ident": point.get("ident"),
                "airway": point.get("airway"),
                "inserted": point.get("inserted", False),
            }
        )

    # Flight plan waypoint가 있으면 OFP 테이블에 나온 순서 그대로 경로로 사용 (route 문자열 무관, 지도 = OFP 표시)
    coordinates_from_plan = []
    if len(waypoints_from_plan) >= 3:
        for w in waypoints_from_plan:
            ident = (w.get("ident") or w.get("Waypoint") or "").strip().upper()
            lat, lon = w.get("lat"), w.get("lon")
            if ident and lat is not None and lon is not None:
                try:
                    coordinates_from_plan.append({
                        "lat": float(lat),
                        "lng": float(lon),
                        "ident": ident,
                    })
                except (TypeError, ValueError):
                    pass
        # OFP 테이블은 출발 공항(RKSI 등)을 포함하지 않을 수 있음 → route 첫 4자리(출발)를 맨 앞에 추가
        import re
        first_token = (route_text.strip().upper().split() or [""])[0]
        dep_match = re.match(r"^([A-Z]{4})\.?", first_token)
        dep_ident = dep_match.group(1) if dep_match else None
        if dep_ident and coordinates_from_plan and coordinates_from_plan[0].get("ident") != dep_ident:
            for point in result.get("points", []):
                if (point.get("ident") or "").upper() == dep_ident:
                    lat, lon = point.get("lat"), point.get("lon")
                    if lat is not None and lon is not None:
                        coordinates_from_plan.insert(0, {
                            "lat": float(lat),
                            "lng": float(lon),
                            "ident": dep_ident,
                        })
                        logger.info(f"출발 공항 {dep_ident} 경로 맨 앞에 추가")
                    break
    if coordinates_from_plan:
        logger.info(f"OFP 테이블 기반 경로 좌표: {len(coordinates_from_plan)}개 (Flight plan waypoint 순서 그대로)")

    out = {"coordinates": coordinates, "warnings": result.get("warnings", [])}
    if coordinates_from_plan:
        out["coordinates_from_plan"] = coordinates_from_plan
    return jsonify(out)


@api_bp.route("/api/fir-geojson", methods=["GET"])
def api_fir_geojson():
    data = load_fir_geojson()
    return jsonify(data)


@api_bp.route("/api/package3-polygons", methods=["GET"])
def api_package3_polygons():
    # 먼저 메모리 캐시에서 Package 3 텍스트 확인 (Cloud Run 호환성)
    package3_text = None
    try:
        # 순환 import 방지를 위해 함수를 통해 접근
        import sys
        if 'app' in sys.modules:
            from app import get_last_package3_text
            package3_text = get_last_package3_text()
            if package3_text:
                logger.info(f"Package 3 캐시에서 텍스트 사용: {len(package3_text)} 문자")
    except Exception as e:
        logger.debug(f"Package 3 캐시 확인 실패 (파일에서 읽기 시도): {e}")
    
    # 캐시가 없으면 파일에서 읽기
    if not package3_text:
        temp_dir = current_app.config.get("TEMP_FOLDER", "temp")
        if not os.path.isabs(temp_dir):
            temp_dir = os.path.join(current_app.root_path, temp_dir)
        parsed = get_package3_data(Path(temp_dir))
    else:
        # 캐시된 텍스트 사용
        parsed = get_package3_data(package3_text=package3_text)

    area_items = []
    for area in parsed.areas:
        area_items.append(
            {
                "notam_id": area.notam_id,
                "geometry": area.geometry,
                "coordinates": [{"lat": float(lat), "lng": float(lng)} for lat, lng in area.coordinates],
                "raw_coordinates": area.raw_coordinates,
                "description": area.description,
                "altitude_text": area.altitude_text,
                "restriction": area.restriction,
                "radius_nm": area.radius_nm,
                "radius_m": area.radius_nm * 1852.0 if area.radius_nm is not None else None,
                "is_buffer": area.is_buffer,
                "raw_notam_text": area.raw_notam_text,
                "affected_routes": area.affected_routes if hasattr(area, 'affected_routes') else [],
            }
        )

    constraint_items = []
    for constraint in parsed.altitude_constraints:
        constraint_items.append(
            {
                "notam_id": constraint.notam_id,
                "altitude_text": constraint.altitude_text,
                "airways": constraint.airways,
                "segments": [
                    {"airway": segment.airway, "points": segment.points, "raw": segment.raw}
                    for segment in constraint.segments
                ],
                "waypoints": constraint.waypoints,
                "description": constraint.description,
                "raw_notam_text": constraint.raw_notam_text,
            }
        )
    
    # VOR/NDB out of service 정보 추가
    navaid_items = []
    for navaid in parsed.navaids:
        navaid_item = {
            "notam_id": navaid.notam_id,
            "navaid_ident": navaid.navaid_ident,
            "navaid_type": navaid.navaid_type,
            "description": navaid.description,
            "raw_notam_text": navaid.raw_notam_text,
        }
        if navaid.coordinates:
            navaid_item["coordinates"] = {"lat": float(navaid.coordinates[0]), "lng": float(navaid.coordinates[1])}
        navaid_items.append(navaid_item)
    
    # 항로 폐쇄 정보 추가
    airway_closure_items = []
    for closure in parsed.airway_closures:
        closure_item = {
            "notam_id": closure.notam_id,
            "airway": closure.airway,
            "start_waypoint": closure.start_waypoint,
            "end_waypoint": closure.end_waypoint,
            "description": closure.description,
            "raw_notam_text": closure.raw_notam_text,
            "coordinates": [{"lat": float(coord[0]), "lng": float(coord[1])} for coord in closure.coordinates]
        }
        airway_closure_items.append(closure_item)

    return jsonify({
        "areas": area_items,
        "altitude_constraints": constraint_items,
        "navaids": navaid_items,
        "airway_closures": airway_closure_items
    })


@api_bp.route("/api/route-weather", methods=["POST"])
def api_route_weather():
    """Route 상의 waypoint들에 대한 날씨 정보를 반환"""
    payload = request.get_json(silent=True) or {}
    coordinates = payload.get("coordinates", [])
    weather_type = payload.get("type", "wind")  # wind, turbulence, satellite
    forecast_time = payload.get("forecast_time")  # 예상 시간 (ISO format)
    
    if not coordinates:
        return jsonify({"error": "coordinates parameter is required"}), 400
    
    try:
        # Windy API를 사용하여 날씨 정보 가져오기
        # 참고: Windy는 Tile 서버를 제공하지만, 특정 위치의 데이터를 가져오려면
        # 다른 방법이 필요할 수 있습니다.
        # 여기서는 기본 구조만 제공하고, 실제 API 호출은 프론트엔드에서 TileLayer로 처리
        
        weather_data = []
        for coord in coordinates:
            lat = coord.get("lat")
            lng = coord.get("lng")
            ident = coord.get("ident", "")
            
            if lat is None or lng is None:
                continue
            
            # Windy Tile 서버 URL 생성
            # 참고: 실제 구현 시 Windy API 키가 필요할 수 있습니다
            weather_info = {
                "lat": lat,
                "lng": lng,
                "ident": ident,
                "type": weather_type,
                "forecast_time": forecast_time,
                # 실제 날씨 데이터는 TileLayer를 통해 표시되므로
                # 여기서는 좌표 정보만 반환
            }
            weather_data.append(weather_info)
        
        return jsonify({
            "weather_data": weather_data,
            "type": weather_type,
            "forecast_time": forecast_time,
            "tile_url_template": f"https://tile.windy.com/{weather_type}/{{z}}/{{x}}/{{y}}.png"
        })
        
    except Exception as exc:
        logger.error(f"Route weather API error: {exc}", exc_info=True)
        return jsonify({"error": f"weather data retrieval failed: {exc}"}), 500


@api_bp.route("/api/aviation-weather", methods=["POST"])
def api_aviation_weather():
    """항공기상 정보 (METAR/TAF)를 가져옵니다 - Aviation Weather Center API 사용"""
    import requests
    import math
    
    payload = request.get_json(silent=True) or {}
    lat = payload.get("lat")
    lon = payload.get("lon")
    icao = payload.get("icao")  # 선택적: 공항 코드가 있으면 직접 사용
    
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon parameters are required"}), 400
    
    try:
        # 1. 공항 코드가 없으면 좌표로 가장 가까운 공항 찾기
        if not icao:
            # airports.csv에서 가장 가까운 공항 찾기
            airports_csv_path = os.path.join(os.path.dirname(__file__), 'airports.csv')
            nearest_airport = None
            min_distance = float('inf')
            
            if os.path.exists(airports_csv_path):
                import csv
                with open(airports_csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            airport_lat = float(row.get('latitude_deg', 0))
                            airport_lon = float(row.get('longitude_deg', 0))
                            airport_icao = (row.get('ident') or '').strip().upper()
                            
                            if not airport_icao or len(airport_icao) != 4:
                                continue
                            
                            # 거리 계산 (Haversine formula)
                            dlat = math.radians(airport_lat - lat)
                            dlon = math.radians(airport_lon - lon)
                            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(airport_lat)) * math.sin(dlon/2)**2
                            c = 2 * math.asin(math.sqrt(a))
                            distance = 6371 * c  # km
                            
                            # 50km 이내의 가장 가까운 공항
                            if distance < min_distance and distance < 50:
                                min_distance = distance
                                nearest_airport = airport_icao
                        except (ValueError, KeyError):
                            continue
            
            if nearest_airport:
                icao = nearest_airport
                logger.info(f"가장 가까운 공항: {icao} (거리: {min_distance:.1f}km)")
        
        if not icao:
            return jsonify({
                "error": "공항을 찾을 수 없습니다",
                "lat": lat,
                "lon": lon
            }), 404
        
        # 2. Aviation Weather Center API에서 METAR, TAF 가져오기
        metar_data = None
        taf_data = None
        
        # METAR 가져오기
        try:
            metar_url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"
            metar_response = requests.get(metar_url, timeout=10)
            
            if metar_response.status_code == 200:
                metar_json = metar_response.json()
                if metar_json and len(metar_json) > 0:
                    metar_data = metar_json[0]
                    logger.info(f"METAR 데이터 수신 (aviationweather.gov): {icao}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"METAR API 호출 실패: {e}")
        
        # TAF 가져오기
        try:
            taf_url = f"https://aviationweather.gov/api/data/taf?ids={icao}&format=json"
            taf_response = requests.get(taf_url, timeout=10)
            
            if taf_response.status_code == 200:
                taf_json = taf_response.json()
                if taf_json and len(taf_json) > 0:
                    taf_data = taf_json[0]
                    logger.info(f"TAF 데이터 수신 (aviationweather.gov): {icao}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"TAF API 호출 실패: {e}")
        
        return jsonify({
            "icao": icao,
            "lat": lat,
            "lon": lon,
            "metar": metar_data,
            "taf": taf_data,
            "atis": None,
            "source": "aviationweather.gov"
        })
        
    except Exception as exc:
        logger.error(f"Aviation Weather API error: {exc}", exc_info=True)
        return jsonify({"error": f"항공기상 데이터 가져오기 실패: {exc}"}), 500


@api_bp.route("/api/aviation-weather/pirep", methods=["POST"])
def api_pirep():
    """PIREP (Pilot Reports) 정보를 가져옵니다"""
    import requests
    
    payload = request.get_json(silent=True) or {}
    lat = payload.get("lat")
    lon = payload.get("lon")
    icao = payload.get("icao")  # 선택적: 공항 코드
    distance = payload.get("distance", 50)  # 반경 거리 (statute miles, 기본값 50)
    age = payload.get("age", 3)  # 시간 이내 데이터 (기본값 3시간)
    level = payload.get("level")  # 고도 ±3000ft (선택적)
    
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon parameters are required"}), 400
    
    try:
        # PIREP API 호출
        # bbox 또는 id+distance 사용
        pirep_data = []
        
        if icao:
            # 공항 코드가 있으면 id+distance 사용
            try:
                pirep_url = f"https://aviationweather.gov/api/data/pirep?format=json&id={icao}&distance={distance}&age={age}"
                if level:
                    pirep_url += f"&level={level}"
                
                logger.info(f"PIREP API 호출: {pirep_url}")
                pirep_response = requests.get(pirep_url, timeout=10)
                
                if pirep_response.status_code == 200:
                    pirep_json = pirep_response.json()
                    if isinstance(pirep_json, list):
                        pirep_data = pirep_json
                        logger.info(f"PIREP 데이터 수신: {icao} - {len(pirep_data)}개")
            except requests.exceptions.RequestException as e:
                logger.warning(f"PIREP API 호출 실패 (id+distance): {e}")
        
        # bbox로도 시도 (항로 상의 waypoint 근처)
        if not pirep_data:
            try:
                # 좌표 주변 bbox 생성 (±0.5도, 약 50nm)
                bbox = f"{lat-0.5},{lon-0.5},{lat+0.5},{lon+0.5}"
                pirep_url = f"https://aviationweather.gov/api/data/pirep?format=json&bbox={bbox}&age={age}"
                if level:
                    pirep_url += f"&level={level}"
                
                logger.info(f"PIREP API 호출 (bbox): {pirep_url}")
                pirep_response = requests.get(pirep_url, timeout=10)
                
                if pirep_response.status_code == 200:
                    pirep_json = pirep_response.json()
                    if isinstance(pirep_json, list):
                        pirep_data = pirep_json
                        logger.info(f"PIREP 데이터 수신 (bbox): {len(pirep_data)}개")
            except requests.exceptions.RequestException as e:
                logger.warning(f"PIREP API 호출 실패 (bbox): {e}")
        
        return jsonify({
            "icao": icao,
            "lat": lat,
            "lon": lon,
            "pireps": pirep_data,
            "count": len(pirep_data)
        })
        
    except Exception as exc:
        logger.error(f"PIREP API error: {exc}", exc_info=True)
        return jsonify({"error": f"PIREP 데이터 가져오기 실패: {exc}"}), 500


@api_bp.route("/api/aviation-weather/sigmet", methods=["POST"])
def api_sigmet():
    """SIGMET/AIRMET 정보를 가져옵니다"""
    import requests
    
    payload = request.get_json(silent=True) or {}
    lat = payload.get("lat")
    lon = payload.get("lon")
    bbox = payload.get("bbox")  # 선택적: 직접 bbox 제공
    hazard = payload.get("hazard")  # 선택적: turb, ice, conv, ifr
    level = payload.get("level")  # 선택적: 고도 ±3000ft
    
    # bbox가 없으면 좌표 주변으로 생성
    if not bbox and lat is not None and lon is not None:
        # ±2도 범위 (약 200nm)
        bbox = f"{lat-2},{lon-2},{lat+2},{lon+2}"
    
    if not bbox:
        return jsonify({"error": "bbox or lat/lon parameters are required"}), 400
    
    try:
        sigmet_data = []
        airsigmet_data = []
        isigmet_data = []
        
        # 1. Domestic SIGMETs (미국)
        try:
            airsigmet_url = f"https://aviationweather.gov/api/data/airsigmet?format=json&bbox={bbox}"
            if hazard:
                airsigmet_url += f"&hazard={hazard}"
            if level:
                airsigmet_url += f"&level={level}"
            
            logger.info(f"AirSIGMET API 호출: {airsigmet_url}")
            airsigmet_response = requests.get(airsigmet_url, timeout=10)
            
            if airsigmet_response.status_code == 200:
                airsigmet_json = airsigmet_response.json()
                if isinstance(airsigmet_json, list):
                    airsigmet_data = airsigmet_json
                    logger.info(f"AirSIGMET 데이터 수신: {len(airsigmet_data)}개")
        except requests.exceptions.RequestException as e:
            logger.warning(f"AirSIGMET API 호출 실패: {e}")
        
        # 2. International SIGMETs
        try:
            isigmet_url = f"https://aviationweather.gov/api/data/isigmet?format=json&bbox={bbox}"
            if hazard:
                isigmet_url += f"&hazard={hazard}"
            if level:
                isigmet_url += f"&level={level}"
            
            logger.info(f"ISIGMET API 호출: {isigmet_url}")
            isigmet_response = requests.get(isigmet_url, timeout=10)
            
            if isigmet_response.status_code == 200:
                isigmet_json = isigmet_response.json()
                if isinstance(isigmet_json, list):
                    isigmet_data = isigmet_json
                    logger.info(f"ISIGMET 데이터 수신: {len(isigmet_data)}개")
        except requests.exceptions.RequestException as e:
            logger.warning(f"ISIGMET API 호출 실패: {e}")
        
        # 3. G-AIRMETs (미국)
        try:
            gairmet_url = f"https://aviationweather.gov/api/data/gairmet?format=json&bbox={bbox}"
            if hazard:
                gairmet_url += f"&hazard={hazard}"
            
            logger.info(f"G-AIRMET API 호출: {gairmet_url}")
            gairmet_response = requests.get(gairmet_url, timeout=10)
            
            if gairmet_response.status_code == 200:
                gairmet_json = gairmet_response.json()
                if isinstance(gairmet_json, list):
                    # G-AIRMET도 airsigmet_data에 포함
                    airsigmet_data.extend(gairmet_json)
                    logger.info(f"G-AIRMET 데이터 수신: {len(gairmet_json)}개")
        except requests.exceptions.RequestException as e:
            logger.warning(f"G-AIRMET API 호출 실패: {e}")
        
        return jsonify({
            "lat": lat,
            "lon": lon,
            "bbox": bbox,
            "airsigmets": airsigmet_data,
            "isigmets": isigmet_data,
            "total_count": len(airsigmet_data) + len(isigmet_data)
        })
        
    except Exception as exc:
        logger.error(f"SIGMET API error: {exc}", exc_info=True)
        return jsonify({"error": f"SIGMET 데이터 가져오기 실패: {exc}"}), 500
