import os
import json
import datetime
import requests
import numpy as np
import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup

# =========================================================================
# ⚙️ 全域核心配置與校正基準
# =========================================================================
BASELINE_W5000 = 75000.0
BASELINE_BUFFETT_PCT = 225.0
BASELINE_FILE = "historical_baseline.json"

# =========================================================================
# 🛠️ 共通工具函式與大腦核心
# =========================================================================
def get_trend_arrow(series):
    """根據過去數據計算最新一天相較於前幾天的趨勢箭頭"""
    if series is None or len(series) < 2:
        return "➡️"
    current = series.iloc[-1]
    prev = series.iloc[-2]
    if current > prev: return "🔺"
    elif current < prev: return "🔻"
    return "➡️"

def fetch_shiller_cape_real():
    """嘗試爬取 multpl.com 的歷史月度 CAPE 數據，若失敗則回傳 None"""
    url = "https://www.multpl.com/shiller-pe/table/by-month"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            dfs = pd.read_html(response.text)
            if dfs:
                df = dfs[0]
                df.columns = ['Date', 'Value']
                cape_values = pd.to_numeric(df['Value'].str.split().str[0], errors='coerce').dropna().tolist()
                if len(cape_values) > 100:
                    return cape_values
        return None
    except Exception as e:
        print(f"❌ Shiller CAPE 歷史數據爬取異常: {e}")
        return None

def calculate_metrics_summary(data_list):
    """計算結構要求的 min, median, max 與 100階百分位"""
    if not data_list:
        return None
    arr = np.array(data_list)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return None
    p_tiles = [float(np.percentile(arr, i)) for i in range(1, 101)]
    return {
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
        "percentiles": p_tiles
    }

def update_historical_baseline():
    """核心大腦功能：每逢 1 號背景自動重刷 15 年歷史百分位大數據 (🛠️ 已對齊 FRED 與安全機制)"""
    print("🔄 [歷史基準大腦] 正在背景建構/更新五大指標 15 年歷史百分位數據庫...")
    baseline_data = {}

    # 1. VIX 恐慌指數 (yfinance 15y)
    try:
        vix_df = yf.download("^VIX", period="15y", progress=False)
        vix_close = vix_df['Close'].dropna().tolist() if 'Close' in vix_df.columns else []
        baseline_data["vix"] = calculate_metrics_summary(vix_close)
    except Exception as e:
        print(f"❌ VIX 歷史抓取失敗: {e}")

    # 2. 10Y-2Y 美債利差 (🛠️ 修正：優先且無條件改用 FRED 權威歷史 CSV 進行高精度日期對齊)
    try:
        url_10y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        url_2y = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"
        
        df_10y = pd.read_csv(url_10y, na_values=".")
        df_2y = pd.read_csv(url_2y, na_values=".")
        
        df_fred = pd.merge(df_10y, df_2y, on="DATE").dropna()
        df_fred['DGS10'] = pd.to_numeric(df_fred['DGS10'])
        df_fred['DGS2'] = pd.to_numeric(df_fred['DGS2'])
        
        # 轉成 bps 單位基準
        fred_spread_bps = ((df_fred['DGS10'] - df_fred['DGS2']) * 100).tolist()
        baseline_data["yield_spread"] = calculate_metrics_summary(fred_spread_bps)
    except Exception as e:
        print(f"❌ FRED 美債利差歷史計算失敗，進入降級隔離線: {e}")
        baseline_data["yield_spread"] = None

    # 3. 台股 20 日乖離率 (^TWII 15y)
    try:
        tw_df = yf.download("^TWII", period="15y", progress=False)
        if 'Close' in tw_df.columns:
            close_series = tw_df['Close']
            ma20 = close_series.rolling(window=20).mean()
            bias = (((close_series - ma20) / ma20) * 100).dropna().tolist()
            baseline_data["tw_bias"] = calculate_metrics_summary(bias)
    except Exception as e:
        print(f"❌ 台股乖離率歷史計算失敗: {e}")

    # 4. 席勒 CAPE 比率 (🛠️ 修正：爬蟲失敗直接記為 None 絕不捏造)
    cape_data = fetch_shiller_cape_real()
    baseline_data["shiller_cape"] = calculate_metrics_summary(cape_data) if cape_data else None

    # 5. 巴菲特指標 (W5000 歷史 15 年校正公式回推)
    try:
        w5000_df = yf.download("^W5000", period="15y", progress=False)
        if 'Close' in w5000_df.columns:
            buffett_series = (w5000_df['Close'] / BASELINE_W5000) * BASELINE_BUFFETT_PCT
            baseline_data["buffett_indicator"] = calculate_metrics_summary(buffett_series.dropna().tolist())
    except Exception as e:
        print(f"❌ 巴菲特指標歷史計算失敗: {e}")

    baseline_data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d")

    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, ensure_ascii=False, indent=2)
    print(f"💾 歷史基準值更新成功！已儲存至 {BASELINE_FILE}")
    return baseline_data

