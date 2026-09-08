"""TCMB Analitik Bilanço: Likidite Analizi

Hesaplama mantığı (DEĞİŞTİRİLMEMİŞTİR):

    Likidite Durumu
        = ΔNet Dış Varlıklar + ΔİçVarlıklar + ΔDeğerleme Hesabı
          − ΔDolaşımdaki Para − ΔFon Hesapları
          − ΔKamu Mevduatı − ΔBanka Dışı Kesim Mevduatı

    Net Dış Varlıklar = Dış Varlıklar − Toplam Dış Yükümlülükler

    Likidite Durumu + ΔAPİ = ΔBankaların TCMB'deki Mevduatı

TP.AB.A24 (APİ) serisinin birinci farkı, analitik bilançodaki işaret
yapısı nedeniyle -1 ile çarpılır. Bu kural değiştirilmemiştir.
"""

from datetime import date, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
    /* Mobilde grafiğe dokunulduğunda sayfanın dikey kaydırmasının
       Plotly tarafından yakalanıp "takılıyormuş" hissi vermesini önler. */
    .js-plotly-plot, .plot-container, .svg-container {
        touch-action: pan-y !important;
    }
    div[data-testid="stElementContainer"]:has(.js-plotly-plot) {
        overflow: hidden;
        max-width: 100%;
    }
    button[data-baseweb="tab"] {
        min-height: 2.6rem;
        padding: 0.35rem 0.7rem;
        font-size: 0.85rem;
    }
    div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
        min-height: 2.6rem;
        border-radius: 8px;
    }
    @media (max-width: 640px) {
        h1 { font-size: 1.3rem !important; }
        div[data-testid="stMetricValue"] { font-size: 1.05rem; }
        .block-container { padding-left: 0.6rem; padding-right: 0.6rem; }
        button[data-baseweb="tab"] { font-size: 0.78rem; padding: 0.3rem 0.4rem; }
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
FREQ_CODES = {
    "Haftalık": ["W-FRI"],
    "Aylık": ["ME", "M"],
    "Yıllık": ["YE", "Y"],
}
LOOKBACK_DAYS = {
    "Günlük": 10,
    "Haftalık": 25,
    "Aylık": 50,
    "Yıllık": 400,
}

RESIDUAL_WARN_THRESHOLD_MILLION = 50.0  # milyon TL cinsinden tolerans

METHOD_SOURCE_URL = (
    "https://ekonomista.pte.pl/pdf-155448-82266"
    "?filename=A%20New%20Monetary%20Analysis.pdf"
)

# --------------------------------------------------------------------------
# Ödeme sistemleri ve serbest mevduat (ayrı, tarih aralığı seçilemeyen bölüm)
# --------------------------------------------------------------------------

# FAST 2021'de devreye girdiği için bu bölümün başlangıcı sabittir;
# kullanıcı bu bölüm için tarih aralığı seçemez.
PAYMENT_START = date(2021, 1, 1)

PAYMENT_SERIES = [
    "TP.EFTEMKT2.TUTAR.A01",
    "TP.OSGMFAST.ATO",
    "TP.OSGMPOS.TUTAR.T01",
    "TP.AB.A20",
]

PAYMENT_SERIES_RENAME = {
    "TP_EFTEMKT2_TUTAR_A01": "EFT Toplam Ödeme Tutarı",
    "TP_OSGMFAST_ATO": "FAST Toplam Ödeme Tutarı",
    "TP_OSGMPOS_TUTAR_T01": "POS Toplam Ödeme Tutarı",
    "TP_AB_A20": "Serbest Mevduat",
}

PAYMENT_COLORS = {
    "EFT Toplam Ödeme Tutarı": "#4C72B0",
    "FAST Toplam Ödeme Tutarı": "#55A868",
    "POS Toplam Ödeme Tutarı": "#C44E52",
    "Serbest Mevduat": "#1A202C",
}

RATIO_COLORS = {
    "Serbest Mevduat / EFT": "#4C72B0",
    "Serbest Mevduat / FAST": "#55A868",
    "Serbest Mevduat / POS": "#C44E52",
}



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
# Veri çekme
# --------------------------------------------------------------------------

def get_api_key():
    try:
        return st.secrets["EVDS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


def year_chunks(start_dt, end_dt):
    """[start_dt, end_dt] aralığını takvim yılı parçalarına böler.

    EVDS3'ün tek sorguda döndürdüğü gözlem sayısı sınırlı olduğundan, çok
    yıllı günlük sorgular sessizce kırpılabiliyor (yalnızca en son ~birkaç
    yılın verisi dönüyor). Her parça en fazla bir takvim yılı kapsadığından
    (≈366 satır) bu sınıra takılma riski ortadan kalkar.
    """
    chunks = []
    current_start = start_dt
    while current_start <= end_dt:
        year_end = date(current_start.year, 12, 31)
        chunk_end = min(year_end, end_dt)
        chunks.append((current_start, chunk_end))
        current_start = chunk_end + timedelta(days=1)
    return chunks


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_evds_chunk(series_tuple, start_date_str, end_date_str, api_key, _cache_bust=0):
    """Tek bir tarih parçası için EVDS3'ten ham veri çeker (cache anahtarı
    seri listesi, başlangıç/bitiş tarihi ve _cache_bust'a açıkça bağlıdır)."""
    url = (
        f"{BASE_URL}series={'-'.join(series_tuple)}"
        f"&startDate={start_date_str}&endDate={end_date_str}&type=json"
    )
    try:
        response = requests.get(url, headers={"key": api_key}, timeout=45)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(
            f"EVDS servisine bağlanılamadı ({start_date_str}–{end_date_str}). "
            "İnternet bağlantınızı, tarih aralığını ve API anahtarını kontrol edin."
        ) from error

    try:
        payload = response.json()
        items = payload["items"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            f"EVDS beklenen biçimde veri döndürmedi ({start_date_str}–{end_date_str})."
        ) from error

    if not items:
        raise ValueError(
            f"{start_date_str}–{end_date_str} aralığında EVDS'de veri bulunamadı."
        )

    return pd.DataFrame(items)


def fetch_evds_range(series_tuple, start_dt, end_dt, api_key, cache_bust):
    """İstenen tüm aralığı yıllık parçalar hâlinde çekip birleştirir.

    Bir parça başarısız olursa sessizce atlanmaz; hangi aralığın
    çekilemediği toplanıp kullanıcıya açıkça bildirilir.
    """
    frames = []
    failed = []
    for chunk_start, chunk_end in year_chunks(start_dt, end_dt):
        try:
            frame = fetch_evds_chunk(
                series_tuple,
                chunk_start.strftime("%d-%m-%Y"),
                chunk_end.strftime("%d-%m-%Y"),
                api_key,
                cache_bust,
            )
            frames.append(frame)
        except (RuntimeError, ValueError) as error:
            failed.append(f"{chunk_start.strftime('%d.%m.%Y')}–{chunk_end.strftime('%d.%m.%Y')}: {error}")

    if failed:
        raise RuntimeError(
            "Şu tarih parçaları için veri çekilemedi: " + " | ".join(failed)
        )
    if not frames:
        raise ValueError("Seçilen tarih aralığında EVDS'de veri bulunamadı.")

    combined = pd.concat(frames, ignore_index=True)
    return combined


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

    # İzole (tek günlük) eksik gözlemleri, o serideki bir önceki gözlemle
    # doldur; bir serideki tek eksik değer yüzünden tüm satırı kaybetme.
    for col in value_columns:
        df[col] = df[col].ffill(limit=2)

    # Hâlâ tamamen boş satır varsa (ör. seri tümüyle kesintiye uğramışsa) at.
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
# Ödeme sistemleri ve serbest mevduat verisi
# --------------------------------------------------------------------------

def prepare_payment_data(raw):
    date_candidates = [
        c for c in raw.columns if c.strip().lower() in ("tarih", "date")
    ]
    if not date_candidates:
        raise ValueError(
            "EVDS yanıtında tarih sütunu bulunamadı. "
            f"Gelen sütunlar: {', '.join(raw.columns)}"
        )
    date_column = date_candidates[0]
    df = raw.rename(columns={date_column: "Date", **PAYMENT_SERIES_RENAME}).copy()

    missing = [n for n in PAYMENT_SERIES_RENAME.values() if n not in df.columns]
    if missing:
        raise ValueError(
            "EVDS yanıtında beklenen ödeme sistemi serileri bulunamadı: "
            + ", ".join(missing)
        )

    df = df[["Date", *PAYMENT_SERIES_RENAME.values()]]
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"])

    value_columns = list(PAYMENT_SERIES_RENAME.values())
    df[value_columns] = df[value_columns].apply(pd.to_numeric, errors="coerce")
    df = df.sort_values("Date").drop_duplicates(subset="Date", keep="last")
    df = df.set_index("Date")

    for col in value_columns:
        df[col] = df[col].ffill(limit=2)
    df = df.dropna(subset=value_columns)

    if df.empty:
        raise ValueError("Ödeme sistemleri verisinde geçerli gözlem bulunamadı.")

    # Serbest Mevduat (TP.AB.A20) diğer analitik bilanço serileri gibi bin TL
    # cinsindendir; EFT/FAST/POS toplam ödeme tutarları ise TL cinsindendir.
    # Ortak birime getirmek için Serbest Mevduat'ı 1000 ile çarpıyoruz.
    df["Serbest Mevduat"] = df["Serbest Mevduat"] * 1000

    return df.sort_index()


def compute_payment_ratios(payment_df):
    """Serbest Mevduatın EFT/FAST/POS günlük ödeme hacimlerine oranı (kat)."""
    ratios = pd.DataFrame(index=payment_df.index)
    for channel, label in [
        ("EFT Toplam Ödeme Tutarı", "Serbest Mevduat / EFT"),
        ("FAST Toplam Ödeme Tutarı", "Serbest Mevduat / FAST"),
        ("POS Toplam Ödeme Tutarı", "Serbest Mevduat / POS"),
    ]:
        ratio = payment_df["Serbest Mevduat"] / payment_df[channel]
        ratios[label] = ratio.replace([np.inf, -np.inf], np.nan)
    return ratios


def scale_payment_data(df, unit):
    # Bu veri seti artık TL (bin TL değil) cinsindendir; bu yüzden
    # scale_data'dan farklı bir bölen kullanılır.
    divisor = 1_000_000_000 if unit == "Milyar TL" else 1_000_000
    return df / divisor


# --------------------------------------------------------------------------
# Frekans dönüşümü ve fark hesaplama
# --------------------------------------------------------------------------

def resample_stock(stock_df, freq_label):
    if freq_label == "Günlük":
        return stock_df
    codes = FREQ_CODES[freq_label]
    last_error = None
    for code in codes:
        try:
            resampled = stock_df.resample(code).last()
            return resampled.dropna(how="all")
        except Exception as error:  # pandas surum farkliligi
            last_error = error
            continue
    raise RuntimeError(f"Frekans dönüştürülemedi ({freq_label}): {last_error}")


def compute_diffs(stock_df, freq_label):
    period_stock = resample_stock(stock_df, freq_label)
    diffs = period_stock.diff().dropna(how="all")

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

    # TCMB analitik bilançosunda pasif tarafta izlenen APİ'nin işaretini
    # çeviriyoruz. (DEĞİŞTİRİLMEMİŞTİR)
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
    # scrollZoom kapalı ve modebar gizli: mobilde parmakla dokunma/kaydırma
    # Plotly'nin zoom/pan davranışıyla çakışıp sayfayı "bozuk" göstermesin.
    config = {
        "displaylogo": False,
        "responsive": True,
        "scrollZoom": False,
        "displayModeBar": False,
        "doubleClick": False,
    }
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
        width=0.55,
        hovertemplate="%{x}<br>Likidite Durumu: %{customdata}<extra></extra>",
        customdata=[format_tr_with_unit(v, unit_label_for(unit)) for v in df["Liquidity"]],
    )
    fig.add_bar(
        x=labels,
        y=df["OMO"],
        name="ΔAPİ",
        marker_color=omo_colors,
        marker_line_color="rgba(0,0,0,0.35)",
        marker_line_width=0.6,
        opacity=0.75,
        width=0.3,
        hovertemplate="%{x}<br>ΔAPİ: %{customdata}<extra></extra>",
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
        dragmode=False,
        title="Likidite Durumu, ΔAPİ ve Bankalar Mevduatı Değişimi",
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
        fixedrange=True,
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
        dragmode=False,
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
        fixedrange=True,
    )
    if n > 60:
        fig.update_xaxes(rangeslider_visible=True)
    return fig


def create_payment_chart(payment_df, ratio_df, unit):
    """Üstte EFT/FAST/POS/Serbest Mevduat, altta Serbest Mevduatın bu üç
    ödeme kanalına oranı — ortak x ekseninde, aşağıdaki alt panelde de
    işlev gören bir aralık kaydırıcı (rangeslider) ile."""
    labels = payment_df.index.strftime("%d-%m-%Y")

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.62, 0.38],
        subplot_titles=(
            "EFT, FAST, POS Toplam Ödeme Tutarları ve Serbest Mevduat",
            "Serbest Mevduatın Ödeme Sistemi Hacimlerine Oranı",
        ),
    )

    for col in ["EFT Toplam Ödeme Tutarı", "FAST Toplam Ödeme Tutarı",
                "POS Toplam Ödeme Tutarı", "Serbest Mevduat"]:
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=payment_df[col],
                name=col,
                mode="lines",
                line=dict(color=PAYMENT_COLORS[col], width=1.6),
                hovertemplate=f"{col}<br>%{{x}}<br>"
                + "%{customdata}<extra></extra>",
                customdata=[format_tr_with_unit(v, unit_label_for(unit)) for v in payment_df[col]],
            ),
            row=1, col=1,
        )

    for col in ["Serbest Mevduat / EFT", "Serbest Mevduat / FAST", "Serbest Mevduat / POS"]:
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=ratio_df[col],
                name=col,
                mode="lines",
                line=dict(color=RATIO_COLORS[col], width=1.4),
                hovertemplate=f"{col}<br>%{{x}}<br>" + "%{y:.2f} kat<extra></extra>",
            ),
            row=2, col=1,
        )

    fig.update_layout(
        dragmode=False,
        template="plotly_white",
        height=640,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.18, xanchor="center", x=0.5),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text=unit_label_for(unit).capitalize(), zeroline=True,
                      zerolinewidth=2, zerolinecolor="black", row=1, col=1, fixedrange=True)
    fig.update_yaxes(title_text="Oran (kat)", zeroline=True, zerolinewidth=2,
                      zerolinecolor="black", row=2, col=1, fixedrange=True)
    fig.update_xaxes(fixedrange=True, row=1, col=1)
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeslider_thickness=0.08,
        fixedrange=True,
        row=2, col=1,
    )
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
    <b>Likidite Durumu</b> hesaplanır; bu değer <b>APİ değişimi (ΔAPİ)</b> ile
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
    lookback = LOOKBACK_DAYS[frequency]
    fetch_start = start_date - timedelta(days=lookback)
    with st.spinner("EVDS verileri alınıyor ve hesaplamalar yapılıyor..."):
        try:
            raw_data = fetch_evds_range(
                tuple(SERIES), fetch_start, end_date, api_key, st.session_state["cache_bust"]
            )
            stock_data = prepare_stock_data(raw_data)

            raw_min = stock_data.index.min()
            raw_max = stock_data.index.max()
            raw_count = len(stock_data)

            diffs_full = compute_diffs(stock_data, frequency)
            diffs = diffs_full.loc[
                (diffs_full.index >= pd.Timestamp(start_date))
                & (diffs_full.index <= pd.Timestamp(end_date))
            ]
            if diffs.empty:
                raise ValueError(
                    "Seçilen tarih aralığında, seçilen sıklıkta tamamlanmış bir "
                    "dönem bulunamadı. Tarih aralığını genişletmeyi deneyin."
                )
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
            st.stop()

    # Talep edilen başlangıcın gerçekten karşılanıp karşılanmadığını
    # kullanıcıya açıkça bildir; sessizce farklı bir başlangıca kaymasın.
    coverage_notes = []
    if raw_min.date() > start_date:
        coverage_notes.append(
            f"Ham veri, istenen {start_date.strftime('%d.%m.%Y')} yerine "
            f"{raw_min.strftime('%d.%m.%Y')} tarihinden itibaren başlıyor "
            "(EVDS bu seriler için daha eskiye veri döndürmemiş olabilir)."
        )
    if diffs.index.min().date() > start_date and frequency != "Günlük":
        coverage_notes.append(
            f"Seçilen sıklıkta ilk hesaplanabilir dönem "
            f"{diffs.index.min().strftime('%d.%m.%Y')} — önceki dönem sonu stok "
            "verisi kapsam dışında kaldığından ilk kısmi dönem hesaplanamadı."
        )

    st.session_state["calculated_data"] = diffs
    st.session_state["unit"] = unit
    st.session_state["frequency"] = frequency
    st.session_state["period"] = (start_date, end_date)
    st.session_state["coverage"] = {
        "requested_start": start_date,
        "requested_end": end_date,
        "fetch_start": fetch_start,
        "raw_min": raw_min,
        "raw_max": raw_max,
        "raw_count": raw_count,
        "period_count": len(diffs),
        "notes": coverage_notes,
    }

    # Ödeme sistemleri ve serbest mevduat: tarih aralığı kullanıcı tarafından
    # seçilemez, her zaman 2021-01-01'den (FAST'in devreye girdiği tarih)
    # bugüne kadar çekilir. Bu bölümün başarısız olması ana analizi durdurmaz.
    with st.spinner("Ödeme sistemleri ve serbest mevduat verileri alınıyor..."):
        try:
            payment_raw = fetch_evds_range(
                tuple(PAYMENT_SERIES), PAYMENT_START, date.today(),
                api_key, st.session_state["cache_bust"],
            )
            payment_data = prepare_payment_data(payment_raw)
            payment_ratios = compute_payment_ratios(payment_data)
            st.session_state["payment_data"] = payment_data
            st.session_state["payment_ratios"] = payment_ratios
            st.session_state["payment_error"] = None
        except (RuntimeError, ValueError) as error:
            st.session_state["payment_data"] = None
            st.session_state["payment_ratios"] = None
            st.session_state["payment_error"] = str(error)

