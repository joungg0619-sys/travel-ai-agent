import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os
import requests

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_weather(destination):
    geo_url = "https://geocoding-api.open-meteo.com/v1/search"
    geo_params = {
        "name": destination,
        "count": 1,
        "language": "ko",
        "format": "json"
    }

    geo_res = requests.get(geo_url, params=geo_params)
    geo_data = geo_res.json()

    if "results" not in geo_data:
        return "날씨 정보를 가져올 수 없습니다. 여행지 이름을 더 정확히 입력해 주세요."

    location = geo_data["results"][0]
    lat = location["latitude"]
    lon = location["longitude"]

    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": 7,
        "timezone": "auto"
    }

    weather_res = requests.get(weather_url, params=weather_params)
    weather_data = weather_res.json()

    daily = weather_data["daily"]

    summary = "날씨 예보:\n"
    for i in range(len(daily["time"])):
        summary += f"- {daily['time'][i]}: 최저 {daily['temperature_2m_min'][i]}°C / 최고 {daily['temperature_2m_max'][i]}°C / 강수확률 {daily['precipitation_probability_max'][i]}%\n"

    return summary

st.title("여행 계획 AI Agent")
st.write("여행 조건을 입력하면 AI가 맞춤형 여행 일정을 생성합니다.")

destination = st.text_input("여행지")
days = st.number_input("여행 기간", min_value=1, max_value=10, value=2)
budget = st.text_input("예산")
preference = st.text_input("여행 취향")

if st.button("여행 계획 생성"):
    weather_info = get_weather(destination)

    st.subheader("여행지 날씨 정보")
    st.write(weather_info)

    prompt = f"""
    너는 전문 여행 플래너 AI Agent야.

    아래 조건과 날씨 정보를 반영해서 여행 계획을 작성해줘.

    여행지: {destination}
    여행 기간: {days}일
    예산: {budget}
    여행 취향: {preference}

    날씨 정보:
    {weather_info}

    작성 조건:
    - 강수확률이 높은 날은 실내 관광지, 카페, 박물관, 쇼핑몰 위주로 추천해줘.
    - 날씨가 좋은 날은 야외 관광지, 자연 경관, 산책 코스를 추천해줘.
    - 예산을 초과하지 않도록 현실적인 일정으로 구성해줘.
    - 이동 동선이 너무 복잡하지 않게 구성해줘.

    출력 형식:
    1. 전체 여행 요약
    2. 날씨 반영 전략
    3. 날짜별 일정
    4. 예상 예산
    5. 추천 음식
    6. 준비물
    7. 비 올 때 대체 일정
    """

    with st.spinner("AI가 여행 계획을 생성 중입니다..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 날씨와 예산을 반영해서 여행 계획을 세워주는 전문 AI Agent야."},
                {"role": "user", "content": prompt}
            ]
        )

        result = response.choices[0].message.content
        st.subheader("AI 여행 계획")
        st.write(result)