def get_percentile(value, p_dict, key_name):
    """安全查表函式：精確獲取百分位，若缺乏基準數據則回傳暫無歷史基準 (🛠️ 修正問題1)"""
    if not p_dict or key_name not in p_dict or p_dict[key_name] is None: 
        return "暫無歷史基準"
    p_list = p_dict[key_name].get("percentiles", [])
    if not p_list: 
        return "暫無歷史基準"
    for i, p_val in enumerate(p_list):
        if value <= p_val:
            return f"{i + 1}%"
    return "100%"

# =========================================================================
# 🧠 第一大核心：總經加權風控塔台
# =========================================================================
def get_risk_control_report(df, baseline_brain):
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    today_str = taiwan_time.strftime("%Y-%m-%d")
    is_monthly_check = (taiwan_time.day == 1)
    data = {}
    
    config_data = {}
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f: config_data = json.load(f)
        except: pass

    close_df = df.get('Close') if df is not None and hasattr(df, 'get') else None

    # =========================================================================
    # 📆 每日核心量化指標數據抓取
    # =========================================================================
    # --- 1. VIX 恐慌指數 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and '^VIX' in close_df.columns:
            vix_series = close_df['^VIX'].dropna()
        else:
            vix_series = yf.Ticker("^VIX").history(period="10d")['Close'].dropna()
        data['vix'] = float(vix_series.iloc[-1])
        data['vix_arrow'] = get_trend_arrow(vix_series)
    except:
        data['vix'], data['vix_arrow'] = None, "⏳"

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
            data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / 238.5, 1)
    except:
        data['pe_ratio'] = None

    # --- 3. 10Y-2Y 美債利差 (FRED 官方線路優先) ---
    t10_val, t02_val = None, None
    t10_src, t02_src = "未取得", "未取得"

    def get_treasury_yield_from_fred(series_id):
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            lines = resp.text.strip().split('\n')
            for line in reversed(lines[1:]):
                parts = line.split(',')
                if len(parts) == 2 and parts[1].strip() != '.':
                    val = float(parts[1].strip())
                    return val, f"FRED({series_id})"
            return None, "空值"
        except:
            return None, "連線失敗"

    t10_val, t10_src = get_treasury_yield_from_fred("DGS10")
    t02_val, t02_src = get_treasury_yield_from_fred("DGS2")

    if t10_val is None:
        try:
            t10_tk = yf.Ticker("^TNX")
            t10_val = t10_tk.fast_info.get('last_price') or t10_tk.info.get('regularMarketPrice')
            if t10_val is None: t10_val = float(t10_tk.history(period="15d")['Close'].dropna().iloc[-1])
            if t10_val > 15: t10_val /= 10
            t10_src = "Yahoo備援"
        except: pass

    if t02_val is None:
        try:
            t02_tk = yf.Ticker("2YY=F")
            t02_val = t02_tk.fast_info.get('last_price') or t02_tk.info.get('regularMarketPrice')
            if t02_val is None: t02_val = float(t02_tk.history(period="15d")['Close'].dropna().iloc[-1])
            if t02_val > 15: t02_val /= 10
            t02_src = "Yahoo備援"
        except: pass

    try:
        if t10_val is not None and t02_val is not None:
            calc_spread_bps = round((t10_val - t02_val) * 100, 1)
            if abs(calc_spread_bps) > 300.0: raise ValueError("利差異常熔斷")
            data['yield_spread_bps'] = calc_spread_bps
            data['yield_arrow'] = "➡️"
        else: raise Exception("全線斷訊")
    except:
        data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    # --- 4. 高收益債變化率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and 'HYG' in close_df.columns:
            hyg_series = close_df['HYG'].dropna()
        else:
            hyg_series = yf.Ticker("HYG").history(period="50d")['Close'].dropna()
        data['hy_oas'] = round(((hyg_series.iloc[-1] - hyg_series.iloc[-30]) / hyg_series.iloc[-30]) * 100, 2)
        data['hy_arrow'] = get_trend_arrow(hyg_series)
    except: data['hy_oas'], data['hy_arrow'] = None, "⏳"

    # --- 5. 台幣兌美元匯率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and 'TWD=X' in close_df.columns:
            twd_series = close_df['TWD=X'].dropna()
        else:
            twd_series = yf.Ticker("TWD=X").history(period="50d")['Close'].dropna()
        current_twd = float(twd_series.iloc[-1])
        ma_30_twd = twd_series.iloc[-30:].mean()
        data['twd_fx'] = current_twd
        data['twd_bias_pct'] = round(((current_twd - ma_30_twd) / ma_30_twd) * 100, 2)
        data['twd_arrow'] = get_trend_arrow(twd_series)
    except: data['twd_fx'], data['twd_bias_pct'], data['twd_arrow'] = None, None, "⏳"

    # --- 6. 台股加權指數 20日乖離率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and '^TWII' in close_df.columns:
            twii_series = close_df['^TWII'].dropna()
        else:
            twii_series = yf.Ticker("^TWII").history(period="50d")['Close'].dropna()
        current_twii = twii_series.iloc[-1]
        ma_20 = twii_series.iloc[-20:].mean()
        data['tw_bias'] = round(((current_twii - ma_20) / ma_20) * 100, 2)
        data['tw_bias_arrow'] = get_trend_arrow(twii_series)
    except: data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"

    # =========================================================================
    # 📅 月度核心指標數據抓取 (僅限每月 1 號)
    # =========================================================================
    if is_monthly_check:
        try:
            resp = requests.get("https://www.multpl.com/shiller-pe", timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            cape_text = soup.find('div', {'id': 'current'}).find('b').text
            data['shiller_cape'] = float(cape_text.strip())
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
    # 🚦 燈號級距與加權總分計算
    # =========================================================================
    total_score = 0
    p_vix = get_percentile(data.get('vix', 0), baseline_brain, "vix") if data.get('vix') else "暫無"
    p_spd = get_percentile(data.get('yield_spread_bps', 0), baseline_brain, "yield_spread") if data.get('yield_spread_bps') else "暫無"
    p_bias = get_percentile(data.get('tw_bias', 0), baseline_brain, "tw_bias") if data.get('tw_bias') else "暫無"

    if data.get('vix') is not None:
        vix_txt = f"{data['vix']:.2f} {data['vix_arrow']} (歷史百分位: {p_vix})"
        vix_l = "🔴" if data['vix'] > 30 else ("🟡" if data['vix'] > 20 else "🟢")
        total_score += 2 if data['vix'] > 30 else (1 if data['vix'] > 20 else 0)
    else: vix_txt, vix_l = "延遲 ⏳", "⚪"

    if data.get('pe_ratio') is not None:
        pe_txt = f"{data['pe_ratio']:.1f}倍"
        pe_l = "🔴" if data['pe_ratio'] > 30 else ("🟡" if data['pe_ratio'] > 26 else "🟢")
        total_score += 2 if data['pe_ratio'] > 30 else (1 if data['pe_ratio'] > 26 else 0)
    else: pe_txt, pe_l = "延遲 ⏳", "⚪"

    if data.get('yield_spread_bps') is not None:
        yield_txt = f"{data['yield_spread_bps']:.1f} bps {data['yield_arrow']} (歷史百分位: {p_spd})"
        yield_l = "🔴" if data['yield_spread_bps'] < -50 else ("🟡" if data['yield_spread_bps'] < 0 else "🟢")
        total_score += 2 if data['yield_spread_bps'] < -50 else (1 if data['yield_spread_bps'] < 0 else 0)
    else: yield_txt, yield_l = "延遲 ⏳", "⚪"

    if data.get('hy_oas') is not None:
        hy_txt = f"{data['hy_oas']:+.2f}% {data['hy_arrow']}"
        hy_l = "🔴" if data['hy_oas'] < -3.5 else ("🟡" if data['hy_oas'] < -1.5 else "🟢")
        total_score += 2 if data['hy_oas'] < -3.5 else (1 if data['hy_oas'] < -1.5 else 0)
    else: hy_txt, hy_l = "延遲 ⏳", "⚪"

    if data.get('twd_bias_pct') is not None:
        twd_txt = f"{data['twd_fx']:.2f} ({data['twd_bias_pct']:+.1f}%) {data['twd_arrow']}"
        twd_l = "🔴" if data['twd_bias_pct'] > 1.5 else ("🟡" if data['twd_bias_pct'] > 0.5 else "🟢")
        total_score += 2 if data['twd_bias_pct'] > 1.5 else (1 if data['twd_bias_pct'] > 0.5 else 0)
    else: twd_txt, twd_l = "延遲 ⏳", "⚪"

    if data.get('tw_bias') is not None:
        tw_txt = f"{data['tw_bias']:.1f}% {data['tw_bias_arrow']} (歷史百分位: {p_bias})"
        tw_l = "🔴" if (data['tw_bias'] > 6 or data['tw_bias'] < -8) else ("🟡" if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5) else "🟢")
        total_score += 2 if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else (1 if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else 0)
    else: tw_txt, tw_l = "延遲 ⏳", "⚪"

    if total_score >= 9: status_light = "🔴 【四級極端風暴】請啟動質押分批解鎖退場/拉高維持率"
    elif total_score >= 6: status_light = "🟠 【三級高風險】減碼/停止槓桿加碼"
    elif total_score >= 3: status_light = "🟡 【二級市場觀望】暫緩追高"
    else: status_light = "🟢 【一級安全綠燈】紀律加碼/維持常態"

    # 歷史去重軌跡計算
    risk_file = "risk_history.json"
    yesterday_score_text = "🔄 啟動"
    try:
        if os.path.exists(risk_file):
            with open(risk_file, "r", encoding="utf-8") as f: rh = json.load(f)
            past = [r for r in rh.get("records", []) if r.get("date") != today_str]
            if past:
                diff = total_score - past[-1]["total_score"]
                yesterday_score_text = f"{past[-1]['total_score']} → {total_score} ({'🔺+' if diff>0 else '🔻' if diff<0 else '➡️'}{diff})"
    except: pass

    # 排版輸出
    report = (
        f"🚨 【unclelee 總經加權風控塔台】\n"
        f"⏰ {taiwan_time.strftime('%m-%d %H:%M')} | 📉 軌跡: {yesterday_score_text}\n"
        f"🚦 指揮燈號：{status_light}\n"
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
        p_cape = get_percentile(data.get('shiller_cape', 0), baseline_brain, "shiller_cape") if data.get('shiller_cape') else "暫無歷史基準"
        p_bft = get_percentile(data.get('buffett_indicator', 0), baseline_brain, "buffett_indicator") if data.get('buffett_indicator') else "暫無歷史基準"
        
        cape_txt = f"{data['shiller_cape']:.1f}倍 (歷史百分位: {p_cape})" if data.get('shiller_cape') else "延遲 ⏳ (暫無歷史基準)"
        bft_txt = f"{data['buffett_indicator']:.1f}% (歷史百分位: {p_bft})" if data.get('buffett_indicator') else "延遲 ⏳ (暫無歷史基準)"
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
    is_ex_dividend_day = False 

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

    # 🚀 優化效果：主成交現價均能直接從 shared_df 記憶體批量提取，拒絕限流
    p_voo = safe_get_price_v3(close_df, 'VOO')
    p_smh = safe_get_price_v3(close_df, 'SMH')
    usd_to_twd = safe_get_price_v3(close_df, 'TWD=X') or 32.5

    # 00713 因加載字尾可能與大盤 MultiIndex 相斥，若記憶體未命中則降級處理
    p_00713 = safe_get_price_v3(close_df, '00713.TW')
    if p_00713 is None:
        try:
            t_00713 = yf.Ticker("00713.TW")
            p_00713 = t_00713.fast_info.get('last_price') or t_00713.info.get('regularMarketPrice')
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
        f"• 00713 ({shares_00713:,}股 × {p_00713_txt}) | 比率: {act_00713*100:.1f}% (目標 40%) | 偏離: {dev_00713:+.1f}%\n"
        f"• VOO   ({shares_voo:,}股 × {p_voo_txt}) | 比率: {act_voo*100:.1f}% (目標 40%) | 偏離: {dev_voo:+.1f}%\n"
        f"• SMH   ({shares_smh:,}股 × {p_smh_txt}) | 比率: {act_smh*100:.1f}% (目標 20%) | 偏離: {dev_smh:+.1f}%\n"
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
    else: report += "💤 部分市場未開盤，不提供具體交易股數建議。\n"
    return report

# =========================================================================
# 📤 第三區塊：自動發送服務
# =========================================================================
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

    # 歷史基準大腦載入與自動維護
    baseline_brain = {}
    if not os.path.exists(BASELINE_FILE) or is_monthly_check:
        try:
            baseline_brain = update_historical_baseline()
        except Exception as e:
            print(f"🚨 大數據更新受波動影響，自動載入現有大腦備份: {e}")
            if os.path.exists(BASELINE_FILE):
                with open(BASELINE_FILE, "r", encoding="utf-8") as f: baseline_brain = json.load(f)
    else:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f: baseline_brain = json.load(f)

    # 每日數據批量下載 (🛠️ 修正問題3：補齊資產 Tickers，全面阻斷重複請求)
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
