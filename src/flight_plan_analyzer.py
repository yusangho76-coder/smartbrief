"""
OFP(Operational Flight Plan) 텍스트에서 비행계획 요약 항목 추출.
비행분석에 표시할 Callsign, PAX, MEL/CDL, 연료, 중량, ETD/ETA 등 정리.
OFP 구조: 번호 붙은 섹션(3. MEL, 4. ..., 5. DISPATCH NOTES 등)과 헤더 블록 활용.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

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

    # 789: A/C 타입 (숫자 3자리)
    out["aircraft_type"] = _first_in_block(header, r"\b(789|788|77W|77F|333|359|321|320|319)\b", 1)
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
        disp_lines = []
        turb_cb_lines = []
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

    # ----- 9. 평균 WIND/TEMP: M058/M51 (minus 58 kts / minus 51°C) -----
    # 데이터는 "AVG WIND/TEMP" 헤더 다음 줄에 있음: "789 HL7208 ... M058/M51 100LBS"
    lines_arr = t.splitlines()
    for i, line in enumerate(lines_arr):
        m = re.search(r"M(\d{3})(?:/M(\d{2,3}))?", line)
        if not m:
            continue
        w, temp = m.group(1), m.group(2)
        val = "M" + w + (("/M" + temp) if temp else "")
        # 현재 줄이 헤더이거나, 바로 이전 줄이 AVG WIND/TEMP 또는 PROGS 포함
        prev_ok = i > 0 and (
            "AVG WIND" in lines_arr[i - 1].upper()
            or "WIND/TEMP" in lines_arr[i - 1].upper()
            or "PROGS" in lines_arr[i - 1].upper()
        )
        if "AVG WIND" in line.upper() or "WIND/TEMP" in line.upper() or "PROGS" in line.upper() or prev_ok:
            out["avg_wind_temp"] = val
            break
    if not out.get("avg_wind_temp"):
        m = re.search(r"M(\d{3})(?:/M(\d{2,3}))?", header)
        if m:
            out["avg_wind_temp"] = "M" + m.group(1) + (("/M" + m.group(2)) if m.group(2) else "")

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
        if key == "ccf_disc_fuel" and label == "DISC":
            ccf = (summary.get("disc_ccf_lbs") or "").strip()
            due_to = (summary.get("disc_due_to") or "").strip()
            if ccf and due_to:
                label = f"DISC(CCF {ccf} + {due_to})"
            elif ccf:
                label = f"DISC(CCF {ccf})"
            elif due_to:
                label = f"DISC({due_to})"
        fuel, time = _parse_fuel_time_value(val)
        indent = key in {"final_res", "pct_cont", "refile_res", "etp_res"}
        rows.append({"label": label, "fuel": fuel, "time": time, "indent": indent})
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

    # ALTN: "ALTERNATE - 1 KPDX" 또는 "ALTN/KPDX"
    for m in re.finditer(r"ALTERNATE\s*-?\s*\d?\s+([A-Z]{4})", text, re.IGNORECASE):
        code = m.group(1)
        if code not in out["altn"]:
            out["altn"].append(code)
    for m in re.finditer(r"ALTN/([A-Z]{4})", text):
        code = m.group(1)
        if code not in out["altn"]:
            out["altn"].append(code)

    # REFILE: "REFILE FLT PLAN ... \n- RKSI TO PANC - 56N50 TO KSEA"
    for m in re.finditer(
        r"REFILE\s+FLT\s+PLAN\b[^\n]*\n\s*-\s*[A-Z]{4}\s+TO\s+([A-Z]{4})\s*-\s*(\S+)\s+TO",
        text, re.IGNORECASE
    ):
        refile_apt = m.group(1)
        decision_pt = m.group(2)
        if not any(r["airport"] == refile_apt for r in out["refile"]):
            out["refile"].append({"airport": refile_apt, "decision_point": decision_pt})

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

    # Package 2 header: "REFILE: PANC PAED" / "EDTO: RJCC PAKN" / "ERA: RJTT RJCC ..."
    pkg2_refile = re.search(r"^REFILE:\s*(.+)$", text, re.MULTILINE)
    if pkg2_refile:
        for code in re.findall(r"[A-Z]{4}", pkg2_refile.group(1)):
            if not any(r["airport"] == code for r in out["refile"]):
                out["refile"].append({"airport": code, "decision_point": ""})
    pkg2_edto = re.search(r"^EDTO:\s*(.+)$", text, re.MULTILINE)
    if pkg2_edto:
        for code in re.findall(r"[A-Z]{4}", pkg2_edto.group(1)):
            if code not in out["edto_enroute"]:
                out["edto_enroute"].append(code)
    pkg2_era = re.search(r"^ERA:\s*(.+)$", text, re.MULTILINE)
    if pkg2_era:
        for code in re.findall(r"[A-Z]{4}", pkg2_era.group(1)):
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


def _fetch_taf_from_api(icao_list: List[str], timeout: int = 10) -> Dict[str, Optional[Dict]]:
    """
    Aviation Weather Center API에서 여러 공항의 TAF를 한 번에 가져온다.
    Returns: {"RKSI": {rawTAF: "...", fcsts: [...]}, "KSEA": {...}, ...}
    실패한 공항은 None으로 반환.
    """
    try:
        import requests as _requests
    except ImportError:
        return {code: None for code in icao_list}

    if not icao_list:
        return {}

    result: Dict[str, Optional[Dict]] = {code: None for code in icao_list}
    ids_param = ",".join(icao_list)
    url = f"https://aviationweather.gov/api/data/taf?ids={ids_param}&format=json"
    try:
        resp = _requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    icao = (item.get("icaoId") or "").upper()
                    if icao in result:
                        result[icao] = item
    except Exception:
        pass
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


def build_airport_weather_table(text: str) -> List[Dict[str, str]]:
    """
    OFP 전체 텍스트에서 DEP/DEST/ALTN/REFILE/EDTO 공항별 TAF를
    Aviation Weather Center API(aviationweather.gov)에서 실시간으로 가져와
    분석 테이블을 생성.
    Returns: [
        {"time_utc": "07:10Z", "location": "RKSI (이륙)", "actm": "DEP", "content": "TAF ..."},
        ...
    ]
    """
    airports = extract_all_airports_from_text(text)
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
    for code in airports.get("edto_enroute", []) + airports.get("era", []):
        if code and code not in seen_collect:
            all_icao.append(code)
            seen_collect.add(code)

    # Aviation Weather API 일괄 호출
    taf_map = _fetch_taf_from_api(all_icao)

    rows: List[Dict[str, str]] = []

    def _build_content(icao: str, ofp_fallback: str, label_type: str) -> str:
        """API TAF 요약 + Ceiling/RVR 체크. 없으면 OFP 내 TAF 폴백."""
        taf_item = taf_map.get(icao)
        if taf_item:
            summary = _summarize_taf_from_api(taf_item, icao)
            raw = _taf_raw(taf_item)
        else:
            # API 실패 시 OFP 내 TAF 사용
            summary = _summarize_taf_line(ofp_fallback) if ofp_fallback else f"{icao}: TAF 없음"
            raw = ofp_fallback or ""

        is_edto_era = label_type in ("EDTO", "ERA", "REFILE")
        if is_edto_era:
            # EDTO/ERA: ceiling 200ft / RVR 550m 체크
            warn = _check_edto_ceiling_rvr_from_api(taf_item) if taf_item else _check_edto_ceiling_rvr(raw)
            if warn:
                return f"{summary} ⚠️ EDTO 기준 미달: {warn}"
            else:
                return f"{summary} ✅ Ceiling/RVR 기준 충족."
        else:
            if "CAVOK" in summary.upper() or "P6SM" in summary.upper() or "SKC" in summary.upper():
                return f"{summary} ✅ 기상 양호."
            return summary

    # DEP
    if dep:
        rows.append({
            "time_utc": etd_str,
            "location": f"{dep} (이륙)",
            "actm": "DEP",
            "content": _build_content(dep, ofp_taf.get("dep_taf", ""), "DEP")
        })

    # DEST
    if dest:
        rows.append({
            "time_utc": eta_str,
            "location": f"{dest} (도착)",
            "actm": "ETA",
            "content": _build_content(dest, ofp_taf.get("arr_taf", ""), "DEST")
        })

    # ALTN
    for altn_code in airports.get("altn", []):
        rows.append({
            "time_utc": eta_str,
            "location": f"{altn_code} (교체)",
            "actm": "ETA",
            "content": _build_content(altn_code, ofp_taf.get("altn_taf", ""), "ALTN")
        })

    # REFILE
    for rf in airports.get("refile", []):
        rf_apt = rf["airport"]
        dp = rf.get("decision_point", "")
        dp_label = f" (결심점: {dp})" if dp else ""
        rows.append({
            "time_utc": "—",
            "location": f"{rf_apt} (REFILE){dp_label}",
            "actm": "REFILE",
            "content": _build_content(rf_apt, "", "REFILE")
        })

    # EDTO Entry/Exit
    seen_edto: set = set()
    for ee in airports.get("edto_entry_exit", []):
        apt = ee["airport"]
        etype = ee["type"]
        if apt in seen_edto:
            continue
        seen_edto.add(apt)
        rows.append({
            "time_utc": "—",
            "location": f"{apt} (EDTO {etype})",
            "actm": "EDTO",
            "content": _build_content(apt, "", "EDTO")
        })

    # EDTO ENROUTE ALTERNATES
    for enrt in airports.get("edto_enroute", []):
        if enrt in seen_edto:
            continue
        seen_edto.add(enrt)
        suit_m = re.search(rf"{enrt}\s+SUITABLE\s+FROM\s+(\d{{4}})\s+UTC\s*/\s*TO\s+(\d{{4}})\s+UTC", text, re.IGNORECASE)
        suit_label = f" (적합: {suit_m.group(1)}~{suit_m.group(2)}Z)" if suit_m else ""
        rows.append({
            "time_utc": "—",
            "location": f"{enrt} (EDTO Enroute){suit_label}",
            "actm": "EDTO",
            "content": _build_content(enrt, "", "EDTO")
        })

    # ERA (EDTO에 없는 공항만)
    for era_apt in airports.get("era", []):
        if era_apt in seen_edto:
            continue
        seen_edto.add(era_apt)
        rows.append({
            "time_utc": "—",
            "location": f"{era_apt} (ERA)",
            "actm": "ERA",
            "content": _build_content(era_apt, "", "ERA")
        })

    return rows


def _find_taf_for_airport(text: str, icao: str) -> Optional[str]:
    """텍스트 전체에서 특정 공항의 TAF 줄을 찾아 반환 (폴백용)."""
    for m in re.finditer(rf"TAF\s+(?:AMD\s+)?{icao}\b[^\n]*", text, re.IGNORECASE):
        line = m.group(0).strip()
        start = m.end()
        extra_lines = []
        for next_line in text[start:start + 500].split("\n")[1:6]:
            nl = next_line.strip()
            if not nl or nl.startswith("---") or nl.startswith("===") or nl.startswith("ARRIVAL") or nl.startswith("ALTERNATE") or nl.startswith("DEPARTURE"):
                break
            if re.match(r"^(FM|TEMPO|BECMG|PROB|RMK)", nl) or re.match(r"^\d{6}Z", nl):
                extra_lines.append(nl)
            else:
                break
        return line + ("\n" + "\n".join(extra_lines) if extra_lines else "")
    return None
