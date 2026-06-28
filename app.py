import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("여행 계획 AI Agent")
st.write("여행 조건을 입력하면 AI가 맞춤형 여행 일정을 생성합니다.")

destination = st.text_input("여행지")
days = st.number_input("여행 기간", min_value=1, max_value=10, value=2)
budget = st.text_input("예산")
preference = st.text_input("여행 취향")

if st.button("여행 계획 생성"):
    prompt = f"""
    너는 전문 여행 플래너 AI Agent야.

    아래 조건에 맞춰 여행 계획을 작성해줘.

    여행지: {destination}
    여행 기간: {days}일
    예산: {budget}
    여행 취향: {preference}

    출력 형식:
    1. 전체 여행 요약
    2. 날짜별 일정
    3. 예상 예산
    4. 추천 음식
    5. 준비물
    6. 비 올 때 대체 일정
    """

    with st.spinner("AI가 여행 계획을 생성 중입니다..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 여행 계획을 세워주는 전문 AI Agent야."},
                {"role": "user", "content": prompt}
            ]
        )

        result = response.choices[0].message.content
        st.subheader("AI 여행 계획")
        st.write(result)