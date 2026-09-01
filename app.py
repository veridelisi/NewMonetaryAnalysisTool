from datetime import date, timedelta
from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="TCMB Likidite Analizi",
    page_icon="🏦",
    layout="wide",
)

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"

SERIES = [
    "TP.AB.A02",
    "TP.AB.A03",
    "TP.AB.A08",
    "TP.AB.A10",
    "TP.AB.A17",
    "TP.AB.A18",
    "TP.AB.A21",
    "TP.AB.A24",
    "TP.AB.A25",
    "TP.AB.A22",
]

SERIES_RENAME = {
    "TP_AB_A02": "Foreign Assets",
    "TP_AB_A03": "Domestic Assets",
    "TP_AB_A08": "Revaluation",
    "TP_AB_A10": "Total Foreign Liabilities",
    "TP_AB_A17": "Currency Issued",
    "TP_AB_A18": "Banking Reserves",
    "TP_AB_A21": "Extra Funds",
    "TP_AB_A24": "OMO",
    "TP_AB_A25": "Deposits of Public Sector",
    "TP_AB_A22": "Deposits of Non-Bank Sector",
}

TURKISH_NAMES = {
    "Net Foreign Assets": "Net Dış Varlıklar",
    "Domestic Assets": "İç Varlıklar",
    "Revaluation": "Değerleme Hesabı",
    "Currency Issued": "Emisyon",
    "Extra Funds": "Bütçe Dışı Fonlar",
    "Deposits of Public Sector": "Kamu Mevduatı",
    "Deposits of Non-Bank Sector": "Banka Dışı Kesim Mevduatı",
    "OMO": "APİ",
    "Liquidity": "Likidite Durumu",
    "Banking Reserves": "Bankalar Mevduatı",
    "Calculated Banking Reserves": "Hesaplanan Bankalar Mevduatı",
    "Control Difference": "Kontrol Farkı",
}

COMPONENTS = [
    "Net Foreign Assets",
    "Domestic Assets",
    "Revaluation",
    "Currency Issued",
    "Extra Funds",
    "Deposits of Public Sector",
    "Deposits of Non-Bank Sector",
]

SIGNS = {
    "Net Foreign Assets": 1,
    "Domestic Assets": 1,
    "Revaluation": 1,
    "Currency Issued": -1,
    "Extra Funds": -1,
    "Deposits of Public Sector": -1,
    "Deposits of Non-Bank Sector": -1,
}

COLORS = {
    "Net Foreign Assets": "#4C72B0",
    "Domestic Assets": "#55A868",
    "Revaluation": "#C44E52",
    "Currency Issued": "#8172B2",
    "Extra Funds": "#CCB974",
    "Deposits of Public Sector": "#64B5CD",
    "Deposits of Non-Bank Sector": "#DD8452",
}


