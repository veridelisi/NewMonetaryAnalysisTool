# ---------------------------------------------------------------------------
# CBRT Analitik Bilanço - Likidite Analizi : https://ekonomista.pte.pl/pdf-155448-82266?filename=A%20New%20Monetary%20Analysis.pdf
# Engin YILMAZ
# ---------------------------------------------------------------------------


import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# ---------------------------------------------------------------------------
# 1) Ayarlar
# ---------------------------------------------------------------------------

# https://evds3.tcmb.gov.tr -> Profil sayfanizdan alacaginiz API anahtari
API_KEY = "Ak2QX6fe8eZA"

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"

# Central Bank Analytical Balance Sheet (Thousand TRY)(Business)
# Foreign Assets | TP.AB.A02                  Domestic Assets | TP.AB.A03
# FX Revaluation Account | TP.AB.A08          Total Foreign Liabilities | TP.AB.A10
# Currency Issued | TP.AB.A17                 Extra Budgetary Funds | TP.AB.A21
# Deposits of Non-Bank Sector | TP.AB.A22     Deposits of Public Sector | TP.AB.A25
# Deposits of Banking Sector | TP.AB.A18      Open Market Operations | TP.AB.A24
SERIES = [
    "TP.AB.A02", "TP.AB.A03", "TP.AB.A08", "TP.AB.A10", "TP.AB.A17",
    "TP.AB.A18", "TP.AB.A21", "TP.AB.A24", "TP.AB.A25", "TP.AB.A22",
]

START_DATE = "20-08-2026"   # dd-mm-yyyy — kisa/gunluk bir donem ornegi
END_DATE = "31-08-2026"     # dd-mm-yyyy — gunluk cubuklarin okunakli olmasi icin dar tuttuk


# ---------------------------------------------------------------------------
# 2) EVDS3'ten veri cekme
#    (test ettiginiz calisan tek-seri sorgusuyla AYNI url/format kullanilir,
#    sadece SERIES listesi '-' ile birlestirilip tek istekte gonderilir)
# ---------------------------------------------------------------------------

def fetch_evds3(series, start_date, end_date, api_key):
    """EVDS3 servisinden JSON formatinda veri cekip DataFrame'e cevirir."""
    url = (
        f"{BASE_URL}series={'-'.join(series)}"
        f"&startDate={start_date}&endDate={end_date}&type=json"
    )
    response = requests.get(url, headers={"key": api_key})

    print(response.status_code)     # 200 gelmeli (siz de boyle kontrol ettiniz)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")

    return pd.DataFrame(response.json()["items"])


raw = fetch_evds3(SERIES, START_DATE, END_DATE, API_KEY)

# Ne donduğunu bir kere gormek isterseniz:
# print(raw.columns.tolist()); print(raw.head())

# ---------------------------------------------------------------------------
# 3) Kolonlari yeniden adlandirma (JSON ciktisinda seri kodlarindaki
#    noktalar alt cizgiye donusur, ornegin TP.AB.A02 -> TP_AB_A02)
# ---------------------------------------------------------------------------

