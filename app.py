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


def mask_secret(value):
    if not value:
        return "없음"

    if len(value) <= 8:
        return "설정됨"

    return value[:4] + "..." + value[-4:]


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


def make_naver_place_link(place):
    # 네이버지도는 장소명 + 상세주소보다 장소명 단독 검색이 더 안정적인 경우가 많음
    title = place.get("title", "")
    return make_naver_map_search_link(title)


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


def get_weather_location(destination):
    broad_region = extract_broad_region(destination)

    if broad_region:
        return broad_region

    tokens = destination.split()

    if tokens:
        return tokens[0]

    return destination


def get_weather(destination, start_date, end_date):
    weather_location = get_weather_location(destination)

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

    if "results" not in geo_data:
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
            place["map_link"] = make_naver_place_link(place)
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


def render_naver_api_debug(destination):
    st.subheader("네이버 API 진단 모드")

    st.write("현재 버전은 Streamlit Secrets를 먼저 읽고, 값의 앞뒤 공백을 제거합니다.")

    st.write(f"OPENAI_API_KEY: {mask_secret(OPENAI_API_KEY)}")
    st.write(f"NAVER_CLIENT_ID: {mask_secret(NAVER_CLIENT_ID)}")
    st.write(f"NAVER_CLIENT_SECRET: {mask_secret(NAVER_CLIENT_SECRET)}")

    test_query = st.text_input(
        "네이버 API 테스트 검색어",
        value=destination if destination else "진주",
    )

    if st.button("네이버 API 연결 테스트"):
        raw = fetch_naver_local_raw(test_query, display=5)

        st.write("요청 URL: https://openapi.naver.com/v1/search/local.json")
        st.write(f"검색어: {test_query}")
        st.write(f"상태 코드: {raw.get('status_code')}")

        if raw["ok"]:
            st.success("네이버 지역 검색 API 호출 성공")

            data = raw["data"] or {}
            items = data.get("items", [])

            st.write(f"검색 결과 개수: {len(items)}개")
            st.json(data)
        else:
            st.error("네이버 지역 검색 API 호출 실패")

            error_text = raw.get("error") or raw.get("text") or "오류 내용 없음"
            st.write(error_text)

            st.info(
                "401이면 Client ID/Secret 값이 잘못되었거나, 값에 공백/줄바꿈이 섞였을 가능성이 큽니다. "
                "403이면 해당 애플리케이션에 검색 API 권한이 없을 가능성이 높습니다."
            )


def render_verified_candidates(candidates, diagnostics, used_relaxed_filter):
    st.subheader("검증된 네이버 지역 장소 후보")

    if used_relaxed_filter:
        st.warning(
            "엄격한 지역 필터 적용 시 후보가 없어, 지역 필터를 완화해서 후보를 가져왔습니다. "
            "결과가 넓은 지역 기준으로 나올 수 있습니다."
        )
    else:
        st.write("아래 후보는 네이버 지역 검색 API 결과를 지역 기준으로 필터링한 목록입니다.")

    with st.expander("네이버 검색 진단 결과 보기"):
        st.write("각 검색어별 API 호출 결과와 필터링 전후 후보 개수입니다.")
        st.json(diagnostics)

    if not candidates:
        st.warning("검증된 장소 후보가 없습니다. 네이버 API 진단 모드에서 상태 코드를 확인해 주세요.")
        return

    cols = st.columns(2)

    for idx, place in enumerate(candidates[:12]):
        with cols[idx % 2]:
            st.markdown(f"**{place['id']} · {place['title']}**")
            st.caption(place["category"])
            st.write(place["road_address"] or place["address"])
            st.link_button("네이버지도에서 보기", place["map_link"])


