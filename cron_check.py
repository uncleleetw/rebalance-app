import os
import json
import datetime
import requests
import re
import numpy as np
import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

# =========================================================================
# ⚙️ 全域核心配置與校正基準
# =========================================================================
TW_TZ = ZoneInfo("Asia/Taipei")

BASELINE_W5000 = 75000.0
BASELINE_BUFFETT_PCT = 225.0
# 💡 巴菲特指標已內建 GDP 自我校正：首次取得 FRED GDP 時錨定基準存入 config
#   （buffett_baseline_gdp），之後 GDP 成長自動抵銷，上面兩個常數永不過時
BASELINE_FILE = "historical_baseline.json"
RISK_HISTORY_FILE = "risk_history.json"
CONFIG_PATH = "config.json"

# 💡【計分紀元】方案B全天候計分上線日。此前的記錄使用舊計分口徑（0~2分時代，
#   且含全斷線日的失真0分），與現行口徑不可比——一律不參與趨勢計算，
#   並在下次存檔時自動清出，讓7日/30日均線從乾淨的同口徑資料重新累積。
SCORE_EPOCH = "2026-07-07"

# ⚠️【需人工年度維護】S&P500 近四季 EPS，僅作為 SPY info 抓不到 PE 時的備援分母
#    最後更新：2026-07（由主任親自校正至 2026 年最新盈餘基準 280.0）
SP500_EPS_TTM = 280.0

DEFAULT_VIX_P = [9.8, 10.5, 11.1, 11.4, 11.8, 12.1, 12.3, 12.5, 12.7, 12.9, 13.1, 13.3, 13.4, 13.6, 13.7, 13.9, 14.0, 14.2, 14.3, 14.5, 14.6, 14.7, 14.9, 15.0, 15.1, 15.3, 15.4, 15.5, 15.7, 15.8, 15.9, 16.1, 16.2, 16.4, 16.5, 16.7, 16.8, 17.0, 17.1, 17.3, 17.4, 17.6, 17.7, 17.9, 18.1, 18.2, 18.4, 18.6, 18.8, 19.0, 19.2, 19.4, 19.6, 19.8, 20.0, 20.3, 20.5, 20.8, 21.1, 21.3, 21.6, 21.9, 22.2, 22.6, 22.9, 23.3, 23.7, 24.1, 24.6, 25.1, 25.6, 26.1, 26.6, 27.2, 27.8, 28.5, 29.2, 30.0, 31.0, 31.9, 32.9, 34.0, 35.3, 36.8, 38.2, 39.8, 41.5, 43.1, 45.0, 47.1, 49.9, 53.0, 56.4, 60.1, 64.3, 69.1, 73.6, 78.4, 82.6, 85.0]
DEFAULT_SPREAD_P = [-90.0, -82.0, -75.0, -70.0, -65.0, -61.0, -58.0, -54.0, -51.0, -48.0, -45.0, -42.0, -39.0, -37.0, -34.0, -32.0, -29.0, -27.0, -24.0, -22.0, -19.0, -17.0, -15.0, -12.0, -10.0, -8.0, -5.0, -3.0, -1.0, 1.0, 4.0, 6.0, 9.0, 11.0, 14.0, 16.0, 19.0, 22.0, 24.0, 27.0, 30.0, 33.0, 35.0, 38.0, 41.0, 44.0, 47.0, 50.0, 53.0, 56.0, 59.0, 62.0, 65.0, 68.0, 71.0, 74.0, 78.0, 81.0, 84.0, 87.0, 91.0, 94.0, 98.0, 102.0, 105.0, 110.0, 114.0, 118.0, 122.0, 126.0, 131.0, 136.0, 140.0, 145.0, 150.0, 155.0, 161.0, 166.0, 172.0, 178.0, 184.0, 191.0, 198.0, 206.0, 214.0, 222.0, 230.0, 240.0, 249.0, 258.0, 267.0, 276.0, 285.0, 294.0, 303.0, 312.0, 321.0, 330.0, 340.0, 350.0]
DEFAULT_BIAS_P = [-9.5, -8.2, -7.1, -6.3, -5.7, -5.2, -4.8, -4.4, -4.1, -3.8, -3.5, -3.3, -3.1, -2.9, -2.7, -2.5, -2.3, -2.1, -2.0, -1.8, -1.7, -1.6, -1.4, -1.3, -1.2, -1.1, -1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9, 3.0, 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.9, 4.0, 4.2, 4.3, 4.5, 4.6, 4.8, 5.0, 5.2, 5.4, 5.6, 5.8, 6.0, 6.2, 6.5, 6.7, 7.0, 7.3, 7.7, 8.1, 8.5, 9.0, 9.5, 10.2, 11.0, 11.9, 13.1, 14.5]
DEFAULT_CAPE_P = [10.0, 12.0, 14.0, 15.0, 15.5, 16.0, 16.5, 17.0, 17.5, 18.0, 18.2, 18.5, 18.8, 19.0, 19.2, 19.5, 19.8, 20.0, 20.2, 20.5, 20.8, 21.0, 21.2, 21.5, 21.8, 22.0, 22.2, 22.5, 22.8, 23.0, 23.2, 23.5, 23.8, 24.0, 24.2, 24.5, 24.8, 25.0, 25.2, 25.5, 25.8, 26.0, 26.2, 26.5, 26.8, 27.0, 27.2, 27.5, 27.8, 28.0, 28.2, 28.5, 28.8, 29.0, 29.2, 29.5, 29.8, 30.0, 30.3, 30.6, 31.0, 31.3, 31.6, 32.0, 32.3, 32.6, 33.0, 33.3, 33.6, 34.0, 34.4, 34.8, 35.2, 35.6, 36.0, 36.5, 37.0, 37.5, 38.0, 38.5, 39.0, 39.5, 40.0, 40.5, 41.0, 41.5, 42.0, 42.6, 43.2, 43.8, 44.5, 45.2, 46.0, 47.0, 48.0, 49.2, 50.5, 52.0, 54.0, 56.0]

# =========================================================================
# 🛠️ 共通工具函式與大腦核心
# =========================================================================
def now_taiwan():
    return datetime.datetime.now(TW_TZ)

def get_trend_arrow(series):
    if series is None or len(series) < 2: return "➡️"
    current = series.iloc[-1]
    prev = series.iloc[-2]
    if current > prev: return "🔺"
    elif current < prev: return "🔻"
    return "➡️"

def get_series_last_date(series):
    try:
        idx = series.index[-1]
        if hasattr(idx, 'date'):
            return idx.date()
        return datetime.datetime.strptime(str(idx), "%Y-%m-%d").date()
    except Exception:
        return None