series_rename = {
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

# Tarih kolonunun adi uc noktaya gore degisebiliyor (Tarih / TARIH / date ...)
date_col_candidates = [c for c in raw.columns if c.strip().lower() in ("tarih", "date")]
if not date_col_candidates:
    raise ValueError(
        f"Tarih kolonu bulunamadi. Gelen kolonlar: {raw.columns.tolist()}"
    )
date_col = date_col_candidates[0]

rename_map = {date_col: "Date", **series_rename}
df = raw.rename(columns=rename_map)

# UNIXTIME / YEARWEEK gibi yardimci kolonlar varsa at
keep_cols = ["Date"] + list(series_rename.values())
df = df[[c for c in keep_cols if c in df.columns]]

missing = [c for c in series_rename.values() if c not in df.columns]
if missing:
    raise ValueError(
        f"Beklenen seriler yanitta bulunamadi: {missing}\n"
        f"Gelen kolonlar: {raw.columns.tolist()}"
    )

# Sayisal kolonlari float'a cevir (JSON'dan string gelebiliyor)
value_cols = [c for c in df.columns if c != "Date"]
df[value_cols] = df[value_cols].apply(pd.to_numeric, errors="coerce")

df.set_index("Date", inplace=True)
df = df.dropna()

# ---------------------------------------------------------------------------
# 4) Net Foreign Assets
# ---------------------------------------------------------------------------

df["Net Foreign Assets"] = df["Foreign Assets"] - df["Total Foreign Liabilities"]
df.drop(["Foreign Assets", "Total Foreign Liabilities"], axis=1, inplace=True)

last_column = df.pop("Net Foreign Assets")
df.insert(0, "Net Foreign Assets", last_column)

# ---------------------------------------------------------------------------
# 5) Birinci fark ve likidite hesabi
# ---------------------------------------------------------------------------

df_diff = df.diff()
df_diff = df_diff.iloc[1:]

df_diff["Liquidity"] = (
    df_diff["Net Foreign Assets"]
    + df_diff["Domestic Assets"]
    + df_diff["Revaluation"]
    - df_diff["Currency Issued"]
    - df_diff["Extra Funds"]
    - df_diff["Deposits of Public Sector"]
    - df_diff["Deposits of Non-Bank Sector"]
)

# OMO normalde aktif hesaptir ama CBRT pasif tarafta gosterir; -1 ile carpiyoruz
df_diff["OMO"] = df_diff["OMO"] * (-1)

# Kontrol serisi: Liquidity + OMO ~ Banking Reserves olmali
df_diff["Banking Reserves 2"] = df_diff["OMO"] + df_diff["Liquidity"]

# ---------------------------------------------------------------------------
# 6) Gunluk grafik (matplotlib) — LS / OMO cubuk (ustuste, ayni x konumunda),
#    BR (Banking Reserves) kesikli cizgi. Yillik toplam yerine artik her
#    GUN icin ayri cubuk/nokta var.
# ---------------------------------------------------------------------------

df_diff.index = pd.to_datetime(df_diff.index, format="%d-%m-%Y")
df_diff = df_diff.sort_index()


def turkce_binlik(x, pos=None):
    """12836537 -> '12.836.537' (Turkce binlik ayrac: nokta)."""
    return f"{x:,.0f}".replace(",", ".")


gunler = df_diff.index.strftime("%d-%m-%Y")
x = np.arange(len(gunler))

ls = df_diff["Liquidity"].to_numpy()
omo = df_diff["OMO"].to_numpy()
br = df_diff["Banking Reserves"].to_numpy()

fig, ax = plt.subplots(figsize=(11, 6))

width = 0.5
# LS (genis, arkada) ile OMO (dar, onde) AYNI x konumunda ustuste
# ciziliyor - yan yana degil.
ax.bar(x, ls, width=width, label="Likidite Durumu", color="#9DC3E6",
       edgecolor="black", linewidth=0.6, zorder=2)
ax.bar(x, omo, width=width, label="APİ", color="#ED7D31",
       edgecolor="black", linewidth=0.6, zorder=3)
ax.plot(x, br, color="black", linestyle="--", marker="o",
        markersize=5, linewidth=1.4, label="Bankalar Mevduatı", zorder=4)

ax.axhline(0, color="black", linewidth=0.8)
ax.yaxis.set_major_formatter(FuncFormatter(turkce_binlik))
ax.set_xticks(x)
ax.set_xticklabels(gunler, rotation=45, ha="right", fontsize=9)

ax.set_title("Likidite Durumu, Açık Piyasa İşlemleri ve Banka Mevduatları (Günlük)",
              fontsize=13)
ax.grid(axis="y", color="#D9D9D9", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)

ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18),
          ncol=3, frameon=False, fontsize=10)

plt.tight_layout()
plt.show()

# ---------------------------------------------------------------------------
# 7) Likidite Bileşenleri (renkli, yigilmis cubuk) — gunluk
# ---------------------------------------------------------------------------

components = [
    "Net Foreign Assets", "Domestic Assets", "Revaluation",
    "Currency Issued", "Extra Funds",
    "Deposits of Public Sector", "Deposits of Non-Bank Sector",
]
# Currency Issued ve mevduat kalemleri likiditeyi AZALTAN yonde (formuldeki
# gibi eksi isaretle) etkiliyor; grafikte de ayni isaretle gosteriyoruz.
signs = {
    "Net Foreign Assets": 1, "Domestic Assets": 1, "Revaluation": 1,
    "Currency Issued": -1, "Extra Funds": -1,
    "Deposits of Public Sector": -1, "Deposits of Non-Bank Sector": -1,
}

renkler = {
    "Net Foreign Assets": "#4C72B0",
    "Domestic Assets": "#55A868",
    "Revaluation": "#C44E52",
    "Currency Issued": "#8172B2",
    "Extra Funds": "#CCB974",
    "Deposits of Public Sector": "#64B5CD",
    "Deposits of Non-Bank Sector": "#DD8452",
}

fig, ax = plt.subplots(figsize=(11, 6))

pozitif_taban = np.zeros(len(x))
negatif_taban = np.zeros(len(x))

for kolon in components:
    deger = df_diff[kolon].to_numpy() * signs[kolon]
    taban = np.where(deger >= 0, pozitif_taban, negatif_taban)
    ax.bar(x, deger, width=0.7, bottom=taban, label=kolon,
           color=renkler[kolon], edgecolor="black", linewidth=0.4, zorder=2)
    pozitif_taban = np.where(deger >= 0, pozitif_taban + deger, pozitif_taban)
    negatif_taban = np.where(deger < 0, negatif_taban + deger, negatif_taban)

ax.axhline(0, color="black", linewidth=0.8)
ax.yaxis.set_major_formatter(FuncFormatter(turkce_binlik))
ax.set_xticks(x)
ax.set_xticklabels(gunler, rotation=45, ha="right", fontsize=9)

ax.set_title("Likidite Bileşenleri (Günlük)", fontsize=13)
ax.grid(axis="y", color="#D9D9D9", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)

ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25),
          ncol=3, frameon=False, fontsize=9)

plt.tight_layout()
plt.show()
