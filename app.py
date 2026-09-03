"""TCMB Analitik Bilanço: Likidite Analizi

Hesaplama mantığı (DEĞİŞTİRİLMEMİŞTİR):

    Likidite Durumu
        = ΔNet Dış Varlıklar + ΔİçVarlıklar + ΔDeğerleme Hesabı
          − ΔDolaşımdaki Para − ΔFon Hesapları
          − ΔKamu Mevduatı − ΔBanka Dışı Kesim Mevduatı

    Net Dış Varlıklar = Dış Varlıklar − Toplam Dış Yükümlülükler

    Likidite Durumu + ΔNet APİ = ΔBankaların TCMB'deki Mevduatı

TP.AB.A24 (APİ) serisinin birinci farkı, analitik bilançodaki işaret
yapısı nedeniyle -1 ile çarpılır. Bu kural değiştirilmemiştir.
"""

from datetime import date, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# --------------------------------------------------------------------------
# Sayfa ayarları ve stil
# --------------------------------------------------------------------------

st.set_page_config(
    page_title="TCMB Likidite Analizi",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }
    div[data-testid="stMetric"] {
        background-color: #F7F9FB;
        border: 1px solid #E3E8EE;
        border-radius: 10px;
        padding: 0.9rem 0.9rem 0.6rem 0.9rem;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem;
        color: #4A5568;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.35rem;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    h1 {
        font-size: 1.65rem !important;
    }
    .method-box {
        background-color: #F0F4F8;
        border-left: 4px solid #2C5282;
        padding: 0.9rem 1.1rem;
        border-radius: 6px;
        font-size: 0.92rem;
        margin-bottom: 1rem;
    }
    @media (max-width: 640px) {
        h1 { font-size: 1.3rem !important; }
        div[data-testid="stMetricValue"] { font-size: 1.05rem; }
        .block-container { padding-left: 0.6rem; padding-right: 0.6rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Sabitler
# --------------------------------------------------------------------------

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
    "Currency Issued": "Dolaşımdaki Para",
    "Extra Funds": "Fon Hesapları",
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

# Bileşenlerin Likidite Durumu kimliğine katkı işareti (DEĞİŞTİRİLMEMİŞTİR)
SIGNS = {
    "Net Foreign Assets": 1,
    "Domestic Assets": 1,
    "Revaluation": 1,
    "Currency Issued": -1,
    "Extra Funds": -1,
    "Deposits of Public Sector": -1,
    "Deposits of Non-Bank Sector": -1,
}

COMPONENT_COLORS = {
    "Net Foreign Assets": "#2C5282",
    "Domestic Assets": "#2F855A",
    "Revaluation": "#805AD5",
    "Currency Issued": "#DD6B20",
    "Extra Funds": "#B7791F",
    "Deposits of Public Sector": "#C53030",
    "Deposits of Non-Bank Sector": "#B83280",
}

POSITIVE_COLOR = "#2F855A"   # likidite sağlayıcı: yeşil
NEGATIVE_COLOR = "#C53030"   # likidite çekici: kırmızı
RESERVE_COLOR = "#1A202C"    # bankalar mevduatı: koyu lacivert/siyah

FREQ_LABELS = ["Günlük", "Haftalık", "Aylık", "Yıllık"]

RESIDUAL_WARN_THRESHOLD_MILLION = 50.0  # milyon TL cinsinden tolerans

METHOD_SOURCE_URL = (
    "https://ekonomista.pte.pl/pdf-155448-82266"
    "?filename=A%20New%20Monetary%20Analysis.pdf"
)


# --------------------------------------------------------------------------
# Yardımcı biçimlendirme fonksiyonları
# --------------------------------------------------------------------------

def format_tr_number(value, decimals=1):
    """Sayıyı 1.234,5 bicimine cevirir (binlik nokta, ondalik virgul)."""
    if pd.isna(value):
        return "—"
    formatted = f"{abs(value):,.{decimals}f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    sign = "+" if value > 0 else ("−" if value < 0 else "")
    return f"{sign}{formatted}"


def format_tr_with_unit(value, unit_label, decimals=1):
    return f"{format_tr_number(value, decimals)} {unit_label}"


def unit_label_for(unit):
    return "milyar TL" if unit == "Milyar TL" else "milyon TL"


# --------------------------------------------------------------------------
# Veri çekme (Parçalara bölünmüş ve önbelleğe alınmış)
# --------------------------------------------------------------------------

def get_api_key():
    try:
        return st.secrets["EVDS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_evds_chunk(series_tuple, start_date_str, end_date_str, api_key):
    url = (
        f"{BASE_URL}series={'-'.join(series_tuple)}"
        f"&startDate={start_date_str}&endDate={end_date_str}&type=json"
    )
    try:
        response = requests.get(url, headers={"key": api_key}, timeout=45)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(
            f"EVDS servisine bağlanılamadı ({start_date_str} - {end_date_str}). "
            "İnternet bağlantınızı, tarih aralığını ve API anahtarını kontrol edin."
        ) from error

    try:
        payload = response.json()
        items = payload["items"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            f"EVDS beklenen biçimde veri döndürmedi ({start_date_str} - {end_date_str})."
        ) from error

    return items


def fetch_all_evds_data(start_date, end_date, api_key, frequency):
    """Uzun sorgulardaki satır sınırı kısıtlamasını aşmak için tarih aralığını 
    yıllık parçalara böler. Yıllık veya diğer frekanslarda ilk dönemin farkının
    doğru hesaplanabilmesi için başlangıç tarihinden önceki yılın sonunu da 
    kapsayacak şekilde ek parça çeker.
    """
    if frequency == "Yıllık":
        extended_start = date(start_date.year - 1, 1, 1)
    else:
        extended_start = start_date - timedelta(days=45)

    chunks = []
    current_start = extended_start
    
    while current_start <= end_date:
        current_end = min(date(current_start.year, 12, 31), end_date)
        if current_start > current_end:
            break
        chunks.append((current_start, current_end))
        current_start = date(current_start.year + 1, 1, 1)

    all_items = []
    series_tuple = tuple(SERIES)

    for chunk_start, chunk_end in chunks:
        s_str = chunk_start.strftime("%d-%m-%Y")
        e_str = chunk_end.strftime("%d-%m-%Y")
        try:
            items = fetch_evds_chunk(series_tuple, s_str, e_str, api_key)
            if items:
                all_items.extend(items)
        except Exception as error:
            raise RuntimeError(
                f"Parça çekilemedi ({s_str} - {e_str}): {str(error)}"
            ) from error

    if not all_items:
        raise ValueError("Seçilen tarih aralığında EVDS'de veri bulunamadı.")

    raw_df = pd.DataFrame(all_items)
    return raw_df


# --------------------------------------------------------------------------
# Veri hazırlama (stok seviyesi)
# --------------------------------------------------------------------------

def prepare_stock_data(raw):
    date_candidates = [
        c for c in raw.columns if c.strip().lower() in ("tarih", "date")
    ]
    if not date_candidates:
        raise ValueError(
            "EVDS yanıtında tarih sütunu bulunamadı. "
            f"Gelen sütunlar: {', '.join(raw.columns)}"
        )
    date_column = date_candidates[0]
    df = raw.rename(columns={date_column: "Date", **SERIES_RENAME}).copy()

    missing = [n for n in SERIES_RENAME.values() if n not in df.columns]
    if missing:
        raise ValueError(
            "EVDS yanıtında beklenen seriler bulunamadı: " + ", ".join(missing)
        )

    df = df[["Date", *SERIES_RENAME.values()]]
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"])

    value_columns = list(SERIES_RENAME.values())
    df[value_columns] = df[value_columns].apply(pd.to_numeric, errors="coerce")
    df = df.sort_values("Date").drop_duplicates(subset="Date", keep="last")
    df = df.set_index("Date")

    for col in value_columns:
        df[col] = df[col].ffill(limit=2)

    df = df.dropna(subset=value_columns, how="all")
    df = df.dropna(subset=value_columns)

    if len(df) < 2:
        raise ValueError(
            "Birinci farkın hesaplanabilmesi için en az iki iş gününe ait "
            "geçerli veri gerekir. Tarih aralığını genişletin."
        )

    df["Net Foreign Assets"] = df["Foreign Assets"] - df["Total Foreign Liabilities"]
    df = df.drop(columns=["Foreign Assets", "Total Foreign Liabilities"])
    net_foreign_assets = df.pop("Net Foreign Assets")
    df.insert(0, "Net Foreign Assets", net_foreign_assets)

    return df.sort_index()


# --------------------------------------------------------------------------
# Frekans dönüşümü ve fark hesaplama
# --------------------------------------------------------------------------

def resample_stock(stock_df, freq_label):
    if freq_label == "Günlük":
        return stock_df
    
    if freq_label == "Haftalık":
        codes = ["W-FRI", "W"]
    elif freq_label == "Aylık":
        codes = ["ME", "M"]
    elif freq_label == "Yıllık":
        codes = ["YE", "Y", "A"]
    else:
        codes = [freq_label]

    last_error = None
    for code in codes:
        try:
            resampled = stock_df.resample(code).last()
            resampled = resampled.dropna(how="all")
            if not resampled.empty:
                return resampled
        except Exception as error:
            last_error = error
            continue
    raise RuntimeError(f"Frekans dönüştürülemedi ({freq_label}): {last_error}")


def compute_diffs(stock_df, freq_label, user_start_date):
    period_stock = resample_stock(stock_df, freq_label)
    diffs = period_stock.diff().dropna(how="all")

    if freq_label == "Yıllık":
        target_year = user_start_date.year
        diffs = diffs.loc[diffs.index.year >= target_year]

    if diffs.empty:
        raise ValueError(
            "Seçilen tarih aralığı ve sıklık için fark hesaplanamadı. "
            "Daha geniş bir tarih aralığı seçmeyi deneyin."
        )

    diffs["Liquidity"] = (
        diffs["Net Foreign Assets"]
        + diffs["Domestic Assets"]
        + diffs["Revaluation"]
        - diffs["Currency Issued"]
        - diffs["Extra Funds"]
        - diffs["Deposits of Public Sector"]
        - diffs["Deposits of Non-Bank Sector"]
    )

    diffs["OMO"] = -diffs["OMO"]

    diffs["Calculated Banking Reserves"] = diffs["Liquidity"] + diffs["OMO"]
    diffs["Control Difference"] = (
        diffs["Calculated Banking Reserves"] - diffs["Banking Reserves"]
    )
    return diffs


def scale_data(df, unit):
    divisor = 1_000_000 if unit == "Milyar TL" else 1_000
    return df / divisor


# --------------------------------------------------------------------------
# Grafik oluşturma (Plotly)
# --------------------------------------------------------------------------

def _tick_step(n_obs):
    if n_obs <= 15:
        return 1
    if n_obs <= 45:
        return 3
    if n_obs <= 120:
        return 7
    return max(1, n_obs // 10)


def render_plot(fig, key=None):
    config = {"displaylogo": False, "responsive": True}
    try:
        st.plotly_chart(fig, width="stretch", config=config, key=key)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, config=config, key=key)


def create_main_chart(df, unit):
    n = len(df)
    labels = df.index.strftime("%d.%m.%Y")
    step = _tick_step(n)
    tick_idx = list(range(0, n, step))

    liquidity_colors = [
        POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in df["Liquidity"]
    ]
    omo_colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in df["OMO"]]

    marker_size = 7 if n <= 45 else (4 if n <= 120 else 3)
    line_mode = "lines+markers" if n <= 120 else "lines"

    fig = go.Figure()
    fig.add_bar(
        x=labels,
        y=df["Liquidity"],
        name="Likidite Durumu",
        marker_color=liquidity_colors,
        marker_line_color="rgba(0,0,0,0.35)",
        marker_line_width=0.6,
        opacity=0.55,
        width=0.3,
        hovertemplate="%{x}<br>Likidite Durumu: %{customdata}<extra></extra>",
        customdata=[format_tr_with_unit(v, unit_label_for(unit)) for v in df["Liquidity"]],
    )
    fig.add_bar(
        x=labels,
        y=df["OMO"],
        name="APİ (Net Fonlama Değişimi)",
        marker_color=omo_colors,
        marker_line_color="rgba(0,0,0,0.35)",
        marker_line_width=0.6,
        opacity=0.75,
        width=0.3,
        hovertemplate="%{x}<br>APİ Katkısı: %{customdata}<extra></extra>",
        customdata=[format_tr_with_unit(v, unit_label_for(unit)) for v in df["OMO"]],
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=df["Banking Reserves"],
            name="Bankalar Mevduatı (Değişim)",
            mode=line_mode,
            line=dict(color=RESERVE_COLOR, width=2, dash="dot"),
            marker=dict(size=marker_size, color=RESERVE_COLOR),
            hovertemplate="%{x}<br>Bankalar Mevduatı Değişimi: %{customdata}<extra></extra>",
            customdata=[
                format_tr_with_unit(v, unit_label_for(unit)) for v in df["Banking Reserves"]
            ],
        )
    )

    fig.update_layout(
        barmode="overlay",
        title="Likidite Durumu, Net APİ Katkısı ve Bankalar Mevduatı Değişimi",
        yaxis_title=unit_label_for(unit).capitalize(),
        template="plotly_white",
        height=460,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        hovermode="x unified",
    )
    fig.update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    fig.update_xaxes(
        tickmode="array",
        tickvals=[labels[i] for i in tick_idx],
        ticktext=[labels[i] for i in tick_idx],
        tickangle=-45,
    )
    if n > 60:
        fig.update_xaxes(rangeslider_visible=True)
    return fig


def create_components_chart(df, unit):
    n = len(df)
    labels = df.index.strftime("%d.%m.%Y")
    step = _tick_step(n)
    tick_idx = list(range(0, n, step))

    fig = go.Figure()
    for col in COMPONENTS:
        signed_values = df[col] * SIGNS[col]
        raw_values = df[col]
        custom = np.stack(
            [
                [format_tr_with_unit(v, unit_label_for(unit)) for v in raw_values],
                [format_tr_with_unit(v, unit_label_for(unit)) for v in signed_values],
            ],
            axis=-1,
        )
        fig.add_bar(
            x=labels,
            y=signed_values,
            name=TURKISH_NAMES[col],
            marker_color=COMPONENT_COLORS[col],
            marker_line_color="rgba(0,0,0,0.25)",
            marker_line_width=0.4,
            customdata=custom,
            hovertemplate=(
                TURKISH_NAMES[col]
                + "<br>Ham bilanço değişimi: %{customdata[0]}"
                + "<br>Likiditeye katkısı: %{customdata[1]}<extra></extra>"
            ),
        )

    fig.update_layout(
        barmode="relative",
        title="Likidite Bileşenleri",
        yaxis_title=unit_label_for(unit).capitalize(),
        template="plotly_white",
        height=480,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.45, xanchor="center", x=0.5),
        hovermode="closest",
    )
    fig.update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor="black")
    fig.update_xaxes(
        tickmode="array",
        tickvals=[labels[i] for i in tick_idx],
        ticktext=[labels[i] for i in tick_idx],
        tickangle=-45,
    )
    if n > 60:
        fig.update_xaxes(rangeslider_visible=True)
    return fig