def format_turkish_number(value, _position=None):
    """Sayilari 1.234,5 biciminde gosterir."""
    formatted = f"{value:,.1f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def get_api_key():
    try:
        return st.secrets["EVDS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_evds3(start_date, end_date, api_key):
    url = (
        f"{BASE_URL}series={'-'.join(SERIES)}"
        f"&startDate={start_date}&endDate={end_date}&type=json"
    )
    try:
        response = requests.get(
            url,
            headers={"key": api_key},
            timeout=45,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(
            "EVDS servisine bağlanılamadı. Tarihleri ve API anahtarını kontrol edin."
        ) from error

    try:
        payload = response.json()
        items = payload["items"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("EVDS beklenen biçimde veri döndürmedi.") from error

    if not items:
        raise ValueError("Seçilen tarih aralığında veri bulunamadı.")

    return pd.DataFrame(items)


def prepare_data(raw):
    date_candidates = [
        column
        for column in raw.columns
        if column.strip().lower() in ("tarih", "date")
    ]
    if not date_candidates:
        raise ValueError(
            "EVDS yanıtında tarih sütunu bulunamadı. "
            f"Gelen sütunlar: {', '.join(raw.columns)}"
        )

    date_column = date_candidates[0]
    df = raw.rename(columns={date_column: "Date", **SERIES_RENAME}).copy()

    missing = [name for name in SERIES_RENAME.values() if name not in df.columns]
    if missing:
        raise ValueError(
            "EVDS yanıtında beklenen seriler bulunamadı: " + ", ".join(missing)
        )

    df = df[["Date", *SERIES_RENAME.values()]]
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    value_columns = list(SERIES_RENAME.values())
    df[value_columns] = df[value_columns].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["Date", *value_columns]).sort_values("Date")
    df = df.drop_duplicates(subset="Date", keep="last").set_index("Date")

    if len(df) < 2:
        raise ValueError(
            "Birinci farkın hesaplanabilmesi için en az iki iş gününe ait veri gerekir."
        )

    df["Net Foreign Assets"] = (
        df["Foreign Assets"] - df["Total Foreign Liabilities"]
    )
    df = df.drop(columns=["Foreign Assets", "Total Foreign Liabilities"])

    net_foreign_assets = df.pop("Net Foreign Assets")
    df.insert(0, "Net Foreign Assets", net_foreign_assets)

    diff = df.diff().iloc[1:].copy()
    diff["Liquidity"] = (
        diff["Net Foreign Assets"]
        + diff["Domestic Assets"]
        + diff["Revaluation"]
        - diff["Currency Issued"]
        - diff["Extra Funds"]
        - diff["Deposits of Public Sector"]
        - diff["Deposits of Non-Bank Sector"]
    )

    # TCMB analitik bilancosunda pasif tarafta izlenen APİ'nin isaretini ceviriyoruz.
    diff["OMO"] = -diff["OMO"]
    diff["Calculated Banking Reserves"] = diff["Liquidity"] + diff["OMO"]
    diff["Control Difference"] = (
        diff["Calculated Banking Reserves"] - diff["Banking Reserves"]
    )
    return diff


def scale_data(df, unit):
    divisor = 1_000_000 if unit == "Milyar TL" else 1_000
    return df / divisor


def create_main_chart(df, unit):
    x = np.arange(len(df))
    labels = df.index.strftime("%d-%m-%Y")

    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.bar(
        x,
        df["Liquidity"],
        width=0.55,
        label="Likidite Durumu",
        color="#9DC3E6",
        edgecolor="black",
        linewidth=0.6,
        zorder=2,
    )
    ax.bar(
        x,
        df["OMO"],
        width=0.55,
        label="APİ",
        color="#ED7D31",
        edgecolor="black",
        linewidth=0.6,
        zorder=3,
    )
    ax.plot(
        x,
        df["Banking Reserves"],
        color="black",
        linestyle="--",
        marker="o",
        markersize=5,
        linewidth=1.4,
        label="Bankalar Mevduatı",
        zorder=4,
    )

    ax.axhline(0, color="black", linewidth=0.8)
    ax.yaxis.set_major_formatter(FuncFormatter(format_turkish_number))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel(unit)
    ax.set_title(
        "Likidite Durumu, Açık Piyasa İşlemleri ve Bankalar Mevduatı (Günlük)",
        fontsize=13,
    )
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=3,
        frameon=False,
        fontsize=10,
    )
    fig.tight_layout()
    return fig


def create_components_chart(df, unit):
    x = np.arange(len(df))
    labels = df.index.strftime("%d-%m-%Y")
    positive_bottom = np.zeros(len(df))
    negative_bottom = np.zeros(len(df))

    fig, ax = plt.subplots(figsize=(12, 6.5))
    for column in COMPONENTS:
        values = df[column].to_numpy() * SIGNS[column]
        bottom = np.where(values >= 0, positive_bottom, negative_bottom)
        ax.bar(
            x,
            values,
            width=0.7,
            bottom=bottom,
            label=TURKISH_NAMES[column],
            color=COLORS[column],
            edgecolor="black",
            linewidth=0.4,
            zorder=2,
        )
        positive_bottom = np.where(
            values >= 0, positive_bottom + values, positive_bottom
        )
        negative_bottom = np.where(
            values < 0, negative_bottom + values, negative_bottom
        )

    ax.axhline(0, color="black", linewidth=0.8)
    ax.yaxis.set_major_formatter(FuncFormatter(format_turkish_number))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel(unit)
    ax.set_title("Likidite Bileşenleri (Günlük)", fontsize=13)
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    fig.tight_layout()
    return fig


def to_excel(df):
    output = BytesIO()
    export_df = df.rename(columns=TURKISH_NAMES).copy()
    export_df.index.name = "Tarih"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="Likidite Analizi")
    output.seek(0)
    return output.getvalue()


st.title("🏦 TCMB Analitik Bilanço: Likidite Analizi")
st.caption(
    "TCMB analitik bilanço verilerinden günlük likidite durumu, açık piyasa "
    "işlemleri ve bankalar mevduatı değişimini hesaplar."
)

with st.sidebar:
    st.header("Analiz Ayarları")
    default_end = date.today()
    default_start = default_end - timedelta(days=14)
    start_date = st.date_input(
        "Başlangıç tarihi",
        value=default_start,
        format="DD/MM/YYYY",
    )
    end_date = st.date_input(
        "Bitiş tarihi",
        value=default_end,
        format="DD/MM/YYYY",
    )
    unit = st.radio("Gösterim birimi", ["Milyar TL", "Milyon TL"], index=0)
    run_analysis = st.button("Verileri Getir", type="primary", use_container_width=True)

    st.divider()
    st.caption("Veri kaynağı: TCMB EVDS3")