if "calculated_data" not in st.session_state:
    st.info("Analize başlamak için tarih aralığını, sıklığı seçip **Verileri Getir** düğmesine basın.")
    st.stop()

calculated_data = st.session_state["calculated_data"]
active_unit = st.session_state["unit"]
active_freq = st.session_state["frequency"]
period_start, period_end = st.session_state["period"]
display_data = scale_data(calculated_data, active_unit)
u_label = unit_label_for(active_unit)

st.success(
    f"{period_start.strftime('%d.%m.%Y')}–{period_end.strftime('%d.%m.%Y')} "
    f"dönemi için {active_freq.lower()} bazda {len(display_data)} gözlem hesaplandı."
)

# Kontrol farkı uyarısı (residual, milyon TL bazında ham veri üzerinden)
residual_raw = calculated_data["Control Difference"]
flagged = residual_raw[residual_raw.abs() > RESIDUAL_WARN_THRESHOLD_MILLION]
if not flagged.empty:
    flagged_dates = ", ".join(flagged.index.strftime("%d.%m.%Y"))
    st.warning(
        "Şu dönemlerde kontrol farkı (Hesaplanan Bankalar Mevduatı − Gerçekleşen "
        f"Bankalar Mevduatı) sıfırdan belirgin şekilde sapıyor: {flagged_dates}. "
        "Veri kesintisi, revize veri veya tatil günü kaynaklı olabilir."
    )