# --------------------------------------------------------------------------
# Excel dışa aktarım
# --------------------------------------------------------------------------

def to_excel(df):
    output = BytesIO()
    export_df = df.rename(columns=TURKISH_NAMES).copy()
    export_df.index.name = "Tarih"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="Likidite Analizi")
    output.seek(0)
    return output.getvalue()


def select_row_count(df, key):
    options = {"Son 10": 10, "Son 25": 25, "Son 50": 50, "Tümü": None}
    choice = st.radio(
        "Gösterilecek gözlem sayısı",
        list(options.keys()),
        index=1,
        horizontal=True,
        key=key,
    )
    n = options[choice]
    return df.tail(n) if n else df


# --------------------------------------------------------------------------
# Ana uygulama
# --------------------------------------------------------------------------

st.title("🏦 TCMB Analitik Bilanço: Likidite Analizi")

st.markdown(
    f"""
    <div class="method-box">
    <b>Yöntem:</b> TCMB analitik bilanço kalemlerinin birinci farkları üzerinden
    <b>Likidite Durumu</b> hesaplanır; bu değer <b>Net APİ katkısı</b> ile
    toplandığında <b>Bankaların TCMB'deki mevduatındaki değişime</b> eşit olmalıdır
    (kontrol ilişkisi). Kaynak: Engin Yılmaz,
    <a href="{METHOD_SOURCE_URL}" target="_blank">
    "A New Monetary Analysis Tool: The Daily Liquidity Dataset"</a>,
    Ekonomista, 2020; TCMB EVDS3 verileri.
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Analiz Ayarları")
    default_end = date.today()
    default_start = default_end - timedelta(days=14)
    start_date = st.date_input("Başlangıç tarihi", value=default_start, format="DD/MM/YYYY")
    end_date = st.date_input("Bitiş tarihi", value=default_end, format="DD/MM/YYYY")
    frequency = st.selectbox("Veri sıklığı", FREQ_LABELS, index=0)
    unit = st.radio("Gösterim birimi", ["Milyar TL", "Milyon TL"], index=0)

    col_a, col_b = st.columns(2)
    fetch_clicked = col_a.button("Verileri Getir", type="primary", use_container_width=True)
    refresh_clicked = col_b.button("Verileri Yenile", use_container_width=True)

    st.divider()
    st.caption("Veri kaynağı: TCMB EVDS3 · Analitik Bilanço")

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

if "cache_bust" not in st.session_state:
    st.session_state["cache_bust"] = 0

if refresh_clicked:
    st.session_state["cache_bust"] += 1
    fetch_clicked = True

if fetch_clicked:
    with st.spinner("EVDS verileri parçalar halinde alınıyor ve hesaplamalar yapılıyor..."):
        try:
            raw_data = fetch_all_evds_data(start_date, end_date, api_key, frequency)
            stock_data = prepare_stock_data(raw_data)
            
            selected_start_year = start_date.year
            assert stock_data.index.min().year <= selected_start_year, \
                f"Ham veri başlangıç yılı ({stock_data.index.min().year}), istenen başlangıç yılından ({selected_start_year}) büyük!"
            assert stock_data.index.max().date() <= end_date + timedelta(days=1), \
                "Ham veri bitiş tarihi seçilen bitiş tarihinden sonrasını içeriyor."

            diffs = compute_diffs(stock_data, frequency, start_date)
            diffs = diffs.loc[
                (diffs.index >= pd.Timestamp(start_date))
                & (diffs.index <= pd.Timestamp(end_date))
            ]
            if diffs.empty:
                raise ValueError(
                    "Seçilen tarih aralığında, seçilen sıklıkta tamamlanmış bir "
                    "dönem bulunamadı. Tarih aralığını genişletmeyi deneyin."
                )
        except (RuntimeError, ValueError, AssertionError) as error:
            st.error(str(error))
            st.stop()

    st.session_state["calculated_data"] = diffs
    st.session_state["unit"] = unit
    st.session_state["frequency"] = frequency
    st.session_state["period"] = (start_date, end_date)
    st.session_state["raw_info"] = {
        "min_date": stock_data.index.min().strftime("%d.%m.%Y"),
        "max_date": stock_data.index.max().strftime("%d.%m.%Y"),
        "count": len(stock_data)
    }

if "calculated_data" not in st.session_state:
    st.info("Analize başlamak için tarih aralığını, sıklığı seçip **Verileri Getir** düğmesine basın.")
    st.stop()

calculated_data = st.session_state["calculated_data"]
active_unit = st.session_state["unit"]
active_freq = st.session_state["frequency"]
period_start, period_end = st.session_state["period"]
raw_info = st.session_state.get("raw_info", {"min_date": "-", "max_date": "-", "count": 0})
display_data = scale_data(calculated_data, active_unit)
u_label = unit_label_for(active_unit)

st.success(
    f"{period_start.strftime('%d.%m.%Y')}–{period_end.strftime('%d.%m.%Y')} "
    f"dönemi için {active_freq.lower()} bazda {len(display_data)} gözlem hesaplandı."
)

with st.expander("📊 Veri Kapsamı ve Teşhis Bilgileri", expanded=True):
    col_inf1, col_inf2, col_inf3, col_inf4 = st.columns(4)
    col_inf1.metric("İstenen Dönem", f"{period_start.strftime('%d.%m.%Y')} – {period_end.strftime('%d.%m.%Y')}")
    col_inf2.metric("Ham Veri Kapsamı", f"{raw_info['min_date']} – {raw_info['max_date']}")
    col_inf3.metric("Ham Günlük Gözlem", f"{raw_info['count']:,}".replace(",", "."))
    col_inf4.metric("Hesaplanan Dönem Sayısı", len(display_data))

residual_raw = calculated_data["Control Difference"]
flagged = residual_raw[residual_raw.abs() > RESIDUAL_WARN_THRESHOLD_MILLION]
if not flagged.empty:
    flagged_dates = ", ".join(flagged.index.strftime("%d.%m.%Y"))
    st.warning(
        "Şu dönemlerde kontrol farkı (Hesaplanan Bankalar Mevduatı − Gerçekleşen "
        f"Bankalar Mevduatı) sıfırdan belirgin şekilde sapıyor: {flagged_dates}. "
        "Veri kesintisi, revize veri veya tatil günü kaynaklı olabilir."
    )

latest = display_data.iloc[-1]
latest_date_label = display_data.index[-1].strftime("%d.%m.%Y")

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Likidite Durumu ({latest_date_label})", format_tr_with_unit(latest["Liquidity"], u_label))
c2.metric("Net APİ Katkısı", format_tr_with_unit(latest["OMO"], u_label))
c3.metric("Bankalar Mevduatı Değişimi", format_tr_with_unit(latest["Banking Reserves"], u_label))
c4.metric("Kontrol Farkı", format_tr_with_unit(latest["Control Difference"], u_label))

tab_1, tab_2, tab_3, tab_4 = st.tabs(
    ["Genel Görünüm", "Likidite Bileşenleri", "Veri Tablosu", "Yöntem"]
)

with tab_1:
    main_fig = create_main_chart(display_data, active_unit)
    render_plot(main_fig, key="main_chart")
    st.caption(
        "Likidite Durumu ve APİ sütunları yan yana, Bankalar Mevduatı değişimi "
        "noktalı çizgi olarak gösterilir. Renk, değerin işaretine göre değişir."
    )

    with st.expander("Hesaplama tablosunu göster"):
        table_cols = [
            "Liquidity", "OMO", "Banking Reserves",
            "Calculated Banking Reserves", "Control Difference",
        ]
        table_main = display_data[table_cols].rename(columns=TURKISH_NAMES).copy()
        table_main.index = table_main.index.strftime("%d.%m.%Y")
        table_main.index.name = "Tarih"
        table_main_view = select_row_count(table_main, key="main_table_rows")
        st.dataframe(
            table_main_view.style.format(format_tr_number),
            width="stretch" if hasattr(st, "dataframe") else None,
        )
        st.caption(f"Tüm değerler {u_label} cinsindendir.")

with tab_2:
    comp_fig = create_components_chart(display_data, active_unit)
    render_plot(comp_fig, key="components_chart")
    st.caption(
        "Net Dış Varlıklar, İç Varlıklar ve Değerleme Hesabı likidite artırıcı; "
        "Dolaşımdaki Para, Fon Hesapları, Kamu Mevduatı ve Banka Dışı Kesim "
        "Mevduatı likidite azaltıcı yönde işaretlenmiştir."
    )

    with st.expander("Bileşen tablosunu göster"):
        comp_cols = COMPONENTS + ["Liquidity"]
        table_comp = display_data[comp_cols].rename(columns=TURKISH_NAMES).copy()
        table_comp.index = table_comp.index.strftime("%d.%m.%Y")
        table_comp.index.name = "Tarih"
        table_comp_view = select_row_count(table_comp, key="comp_table_rows")
        st.dataframe(table_comp_view.style.format(format_tr_number))
        st.caption(
            f"Tüm değerler {u_label} cinsindendir; işaretler ham bilanço "
            "değişimini gösterir (likidite kimliğine katkı için tablodaki "
            "işaret kurallarına bakınız)."
        )

with tab_3:
    full_cols = [
        "Liquidity", "OMO", "Banking Reserves",
        "Calculated Banking Reserves", "Control Difference",
        *COMPONENTS,
    ]
    full_table = display_data[full_cols].rename(columns=TURKISH_NAMES).copy()
    full_table.index = full_table.index.strftime("%d.%m.%Y")
    full_table.index.name = "Tarih"
    full_table_view = select_row_count(full_table, key="full_table_rows")
    st.dataframe(full_table_view.style.format(format_tr_number))
    st.caption(f"Tüm değerler {u_label} cinsindendir.")

    st.download_button(
        "Excel Olarak İndir",
        data=to_excel(calculated_data),
        file_name=(
            f"TCMB_Likidite_Analizi_{period_start.strftime('%Y%m%d')}_"
            f"{period_end.strftime('%Y%m%d')}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with tab_4:
    st.markdown("### Hesaplama Yöntemi ve Detayları")
    
    st.markdown(
        """
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 1.2rem; border-radius: 8px; margin-bottom: 1.2rem;">
        <b>1. Temel Hesaplama Mantığı (Likidite Özdeşliği):</b><br>
        TCMB analitik bilanço kalemlerinin birinci farkları ($\Delta$) üzerinden piyasanın likidite durumu türetilir:
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    st.latex(
        r"\text{Likidite Durumu} = \Delta\text{Net Dış Varlıklar} + \Delta\text{İç Varlıklar} + \Delta\text{Değerleme Hesabı} - \Delta\text{Dolaşımdaki Para} - \Delta\text{Fon Hesapları} - \Delta\text{Kamu Mevduatı} - \Delta\text{Banka Dışı Kesim Mevduatı}"
    )

    st.markdown(
        """
        * **Net Dış Varlıklar:** Önce stok seviyesinde hesaplanır (aşağıdaki formüle bakın), ardından bu serinin birinci farkı alınır.
        """,
        unsafe_allow_html=True,
    )
    
    st.latex(r"\text{Net Dış Varlıklar} = \text{Dış Varlıklar} - \text{Toplam Dış Yükümlülükler}")

    st.markdown(
        """
        * **APİ Katkısı:** TCMB analitik bilançosunda pasif tarafta izlenen Açık Piyasa İşlemleri serisinin birinci farkı, bilanço işaret yapısı gereği $-1$ ile çarpılır.
        
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 1.2rem; border-radius: 8px; margin-top: 1rem; margin-bottom: 1.2rem;">
        <b>2. Kontrol Mekanizması:</b><br>
        Tüm kalemler birinci fark ($\Delta$) bazında hesaplandığı için kontrol ilişkisi <b>mevduat değişimleri</b> üzerinden kurulur:
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    st.latex(r"\Delta\text{Hesaplanan Bankalar Mevduatı} = \text{Likidite Durumu} + \text{Net APİ}")
    st.latex(r"\text{Kontrol Farkı} = \Delta\text{Hesaplanan Bankalar Mevduatı} - \Delta\text{Gerçekleşen Bankalar Mevduatı}")

    st.markdown(
        """
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 1.2rem; border-radius: 8px; margin-top: 1rem; margin-bottom: 1.2rem;">
        <b>3. Frekans Dönüşümü ve Yıllık/Dönemsel Hesaplama Mantığı:</b><br>
        Haftalık, aylık veya yıllık sıklıkta hesaplama yapılırken günlük ortalama alınmaz. Her dönemin <b>son geçerli stok gözlemi</b> seçilip ardışık dönem sonları arasında fark ($\Delta$) alınır.
        </div>
        
        * **Yıllık Analizlerde Geriye Dönük Çekim:** Bir yılın (örneğin 2025) yıllık likidite değişimini hesaplayabilmek için sistem, <b>2025 yıl sonu stoku</b> ile bir önceki dönemin sonu olan <b>2024 yıl sonu stoku</b> arasındaki farkı alır. Bu nedenle sistem otomatik olarak bir önceki yılın sonunu da kapsayacak şekilde geriye dönük veri çeker ve ardından hedef yılı filtreleyerek sunar.
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown(
        f"*Kaynak: Engin Yılmaz, [\"A New Monetary Analysis Tool: The Daily Liquidity Dataset\"]({METHOD_SOURCE_URL}), "
        f"Ekonomista, 2020; TCMB EVDS3 Analitik Bilanço verileri.*"
    )