def get_trend_regime(series):
    """💡【長線戰略層】200日均線趨勢格局判定——長線投資最經典的格局濾網。
    收盤在200日線上方且均線上彎＝多頭格局；下方且下彎＝空頭格局；其餘＝轉換中。
    回傳 dict 或 None（資料不足）。"""
    if series is None or len(series) < 210:
        return None
    try:
        close = float(series.iloc[-1])
        ma200 = series.rolling(200).mean()
        ma_now = float(ma200.iloc[-1])
        ma_prev = float(ma200.iloc[-21])  # 約一個月前的均線位置，判斜率
        above_pct = (close - ma_now) / ma_now * 100
        if ma_now > ma_prev * 1.001: slope = "上彎"
        elif ma_now < ma_prev * 0.999: slope = "下彎"
        else: slope = "走平"
        if close >= ma_now and slope == "上彎":
            regime = "🟢 多頭格局"
        elif close < ma_now and slope == "下彎":
            regime = "🔴 空頭格局"
        else:
            regime = "🟡 格局轉換中"
        return {"regime": regime, "above_pct": above_pct, "slope": slope}
    except Exception as e:
        print(f"⚠️ 趨勢格局計算失敗: {e}")
        return None

def format_regime(r):
    if r is None: return "資料不足 ⏳"
    return f"{r['regime']} (距200日線 {r['above_pct']:+.1f}%｜均線{r['slope']})"

def yf_close_series(ticker, period):
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df is None or df.empty or 'Close' not in df:
            return None
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.squeeze("columns")
        close = close.dropna()
        return close if not close.empty else None
    except Exception as e:
        print(f"❌ {ticker} 下載失敗: {e}")
        return None

def fred_series(series_id, tail_n=60):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        import io
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ FRED {series_id} 回應異常: HTTP {response.status_code}")
            return None
        df = pd.read_csv(io.StringIO(response.text), na_values=".")
        df.columns = ["DATE", "VAL"]
        s = pd.Series(pd.to_numeric(df["VAL"]).values, index=df["DATE"]).dropna()
        return s.tail(tail_n) if not s.empty else None
    except Exception as e:
        print(f"❌ FRED {series_id} 抓取異常: {e}")
        return None

def safe_save_config_field(field_key, field_value, sub_key=None):
    try:
        current_config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                current_config = json.load(f)
        if sub_key:
            if field_key not in current_config or not isinstance(current_config[field_key], dict):
                current_config[field_key] = {}
            current_config[field_key][sub_key] = field_value
        else:
            current_config[field_key] = field_value

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ 安全寫入 config.json 欄位 {field_key} 失敗: {e}")

def get_recession_prob_from_fred():
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RECPROUSM156N"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            lines = response.text.strip().split('\n')
            for line in reversed(lines[1:]):
                p = line.split(',')
                if len(p) == 2 and p[1].strip() != '.':
                    return float(p[1].strip()), p[0].strip()
        print(f"⚠️ FRED 衰退機率回應異常: HTTP {response.status_code}")
        return None, None
    except Exception as e:
        print(f"❌ FRED 衰退機率抓取異常: {e}")
        return None, None

def fetch_shiller_cape_real():
    """💡【2026-07 重寫】multpl 改版曾使字串切割解析失效（誤抓到 span 標籤文字）。
    改用三層「結構無關」策略，不依賴特定 HTML 標記：
    1. meta description（SEO 文案 'Current Shiller PE Ratio is 41.60'，最不易變動）
    2. id="current" 區塊後 500 字內掃描第一個合理範圍的小數
    3. 'Shiller PE Ratio' 字樣鄰近掃描
    所有候選值須通過 3~80 的合理範圍檢查，杜絕再次抓到雜訊。"""
    url = "https://www.multpl.com/shiller-pe"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ multpl CAPE 頁面回應異常: HTTP {response.status_code}")
            return None
        html = response.text

        # 路徑 1：meta description
        m = re.search(r'Current Shiller PE Ratio is\s*([\d]{1,3}\.\d{1,2})', html)
        if m:
            v = float(m.group(1))
            if 3 <= v <= 80:
                return v

        # 路徑 2：id="current" 區塊掃描
        seg = re.search(r'id="current"(.{0,500})', html, re.S)
        if seg:
            for cand in re.findall(r'([\d]{1,3}\.\d{1,2})', seg.group(1)):
                v = float(cand)
                if 3 <= v <= 80:
                    return v

        # 路徑 3：標題文字鄰近掃描
        seg = re.search(r'Shiller PE Ratio(.{0,200})', html, re.S)
        if seg:
            for cand in re.findall(r'([\d]{1,3}\.\d{1,2})', seg.group(1)):
                v = float(cand)
                if 3 <= v <= 80:
                    return v

        print("⚠️ multpl CAPE 頁面結構再度變更，三層解析路徑均未命中")
        return None
    except Exception as e:
        print(f"❌ 席勒 CAPE 抓取異常: {e}")
        return None

def fetch_shiller_cape_history(max_months=180):
    """💡【2026-07 重寫】不再依賴 class="right" 等特定標記，改用「日期-數值配對」：
    尋找 'Jul 2, 2026' 這類日期後 120 字內的第一個合理範圍小數。
    網站怎麼改表格標記都不影響。回傳序列為新到舊（[0] 即當前月份值）。"""
    url = "https://www.multpl.com/shiller-pe/table/by-month"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ multpl CAPE 歷史表回應異常: HTTP {response.status_code}")
            return None
        pairs = re.findall(
            r'([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})(.{0,120}?)([\d]{1,3}\.\d{1,2})',
            response.text, re.S)
        cape_hist = [float(v) for (_d, _gap, v) in pairs if 3 <= float(v) <= 80]
        cape_hist = cape_hist[:max_months]
        if len(cape_hist) < 24 and max_months >= 24:
            print(f"⚠️ CAPE 歷史序列過短（{len(cape_hist)} 筆），視為抓取失敗")
            return None
        if not cape_hist:
            print("⚠️ CAPE 歷史表解析 0 筆，頁面結構可能再度變更")
            return None
        return cape_hist
    except Exception as e:
        print(f"❌ 席勒 CAPE 歷史抓取異常: {e}")
        return None

def fetch_cape_history_github(max_months=180):
    """💡 CAPE 歷史序列首選來源：GitHub 公開 Shiller 資料集
    （raw.githubusercontent.com，Actions 對 GitHub 域名必通、無 Cloudflare）。
    注意：其 PE10 欄位因盈餘發布延遲，最新有效值約落後 2~3 年，
    因此只用於歷史百分位分布（慢速估值指標的分布足夠穩定），不作為當前值來源。"""
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv"
    try:
        import io, csv as _csv
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            print(f"⚠️ GitHub Shiller 資料集回應異常: HTTP {r.status_code}")
            return None
        rows = list(_csv.DictReader(io.StringIO(r.text)))
        vals = [float(row["PE10"]) for row in rows if row.get("PE10") and float(row["PE10"]) > 0]
        if len(vals) < 24:
            print(f"⚠️ GitHub Shiller PE10 有效筆數過少（{len(vals)}）")
            return None
        print(f"📌 CAPE 歷史序列取自 GitHub Shiller 資料集（共 {len(vals)} 筆，取近 {max_months} 筆）")
        return vals[-max_months:]
    except Exception as e:
        print(f"❌ GitHub Shiller 資料集抓取異常: {e}")
        return None

