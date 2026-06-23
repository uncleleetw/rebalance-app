import os
import json
import datetime
import requests
import numpy as np
import yfinance as yf
import pandas as pd

# =========================================================================
# ⚙️ 全域核心配置與校正基準
# =========================================================================
BASELINE_W5000 = 75000.0
BASELINE_BUFFETT_PCT = 225.0
BASELINE_FILE = "historical_baseline.json"
RISK_HISTORY_FILE = "risk_history.json"

DEFAULT_VIX_P = [9.8, 10.5, 11.1, 11.4, 11.8, 12.1, 12.3, 12.5, 12.7, 12.9, 13.1, 13.3, 13.4, 13.6, 13.7, 13.9, 14.0, 14.2, 14.3, 14.5, 14.6, 14.7, 14.9, 15.0, 15.1, 15.3, 15.4, 15.5, 15.7, 15.8, 15.9, 16.1, 16.2, 16.4, 16.5, 16.7, 16.8, 17.0, 17.1, 17.3, 17.4, 17.6, 17.7, 17.9, 18.1, 18.2, 18.4, 18.6, 18.8, 19.0, 19.2, 19.4, 19.6, 19.8, 20.0, 20.3, 20.5, 20.8, 21.1, 21.3, 21.6, 21.9, 22.2, 22.6, 22.9, 23.3, 23.7, 24.1, 24.6, 25.1, 25.6, 26.1, 26.6, 27.2, 27.8, 28.5, 29.2, 30.0, 31.0, 31.9, 32.9, 34.0, 35.3, 36.8, 38.2, 39.8, 41.5, 43.1, 45.0, 47.1, 49.9, 53.0, 56.4, 60.1, 64.3, 69.1, 73.6, 78.4, 82.6, 85.0]
DEFAULT_SPREAD_P = [-90.0, -82.0, -75.0, -70.0, -65.0, -61.0, -58.0, -54.0, -51.0, -48.0, -45.0, -42.0, -39.0, -37.0, -34.0, -32.0, -29.0, -27.0, -24.0, -22.0, -19.0, -17.0, -15.0, -12.0, -10.0, -8.0, -5.0, -3.0, -1.0, 1.0, 4.0, 6.0, 9.0, 11.0, 14.0, 16.0, 19.0, 22.0, 24.0, 27.0, 30.0, 33.0, 35.0, 38.0, 41.0, 44.0, 47.0, 50.0, 53.0, 56.0, 59.0, 62.0, 65.0, 68.0, 71.0, 74.0, 78.0, 81.0, 84.0, 87.0, 91.0, 94.0, 98.0, 102.0, 105.0, 110.0, 114.0, 118.0, 122.0, 126.0, 131.0, 136.0, 140.0, 145.0, 150.0, 155.0, 161.0, 166.0, 172.0, 178.0, 184.0, 191.0, 198.0, 206.0, 214.0, 222.0, 230.0, 240.0, 249.0, 258.0, 267.0, 276.0, 285.0, 294.0, 303.0, 312.0, 321.0, 330.0, 340.0, 350.0]
DEFAULT_BIAS_P = [-9.5, -8.2, -7.1, -6.3, -5.7, -5.2, -4.8, -4.4, -4.1, -3.8, -3.5, -3.3, -3.1, -2.9, -2.7, -2.5, -2.3, -2.1, -2.0, -1.8, -1.7, -1.6, -1.4, -1.3, -1.2, -1.1, -1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9, 3.0, 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.9, 4.0, 4.2, 4.3, 4.5, 4.6, 4.8, 5.0, 5.2, 5.4, 5.6, 5.8, 6.0, 6.2, 6.5, 6.7, 7.0, 7.3, 7.7, 8.1, 8.5, 9.0, 9.5, 10.2, 11.0, 11.9, 13.1, 14.5]

# =========================================================================
# 🛠️ 共通工具函式與大腦核心
# =========================================================================
def get_trend_arrow(series):
    if series is None or len(series) < 2: return "➡️"
    current = series.iloc[-1]
    prev = series.iloc[-2]
    if current > prev: return "🔺"
    elif current < prev: return "🔻"
    return "➡️"