def render_travel_plan(plan_data, candidates):
    st.markdown("## 전체 여행 요약")
    st.write(plan_data.get("summary", ""))

    st.markdown("## 날씨 반영 전략")
    st.write(plan_data.get("weather_strategy", ""))

    st.markdown("## 예산 사용 전략")
    st.write(plan_data.get("budget_strategy", ""))

    st.markdown("## 날짜별 일정")

    daily_schedule = plan_data.get("daily_schedule", [])
    used_place_ids = []

    for day in daily_schedule:
        date_text = day.get("date", "")
        title = day.get("day_title", "")
        st.markdown(f"### {title} - {date_text}")

        items = day.get("items", [])

        for item in items:
            time_text = item.get("time", "")
            place_id = item.get("place_id", "")
            description = item.get("description", "")
            cost = item.get("estimated_cost", "")

            place = get_candidate_by_id(candidates, place_id)

            if place:
                used_place_ids.append(place_id)
                st.markdown(
                    f"- **{time_text}**: "
                    f"[{place['title']}]({place['map_link']}) - "
                    f"{description} "
                    f"`예상 비용: {cost}`"
                )
            else:
                st.markdown(
                    f"- **{time_text}**: {description} "
                    f"`예상 비용: {cost}`"
                )

                if place_id:
                    st.caption(f"검증되지 않은 장소 ID가 제외되었습니다: {place_id}")

    st.markdown("## 예상 상세 예산")
    st.write(plan_data.get("estimated_budget_detail", ""))

    st.markdown("## 추천 음식")
    for food in plan_data.get("recommended_foods", []):
        st.markdown(f"- {food}")

    st.markdown("## 준비물")
    for item in plan_data.get("packing_list", []):
        st.markdown(f"- {item}")

    st.markdown("## 비 올 때 대체 일정")
    for item in plan_data.get("rainy_day_alternatives", []):
        st.markdown(f"- {item}")

    st.markdown("## 절약 팁")
    for tip in plan_data.get("saving_tips", []):
        st.markdown(f"- {tip}")

    recommended_place_ids = plan_data.get("recommended_place_ids", [])

    all_link_ids = []

    for place_id in recommended_place_ids:
        if place_id not in all_link_ids:
            all_link_ids.append(place_id)

    for place_id in used_place_ids:
        if place_id not in all_link_ids:
            all_link_ids.append(place_id)

    valid_places = [
        get_candidate_by_id(candidates, place_id)
        for place_id in all_link_ids
        if get_candidate_by_id(candidates, place_id)
    ]

    if valid_places:
        st.markdown("## 추천 장소 네이버지도 링크")
        st.write("아래 버튼을 누르면 네이버지도에서 위치, 리뷰, 메뉴, 가격 정보를 확인할 수 있습니다.")

        cols = st.columns(3)

        for idx, place in enumerate(valid_places):
            with cols[idx % 3]:
                st.link_button(place["title"], place["map_link"])


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
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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

    story.append(pdf_paragraph("9. 준비물", h1_style))
    for item in plan_data.get("packing_list", []):
        story.append(pdf_paragraph(f"- {item}", body_style))

    story.append(pdf_paragraph("10. 비 올 때 대체 일정", h1_style))
    for item in plan_data.get("rainy_day_alternatives", []):
        story.append(pdf_paragraph(f"- {item}", body_style))

    story.append(pdf_paragraph("11. 절약 팁", h1_style))
    for tip in plan_data.get("saving_tips", []):
        story.append(pdf_paragraph(f"- {tip}", body_style))

    recommended_place_ids = plan_data.get("recommended_place_ids", [])

    if recommended_place_ids:
        story.append(pdf_paragraph("12. 네이버지도 확인 링크", h1_style))
        story.append(pdf_paragraph("장소명은 PDF에서도 클릭 가능한 링크로 삽입했습니다.", body_style))

        for place_id in recommended_place_ids:
            place = get_candidate_by_id(candidates, place_id)

            if place:
                story.append(pdf_place_link(place, body_style))

    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()


st.title("여행 계획 AI Agent")
st.write("여행 조건을 입력하면 AI가 날씨, 예산, 네이버 지역 검색 결과를 검증해 맞춤형 여행 일정을 생성합니다.")

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

    if days < 1:
        st.warning("종료일은 시작일보다 늦거나 같아야 합니다.")
        days = 1
    else:
        st.caption(f"선택한 여행 기간: {start_date} ~ {end_date} / 총 {days}일")
else:
    start_date = today
    end_date = today
    days = 1
    st.info("여행 시작일과 종료일을 모두 선택해 주세요.")

budget = st.text_input("예산", placeholder="예: 35만원, 500000원")
preference = st.text_input("여행 취향", placeholder="예: 맛집, 카페, 관광지")

st.subheader("빠른 네이버지도 검색")

