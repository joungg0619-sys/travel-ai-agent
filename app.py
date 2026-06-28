import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os
import requests
from urllib.parse import quote
import re
import json
import html
from datetime import date, timedelta
from io import BytesIO
import math

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

load_dotenv()

st.set_page_config(
    page_title="여행 계획 AI Agent",
    page_icon="✈️",
    layout="wide",
)


st.markdown(
    """
    <style>
        .place-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.9rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.035);
    }

    .place-title {
        font-size: 1rem;
        font-weight: 800;
        color: #111827;
        margin-bottom: 0.25rem;
    }

    .place-category {
        font-size: 0.85rem;
        color: #6b7280;
        margin-bottom: 0.35rem;
    }

    .place-address {
        font-size: 0.82rem;
        color: #4b5563;
        margin-bottom: 0.55rem;
    }

    .budget-item-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1rem 1.1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.035);
        min-height: 105px;
    }

    .budget-item-title {
        font-size: 0.88rem;
        color: #6b7280;
        margin-bottom: 0.35rem;
    }

    .budget-item-value {
        font-size: 1.25rem;
        font-weight: 800;
        color: #111827;
    }

    .budget-item-percent {
        font-size: 0.8rem;
        color: #6b7280;
        margin-top: 0.25rem;
    }
    .main-title {
        font-size: 2.6rem;
        font-weight: 800;
        margin-bottom: 0.3rem;
    }

    .sub-title {
        font-size: 1.05rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }

    .section-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1.3rem 1.5rem;
        margin-bottom: 1.1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }

    .metric-card {
        background: linear-gradient(180deg, #ffffff 0%, #f9fafb 100%);
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1rem 1.2rem;
        min-height: 115px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.035);
    }

    .metric-label {
        color: #6b7280;
        font-size: 0.9rem;
        margin-bottom: 0.35rem;
    }

    .metric-value {
        font-size: 1.35rem;
        font-weight: 800;
        color: #111827;
    }

    .metric-caption {
        color: #6b7280;
        font-size: 0.85rem;
        margin-top: 0.4rem;
    }

    .timeline-item {
        border-left: 4px solid #3b82f6;
        padding: 0.2rem 0 0.8rem 1rem;
        margin-bottom: 0.6rem;
    }

    .timeline-time {
        font-weight: 800;
        color: #1f2937;
    }

    .timeline-place a {
        font-weight: 700;
        color: #2563eb;
        text-decoration: none;
    }

    .timeline-desc {
        color: #374151;
        margin-top: 0.15rem;
    }

    .cost-badge {
        display: inline-block;
        background-color: #ecfdf5;
        color: #047857;
        padding: 0.15rem 0.45rem;
        border-radius: 8px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-left: 0.25rem;
    }

    .download-box {
        background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
        border: 1px solid #bfdbfe;
        border-radius: 18px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1.3rem;
    }

    div[data-testid="stSidebar"] {
        background-color: #f8fafc;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_secret(name):
    try:
        value = st.secrets[name]
        if value:
            return str(value).strip()
    except Exception:
        pass

    value = os.getenv(name)
    if value:
        return str(value).strip()

    return None


OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
NAVER_CLIENT_ID = get_secret("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = get_secret("NAVER_CLIENT_SECRET")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


REGION_ALIASES = {
    "서울": ["서울", "서울시", "서울특별시"],
    "부산": ["부산", "부산시", "부산광역시"],
    "대구": ["대구", "대구시", "대구광역시"],
    "인천": ["인천", "인천시", "인천광역시"],
    "광주": ["광주", "광주시", "광주광역시"],
    "대전": ["대전", "대전시", "대전광역시"],
    "울산": ["울산", "울산시", "울산광역시"],
    "세종": ["세종", "세종시", "세종특별자치시"],
    "경기": ["경기", "경기도"],
    "강원": ["강원", "강원도", "강원특별자치도"],
    "충북": ["충북", "충청북도"],
    "충남": ["충남", "충청남도"],
    "전북": ["전북", "전라북도", "전북특별자치도"],
    "전남": ["전남", "전라남도"],
    "경북": ["경북", "경상북도"],
    "경남": ["경남", "경상남도"],
    "제주": ["제주", "제주도", "제주특별자치도"],
}

KOREA_CITY_COORDS = {
    "서울": (37.5665, 126.9780),
    "명동": (37.5636, 126.9820),
    "강남": (37.4979, 127.0276),
    "홍대": (37.5563, 126.9220),
    "부산": (35.1796, 129.0756),
    "해운대": (35.1631, 129.1635),
    "대구": (35.8714, 128.6014),
    "인천": (37.4563, 126.7052),
    "광주": (35.1595, 126.8526),
    "대전": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114),
    "세종": (36.4800, 127.2890),
    "수원": (37.2636, 127.0286),
    "성남": (37.4200, 127.1265),
    "용인": (37.2411, 127.1776),
    "고양": (37.6584, 126.8320),
    "춘천": (37.8813, 127.7298),
    "강릉": (37.7519, 128.8761),
    "청주": (36.6424, 127.4890),
    "천안": (36.8151, 127.1139),
    "전주": (35.8242, 127.1480),
    "여수": (34.7604, 127.6622),
    "포항": (36.0190, 129.3435),
    "경주": (35.8562, 129.2247),
    "창원": (35.2285, 128.6811),
    "진주": (35.1800, 128.1076),
    "제주": (33.4996, 126.5312),
    "서귀포": (33.2541, 126.5601),
}

KOREA_REGION_COORDS = {
    "경기": (37.4138, 127.5183),
    "강원": (37.8228, 128.1555),
    "충북": (36.8000, 127.7000),
    "충남": (36.5184, 126.8000),
    "전북": (35.7175, 127.1530),
    "전남": (34.8679, 126.9910),
    "경북": (36.4919, 128.8889),
    "경남": (35.4606, 128.2132),
}

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<.*?>", "", text)
    return html.unescape(text)


def extract_broad_region(text):
    if not text:
        return None

    for region, aliases in REGION_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return region

    return None


def make_naver_map_search_link(query):
    encoded_query = quote(query)
    return f"https://map.naver.com/p/search/{encoded_query}"


def get_location_keyword(destination):
    """
    네이버지도 검색 정확도를 높이기 위해
    사용자가 입력한 여행지에서 핵심 지역명만 추출한다.

    예:
    - 서울 명동 → 명동
    - 경기도 수원 → 수원
    - 부산 해운대 → 해운대
    - 노량진 → 노량진
    """
    if not destination:
        return ""

    text = destination.strip()

    remove_words = [
        "서울특별시", "서울시", "서울",
        "부산광역시", "부산시", "부산",
        "대구광역시", "대구시", "대구",
        "인천광역시", "인천시", "인천",
        "광주광역시", "광주시", "광주",
        "대전광역시", "대전시", "대전",
        "울산광역시", "울산시", "울산",
        "세종특별자치시", "세종시", "세종",
        "경기도", "경기",
        "강원특별자치도", "강원도", "강원",
        "충청북도", "충북",
        "충청남도", "충남",
        "전북특별자치도", "전라북도", "전북",
        "전라남도", "전남",
        "경상북도", "경북",
        "경상남도", "경남",
        "제주특별자치도", "제주도", "제주",
    ]

    for word in remove_words:
        text = text.replace(word, " ")

    text = re.sub(r"\s+", " ", text).strip()

    if text:
        return text

    return destination.strip()


def make_naver_place_link(place, destination=""):
    """
    네이버지도 검색어는 '장소명 + 핵심 지역명'으로 만든다.
    상세 주소를 붙이면 검색 실패가 생길 수 있고,
    장소명만 쓰면 다른 지역의 동명이 검색될 수 있다.
    """
    title = place.get("title", "").strip()
    location_keyword = get_location_keyword(destination)

    if location_keyword and location_keyword not in title:
        query = f"{title} {location_keyword}"
    else:
        query = title

    return make_naver_map_search_link(query)


def fetch_naver_local_raw(query, display=5, start=1, sort="random"):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {
            "ok": False,
            "status_code": None,
            "error": "NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 설정되어 있지 않습니다.",
            "data": None,
            "text": "",
        }

    url = "https://openapi.naver.com/v1/search/local.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Accept": "application/json",
    }

    params = {
        "query": query,
        "display": min(display, 5),
        "start": start,
        "sort": sort,
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)

        try:
            data = res.json()
        except Exception:
            data = None

        return {
            "ok": res.status_code == 200,
            "status_code": res.status_code,
            "error": None if res.status_code == 200 else res.text,
            "data": data,
            "text": res.text,
        }

    except Exception as e:
        return {
            "ok": False,
            "status_code": None,
            "error": str(e),
            "data": None,
            "text": "",
        }


def search_naver_local(query, display=5):
    raw = fetch_naver_local_raw(query, display=display)

    if not raw["ok"]:
        return [], raw

    data = raw["data"] or {}
    items = data.get("items", [])

    results = []

    for item in items:
        title = clean_html(item.get("title", ""))
        category = clean_html(item.get("category", ""))
        address = clean_html(item.get("address", ""))
        road_address = clean_html(item.get("roadAddress", ""))
        mapx = item.get("mapx", "")
        mapy = item.get("mapy", "")

        if not title:
            continue

        results.append(
            {
                "title": title,
                "category": category,
                "address": address,
                "road_address": road_address,
                "mapx": mapx,
                "mapy": mapy,
            }
        )

    return results, raw


def address_matches_region(place, broad_region):
    if not broad_region:
        return True

    address_text = f"{place.get('address', '')} {place.get('road_address', '')}"
    aliases = REGION_ALIASES.get(broad_region, [broad_region])

    return any(alias in address_text for alias in aliases)

def get_weather_target(destination):
    """
    한국 주요 지역은 Open-Meteo geocoding에 의존하지 않고
    직접 좌표를 사용한다.
    """
    if not destination:
        return None, None, None

    # 도시/관광지 단위 우선 매칭
    for name, coords in KOREA_CITY_COORDS.items():
        if name in destination:
            return name, coords[0], coords[1]

    # 광역 지역 매칭
    broad_region = extract_broad_region(destination)

    if broad_region in KOREA_REGION_COORDS:
        lat, lon = KOREA_REGION_COORDS[broad_region]
        return broad_region, lat, lon

    if broad_region in KOREA_CITY_COORDS:
        lat, lon = KOREA_CITY_COORDS[broad_region]
        return broad_region, lat, lon

    # 그래도 없으면 첫 단어를 geocoding 후보로 사용
    tokens = destination.split()
    fallback_name = tokens[0] if tokens else destination

    return fallback_name, None, None


def get_weather(destination, start_date, end_date):
    weather_location, lat, lon = get_weather_target(destination)

    if not weather_location:
        return "날씨 정보를 가져올 수 없습니다. 여행지를 입력해 주세요."

    # 좌표가 없을 때만 geocoding API 사용
    if lat is None or lon is None:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_params = {
            "name": weather_location,
            "count": 1,
            "language": "ko",
            "format": "json",
        }

        try:
            geo_res = requests.get(geo_url, params=geo_params, timeout=10)
            geo_data = geo_res.json()
        except Exception:
            return "날씨 정보를 가져오는 중 오류가 발생했습니다."

        if "results" not in geo_data or not geo_data["results"]:
            return f"날씨 정보를 가져올 수 없습니다. 날씨 기준 지역: {weather_location}"

        location = geo_data["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]

    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "auto",
    }

    try:
        weather_res = requests.get(weather_url, params=weather_params, timeout=10)
        weather_data = weather_res.json()
    except Exception:
        return "날씨 정보를 가져오는 중 오류가 발생했습니다."

    if "daily" not in weather_data:
        return (
            f"해당 기간의 상세 날씨 예보를 가져올 수 없습니다. "
            f"날씨 기준 지역은 {weather_location}입니다. "
            f"너무 먼 날짜는 예보가 제공되지 않을 수 있습니다."
        )

    daily = weather_data["daily"]

    summary = f"날씨 기준 지역: {weather_location}\n"
    summary += "날씨 예보:\n"

    for i in range(len(daily["time"])):
        summary += (
            f"- {daily['time'][i]}: "
            f"최저 {daily['temperature_2m_min'][i]}°C / "
            f"최고 {daily['temperature_2m_max'][i]}°C / "
            f"강수확률 {daily['precipitation_probability_max'][i]}%\n"
        )

    return summary

def parse_budget_to_won(budget_text):
    if not budget_text:
        return None

    text = budget_text.replace(",", "").replace(" ", "")
    match = re.search(r"\d+(\.\d+)?", text)

    if not match:
        return None

    amount = float(match.group())

    if "만원" in text or "만" in text:
        return int(amount * 10000)
    elif "천원" in text:
        return int(amount * 1000)
    else:
        return int(amount)


def format_won(amount):
    return f"{amount:,}원"


def calculate_budget_plan(total_budget, days):
    if total_budget is None:
        return None

    lodging = int(total_budget * 0.35)
    food = int(total_budget * 0.28)
    transport = int(total_budget * 0.14)
    activity = int(total_budget * 0.13)
    emergency = total_budget - lodging - food - transport - activity
    daily_budget = int(total_budget / days)

    if daily_budget < 70000:
        budget_level = "초절약형"
        budget_warning = "1일 예산이 낮은 편입니다. 무료 관광지, 대중교통, 저가 숙소 중심으로 계획하는 것이 좋습니다."
    elif daily_budget < 120000:
        budget_level = "절약형"
        budget_warning = "가성비 여행이 적합합니다. 숙박과 식비를 조절하면 무리 없이 여행할 수 있습니다."
    elif daily_budget < 200000:
        budget_level = "일반형"
        budget_warning = "일반적인 국내 여행 예산으로 무난한 일정 구성이 가능합니다."
    else:
        budget_level = "여유형"
        budget_warning = "숙소, 음식, 체험 활동 선택 폭이 넓은 예산입니다."

    return {
        "총 예산": total_budget,
        "1일 평균 예산": daily_budget,
        "숙박비": lodging,
        "식비": food,
        "교통비": transport,
        "관광/체험비": activity,
        "예비비": emergency,
        "예산 유형": budget_level,
        "예산 코멘트": budget_warning,
    }


def get_korea_price_guide():
    return """
한국 여행 물가 보정 기준:
- 일반 식사 1끼: 10,000원부터 15,000원
- 국밥/분식/간단한 식사: 8,000원부터 12,000원
- 카페 음료 1잔: 4,500원부터 7,000원
- 프랜차이즈 치킨 1마리: 18,000원부터 25,000원
- 택시 기본 이동: 5,000원부터 15,000원 이상
- 시내 대중교통 1회: 약 1,500원 내외
- 관광지 입장료: 무료부터 20,000원 수준
- 국내 숙박 1박: 저가형 40,000원부터 80,000원, 일반형 80,000원부터 150,000원 이상

주의:
- 음식 가격을 지나치게 낮게 잡지 말 것.
- 특히 치킨, 회, 고기, 해산물, 관광지 주변 음식은 보수적으로 계산할 것.
- 2020년대 중반 한국 물가 기준으로 현실적인 비용을 제시할 것.
"""


def build_search_queries(destination, preference):
    queries = []

    base_keywords = [
        "관광지",
        "맛집",
        "카페",
        "실내 관광지",
        "박물관",
        "쇼핑",
        "숙소",
    ]

    for keyword in base_keywords:
        queries.append(f"{destination} {keyword}")

    if preference:
        preference_parts = re.split(r"[,/ ]+", preference)

        for part in preference_parts:
            part = part.strip()
            if part:
                queries.append(f"{destination} {part}")

    return queries


def get_verified_place_candidates(destination, preference, use_region_filter=True):
    broad_region = extract_broad_region(destination)
    queries = build_search_queries(destination, preference)

    candidates = []
    seen = set()
    diagnostics = []

    for query in queries:
        raw_results, raw_response = search_naver_local(query, display=5)

        before_count = len(raw_results)

        if use_region_filter:
            filtered_results = [
                place for place in raw_results
                if address_matches_region(place, broad_region)
            ]
        else:
            filtered_results = raw_results

        after_count = len(filtered_results)

        diagnostics.append(
            {
                "query": query,
                "status_code": raw_response.get("status_code"),
                "ok": raw_response.get("ok"),
                "before_filter": before_count,
                "after_filter": after_count,
                "error": raw_response.get("error"),
            }
        )

        for place in filtered_results:
            key = f"{place['title']}|{place.get('road_address') or place.get('address')}"

            if key in seen:
                continue

            seen.add(key)

            place_id = f"P{len(candidates) + 1:03d}"
            place["id"] = place_id
            place["map_link"] = make_naver_place_link(place, destination)
            candidates.append(place)

    return candidates[:30], diagnostics


def format_candidates_for_prompt(candidates):
    lines = []

    for place in candidates:
        lines.append(
            f"{place['id']} | {place['title']} | "
            f"카테고리: {place['category']} | "
            f"주소: {place['road_address'] or place['address']}"
        )

    return "\n".join(lines)


def get_candidate_by_id(candidates, place_id):
    for place in candidates:
        if place["id"] == place_id:
            return place

    return None
def get_used_place_ids(plan_data):
    used_place_ids = set()

    for day in plan_data.get("daily_schedule", []):
        for item in day.get("items", []):
            place_id = item.get("place_id")
            if place_id:
                used_place_ids.add(place_id)

    return used_place_ids


def get_place_lon_lat(place):
    """
    네이버 지역 검색 API의 mapx, mapy 값을 위도/경도로 변환한다.
    mapx, mapy는 보통 경도/위도에 10,000,000을 곱한 값이다.
    """
    mapx = place.get("mapx")
    mapy = place.get("mapy")

    if not mapx or not mapy:
        return None, None

    try:
        lon = float(mapx) / 10000000
        lat = float(mapy) / 10000000
    except Exception:
        return None, None

    # 한국 좌표 범위가 아니면 잘못된 값으로 판단
    if not (120 <= lon <= 135 and 30 <= lat <= 40):
        return None, None

    return lon, lat


def lon_lat_to_web_mercator(lon, lat):
    """
    네이버지도 길찾기 URL은 일반 위도/경도보다 Web Mercator 좌표를 더 안정적으로 받는다.
    WGS84 lon/lat → Web Mercator x/y 변환.
    """
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y = y * 20037508.34 / 180

    return x, y


def make_naver_direction_point(place):
    """
    네이버지도 길찾기 URL에 들어갈 출발지/도착지 포인트 문자열을 만든다.
    형식:
    x좌표,y좌표,장소명,-,PLACE_POI
    """
    title = place.get("title", "").strip()
    lon, lat = get_place_lon_lat(place)

    if not title or lon is None or lat is None:
        return None

    x, y = lon_lat_to_web_mercator(lon, lat)
    encoded_title = quote(title)

    return f"{x:.7f},{y:.7f},{encoded_title},-,PLACE_POI"


def make_route_search_link(start_place, end_place, destination):
    """
    네이버지도 검색창이 아니라, 왼쪽 '길찾기' 탭에
    출발지와 도착지가 들어가도록 directions URL을 만든다.
    """
    start_point = make_naver_direction_point(start_place)
    end_point = make_naver_direction_point(end_place)

    # 좌표를 만들 수 없을 때만 검색 방식으로 fallback
    if not start_point or not end_point:
        start_name = start_place.get("title", "").strip()
        end_name = end_place.get("title", "").strip()
        location_keyword = get_location_keyword(destination)

        if location_keyword:
            query = f"{start_name}에서 {end_name} 가는 길 {location_keyword}"
        else:
            query = f"{start_name}에서 {end_name} 가는 길"

        return make_naver_map_search_link(query)

    return f"https://map.naver.com/p/directions/{start_point}/{end_point}/-/transit?c=15.00,0,0,0,dh"

def get_day_places(day, candidates):
    """
    하루 일정에 포함된 place_id를 실제 후보 장소 정보로 변환한다.
    같은 장소가 연속으로 반복되면 한 번만 남긴다.
    """
    places = []
    seen_ids = set()

    for item in day.get("items", []):
        place_id = item.get("place_id", "")
        place = get_candidate_by_id(candidates, place_id)

        if place and place.get("id") not in seen_ids:
            places.append(place)
            seen_ids.add(place.get("id"))

    return places


def render_day_route_links(day, candidates, destination):
    """
    날짜별 일정 아래에 구간별 네이버지도 동선 확인 버튼을 표시한다.
    예: A 장소 → B 장소 [네이버지도에서 동선 확인]
    """
    day_places = get_day_places(day, candidates)

    if len(day_places) < 2:
        return

    st.markdown("#### 날짜별 동선 확인")
    st.caption("각 버튼을 누르면 네이버지도에서 두 장소 사이의 이동 경로를 확인할 수 있습니다.")

    for i in range(len(day_places) - 1):
        start_place = day_places[i]
        end_place = day_places[i + 1]
        route_link = make_route_search_link(start_place, end_place, destination)

        route_col1, route_col2 = st.columns([2, 1])

        with route_col1:
            st.markdown(f"**{start_place['title']} → {end_place['title']}**")

        with route_col2:
            st.link_button(
                "네이버지도에서 동선 확인",
                route_link,
                use_container_width=True,
            )


def render_extra_place_recommendations(plan_data, candidates, max_items=6):
    used_place_ids = get_used_place_ids(plan_data)

    extra_places = [
        place for place in candidates
        if place.get("id") not in used_place_ids
    ]

    if not extra_places:
        return

    st.markdown("## 추가 추천 장소")
    st.write("아래 장소들은 일정에는 포함되지 않았지만, 네이버 지역 검색 결과를 기반으로 추가로 방문해볼 만한 장소입니다.")

    cols = st.columns(3)

    for idx, place in enumerate(extra_places[:max_items]):
        with cols[idx % 3]:
            title = place.get("title", "")
            category = place.get("category", "분류 정보 없음")
            address = place.get("road_address") or place.get("address") or "주소 정보 없음"
            link = place.get("map_link", "")

            st.markdown(
                f"""
                <div class="place-card">
                    <div class="place-title">{title}</div>
                    <div class="place-category">{category}</div>
                    <div class="place-address">{address}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if link:
                st.link_button("네이버지도에서 보기", link, use_container_width=True)


def render_budget_breakdown_cards(budget_plan):
    st.markdown("## 예상 상세 예산")
    st.write("입력한 총예산을 기준으로 숙박, 식비, 교통, 관광/체험, 예비비를 품목별로 나누어 계산했습니다.")

    total_budget = budget_plan["총 예산"]

    budget_items = [
        ("숙박비", budget_plan["숙박비"]),
        ("식비", budget_plan["식비"]),
        ("교통비", budget_plan["교통비"]),
        ("관광/체험비", budget_plan["관광/체험비"]),
        ("예비비", budget_plan["예비비"]),
    ]

    cols = st.columns(5)

    for idx, (label, amount) in enumerate(budget_items):
        percent = round((amount / total_budget) * 100, 1) if total_budget else 0

        with cols[idx]:
            st.markdown(
                f"""
                <div class="budget-item-card">
                    <div class="budget-item-title">{label}</div>
                    <div class="budget-item-value">{format_won(amount)}</div>
                    <div class="budget-item-percent">총예산의 {percent}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.progress(min(percent / 100, 1.0))

    st.caption(f"총 예산 {format_won(total_budget)} 기준 / 1일 평균 예산 {format_won(budget_plan['1일 평균 예산'])}")


def render_metric_card(label, value, caption=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_travel_plan(plan_data, candidates, budget_plan, destination):
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("## 전체 여행 요약")
    st.write(plan_data.get("summary", ""))
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### 날씨 반영 전략")
        st.write(plan_data.get("weather_strategy", ""))
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### 예산 사용 전략")
        st.write(plan_data.get("budget_strategy", ""))
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("## 날짜별 일정")

    daily_schedule = plan_data.get("daily_schedule", [])

    if daily_schedule:
        tab_titles = [
            f"{day.get('day_title', f'{idx + 1}일차')} · {day.get('date', '')}"
            for idx, day in enumerate(daily_schedule)
        ]

        tabs = st.tabs(tab_titles)

        for tab, day in zip(tabs, daily_schedule):
            with tab:
                for item in day.get("items", []):
                    time_text = item.get("time", "")
                    place_id = item.get("place_id", "")
                    description = item.get("description", "")
                    cost = item.get("estimated_cost", "")

                    place = get_candidate_by_id(candidates, place_id)

                    if place:
                        place_html = f'<a href="{place["map_link"]}" target="_blank">{place["title"]}</a>'
                    else:
                        place_html = "장소 정보 없음"

                    st.markdown(
                        f"""
                        <div class="timeline-item">
                            <div class="timeline-time">{time_text}</div>
                            <div class="timeline-place">{place_html}
                                <span class="cost-badge">예상 비용: {cost}</span>
                            </div>
                            <div class="timeline-desc">{description}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.divider()
                render_day_route_links(day, candidates, destination)

                st.divider()
                render_day_route_links(day, candidates, destination)

    render_extra_place_recommendations(plan_data, candidates)

    render_budget_breakdown_cards(budget_plan)


def register_korean_pdf_fonts():
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    except Exception:
        pass

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    except Exception:
        pass


def pdf_paragraph(text, style):
    safe = html.escape(str(text or ""))
    safe = safe.replace("\n", "<br/>")
    return Paragraph(safe, style)


def pdf_place_link(place, style):
    title = html.escape(place.get("title", ""))
    url = html.escape(place.get("map_link", ""), quote=True)

    if url:
        return Paragraph(f'<link href="{url}">{title}</link>', style)

    return Paragraph(title, style)


def build_travel_pdf(
    destination,
    start_date,
    end_date,
    days,
    weather_info,
    budget_plan,
    plan_data,
    candidates,
):
    register_korean_pdf_fonts()

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KoreanTitle",
        parent=styles["Title"],
        fontName="HYGothic-Medium",
        fontSize=20,
        leading=26,
        alignment=TA_CENTER,
        spaceAfter=18,
    )

    h1_style = ParagraphStyle(
        "KoreanH1",
        parent=styles["Heading1"],
        fontName="HYGothic-Medium",
        fontSize=15,
        leading=20,
        spaceBefore=14,
        spaceAfter=8,
    )

    h2_style = ParagraphStyle(
        "KoreanH2",
        parent=styles["Heading2"],
        fontName="HYGothic-Medium",
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "KoreanBody",
        parent=styles["BodyText"],
        fontName="HYSMyeongJo-Medium",
        fontSize=10,
        leading=15,
        spaceAfter=6,
    )

    small_style = ParagraphStyle(
        "KoreanSmall",
        parent=styles["BodyText"],
        fontName="HYSMyeongJo-Medium",
        fontSize=8,
        leading=11,
    )

    story = []

    story.append(pdf_paragraph("여행 계획 AI Agent 일정표", title_style))
    story.append(pdf_paragraph(f"여행지: {destination}", body_style))
    story.append(pdf_paragraph(f"여행 기간: {start_date} ~ {end_date} / 총 {days}일", body_style))
    story.append(Spacer(1, 10))

    story.append(pdf_paragraph("1. 전체 여행 요약", h1_style))
    story.append(pdf_paragraph(plan_data.get("summary", ""), body_style))

    story.append(pdf_paragraph("2. 날씨 정보", h1_style))
    story.append(pdf_paragraph(weather_info, body_style))

    story.append(pdf_paragraph("3. 예산 분석", h1_style))

    budget_table_data = [
        ["항목", "금액"],
        ["총 예산", format_won(budget_plan["총 예산"])],
        ["1일 평균 예산", format_won(budget_plan["1일 평균 예산"])],
        ["숙박비", format_won(budget_plan["숙박비"])],
        ["식비", format_won(budget_plan["식비"])],
        ["교통비", format_won(budget_plan["교통비"])],
        ["관광/체험비", format_won(budget_plan["관광/체험비"])],
        ["예비비", format_won(budget_plan["예비비"])],
        ["예산 유형", budget_plan["예산 유형"]],
    ]

    budget_table = Table(budget_table_data, colWidths=[160, 280])
    budget_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "HYSMyeongJo-Medium"),
                ("FONTNAME", (0, 0), (-1, 0), "HYGothic-Medium"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    story.append(budget_table)
    story.append(Spacer(1, 8))
    story.append(pdf_paragraph(budget_plan["예산 코멘트"], body_style))

    story.append(pdf_paragraph("4. 날씨 반영 전략", h1_style))
    story.append(pdf_paragraph(plan_data.get("weather_strategy", ""), body_style))

    story.append(pdf_paragraph("5. 예산 사용 전략", h1_style))
    story.append(pdf_paragraph(plan_data.get("budget_strategy", ""), body_style))

    story.append(PageBreak())
    story.append(pdf_paragraph("6. 날짜별 일정", h1_style))

    daily_schedule = plan_data.get("daily_schedule", [])

    for day in daily_schedule:
        date_text = day.get("date", "")
        title = day.get("day_title", "")
        story.append(pdf_paragraph(f"{title} - {date_text}", h2_style))

        table_data = [["시간", "장소", "설명", "예상 비용"]]

        for item in day.get("items", []):
            place_id = item.get("place_id", "")
            place = get_candidate_by_id(candidates, place_id)

            if place:
                place_cell = pdf_place_link(place, small_style)
            else:
                place_cell = pdf_paragraph("검증된 장소 없음", small_style)

            table_data.append(
                [
                    pdf_paragraph(item.get("time", ""), small_style),
                    place_cell,
                    pdf_paragraph(item.get("description", ""), small_style),
                    pdf_paragraph(item.get("estimated_cost", ""), small_style),
                ]
            )

        schedule_table = Table(table_data, colWidths=[55, 105, 230, 80])
        schedule_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "HYSMyeongJo-Medium"),
                    ("FONTNAME", (0, 0), (-1, 0), "HYGothic-Medium"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        story.append(schedule_table)
        story.append(Spacer(1, 10))

    story.append(PageBreak())

    story.append(pdf_paragraph("7. 예상 상세 예산", h1_style))
    story.append(pdf_paragraph(plan_data.get("estimated_budget_detail", ""), body_style))

    story.append(pdf_paragraph("8. 추천 음식", h1_style))
    for food in plan_data.get("recommended_foods", []):
        story.append(pdf_paragraph(f"- {food}", body_style))

    story.append(pdf_paragraph("9. 비 올 때 대체 일정", h1_style))
    for item in plan_data.get("rainy_day_alternatives", []):
        story.append(pdf_paragraph(f"- {item}", body_style))

    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()


def generate_travel_plan(destination, start_date, end_date, days, budget, preference):
    total_budget = parse_budget_to_won(budget)
    budget_plan = calculate_budget_plan(total_budget, days)

    if budget_plan is None:
        raise ValueError("예산 형식을 인식하지 못했습니다. 예: 35만원, 500000원")

    weather_info = get_weather(destination, start_date, end_date)
    price_guide = get_korea_price_guide()

    strict_candidates, _ = get_verified_place_candidates(
        destination,
        preference,
        use_region_filter=True,
    )

    candidates = strict_candidates

    if not strict_candidates:
        relaxed_candidates, _ = get_verified_place_candidates(
            destination,
            preference,
            use_region_filter=False,
        )

        if relaxed_candidates:
            candidates = relaxed_candidates

    if not candidates:
        raise ValueError("네이버 지역 검색 결과가 충분하지 않습니다. 여행지를 더 넓은 지역명으로 입력해 보세요.")

    candidates_text = format_candidates_for_prompt(candidates)

    prompt = f"""
    너는 전문 여행 플래너 AI Agent야.

    아래 조건, 여행 기간, 날씨 정보, 예산 분석 정보, 한국 물가 보정 기준, 검증된 네이버 지역 검색 장소 후보를 모두 반영해서 여행 계획을 작성해줘.

    여행지: {destination}
    여행 기간: {start_date}부터 {end_date}까지, 총 {days}일
    사용자가 입력한 예산: {budget}
    여행 취향: {preference}

    날씨 정보:
    {weather_info}

    예산 분석:
    - 총 예산: {format_won(budget_plan['총 예산'])}
    - 1일 평균 예산: {format_won(budget_plan['1일 평균 예산'])}
    - 숙박비: {format_won(budget_plan['숙박비'])}
    - 식비: {format_won(budget_plan['식비'])}
    - 교통비: {format_won(budget_plan['교통비'])}
    - 관광/체험비: {format_won(budget_plan['관광/체험비'])}
    - 예비비: {format_won(budget_plan['예비비'])}
    - 예산 유형: {budget_plan['예산 유형']}
    - 예산 코멘트: {budget_plan['예산 코멘트']}

    한국 물가 보정 기준:
    {price_guide}

    검증된 네이버 지역 검색 장소 후보:
    {candidates_text}

    매우 중요한 규칙:
    - 장소는 반드시 위의 검증된 후보 목록에 있는 place_id만 사용해.
    - 새로운 장소명, 임의 업체명, 과거에 있었던 브랜드명, 존재 여부가 불확실한 장소명은 절대 만들지 마.
    - place_id는 반드시 P001, P002 같은 형식으로 후보 목록에 존재하는 값만 사용해.
    - 후보 목록에 없는 장소는 절대 사용하지 마.
    - 음식 가격을 지나치게 낮게 잡지 마.
    - 한국 물가 보정 기준을 반드시 반영해.
    - 준비물과 절약 팁 항목은 작성하지 마.

    반드시 아래 JSON 형식으로만 답변해줘.
    마크다운 문법은 사용하지 말고, JSON 이외의 설명도 쓰지 마.

    {{
      "summary": "전체 여행 요약",
      "weather_strategy": "날씨를 어떻게 반영했는지 설명",
      "budget_strategy": "예산을 어떻게 배분했는지 설명",
      "daily_schedule": [
        {{
          "date": "YYYY-MM-DD",
          "day_title": "1일차",
          "items": [
            {{
              "time": "아침",
              "place_id": "P001",
              "description": "일정 설명",
              "estimated_cost": "예상 비용"
            }}
          ]
        }}
      ],
      "estimated_budget_detail": "상세 예산 설명",
      "recommended_foods": ["추천 음식 1", "추천 음식 2"],
      "rainy_day_alternatives": ["우천 시 대체 일정 1", "우천 시 대체 일정 2"]
    }}

    조건:
    - 날짜는 반드시 사용자가 선택한 날짜 범위와 일치해야 해.
    - daily_schedule의 날짜 개수는 반드시 {days}개여야 해.
    - 하루에 아침, 점심, 오후, 저녁 중심으로 일정을 구성해줘.
    - 강수확률이 높은 날은 실내 관광지, 카페, 박물관, 쇼핑몰 위주로 추천해줘.
    - 날씨가 좋은 날은 야외 관광지, 자연 경관, 산책 코스를 추천해줘.
    - 예산을 초과하지 않도록 현실적인 일정으로 구성해줘.
    - 이동 동선이 너무 복잡하지 않게 구성해줘.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "너는 검증된 장소 후보 안에서만 여행 일정을 구성하는 전문 AI Agent야. 후보에 없는 장소를 절대 만들지 않는다.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    result = response.choices[0].message.content
    plan_data = json.loads(result)

    pdf_bytes = build_travel_pdf(
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        days=days,
        weather_info=weather_info,
        budget_plan=budget_plan,
        plan_data=plan_data,
        candidates=candidates,
    )

    return {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "budget": budget,
        "preference": preference,
        "weather_info": weather_info,
        "budget_plan": budget_plan,
        "candidates": candidates,
        "plan_data": plan_data,
        "pdf_bytes": pdf_bytes,
    }


st.markdown('<div class="main-title">여행 계획 AI Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">날씨, 예산, 실제 장소 데이터를 반영해 맞춤형 여행 일정을 생성합니다.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 여행 조건 입력")
    st.caption("조건을 입력한 뒤 여행 계획을 생성하세요.")

    with st.form("travel_form"):
        destination = st.text_input("여행지", placeholder="예: 서울 명동, 부산 해운대, 진주")

        today = date.today()
        default_start = today
        default_end = today + timedelta(days=2)

        trip_range = st.date_input(
            "여행 기간",
            value=(default_start, default_end),
            min_value=today,
        )

        if isinstance(trip_range, tuple) and len(trip_range) == 2:
            start_date, end_date = trip_range
            days = (end_date - start_date).days + 1
        else:
            start_date = today
            end_date = today
            days = 1

        budget = st.text_input("예산", placeholder="예: 35만원, 500000원")
        preference = st.text_input("여행 취향", placeholder="예: 맛집, 카페, 관광지")

        submitted = st.form_submit_button("여행 계획 생성", use_container_width=True)

    st.divider()
    st.caption("생성된 일정은 PDF로 다운로드할 수 있습니다.")

if submitted:
    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY가 설정되어 있지 않습니다. Streamlit Secrets 또는 .env 파일을 확인해 주세요.")
    elif not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        st.error("NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 필요합니다. Streamlit Secrets를 확인해 주세요.")
    elif not destination:
        st.warning("여행지를 입력해 주세요.")
    elif not budget:
        st.warning("예산을 입력해 주세요.")
    elif not preference:
        st.warning("여행 취향을 입력해 주세요.")
    elif days < 1:
        st.warning("여행 기간을 올바르게 선택해 주세요.")
    else:
        with st.spinner("AI가 여행 계획을 생성 중입니다..."):
            try:
                st.session_state["travel_result"] = generate_travel_plan(
                    destination=destination,
                    start_date=start_date,
                    end_date=end_date,
                    days=days,
                    budget=budget,
                    preference=preference,
                )
            except json.JSONDecodeError:
                st.error("AI 응답을 처리하는 중 오류가 발생했습니다. 다시 시도해 주세요.")
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

if "travel_result" not in st.session_state:
    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("### 시작하기")
        st.write("왼쪽 사이드바에서 여행 조건을 입력하면 여행 계획이 생성됩니다.")
        st.info("현재 앱은 날씨 API, 네이버 지역 검색 API, OpenAI API를 조합해 일정을 생성합니다.")

    with right:
        st.markdown(
            """
            <div class="section-card">
                <h3>앱 기능</h3>
                <p>• 여행 날짜 기반 날씨 반영</p>
                <p>• 네이버 지역 검색 기반 실제 장소 후보 사용</p>
                <p>• 한국 물가 기준 예산 분석</p>
                <p>• PDF 여행 일정표 다운로드</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    result = st.session_state["travel_result"]

    st.markdown(
        f"""
        <div class="download-box">
            <h3>여행 계획이 완성되었습니다</h3>
            <p>{result["destination"]} / {result["start_date"]} ~ {result["end_date"]} / 총 {result["days"]}일</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.download_button(
        label="PDF 여행 일정표 다운로드",
        data=result["pdf_bytes"],
        file_name=f'{result["destination"].replace(" ", "_")}_travel_plan.pdf',
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )

    st.markdown("## 핵심 요약")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    budget_plan = result["budget_plan"]

    with metric_col1:
        render_metric_card("여행 기간", f'{result["days"]}일', f'{result["start_date"]} ~ {result["end_date"]}')

    with metric_col2:
        render_metric_card("총 예산", format_won(budget_plan["총 예산"]), "사용자 입력 기준")

    with metric_col3:
        render_metric_card("1일 평균", format_won(budget_plan["1일 평균 예산"]), "하루 사용 가능 예산")

    with metric_col4:
        render_metric_card("예산 유형", budget_plan["예산 유형"], budget_plan["예산 코멘트"])

    with st.expander("날씨 정보 보기"):
        st.text(result["weather_info"])

    with st.expander("한국 물가 보정 기준 보기"):
        st.text(get_korea_price_guide())

    render_travel_plan(
        result["plan_data"],
        result["candidates"],
        result["budget_plan"],
        result["destination"],
    )