def fetch_shiller_cape_real():
    url = "https://www.multpl.com/shiller-pe"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            html = response.text
            if 'id="current"' in html:
                part = html.split('id="current"')[1].split('</div')[0]
                if '<b>' in part:
                    val_str = part.split('<b>')[1].split('</b>')[0].strip()
                    return [float(val_str)] * 150
        return None
    except Exception as e:
        print(f"❌ Shiller CAPE 數據提取異常: {e}")
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

    try:
        vix_df = yf.download("^VIX", period="15y", progress=False)
        vix_close = vix_df['Close'].dropna().tolist() if 'Close' in vix_df.columns else []
        baseline_data["vix"] = calculate_metrics_summary(vix_close)
    except Exception as e: print(f"❌ VIX 歷史抓取失敗: {e}")

    try:
        url_10y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        url_2y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"
        df_10y = pd.read_csv(url_10y, na_values=".")
        df_2y = pd.read_csv(url_2y, na_values=".")
        df_fred = pd.merge(df_10y, df_2y, on="DATE").dropna()
        df_fred['DGS10'] = pd.to_numeric(df_fred['DGS10'])
        df_fred['DGS2'] = pd.to_numeric(df_fred['DGS2'])
        fred_spread_bps = ((df_fred['DGS10'] - df_fred['DGS2']) * 100).tolist()
        baseline_data["yield_spread"] = calculate_metrics_summary(fred_spread_bps)
    except Exception as e:
        print(f"❌ FRED 美債利差歷史計算失敗: {e}")
        baseline_data["yield_spread"] = None

    try:
        tw_df = yf.download("^TWII", period="15y", progress=False)
        if 'Close' in tw_df.columns:
            close_series = tw_df['Close']
            ma20 = close_series.rolling(window=20).mean()
            bias = (((close_series - ma20) / ma20) * 100).dropna().tolist()
            baseline_data["tw_bias"] = calculate_metrics_summary(bias)
    except Exception as e: print(f"❌ 台股乖離率歷史計算失敗: {e}")

    cape_data = fetch_shiller_cape_real()
    baseline_data["shiller_cape"] = calculate_metrics_summary(cape_data) if cape_data else None

    try:
        w5000_df = yf.download("^W5000", period="15y", progress=False)
        if 'Close' in w5000_df.columns:
            buffett_series = (w5000_df['Close'] / BASELINE_W5000) * BASELINE_BUFFETT_PCT
            baseline_data["buffett_indicator"] = calculate_metrics_summary(buffett_series.dropna().tolist())
    except Exception as e: print(f"❌ 巴菲特指標歷史計算失敗: {e}")

    baseline_data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, ensure_ascii=False, indent=2)
    except: pass
    return baseline_data

