"""
OFP(Operational Flight Plan) 텍스트에서 비행계획 요약 항목 추출.
비행분석에 표시할 Callsign, PAX, MEL/CDL, 연료, 중량, ETD/ETA 등 정리.
OFP 구조: 번호 붙은 섹션(3. MEL, 4. ..., 5. DISPATCH NOTES 등)과 헤더 블록 활용.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from markupsafe import Markup

# NavData apts.txt 에서 공항명 로드 캐시 (ident -> 표시용 이름)
_airport_name_cache: Optional[Dict[str, str]] = None


def _get_airport_name(ident: str) -> Optional[str]:
    """NavData apts.txt에서 ICAO 코드에 해당하는 공항명 반환. JAIPUR_INTL -> Jaipur International."""
    global _airport_name_cache
    if not ident or len(ident) != 4:
        return None
    ident = ident.upper()
    if _airport_name_cache is None:
        _airport_name_cache = {}
        apts_path = Path(__file__).resolve().parent.parent / "NavData" / "apts.txt"
        if apts_path.exists():
            try:
                with apts_path.open(encoding="utf-8") as f:
                    for line in f:
                        if not line.strip() or line.startswith(";"):
                            continue
                        parts = line.split()
                        if len(parts) < 5:
                            continue
                        code = parts[0].upper()
                        if len(code) == 4:
                            raw_name = parts[1].replace("_", " ").strip()
                            if raw_name.endswith(" INTL"):
                                raw_name = raw_name[:-5].strip() + " International"
                            else:
                                raw_name = raw_name.replace(" INTL ", " International ").replace(" INTL", " International")
                            raw_name = raw_name.title()
                            _airport_name_cache[code] = raw_name
            except Exception:
                pass
    name = _airport_name_cache.get(ident)
    return name if name else None


def _strip(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _section_block(text: str, section_num: int, title_keywords: List[str]) -> Optional[str]:
    """예: '3. MEL' 또는 '5. DISPATCH NOTES' 다음 블록을 다음 'N. ' 전까지 반환."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # "3. MEL" 또는 "5. DISPATCH NOTES" 형태
        m = re.match(r"^(\d+)\.\s+(.+)", stripped)
        if m:
            num = int(m.group(1))
            rest = m.group(2).upper()
            if num == section_num and any(kw in rest for kw in title_keywords):
                start = i
                break
    if start is None:
        return None
    # 다음 번호 섹션 전까지 수집
    block_lines = []
    for j in range(start + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if re.match(r"^\d+\.\s+", stripped):
            break
        if stripped:
            block_lines.append(stripped)
    return "\n".join(block_lines) if block_lines else None


def _first_in_block(block: Optional[str], pattern: str, group: int = 1) -> Optional[str]:
    if not block:
        return None
    m = re.search(pattern, block, re.IGNORECASE)
    if m and m.lastindex >= group:
        return _strip(m.group(group))
    return None


def _fuel_time_display(fuel_4digit: Optional[str], time_str: Optional[str]) -> str:
    """연료 4자리(100 lbs 단위) + 시간 'HH.MM' -> '84100 07시간32분' 형식."""
    parts = []
    if fuel_4digit:
        s = re.sub(r"\D", "", fuel_4digit)
        if len(s) >= 3:
            try:
                val = int(s)
                # 3~4자리: 100 lbs 단위 (0841 -> 84100), 5자리 이상은 그대로
                lbs = val * 100 if len(s) <= 4 else val
                parts.append(f"{lbs}")
            except ValueError:
                parts.append(fuel_4digit.strip())
    if time_str:
        s = time_str.strip()
        if re.match(r"^\d{1,2}\.\d{2}$", s):
            h, m = s.split(".")
            parts.append(f"{int(h):02d}시간{m}분")
        elif re.match(r"^\d{4}$", s):
            parts.append(f"{s[:2]}시간{s[2:]}분")
        else:
            parts.append(s)
    return " ".join(parts) if parts else ""


def _extract_header_block(text: str, max_chars: int = 4000) -> str:
    """OFP 앞부분(헤더·요약)만 반환. 'DIST LATITUDE' 또는 '3. MEL' 이전까지."""
    dist_pos = text.upper().find("DIST LATITUDE")
    if dist_pos > 0 and dist_pos < max_chars:
        max_chars = min(max_chars, dist_pos + 500)
    mel_pos = text.find("3. MEL")
    if mel_pos > 0 and mel_pos < max_chars:
        max_chars = min(max_chars, mel_pos + 500)
    return text[:max_chars]


def extract_flight_plan_summary(text: str) -> Dict[str, Any]:
    """
    OFP 전체 텍스트에서 비행계획 요약 항목을 추출합니다.
    섹션 번호(3. MEL, 4., 5. DISPATCH 등)와 헤더 블록을 이용해 정확히 매칭.
    """
    if not text or not text.strip():
        return _empty_summary()

    t = text
    header = _extract_header_block(t)
    out: Dict[str, Any] = {}

    # ----- 1. Callsign / 항공기 / 등록번호 (헤더에서만) -----
    # KAL497: -KAL497-IS 또는 KAL497, FLIGHT KAL497
    out["callsign"] = _first_in_block(header, r"[-]?KAL\s*(\d{3})", 1)
    if not out["callsign"]:
        out["callsign"] = _first_in_block(header, r"(?:FLIGHT|FLT)\s*(\w+\d+)", 1)
    if not out["callsign"]:
        out["callsign"] = _first_in_block(header, r"-([A-Z]{2,}\d{3,})-", 1)

    # A/C 타입: "781 HL8732 GENX-1B74 ..." 형태 라인에서 맨 앞 3자리 숫자 추출
    out["aircraft_type"] = _first_in_block(header, r"(?m)^\s*(\d{3})\s+HL\d{4}\b", 1)
    if not out["aircraft_type"]:
        out["aircraft_type"] = _first_in_block(header, r"A[/\s]*C\s*(?:TYPE)?\s*[:]?\s*(\w+)", 1)

    # HL7208: 등록번호
    out["registration"] = _first_in_block(header, r"\b(HL\d{4})\b", 1)
    if not out["registration"]:
        out["registration"] = _first_in_block(header, r"REG(?:\.|ISTRATION)?\s*[:]?\s*([A-Z0-9\-]{4,10})", 1)

    # 한 줄로 합치기: KAL497 / 789 / HL7208
    if out.get("callsign") or out.get("aircraft_type") or out.get("registration"):
        out["callsign_line"] = " / ".join([
            _strip(out.get("callsign")) or "—",
            _strip(out.get("aircraft_type")) or "—",
            _strip(out.get("registration")) or "—",
        ])
    else:
        out["callsign_line"] = None

    # ----- 2. PAX: FIRST 0/0 BUSINESS 19/24 ECONOMY 135/254 -----
    # OFP에서는 "1. PAX/CARGO RESERVATION" 다음 줄에 "PASSENGERS: FIRST 0/0 BUSINESS 19/24 ECONOMY 135/254"
    pax_section = _section_block(t, 1, ["PAX", "CARGO", "RESERVATION"]) or ""
    if not pax_section:
        pax_section = _section_block(t, 2, ["PAX", "PASSENGER"]) or ""
    if not pax_section:
        for line in t.splitlines():
            if "PASSENGERS:" in line.upper() and "FIRST" in line.upper() and "BUSINESS" in line.upper():
                pax_section = line
                break
    if not pax_section:
        for line in t.splitlines():
            if "FIRST" in line.upper() and "BUSINESS" in line.upper() and "ECONOMY" in line.upper():
                pax_section = line
                break
    first_n = _first_in_block(pax_section, r"FIRST\s*(\d+/\d+|\d+\s+\d+)", 1)
    biz_n = _first_in_block(pax_section, r"BUSINESS\s*(\d+/\d+|\d+\s+\d+)", 1)
    econ_n = _first_in_block(pax_section, r"ECONOMY\s*(\d+/\d+|\d+\s+\d+)", 1)
    if first_n or biz_n or econ_n:
        if first_n and " " in first_n and "/" not in first_n:
            first_n = first_n.replace(" ", "/", 1)
        if biz_n and " " in biz_n and "/" not in biz_n:
            biz_n = biz_n.replace(" ", "/", 1)
        if econ_n and " " in econ_n and "/" not in econ_n:
            econ_n = econ_n.replace(" ", "/", 1)
        out["pax_line"] = " ".join([
            "FIRST " + (first_n or "—"),
            "BUSINESS " + (biz_n or "—"),
            "ECONOMY " + (econ_n or "—"),
        ])
    else:
        out["pax_line"] = None

    # ----- 3. MEL / CDL (섹션 3 전체, 여러 줄) -----
    mel_block = _section_block(t, 3, ["MEL", "CDL"])
    if mel_block:
        mel_lines = [ln.strip() for ln in mel_block.splitlines() if ln.strip() and ("MEL" in ln.upper() or "CDL" in ln.upper() or ln.startswith("-"))]
        out["mel_cdl"] = "\n".join(mel_lines) if mel_lines else mel_block
    else:
        out["mel_cdl"] = _line_containing(t, "MEL 26-", 2) or _line_containing(t, "MEL / CDL", 5)

    # ----- 4. Trip fuel increase (한 줄만) -----
    block4 = _section_block(t, 4, ["TRIP", "FUEL", "2000", "ADDITIONAL"])
    if block4:
        for line in block4.splitlines():
            if "TRIP FUEL INCREASE" in line.upper() and "2000" in line.upper():
                out["trip_fuel_increase_2000lbs"] = line.strip()
                break
    if not out.get("trip_fuel_increase_2000lbs"):
        m = re.search(r"(-?\s*TRIP FUEL INCREASE FOR 2000\s*LBS[^\n]+)", t, re.IGNORECASE)
        if m:
            out["trip_fuel_increase_2000lbs"] = m.group(1).strip()

    # ----- 5. Dispatch note (TURB/CB 이전까지만) + TURB/CB 블록 별도 -----
    # OFP에 "- TURB/CB" 또는 "- CB/TURB" 둘 다 올 수 있음
    disp_block = _section_block(t, 5, ["DISPATCH", "NOTE"])
    if disp_block:
        disp_lines: List[str] = []
        turb_cb_lines: List[str] = []
        seen_turb_cb = False
        for ln in disp_block.splitlines():
            line = ln.strip()
            if not line:
                if seen_turb_cb:
                    turb_cb_lines.append("")
                continue
            if re.match(r"-\s*(?:TURB/CB|CB/TURB)\s*$", line, re.IGNORECASE):
                seen_turb_cb = True
                continue
            if seen_turb_cb:
                # 다음 "-" 로 시작하는 줄(다른 디스패치 항목)이 나오면 TURB/CB 블록 종료
                if line.startswith("-"):
                    break
                turb_cb_lines.append(line)
            else:
                if line.startswith("-"):
                    disp_lines.append(line)
        out["dispatch_note"] = "\n".join(disp_lines) if disp_lines else None
        out["turb_cb"] = "\n".join(turb_cb_lines).strip() if turb_cb_lines else None
    else:
        out["dispatch_note"] = _first_match(t, r"(-\s*CCF\s*:[^\n]+)", 1)
        if out["dispatch_note"]:
            for line in t.splitlines():
                if "DISC FUEL DUE" in line.upper() or re.search(r"TANK\s*:", line):
                    out["dispatch_note"] += "\n" + line.strip()
        out["turb_cb"] = None

    # TURB/CB가 DISPATCH NOTE에 없고, OFP 하단의 "TURB/CB INFO" 블록만 있는 경우 보완
    if not out.get("turb_cb"):
        lines_text = t.splitlines()
        turb_cb_info: List[str] = []
        for i, ln in enumerate(lines_text):
            if "TURB/CB INFO" in ln.upper():
                turb_cb_info.append(ln.strip())
                for j in range(i + 1, min(i + 10, len(lines_text))):
                    nxt = lines_text[j].strip()
                    if not nxt:
                        # 빈 줄 두 개 연속이면 종료
                        if j + 1 < len(lines_text) and not lines_text[j + 1].strip():
                            break
                        continue
                    # 다음 섹션 시작으로 보이는 패턴이면 종료
                    if nxt.startswith(("WEATHER BRIEFING", "ROUTE TO ALTN", "END OF", "---", "===")):
                        break
                    # TURB/CB 관련 키워드가 있으면 우선 포함
                    if any(k in nxt.upper() for k in ["CAUTION", "CB", "TURB", "SIG WX", "TURBULENCE", "CHART"]):
                        turb_cb_info.append(nxt)
                    # 아니더라도 처음 몇 줄은 그대로 포함 (설명 문장)
                    elif len(turb_cb_info) <= 4:
                        turb_cb_info.append(nxt)
                break
        if turb_cb_info:
            cleaned = [
                l for l in turb_cb_info
                if "TURB/CB INFO" not in l.upper() or not l.strip().startswith("-")
            ]
            out["turb_cb"] = "\n".join(cleaned).strip() if cleaned else "\n".join(turb_cb_info).strip()

    # ----- 6. Route fuel consumption (MEAN/ +581LBS 형식) -----
    block6 = _section_block(t, 6, ["CONSUMPTION", "STATISTICS", "ROUTE", "FUEL"])
    if block6:
        m = re.search(r"(MEAN/\s*[+\-]?\s*\d+\s*LBS[^\n]*(?:STAT[^\n]*)?)", block6, re.IGNORECASE)
        if m:
            out["route_fuel_consumption"] = m.group(1).strip()
    if not out.get("route_fuel_consumption"):
        out["route_fuel_consumption"] = _first_match(t, r"(MEAN/\s*[+\-]?\s*\d+\s*LBS[^\n]*)", 1)

    # ----- 7. Flight plan number: PLAN 6776 -----
    out["flight_plan_number"] = _first_match(t, r"\bPLAN\s+(\d{4,})", 1)
    if not out["flight_plan_number"]:
        out["flight_plan_number"] = _first_match(t, r"FLIGHT\s*PLAN\s*NUMBER\s*[:]?\s*(\S+)", 1)

    # ----- 8. APMS: "APMS/P 02.4" 에서 02.4 추출 -----
    for line in t.splitlines():
        if "APMS" in line.upper():
            m = re.search(r"APMS\s*/\s*P\s*(\d+\.?\d*)", line, re.IGNORECASE)
            if m:
                out["apms"] = m.group(1)
                break
            m = re.search(r"APMS[/\s]*P\s*(\d+\.?\d*)", line, re.IGNORECASE)
            if m:
                out["apms"] = m.group(1)
                break
            m = re.search(r"(\d+\.\d+)\s*PCNT", line)
            if m:
                out["apms"] = m.group(1)
                break

    # ----- 9. 평균 WIND/TEMP: P085/M54 또는 M058/M51 -----
    # Normal flight plan의 첫 번째 "100LBS" 바로 앞에 위치한 [PM]NNN/[PM]NN 패턴 추출
    # 예: "781 HL8570 GENX-1B74 BJ-HL NP16 F BRK 1518UK P085/M54 100LBS"
    _wt_m = re.search(r"([PM]\d{2,3}/[PM]\d{2,3})\s+100LBS", t, re.IGNORECASE)
    if _wt_m:
        out["avg_wind_temp"] = _wt_m.group(1).upper()
    if not out.get("avg_wind_temp"):
        # 폴백: AVG WIND/TEMP 헤더 인근 줄에서 [PM]NNN/[PM]NN 또는 M-only 패턴 검색
        lines_arr = t.splitlines()
        for i, line in enumerate(lines_arr):
            wt_m = re.search(r"([PM]\d{2,3}/[PM]\d{2,3})", line)
            if not wt_m:
                wt_m = re.search(r"(M\d{3}(?:/M\d{2,3})?)", line)
            if not wt_m:
                continue
            prev_ok = i > 0 and (
                "AVG WIND" in lines_arr[i - 1].upper()
                or "WIND/TEMP" in lines_arr[i - 1].upper()
                or "PROGS" in lines_arr[i - 1].upper()
            )
            if "AVG WIND" in line.upper() or "WIND/TEMP" in line.upper() or "PROGS" in line.upper() or prev_ok:
                out["avg_wind_temp"] = wt_m.group(1).upper()
                break

    # ----- 10. 비행 연료/시간 (TRIP 0841 07.32) -----
    m = re.search(r"TRIP\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t)
    if m:
        out["flight_time"] = _fuel_time_display(m.group(1), m.group(2))
    if not out.get("flight_time"):
        m = re.search(r"EET\s+(\d+)[\s:]*(\d*)", t, re.IGNORECASE)
        if m:
            out["flight_time"] = _fuel_time_display(m.group(1), m.group(2) or None)

    # ----- 11. Reserve (0139 01.23) -----
    m = re.search(r"RESERVE\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["reserve"] = _fuel_time_display(m.group(1), m.group(2))
    if not out.get("reserve"):
        m = re.search(r"\b(\d{3,4})\s+(\d{1,2}\.\d{2})\s+ACTL\s+ETD", t)
        if m:
            out["reserve"] = _fuel_time_display(m.group(1), m.group(2))

    # ----- 13. Alternate (VIJP (Jaipur International) 7100 00.36분) -----
    def _fmt_alternate(code: str, fuel: int, time_str: str) -> str:
        name = _get_airport_name(code)
        if name:
            return f"{code} ({name}) {fuel} {time_str}분"
        return f"{code} {fuel} {time_str}분"

    m = re.search(r"(?:ALTN|ALTERNATE)\s*[:\s/]*([A-Z]{4})\s+(\d{3,5})\s+(\d{2}\.\d{2})", t, re.IGNORECASE)
    if m:
        icao = m.group(1).upper()
        out["alternate_icao"] = icao
        fuel = int(m.group(2)) * 100 if len(m.group(2)) <= 4 else int(m.group(2))
        out["alternate"] = _fmt_alternate(icao, fuel, m.group(3))
    if not out.get("alternate"):
        m = re.search(r"N/([A-Z]{4})\s+(\d{4})\s+(\d{2}\.\d{2})", t)
        if m:
            icao = m.group(1).upper()
            out["alternate_icao"] = icao
            fuel = int(m.group(2)) * 100
            out["alternate"] = _fmt_alternate(icao, fuel, m.group(3))

    # ----- 14. RQD TAKEOFF (0980 08.55) -----
    m = re.search(r"RQD\s*TAKEOFF\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["rqd_takeoff"] = _fuel_time_display(m.group(1), m.group(2))

    # ----- 15. CCF/DISC fuel (5900 00.40) -----
    m = re.search(r"DISC\s+(\d{3,5})\s+(\d{2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["ccf_disc_fuel"] = _fuel_time_display(m.group(1), m.group(2))
    if not out.get("ccf_disc_fuel"):
        out["ccf_disc_fuel"] = _first_match(t, r"CCF\s*:\s*(\d+)\s*LBS", 1)
        if out["ccf_disc_fuel"]:
            out["ccf_disc_fuel"] = out["ccf_disc_fuel"] + " LBS INCLUDED IN DISC"
    # 연료 테이블 DISC 라벨용: dispatch note의 CCF 값과 "DISC FUEL DUE TO XXX" 문구
    out["disc_ccf_lbs"] = _first_match(t, r"CCF\s*:\s*(\d+)\s*LBS", 1)
    due_to = _first_match(t, r"DISC\s+FUEL\s+DUE\s+TO\s+([^\n\-]+)", 1)
    out["disc_due_to"] = due_to.strip() if due_to else None

    # ----- 16. Ramp out fuel (1051 09.35) -----
    m = re.search(r"RAMP\s*OUT\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["ramp_out_fuel"] = _fuel_time_display(m.group(1), m.group(2))
    if not out.get("ramp_out_fuel"):
        m = re.search(r"OUT\s+(\d{3,5})\s+(\d{1,2}\.\d{2})\s+ACTL", t)
        if m:
            out["ramp_out_fuel"] = _fuel_time_display(m.group(1), m.group(2))

    # ----- 17. FOD (0198 02.03) -----
    m = re.search(r"FOD\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["fod_reserve_fuel"] = _fuel_time_display(m.group(1), m.group(2))

    # ----- FINAL RES, 3 PCT CONT, REFILE RES, TANKERING, PLN TAKEOFF, TAXI (연료 블록 동일 형식) -----
    m = re.search(r"FINAL\s+RES\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["final_res"] = _fuel_time_display(m.group(1), m.group(2))
    m = re.search(r"(\d+)\s*PCT\s*CONT\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["pct_cont"] = _fuel_time_display(m.group(2), m.group(3))
        out["pct_cont_label"] = f"{m.group(1)} PCT CONT"
    m = re.search(r"REFILE\s+RES\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["refile_res"] = _fuel_time_display(m.group(1), m.group(2))
    m = re.search(r"ETP\s+RES\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["etp_res"] = _fuel_time_display(m.group(1), m.group(2))
    m = re.search(r"TANKERING\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["tankering"] = _fuel_time_display(m.group(1), m.group(2))
    m = re.search(r"PLN\s*TAKEOFF\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["pln_takeoff"] = _fuel_time_display(m.group(1), m.group(2))
    m = re.search(r"TAXI\s+(\d{3,5})(?:\s|$)", t, re.IGNORECASE)
    if m:
        out["taxi"] = _fuel_time_display(m.group(1), None)  # 시간 없음

    # ----- 18. AGTOW 503900 / MZFW -----
    m = re.search(r"AGTOW\s+(\d{4,6})", t, re.IGNORECASE)
    if m:
        agtow_val = m.group(1)
        out["agtow"] = str(int(agtow_val) * 100) if len(agtow_val) <= 5 else agtow_val
    # AGTOW 한계 요인: AGTOW가 나온 줄 또는 그 전후에서 MZFW 등 검색
    limited = None
    for line in t.splitlines():
        if "AGTOW" in line.upper():
            limited = _first_match(line, r"\b(MZFW|MLW|MTOW|STRUCTURAL)\b", 1)
            if limited:
                break
    if not limited:
        limited = _first_match(t, r"AGTOW\s+\d+\s+[/]?\s*(MZFW|MLW|MTOW|STRUCTURAL)", 1)
    if limited:
        out["agtow_limited_by"] = limited
    if out.get("agtow") and out.get("agtow_limited_by"):
        out["agtow"] = out["agtow"] + " / " + out["agtow_limited_by"]
    elif out.get("agtow"):
        out["agtow_limited_by"] = None

    # ----- 19. ACL / PLD / 여유 (116600 - 50400 = 66,200) -----
    acl_m = re.search(r"ACL\s+(\d{4,6})", t, re.IGNORECASE)
    pld_m = re.search(r"PLD\s+(\d{4,6})", t, re.IGNORECASE)
    if acl_m and pld_m:
        try:
            acl = int(acl_m.group(1)) * (100 if len(acl_m.group(1)) <= 5 else 1)
            pld = int(pld_m.group(1)) * (100 if len(pld_m.group(1)) <= 5 else 1)
            margin = acl - pld
            out["payload_margin"] = f"{acl} - {pld} = {margin:,}"
            out["acl"] = str(acl)
            out["pld"] = str(pld)
        except ValueError:
            out["acl"] = acl_m.group(1)
            out["pld"] = pld_m.group(1)

    # ----- 20. Cost index / Initial altitude / TOW (50 / FL320 / 437700) -----
    # Cost index: COST INDEX, CI, 또는 SPEED 줄의 "CRZ- 50" 형식
    ci = _first_match(t, r"COST\s*INDEX\s*[:]?\s*(\d+)", 1) or _first_match(t, r"CI\s*[:]?\s*(\d+)", 1) or _first_match(t, r"CRZ-\s*(\d+)", 1)
    init_alt = _first_match(t, r"INIT(?:IAL)?\s*ALT(?:ITUDE)?\s*[:]?\s*FL?\s*(\d{2,3})", 1) or _first_match(t, r"FL\s*(\d{2,3})\b", 1)
    tow_m = re.search(r"TOW\s+(\d{4,6})", t, re.IGNORECASE)
    tow_val = tow_m.group(1) if tow_m else None
    if tow_val and len(tow_val) <= 5:
        tow_val = str(int(tow_val) * 100)
    parts = [ci or "—", "FL" + init_alt if init_alt else "—", tow_val or "—"]
    out["cost_index"] = " / ".join(p for p in parts if p != "—")
    out["cost_index_value"] = ci  # Cost index 숫자만 (APMS 위 행용)
    out["initial_altitude"] = "FL" + init_alt if init_alt else None

    # ----- 22. MTOW - TOW = 차이 -----
    mtow_m = re.search(r"MTOW\s+(\d{4,6})", t, re.IGNORECASE)
    tow_m = re.search(r"TOW\s+(\d{4,6})", t, re.IGNORECASE)
    if mtow_m and tow_m:
        try:
            mtow = int(mtow_m.group(1)) * (100 if len(mtow_m.group(1)) <= 5 else 1)
            tow = int(tow_m.group(1)) * (100 if len(tow_m.group(1)) <= 5 else 1)
            out["mtow_tow"] = f"{mtow} - {tow} = {mtow - tow:,}"
        except ValueError:
            out["mtow_tow"] = f"{mtow_m.group(1)} - {tow_m.group(1)}"

    # ----- 23. MLDW - LDW = 차이 -----
    mldw_m = re.search(r"MLDW\s+(\d{4,6})", t, re.IGNORECASE)
    ldw_m = re.search(r"LDW\s+(\d{4,6})", t, re.IGNORECASE)
    if mldw_m and ldw_m:
        try:
            mldw = int(mldw_m.group(1)) * (100 if len(mldw_m.group(1)) <= 5 else 1)
            ldw = int(ldw_m.group(1)) * (100 if len(ldw_m.group(1)) <= 5 else 1)
            out["mldw_ldw"] = f"{mldw} - {ldw} = {mldw - ldw:,}"
        except ValueError:
            out["mldw_ldw"] = f"{mldw_m.group(1)} - {ldw_m.group(1)}"

    # ----- 24. ETD, ETA (한 줄: RKSI 0345Z ETA VIDP 1117Z) -----
    etd_m = re.search(r"ETD\s+([A-Z]{4})\s+(\d{4})Z?", t, re.IGNORECASE)
    eta_m = re.search(r"ETA\s+([A-Z]{4})\s+(\d{4})Z?", t, re.IGNORECASE)
    if etd_m and eta_m:
        out["etd_eta"] = f"{etd_m.group(1)} {etd_m.group(2)}Z ETA {eta_m.group(1)} {eta_m.group(2)}Z"
    out["etd"] = f"{etd_m.group(1)} {etd_m.group(2)}Z" if etd_m else None
    out["eta"] = f"{eta_m.group(1)} {eta_m.group(2)}Z" if eta_m else None

    # ----- 24. 2nd plan 연료·시간 (2ND-$ 280 0972 07.45 → FL280, 97200 07시간45분) -----
    # OFP: "2ND-$ 280 0972 07.45" → 280=FL, 0972=연료, 07.45=시간
    m = re.search(r"2ND[-\s\$]*\s+(\d+)\s+(\d{3,5})\s+(\d{1,2}\.\d{2})", t, re.IGNORECASE)
    if m:
        out["second_plan_fl"] = m.group(1)  # FL280
        out["second_plan_fuel_time_diff"] = _fuel_time_display(m.group(2), m.group(3))
    else:
        out["second_plan_fuel_time_diff"] = _line_containing(t, "2ND", 1)

    # ----- 무게 블록 (SOW, RWY, ZFW, MZFW, TOF, TIF, TCAP, TOW, MTOW, LDW, MLDW) -----
    def _weight_num(key: str) -> Optional[str]:
        m = re.search(rf"\b{key}\s+(\d{{4,6}})\b", t, re.IGNORECASE)
        if not m:
            return None
        v = m.group(1)
        if len(v) <= 5:
            try:
                return str(int(v) * 100)
            except ValueError:
                return v
        return v

    out["weight_sow"] = _weight_num("SOW")
    out["weight_rwy"] = _weight_num("RWY")
    out["weight_zfw"] = _weight_num("ZFW")
    out["weight_mzfw"] = _weight_num("MZFW")
    out["weight_tof"] = _weight_num("TOF")
    out["weight_tif"] = _weight_num("TIF")
    out["weight_tcap"] = _weight_num("TCAP")
    out["weight_tow"] = _weight_num("TOW")
    out["weight_mtow"] = _weight_num("MTOW")
    out["weight_ldw"] = _weight_num("LDW")
    out["weight_mldw"] = _weight_num("MLDW")
    # AGTOW, ACL, PLD는 이미 있음 (agtow, acl, pld)

    return out


def _line_containing(text: str, keyword: str, max_lines_after: int = 2) -> Optional[str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if keyword.upper() in line.upper():
            block = [line.strip()]
            for j in range(i + 1, min(i + 1 + max_lines_after, len(lines))):
                block.append(lines[j].strip())
            return " | ".join(b for b in block if b)
    return None


def _first_match(text: str, pattern: str, group: int = 1) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        if isinstance(group, int) and m.lastindex >= group:
            return _strip(m.group(group))
        if isinstance(group, int) and group == 1:
            return _strip(m.group(0))
    return None


def _empty_summary() -> Dict[str, Any]:
    keys = [
        "callsign", "aircraft_type", "registration", "callsign_line",
        "pax_line", "mel_cdl", "trip_fuel_increase_2000lbs", "dispatch_note",
        "turb_cb", "route_fuel_consumption", "flight_plan_number", "apms", "avg_wind_temp",
        "flight_time", "reserve", "alternate", "alternate_icao", "final_res", "pct_cont", "pct_cont_label",
        "refile_res", "etp_res", "rqd_takeoff", "ccf_disc_fuel", "tankering", "pln_takeoff", "taxi",
        "ramp_out_fuel", "fod_reserve_fuel", "agtow", "agtow_limited_by",
        "acl", "pld", "payload_margin", "cost_index", "cost_index_value", "initial_altitude",
        "mtow_tow", "mldw_ldw", "etd", "eta", "etd_eta", "second_plan_fl", "second_plan_fuel_time_diff",
        "disc_ccf_lbs", "disc_due_to",
        "weight_sow", "weight_rwy", "weight_zfw", "weight_mzfw", "weight_tof", "weight_tif",
        "weight_tcap", "weight_tow", "weight_mtow", "weight_ldw", "weight_mldw",
    ]
    return {k: None for k in keys}


# 무게 블록 표시 순서 (라벨, summary 키). 값이 있는 항목만 표시
WEIGHT_TABLE_KEYS = [
    ("SOW", "weight_sow"),
    ("AGTOW", "agtow"),  # agtow는 "503900" 또는 "503900 / MZFW" 형태
    ("RWY", "weight_rwy"),
    ("PLD", "pld"),
    ("ACL", "acl"),
    ("ZFW", "weight_zfw"),
    ("MZFW", "weight_mzfw"),
    ("TOF", "weight_tof"),
    ("TOW", "weight_tow"),
    ("MTOW", "weight_mtow"),
    ("TCAP", "weight_tcap"),
    ("LDW", "weight_ldw"),
    ("MLDW", "weight_mldw"),
    ("TIF", "weight_tif"),
]


# 연료/시간 테이블에 넣을 항목 (OFP 이미지 순서: 구분 | 연료 | 시간, 0값 포함)
# alternate: 라벨 "ALTN/{alternate_icao}". pct_cont: 라벨 "N PCT CONT" (OFP에 따라 3/5 등)
FUEL_TIME_KEYS = [
    ("TRIP", "flight_time"),
    ("RESERVE", "reserve"),
       (None, "alternate"),  # 라벨 = "ALTN/" + alternate_icao
       ("FINAL RES", "final_res"),
       (None, "pct_cont"),   # 라벨 = pct_cont_label (예: "3 PCT CONT", "5 PCT CONT"), 없으면 "—"
       ("REFILE RES", "refile_res"),
       ("ETP RES", "etp_res"),  # 있을 때만 파싱됨, 없으면 행 생략
    ("RQD TAKEOFF", "rqd_takeoff"),
    ("DISC", "ccf_disc_fuel"),
    ("TANKERING", "tankering"),
    ("PLN TAKEOFF", "pln_takeoff"),
    ("TAXI", "taxi"),
    ("RAMP OUT", "ramp_out_fuel"),
    ("FOD", "fod_reserve_fuel"),
]
_FUEL_TIME_KEY_SET = {k for (_, k) in FUEL_TIME_KEYS}


def get_flight_plan_summary_display_items(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    """템플릿용 (라벨, 값) 리스트. 10,11,13,14,15,16,17은 연료 테이블로 따로 가므로 제외."""
    label_map = [
        ("Flight plan number", "flight_plan_number"),
        ("Callsign / 항공기 / 등록번호", "callsign_line"),  # 한 줄: KAL497 / 789 / HL7208
        ("승객 탑승 (First / Business / Economy)", "pax_line"),
        ("MEL/CDL items", "mel_cdl"),
        ("Trip fuel increase (2000 lbs 추가 이륙중량)", "trip_fuel_increase_2000lbs"),
        ("Dispatch note", "dispatch_note"),
        ("TURB/CB", "turb_cb"),
        ("Route fuel consumption", "route_fuel_consumption"),
        ("Cost index", "cost_index_value"),  # CRZ- 50 등에서 추출, APMS 바로 위
        ("APMS", "apms"),
        ("평균 WIND/TEMP", "avg_wind_temp"),
        ("비행 연료/시간", "flight_time"),
        ("Reserve", "reserve"),
        ("Alternate", "alternate"),
        ("RQD TAKEOFF", "rqd_takeoff"),
        ("CCF/DISC fuel", "ccf_disc_fuel"),
        ("Ramp out fuel", "ramp_out_fuel"),
        ("FOD", "fod_reserve_fuel"),
        ("ETD, ETA", "etd_eta"),
        ("2nd plan 연료·시간 차이", "second_plan_fuel_time_diff"),  # 라벨은 FL 있으면 "2nd plan FL280"으로
    ]
    items = []
    for label, key in label_map:
        # 연료/시간 항목은 아래 연료 테이블에서만 표시
        if key in _FUEL_TIME_KEY_SET:
            continue
        # 2nd plan: FL 값 있으면 "2nd plan FL280" 형태로 라벨
        if key == "second_plan_fuel_time_diff" and summary.get("second_plan_fl"):
            label = f"2nd plan FL{summary.get('second_plan_fl')}"
        val = summary.get(key)
        if val is None:
            val = ""
        if isinstance(val, str):
            val = val.strip()
        items.append({"label": label, "value": val if val else "—", "key": key})
    return items


def _parse_fuel_time_value(value: str) -> tuple:
    """'84100 07시간32분' 또는 'VIJP (Jaipur International) 7100 00.36분' -> (fuel_str, time_str). 연료만 있으면 (fuel_str, '—')."""
    if not value or not value.strip():
        return ("—", "—")
    value = value.strip()
    parts = value.split()
    time_str = "—"
    fuel_str = "—"
    for i, p in enumerate(parts):
        if p.endswith("분"):
            time_str = p
            if i > 0:
                # 직전 토큰이 숫자면 연료
                prev = parts[i - 1].replace(",", "")
                if prev.replace(".", "").isdigit():
                    fuel_str = parts[i - 1]
                else:
                    # 더 앞에서 마지막 숫자 토큰 찾기 (Alternate 등)
                    for j in range(i - 1, -1, -1):
                        cand = parts[j].replace(",", "").replace(")", "")
                        if cand.replace(".", "").isdigit():
                            fuel_str = parts[j]
                            break
            break
    # 연료만 있는 경우 (TAXI 0012 등): 숫자 토큰 하나를 연료로
    if fuel_str == "—" and parts:
        for p in parts:
            cand = p.replace(",", "")
            if cand.replace(".", "").isdigit():
                fuel_str = cand
                break
    return (fuel_str, time_str)


def get_fuel_time_table(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    """연료/시간만 따로 쓰는 테이블용 행 목록. [ { label, fuel, time }, ... ]"""
    rows = []
    for label, key in FUEL_TIME_KEYS:
        raw_val = summary.get(key)
        # 플랜에 해당 항목이 아예 없으면 행을 표시하지 않음 (예: ETP RES가 없는 OFP)
        if raw_val is None:
            continue
        val = str(raw_val).strip()
        if not val:
            continue
        # 동적 라벨 처리
        if label is None and key == "alternate":
            label = "ALTN/" + (summary.get("alternate_icao") or "—")
        elif label is None and key == "pct_cont":
            label = summary.get("pct_cont_label") or "—"
        elif label is None:
            label = "—"
        # DISC 행: "DISC(CCF 1000 + DW/DA (ATC, ENROUTE WX))" 형태로 표시
        # 요청: "+ DW ..." 부분을 줄 바꿈해서 표시 (테이블에서 가독성 향상)
        if key == "ccf_disc_fuel" and label == "DISC":
            ccf = (summary.get("disc_ccf_lbs") or "").strip()
            due_to = (summary.get("disc_due_to") or "").strip()
            if ccf and due_to:
                # "+ DW ..." 부분을 줄 바꿈해서 두 줄로 표시
                label = Markup(f"DISC(CCF {ccf} +<br>{due_to})")
            elif ccf:
                label = f"DISC(CCF {ccf})"
            elif due_to:
                label = f"DISC({due_to})"
        fuel, time = _parse_fuel_time_value(val)
        # TRIP/RESERVE 아래, RQD TAKEOFF 위의 세부 항목들은 시각적으로 들여쓰기
        indent = key in {"alternate", "final_res", "pct_cont", "refile_res", "etp_res"}
        display_label: Any
        if indent:
            # HTML 템플릿에서 이스케이프되지 않도록 Markup 사용
            display_label = Markup("&nbsp;&nbsp;") + label
        else:
            display_label = label
        rows.append({"label": display_label, "fuel": fuel, "time": time, "indent": indent})
    return rows


def get_weight_table(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    """무게 블록 테이블용 행 목록. [ { label, value, match_agtow? }, ... ] — 값이 있는 항목만. MZFW+TOF, MLDW+TIF 합산 행 포함. AGTOW와 같은 값은 match_agtow=True."""
    rows = []
    # AGTOW 숫자만 추출 (예: "503900 / MZFW" -> "503900")
    agtow_raw = (summary.get("agtow") or "").strip()
    agtow_num = agtow_raw.split()[0] if agtow_raw and agtow_raw.split() else None
    if agtow_num and not agtow_num.isdigit():
        agtow_num = None

    for label, key in WEIGHT_TABLE_KEYS:
        val = summary.get(key)
        if val is None:
            continue
        val = str(val).strip()
        if not val:
            continue
        match_agtow = agtow_num is not None and val == agtow_num
        rows.append({"label": label, "value": val, "match_agtow": match_agtow})
        # TOF 행 다음에 MZFW+TOF 합산 행 추가 (OFP 무게 블록 표기)
        if key == "weight_tof":
            mzfw_s = (summary.get("weight_mzfw") or "").strip()
            tof_s = (summary.get("weight_tof") or "").strip()
            if mzfw_s and tof_s:
                try:
                    total = int(mzfw_s) + int(tof_s)
                    v = str(total)
                    rows.append({"label": "MZFW+TOF", "value": v, "match_agtow": agtow_num is not None and v == agtow_num})
                except ValueError:
                    pass
        # TIF 행 다음에 MLDW+TIF 합산 행 추가 (OFP 무게 블록 표기: TCAP, LDW, MLDW, TIF, MLDW+TIF 순)
        if key == "weight_tif":
            mldw_s = (summary.get("weight_mldw") or "").strip()
            tif_s = (summary.get("weight_tif") or "").strip()
            if mldw_s and tif_s:
                try:
                    total = int(mldw_s) + int(tif_s)
                    v = str(total)
                    rows.append({"label": "MLDW+TIF", "value": v, "match_agtow": agtow_num is not None and v == agtow_num})
                except ValueError:
                    pass
    return rows


def build_flight_plan_korean_report(summary: Dict[str, Any]) -> str:
    """
    사용자 예시 형식에 맞춘 한국어 Flight Plan 분석 리포트 생성.
    summary(dict)에 없는 값은 문장을 생략하거나 최소한으로만 표기.
    """
    lines: List[str] = []

    # 1. 항공편/기재/등록
    callsign_line = (summary.get("callsign_line") or "").strip()
    cs, ac_type, reg = None, None, None
    if callsign_line:
        parts = [p.strip() for p in callsign_line.split("/")]
        if len(parts) >= 1:
            cs = parts[0] or None
        if len(parts) >= 2:
            ac_type = parts[1] or None
        if len(parts) >= 3:
            reg = parts[2] or None
    if cs or ac_type or reg:
        # 예: "KE497, B789항공기 HL7208이고,"
        segs = []
        if cs:
            segs.append(f"{cs}")
        if ac_type:
            segs.append(f"{ac_type}항공기")
        if reg:
            segs.append(reg)
        lines.append("".join(segs) + "이고,")

    # 2. 승객 탑승
    pax_line = (summary.get("pax_line") or "").strip()
    if pax_line:
        lines.append(f"승객 탑승은 다음과 같고.\n{pax_line}")

    # 3. MEL / CDL
    mel = (summary.get("mel_cdl") or "").strip()
    if mel:
        lines.append("\nMEL 사항은 다음과 같고,\n" + mel)

    # 4. CCF / DISC / 추가 연료 (dispatch_note + ccf_disc_fuel)
    dispatch = (summary.get("dispatch_note") or "").strip()
    ccf_disc = (summary.get("ccf_disc_fuel") or "").strip()
    extra_fuel_desc = []
    if dispatch:
        extra_fuel_desc.append(dispatch)
    if ccf_disc and "CCF" in ccf_disc.upper() and "LBS" in ccf_disc.upper():
        extra_fuel_desc.append(ccf_disc)
    if extra_fuel_desc:
        lines.append("\n추가 연료 및 DISPATCH NOTE는 다음과 같습니다.\n" + "\n".join(extra_fuel_desc))

    # 5. TURB/CB (OFP에서 추출한 텍스트)
    turb_cb = (summary.get("turb_cb") or "").strip()
    if turb_cb:
        lines.append("\nTURB/CB 정보는 다음과 같습니다.\n" + turb_cb)
    else:
        lines.append("\nTURB/CB 정보는 별도 TURB/CB 섹션을 참고하십시오.")

    # 6. 연료 평균 통계
    route_stat = (summary.get("route_fuel_consumption") or "").strip()
    if route_stat:
        lines.append("\n연료 평균은\n" + route_stat)

    # 7. Flight Plan Number / 구간 / 계산 시각 (텍스트에서 추출한 경우가 없으므로 flight_plan_number만 사용)
    flight_plan_number = (summary.get("flight_plan_number") or "").strip()
    if flight_plan_number:
        lines.append(f"\nFlight Plan Number: {flight_plan_number}")

    # 8. 평균 풍속/온도, CI, APMS
    avg_wind_temp = (summary.get("avg_wind_temp") or "").strip()  # 예: M058/M51
    ci = None
    init_alt = None
    cost_index_combo = (summary.get("cost_index") or "").strip()
    # cost_index 필드에는 "50 / FL320 / 437700" 형식이 들어있을 수 있음
    m_ci = re.search(r"\b(\d+)\b", cost_index_combo)
    if m_ci:
        ci = m_ci.group(1)
    m_fl = re.search(r"FL(\d{2,3})", cost_index_combo)
    if m_fl:
        init_alt = "FL" + m_fl.group(1)

    apms = (summary.get("apms") or "").strip()
    if avg_wind_temp or ci or apms:
        desc_parts = []
        if avg_wind_temp:
            # M058/M51 → -58kts / -51도
            m = re.match(r"M(\d{3})(?:/M(\d{2,3}))?", avg_wind_temp)
            if m:
                wind = m.group(1)
                temp = m.group(2)
                if wind:
                    desc_parts.append(f"평균 풍속은 -{int(wind)}kts")
                if temp:
                    desc_parts.append(f"평균 온도는 -{int(temp)}도")
            else:
                desc_parts.append(f"평균 WIND/TEMP는 {avg_wind_temp}")
        if ci:
            desc_parts.append(f"cost index는 {ci}")
        if apms:
            desc_parts.append(f"APMS 값은 {apms}")
        if desc_parts:
            lines.append("\n" + " ".join(desc_parts) + " 입니다.")

    # 9. 주요 연료/시간 항목들
    def _add_if(label: str, key: str) -> Optional[str]:
        v = (summary.get(key) or "").strip()
        if v:
            return f"{label} {v}"
        return None

    fuel_lines: List[str] = []
    v = _add_if("TRIP fuel", "flight_time")  # flight_time에는 이미 연료+시간 조합이 들어 있음
    if v:
        fuel_lines.append(v)
    v = _add_if("Reserve", "reserve")
    if v:
        fuel_lines.append(v)
    v = _add_if("ALTN는", "alternate")
    if v:
        fuel_lines.append(v)
    v = _add_if("Required takeoff fuel은", "rqd_takeoff")
    if v:
        fuel_lines.append(v)
    v = _add_if("Discretionary fuel은", "ccf_disc_fuel")
    if v:
        fuel_lines.append(v)
    v = _add_if("Plan takeoff fuel은", "ramp_out_fuel")
    if v:
        fuel_lines.append(v)

    if fuel_lines:
        lines.append("\n연료는\n" + "\n".join(fuel_lines))

    # 10. Taxi / Ramp / FOD
    ramp = (summary.get("ramp_out_fuel") or "").strip()
    fod = (summary.get("fod_reserve_fuel") or "").strip()
    if ramp or fod:
        desc = []
        if ramp:
            desc.append(f"Ramp out fuel은 {ramp} 이고,")
        if fod:
            desc.append(f"FOD는 {fod} 입니다.")
        lines.append("\n" + " ".join(desc))

    # 11. 중량 여유
    payload_margin = (summary.get("payload_margin") or "").strip()
    mtow_tow = (summary.get("mtow_tow") or "").strip()
    mldw_ldw = (summary.get("mldw_ldw") or "").strip()
    if payload_margin or mtow_tow or mldw_ldw:
        segs = []
        if payload_margin:
            segs.append(f"ACL/PLD 여유는 {payload_margin} 입니다.")
        if mtow_tow:
            segs.append(f"MTOW와 TOW 차이는 {mtow_tow} 입니다.")
        if mldw_ldw:
            segs.append(f"MLDW와 LDW 차이는 {mldw_ldw} 입니다.")
        lines.append("\n" + " ".join(segs))

    # 12. ETD/ETA
    etd_eta = (summary.get("etd_eta") or "").strip()
    if etd_eta:
        lines.append(f"\nETD/ETA는 {etd_eta} 입니다.")

    # 13. 2nd plan
    second = (summary.get("second_plan_fuel_time_diff") or "").strip()
    if second:
        lines.append(f"\n2nd flight plan은 {second} 입니다.")

    report = "\n".join(l for l in lines if l and l.strip())
    return report


# ─── 공항별 기상(TAF) 분석 테이블 ───────────────────────────────

def extract_all_airports_from_text(text: str) -> Dict[str, Any]:
    """
    OFP 전체 텍스트에서 DEP, DEST, ALTN, REFILE, EDTO Entry/Exit 공항을 동적 추출.
    Returns: {
        "dep": "RKSI", "dest": "KSEA",
        "altn": ["KPDX"],
        "refile": [{"airport": "PANC", "decision_point": "56N50"}],
        "edto_entry_exit": [{"type": "Entry", "airport": "RJCC"}, {"type": "Exit", "airport": "PACD"}],
        "edto_enroute": ["RJCC", "PAKN"],
        "era": ["RJTT", "RJCC", "PACD", "PAKN", "PANC", "PAKT", "CYVR"],
        "etd_time": "0345", "eta_time": "1117",
    }
    """
    out: Dict[str, Any] = {
        "dep": None, "dest": None,
        "altn": [], "refile": [],
        "edto_entry_exit": [], "edto_enroute": [], "era": [],
        "etd_time": None, "eta_time": None,
    }

    etd_m = re.search(r"ETD\s+([A-Z]{4})\s+(\d{4})Z?", text, re.IGNORECASE)
    eta_m = re.search(r"ETA\s+([A-Z]{4})\s+(\d{4})Z?", text, re.IGNORECASE)
    if etd_m:
        out["dep"] = etd_m.group(1)
        out["etd_time"] = etd_m.group(2)
    if eta_m:
        out["dest"] = eta_m.group(1)
        out["eta_time"] = eta_m.group(2)

    # REFILE 섹션 이전(메인 플랜)만 사용 — REFILE 내부 ALTERNATE 줄이 메인 ALTN으로 오탐되는 것 방지
    refile_pos = text.upper().find("REFILE FLT PLAN")
    main_text = text[:refile_pos] if refile_pos > 0 else text

    # ALTN: "ALTERNATE - 1 KPDX ..." — main_text 범위(REFILE 이전)에서만 검색
    # 부정 전방탐색 (?![A-Z]) 으로 ALTERNATE WEATHER(→WEAT), ALTERNATE MINIMUMS(→MINI) 오탐 방지
    for m in re.finditer(r"ALTERNATE\s*-\s*\d+\s+([A-Z]{4})(?![A-Z])", main_text, re.IGNORECASE):
        code = m.group(1)
        if code not in out["altn"]:
            out["altn"].append(code)
    # "ALTN/KPDX" 패턴 — REFILE 섹션 이전 줄(메인 플랜)에서만 추출
    for m in re.finditer(r"ALTN/([A-Z]{4})", main_text):
        code = m.group(1)
        if code not in out["altn"]:
            out["altn"].append(code)

    # REFILE: "REFILE FLT PLAN ... \n- RKSI TO PANC - 56N50 TO KSEA"
    # role="dest" → REFILE 교체착륙지
    for m in re.finditer(
        r"REFILE\s+FLT\s+PLAN\b[^\n]*\n\s*-\s*[A-Z]{4}\s+TO\s+([A-Z]{4})\s*-\s*(\S+)\s+TO",
        text, re.IGNORECASE
    ):
        refile_apt = m.group(1)
        decision_pt = m.group(2)
        if not any(r["airport"] == refile_apt for r in out["refile"]):
            out["refile"].append({"airport": refile_apt, "decision_point": decision_pt, "role": "dest"})

    # REFILE 섹션 내 ALTN/ 패턴 → role="altn" (REFILE 교체 공항)
    if refile_pos > 0:
        refile_section = text[refile_pos:]
        for m in re.finditer(r"ALTN/([A-Z]{4})", refile_section):
            code = m.group(1)
            if not any(r["airport"] == code for r in out["refile"]):
                out["refile"].append({"airport": code, "decision_point": "", "role": "altn"})

    # EDTO Entry/Exit: "Entry point 0: RJCC" / "Exit point 0: PACD"
    for m in re.finditer(r"(Entry|Exit)\s+point\s+\d+\s*:\s*([A-Z]{4})", text, re.IGNORECASE):
        entry_type = m.group(1).capitalize()
        code = m.group(2)
        if not any(e["airport"] == code and e["type"] == entry_type for e in out["edto_entry_exit"]):
            out["edto_entry_exit"].append({"type": entry_type, "airport": code})

    # EDTO ENROUTE ALTERNATES: "RJCC SUITABLE FROM ..."
    for m in re.finditer(r"([A-Z]{4})\s+SUITABLE\s+FROM", text, re.IGNORECASE):
        code = m.group(1)
        if code not in out["edto_enroute"]:
            out["edto_enroute"].append(code)

    # Package 2: ERA 공항은 "ERA: ..." 라인에서만 추출 (NOTAM 본문 전체 스캔 시 KORE/NOTA/PACK 등 단어 조각이 들어감 방지)
    # Package 2 내 REFILE:/EDTO:/ERA: 라벨 블록 (라벨별 구분용)
    def _pkg2_block(key: str) -> str:
        """키로 시작하는 줄과, 다음 줄부터 다른 섹션(REFILE/EDTO/ERA:) 또는 빈 줄 전까지 이어붙임."""
        m = re.search(r"^" + key + r":\s*(.+)$", text, re.MULTILINE)
        if not m:
            return ""
        end_of_line = text.find("\n", m.end())
        if end_of_line == -1:
            end_of_line = len(text)
        chunk = m.group(1).strip()
        pos = end_of_line + 1
        while pos < len(text):
            line_end = text.find("\n", pos)
            if line_end == -1:
                line_end = len(text)
            line = text[pos:line_end].strip()
            if not line:
                break
            if re.match(r"^(REFILE|EDTO|ERA):", line, re.IGNORECASE):
                break
            chunk += " " + line
            pos = line_end + 1
        return chunk

    pkg2_refile = _pkg2_block("REFILE")
    if pkg2_refile:
        dest_codes = {r["airport"] for r in out["refile"] if r.get("role") == "dest"}
        for code in re.findall(r"[A-Z]{4}", pkg2_refile):
            if not any(r["airport"] == code for r in out["refile"]):
                role = "dest" if code in dest_codes else "altn"
                out["refile"].append({"airport": code, "decision_point": "", "role": role})
    pkg2_edto = _pkg2_block("EDTO")
    if pkg2_edto:
        for code in re.findall(r"[A-Z]{4}", pkg2_edto):
            if code not in out["edto_enroute"]:
                out["edto_enroute"].append(code)
    # ERA: 라인도 반영 (Package 2 섹션을 못 찾은 경우 또는 추가 공항)
    pkg2_era = _pkg2_block("ERA")
    if pkg2_era:
        for code in re.findall(r"[A-Z]{4}", pkg2_era):
            if code not in out["era"]:
                out["era"].append(code)

    return out


def _extract_weather_briefing_taf(text: str) -> Dict[str, str]:
    """
    WEATHER BRIEFING 섹션에서 DEPARTURE/ARRIVAL/ALTERNATE TAF 텍스트를 추출.
    Returns: {"dep_taf": "TAF RKSI ...", "arr_taf": "TAF ...", "altn_taf": "TAF ..."}
    """
    result = {"dep_taf": "", "arr_taf": "", "altn_taf": ""}
    wb_match = re.search(r"WEATHER\s+BRIEFING", text, re.IGNORECASE)
    if not wb_match:
        return result
    wb_text = text[wb_match.start():]
    # 끝 범위 제한 (다음 큰 섹션 시작 전)
    end_markers = [r"END\s+OF\s+JEPPESEN", r"ROUTE\s+TO\s+ALTN", r"REFILE\s+FLT\s+PLAN"]
    end_pos = len(wb_text)
    for em in end_markers:
        em_m = re.search(em, wb_text[200:], re.IGNORECASE)
        if em_m:
            end_pos = min(end_pos, 200 + em_m.start())
    wb_text = wb_text[:end_pos]

    dep_m = re.search(
        r"DEPARTURE\s+WEATHER[^\n]*\n[-]+\n(.*?)(?=(?:ARRIVAL\s+WEATHER|ALTERNATE\s+WEATHER|$))",
        wb_text, re.DOTALL | re.IGNORECASE
    )
    if dep_m:
        result["dep_taf"] = dep_m.group(1).strip()

    arr_m = re.search(
        r"ARRIVAL\s+WEATHER[^\n]*\n[-]+\n(.*?)(?=(?:ALTERNATE\s+WEATHER|$))",
        wb_text, re.DOTALL | re.IGNORECASE
    )
    if arr_m:
        result["arr_taf"] = arr_m.group(1).strip()

    alt_m = re.search(
        r"ALTERNATE\s+WEATHER[^\n]*\n[-]+\n(.*?)$",
        wb_text, re.DOTALL | re.IGNORECASE
    )
    if alt_m:
        result["altn_taf"] = alt_m.group(1).strip()

    return result


def _summarize_taf_line(taf_text: str) -> str:
    """TAF 텍스트를 한 줄 요약 (첫 TAF 줄 기반)."""
    if not taf_text:
        return "TAF 없음"
    first_line = taf_text.split("\n")[0].strip()
    if len(first_line) > 120:
        first_line = first_line[:120] + "…"
    return first_line


def _check_edto_ceiling_rvr(taf_text: str) -> Optional[str]:
    """
    EDTO ERA 공항의 TAF에서 ceiling 200ft 미만 또는 RVR 550m 미만 확인.
    문제가 있으면 경고 문자열 반환, 없으면 None.
    """
    if not taf_text:
        return None
    warnings = []
    # Ceiling: BKN/OVC + 3자리 (hundreds of ft). BKN003 = 300ft, OVC002 = 200ft
    for m in re.finditer(r"(BKN|OVC)(\d{3})", taf_text, re.IGNORECASE):
        ceil_ft = int(m.group(2)) * 100
        if ceil_ft < 200:
            warnings.append(f"Ceiling {ceil_ft}ft ({m.group(0)})")
    # RVR: "R??/????M" 또는 시정 미터 (4자리 SM 이하는 미터)
    for m in re.finditer(r"R\d{2}[LCR]?/(\d{4})M?", taf_text, re.IGNORECASE):
        rvr_m = int(m.group(1))
        if rvr_m < 550:
            warnings.append(f"RVR {rvr_m}m ({m.group(0)})")
    # 시정: ????SM 형식 (SM은 statute miles)
    for m in re.finditer(r"\b(\d{1,2})SM\b", taf_text):
        vis_sm = int(m.group(1))
        if vis_sm <= 0:
            warnings.append(f"VIS {vis_sm}SM")
    if warnings:
        return "; ".join(warnings)
    return None


def _fmt_hhmm(hhmm: Optional[str]) -> str:
    """'0345' -> '03:45Z'"""
    if not hhmm or len(hhmm) != 4:
        return hhmm or "—"
    return f"{hhmm[:2]}:{hhmm[2:]}Z"


def _flight_category(taf_item: Optional[Dict]) -> str:
    """
    Aviation Weather API TAF fcsts에서 가장 나쁜 비행 카테고리 반환.
    FAA 기준:
      VFR  : Ceiling > 3000ft  AND  Vis > 5SM
      MVFR : Ceiling 1000~3000ft  OR  Vis 3~5SM
      IFR  : Ceiling  500~999ft   OR  Vis 1~3SM (미만)
      LIFR : Ceiling < 500ft      OR  Vis < 1SM
    """
    if not taf_item:
        return ""

    _order = {"LIFR": 0, "IFR": 1, "MVFR": 2, "VFR": 3}

    def _ceil_cat(base_ft: int) -> str:
        if base_ft < 500:
            return "LIFR"
        if base_ft < 1000:
            return "IFR"
        if base_ft <= 3000:
            return "MVFR"
        return "VFR"

    def _vis_cat(vis_sm: float) -> str:
        if vis_sm < 1:
            return "LIFR"
        if vis_sm < 3:
            return "IFR"
        if vis_sm <= 5:
            return "MVFR"
        return "VFR"

    worst = "VFR"
    for fcst in taf_item.get("fcsts", []):
        for cloud in fcst.get("clouds", []):
            cover = (cloud.get("cover") or "").upper()
            base = cloud.get("base")
            if cover in ("BKN", "OVC") and base is not None:
                cat = _ceil_cat(int(base))
                if _order[cat] < _order[worst]:
                    worst = cat

        vis_str = str(fcst.get("visib") or "")
        if vis_str and vis_str not in ("6+", ""):
            try:
                if "/" in vis_str:
                    num, den = vis_str.split("/", 1)
                    vis_f = float(num) / float(den)
                else:
                    vis_f = float(vis_str.replace("+", ""))
                cat = _vis_cat(vis_f)
                if _order[cat] < _order[worst]:
                    worst = cat
            except Exception:
                pass

    return worst


def _fetch_metar_from_api(icao_list: List[str], timeout: int = 20) -> Dict[str, Optional[str]]:
    """
    Aviation Weather Center API에서 여러 공항의 최신 METAR raw 문자열을 가져온다.
    Returns: {"RKSI": "METAR RKSI ...", "KSEA": None, ...}
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    try:
        import requests as _requests
    except ImportError:
        return {code: None for code in icao_list}

    if not icao_list:
        return {}

    result: Dict[str, Optional[str]] = {code: None for code in icao_list}
    ids_param = ",".join(icao_list)
    url = f"https://aviationweather.gov/api/data/metar?ids={ids_param}&format=json&hoursBeforeNow=2"
    try:
        _log.info(f"METAR API 요청: {url}")
        resp = _requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                # 동일 공항에 여러 METAR가 있으면 가장 최신(첫 번째) 사용
                seen: set = set()
                for item in data:
                    icao = (item.get("icaoId") or "").upper()
                    if icao in result and icao not in seen:
                        result[icao] = item.get("rawOb") or item.get("rawMETAR") or None
                        seen.add(icao)
                _log.info(f"METAR API 성공: {list(seen)}")
        else:
            _log.warning(f"METAR API: HTTP {resp.status_code}")
    except Exception as e:
        _log.error(f"METAR API 호출 오류: {type(e).__name__}: {e}")
    return result


def _fetch_taf_from_api(icao_list: List[str], timeout: int = 20) -> Dict[str, Optional[Dict]]:
    """
    Aviation Weather Center API에서 여러 공항의 TAF를 한 번에 가져온다.
    Returns: {"RKSI": {rawTAF: "...", fcsts: [...]}, "KSEA": {...}, ...}
    실패한 공항은 None으로 반환.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    try:
        import requests as _requests
    except ImportError:
        _log.warning("TAF API: requests 라이브러리 없음")
        return {code: None for code in icao_list}

    if not icao_list:
        return {}

    result: Dict[str, Optional[Dict]] = {code: None for code in icao_list}
    ids_param = ",".join(icao_list)
    url = f"https://aviationweather.gov/api/data/taf?ids={ids_param}&format=json&hoursBeforeNow=24"
    try:
        _log.info(f"TAF API 요청: {url}")
        resp = _requests.get(url, timeout=timeout)
        _log.info(f"TAF API 응답: status={resp.status_code}, 길이={len(resp.text)}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                found = []
                for item in data:
                    icao = (item.get("icaoId") or "").upper()
                    if icao in result:
                        result[icao] = item
                        found.append(icao)
                _log.info(f"TAF API 성공: {found} / 요청={icao_list}")
            else:
                _log.warning(f"TAF API: 예상치 못한 응답 형식 - {type(data)}")
        else:
            _log.warning(f"TAF API: HTTP {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        _log.error(f"TAF API 호출 오류: {type(e).__name__}: {e}")
    return result


def _taf_raw(taf_item: Optional[Dict]) -> str:
    """TAF dict에서 rawTAF 문자열 반환. 없으면 빈 문자열."""
    if not taf_item:
        return ""
    return (taf_item.get("rawTAF") or "").strip()


def _check_edto_ceiling_rvr_from_api(taf_item: Optional[Dict]) -> Optional[str]:
    """
    Aviation Weather API의 TAF fcsts에서 ceiling 200ft 미만 / RVR 550m 미만 확인.
    문제 있으면 경고 문자열, 없으면 None.
    """
    if not taf_item:
        return None
    warnings = []
    for fcst in taf_item.get("fcsts", []):
        for cloud in fcst.get("clouds", []):
            cover = (cloud.get("cover") or "").upper()
            base_ft = cloud.get("base")  # 단위: feet
            if cover in ("BKN", "OVC") and base_ft is not None:
                if base_ft < 200:
                    warnings.append(f"Ceiling {base_ft}ft ({cover}{int(base_ft/100):03d})")
        # 시정 처리 (visib: "6+", "1/4", "1/2", 숫자 SM 등)
        vis = fcst.get("visib")
        if vis and str(vis) not in ("6+", "P6SM"):
            try:
                vis_f = float(str(vis).replace("+", "").split("/")[0]) if "/" not in str(vis) else float(str(vis).split("/")[0]) / float(str(vis).split("/")[1])
                if vis_f <= 0:
                    warnings.append(f"VIS {vis}SM")
            except Exception:
                pass
    # rawTAF에서 RVR 패턴도 확인
    raw = _taf_raw(taf_item)
    for m in re.finditer(r"R\d{2}[LCR]?/(\d{4})(?:FT)?M?", raw, re.IGNORECASE):
        rvr_m = int(m.group(1))
        if rvr_m < 550:
            warnings.append(f"RVR {rvr_m}m ({m.group(0)})")
    return "; ".join(dict.fromkeys(warnings)) if warnings else None


def _summarize_taf_from_api(taf_item: Optional[Dict], icao: str) -> str:
    """TAF dict의 rawTAF 첫 줄 요약."""
    raw = _taf_raw(taf_item)
    if not raw:
        return f"{icao}: TAF 없음 (Aviation Weather API)"
    first_line = raw.split("\n")[0].strip()
    return first_line[:140] + ("…" if len(first_line) > 140 else "")


def _highlight_active_taf_section(raw_taf: str, target_hhmm: str) -> str:
    """
    rawTAF 문자열에서 target_hhmm (예: '2027') 시각에 해당하는 FM 구간을
    <strong> 태그로 감싸 반환한다. 나머지 텍스트는 html.escape 처리.
    FM 구간이 없거나 대상 시각을 결정할 수 없으면 전체 텍스트를 escape만 해서 반환.
    """
    import html as _html

    if not raw_taf:
        return ""
    if not target_hhmm or len(target_hhmm) < 4:
        return _html.escape(raw_taf)

    try:
        t_hh = int(target_hhmm[:2])
        t_mm = int(target_hhmm[2:4])
    except ValueError:
        return _html.escape(raw_taf)

    # TAF 유효기간 (예: 0406/0512) → 기준일(start_day) 파악
    valid_m = re.search(r'\b(\d{2})(\d{2})/(\d{2})(\d{2})\b', raw_taf)
    start_day = int(valid_m.group(1)) if valid_m else 0

    def _to_abs(day: int, hh: int, mm: int) -> int:
        """start_day 00:00Z 기준 절대 분."""
        return (day - start_day) * 1440 + hh * 60 + mm

    # 대상 시각의 절대 분 결정
    if valid_m:
        v_start_hh = int(valid_m.group(2))
        v_end_day = int(valid_m.group(3))
        # 대상 시각이 유효기간 시작 시각보다 이르면 익일로 간주
        if t_hh < v_start_hh and v_end_day > start_day:
            target_abs = _to_abs(v_end_day, t_hh, t_mm)
        else:
            target_abs = _to_abs(start_day, t_hh, t_mm)
    else:
        target_abs = t_hh * 60 + t_mm

    # FM 구간 위치 추출: FM + DDHHMM
    fm_pat = re.compile(r'FM(\d{2})(\d{2})(\d{2})', re.IGNORECASE)
    positions = list(fm_pat.finditer(raw_taf))

    if not positions:
        return _html.escape(raw_taf)

    # 활성 FM 구간 탐색
    active_idx: Optional[int] = None
    for i, m in enumerate(positions):
        fm_abs = _to_abs(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if fm_abs <= target_abs:
            active_idx = i

    if active_idx is None:
        # 대상 시각이 첫 FM보다 이전 → 초기 예보 구간이 활성
        seg_start = 0
        seg_end = positions[0].start()
    else:
        seg_start = positions[active_idx].start()
        seg_end = (positions[active_idx + 1].start()
                   if active_idx + 1 < len(positions) else len(raw_taf))

    before = _html.escape(raw_taf[:seg_start])
    middle = _html.escape(raw_taf[seg_start:seg_end].rstrip())
    after = _html.escape(raw_taf[seg_end:])
    return f"{before}<strong class='fw-bold text-dark'>{middle}</strong>{after}"


def build_airport_weather_table(
    text: str,
    package_airports: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, str]]:
    """
    OFP 전체 텍스트에서 DEP/DEST/ALTN/REFILE/EDTO/ERA 공항별 TAF를
    Aviation Weather Center API(aviationweather.gov)에서 실시간으로 가져와
    분석 테이블을 생성.

    package_airports: 공항 필터 UI와 동일한 소스(notam_filter.extract_package_airports 결과).
                      전달 시 ERA 행은 package_airports['package2']를 사용(필터 UI와 일치).
    Returns: [
        {"time_utc": "07:10Z", "location": "RKSI (이륙)", "actm": "DEP", "content": "TAF ..."},
        ...
    ]
    """
    airports = extract_all_airports_from_text(text)
    # 공항 필터에서 추출한 Package 2 목록이 있으면 ERA 소스로 사용 (필터 UI와 동일)
    era_source: List[str] = []
    if package_airports and "package2" in package_airports:
        era_source = list(package_airports["package2"])
    else:
        era_source = airports.get("era", [])
    # OFP 내 WEATHER BRIEFING TAF (API 실패 시 폴백용)
    ofp_taf = _extract_weather_briefing_taf(text)

    etd_str = _fmt_hhmm(airports.get("etd_time"))
    eta_str = _fmt_hhmm(airports.get("eta_time"))
    dep = airports.get("dep") or ""
    dest = airports.get("dest") or ""

    # 모든 공항 코드 수집 (중복 제거)
    all_icao: List[str] = []
    seen_collect: set = set()
    for code in ([dep] if dep else []) + ([dest] if dest else []) + airports.get("altn", []):
        if code and code not in seen_collect:
            all_icao.append(code)
            seen_collect.add(code)
    for rf in airports.get("refile", []):
        code = rf["airport"]
        if code and code not in seen_collect:
            all_icao.append(code)
            seen_collect.add(code)
    for ee in airports.get("edto_entry_exit", []):
        code = ee["airport"]
        if code and code not in seen_collect:
            all_icao.append(code)
            seen_collect.add(code)
    for code in airports.get("edto_enroute", []) + era_source:
        if code and code not in seen_collect:
            all_icao.append(code)
            seen_collect.add(code)

    # Aviation Weather API 일괄 호출 (TAF)
    taf_map = _fetch_taf_from_api(all_icao)
    # DEP 공항 METAR 별도 조회
    metar_map = _fetch_metar_from_api([dep] if dep else [])

    import html as _html

    rows: List[Dict[str, str]] = []

    def _build_row(icao: str, ofp_fallback: str, label_type: str,
                   target_hhmm: str = "") -> Dict[str, str]:
        """API TAF 요약 + 비행 카테고리 + Ceiling/RVR 체크를 포함한 row 딕셔너리 반환.
        target_hhmm 이 주어지면 해당 시각의 FM 구간을 <strong> bold 처리한 content_html 생성.
        """
        taf_item = taf_map.get(icao)
        if taf_item:
            summary = _summarize_taf_from_api(taf_item, icao)
            raw = _taf_raw(taf_item)
        else:
            # AWC(aviationweather.gov)는 일부 공항(중국 내륙 등) TAF를 제공하지 않음
            no_taf_msg = f"{icao}: TAF 없음 (AWC 미제공)"
            summary = _summarize_taf_line(ofp_fallback) if ofp_fallback else no_taf_msg
            raw = ofp_fallback or ""
            taf_item = None

        # 비행 카테고리 (VFR/MVFR/IFR/LIFR)
        category = _flight_category(taf_item) if taf_item else ""

        is_edto_era = label_type in ("EDTO", "ERA", "REFILE")
        if is_edto_era:
            warn = _check_edto_ceiling_rvr_from_api(taf_item) if taf_item else _check_edto_ceiling_rvr(raw)
            suffix = f" ⚠️ EDTO 기준 미달: {_html.escape(warn)}" if warn else " ✅ Ceiling/RVR 기준 충족."
        else:
            good = any(k in summary.upper() for k in ("CAVOK", "P6SM", "SKC"))
            suffix = " ✅ 기상 양호." if good else ""

        # plain text content (기존 호환용)
        content = f"{summary}{suffix.replace(_html.escape(''), '')}"

        # HTML content: TAF 부분에 활성 FM 구간 bold 처리
        if raw and target_hhmm:
            taf_html = _highlight_active_taf_section(raw, target_hhmm)
        else:
            taf_html = _html.escape(summary)
        content_html = f"{taf_html}{_html.escape(suffix) if not suffix.startswith(' ✅') else _html.escape(suffix)}"

        return {"content": content, "content_html": content_html, "category": category}

    # DEP — METAR + TAF 함께 표시 (TAF는 ETD 시각 기준 bold)
    if dep:
        r = _build_row(dep, ofp_taf.get("dep_taf", ""), "DEP",
                       target_hhmm=airports.get("etd_time") or "")
        metar_raw = metar_map.get(dep)
        if metar_raw:
            dep_content_html = (f"<span class='text-secondary fw-semibold'>[METAR]</span> "
                                f"{_html.escape(metar_raw)}"
                                f" <span class='text-secondary'>|</span> "
                                f"<span class='text-secondary fw-semibold'>[TAF]</span> "
                                f"{r['content_html']}")
            dep_content = f"[METAR] {metar_raw} | [TAF] {r['content']}"
        else:
            dep_content_html = r["content_html"]
            dep_content = r["content"]
        rows.append({
            "time_utc": etd_str,
            "location": f"{dep} (이륙)",
            "actm": "DEP",
            "content": dep_content,
            "content_html": dep_content_html,
            "category": r["category"],
        })

    # DEST
    if dest:
        r = _build_row(dest, ofp_taf.get("arr_taf", ""), "DEST",
                       target_hhmm=airports.get("eta_time") or "")
        rows.append({
            "time_utc": eta_str,
            "location": f"{dest} (도착)",
            "actm": "ETA",
            "content": r["content"],
            "content_html": r["content_html"],
            "category": r["category"],
        })

    # 메인 ALTN 집합 (메인 플랜에서 추출된 교체 공항)
    main_altn_set = set(airports.get("altn", []))

    # ALTN — 메인 플랜 교체 공항은 모두 표시 (REFILE에도 나타나더라도 우선)
    for altn_code in airports.get("altn", []):
        r = _build_row(altn_code, ofp_taf.get("altn_taf", ""), "ALTN",
                       target_hhmm=airports.get("eta_time") or "")
        rows.append({
            "time_utc": eta_str,
            "location": f"{altn_code} (교체)",
            "actm": "ETA",
            "content": r["content"],
            "content_html": r["content_html"],
            "category": r["category"],
        })

    # REFILE
    for rf in airports.get("refile", []):
        rf_apt = rf["airport"]
        role = rf.get("role", "dest")

        # role="altn"이고 이미 메인 ALTN에 있으면 건너뜀 (중복 방지)
        # 예: KPDX는 메인 플랜에도 ALTN/KPDX로 나오므로 위에서 이미 표시됨
        if role == "altn" and rf_apt in main_altn_set:
            continue

        if role == "altn":
            # 메인 플랜에 없는 REFILE 전용 교체 (예: PAED)
            location_label = f"{rf_apt} (REFILE ALTN)"
        else:
            # REFILE 교체착륙지 (예: PANC)
            location_label = f"{rf_apt} (REFILE)"

        r = _build_row(rf_apt, "", "REFILE")
        rows.append({
            "time_utc": "—",
            "location": location_label,
            "actm": "REFILE",
            "content": r["content"],
            "content_html": r["content_html"],
            "category": r["category"],
        })

    # EDTO Entry/Exit
    seen_edto: set = set()
    for ee in airports.get("edto_entry_exit", []):
        apt = ee["airport"]
        etype = ee["type"]
        if apt in seen_edto:
            continue
        seen_edto.add(apt)
        r = _build_row(apt, "", "EDTO")
        rows.append({
            "time_utc": "—",
            "location": f"{apt} (EDTO {etype})",
            "actm": "EDTO",
            "content": r["content"],
            "content_html": r["content_html"],
            "category": r["category"],
        })

    # EDTO ENROUTE ALTERNATES
    for enrt in airports.get("edto_enroute", []):
        if enrt in seen_edto:
            continue
        seen_edto.add(enrt)
        r = _build_row(enrt, "", "EDTO")
        rows.append({
            "time_utc": "—",
            "location": f"{enrt} (EDTO Enroute)",
            "actm": "EDTO",
            "content": r["content"],
            "content_html": r["content_html"],
            "category": r["category"],
        })

    # ERA (EDTO에 없는 공항만, 소스: package_airports['package2'] 또는 extract ERA)
    for era_apt in era_source:
        if era_apt in seen_edto:
            continue
        seen_edto.add(era_apt)
        r = _build_row(era_apt, "", "ERA")
        rows.append({
            "time_utc": "—",
            "location": f"{era_apt} (ERA)",
            "actm": "ERA",
            "content": r["content"],
            "content_html": r["content_html"],
            "category": r["category"],
        })

    return rows


def extract_high_terrain_waypoints(text: str, etd_hhmm: str = "") -> List[Dict[str, Any]]:
    """
    첫 번째 비행 계획(REFILE 이전)에서 MSA > 10,000ft (---/ 뒤 숫자 > 100) 구간을 추출.
    연속된 고지대 구간은 하나의 세그먼트로 묶어 반환.

    Returns: [
        {
            "from_wp": "EPGAL", "to_wp": "TAXOR",
            "msa_ft": 10400, "fl": 381,
            "entry_utc": "10:06Z", "exit_utc": "10:18Z",
            "segment": True,           # 단일 구간 vs 연속 구간
        },
        ...
    ]
    """
    # 첫 번째 비행 계획 블록만 사용
    # (1) REFILE FLT PLAN 이전
    refile_pos = text.upper().find("REFILE FLT PLAN")
    plan_text = text[:refile_pos] if refile_pos > 0 else text
    # (2) "CFP PLAN"이 두 번 이상 나오면 두 번째부터는 제거 (동일 계획서 중복 방지)
    cfp_matches = [m.start() for m in re.finditer(r"CFP PLAN", plan_text, re.IGNORECASE)]
    if len(cfp_matches) >= 2:
        plan_text = plan_text[:cfp_matches[1]]

    # ETD 절대 분 계산
    etd_total_min = 0
    if etd_hhmm and len(etd_hhmm) >= 4:
        try:
            etd_total_min = int(etd_hhmm[:2]) * 60 + int(etd_hhmm[2:4])
        except ValueError:
            pass

    def _elapsed_to_utc(elapsed_hh: int, elapsed_mm: int) -> str:
        if etd_total_min == 0:
            return f"+{elapsed_hh:02d}:{elapsed_mm:02d}"
        total = etd_total_min + elapsed_hh * 60 + elapsed_mm
        return f"{(total // 60) % 24:02d}:{total % 60:02d}Z"

    # 데이터 줄 패턴: <dist> <lat> <lon_part> <hdg> <FL> ---/<MSA> ...
    data_pat = re.compile(
        r'^\s*\d{4}\s+[NS]\d+\s+[\d.]+\s+\d+\s+(\d{3})\s+---/(\d{3})'
    )
    # 웨이포인트 줄 패턴: <NAME> <E|W><lon> ... <HH>.<MM> <dist>/
    wp_pat = re.compile(
        r'^\s*([A-Z][A-Z0-9]{1,4})\s+[EW]\d+\s+[\d.]+\s+\d+\s+/.*?(\d{2})\.(\d{2})\s+\d{4}/'
    )
    # 이전 웨이포인트 행 패턴: <course> <WPNAME>  또는  <WPNAME> 단독
    prev_wp_pat = re.compile(r'^\s*(?:\d{3}\s+)?([A-Z][A-Z0-9]{1,4})\s*$')

    lines = plan_text.splitlines()

    # 각 데이터 줄로부터 (FL, msa_ft, dest_wp, elapsed_hh, elapsed_mm, from_wp) 추출
    segments_raw: List[Dict[str, Any]] = []
    prev_wp_name = ""

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # 이전 웨이포인트 이름 트래킹 (예: "243 TAXOR" 또는 "/ ZPKM FIR 244 KUNMING FIR TAXOR")
        prev_m = prev_wp_pat.match(stripped)
        if prev_m and not data_pat.match(stripped):
            candidate = prev_m.group(1)
            # 너무 짧거나 숫자만인 경우 제외
            if len(candidate) >= 2 and not candidate.isdigit():
                prev_wp_name = candidate
            i += 1
            continue

        data_m = data_pat.match(stripped)
        if data_m:
            fl = int(data_m.group(1))
            msa_code = int(data_m.group(2))
            msa_ft = msa_code * 100

            # 다음 유효 줄(Page 구분선 제외)에서 목적지 웨이포인트 파악
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("Page")):
                j += 1

            if j < len(lines):
                wp_m = wp_pat.match(lines[j].strip())
                if wp_m:
                    dest_wp = wp_m.group(1)
                    e_hh = int(wp_m.group(2))
                    e_mm = int(wp_m.group(3))
                    segments_raw.append({
                        "from_wp": prev_wp_name,
                        "to_wp": dest_wp,
                        "fl": fl,
                        "msa_ft": msa_ft,
                        "elapsed_hh": e_hh,
                        "elapsed_mm": e_mm,
                    })
                    prev_wp_name = dest_wp
                    i = j + 1
                    continue
        i += 1

    # MSA > 10,000ft인 구간만 필터
    high = [s for s in segments_raw if s["msa_ft"] > 10000]
    if not high:
        return []

    # 연속 구간 병합: 연속된 leg들을 하나의 세그먼트로 묶기
    merged: List[Dict[str, Any]] = []
    grp_start = high[0]
    grp_end = high[0]
    grp_max_msa = high[0]["msa_ft"]

    for seg in high[1:]:
        # 직전 seg의 to_wp == 현재 seg의 from_wp 이면 연속
        if seg["from_wp"] == grp_end["to_wp"]:
            grp_end = seg
            grp_max_msa = max(grp_max_msa, seg["msa_ft"])
        else:
            # 병합 결과 저장
            merged.append({
                "from_wp": grp_start["from_wp"] or grp_start["to_wp"],
                "to_wp": grp_end["to_wp"],
                "max_msa_ft": grp_max_msa,
                "fl": grp_start["fl"],
                "entry_utc": _elapsed_to_utc(grp_start["elapsed_hh"], grp_start["elapsed_mm"]),
                "exit_utc": _elapsed_to_utc(grp_end["elapsed_hh"], grp_end["elapsed_mm"]),
            })
            grp_start = seg
            grp_end = seg
            grp_max_msa = seg["msa_ft"]

    merged.append({
        "from_wp": grp_start["from_wp"] or grp_start["to_wp"],
        "to_wp": grp_end["to_wp"],
        "max_msa_ft": grp_max_msa,
        "fl": grp_start["fl"],
        "entry_utc": _elapsed_to_utc(grp_start["elapsed_hh"], grp_start["elapsed_mm"]),
        "exit_utc": _elapsed_to_utc(grp_end["elapsed_hh"], grp_end["elapsed_mm"]),
    })

    return merged


def extract_etp_summaries(text: str, etd_hhmm: str = "") -> List[Dict[str, Any]]:
    """
    OFP 텍스트에서 EQUAL TIME POINT DATA 블록(ETP01 등)의 요약 정보를 추출한다.

    예시 블록:
        RJCC/PAKN - EQUAL TIME POINT DATA - ETP01
        ETP LOCATION N51 58.2 E167 16.8 ETE 03.54
        GWT AT DIVERSION 461763 FOB 076562
        DIVERSION AIRPORTS RJCC PAKN
        G/C DIST 1172 1282
        ...
        CRITICAL FUEL REQUIRED AT ETP01 - DECOMP 1 ENG TO PAKN
        AMOUNT TIME
        CFR 046193 03.39
        FOB 076562
        QTY DIFF. 30369

    Returns: [
        {
            "label": "ETP01",
            "pair": "RJCC/PAKN",
            "from_apt": "RJCC",
            "to_apt": "PAKN",
            "location": "N51 58.2 E167 16.8",
            "ete": "03:54",
            "etp_utc": "10:04Z" 또는 "+03:54",
            "gcdist_from": 1172,
            "gcdist_to": 1282,
            "cfr_lbs": 46193,
            "cfr_time": "03:39",
            "fob_lbs": 76562,
            "diff_lbs": 30369,
            "scenario": "DECOMP 1 ENG TO PAKN",
        },
        ...
    ]
    """
    # 첫 번째 플랜 블록만 사용 (high terrain과 동일 로직)
    refile_pos = text.upper().find("REFILE FLT PLAN")
    plan_text = text[:refile_pos] if refile_pos > 0 else text
    cfp_matches = [m.start() for m in re.finditer(r"CFP PLAN", plan_text, re.IGNORECASE)]
    if len(cfp_matches) >= 2:
        plan_text = plan_text[:cfp_matches[1]]

    # ETD 절대 분
    etd_total_min = 0
    if etd_hhmm and len(etd_hhmm) >= 4:
        try:
            etd_total_min = int(etd_hhmm[:2]) * 60 + int(etd_hhmm[2:4])
        except ValueError:
            pass

    def _ete_to_utc(ete_str: str) -> Tuple[str, str]:
        """
        '03.54' → ('03:54', '10:04Z') 형태로 변환.
        ETD 정보가 없으면 etp_utc는 '+03:54' 형식으로 반환.
        """
        m = re.match(r"(\d{2})\.(\d{2})", ete_str)
        if not m:
            return ete_str, f"+{ete_str}"
        hh = int(m.group(1))
        mm = int(m.group(2))
        ete_fmt = f"{hh:02d}:{mm:02d}"
        if etd_total_min == 0:
            return ete_fmt, f"+{ete_fmt}"
        total = etd_total_min + hh * 60 + mm
        return ete_fmt, f"{(total // 60) % 24:02d}:{total % 60:02d}Z"

    lines = plan_text.splitlines()
    out: List[Dict[str, Any]] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        uline = line.upper()

        # ETP LOCATION 이 있는 줄을 기준으로 블록 시작을 판단
        if "ETP LOCATION" not in uline:
            i += 1
            continue

        # 보통 바로 위나 두 줄 위에 "RJCC/PAKN - EQUAL TIME POINT DATA - ETP01" 가 존재
        from_apt = to_apt = ""
        label = ""
        for k in range(max(0, i - 3), i + 1):
            h = lines[k].strip()
            mh = re.search(r"([A-Z]{4})/([A-Z]{4}).*ETP(\d+)", h)
            if mh:
                from_apt, to_apt = mh.group(1), mh.group(2)
                label = "ETP" + mh.group(3)
                break

        # 헤더를 찾지 못하면 DIVERSION AIRPORTS 줄과 CRITICAL FUEL REQUIRED 줄에서 보완
        # (아래 블록 파싱 과정에서 채워질 수 있음)
        item: Dict[str, Any] = {
            "label": label,
            "pair": f"{from_apt}/{to_apt}",
            "from_apt": from_apt,
            "to_apt": to_apt,
            "location": "",
            "ete": "",
            "etp_utc": "",
            "gcdist_from": None,
            "gcdist_to": None,
            "cfr_lbs": None,
            "cfr_time": "",
            "fob_lbs": None,
            "diff_lbs": None,
            "scenario": "",
        }

        j = i
        # 블록 끝: 빈 줄이거나 다른 큰 섹션 시작 전까지
        while j < len(lines) and lines[j].strip():
            l = lines[j].strip()
            u = l.upper()

            if u.startswith("ETP LOCATION"):
                # ETP LOCATION N51 58.2 E167 16.8 ETE 03.54
                loc_part = l[len("ETP LOCATION") :].strip()
                m_ete = re.search(r"ETE\s+(\d{2}\.\d{2})", loc_part)
                if m_ete:
                    ete_str_raw = m_ete.group(1)
                    ete_fmt, etp_utc = _ete_to_utc(ete_str_raw)
                    item["ete"] = ete_fmt
                    item["etp_utc"] = etp_utc
                    loc_part = loc_part[: m_ete.start()].strip()
                item["location"] = loc_part

            elif u.startswith("GWT AT DIVERSION"):
                # GWT AT DIVERSION 461763 FOB 076562
                m_fob = re.search(r"FOB\s+(\d+)", l)
                if m_fob:
                    item["fob_lbs"] = int(m_fob.group(1))

            elif u.startswith("DIVERSION AIRPORTS"):
                # DIVERSION AIRPORTS RJCC PAKN
                m_div = re.search(r"DIVERSION\s+AIRPORTS\s+([A-Z]{4})\s+([A-Z]{4})", u)
                if m_div:
                    item["from_apt"] = m_div.group(1)
                    item["to_apt"] = m_div.group(2)
                    item["pair"] = f"{item['from_apt']}/{item['to_apt']}"

            elif u.startswith("G/C DIST"):
                # G/C DIST 1172 1282  (from/to 순서)
                m_dist = re.search(r"G/C\s+DIST\s+(\d+)\s+(\d+)", u)
                if m_dist:
                    item["gcdist_from"] = int(m_dist.group(1))
                    item["gcdist_to"] = int(m_dist.group(2))

            elif u.startswith("CRITICAL FUEL REQUIRED"):
                # CRITICAL FUEL REQUIRED AT ETP01 - DECOMP 1 ENG TO PAKN
                m_scn = re.search(r"-\s*(.+)$", l)
                if m_scn:
                    item["scenario"] = m_scn.group(1).strip()

                # 다음 몇 줄에서 CFR/FOB/QTY DIFF. 추출
                k = j + 1
                while k < len(lines) and lines[k].strip():
                    l2 = lines[k].strip()
                    u2 = l2.upper()
                    if u2.startswith("CFR"):
                        # CFR 046193 03.39
                        m_cfr = re.search(r"CFR\s+(\d+)\s+(\d{2}\.\d{2})", l2)
                        if m_cfr:
                            item["cfr_lbs"] = int(m_cfr.group(1))
                            t = m_cfr.group(2)
                            item["cfr_time"] = f"{t[:2]}:{t[3:]}"
                    elif u2.startswith("FOB"):
                        m_fob2 = re.search(r"FOB\s+(\d+)", l2)
                        if m_fob2:
                            item["fob_lbs"] = int(m_fob2.group(1))
                    elif u2.startswith("QTY DIFF"):
                        m_diff = re.search(r"QTY\s+DIFF\.\s+(\d+)", l2.upper())
                        if m_diff:
                            item["diff_lbs"] = int(m_diff.group(1))
                    k += 1
                j = k - 1  # 내부 루프가 진행한 만큼 이동

            j += 1

        # 최소한 위치와 CFR/FOB 중 하나라도 있으면 결과에 추가
        if item["location"] or item["cfr_lbs"] is not None:
            out.append(item)

        i = j

    return out


def extract_refile_fuel_summaries(text: str) -> List[Dict[str, Any]]:
    """
    REFILE FLT PLAN 블록에서 Refile point 연료 요약을 추출한다.

    예시:
        REFILE FLT PLAN KAL041 16/FEB/26
        - RKSI TO PANC - 56N50 TO KSEA
        ...
        PLANNED R/F AT REFILE POINT 00436
        ...
        RQRD 0368 03.37
        ...
        VFR 0301 03.06
        ...
        FINAL RES 0050 00.30

    Returns (여러 REFILE 플랜이 있을 수 있으므로 리스트):
      [{
        "refile_dep": "RKSI",
        "refile_dest": "PANC",
        "original_dest": "KSEA",
        "ref_point": "56N50",
        "planned_rf_lbs": 43600,
        "required_ifr_lbs": 36800,
        "required_ifr_time": "03:37",
        "vfr_required_lbs": 32600,
        "vfr_base_lbs": 30100,
        "vfr_required_time": "03:06",
        "final_res_lbs": 5000,
        "if_margin_lbs": 6800,
        "vfr_margin_lbs": 11000,
        "status": "IFR_VFR_OK" / "VFR_ONLY" / "INSUFFICIENT",
      }, ...]
    """
    lines = text.splitlines()
    # PDF 표/레이아웃으로 "REFILE FLT PLAN"이 두 줄로 나뉘는 경우 보정 (항상 "REFILE FLT PLAN + 콜싸인 + 날짜" 형식)
    merged: List[str] = []
    skip_next = False
    for idx, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        upper = line.upper().strip()
        # 현재 줄 끝이 REFILE이고 다음 줄이 FLT PLAN / FLIGHT PLAN 으로 시작하면 한 줄로 합침
        if upper.endswith("REFILE") and idx + 1 < len(lines):
            next_upper = lines[idx + 1].upper().strip()
            if next_upper.startswith("FLT PLAN") or next_upper.startswith("FLIGHT PLAN"):
                merged.append((line.rstrip() + " " + lines[idx + 1].strip()).strip())
                skip_next = True
                continue
        merged.append(line)
    lines = merged

    out: List[Dict[str, Any]] = []
    seen_keys: set = set()

    # 헤더: 항상 "REFILE FLT PLAN" 뒤 콜싸인·날짜 (한 줄에 있거나 위에서 이미 합쳐진 상태)
    def _is_refile_header(l: str) -> bool:
        u = l.upper()
        return "REFILE FLT PLAN" in u or "REFILE FLIGHT PLAN" in u

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not _is_refile_header(line):
            i += 1
            continue

        # 헤더 바로 다음 줄에 "- RKSI TO LTFM - NEGEM TO LOWW" 형식 (한 줄 또는 두 줄로 나뉜 경우)
        refile_dep = ""
        refile_dest = ""
        ref_point = ""
        orig_dest = ""
        if i + 1 < n:
            hdr = lines[i + 1].strip()
            if i + 2 < n:
                second = lines[i + 2].strip()
                # 두 줄로 나뉜 경우 "LOWW TO ZBAA" / "- UPSUR TO RKSI" 또는 "- RKSI TO LTFM" / "NEGEM TO LOWW"
                if second and not second.startswith("-"):
                    sep = " - "
                else:
                    sep = " "
                hdr_merged = hdr + sep + second
            else:
                hdr_merged = hdr
            # 형식1: "- RKSI TO LTFM - NEGEM TO LOWW" 또는 "LOWW TO ZBAA - UPSUR TO RKSI" (앞에 - 없어도 됨)
            m_hdr = re.search(
                r"(?:-\s*)?([A-Z]{4})\s+TO\s+([A-Z]{4})\s*-\s*([0-9A-Z]{3,8})\s+TO\s+([A-Z]{4})",
                hdr_merged,
                re.IGNORECASE,
            )
            if m_hdr:
                refile_dep = m_hdr.group(1).upper()
                refile_dest = m_hdr.group(2).upper()
                ref_point = m_hdr.group(3).upper()
                orig_dest = m_hdr.group(4).upper()
            else:
                # 형식2: "- UPSUR TO RKSI" 만 있는 경우 (한 구간만 표기)
                m_single = re.search(
                    r"-\s*([0-9A-Z]{3,8})\s+TO\s+([A-Z]{4})",
                    hdr_merged,
                    re.IGNORECASE,
                )
                if m_single:
                    refile_dep = m_single.group(1).upper()
                    refile_dest = m_single.group(2).upper()
                else:
                    # 형식3: "LOWW TO ZBAA" 만 (앞에 - 없음)
                    m_two = re.search(
                        r"([A-Z]{4})\s+TO\s+([A-Z]{4})",
                        hdr_merged,
                        re.IGNORECASE,
                    )
                    if m_two:
                        refile_dep = m_two.group(1).upper()
                        refile_dest = m_two.group(2).upper()

        # 블록 끝: 다음 REFILE 헤더 또는 "CFP PLAN" 전까지
        j = i + 1
        block_lines: List[str] = []
        while j < n:
            l2 = lines[j]
            if _is_refile_header(l2) and j != i:
                break
            if l2.upper().startswith("CFP PLAN"):
                break
            block_lines.append(l2.strip())
            j += 1

        block = "\n".join(block_lines)

        # RQRD/VFR/FINAL RES는 "Refile Point TO 원래 목적지" 구간 값만 사용 (예: UPSUR TO RKSI)
        # 블록에 "LOWW TO ZBAA"와 "UPSUR TO RKSI" 두 구간이 있으면 첫 번째 구간의 RQRD가 아닌
        # Refile 구간( ref_point → orig_dest )의 RQRD/VFR를 써야 함.
        # 줄 시작의 구간 헤더( "- UPSUR TO RKSI" 또는 "UPSUR TO RKSI 0133 ..." )부터 사용 (헤더 한 줄 "LOWW TO ZBAA - UPSUR TO RKSI" 내 매칭 제외)
        segment_block = block
        if ref_point and orig_dest:
            seg_at_line_start = re.compile(
                r"\n\s*-?\s*" + re.escape(ref_point) + r"\s+TO\s+" + re.escape(orig_dest) + r"(?:\s+\d+|\s*$)",
                re.IGNORECASE,
            )
            m_seg = seg_at_line_start.search(block)
            if m_seg:
                segment_block = block[m_seg.start():].lstrip()

        def _fuel_val(raw: Optional[str]) -> Optional[int]:
            if not raw:
                return None
            raw = raw.strip()
            if not raw.isdigit():
                return None
            v = int(raw)
            return v * 100 if v < 10000 else v

        # Planned R/F at refile point (줄바꿈/공백 유연: POINT 뒤 숫자가 다음 줄에 있어도 매칭)
        planned_rf_lbs: Optional[int] = None
        m_planned = re.search(
            r"PLANNED\s+R/F\s+AT\s+REFILE\s+POINT\s*(\d+)", block, re.IGNORECASE | re.DOTALL
        )
        if m_planned:
            planned_rf_lbs = _fuel_val(m_planned.group(1))
        if not planned_rf_lbs:
            m_planned = re.search(r"REFILE\s+POINT\s*(\d{3,6})", block, re.IGNORECASE | re.DOTALL)
            if m_planned:
                planned_rf_lbs = _fuel_val(m_planned.group(1))
        if not planned_rf_lbs:
            # POINT 다음 줄에만 숫자 있는 경우 (예: "PLANNED R/F AT REFILE POINT" \n "00298")
            m_planned = re.search(
                r"REFILE\s+POINT\s*\n\s*(\d{3,6})", block, re.IGNORECASE
            )
            if m_planned:
                planned_rf_lbs = _fuel_val(m_planned.group(1))

        # IFR required: RQRD 0228 02.28 (Refile 구간만: segment_block 사용)
        required_ifr_lbs: Optional[int] = None
        required_ifr_time = ""
        m_rqrd = re.search(r"R[QO]RD\s+(\d+)\s+(\d{1,2}\.\d{2})", segment_block, re.IGNORECASE)
        if m_rqrd:
            required_ifr_lbs = _fuel_val(m_rqrd.group(1))
            t = m_rqrd.group(2)
            required_ifr_time = f"{t[:2]}:{t[3:]}"

        # VFR 0188 02.10 (Refile 구간만: segment_block 사용)
        vfr_base_lbs: Optional[int] = None
        vfr_required_time = ""
        m_vfr = re.search(r"\bVFR\s+(\d+)\s+(\d{2}\.\d{2})", segment_block, re.IGNORECASE)
        if m_vfr:
            vfr_base_lbs = _fuel_val(m_vfr.group(1))
            t = m_vfr.group(2)
            vfr_required_time = f"{t[:2]}:{t[3:]}"

        # FINAL RES (Refile 구간만: segment_block 사용)
        final_res_lbs: Optional[int] = None
        m_final = re.search(r"FINAL\s+RES\s+(\d+)\s+\d{2}\.\d{2}", segment_block, re.IGNORECASE)
        if m_final:
            final_res_lbs = _fuel_val(m_final.group(1))

        if not planned_rf_lbs:
            i = j
            continue

        # VFR 기준 필요 연료 = VFR base + FINAL RES 절반
        vfr_required_lbs: Optional[int] = None
        if vfr_base_lbs is not None:
            extra = (final_res_lbs or 0) // 2
            vfr_required_lbs = vfr_base_lbs + extra

        # 여유량 계산
        if_margin_lbs: Optional[int] = None
        if required_ifr_lbs is not None:
            if_margin_lbs = planned_rf_lbs - required_ifr_lbs
        vfr_margin_lbs: Optional[int] = None
        if vfr_required_lbs is not None:
            vfr_margin_lbs = planned_rf_lbs - vfr_required_lbs

        status = "UNKNOWN"
        if planned_rf_lbs is not None:
            if required_ifr_lbs is not None and if_margin_lbs is not None and if_margin_lbs >= 0:
                if vfr_required_lbs is not None and vfr_margin_lbs is not None and vfr_margin_lbs >= 0:
                    status = "IFR_VFR_OK"
                else:
                    status = "IFR_OK"
            elif vfr_required_lbs is not None and vfr_margin_lbs is not None and vfr_margin_lbs >= 0:
                status = "VFR_ONLY"
            else:
                status = "INSUFFICIENT"

        item = {
            "refile_dep": refile_dep,
            "refile_dest": refile_dest,
            "original_dest": orig_dest,
            "ref_point": ref_point,
            "planned_rf_lbs": planned_rf_lbs,
            "required_ifr_lbs": required_ifr_lbs,
            "required_ifr_time": required_ifr_time,
            "vfr_base_lbs": vfr_base_lbs,
            "vfr_required_lbs": vfr_required_lbs,
            "vfr_required_time": vfr_required_time,
            "final_res_lbs": final_res_lbs,
            "if_margin_lbs": if_margin_lbs,
            "vfr_margin_lbs": vfr_margin_lbs,
            "status": status,
        }

        # 동일한 REFILE 플랜이 OFP에 두 번 들어있는 경우(중복 블록) 중복 제거
        key = (
            item["refile_dep"],
            item["refile_dest"],
            item["original_dest"],
            item["ref_point"],
            item["planned_rf_lbs"],
            item["required_ifr_lbs"],
            item["vfr_required_lbs"],
        )
        if key not in seen_keys:
            seen_keys.add(key)
            out.append(item)

        i = j

    return out


def _extract_wind_temp_block(text: str) -> str:
    """
    OFP 전체 텍스트에서 'START OF WIND AND TEMPERATURE SUMMARY' 섹션만 잘라낸다.
    명시적인 END 태그가 없을 수 있으므로 다음 CFP PLAN 또는 FLIGHT RELEASE 이전까지만 사용.
    """
    m = re.search(r"START OF WIND AND TEMPERATURE SUMMARY", text, re.IGNORECASE)
    if not m:
        return ""
    start = m.start()
    # 끝 후보: 다음 CFP PLAN, FLIGHT RELEASE, 또는 START OF SIGNIFICANT WEATHER 등
    tail = text[start:]
    end_candidates = []
    for pat in [r"\nCFP PLAN\b", r"\nFLIGHT RELEASE\b", r"\nSTART OF SIGNIFICANT", r"\nEND OF WIND AND TEMPERATURE SUMMARY"]:
        em = re.search(pat, tail, re.IGNORECASE)
        if em:
            end_candidates.append(em.start())
    end = min(end_candidates) if end_candidates else len(tail)
    return tail[:end]


def _parse_wind_temp_grid(block: str) -> Dict[Tuple[str, int], Dict[str, float]]:
    """
    Wind/Temp Summary 블록을 (waypoint, FL) 그리드로 변환.
    키: (waypoint, flight_level)
    값: {"dir": deg, "spd": kt, "cmp": kt, "temp": degC}
    OFP: (1) 헤더 전 단일 컬럼 행은 다음 단일 WP 헤더(예: PILIT)에 귀속.
         (2) 데이터 행이 헤더 위에 오는 경우: pending 중 컬럼 수가 헤더 WP 수와 같은 행을 해당 헤더에 귀속.
         (3) 헤더 아래 행의 컬럼 수가 WP 수와 다르면 해당 행은 현재 블록에 붙이지 않고 pending으로.
    """
    grid: Dict[Tuple[str, int], Dict[str, float]] = {}
    if not block:
        return grid

    current_wps: List[str] = []
    pending_rows: List[Tuple[int, List[str]]] = []

    def _store_cell(wp: str, fl: int, tok: str) -> None:
        # 6자리(풍향3+풍속3) 예: 281103+090-49 → 281°, 103kt
        wm6 = re.match(r"^(\d{3})(\d{3})([+-]\d{3})([+-]\d{2})$", tok)
        if wm6:
            try:
                wdir = int(wm6.group(1))
                wspd = int(wm6.group(2))
                cmp_val = int(wm6.group(3))
                temp = int(wm6.group(4))
                grid[(wp, fl)] = {"dir": float(wdir), "spd": float(wspd), "cmp": float(cmp_val), "temp": float(temp)}
                return
            except ValueError:
                pass
        # 5자리(풍향2×10+풍속3) 예: 26092+068-52 → 260°, 92kt / 26101+100-51 → 260°, 101kt
        wm = re.match(r"^(\d{2})(\d{3})([+-]\d{3})([+-]\d{2})$", tok)
        if not wm:
            return
        try:
            wdir = int(wm.group(1)) * 10
            wspd = int(wm.group(2))
            cmp_val = int(wm.group(3))
            temp = int(wm.group(4))
        except ValueError:
            return
        grid[(wp, fl)] = {
            "dir": float(wdir),
            "spd": float(wspd),
            "cmp": float(cmp_val),
            "temp": float(temp),
        }

    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        u = line.upper()
        if u.startswith("START OF WIND") or u.startswith("FL ISA"):
            continue
        # PDF에서 추출된 페이지 표시 줄 무시 (데이터 행 사이에 끼어 있어 추출 방해)
        if re.match(r"^PAGE\s*(-\s*)?\d+(\s+OF\s+\d+)?\s*$", u):
            continue

        # 데이터 행이면 아래에서 처리 (FL ISA rest 형식)
        data_row_m = re.match(r"^\s*(\d{3})\s+(-?\d{2})\s+(.+)$", line)
        if data_row_m:
            fl = int(data_row_m.group(1))
            rest = data_row_m.group(3).split()
            if not rest:
                continue
            if not current_wps:
                pending_rows.append((fl, rest))
                continue
            if len(rest) != len(current_wps):
                pending_rows.append((fl, rest))
                current_wps = []
                continue
            for idx, tok in enumerate(rest):
                _store_cell(current_wps[idx], fl, tok)
            continue

        # 웨이포인트 헤더 행 (숫자 포함 WP명 허용, 예: 55N50)
        tokens = line.split()
        if tokens and all(re.match(r"^[A-Z0-9]+$", t) for t in tokens):
            n_wp = len(tokens)
            still_pending: List[Tuple[int, List[str]]] = []
            for fl, rest_tokens in pending_rows:
                if len(rest_tokens) == n_wp:
                    for idx, tok in enumerate(rest_tokens):
                        _store_cell(tokens[idx], fl, tok)
                else:
                    still_pending.append((fl, rest_tokens))
            pending_rows = still_pending
            current_wps = tokens
            if n_wp == 1:
                current_wps = []
        continue

    return grid


def build_wind_shear_inversion_table(text: str, cruise_fl: Optional[int] = None) -> List[Dict[str, str]]:
    """
    Wind/Temp Summary를 분석하여 운항 고도 주변의
    - 기온 역전 (Temperature Inversion)
    - 수직 wind shear
    가 큰 구간을 요약 테이블로 생성.

    Returns: [
      {
        "location": "OVSOS (FL330↔FL350)",
        "issue": "기온 역전 +4°C, 수직 wind shear ΔV 22kt, ΔDir 35°",
      },
      ...
    ]
    """
    block = _extract_wind_temp_block(text)
    grid = _parse_wind_temp_grid(block)
    if not grid:
        return []

    # 웨이포인트 목록과 사용된 FL 집합
    waypoints = sorted({wp for (wp, _fl) in grid.keys()})
    fl_set = sorted({fl for (_wp, fl) in grid.keys()})

    # 운항 FL 기준: second plan FL이 주어지면 그 주변 ±20을 우선
    if cruise_fl is None:
        cruise_fl = fl_set[len(fl_set) // 2] if fl_set else None
    focus_fls: List[int] = []
    if cruise_fl:
        for off in (-20, 0, 20):
            target = cruise_fl + off
            if target in fl_set and target not in focus_fls:
                focus_fls.append(target)
    if not focus_fls:
        focus_fls = fl_set

    def _dir_diff(a: float, b: float) -> float:
        d = abs(a - b) % 360.0
        return d if d <= 180.0 else 360.0 - d

    rows: List[Dict[str, str]] = []

    for wp in waypoints:
        # 해당 웨이포인트에서 사용 가능한 FL들
        wp_levels = sorted(fl for (w, fl) in grid.keys() if w == wp and fl in focus_fls)
        if len(wp_levels) < 2:
            continue

        for i in range(len(wp_levels) - 1):
            fl_low = wp_levels[i]
            fl_high = wp_levels[i + 1]
            d_low = grid[(wp, fl_low)]
            d_high = grid[(wp, fl_high)]

            t_low = d_low["temp"]
            t_high = d_high["temp"]
            temp_delta = t_high - t_low  # 위층 - 아래층

            # ΔV = 풍속(spd) 차이 (기상 wind shear)
            spd_delta = abs(d_high["spd"] - d_low["spd"])
            dir_delta = _dir_diff(d_low["dir"], d_high["dir"])

            issues: List[str] = []

            # 기온 역전: 위가 더 따뜻하거나, 감소 폭이 거의 없는 경우
            if temp_delta > 0:
                issues.append(f"기온 역전 +{int(temp_delta)}°C")
            elif temp_delta > -2:
                issues.append(f"약한 역전/온도 정체 (ΔT {int(temp_delta)}°C)")

            # 수직 wind shear: 풍속 또는 방향 변화가 큰 경우
            if spd_delta >= 20 or dir_delta >= 30:
                issues.append(f"수직 wind shear ΔV {int(spd_delta)}kt, ΔDir {int(dir_delta)}°")

            if not issues:
                continue

            rows.append({
                "location": f"{wp} (FL{fl_low}↔FL{fl_high})",
                "issue": "; ".join(issues),
            })

    return rows


def build_wind_shear_inversion_table_for_route(
    text: str,
    legs: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """
    Flight Plan 테이블에서 추출한 실제 운항 구간(waypoint + FL)을 기준으로
    Wind/Temp Summary를 분석하여:
    - 기온 역전 / 수직 wind shear (같은 WP, 인접 FL)
    - 수평 wind shear (연속 WP 간 같은 FL에서 풍속·풍향·진로성분 변화)
    를 요약한다. 기준: ΔV≥20kt 또는 ΔDir≥30° 또는 ΔCMP≥20kt 중 하나라도 충족 시 표시.

    legs: extract_flight_data_from_pdf() 의 반환 리스트 일부
          (각 원소에 'Waypoint', 'FL (Flight Level)' 키가 포함되어 있어야 함)
    """
    block = _extract_wind_temp_block(text)
    grid = _parse_wind_temp_grid(block)
    if not block or not grid or not legs:
        return []

    # 웨이포인트별 사용 가능한 FL 목록 캐시
    wp_levels_map: Dict[str, List[int]] = {}
    for (wp, fl) in grid.keys():
        wp_levels_map.setdefault(wp, []).append(fl)
    for wp in wp_levels_map:
        wp_levels_map[wp] = sorted(wp_levels_map[wp])

    def _dir_diff(a: float, b: float) -> float:
        d = abs(a - b) % 360.0
        return d if d <= 180.0 else 360.0 - d

    seen_vertical: set = set()
    seen_horizontal: set = set()
    # 수직 shear 행을 먼저 리스트로 모은 뒤, 연속 waypoint 구간별로 묶어서 rows에 반영
    vertical_raw: List[Dict[str, Any]] = []

    # Waypoint별 ACTM (이륙 후 누적 시간, 예: "01.28") 매핑
    wp_actm_map: Dict[str, str] = {}
    for leg in legs:
        wp = (leg.get("Waypoint") or "").strip()
        actm = (leg.get("ACTM (Accumulated Time)") or "").strip()
        if wp and actm:
            # 동일 waypoint가 여러 번 나와도 가장 마지막 값으로 덮어씀
            wp_actm_map[wp] = actm

    # Route 순서: legs에서 (Waypoint, FL) 리스트 추출
    route: List[Tuple[str, int]] = []
    for leg in legs:
        wp = (leg.get("Waypoint") or "").strip()
        fl_str = (leg.get("FL (Flight Level)") or "").strip()
        if not wp or not fl_str.isdigit():
            continue
        route.append((wp, int(fl_str)))

    # ----- 수직 shear / 기온 역전 (기존 로직) -----
    for leg in legs:
        wp = (leg.get("Waypoint") or "").strip()
        fl_str = (leg.get("FL (Flight Level)") or "").strip()
        if not wp or not fl_str.isdigit():
            continue
        leg_fl = int(fl_str)

        levels = wp_levels_map.get(wp)
        if not levels or len(levels) < 2:
            continue

        fl_low = levels[0]
        fl_high = levels[1]
        for idx, lv in enumerate(levels):
            if lv <= leg_fl:
                fl_low = lv
            if lv >= leg_fl:
                fl_high = lv
                if idx > 0:
                    fl_low = levels[idx - 1]
                break
        else:
            fl_low, fl_high = levels[-2], levels[-1]

        key = (wp, fl_low, fl_high)
        if key in seen_vertical:
            continue
        seen_vertical.add(key)

        d_low = grid.get((wp, fl_low))
        d_high = grid.get((wp, fl_high))
        if not d_low or not d_high:
            continue

        t_low = d_low["temp"]
        t_high = d_high["temp"]
        temp_delta = t_high - t_low

        # ΔV = 풍속(spd) 차이 (기상 wind shear)
        spd_delta = abs(d_high["spd"] - d_low["spd"])
        dir_delta = _dir_diff(d_low["dir"], d_high["dir"])

        issues: List[str] = []
        if temp_delta > 0:
            issues.append(f"기온 역전 +{int(temp_delta)}°C")
        elif temp_delta > -2:
            issues.append(f"약한 역전/온도 정체 (ΔT {int(temp_delta)}°C)")
        if spd_delta >= 20 or dir_delta >= 30:
            issues.append(f"수직 wind shear ΔV {int(spd_delta)}kt, ΔDir {int(dir_delta)}°")

        if not issues:
            continue

        actm = wp_actm_map.get(wp, "")
        vertical_raw.append({
            "wp": wp,
            "leg_fl": leg_fl,
            "fl_low": fl_low,
            "fl_high": fl_high,
            "location": f"{wp} (운항 FL{leg_fl}, 분석 FL{fl_low}↔FL{fl_high})",
            "issue": "; ".join(issues),
            "actm": actm,
        })

    # ----- 연속 waypoint 구간 묶기: route 순서대로 WP_first ~ WP_last 한 행으로 -----
    route_wp_order = [wp for wp, _ in route]
    # route 순서대로 vertical_raw에 등장하는 waypoint만 나열 (중복 제거, 순서 유지)
    seen_wp: set = set()
    ordered_vertical_wps: List[str] = []
    for w in route_wp_order:
        if w in seen_wp:
            continue
        if any(v["wp"] == w for v in vertical_raw):
            seen_wp.add(w)
            ordered_vertical_wps.append(w)
    # route에서 연속된 waypoint끼리 그룹화
    groups: List[List[str]] = []
    i = 0
    while i < len(ordered_vertical_wps):
        seg = [ordered_vertical_wps[i]]
        j = i + 1
        while j < len(ordered_vertical_wps):
            prev_idx = route_wp_order.index(ordered_vertical_wps[j - 1])
            cur_idx = route_wp_order.index(ordered_vertical_wps[j])
            if cur_idx == prev_idx + 1:
                seg.append(ordered_vertical_wps[j])
                j += 1
            else:
                break
        groups.append(seg)
        i = j

    rows: List[Dict[str, str]] = []
    for seg in groups:
        if not seg:
            continue
        first_wp, last_wp = seg[0], seg[-1]
        seg_set = set(seg)
        seg_raws = [v for v in vertical_raw if v["wp"] in seg_set]
        leg_fls = [v["leg_fl"] for v in seg_raws]
        fl_lows = [v["fl_low"] for v in seg_raws]
        fl_highs = [v["fl_high"] for v in seg_raws]
        issues_seen: List[str] = []
        for v in seg_raws:
            if v["issue"] not in issues_seen:
                issues_seen.append(v["issue"])
        actm_first = wp_actm_map.get(first_wp, "")
        actm_last = wp_actm_map.get(last_wp, "")
        actm_str = f"{actm_first}~{actm_last}" if (actm_first and actm_last and actm_first != actm_last) else (actm_last or actm_first)
        fl_range = f"FL{min(leg_fls)}~FL{max(leg_fls)}" if min(leg_fls) != max(leg_fls) else f"FL{leg_fls[0]}"
        if first_wp != last_wp:
            loc = f"{first_wp} ~ {last_wp} (운항 {fl_range}, 분석 FL{min(fl_lows)}↔FL{max(fl_highs)})"
        else:
            loc = next((v["location"] for v in seg_raws if v["wp"] == first_wp), seg_raws[0]["location"])
        issue_str = "; ".join(issues_seen) if len(issues_seen) <= 2 else (issues_seen[0] + f" 등 ({len(seg)}개 WP)")
        rows.append({"location": loc, "issue": issue_str, "actm": actm_str})

    # ----- 수평 shear: 연속 waypoint 쌍, 동일 FL에서 ΔV/ΔDir -----
    for i in range(len(route) - 1):
        wp1, fl1 = route[i]
        wp2, fl2 = route[i + 1]
        # 비교 FL: 도착점(wp2)의 운항고도. 두 WP 모두 해당 FL 데이터가 있을 때만 비교
        common_fl = fl2
        d1 = grid.get((wp1, common_fl))
        d2 = grid.get((wp2, common_fl))
        if not d1 or not d2:
            continue

        key_h = (wp1, wp2, common_fl)
        if key_h in seen_horizontal:
            continue
        seen_horizontal.add(key_h)

        # 수평 shear 세 가지 원인: 풍속 변화(ΔV), 풍향 변화(ΔDir), 진로 기준 성분 변화(ΔCMP)
        spd_delta = abs(d2["spd"] - d1["spd"])
        dir_delta = _dir_diff(d1["dir"], d2["dir"])
        cmp_delta = abs(d2.get("cmp", 0.0) - d1.get("cmp", 0.0))
        # 하나라도 임계 초과 시 수평 shear로 표시 (ΔV≥20kt or ΔDir≥30° or ΔCMP≥20kt)
        if spd_delta < 20 and dir_delta < 30 and cmp_delta < 20:
            continue

        actm1 = wp_actm_map.get(wp1)
        actm2 = wp_actm_map.get(wp2)
        if actm1 and actm2 and actm1 != actm2:
            actm = f"{actm1}~{actm2}"
        else:
            actm = actm2 or actm1 or ""

        rows.append({
            "location": f"{wp1} → {wp2} (운항 FL{common_fl})",
            "issue": f"수평 wind shear ΔV {int(spd_delta)}kt, ΔDir {int(dir_delta)}°, ΔCMP {int(cmp_delta)}kt",
            "actm": actm,
        })

    return rows
