"""
Flight Information Region (FIR) Reference Database
Based on ICAO FIR list with FIR codes and names
"""

FIR_DATABASE = {
    # Pacific/Australia
    'PGZU': {'name': 'GUAM FIR', 'country': 'US', 'acc': 'Guam ACC'},
    'AYPM': {'name': 'PORT MORESBY FIR', 'country': 'PG', 'acc': 'Port Moresby ACC'},
    'YBBB': {'name': 'BRISBANE FIR', 'country': 'Australia', 'acc': 'Brisbane ACC'},
    'YMMM': {'name': 'MELBOURNE FIR', 'country': 'Australia', 'acc': 'Melbourne ACC'},
    'NFFF': {'name': 'FIJI FIR', 'country': 'Fiji/Kiribati/Vanuatu', 'acc': 'Nadi ACC'},
    'NTTT': {'name': 'TAHITI FIR', 'country': 'French Polynesia', 'acc': 'Tahiti ACC'},
    'NZZC': {'name': 'NEW ZEALAND FIR', 'country': 'New Zealand', 'acc': 'Christchurch ACC'},
    'NZZO': {'name': 'AUCKLAND OCEANIC FIR', 'country': 'New Zealand', 'acc': 'Auckland OAC'},
    
    # Asia/Korea
    'RKRR': {'name': 'INCHEON FIR', 'country': 'South Korea', 'acc': 'Incheon ACC'},
    'RJJJ': {'name': 'FUKUOKA FIR', 'country': 'Japan', 'acc': 'Air Traffic Management Center'},
    'RJFF': {'name': 'FUKUOKA FIR', 'country': 'Japan', 'acc': 'Fukuoka ACC'},
    'RJCG': {'name': 'FUKUOKA FIR', 'country': 'Japan', 'acc': 'Sapporo ACC'},
    'RJBE': {'name': 'FUKUOKA FIR', 'country': 'Japan', 'acc': 'Kobe ACC'},
    'RJTG': {'name': 'FUKUOKA FIR', 'country': 'Japan', 'acc': 'Tokyo ACC'},
    'RPHI': {'name': 'MANILA FIR', 'country': 'Philippines', 'acc': 'Manila ACC'},
    
    # USA/Oceanic
    'KZAK': {'name': 'OAKLAND OCEANIC FIR', 'country': 'Micronesia/Marshall Islands/Palau/US', 'acc': 'Oakland ARTCC', 'type': 'Oceanic'},
    'KZAB': {'name': 'ALBUQUERQUE FIR', 'country': 'US', 'acc': 'Albuquerque ARTCC'},
    'KZAU': {'name': 'CHICAGO FIR', 'country': 'US', 'acc': 'Chicago ARTCC'},
    'KZBW': {'name': 'BOSTON FIR', 'country': 'US', 'acc': 'Boston ARTCC'},
    'KZDC': {'name': 'WASHINGTON FIR', 'country': 'US', 'acc': 'Washington ARTCC'},
    'KZDV': {'name': 'DENVER FIR', 'country': 'US', 'acc': 'Denver ARTCC'},
    'KZFW': {'name': 'FORT WORTH FIR', 'country': 'US', 'acc': 'Fort Worth ARTCC'},
    'KZHU': {'name': 'HOUSTON FIR', 'country': 'US', 'acc': 'Houston ARTCC'},
    'KZID': {'name': 'INDIANAPOLIS FIR', 'country': 'US', 'acc': 'Indianapolis ARTCC'},
    'KZJX': {'name': 'JACKSONVILLE FIR', 'country': 'US', 'acc': 'Jacksonville ARTCC'},
    'KZKC': {'name': 'KANSAS CITY FIR', 'country': 'US', 'acc': 'Kansas City ARTCC'},
    'KZLA': {'name': 'LOS ANGELES FIR', 'country': 'US', 'acc': 'Los Angeles ARTCC'},
    'KZLC': {'name': 'SALT LAKE FIR', 'country': 'US', 'acc': 'Salt Lake ARTCC'},
    'KZMA': {'name': 'MIAMI FIR', 'country': 'US', 'acc': 'Miami ARTCC'},
    'KZME': {'name': 'MEMPHIS FIR', 'country': 'US', 'acc': 'Memphis ARTCC'},
    'KZMP': {'name': 'MINNEAPOLIS FIR', 'country': 'US', 'acc': 'Minneapolis ARTCC'},
    'KZNY': {'name': 'NEW YORK FIR', 'country': 'US', 'acc': 'New York ARTCC'},
    'KZOA': {'name': 'OAKLAND FIR', 'country': 'US', 'acc': 'Oakland ARTCC'},
    'KZOB': {'name': 'CLEVELAND FIR', 'country': 'US', 'acc': 'Cleveland ARTCC'},
    'KZSE': {'name': 'SEATTLE FIR', 'country': 'US', 'acc': 'Seattle ARTCC'},
    'KZTL': {'name': 'ATLANTA FIR', 'country': 'US', 'acc': 'Atlanta ARTCC'},
    'KZWY': {'name': 'NEW YORK OCEANIC FIR', 'country': 'US', 'acc': 'New York ARTCC', 'type': 'Oceanic'},
    'PAZA': {'name': 'ANCHORAGE CONTINENTAL FIR', 'country': 'US', 'acc': 'Anchorage ARTCC'},
    'PAZN': {'name': 'ANCHORAGE OCEANIC FIR', 'country': 'US', 'acc': 'Anchorage ARTCC', 'type': 'Oceanic'},
    'PHZH': {'name': 'HONOLULU FIR', 'country': 'US', 'acc': 'Honolulu ACC'},
    
    # China
    'ZBPE': {'name': 'BEIJING FIR', 'country': 'China', 'acc': 'Beijing ACC'},
    'ZGZU': {'name': 'GUANGZHOU FIR', 'country': 'China', 'acc': 'Guangzhou ACC'},
    'ZHWH': {'name': 'WUHAN FIR', 'country': 'China', 'acc': 'Wuhan ACC'},
    'ZJSA': {'name': 'SANYA FIR', 'country': 'China', 'acc': 'Sanya ACC'},
    'ZKKP': {'name': 'PYONGYANG FIR', 'country': 'North Korea', 'acc': 'Pyongyang ACC'},
    'ZLHW': {'name': 'LANZHOU FIR', 'country': 'China', 'acc': 'Lanzhou ACC'},
    'ZMUB': {'name': 'ULAANBAATAR FIR', 'country': 'Mongolia', 'acc': 'Ulan Bator ACC'},
    'ZPKM': {'name': 'KUNMING FIR', 'country': 'China', 'acc': 'Kunming ACC'},
    'ZSHA': {'name': 'SHANGHAI FIR', 'country': 'China', 'acc': 'Shanghai ACC'},
    'ZWUQ': {'name': 'URUMQI FIR', 'country': 'China', 'acc': 'Urumqi ACC'},
    'ZYSH': {'name': 'SHENYANG FIR', 'country': 'China', 'acc': 'Shenyang ACC'},
    
    # Russia/CIS
    'UAAA': {'name': 'ALMATY FIR', 'country': 'Kazakhstan', 'acc': 'Almaty ACC'},
    'UACN': {'name': 'ASTANA FIR', 'country': 'Kazakhstan', 'acc': 'Astana ACC'},
    'UAII': {'name': 'SHYMKENT FIR', 'country': 'Kazakhstan', 'acc': 'Shymkent ACC'},
    'UATT': {'name': 'AKTOBE FIR', 'country': 'Kazakhstan', 'acc': 'Aktobe ACC'},
    'UBBA': {'name': 'BAKU FIR', 'country': 'Azerbaijan', 'acc': 'Baku ACC'},
    'UCFM': {'name': 'BISHKEK FIR', 'country': 'Kyrgyzstan', 'acc': 'Bishkek ACC'},
    'UCFO': {'name': 'OSH FIR', 'country': 'Kyrgyzstan', 'acc': 'Osh ACC'},
    'UDDD': {'name': 'YEREVAN FIR', 'country': 'Armenia', 'acc': 'Yerevan ACC'},
    'UEEE': {'name': 'YAKUTSK FIR', 'country': 'Russia', 'acc': 'Yakutsk ACC'},
    'UGGG': {'name': 'TBILISI FIR', 'country': 'Georgia', 'acc': 'Tbilisi ACC'},
    'UHHH': {'name': 'KHABAROVSK FIR', 'country': 'Russia', 'acc': 'Khabarovsk ACC'},
    'UHMM': {'name': 'MAGADAN FIR', 'country': 'Russia', 'acc': 'Magadan ACC', 'type': 'Oceanic'},
    'UHPP': {'name': 'PETROPAVLOVSK FIR', 'country': 'Russia', 'acc': 'Petropavlovsk-Kamchatsky ACC'},
    'UIII': {'name': 'IRKUTSK FIR', 'country': 'Russia', 'acc': 'Irkutsk ACC'},
    'UKBV': {'name': 'KYIV FIR', 'country': 'Ukraine', 'acc': 'Kyiv ACC'},
    'UKDV': {'name': 'DNIPRO FIR', 'country': 'Ukraine', 'acc': 'Dnipro ACC'},
    'UKFV': {'name': 'SIMFEROPOL FIR', 'country': 'Ukraine', 'acc': 'Simferopol ACC'},
    'UKLV': {'name': 'LVIV FIR', 'country': 'Ukraine', 'acc': 'Lviv ACC'},
    'UKOV': {'name': 'ODESA FIR', 'country': 'Ukraine', 'acc': 'Odesa ACC'},
    'ULLL': {'name': 'SANKT PETERBURG FIR', 'country': 'Russia', 'acc': 'Sankt-Peterburg ACC'},
    'UMKK': {'name': 'KALININGRAD FIR', 'country': 'Russia', 'acc': 'Kaliningrad ACC'},
    'UMMV': {'name': 'MINSK FIR', 'country': 'Belarus', 'acc': 'Minsk ACC'},
    'UNKL': {'name': 'KRASNOYARSK FIR', 'country': 'Russia', 'acc': 'Krasnoyarsk ACC'},
    'UNNT': {'name': 'NOVOSIBIRSK FIR', 'country': 'Russia', 'acc': 'Novosibirsk ACC'},
    'URRV': {'name': 'ROSTOV FIR', 'country': 'Russia', 'acc': 'Rostov-Na-Donu ACC'},
    'USSV': {'name': 'YEKATERINBURG FIR', 'country': 'Russia', 'acc': 'Yekaterinburg ACC'},
    'USTV': {'name': 'TYUMEN FIR', 'country': 'Russia', 'acc': 'Tyumen ACC'},
    'UTAA': {'name': 'ASHGABAT FIR', 'country': 'Turkmenistan', 'acc': 'Ashgabat ACC'},
    'UTAK': {'name': 'TURKMENBASHI FIR', 'country': 'Turkmenistan', 'acc': 'Turkmenbashi ACC'},
    'UTAT': {'name': 'DASHOGUZ FIR', 'country': 'Turkmenistan', 'acc': 'Dashoguz ACC'},
    'UTAV': {'name': 'TURKMENABAT FIR', 'country': 'Turkmenistan', 'acc': 'Turkmenabat ACC'},
    'UTDD': {'name': 'DUSHANBE FIR', 'country': 'Tajikistan', 'acc': 'Dushanbe ACC'},
    'UTSD': {'name': 'SAMARKAND FIR', 'country': 'Uzbekistan', 'acc': 'Samarkand ACC'},
    'UTTR': {'name': 'TASHKENT FIR', 'country': 'Uzbekistan', 'acc': 'Tashkent ACC'},
    'UUWV': {'name': 'MOSCOW FIR', 'country': 'Russia', 'acc': 'Moscow ACC'},
    'UWWW': {'name': 'SAMARA FIR', 'country': 'Russia', 'acc': 'Samara ACC'},
    
    # Europe
    'LOWW': {'name': 'VIENNA FIR', 'country': 'Austria', 'acc': 'Wien ACC'},
    'LBSR': {'name': 'SOFIA FIR', 'country': 'Bulgaria', 'acc': 'Sofia ACC'},
    'LCCC': {'name': 'NICOSIA FIR', 'country': 'Cyprus', 'acc': 'Nicosia ACC'},
    'LDZO': {'name': 'ZAGREB FIR', 'country': 'Croatia', 'acc': 'Zagreb ACC'},
    'LECB': {'name': 'BARCELONA FIR', 'country': 'Spain', 'acc': 'Barcelona ACC'},
    'LECM': {'name': 'MADRID FIR', 'country': 'Spain', 'acc': 'Madrid ACC'},
    'LECS': {'name': 'SEVILLA FIR', 'country': 'Spain', 'acc': 'Sevilla ACC'},
    'LFBB': {'name': 'BORDEAUX FIR', 'country': 'France', 'acc': 'Bordeaux ACC'},
    'LFEE': {'name': 'REIMS FIR', 'country': 'France', 'acc': 'Reims ACC'},
    'LFFF': {'name': 'PARIS FIR', 'country': 'France', 'acc': 'Paris ACC'},
    'LFMM': {'name': 'MARSEILLE FIR', 'country': 'France', 'acc': 'Marseille ACC'},
    'LFRR': {'name': 'BREST FIR', 'country': 'France', 'acc': 'Brest ACC'},
    'LGGG': {'name': 'ATHENS FIR', 'country': 'Greece', 'acc': 'Athens ACC'},
    'LHCC': {'name': 'BUDAPEST FIR', 'country': 'Hungary', 'acc': 'Budapest ACC'},
    'LIBB': {'name': 'BRINDISI FIR', 'country': 'Italy', 'acc': 'Brindisi ACC'},
    'LIMM': {'name': 'MILANO FIR', 'country': 'Italy', 'acc': 'Milano ACC'},
    'LIRR': {'name': 'ROMA FIR', 'country': 'Italy', 'acc': 'Roma ACC'},
    'LJLA': {'name': 'LJUBLJANA FIR', 'country': 'Slovenia', 'acc': 'Ljubljana ACC'},
    'LKAA': {'name': 'PRAHA FIR', 'country': 'Czech Republic', 'acc': 'Praha ACC'},
    'LLLL': {'name': 'TEL-AVIV FIR', 'country': 'Israel', 'acc': 'Tel-Aviv ACC'},
    'LMMM': {'name': 'MALTA FIR', 'country': 'Malta', 'acc': 'Malta ACC'},
    'LOVV': {'name': 'VIENNA FIR', 'country': 'Austria', 'acc': 'Wien ACC'},
    'LPPC': {'name': 'LISBOA FIR', 'country': 'Portugal', 'acc': 'Lisboa ACC'},
    'LPPO': {'name': 'SANTA MARIA FIR', 'country': 'Azores', 'acc': 'Santa Maria OAC'},
    'LQSB': {'name': 'SARAJEVO FIR', 'country': 'Bosnia and Herzegovina', 'acc': 'Sarajevo ACC'},
    'LRBB': {'name': 'BUCURESTI FIR', 'country': 'Romania', 'acc': 'Bucuresti ACC'},
    'LSAG': {'name': 'GENEVE FIR', 'country': 'Switzerland', 'acc': 'Geneve ACC'},
    'LSAS': {'name': 'SWITZERLAND FIR', 'country': 'Switzerland', 'acc': 'Switzerland ACC'},
    'LSAZ': {'name': 'ZURICH FIR', 'country': 'Switzerland', 'acc': 'Zurich ACC'},
    'LTAA': {'name': 'ANKARA FIR', 'country': 'Turkey', 'acc': 'Ankara ACC'},
    'LTBB': {'name': 'ISTANBUL FIR', 'country': 'Turkey', 'acc': 'Istanbul ACC'},
    'LUUU': {'name': 'CHISINAU FIR', 'country': 'Moldova', 'acc': 'Chisinau ACC'},
    'LWSS': {'name': 'SKOPJE FIR', 'country': 'North Macedonia', 'acc': 'Skopje ACC'},
    'LYBA': {'name': 'BEOGRAD FIR', 'country': 'Serbia', 'acc': 'Beograd ACC'},
    'LZBB': {'name': 'BRATISLAVA FIR', 'country': 'Slovakia', 'acc': 'Bratislava ACC'},
    
    # Other regions
    'RCAA': {'name': 'TAIBEI FIR', 'country': 'Taiwan', 'acc': 'Taipei ACC'},
    'VABF': {'name': 'MUMBAI FIR', 'country': 'India', 'acc': 'Mumbai ACC'},
    'VCCC': {'name': 'COLOMBO FIR', 'country': 'Sri Lanka', 'acc': 'Colombo ACC'},
    'VDPF': {'name': 'PHNOM PENH FIR', 'country': 'Cambodia', 'acc': 'Phnom Penh ACC'},
    'VECF': {'name': 'KOLKATA FIR', 'country': 'Bhutan/India', 'acc': 'Kolkata ACC'},
    'VGFR': {'name': 'DHAKA FIR', 'country': 'Bangladesh', 'acc': 'Dhaka ACC'},
    'VHHK': {'name': 'HONG KONG FIR', 'country': 'Hong Kong', 'acc': 'Hong Kong ACC'},
    'VIDF': {'name': 'DELHI FIR', 'country': 'India', 'acc': 'Delhi ACC'},
    'VLVT': {'name': 'VIENTIANE FIR', 'country': 'Laos', 'acc': 'Vientiane ACC'},
    'VNSM': {'name': 'KATHMANDU FIR', 'country': 'Nepal', 'acc': 'Kathmandu ACC'},
    'VOMF': {'name': 'CHENNAI FIR', 'country': 'India', 'acc': 'Chennai ACC'},
    'VRMF': {'name': 'MALE FIR', 'country': 'Maldives', 'acc': 'Male ACC'},
    'VTBB': {'name': 'BANGKOK FIR', 'country': 'Thailand', 'acc': 'Bangkok ACC'},
    'VVHM': {'name': 'HO CHI MINH FIR', 'country': 'Vietnam', 'acc': 'Ho Chi Minh ACC'},
    'VVHN': {'name': 'HANOI FIR', 'country': 'Vietnam', 'acc': 'Hanoi ACC'},
    'VYYF': {'name': 'YANGON FIR', 'country': 'Myanmar', 'acc': 'Yangon ACC'},
    'WAAF': {'name': 'UJUNG PANDANG FIR', 'country': 'Indonesia/Timor Leste', 'acc': 'Ujung Pandang ACC'},
    'WBFC': {'name': 'KOTA KINABALU FIR', 'country': 'Brunei/Malaysia', 'acc': 'Kota Kinabalu ACC'},
    'WIIF': {'name': 'JAKARTA FIR', 'country': 'Indonesia', 'acc': 'Jakarta ACC'},
    'WMFC': {'name': 'KUALA LUMPUR FIR', 'country': 'Malaysia', 'acc': 'Kuala Lumpur ACC'},
    'WSJC': {'name': 'SINGAPORE FIR', 'country': 'Singapore', 'acc': 'Singapore ACC'},
}