def get_percentile(value, p_dict, key_name):
    p_list = []
    if p_dict and key_name in p_dict and p_dict[key_name] is not None:
        p_list = p_dict[key_name].get("percentiles", [])
        
    if not p_list:
        if key_name == "vix": p_list = DEFAULT_VIX_P
        elif key_name == "yield_spread": p_list = DEFAULT_SPREAD_P
        elif key_name == "tw_bias": p_list = DEFAULT_BIAS_P
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
# 🧠 第一大核心：總經加權風控塔台 (🛠️ 已補回 None 隔離與 90 天上限)
# =========================================================================
def get_risk_control_report(df, baseline_brain):
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    today_str = taiwan_time.strftime("%Y-%m-%d")
    is_monthly_check = (taiwan_time.day == 1)
    data = {}

    config_data = {}
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f: config_data = json.load(f)
        except: pass

    close_df = df.get('Close') if df is not None and hasattr(df, 'get') else None

    # --- 1. VIX 恐慌指數 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and '^VIX' in close_df.columns:
            vix_series = close_df['^VIX'].dropna()
        else:
            vix_series = yf.Ticker("^VIX").history(period="10d")['Close'].dropna()
        if not vix_series.empty:
            data['vix'] = float(vix_series.iloc[-1])
            data['vix_arrow'] = get_trend_arrow(vix_series)
        else: data['vix'], data['vix_arrow'] = None, "⏳"
    except: data['vix'], data['vix_arrow'] = None, "⏳"

    # --- 2. S&P 500 本益比 ---
    try:
        spy = yf.Ticker("SPY")
        pe_val = spy.info.get('trailingPE') or spy.fast_info.get('trailing_pe') or spy.info.get('forwardPE')
        if pe_val and pe_val > 0: data['pe_ratio'] = float(pe_val)
        else:
            if close_df is not None and hasattr(close_df, 'columns') and '^GSPC' in close_df.columns:
                sp500_close = close_df['^GSPC'].dropna()
            else:
                sp500_close = yf.Ticker("^GSPC").history(period="10d")['Close'].dropna()
            if not sp500_close.empty:
                data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / 238.5, 1)
            else: data['pe_ratio'] = None
    except: data['pe_ratio'] = None

    # --- 3. 10Y-2Y 美債利差 ---
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
    except: pass

    if t10_val is None or t02_val is None:
        try:
            t10_s = yf.Ticker("^TNX").history(period="5d")['Close'].dropna()
            t02_s = yf.Ticker("2YY=F").history(period="5d")['Close'].dropna()
            if not t10_s.empty and not t02_s.empty:
                t10_val = float(t10_s.iloc[-1])
                t02_val = float(t02_s.iloc[-1])
                if t10_val > 15: t10_val /= 10
                if t02_val > 15: t02_val /= 10
        except: pass

    try:
        if t10_val is not None and t02_val is not None:
            data['yield_spread_bps'] = round((t10_val - t02_val) * 100, 1)
            data['yield_arrow'] = "➡️"
        else: raise Exception("斷訊")
    except: data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    # --- 4. 高收益債變化率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and 'HYG' in close_df.columns:
            hyg_series = close_df['HYG'].dropna()
        else:
            hyg_series = yf.Ticker("HYG").history(period="50d")['Close'].dropna()
        if len(hyg_series) >= 30:
            data['hy_oas'] = round(((hyg_series.iloc[-1] - hyg_series.iloc[-30]) / hyg_series.iloc[-30]) * 100, 2)
            data['hy_arrow'] = get_trend_arrow(hyg_series)
        else: data['hy_oas'], data['hy_arrow'] = None, "⏳"
    except: data['hy_oas'], data['hy_arrow'] = None, "⏳"

    # --- 5. 台幣兌美元匯率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and 'TWD=X' in close_df.columns:
            twd_series = close_df['TWD=X'].dropna()
        else:
            twd_series = yf.Ticker("TWD=X").history(period="50d")['Close'].dropna()
        if len(twd_series) >= 30:
            current_twd = float(twd_series.iloc[-1])
            ma_30_twd = twd_series.iloc[-30:].mean()
            data['twd_fx'] = current_twd
            data['twd_bias_pct'] = round(((current_twd - ma_30_twd) / ma_30_twd) * 100, 2)
            data['twd_arrow'] = get_trend_arrow(twd_series)
        else: data['twd_fx'], data['twd_bias_pct'], data['twd_arrow'] = None, None, "⏳"
    except: data['twd_fx'], data['twd_bias_pct'], data['twd_arrow'] = None, None, "⏳"

    # --- 6. 台股加權指數 20日乖離率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and '^TWII' in close_df.columns:
            twii_series = close_df['^TWII'].dropna()
        else:
            twii_series = yf.Ticker("^TWII").history(period="50d")['Close'].dropna()
        if len(twii_series) >= 20:
            current_twii = twii_series.iloc[-1]
            ma_20 = twii_series.iloc[-20:].mean()
            data['tw_bias'] = round(((current_twii - ma_20) / ma_20) * 100, 2)
            data['tw_bias_arrow'] = get_trend_arrow(twii_series)
        else: data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"
    except: data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"

    # --- 月度核心指標數據抓取 ---
    if is_monthly_check:
        try:
            current_cape_url = "https://www.multpl.com/shiller-pe"
            current_cape_resp = requests.get(current_cape_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
            real_cape_val = float(current_cape_resp.split('id="current"')[1].split('<b>')[1].split('</b>')[0].strip())
            data['shiller_cape'] = real_cape_val
        except: data['shiller_cape'] = None

        try:
            if close_df is not None and hasattr(close_df, 'columns') and '^W5000' in close_df.columns:
                w5000_val = close_df['^W5000'].dropna().iloc[-1]
            else:
                w5000_val = yf.Ticker("^W5000").history(period="10d")['Close'].dropna().iloc[-1]
            data['buffett_indicator'] = round(BASELINE_BUFFETT_PCT * (w5000_val / BASELINE_W5000), 1)
        except: data['buffett_indicator'] = None

        data['recession_prob'] = config_data.get("recession_probability_manual", None)

    # =========================================================================
    # 🚦 燈號統計 (🛠️ 修正：先判斷 is not None，缺失時強制為 ⚪ 且不計分)
    # =========================================================================
    total_score = 0
    
    # 1. VIX 指數
    if data.get('vix') is not None:
        vix_l = "🔴" if data['vix'] > 30 else ("🟡" if data['vix'] > 20 else "🟢")
        total_score += 2 if data['vix'] > 30 else (1 if data['vix'] > 20 else 0)
    else:
        vix_l = "⚪"

    # 2. S&P500 本益比
    if data.get('pe_ratio') is not None:
        pe_l = "🔴" if data['pe_ratio'] > 30 else ("🟡" if data['pe_ratio'] > 26 else "🟢")
        total_score += 2 if data['pe_ratio'] > 30 else (1 if data['pe_ratio'] > 26 else 0)
    else:
        pe_l = "⚪"

    # 3. 10Y-2Y 美債利差
    if data.get('yield_spread_bps') is not None:
        yield_l = "🔴" if data['yield_spread_bps'] < -50 else ("🟡" if data['yield_spread_bps'] < 0 else "🟢")
        total_score += 2 if data['yield_spread_bps'] < -50 else (1 if data['yield_spread_bps'] < 0 else 0)
    else:
        yield_l = "⚪"

    # 4. 高收益債動能
    if data.get('hy_oas') is not None:
        hy_l = "🔴" if data['hy_oas'] < -3.5 else ("🟡" if data['hy_oas'] < -1.5 else "🟢")
        total_score += 2 if data['hy_oas'] < -3.5 else (1 if data['hy_oas'] < -1.5 else 0)
    else:
        hy_l = "⚪"

    # 5. 台幣匯率偏離
    if data.get('twd_bias_pct') is not None:
        twd_l = "🔴" if data['twd_bias_pct'] > 1.5 else ("🟡" if data['twd_bias_pct'] > 0.5 else "🟢")
        total_score += 2 if data['twd_bias_pct'] > 1.5 else (1 if data['twd_bias_pct'] > 0.5 else 0)
    else:
        twd_l = "⚪"

    # 6. 台股20日乖離
    if data.get('tw_bias') is not None:
        tw_l = "🔴" if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else ("🟡" if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else "🟢")
        total_score += 2 if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else (1 if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else 0)
    else:
        tw_l = "⚪"

    # 月度長檢計分附加
    if is_monthly_check:
        if data.get('shiller_cape') is not None:
            total_score += 0 if data['shiller_cape'] < 25 else (1 if data['shiller_cape'] < 32 else (2 if data['shiller_cape'] < 40 else 3))
        if data.get('buffett_indicator') is not None:
            total_score += 0 if data['buffett_indicator'] < 100 else (1 if data['buffett_indicator'] < 150 else (2 if data['buffett_indicator'] < 200 else 3))
        if data.get('recession_prob') is not None:
            total_score += 0 if data['recession_prob'] < 15 else (1 if data['recession_prob'] < 30 else (2 if data['recession_prob'] < 50 else 3))

    # 指揮決策燈號判定
    if is_monthly_check:
        if total_score >= 15: status_light = "🔴 【四級極端風暴】請啟動質押分批解鎖退場/拉高維持率"
        elif total_score >= 10: status_light = "🟠 【三級高風險】減碼/停止槓桿加碼"
        elif total_score >= 5: status_light = "🟡 【二級市場觀望】暫緩追高"
        else: status_light = "🟢 【一級安全綠燈】紀律加碼/維持常態"
    else:
        if total_score >= 9: status_light = "🔴 【四級極端風暴】請啟動質押分批解鎖退場/拉高維持率"
        elif total_score >= 6: status_light = "🟠 【三級高風險】減碼/停止槓桿加碼"
        elif total_score >= 3: status_light = "🟡 【二級市場觀望】暫緩追高"
        else: status_light = "🟢 【一級安全綠燈】紀律加碼/維持常態"

    # 🛠️ 修正：風險歷史軌跡去重寫入，並強制加上 [ -90: ] 滑動視窗上限
    yesterday_score_text = "🔄 啟動"
    try:
        rh_data = {"records": []}
        if os.path.exists(RISK_HISTORY_FILE):
            with open(RISK_HISTORY_FILE, "r", encoding="utf-8") as f: rh_data = json.load(f)
        past_records = [r for r in rh_data.get("records", []) if r.get("date") != today_str]
        if past_records:
            prev_score = past_records[-1]["total_score"]
            diff = total_score - prev_score
            arrow = "🔺+" if diff > 0 else ("🔻" if diff < 0 else "➡️ ")
            lbl = "持平" if diff == 0 else ""
            yesterday_score_text = f"{prev_score} → {total_score} ({arrow}{diff}{lbl})"
        past_records.append({"date": today_str, "total_score": total_score})
        
        # ⚡ 補回 90 天上限避免檔案隨時間無限增長
        rh_data["records"] = past_records[-90:]
        with open(RISK_HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(rh_data, f, indent=2)
    except Exception as e: print(f"⚠️ 軌跡讀寫失敗: {e}")

    situation_msg = get_situation_assessment(data, vix_l, yield_l, hy_l, twd_l, tw_l, pe_l)

    p_vix = get_percentile(data['vix'], baseline_brain, "vix") if data.get('vix') is not None else "暫無"
    p_spd = get_percentile(data['yield_spread_bps'], baseline_brain, "yield_spread") if data.get('yield_spread_bps') is not None else "暫無"
    p_bias = get_percentile(data['tw_bias'], baseline_brain, "tw_bias") if data.get('tw_bias') is not None else "暫無"

    vix_txt = f"{data['vix']:.2f} {data['vix_arrow']} (歷史百分位: {p_vix})" if data.get('vix') is not None else "延遲 ⏳"
    pe_txt = f"{data['pe_ratio']:.1f}倍" if data.get('pe_ratio') is not None else "延遲 ⏳"
    yield_txt = f"{data['yield_spread_bps']:.1f} bps {data['yield_arrow']} (歷史百分位: {p_spd})" if data.get('yield_spread_bps') is not None else "延遲 ⏳"
    hy_txt = f"{data['hy_oas']:+.2f}% {data['hy_arrow']}" if data.get('hy_oas') is not None else "延遲 ⏳"
    twd_txt = f"{data['twd_fx']:.2f} ({data['twd_bias_pct']:+.1f}%) {data['twd_arrow']}" if data.get('twd_bias_pct') is not None else "延遲 ⏳"
    tw_txt = f"{data['tw_bias']:.1f}% {data['tw_bias_arrow']} (歷史百分位: {p_bias})" if data.get('tw_bias') is not None else "延遲 ⏳"

    report = (
        f"🚨 【unclelee 總經加權風控塔台】\n"
        f"⏰ {taiwan_time.strftime('%m-%d %H:%M')} | 📉 軌跡: {yesterday_score_text}\n"
        f"🚦 指揮燈號：{status_light}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"{situation_msg}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📊 【每日核心量化指標體檢】\n"
        f"• VIX 恐慌指數 : {vix_txt} | 風險: {vix_l}\n"
        f"• S&P500本益比 : {pe_txt} | 風險: {pe_l}\n"
        f"• 10Y-2Y美債利 : {yield_txt} | 風險: {yield_l}\n"
        f"• 高收益債動能 : {hy_txt} | 風險: {hy_l}\n"
        f"• 台幣匯率偏離 : {twd_txt} | 風險: {twd_l}\n"
        f"• 台股20日乖離 : {tw_txt} | 風險: {tw_l}\n"
    )

    if is_monthly_check:
        p_cape = get_percentile(data['shiller_cape'], baseline_brain, "shiller_cape") if data.get('shiller_cape') is not None else "暫無歷史基準"
        p_bft = get_percentile(data['buffett_indicator'], baseline_brain, "buffett_indicator") if data.get('buffett_indicator') is not None else "暫無歷史基準"
        
        cape_txt = f"{data['shiller_cape']:.1f}倍 (歷史百分位: {p_cape})" if data.get('shiller_cape') is not None else "延遲 ⏳"
        bft_txt = f"{data['buffett_indicator']:.1f}% (歷史百分位: {p_bft})" if data.get('buffett_indicator') is not None else "延遲 ⏳"
        rec_txt = f"{data['recession_prob']:.1f}%" if data.get('recession_prob') is not None else "未設定 ⏳"
        
        report += (
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📅 【每月1號大盤長檢指標】\n"
            f"• 席勒CAPE比率 : {cape_txt}\n"
            f"• 修正巴菲特指 : {bft_txt}\n"
            f"• 聯準會衰退率 : {rec_txt}\n"
        )
    return report

# =========================================================================
# 📊 第二大核心：資產再平衡決策哨兵
# =========================================================================
def get_rebalance_report(df):
    config_file = "config.json"
    shares_00713, shares_voo, shares_smh = 10153, 28, 15
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cd = json.load(f)
                shares_00713 = cd.get("shares_00713", 10153)
                shares_voo = cd.get("shares_voo", 28)
                shares_smh = cd.get("shares_smh", 15)
        except: pass

    target_00713, target_voo, target_smh = 0.40, 0.40, 0.20
    close_df = df.get('Close') if df is not None and hasattr(df, 'get') else None

    def safe_get_price_v3(close_df, ticker):
        try:
            if close_df is not None and hasattr(close_df, 'columns') and ticker in close_df.columns:
                series = close_df[ticker].dropna()
                if not series.empty: return float(series.iloc[-1])
        except: pass
        try:
            fallback = yf.Ticker(ticker).history(period="15d")['Close'].dropna()
            if not fallback.empty: return float(fallback.iloc[-1])
        except: pass
        return None

    p_voo = safe_get_price_v3(close_df, 'VOO')
    p_smh = safe_get_price_v3(close_df, 'SMH')
    usd_to_twd = safe_get_price_v3(close_df, 'TWD=X') or 32.5
    p_00713 = safe_get_price_v3(close_df, '00713.TW')
    if p_00713 is None:
        try: p_00713 = float(yf.Ticker("00713.TW").fast_info.get('last_price'))
        except: p_00713 = None

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
    if not token or not user_id: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": message_text}]}
    try: requests.post(url, headers=headers, json=payload)
    except: pass

# =========================================================================
# 🚀 核心控制台
# =========================================================================
def main():
    today = datetime.datetime.now()
    is_monthly_check = (today.day == 1)

    baseline_brain = {}
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r", encoding="utf-8") as f: baseline_brain = json.load(f)
        except: pass

    if not baseline_brain or is_monthly_check:
        try:
            baseline_brain = update_historical_baseline()
        except Exception as e: print(f"🚨 歷史數據更新異常: {e}")

    shared_df = None
    try:
        tickers = ["^VIX", "SPY", "^GSPC", "HYG", "TWD=X", "^TWII", "00713.TW", "VOO", "SMH"]
        if is_monthly_check: tickers.append("^W5000")
        shared_df = yf.download(tickers, period="50d", progress=False)
        if shared_df is None or shared_df.empty or 'Close' not in shared_df: shared_df = None
    except: shared_df = None

    risk_report = get_risk_control_report(shared_df, baseline_brain)
    rebalance_report = get_rebalance_report(shared_df)
    
    combined_report = f"{risk_report}\n\n═══════════════════════════\n\n{rebalance_report}"
    send_line_message(combined_report)

if __name__ == "__main__":
    main()