# Özet kartlar
latest = display_data.iloc[-1]
latest_date_label = display_data.index[-1].strftime("%d.%m.%Y")

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Likidite Durumu ({latest_date_label})", format_tr_with_unit(latest["Liquidity"], u_label))
c2.metric("ΔAPİ", format_tr_with_unit(latest["OMO"], u_label))
c3.metric("Bankalar Mevduatı Değişimi", format_tr_with_unit(latest["Banking Reserves"], u_label))
c4.metric("Kontrol Farkı", format_tr_with_unit(latest["Control Difference"], u_label))

tab_1, tab_2, tab_3, tab_4, tab_5, tab_6 = st.tabs(
    [
        "Genel Görünüm", "Likidite Bileşenleri", "Veri Tablosu", "Yöntem",
        "Veri Kapsamı", "Ödeme Sistemleri",
    ]
)

with tab_1:
    main_fig = create_main_chart(display_data, active_unit)
    render_plot(main_fig, key="main_chart")
    st.caption(
        "Likidite Durumu ve ΔAPİ aynı tarih konumunda üst üste (dıştaki geniş "
        "çubuk Likidite Durumu, içteki dar çubuk ΔAPİ), Bankalar Mevduatı "
        "değişimi noktalı çizgi olarak gösterilir. Renk, değerin işaretine göre değişir."
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
    st.markdown(
        f"""
### Hesaplama yöntemi

**Likidite Durumu = ΔNet Dış Varlıklar + ΔİçVarlıklar + ΔDeğerleme Hesabı
− ΔDolaşımdaki Para − ΔFon Hesapları − ΔKamu Mevduatı
− ΔBanka Dışı Kesim Mevduatı**

Net Dış Varlıklar önce stok seviyesinde hesaplanır (Dış Varlıklar − Toplam
Dış Yükümlülükler), farkı bu seviyeden alınır.

TCMB analitik bilançosunda pasif tarafta izlenen açık piyasa işlemleri
serisinin birinci farkının işareti çevrilerek **ΔAPİ** elde edilir:

**Hesaplanan Bankalar Mevduatı = Likidite Durumu + ΔAPİ**

**Kontrol Farkı = Hesaplanan Bankalar Mevduatı − Gerçekleşen Bankalar Mevduatı**

Haftalık/aylık/yıllık sıklıkta hesaplama, günlük ortalama alınarak değil,
her dönemin **son geçerli stok gözlemi** seçilip ardışık dönem sonları
arasında fark alınarak yapılır.

Kaynak: Engin Yılmaz, *A New Monetary Analysis Tool: The Daily Liquidity
Dataset*, Ekonomista, 2020 —
[çalışmaya bağlantı]({METHOD_SOURCE_URL}); TCMB EVDS3 Analitik Bilanço
verileri.
        """
    )

with tab_5:
    coverage = st.session_state.get("coverage")
    if not coverage:
        st.info("Veri kapsamı bilgisi, veriler getirildikten sonra burada görünecek.")
    else:
        st.markdown("### Veri kapsamında işlenen dönem bilgileri")

        cov_col1, cov_col2 = st.columns(2)
        with cov_col1:
            st.markdown(
                f"**İstenen dönem:** "
                f"{coverage['requested_start'].strftime('%d.%m.%Y')}–"
                f"{coverage['requested_end'].strftime('%d.%m.%Y')}"
            )
            st.markdown(
                f"**Fark hesabı için EVDS'den istenen başlangıç:** "
                f"{coverage['fetch_start'].strftime('%d.%m.%Y')} "
                "(önceki dönem stok gözlemini de kapsaması için geriye çekilmiştir)"
            )
        with cov_col2:
            st.markdown(
                f"**Ham verinin fiilen kapsadığı dönem:** "
                f"{coverage['raw_min'].strftime('%d.%m.%Y')}–"
                f"{coverage['raw_max'].strftime('%d.%m.%Y')}"
            )
            st.markdown(f"**Ham günlük gözlem sayısı:** {coverage['raw_count']}")

        st.markdown(
            f"**Hesaplanan {active_freq.lower()} dönem sayısı "
            f"(seçilen aralığa filtrelendikten sonra):** {coverage['period_count']}"
        )

        if coverage["notes"]:
            for note in coverage["notes"]:
                st.warning(note)
        else:
            st.success("Ham veri, istenen tarih aralığını ve fark hesabı için gereken önceki dönemi eksiksiz kapsıyor.")

        st.caption(
            "Bu bölüm, uzun tarih aralıklarında EVDS'nin tek sorguda döndürdüğü "
            "gözlem sayısı sınırlı olduğu için verinin sessizce kırpılmadığını "
            "doğrulamanız içindir: veri artık yıllık parçalar hâlinde çekilip "
            "birleştirilmektedir."
        )

with tab_6:
    payment_data = st.session_state.get("payment_data")
    payment_ratios = st.session_state.get("payment_ratios")
    payment_error = st.session_state.get("payment_error")

    st.markdown(
        f"**Kapsam:** {PAYMENT_START.strftime('%d.%m.%Y')}–{date.today().strftime('%d.%m.%Y')} "
        "· bu bölümde tarih aralığı seçilemez (FAST 2021'de devreye girdiği için "
        "başlangıç sabittir); yakınlaştırma/kaydırma için grafiğin altındaki "
        "aralık kaydırıcıyı kullanın."
    )

    if payment_error:
        st.warning(f"Ödeme sistemleri verisi alınamadı: {payment_error}")
    elif payment_data is None:
        st.info("Bu bölümün verisi, **Verileri Getir** düğmesine bastığınızda ana veriyle birlikte çekilir.")
    else:
        payment_display = scale_payment_data(payment_data, active_unit)
        payment_fig = create_payment_chart(payment_display, payment_ratios, active_unit)
        render_plot(payment_fig, key="payment_chart")
        st.caption(
            "Üst panel: EFT, FAST, POS toplam ödeme tutarları ve Serbest Mevduat "
            f"({u_label}, aynı eksende). Alt panel: Serbest Mevduatın bu üç ödeme "
            "kanalının günlük hacmine oranı (kaç katı). Serbest Mevduat (bin TL) "
            "diğer üç seriyle (TL) ortak birime getirmek için 1000 ile çarpılmıştır."
        )

        with st.expander("Veri tablosunu göster"):
            payment_cols = list(PAYMENT_SERIES_RENAME.values())
            table_payment = payment_display[payment_cols].copy()
            for ratio_col in payment_ratios.columns:
                table_payment[ratio_col] = payment_ratios[ratio_col]
            table_payment.index = table_payment.index.strftime("%d.%m.%Y")
            table_payment.index.name = "Tarih"
            table_view = select_row_count(table_payment, key="payment_table_rows")
            st.dataframe(table_view.style.format(format_tr_number))
            st.caption(
                f"EFT/FAST/POS/Serbest Mevduat sütunları {u_label} cinsindendir; "
                "oran sütunları katsayı (kat) olarak gösterilir."
            )