def fetch_cape_from_nasdaq():
    """💡 當前 CAPE 最高優先來源：Nasdaq Data Link 官方 API（正規管道，無爬蟲風險）。
    需在 GitHub Secrets 設定 NASDAQ_API_KEY（免費註冊取得）；未設定時靜默跳過，
    由 multpl 雙路徑接手，完全不影響既有流程。"""
    api_key = os.environ.get("NASDAQ_API_KEY")
    if not api_key:
        return None
    url = f"https://data.nasdaq.com/api/v3/datasets/MULTPL/SHILLER_PE_RATIO_MONTH.json?rows=1&api_key={api_key}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            print(f"⚠️ Nasdaq CAPE API 回應異常: HTTP {r.status_code}（請檢查 API key 是否有效）")
            return None
        rows = r.json().get("dataset", {}).get("data", [])
        if rows and len(rows[0]) >= 2:
            d, v = rows[0][0], float(rows[0][1])
            print(f"📌 當前 CAPE 取自 Nasdaq Data Link API: {v:.2f}（資料月份 {d}）")
            return v
        print("⚠️ Nasdaq CAPE API 回傳格式異常")
        return None
    except Exception as e:
        print(f"❌ Nasdaq CAPE API 抓取異常: {e}")
        return None

def fetch_cape_current():
    """當前 CAPE 三路徑：Nasdaq 官方 API → multpl 主頁 → multpl 歷史表首筆。
    全數失敗則回 None，由 config 持久化值接手。"""
    val = fetch_cape_from_nasdaq()
    if val is not None:
        return val
    val = fetch_shiller_cape_real()
    if val is not None:
        return val
    hist = fetch_shiller_cape_history(max_months=3)
    if hist:
        print(f"📌 當前 CAPE 改用 multpl 歷史表首筆: {hist[0]:.1f}")
        return hist[0]
    return None

def calculate_metrics_summary(data_list):
    if not data_list: return None
    arr = np.array(data_list)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0: return None
    p_tiles = [float(np.percentile(arr, i)) for i in range(1, 101)]
    return {
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
        "percentiles": p_tiles
    }

def update_historical_baseline():
    print("🔄 [歷史基準大腦] 正在背景建構/更新五大指標 15 年歷史百分位數據庫...")
    baseline_data = {}

    vix_close = yf_close_series("^VIX", "15y")
    if vix_close is not None:
        baseline_data["vix"] = calculate_metrics_summary(vix_close.tolist())
    else:
        print("❌ VIX 歷史抓取失敗")
        baseline_data["vix"] = None

    try:
        url_10y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        url_2y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"
        df_10y = pd.read_csv(url_10y, na_values=".")
        df_2y = pd.read_csv(url_2y, na_values=".")
        df_10y.columns = ["DATE", "DGS10"]
        df_2y.columns = ["DATE", "DGS2"]
        df_fred = pd.merge(df_10y, df_2y, on="DATE").dropna()
        df_fred['DGS10'] = pd.to_numeric(df_fred['DGS10'])
        df_fred['DGS2'] = pd.to_numeric(df_fred['DGS2'])
        fred_spread_bps = ((df_fred['DGS10'] - df_fred['DGS2']) * 100).tolist()
        baseline_data["yield_spread"] = calculate_metrics_summary(fred_spread_bps)
    except Exception as e:
        print(f"❌ FRED 美債利差歷史計算失敗: {e}")
        baseline_data["yield_spread"] = None

    twii_close = yf_close_series("^TWII", "15y")
    if twii_close is not None:
        try:
            ma20 = twii_close.rolling(window=20).mean()
            bias = (((twii_close - ma20) / ma20) * 100).dropna().tolist()
            baseline_data["tw_bias"] = calculate_metrics_summary(bias)
        except Exception as e:
            print(f"❌ 台股乖離率歷史計算失敗: {e}")
            baseline_data["tw_bias"] = None
    else:
        baseline_data["tw_bias"] = None

    # CAPE 歷史：GitHub Shiller 資料集首選（Actions 必通），multpl 表格備援
    cape_hist = fetch_cape_history_github() or fetch_shiller_cape_history()
    baseline_data["shiller_cape"] = calculate_metrics_summary(cape_hist) if cape_hist else None

    w5000_close = yf_close_series("^W5000", "15y")
    if w5000_close is not None:
        try:
            buffett_series = (w5000_close / BASELINE_W5000) * BASELINE_BUFFETT_PCT
            # 💡【GDP 校正】歷史序列以「基準GDP / 各時點GDP」逐日校正，
            # 消除「假設GDP不變導致過去指標被高估」的結構性偏差
            gdp_full = fred_series("GDP", tail_n=120)
            if gdp_full is not None:
                base_gdp = None
                try:
                    if os.path.exists(CONFIG_PATH):
                        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                            base_gdp = json.load(f).get("buffett_baseline_gdp")
                except Exception:
                    pass
                gdp_ts = gdp_full.copy()
                gdp_ts.index = pd.to_datetime(gdp_ts.index)
                if base_gdp is None:
                    base_gdp = float(gdp_ts.iloc[-1])
                w_idx = buffett_series.index
                try:
                    w_idx = w_idx.tz_localize(None)
                except (TypeError, AttributeError):
                    pass
                buffett_series.index = w_idx
                gdp_aligned = gdp_ts.reindex(w_idx, method='ffill')
                buffett_series = (buffett_series * (float(base_gdp) / gdp_aligned)).dropna()
                print("📌 巴菲特歷史基準已完成 GDP 逐日校正")
            else:
                print("⚠️ FRED GDP 不可用，巴菲特歷史基準未做 GDP 校正（沿用固定比例）")
            baseline_data["buffett_indicator"] = calculate_metrics_summary(buffett_series.dropna().tolist())
        except Exception as e:
            print(f"❌ 巴菲特指標歷史計算失敗: {e}")
            baseline_data["buffett_indicator"] = None
    else:
        baseline_data["buffett_indicator"] = None

    baseline_data["last_updated"] = now_taiwan().strftime("%Y-%m-%d")

    try:
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 歷史基準檔寫入失敗: {e}")
    return baseline_data

def get_percentile(value, p_dict, key_name):
    p_list = []
    if p_dict and key_name in p_dict and p_dict[key_name] is not None:
        p_list = p_dict[key_name].get("percentiles", [])
    if not p_list:
        if key_name == "vix": p_list = DEFAULT_VIX_P
        elif key_name == "yield_spread": p_list = DEFAULT_SPREAD_P
        elif key_name == "tw_bias": p_list = DEFAULT_BIAS_P
        elif key_name == "shiller_cape": p_list = DEFAULT_CAPE_P
        else: return "暫無歷史基準"
    for i, p_val in enumerate(p_list):
        if value <= p_val: return f"{i + 1}%"
    return "100%"

