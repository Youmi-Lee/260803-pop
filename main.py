import re
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="전국 영유아 비율 지도", layout="wide")
st.title("🗺️ 전국 영유아 비율 지도")
st.caption("시군구별 0~4세 인구 비율 (행정안전부 주민등록 인구) · 연도별 변화 애니메이션")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    # '코드' 열은 앞자리 0이 사라지지 않게 글자로 읽습니다
    return pd.read_csv(POP_URL, dtype={"코드": str})


@st.cache_data(show_spinner="지도 경계를 불러오는 중입니다...")
def load_geojson():
    return requests.get(GEO_URL, timeout=30).json()


df = load_population()
geojson = load_geojson()

# 1. '계_'로 시작하는 나이 열만 (남_·여_ 열까지 더하면 두 배가 됩니다)
total_cols = [c for c in df.columns if c.startswith("계_")]


def age_of(col):
    m = re.match(r"계_(\d+)세", col)
    return int(m.group(1)) if m else None


# 2. 그중 0~4세 열만 ('계_0세' ~ '계_4세')
young_cols = [c for c in total_cols if age_of(c) is not None and 0 <= age_of(c) <= 4]

# 3. 동 단위로 전체 인구·영유아(0~4세) 인구 계산 (모든 연도 대상)
df["전체인구"] = df[total_cols].sum(axis=1)
df["영유아인구"] = df[young_cols].sum(axis=1)

# 4. '코드' 앞 5자리 = 시군구 코드 → 연도·시군구별로 묶어 비율 계산
df["시군구코드"] = df["코드"].str[:5]
grouped = (
    df.groupby(["연도", "시군구코드"])[["전체인구", "영유아인구"]]
    .sum()
    .reset_index()
)
grouped["영유아비율"] = (grouped["영유아인구"] / grouped["전체인구"] * 100).round(2)

# 경계 파일에서 코드 → 시군구·시도 이름 짝 만들기
names = pd.DataFrame([
    {
        "시군구코드": str(f["properties"]["코드"]),
        "시군구": f["properties"]["시군구"],
        "시도": f["properties"]["시도"],
    }
    for f in geojson["features"]
])
merged = grouped.merge(names, on="시군구코드", how="left")
merged = merged.sort_values("연도")
merged["연도"] = merged["연도"].astype(str)  # 애니메이션 프레임 라벨용

# 5. 5단계 색 구간 (0~4세 비율은 보통 2~5% 내외이므로 구간을 그에 맞게 설정)
#    실제 데이터 분포를 보고 필요하면 이 값을 조정하세요.
BINS = [0, 2.5, 3.5, 4.5, 5.5, 100]
LABELS = ["2.5% 미만", "2.5~3.5%", "3.5~4.5%", "4.5~5.5%", "5.5% 이상"]
COLORS = {
    "2.5% 미만": "#deebf7",
    "2.5~3.5%": "#9ecae1",
    "3.5~4.5%": "#4292c6",
    "4.5~5.5%": "#2171b5",
    "5.5% 이상": "#084594",
}
merged["단계"] = pd.cut(merged["영유아비율"], bins=BINS, labels=LABELS, right=False)

# 6. 단계구분도 그리기 (연도를 애니메이션 프레임으로 사용)
fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="단계",
    animation_frame="연도",
    category_orders={
        "단계": LABELS,
        "연도": sorted(merged["연도"].unique()),
    },
    color_discrete_map=COLORS,
    hover_name="시군구",
    hover_data={"영유아비율": True, "시도": True, "시군구코드": False, "단계": False},
    labels={"영유아비율": "0~4세 비율(%)"},
)
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=700,
    legend_title_text="0~4세 인구 비율",
)
# 애니메이션 프레임 전환 속도 조절 (선택 사항)
fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 800
fig.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 300

st.plotly_chart(fig, width="stretch")

# 7. 특정 연도를 골라 순위표를 보고 싶을 때 사용하는 선택 슬라이더
years = sorted(merged["연도"].unique())
selected_year = st.select_slider("순위표에 사용할 연도 선택", options=years, value=years[-1])
year_df = merged[merged["연도"] == selected_year]

c1, c2 = st.columns(2)
cols = ["시도", "시군구", "영유아비율"]
with c1:
    st.subheader(f"🔵 영유아 비율 높은 곳 10 ({selected_year}년)")
    st.dataframe(year_df.nlargest(10, "영유아비율")[cols].reset_index(drop=True))
with c2:
    st.subheader(f"⚪ 영유아 비율 낮은 곳 10 ({selected_year}년)")
    st.dataframe(year_df.nsmallest(10, "영유아비율")[cols].reset_index(drop=True))
