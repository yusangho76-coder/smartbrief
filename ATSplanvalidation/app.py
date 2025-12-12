"""
DocPack Route Validator - Streamlit 앱
PDF에서 ATS Flight Plan과 OFP route를 추출하고 비교합니다.
"""
import streamlit as st
import pdfplumber
import re
from pathlib import Path
from route_extractor import (
    extract_ofp_route_from_page,
    extract_ats_fpl_route_from_page,
    compare_routes
)

def is_docpack(text: str) -> bool:
    """
    docpack 파일인지 감지 (NOTAM, 기상자료, flightplan이 모두 포함된 종합 파일)
    docpack 파일은 반드시 "Important files"로 시작함
    """
    text_upper = text.upper()
    
    # docpack 파일은 반드시 "Important files"로 시작
    # 텍스트 앞부분(처음 500자)에서 확인하여 정확도 향상
    text_start = text_upper[:500].strip()
    starts_with_important_files = text_start.startswith('IMPORTANT FILES') or '**IMPORTANT FILES**' in text_start
    
    if not starts_with_important_files:
        return False
    
    # "Important files"로 시작하는 경우 추가 검증
    # NOTAM 패키지 정보가 포함되어 있는지 확인
    has_notam_package = 'KOREAN AIR NOTAM PACKAGE' in text_upper
    has_weather = any(keyword in text_upper for keyword in ['WEATHER', 'METAR', 'TAF', '기상', 'MET'])
    # flightplan은 공항코드.. 패턴 (예: RKSI..)이 있는지 확인
    has_flightplan_pattern = bool(re.search(r'[A-Z]{4}\.\.\.?', text_upper))
    has_flightplan_keyword = any(keyword in text_upper for keyword in ['FLIGHT PLAN', 'FLIGHTPLAN'])
    
    # "Important files"로 시작하고, NOTAM 패키지 또는 기상자료/flightplan이 포함되어 있으면 docpack
    is_docpack_file = starts_with_important_files and (has_notam_package or has_weather or has_flightplan_pattern or has_flightplan_keyword)
    
    return is_docpack_file

def extract_route_from_docpack(text: str) -> str:
    """
    docpack에서 route 문자열 추출
    출발공항.. 패턴 (예: RKSI..)을 찾고, DIST 키워드 전까지 추출
    이 패턴을 만족하지 못하면 빈 문자열 반환
    """
    # 출발공항.. 패턴 찾기 (예: RKSI.., RKSS.. 등)
    # 공항코드 4자 + 점 2개 이상 패턴의 시작 위치 찾기
    airport_pattern = r'\b([A-Z]{4}\.\.\.?)'
    airport_match = re.search(airport_pattern, text, re.IGNORECASE | re.MULTILINE)
    
    if not airport_match:
        return ''
    
    # 공항코드 패턴의 시작 위치
    start_pos = airport_match.start()
    
    # 시작 위치부터 첫 번째 DIST 키워드까지 찾기
    remaining_text = text[start_pos:]
    
    # DIST 키워드를 찾되, 단어 경계로 구분된 것만 찾기
    dist_pattern = r'\bDIST\b'
    dist_match = re.search(dist_pattern, remaining_text, re.IGNORECASE | re.MULTILINE)
    
    if not dist_match:
        return ''
    
    # DIST 키워드의 시작 위치
    dist_pos = dist_match.start()
    
    # 공항코드 패턴부터 DIST 키워드 전까지 추출
    route = remaining_text[:dist_pos].strip()
    
    # 공백 정리 (여러 공백을 하나로, 줄바꿈을 공백으로)
    route = ' '.join(route.split())
    
    # 추출된 route가 너무 길면 (예: 500자 이상) 잘못된 추출로 간주
    if len(route) > 500:
        return ''
    
    # 추출된 route가 NOTAM 본문처럼 보이는지 확인
    # NOTAM 본문에는 보통 "E)", "F)", "G)" 같은 필드 구분자가 포함됨
    if re.search(r'[A-Z]\)\s+', route):
        return ''
    
    return route

# 페이지 설정
st.set_page_config(
    page_title="ATS FPL Validator",
    page_icon="✈️",
    layout="wide"
)

# 제목
st.title("✈️ ATS FPL Route Validator")
st.markdown("---")
st.markdown("""
이 앱은 DocPack PDF에서 ATS Flight Plan과 OFP(Operation Flight Plan) route를 자동으로 추출하고 비교합니다.
""")

# 파일 업로드
uploaded_file = st.file_uploader(
    "DocPack PDF 파일을 업로드하세요",
    type=['pdf'],
    help="2페이지에 OFP route가 있고, 'COPY OF ATS FPL' 페이지에 ATS FPL route가 있는 PDF 파일을 업로드하세요."
)