# =========================================================================
# 📢 核心情境交叉研判模組
# =========================================================================
def get_situation_assessment(data, vix_l, yield_l, hy_l, twd_l, tw_l, pe_l):
    vix_val = data.get('vix')
    if vix_val is None: return "📊 情境研判：數據不足，暫不研判"
    other_lights = [yield_l, hy_l, twd_l, tw_l, pe_l]
    all_lights = [vix_l, yield_l, hy_l, twd_l, tw_l, pe_l]
    green_yellow_count_other = sum(1 for l in other_lights if l in ["🟢", "🟡"])
    red_count_all = sum(1 for l in all_lights if l == "🔴")
    if vix_val > 30 and green_yellow_count_other >= 4:
        return "📢 情境研判：恐慌性下殺 - 基本面未同步惡化，可考慮分批加碼"
    if vix_val > 27 and red_count_all >= 3 and hy_l == "🔴" and (yield_l in ["🟡", "🔴"]):
        return "🚨 情境研判：系統性風險 - 基本面同步惡化，暫停進場，優先保護質押維持率"
    return "📊 情境研判：正常市場波動，依總分燈號正常操作"

# =========================================================================
# 🧠 第一大核心：總經加權風控塔台
# =========================================================================
def get_risk_control_report(df, baseline_brain, taiwan_time, is_monthly_check):
    today_str = taiwan_time.strftime("%Y-%m-%d")
    data = {}

    config_data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f: config_data = json.load(f)
        except Exception as e:
            print(f"⚠️ config.json 讀取失敗: {e}")

    close_df = df.get('Close') if df is not None and hasattr(df, 'get') else None

    stale_notes = []
    def check_freshness(name, series):
        if series is None: return
        d = get_series_last_date(series)
        if d is None: return
        print(f"📅 {name} 最後資料日: {d.strftime('%m-%d')}")
        if (taiwan_time.date() - d).days > 3:
            stale_notes.append(f"- {name}：資料停留在 {d.strftime('%m-%d')}")

    def shared_or_fetch(ticker, period="50d"):
        try:
            if close_df is not None and hasattr(close_df, 'columns') and ticker in close_df.columns:
                s = close_df[ticker].dropna()
                if not s.empty: return s
        except Exception as e:
            print(f"⚠️ 共享數據取 {ticker} 失敗: {e}")
        try:
            s = yf.Ticker(ticker).history(period=period)['Close'].dropna()
            return s if not s.empty else None
        except Exception as e:
            print(f"❌ {ticker} 單獨補抓失敗: {e}")
            return None

    def load_persisted_value(value_key, date_key, max_age_days):
        val = config_data.get(value_key)
        d_str = config_data.get(date_key)
        if val is None or d_str is None: return None
        try:
            d = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            if (taiwan_time.date() - d).days <= max_age_days:
                return float(val)
        except Exception:
            pass
        return None

    # --- 1. 每日核心量化 6 大基礎資料下載 ---
    vix_series = shared_or_fetch("^VIX", "10d")
    if vix_series is None:
        vix_series = fred_series("VIXCLS", 10)
        if vix_series is not None:
            print("📌 VIX 已改用 FRED VIXCLS 備援")
    if vix_series is not None:
        check_freshness("VIX", vix_series)
        data['vix'] = float(vix_series.iloc[-1])
        data['vix_arrow'] = get_trend_arrow(vix_series)
    else:
        data['vix'], data['vix_arrow'] = None, "⏳"

    try:
        spy = yf.Ticker("SPY")
        pe_val = spy.info.get('trailingPE') or spy.fast_info.get('trailing_pe') or spy.info.get('forwardPE')
        if pe_val and pe_val > 0: data['pe_ratio'] = float(pe_val)
        else: raise ValueError("SPY info 無有效 PE")
    except Exception as e:
        print(f"⚠️ SPY PE 主路徑失敗，退回 EPS 常數備援: {e}")
        sp500_close = shared_or_fetch("^GSPC", "10d")
        if sp500_close is None:
            sp500_close = fred_series("SP500", 10)
            if sp500_close is not None:
                print("📌 S&P500 已改用 FRED SP500 備援")
        if sp500_close is not None:
            data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / SP500_EPS_TTM, 1)
        else:
            data['pe_ratio'] = None

    t10_val, t02_val = None, None
    try:
        url_10y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        url_2y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"
        r10 = requests.get(url_10y, timeout=10).text.strip().split('\n')
        r02 = requests.get(url_2y, timeout=10).text.strip().split('\n')
        for line in reversed(r10[1:]):
            p = line.split(',')
            if len(p) == 2 and p[1].strip() != '.': t10_val = float(p[1].strip()); break
        for line in reversed(r02[1:]):
            p = line.split(',')
            if len(p) == 2 and p[1].strip() != '.': t02_val = float(p[1].strip()); break
    except Exception as e:
        print(f"⚠️ FRED 美債殖利率抓取失敗，將嘗試 yfinance 備援: {e}")

    if t10_val is None or t02_val is None:
        try:
            t10_s = yf.Ticker("^TNX").history(period="5d")['Close'].dropna()
            t02_s = yf.Ticker("2YY=F").history(period="5d")['Close'].dropna()
            if not t10_s.empty and not t02_s.empty:
                t10_val = float(t10_s.iloc[-1])
                t02_val = float(t02_s.iloc[-1])
                if t10_val > 15: t10_val /= 10
                if t02_val > 15: t02_val /= 10
        except Exception as e:
            print(f"❌ 美債殖利率備援亦失敗: {e}")

    if t10_val is not None and t02_val is not None:
        data['yield_spread_bps'] = round((t10_val - t02_val) * 100, 1)
        data['yield_arrow'] = "➡️"
    else:
        data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    hyg_series = shared_or_fetch("HYG", "50d")
    if hyg_series is not None and len(hyg_series) >= 30:
        check_freshness("高收益債HYG", hyg_series)
        data['hy_momentum'] = round(((hyg_series.iloc[-1] - hyg_series.iloc[-30]) / hyg_series.iloc[-30]) * 100, 2)
        data['hy_arrow'] = get_trend_arrow(hyg_series)
    else:
        data['hy_momentum'], data['hy_arrow'] = None, "⏳"

    twd_series = shared_or_fetch("TWD=X", "50d")
    if twd_series is None or len(twd_series) < 30:
        twd_series = fred_series("DEXTAUS", 60)
        if twd_series is not None:
            print("📌 台幣匯率已改用 FRED DEXTAUS 備援")
    if twd_series is not None and len(twd_series) >= 30:
        check_freshness("台幣匯率", twd_series)
        current_twd = float(twd_series.iloc[-1])
        ma_30_twd = twd_series.iloc[-30:].mean()
        data['twd_fx'] = current_twd
        data['twd_bias_pct'] = round(((current_twd - ma_30_twd) / ma_30_twd) * 100, 2)
        data['twd_arrow'] = get_trend_arrow(twd_series)
    else:
        data['twd_fx'], data['twd_bias_pct'], data['twd_arrow'] = None, None, "⏳"

    twii_series = shared_or_fetch("^TWII", "400d")
    if twii_series is not None and len(twii_series) >= 20:
        check_freshness("台股指數", twii_series)
        current_twii = twii_series.iloc[-1]
        ma_20 = twii_series.iloc[-20:].mean()
        data['tw_bias'] = round(((current_twii - ma_20) / ma_20) * 100, 2)
        data['tw_bias_arrow'] = get_trend_arrow(twii_series)
    else:
        data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"

    w5000_series = shared_or_fetch("^W5000", "10d")
    if w5000_series is not None:
        # 💡【GDP 校正】首次成功取得 FRED GDP 時自動錨定為基準（factor 起始為 1.0），
        # 之後 GDP 每成長一分，指標自動除回一分——結構性漂移歸零，常數永不過時
        gdp_factor = 1.0
        gdp_series = fred_series("GDP", 8)
        if gdp_series is not None:
            latest_gdp = float(gdp_series.iloc[-1])
            base_gdp = config_data.get("buffett_baseline_gdp")
            if not base_gdp:
                safe_save_config_field("buffett_baseline_gdp", latest_gdp)
                base_gdp = latest_gdp
                print(f"📌 巴菲特 GDP 基準完成自我錨定: {latest_gdp:,.0f}（十億美元）")
            gdp_factor = float(base_gdp) / latest_gdp
        else:
            print("⚠️ FRED GDP 取得失敗，本日巴菲特指標未做 GDP 校正")
        data['buffett_indicator'] = round(BASELINE_BUFFETT_PCT * (float(w5000_series.iloc[-1]) / BASELINE_W5000) * gdp_factor, 1)
        safe_save_config_field("buffett_indicator_manual", data['buffett_indicator'])
        safe_save_config_field("buffett_indicator_last_updated", today_str)
    else:
        data['buffett_indicator'] = load_persisted_value("buffett_indicator_manual", "buffett_indicator_last_updated", 45)
        if data['buffett_indicator'] is not None:
            print("📌 巴菲特指標使用 config 持久化值（45天內有效）")

    # =========================================================================
    # 🧭【長線戰略層】200日均線趨勢格局（美股 / 台股）
    # 共享下載已改為400天，直接就地計算；純顯示，不參與計分
    # =========================================================================
    gspc_series = shared_or_fetch("^GSPC", "400d")
    us_regime = get_trend_regime(gspc_series)
    tw_regime = get_trend_regime(twii_series)

    # =========================================================================
    # ⚙️ 核心調度：追蹤機制狀態初始化與判定邏輯
    # =========================================================================
    pending_status = config_data.get("pending_monthly_checks", {"shiller_cape": False, "recession_prob": False})

    if is_monthly_check:
        pending_status = {"shiller_cape": False, "recession_prob": False}

    success_catch_notifications = []
    still_tracking_notifications = []
    auto_val, auto_date = None, None

    def recession_data_is_fresh(date_str):
        try:
            dt_prob = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            return (taiwan_time.date() - dt_prob).days <= 75
        except Exception:
            return False

    def persist_cape(val):
        safe_save_config_field("shiller_cape_manual", val)
        safe_save_config_field("shiller_cape_last_updated", today_str)

    # --- 執行常態月度長檢 (1號當天) ---
    if is_monthly_check:
        cape_val = fetch_cape_current()
        data['shiller_cape'] = cape_val
        pending_status["shiller_cape"] = (cape_val is None)
        if cape_val is not None:
            persist_cape(cape_val)
        else:
            data['shiller_cape'] = load_persisted_value("shiller_cape_manual", "shiller_cape_last_updated", 45)

        auto_val, auto_date = get_recession_prob_from_fred()
        if auto_val is not None:
            data['recession_prob'] = auto_val
            safe_save_config_field("recession_probability_manual", auto_val)
            safe_save_config_field("recession_probability_last_updated", auto_date)
            pending_status["recession_prob"] = not recession_data_is_fresh(auto_date)
        else:
            data['recession_prob'] = config_data.get("recession_probability_manual", None)
            pending_status["recession_prob"] = True

        safe_save_config_field("pending_monthly_checks", pending_status)

    # --- 每日補抓執行邏輯 (平日追蹤偵測) ---
    else:
        if pending_status.get("shiller_cape", False):
            cape_retry = fetch_cape_current()
            if cape_retry is not None:
                data['shiller_cape'] = cape_retry
                persist_cape(cape_retry)
                pending_status["shiller_cape"] = False
                safe_save_config_field("pending_monthly_checks", pending_status)
                success_catch_notifications.append(f"- 席勒CAPE已補獲：{cape_retry:.1f}倍（補獲於{taiwan_time.strftime('%m-%d')}）✅")
            else:
                data['shiller_cape'] = load_persisted_value("shiller_cape_manual", "shiller_cape_last_updated", 45)
                still_tracking_notifications.append("- 席勒CAPE：持續嘗試補抓中 🔄")
        else:
            data['shiller_cape'] = load_persisted_value("shiller_cape_manual", "shiller_cape_last_updated", 45)

        if pending_status.get("recession_prob", False):
            auto_val, auto_date = get_recession_prob_from_fred()
            if auto_val is not None:
                data['recession_prob'] = auto_val
                if recession_data_is_fresh(auto_date):
                    pending_status["recession_prob"] = False

                safe_save_config_field("recession_probability_manual", auto_val)
                safe_save_config_field("recession_probability_last_updated", auto_date)
                safe_save_config_field("pending_monthly_checks", pending_status)

                if not pending_status["recession_prob"]:
                    success_catch_notifications.append(f"- 聯準會衰退率已補獲：{auto_val:.1f}%（資料日期: {auto_date}）✅")
                else:
                    still_tracking_notifications.append("- 聯準會衰退率：等待FRED釋出新月份數據 🔄")
            else:
                data['recession_prob'] = config_data.get("recession_probability_manual", None)
                still_tracking_notifications.append("- 聯準會衰退率：等待FRED釋出新月份數據 🔄")
        else:
            data['recession_prob'] = config_data.get("recession_probability_manual", None)

    recession_for_scoring = data.get('recession_prob')
    rec_date_str = config_data.get("recession_probability_last_updated")
    if recession_for_scoring is not None and rec_date_str:
        try:
            rec_d = datetime.datetime.strptime(rec_date_str, "%Y-%m-%d").date()
            if (taiwan_time.date() - rec_d).days > 120:
                print("⚠️ 衰退率資料超過120天，本日不參與計分")
                recession_for_scoring = None
        except Exception:
            pass

    # =========================================================================
    # 🚦 每日指標明確 if/else 燈號與計分邏輯
    # =========================================================================
    if data.get('vix') is not None:
        vix_l = "🔴" if data['vix'] > 30 else ("🟡" if data['vix'] > 20 else "🟢")
        vix_score = 2 if data['vix'] > 30 else (1 if data['vix'] > 20 else 0)
    else:
        vix_l = "⚪"
        vix_score = 0

    if data.get('pe_ratio') is not None:
        pe_l = "🔴" if data['pe_ratio'] > 30 else ("🟡" if data['pe_ratio'] > 26 else "🟢")
        pe_score = 2 if data['pe_ratio'] > 30 else (1 if data['pe_ratio'] > 26 else 0)
    else:
        pe_l = "⚪"
        pe_score = 0

    if data.get('yield_spread_bps') is not None:
        yield_l = "🔴" if data['yield_spread_bps'] < -50 else ("🟡" if data['yield_spread_bps'] < 0 else "🟢")
        yield_score = 2 if data['yield_spread_bps'] < -50 else (1 if data['yield_spread_bps'] < 0 else 0)
    else:
        yield_l = "⚪"
        yield_score = 0

    if data.get('hy_momentum') is not None:
        hy_l = "🔴" if data['hy_momentum'] < -3.5 else ("🟡" if data['hy_momentum'] < -1.5 else "🟢")
        hy_score = 2 if data['hy_momentum'] < -3.5 else (1 if data['hy_momentum'] < -1.5 else 0)
    else:
        hy_l = "⚪"
        hy_score = 0

    if data.get('twd_bias_pct') is not None:
        twd_l = "🔴" if data['twd_bias_pct'] > 1.5 else ("🟡" if data['twd_bias_pct'] > 0.5 else "🟢")
        twd_score = 2 if data['twd_bias_pct'] > 1.5 else (1 if data['twd_bias_pct'] > 0.5 else 0)
    else:
        twd_l = "⚪"
        twd_score = 0

    if data.get('tw_bias') is not None:
        tw_l = "🔴" if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else ("🟡" if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else "🟢")
        tw_score = 2 if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else (1 if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else 0)
    else:
        tw_l = "⚪"
        tw_score = 0

    total_score = vix_score + pe_score + yield_score + hy_score + twd_score + tw_score

    n_monthly_scored = 0

    if data.get('shiller_cape') is not None:
        total_score += 0 if data['shiller_cape'] < 25 else (1 if data['shiller_cape'] < 32 else (2 if data['shiller_cape'] < 40 else 3))
        n_monthly_scored += 1

    if data.get('buffett_indicator') is not None:
        total_score += 0 if data['buffett_indicator'] < 100 else (1 if data['buffett_indicator'] < 150 else (2 if data['buffett_indicator'] < 200 else 3))
        n_monthly_scored += 1

    if recession_for_scoring is not None:
        total_score += 0 if recession_for_scoring < 15 else (1 if recession_for_scoring < 30 else (2 if recession_for_scoring < 50 else 3))
        n_monthly_scored += 1

    red_threshold = 9 + 2 * n_monthly_scored
    orange_threshold = 6 + round(4 * n_monthly_scored / 3)
    yellow_threshold = 3 + round(2 * n_monthly_scored / 3)

    if total_score >= red_threshold:
        status_light = "🔴 【四級極端風暴】請啟動質押分批解鎖退場/拉高維持率"
    elif total_score >= orange_threshold:
        status_light = "🟠 【三級高風險】減碼/停止槓桿加碼"
    elif total_score >= yellow_threshold:
        status_light = "🟡 【二級市場觀望】暫緩追高"
    else:
        status_light = "🟢 【一級安全綠燈】紀律加碼/維持常態"

    daily_lights = [vix_l, pe_l, yield_l, hy_l, twd_l, tw_l]
    missing_count = daily_lights.count("⚪")
    data_fuse_tripped = (missing_count >= 3)
    if data_fuse_tripped:
        status_light = f"⚪ 【數據斷線 {missing_count}/6】指標多數無法取得，燈號暫停研判——今日勿依系統加減碼，請查 Actions log"

    # =========================================================================
    # 📉 風險軌跡儲存 ＋ 💡【長線戰略層】分數趨勢計算（近7日均 vs 近30日均）
    # =========================================================================
    yesterday_score_text = "🔄 啟動"
    score_trend_txt = "樣本累積中（需至少7個交易日）"
    try:
        rh_data = {"records": []}
        if os.path.exists(RISK_HISTORY_FILE):
            with open(RISK_HISTORY_FILE, "r", encoding="utf-8") as f: rh_data = json.load(f)
        past_records = [r for r in rh_data.get("records", [])
                        if r.get("date") != today_str and r.get("date", "") >= SCORE_EPOCH]

        if data_fuse_tripped:
            # 斷線日：今日分數失真，不寫入、不做日對日比較，
            # 但趨勢來自過去記錄，仍然有效，照常計算顯示
            yesterday_score_text = "⚪ 斷線日不記錄"
            trend_scores = [r["total_score"] for r in past_records]
        else:
            if past_records:
                prev_score = past_records[-1]["total_score"]
                diff = total_score - prev_score
                if diff > 0: diff_txt = f"🔺+{diff}"
                elif diff < 0: diff_txt = f"🔻{diff}"
                else: diff_txt = "➡️ 持平"
                yesterday_score_text = f"{prev_score} → {total_score} ({diff_txt})"
            past_records.append({"date": today_str, "total_score": total_score})
            rh_data["records"] = past_records[-90:]
            with open(RISK_HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(rh_data, f, indent=2)
            trend_scores = [r["total_score"] for r in past_records]

        # 💡【長線戰略層】分數趨勢：近7日均 vs 近30日均，看風險水位的方向而非單日跳動
        if len(trend_scores) >= 7:
            avg7 = sum(trend_scores[-7:]) / len(trend_scores[-7:])
            avg30 = sum(trend_scores[-30:]) / len(trend_scores[-30:])
            gap = avg7 - avg30
            if gap > 0.5: trend_word = "風險升溫中 🔺"
            elif gap < -0.5: trend_word = "風險消退中 🔻"
            else: trend_word = "風險水位平穩 ➡️"
            score_trend_txt = f"近7日均 {avg7:.1f} vs 近30日均 {avg30:.1f} → {trend_word}"
    except Exception as e:
        print(f"⚠️ 風險軌跡檔讀寫失敗: {e}")

    situation_msg = get_situation_assessment(data, vix_l, yield_l, hy_l, twd_l, tw_l, pe_l)

    p_vix = get_percentile(data['vix'], baseline_brain, "vix") if data.get('vix') is not None else "暫無"
    p_spd = get_percentile(data['yield_spread_bps'], baseline_brain, "yield_spread") if data.get('yield_spread_bps') is not None else "暫無"
    p_bias = get_percentile(data['tw_bias'], baseline_brain, "tw_bias") if data.get('tw_bias') is not None else "暫無"

    vix_txt = f"{data['vix']:.2f} {data['vix_arrow']} (歷史百分位: {p_vix})" if data.get('vix') is not None else "延遲 ⏳"
    pe_txt = f"{data['pe_ratio']:.1f}倍" if data.get('pe_ratio') is not None else "延遲 ⏳"
    yield_txt = f"{data['yield_spread_bps']:.1f} bps {data['yield_arrow']} (歷史百分位: {p_spd})" if data.get('yield_spread_bps') is not None else "延遲 ⏳"
    hy_txt = f"{data['hy_momentum']:+.2f}% {data['hy_arrow']}" if data.get('hy_momentum') is not None else "延遲 ⏳"
    twd_txt = f"{data['twd_fx']:.2f} ({data['twd_bias_pct']:+.1f}%) {data['twd_arrow']}" if data.get('twd_bias_pct') is not None else "延遲 ⏳"
    tw_txt = f"{data['tw_bias']:.1f}% {data['tw_bias_arrow']} (歷史百分位: {p_bias})" if data.get('tw_bias') is not None else "延遲 ⏳"

    # 長檢估值精簡行
    lc_parts = []
    if data.get('shiller_cape') is not None: lc_parts.append(f"CAPE {data['shiller_cape']:.1f}倍")
    if data.get('buffett_indicator') is not None: lc_parts.append(f"巴菲特 {data['buffett_indicator']:.0f}%")
    if recession_for_scoring is not None: lc_parts.append(f"衰退率 {recession_for_scoring:.1f}%")
    lc_txt = " | ".join(lc_parts) if lc_parts else "暫無有效數據 ⏳"

    # =========================================================================
    # 📋 兩層式報告組裝：先戰略（長線決策依據）、後防護（短線警報器）
    # =========================================================================
    report = (
        f"🚨 【unclelee 總經加權風控塔台】\n"
        f"⏰ {taiwan_time.strftime('%m-%d %H:%M')} | 📉 軌跡: {yesterday_score_text}\n"
        f"🚦 指揮燈號：{status_light}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"{situation_msg}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🧭 【長線戰略層】槓桿部署與大方向依據\n"
        f"• 美股趨勢格局 : {format_regime(us_regime)}\n"
        f"• 台股趨勢格局 : {format_regime(tw_regime)}\n"
        f"• 10Y-2Y美債利 : {yield_txt} | 風險: {yield_l}\n"
        f"• 長檢估值({n_monthly_scored}/3) : {lc_txt}\n"
        f"• 風險分數趨勢 : {score_trend_txt}\n"
        f"   總分 {total_score}｜門檻 🟡{yellow_threshold} 🟠{orange_threshold} 🔴{red_threshold}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"⚡ 【短線防護層】維持率保衛與時機偵測\n"
        f"• VIX 恐慌指數 : {vix_txt} | 風險: {vix_l}\n"
        f"• S&P500本益比 : {pe_txt} | 風險: {pe_l}\n"
        f"• 高收益債動能 : {hy_txt} | 風險: {hy_l}\n"
        f"• 台幣匯率偏離 : {twd_txt} | 風險: {twd_l}\n"
        f"• 台股20日乖離 : {tw_txt} | 風險: {tw_l}\n"
    )

    if stale_notes:
        report += (
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"⚠️ 【資料時效警示】以下行情逾3天未更新，今日燈號僅供參考\n"
            + "\n".join(stale_notes) + "\n"
        )

    if is_monthly_check:
        p_cape = get_percentile(data['shiller_cape'], baseline_brain, "shiller_cape") if data.get('shiller_cape') is not None else "暫無歷史基準"
        p_bft = get_percentile(data['buffett_indicator'], baseline_brain, "buffett_indicator") if data.get('buffett_indicator') is not None else "暫無歷史基準"
        cape_txt = f"{data['shiller_cape']:.1f}倍 (歷史百分位: {p_cape})" if data.get('shiller_cape') is not None else "延遲 ⏳"
        bft_txt = f"{data['buffett_indicator']:.1f}% (歷史百分位: {p_bft}·僅供參考)" if data.get('buffett_indicator') is not None else "延遲 ⏳"

        ref_date = auto_date if auto_val is not None else config_data.get("recession_probability_last_updated", "未知")
        rec_txt = f"{data['recession_prob']:.1f}% (資料日期: {ref_date}，擴張期常態<1%)" if data.get('recession_prob') is not None else "未設定 ⏳"

        report += (
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📅 【每月1號大盤長檢指標】(本月成功計分 {n_monthly_scored}/3 項，門檻已同步調整)\n"
            f"• 席勒CAPE比率 : {cape_txt}\n"
            f"• 修正巴菲特指 : {bft_txt}\n"
            f"• 聯準會衰退率 : {rec_txt}\n"
        )

    if not is_monthly_check:
        if success_catch_notifications:
            report += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📌 【月度指標補獲通知】\n" + "\n".join(success_catch_notifications) + "\n"
        if still_tracking_notifications:
            report += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📌 【月度指標追蹤中】\n" + "\n".join(still_tracking_notifications) + "\n"

    return report

# =========================================================================
# 📊 第二大核心：資產再平衡決策哨兵
# =========================================================================
def get_rebalance_report(df):
    shares_00713, shares_voo, shares_smh = 10153, 28, 15
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cd = json.load(f)
                shares_00713 = cd.get("shares_00713", 10153)
                shares_voo = cd.get("shares_voo", 28)
                shares_smh = cd.get("shares_smh", 15)
        except Exception as e:
            print(f"⚠️ config.json 持股讀取失敗，使用預設值: {e}")

    target_00713, target_voo, target_smh = 0.40, 0.40, 0.20
    close_df = df.get('Close') if df is not None and hasattr(df, 'get') else None

    def safe_get_price_v3(close_df, ticker):
        try:
            fi = yf.Ticker(ticker).fast_info
            lp = None
            for key in ('last_price', 'lastPrice', 'regular_market_price'):
                try:
                    lp = fi[key] if hasattr(fi, '__getitem__') else getattr(fi, key, None)
                except Exception:
                    lp = getattr(fi, key, None)
                if lp: break
            if lp and float(lp) > 0:
                return float(lp)
        except Exception as e:
            print(f"⚠️ {ticker} fast_info 即時報價失敗，退回日線: {e}")
        try:
            if close_df is not None and hasattr(close_df, 'columns') and ticker in close_df.columns:
                series = close_df[ticker].dropna()
                if not series.empty:
                    d = get_series_last_date(series)
                    print(f"📅 {ticker} 使用日線備援，資料日: {d.strftime('%m-%d') if d else '?'}")
                    return float(series.iloc[-1])
        except Exception as e:
            print(f"⚠️ 共享數據取 {ticker} 價格失敗: {e}")
        try:
            fallback = yf.Ticker(ticker).history(period="15d")['Close'].dropna()
            if not fallback.empty:
                d = get_series_last_date(fallback)
                print(f"📅 {ticker} 使用單獨日線備援，資料日: {d.strftime('%m-%d') if d else '?'}")
                return float(fallback.iloc[-1])
        except Exception as e:
            print(f"❌ {ticker} 價格補抓失敗: {e}")
        return None

    p_voo = safe_get_price_v3(close_df, 'VOO')
    p_smh = safe_get_price_v3(close_df, 'SMH')
    usd_to_twd = safe_get_price_v3(close_df, 'TWD=X') or 32.5
    p_00713 = safe_get_price_v3(close_df, '00713.TW')

    us_market_status = "正常交易 ✅" if p_voo and p_smh else "休市 💤"

    v_00713 = shares_00713 * p_00713 if p_00713 else 0
    v_voo = shares_voo * p_voo * usd_to_twd if p_voo else 0
    v_smh = shares_smh * p_smh * usd_to_twd if p_smh else 0
    total_portfolio_value = v_00713 + v_voo + v_smh

    act_00713 = (v_00713 / total_portfolio_value) if total_portfolio_value > 0 else 0
    act_voo = (v_voo / total_portfolio_value) if total_portfolio_value > 0 else 0
    act_smh = (v_smh / total_portfolio_value) if total_portfolio_value > 0 else 0

    dev_00713 = (act_00713 - target_00713) * 100
    dev_voo = (act_voo - target_voo) * 100
    dev_smh = (act_smh - target_smh) * 100

    p_00713_txt = f"{p_00713:.1f} TWD" if p_00713 else "延遲"
    p_voo_txt = f"{p_voo:.1f} USD" if p_voo else "休市"
    p_smh_txt = f"{p_smh:.1f} USD" if p_smh else "休市"

    if not (p_00713 and p_voo and p_smh):
        missing_list = [n for n, p in [("00713", p_00713), ("VOO", p_voo), ("SMH", p_smh)] if not p]
        return (
            f"📊 【unclelee 資產再平衡決策哨兵】\n"
            f"⚪ 報價斷線：{('、'.join(missing_list))} 無法取得\n"
            f"今日市值與偏離度失真，暫停再平衡研判。請查 Actions log 確認資料源狀態。\n"
        )

    report = (
        f"📊 【unclelee 資產再平衡決策哨兵】\n"
        f"💵 匯率: {usd_to_twd:.2f} | 💰 總市值: NT$ {round(total_portfolio_value):,} 元 ({us_market_status})\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🔍 【核心配置分項指標體檢】\n"
        f"• 00713 ({shares_00713:,}股 × {p_00713_txt})\n"
        f"  💰 價值: NT$ {round(v_00713):,} 元 | 比率: {act_00713*100:.1f}% (目標 40%) | 偏離: {dev_00713:+.1f}%\n"
        f"• VOO   ({shares_voo:,}股 × {p_voo_txt})\n"
        f"  💰 價值: NT$ {round(v_voo):,} 元 | 比率: {act_voo*100:.1f}% (目標 40%) | 偏離: {dev_voo:+.1f}%\n"
        f"• SMH   ({shares_smh:,}股 × {p_smh_txt})\n"
        f"  💰 價值: NT$ {round(v_smh):,} 元 | 比率: {act_smh*100:.1f}% (目標 20%) | 偏離: {dev_smh:+.1f}%\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    )

    if p_voo and p_smh and p_00713:
        if abs(dev_00713) > 5.0 or abs(dev_voo) > 5.0 or abs(dev_smh) > 5.0:
            t_shares_00713 = round((total_portfolio_value * target_00713 - v_00713) / p_00713)
            t_shares_voo = round((total_portfolio_value * target_voo - v_voo) / (p_voo * usd_to_twd))
            t_shares_smh = round((total_portfolio_value * target_smh - v_smh) / (p_smh * usd_to_twd))
            report += (
                f"🎯 偏離過大，建議交易建議：\n"
                f"1. 00713: {'補進 +' if t_shares_00713>0 else '減碼 '}{t_shares_00713} 股\n"
                f"2. VOO  : {'補進 +' if t_shares_voo>0 else '減碼 '}{t_shares_voo} 股\n"
                f"3. SMH  : {'補進 +' if t_shares_smh>0 else '減碼 '}{t_shares_smh} 股\n"
            )
        else: report += "⚖️ 資產偏離控制在 ±5% 內，【今日建議維持不動】。\n"
    return report

def send_line_message(message_text):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        print("⚠️ LINE 環境變數未設定，跳過推播")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    chunks = [message_text[i:i+4900] for i in range(0, len(message_text), 4900)][:5]
    payload = {"to": user_id, "messages": [{"type": "text", "text": c} for c in chunks]}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"❌ LINE 推播失敗: HTTP {resp.status_code} | {resp.text[:200]}")
    except Exception as e:
        print(f"❌ LINE 推播異常: {e}")

# =========================================================================
# 🚀 核心控制台
# =========================================================================
def main():
    taiwan_time = now_taiwan()
    is_monthly_check = (taiwan_time.day == 1)

    baseline_brain = {}
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f: baseline_brain = json.load(f)
        except Exception as e:
            print(f"⚠️ 歷史基準檔讀取失敗: {e}")

    if not baseline_brain or is_monthly_check:
        try: baseline_brain = update_historical_baseline()
        except Exception as e: print(f"🚨 歷史數據更新異常: {e}")

    shared_df = None
    try:
        # 💡【長線戰略層】下載窗口 50d → 400d，供 200 日均線趨勢格局計算
        tickers = ["^VIX", "SPY", "^GSPC", "HYG", "TWD=X", "^TWII", "00713.TW", "VOO", "SMH", "^W5000"]
        shared_df = yf.download(tickers, period="400d", progress=False)
        # 💡【防禦】若 yfinance 未來將預設 group_by 改為 'ticker'（層級順序顛倒成
        # (SPY, Close)），df.get('Close') 會拿到 None、共享機制靜默退化為逐一補抓。
        # 偵測到顛倒時就地交換層級，維持 (Close, ticker) 結構。
        if shared_df is not None and isinstance(shared_df.columns, pd.MultiIndex):
            lv0 = shared_df.columns.get_level_values(0)
            lv_last = shared_df.columns.get_level_values(-1)
            if 'Close' not in lv0 and 'Close' in lv_last:
                shared_df = shared_df.swaplevel(axis=1)
                print("📌 偵測到 yfinance 欄位層級顛倒，已自動交換為 (Close, ticker) 結構")
        if shared_df is None or shared_df.empty or 'Close' not in shared_df: shared_df = None
    except Exception as e:
        print(f"⚠️ 共享行情下載失敗，各指標將自行補抓: {e}")
        shared_df = None

    risk_report = get_risk_control_report(shared_df, baseline_brain, taiwan_time, is_monthly_check)
    rebalance_report = get_rebalance_report(shared_df)

    combined_report = f"{risk_report}\n\n═══════════════════════════\n\n{rebalance_report}"
    print(combined_report)
    send_line_message(combined_report)

if __name__ == "__main__":
    main()
