#!/usr/bin/env python3
"""OFP 테이블 텍스트로부터 waypoint 추출 검증"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flightplanextractor import extract_flight_plan_waypoints_from_text

# 사용자가 제공한 OFP 테이블 텍스트 (일부)
OFP_SAMPLE = r"""DIST LATITUDE MC FL ETO/MSA R/F OT WIND/COMP SR TAS ZT B/O
TO LONGITUDE MH ACT ATO/DF ACTL MW GS ACTM ACBO/
TC
0058 N37 24.2 274 CLB ---/041 0981 40 ......... .. ... 011 058
NOPIK E125 39.1 273 / .. ... 00.11 0058/
265 NOPIK
0017 N37 24.0 278 300 ---/028 0965 49 ......... .. ... 003 016
TOC E125 18.0 276 / .. ... 00.14 0074/
269 TOC
0003 N37 23.8 278 300 ---/028 0965 49 26063M062 02 477 000 000
BINIL E125 14.0 276 / 34 415 00.14 0074/
269 BINIL
0019 N37 23.4 278 320 ---/028 0957 53 26066M065 01 482 003 008
ANSIM E124 50.2 277 / 34 417 00.17 0082/
269 ANSIM
Page - 1 of 9
Page 2
0020 N37 22.8 277 320 ---/025 0951 53 26066M066 02 482 003 006
NOGON E124 25.1 276 / 34 416 00.20 0088/
268 NOGON
0016 N37 14.2 247 320 ---/025 0946 53 26066M061 02 481 002 005
OLBIM E124 07.9 250 / 34 420 00.22 0093/
238 OLBIM
0008 N37 10.0 245 320 ---/025 0944 53 26065M058 02 480 001 002
AGAVO E124 00.0 249 / 34 422 00.23 0095/
/ ZSHA FIR 236 SHANGHAI AGAVO
0037 N36 49.9 246 341 ---/025 0932 55 27069M062 02 485 006 012
IKEKA E123 21.3 250 / 34 423 00.29 0107/
237 IKEKA
0052 N37 04.6 295 341 ---/032 0918 55 27069M066 02 486 007 014
SEBLI E122 19.5 293 / 34 420 00.36 0121/
287 SEBLI
0008 N37 11.1 332 360 ---/032 0915 55 27071M046 02 494 001 003
WEH E122 13.5 326 / 34 448 00.37 0124/
324 WEIHAI
0109 N28 34.1 291 DSC ------- 0198 16 29015M015 .. ... 023 015
VIDP E077 06.7 287 / .. .. 07.32 0841/
292 INDIRA GANDHI INTL"""

def main():
    waypoints = extract_flight_plan_waypoints_from_text(OFP_SAMPLE)
    print(f"추출된 waypoint 수: {len(waypoints)}")
    print()
    for i, w in enumerate(waypoints):
        print(f"{i+1:3} {w['Waypoint']:8}  lat={w['lat']:.6f}  lon={w['lon']:.6f}")
    # 기대: NOPIK, TOC, BINIL, ANSIM, NOGON, OLBIM, AGAVO, IKEKA, SEBLI, WEH, VIDP 등
    expected = ["NOPIK", "TOC", "BINIL", "ANSIM", "NOGON", "OLBIM", "AGAVO", "IKEKA", "SEBLI", "WEH", "VIDP"]
    got = [w["Waypoint"] for w in waypoints]
    missing = [e for e in expected if e not in got]
    if missing:
        print(f"\n누락된 waypoint: {missing}")
    else:
        print(f"\n기대한 주요 waypoint 모두 추출됨.")

if __name__ == "__main__":
    main()