if uploaded_file is not None:
    try:
        # 처리 중 상태 표시
        with st.spinner("⏳ 처리중..."):
            # PDF 파일 읽기 및 처리
            with pdfplumber.open(uploaded_file) as pdf:
                total_pages = len(pdf.pages)
                
                # 전체 PDF 텍스트 추출 (DocPack 파일이므로 검증 없이 바로 추출)
                all_text = ""
                page_texts = []  # 페이지별 텍스트 저장
                for page in pdf.pages:
                    page_text = page.extract_text()
                    page_texts.append(page_text if page_text else "")
                    if page_text:
                        all_text += page_text + "\n"
                
                # OFP route 추출 (DocPack 전용 추출 로직 사용)
                ofp_route = None
                ofp_page_num = None
                
                # DocPack에서 route 추출
                ofp_route = extract_route_from_docpack(all_text)
                if ofp_route:
                    ofp_page_num = "DocPack 전체"
                else:
                    # extract_route_from_docpack이 실패한 경우, 페이지별로 확인 (fallback)
                    max_pages_to_check = min(5, total_pages)
                    for page_idx in range(max_pages_to_check):
                        page_text = page_texts[page_idx]
                        if page_text:
                            ofp_route = extract_ofp_route_from_page(page_text)
                            if ofp_route:
                                ofp_page_num = page_idx + 1
                                break
                
                # "COPY OF ATS FPL" 페이지에서 ATS FPL route 추출
                ats_route = None
                ats_page_num = None
                for i, page_text in enumerate(page_texts):
                    if page_text and ('COPY OF ATS FPL' in page_text.upper() or 'ATS FPL' in page_text.upper()):
                        ats_route = extract_ats_fpl_route_from_page(page_text)
                        if ats_route:
                            ats_page_num = i + 1
                            break
            
        # 처리 완료 후 결과 표시
        st.info(f"📄 총 {total_pages}페이지의 PDF를 읽었습니다.")
        
        # 결과 표시
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"📋 OFP Route" + (f" ({ofp_page_num}페이지)" if ofp_page_num else ""))
            if ofp_route:
                st.success(f"✅ OFP route를 찾았습니다! ({ofp_page_num}페이지)")
                st.text_area("OFP Route", ofp_route, height=150, key="ofp_route")
            else:
                st.error("❌ 1페이지와 2페이지에서 OFP route를 찾을 수 없습니다.")
                if total_pages >= 1:
                    st.text_area("1페이지 텍스트", page_texts[0][:500] if page_texts[0] else "텍스트 없음", height=150, key="ofp_text_1")
                if total_pages >= 2:
                    st.text_area("2페이지 텍스트", page_texts[1][:500] if page_texts[1] else "텍스트 없음", height=150, key="ofp_text_2")
        
        with col2:
            st.subheader("📋 ATS FPL Route")
            if ats_route:
                st.success(f"✅ ATS FPL route를 찾았습니다! (페이지 {ats_page_num})")
                st.text_area("ATS FPL Route", ats_route, height=150, key="ats_route")
            else:
                st.error("❌ 'COPY OF ATS FPL' 페이지에서 route를 찾을 수 없습니다.")
                if ats_page_num:
                    st.info(f"ATS FPL 페이지는 {ats_page_num}페이지에서 찾았지만 route를 추출하지 못했습니다.")
        
        # 디버깅용 expander (결과 표시 후)
        if not ofp_route:
            max_pages_to_check = min(5, total_pages)
            for page_idx in range(max_pages_to_check):
                if page_texts[page_idx]:
                    with st.expander(f"🔍 {page_idx+1}페이지 텍스트 (디버깅)", expanded=False):
                        st.text(page_texts[page_idx][:2000] if page_texts[page_idx] else "텍스트 없음")
        
        if not ats_route and ats_page_num and page_texts[ats_page_num - 1]:
            with st.expander(f"🔍 ATS FPL 페이지 {ats_page_num} 텍스트 (디버깅)", expanded=False):
                st.text(page_texts[ats_page_num - 1][:2000] if page_texts[ats_page_num - 1] else "텍스트 없음")
        
        # 비교 결과
        if ofp_route and ats_route:
            st.markdown("---")
            st.subheader("🔍 Route 비교 결과")
            
            comparison = compare_routes(ofp_route, ats_route)
            
            # 정규화된 route 표시
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**정규화된 OFP Route:**")
                st.code(comparison['ofp_normalized'], language=None)
            with col2:
                st.markdown("**정규화된 ATS FPL Route:**")
                st.code(comparison['ats_normalized'], language=None)
            
            # 비교 결과
            if comparison['match']:
                st.success("✅ 두 route가 일치합니다!")
            else:
                st.warning("⚠️ 두 route에 차이가 있습니다.")
                
                # 차이점 표시
                if comparison['only_in_ofp']:
                    st.error(f"❌ OFP에만 있는 waypoint/airway: {', '.join(comparison['only_in_ofp'])}")
                
                if comparison['only_in_ats']:
                    st.error(f"❌ ATS FPL에만 있는 waypoint/airway: {', '.join(comparison['only_in_ats'])}")
                
                if comparison['order_mismatch']:
                    st.warning("⚠️ Waypoint 순서가 다릅니다:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**OFP 순서:**")
                        st.write(comparison['order_mismatch']['ofp_order'])
                    with col2:
                        st.markdown("**ATS FPL 순서:**")
                        st.write(comparison['order_mismatch']['ats_order'])
            
            # Waypoint 리스트 (비교 테이블 형식)
            with st.expander("📊 상세 Waypoint 리스트", expanded=True):
                ofp_waypoints = comparison['ofp_waypoints']
                ats_waypoints = comparison['ats_waypoints']
                
                # 테이블 데이터 준비
                max_len = max(len(ofp_waypoints), len(ats_waypoints))
                
                # 테이블 헤더
                table_data = {
                    'Index': list(range(max_len)),
                    'OFP Waypoint': [ofp_waypoints[i] if i < len(ofp_waypoints) else '' for i in range(max_len)],
                    'ATS FPL Waypoint': [ats_waypoints[i] if i < len(ats_waypoints) else '' for i in range(max_len)],
                    'Match': []
                }
                
                # 일치 여부 확인
                for i in range(max_len):
                    ofp_wpt = ofp_waypoints[i] if i < len(ofp_waypoints) else ''
                    ats_wpt = ats_waypoints[i] if i < len(ats_waypoints) else ''
                    match = '✅' if ofp_wpt == ats_wpt and ofp_wpt != '' else '❌' if ofp_wpt != '' and ats_wpt != '' else '⚠️'
                    table_data['Match'].append(match)
                
                # 테이블 형식으로 표시 (더 명확한 비교를 위해)
                # HTML 테이블로 표시 (pandas 없이)
                # CSS 스타일
                st.markdown("""
                <style>
                .waypoint-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 10px 0;
                    font-size: 14px;
                }
                .waypoint-table th {
                    background-color: #0d6efd;
                    color: white;
                    padding: 10px;
                    text-align: center;
                    border: 1px solid #ddd;
                    position: sticky;
                    top: 0;
                }
                .waypoint-table td {
                    padding: 8px;
                    text-align: center;
                    border: 1px solid #ddd;
                }
                .waypoint-table tr:nth-child(even) {
                    background-color: #f8f9fa;
                }
                .match-ok {
                    background-color: #d4edda !important;
                    color: #155724;
                    font-weight: bold;
                }
                .match-fail {
                    background-color: #f8d7da !important;
                    color: #721c24;
                    font-weight: bold;
                }
                .match-warn {
                    background-color: #fff3cd !important;
                    color: #856404;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # HTML 테이블 생성
                html_table = "<table class='waypoint-table'><thead><tr><th>Index</th><th>OFP Waypoint</th><th>ATS FPL Waypoint</th><th>Match</th></tr></thead><tbody>"
                
                for i in range(max_len):
                    ofp_wpt = ofp_waypoints[i] if i < len(ofp_waypoints) else ''
                    ats_wpt = ats_waypoints[i] if i < len(ats_waypoints) else ''
                    match = table_data['Match'][i]
                    
                    # 매치 상태에 따른 CSS 클래스
                    if match == '✅':
                        row_class = 'match-ok'
                    elif match == '❌':
                        row_class = 'match-fail'
                    else:
                        row_class = 'match-warn'
                    
                    html_table += f"<tr class='{row_class}'><td>{i}</td><td>{ofp_wpt}</td><td>{ats_wpt}</td><td>{match}</td></tr>"
                
                html_table += "</tbody></table>"
                st.markdown(html_table, unsafe_allow_html=True)
        
        elif ofp_route or ats_route:
            st.warning("⚠️ 하나의 route만 추출되었습니다. 두 route를 모두 추출해야 비교할 수 있습니다.")
        else:
            st.error("❌ OFP route와 ATS FPL route를 모두 찾을 수 없습니다.")
    
    except Exception as e:
        st.error(f"❌ 오류가 발생했습니다: {str(e)}")
        st.exception(e)

else:
    st.info("👆 위에서 PDF 파일을 업로드하세요.")
    st.markdown("---")
    # st.markdown("""
    # ### 사용 방법
    
    # 1. **PDF 파일 업로드**: DocPack PDF 파일을 선택합니다.
    # 2. **자동 추출**: 앱이 자동으로 다음을 수행합니다:
    #    - 2페이지에서 OFP route 추출
    #    - "COPY OF ATS FPL" 페이지에서 ATS Flight Plan route 추출
    # 3. **비교 결과 확인**: 두 route를 비교하여 차이점을 확인합니다.
    
    # ### Route 정규화 규칙
    
    # - 시간 정보 제거 (RKSI0255 → RKSI)
    # - TAS/고도 정보 제거 (N0495F320)
    # - 속도/고도 제약 제거 (/K0917S0980)
    # - DCT 제거
    # - ..를 공백으로 변환
    # """)