if destination:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.link_button(
            "관광지 검색",
            make_naver_map_search_link(f"{destination} 관광지"),
        )

    with col2:
        st.link_button(
            "맛집 검색",
            make_naver_map_search_link(f"{destination} 맛집"),
        )

    with col3:
        st.link_button(
            "카페 검색",
            make_naver_map_search_link(f"{destination} 카페"),
        )
else:
    st.info("여행지를 입력하면 네이버지도 검색 버튼이 표시됩니다.")

with st.expander("네이버 API 진단 모드 열기"):
    render_naver_api_debug(destination)


if st.button("여행 계획 생성"):
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
        total_budget = parse_budget_to_won(budget)
        budget_plan = calculate_budget_plan(total_budget, days)

        if budget_plan is None:
            st.warning("예산 형식을 인식하지 못했습니다. 예: 35만원, 500000원")
        else:
            weather_info = get_weather(destination, start_date, end_date)
            price_guide = get_korea_price_guide()

            strict_candidates, strict_diagnostics = get_verified_place_candidates(
                destination,
                preference,
                use_region_filter=True,
            )

            used_relaxed_filter = False
            candidates = strict_candidates
            diagnostics = strict_diagnostics

            if not strict_candidates:
                relaxed_candidates, relaxed_diagnostics = get_verified_place_candidates(
                    destination,
                    preference,
                    use_region_filter=False,
                )

                if relaxed_candidates:
                    candidates = relaxed_candidates
                    diagnostics = {
                        "strict_filter": strict_diagnostics,
                        "relaxed_filter": relaxed_diagnostics,
                    }
                    used_relaxed_filter = True

            candidates_text = format_candidates_for_prompt(candidates)

            st.subheader("여행지 날씨 정보")
            st.write(weather_info)

            st.subheader("예산 분석")
            st.write(f"총 예산: {format_won(budget_plan['총 예산'])}")
            st.write(f"1일 평균 예산: {format_won(budget_plan['1일 평균 예산'])}")
            st.write(f"예산 유형: {budget_plan['예산 유형']}")
            st.info(budget_plan["예산 코멘트"])

            budget_col1, budget_col2 = st.columns(2)

            with budget_col1:
                st.write(f"숙박비: {format_won(budget_plan['숙박비'])}")
                st.write(f"식비: {format_won(budget_plan['식비'])}")
                st.write(f"교통비: {format_won(budget_plan['교통비'])}")

            with budget_col2:
                st.write(f"관광/체험비: {format_won(budget_plan['관광/체험비'])}")
                st.write(f"예비비: {format_won(budget_plan['예비비'])}")

            with st.expander("한국 물가 보정 기준 보기"):
                st.text(price_guide)

            render_verified_candidates(candidates, diagnostics, used_relaxed_filter)

            if not candidates:
                st.stop()

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
            - recommended_place_ids도 반드시 후보 목록의 place_id만 사용해.
            - 후보 목록에 없는 장소는 절대 사용하지 마.
            - 음식 가격을 지나치게 낮게 잡지 마.
            - 한국 물가 보정 기준을 반드시 반영해.

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
              "packing_list": ["준비물 1", "준비물 2"],
              "rainy_day_alternatives": ["우천 시 대체 일정 1", "우천 시 대체 일정 2"],
              "saving_tips": ["절약 팁 1", "절약 팁 2"],
              "recommended_place_ids": ["P001", "P002", "P003"]
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

            with st.spinner("여행 계획을 생성 중입니다..."):
                try:
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

                    render_travel_plan(plan_data, candidates)

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

                    st.download_button(
                        label="PDF 여행 일정표 다운로드",
                        data=pdf_bytes,
                        file_name=f"{destination.replace(' ', '_')}_travel_plan.pdf",
                        mime="application/pdf",
                    )

                    st.subheader("추가 네이버지도 검색")
                    col4, col5, col6 = st.columns(3)

                    with col4:
                        st.link_button(
                            "숙소 검색",
                            make_naver_map_search_link(f"{destination} 숙소"),
                        )

                    with col5:
                        st.link_button(
                            "대중교통 검색",
                            make_naver_map_search_link(f"{destination} 대중교통"),
                        )

                    with col6:
                        st.link_button(
                            "실내 관광지 검색",
                            make_naver_map_search_link(f"{destination} 실내 관광지"),
                        )

                except json.JSONDecodeError:
                    st.error("AI 응답을 처리하는 중 오류가 발생했습니다. 다시 시도해 주세요.")
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")