def get_fir_name(fir_code: str) -> str:
    """Get FIR full name from code"""
    fir_info = FIR_DATABASE.get(fir_code.upper())
    if fir_info:
        return fir_info['name']
    return f"{fir_code} FIR"


def get_fir_info(fir_code: str) -> dict:
    """Get complete FIR information from code"""
    return FIR_DATABASE.get(fir_code.upper(), {
        'name': f'{fir_code} FIR',
        'country': 'Unknown',
        'acc': 'Unknown'
    })


def is_oceanic_fir(fir_code: str) -> bool:
    """Check if FIR is oceanic type"""
    fir_info = FIR_DATABASE.get(fir_code.upper())
    if fir_info:
        return fir_info.get('type') == 'Oceanic'
    return False


def get_package3_fir_codes() -> list:
    """Get FIR codes for Package 3"""
    # Package 3는 노선/패키지 내용에 따라 포함 FIR이 달라질 수 있으므로
    # 하드코딩된 소수 FIR로 제한하지 않고, 데이터베이스에 등록된 모든 FIR 코드를 반환합니다.
    # 실제 표시 순서/실제 사용 FIR은 상위 로직에서 추출된 actual_fir_list와 fir_order로 제한합니다.
    return list(FIR_DATABASE.keys())


def validate_fir_code(fir_code: str) -> bool:
    """Check if FIR code exists in database"""
    return fir_code.upper() in FIR_DATABASE