api_key = get_api_key()
if not api_key:
    st.error(
        "EVDS API anahtarı tanımlanmamış. Streamlit Secrets bölümüne "
        '`EVDS_API_KEY = "anahtarınız"` satırını ekleyin.'
    )
    st.stop()

if start_date > end_date:
    st.error("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
    st.stop()

if run_analysis:
    with st.spinner("EVDS verileri alınıyor ve hesaplamalar yapılıyor..."):
        try:
            raw_data = fetch_evds3(
                start_date.strftime("%d-%m-%Y"),
                end_date.strftime("%d-%m-%Y"),
                api_key,
            )
            calculated_data = prepare_data(raw_data)
            display_data = scale_data(calculated_data, unit)
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
            st.stop()

    st.session_state["calculated_data"] = calculated_data
    st.session_state["display_data"] = display_data
    st.session_state["unit"] = unit
    st.session_state["period"] = (start_date, end_date)

if "display_data" not in st.session_state:
    st.info("Analize başlamak için tarih aralığını seçip **Verileri Getir** düğmesine basın.")
    st.stop()

display_data = st.session_state["display_data"]
calculated_data = st.session_state["calculated_data"]
active_unit = st.session_state["unit"]
period_start, period_end = st.session_state["period"]

st.success(
    f"{period_start.strftime('%d.%m.%Y')}–{period_end.strftime('%d.%m.%Y')} "
    f"dönemi için {len(display_data)} günlük değişim hesaplandı."
)

latest = display_data.iloc[-1]
metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Son Gün Likidite", format_turkish_number(latest["Liquidity"]))
metric_2.metric("Son Gün APİ", format_turkish_number(latest["OMO"]))
metric_3.metric(
    "Bankalar Mevduatı",
    format_turkish_number(latest["Banking Reserves"]),
)
metric_4.metric(
    "Kontrol Farkı",
    format_turkish_number(latest["Control Difference"]),
)
st.caption(f"Özet değerlerin birimi: {active_unit}")

tab_1, tab_2, tab_3, tab_4 = st.tabs(
    ["Genel Görünüm", "Likidite Bileşenleri", "Veri Tablosu", "Yöntem"]
)

with tab_1:
    main_figure = create_main_chart(display_data, active_unit)
    st.pyplot(main_figure, use_container_width=True)
    plt.close(main_figure)
    st.caption(
        "Likidite Durumu ve APİ sütunları aynı tarih konumunda üst üste "
        "çizilmektedir; kesikli çizgi bankalar mevduatındaki günlük değişimi gösterir."
    )

with tab_2:
    components_figure = create_components_chart(display_data, active_unit)
    st.pyplot(components_figure, use_container_width=True)
    plt.close(components_figure)
    st.caption(
        "Emisyon, bütçe dışı fonlar, kamu mevduatı ve banka dışı kesim mevduatı "
        "likiditeyi azaltan yöndeki işaretleriyle gösterilmiştir."
    )

with tab_3:
    table_columns = [
        "Liquidity",
        "OMO",
        "Banking Reserves",
        "Calculated Banking Reserves",
        "Control Difference",
        *COMPONENTS,
    ]
    table = display_data[table_columns].rename(columns=TURKISH_NAMES).copy()
    table.index = table.index.strftime("%d-%m-%Y")
    table.index.name = "Tarih"
    st.dataframe(table.style.format(format_turkish_number), use_container_width=True)
    st.download_button(
        "Excel Olarak İndir",
        data=to_excel(calculated_data),
        file_name=(
            f"TCMB_Likidite_Analizi_"
            f"{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with tab_4:
    st.markdown(
        """
### Hesaplama yöntemi

Günlük likidite durumu, TCMB analitik bilançosundaki ilgili kalemlerin birinci
farkları kullanılarak hesaplanır:

**Likidite Durumu = Net Dış Varlıklar + İç Varlıklar + Değerleme Hesabı
− Emisyon − Bütçe Dışı Fonlar − Kamu Mevduatı − Banka Dışı Kesim Mevduatı**

TCMB analitik bilançosunda pasif tarafta gösterilen açık piyasa işlemlerinin
işareti çevrilir. Kontrol ilişkisi şöyledir:

**Hesaplanan Bankalar Mevduatı = Likidite Durumu + APİ**

**Kontrol Farkı = Hesaplanan Bankalar Mevduatı − Gerçekleşen Bankalar Mevduatı**

Kaynak: Engin Yılmaz, *A New Monetary Analysis Tool: The Daily Liquidity Dataset*,
Ekonomista, 2020; TCMB EVDS3 Analitik Bilanço verileri.
        """
    )
