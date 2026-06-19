import os
import json
import datetime
import requests
import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup

# =========================================================================
# 🛠️ 共通工具函式：趨勢箭頭判定
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

# =========================================================================
# 🧠 第一大核心：總經加權風控塔台 (🛠️ 修正：長週期指標完全限縮至每月1號)
# =========================================================================
def get_risk_control_report(df):
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    today_str = taiwan_time.strftime("%Y-%m-%d")
    is_monthly_check = (taiwan_time.day == 1)
    data = {}
    
    # 🗟 讀取 config.json 的手動配置
    config_data = {}
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            print("風控讀取 config.json 異常:", e)

    # =========================================================================
    # 📆 每日必定執行：6大核心量化指標
    # =========================================================================
    # --- 1. VIX 恐慌指數 ---
    try:
        if df is not None and 'Close' in df and '^VIX' in df['Close'].columns:
            vix_series = df['Close']['^VIX'].dropna()
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
            if df is not None and 'Close' in df and '^GSPC' in df['Close'].columns:
                sp500_close = df['Close']['^GSPC'].dropna()
            else:
                sp500_close = yf.Ticker("^GSPC").history(period="10d")['Close'].dropna()
            data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / 238.5, 1)
    except:
        data['pe_ratio'] = None

    # --- 3. 10Y-2Y 美債利差 ---
    try:
        t10_series, t02_series = None, None
        if df is not None and 'Close' in df and '^TNX' in df['Close'].columns and '^2Y' in df['Close'].columns:
            t10_series = df['Close']['^TNX'].dropna()
            t02_series = df['Close']['^2Y'].dropna()

        if t10_series is None or t10_series.empty:
            t10_series = yf.Ticker("^TNX").history(period="15d")['Close'].dropna()
        if t02_series is None or t02_series.empty:
            t02_series = yf.Ticker("^2Y").history(period="15d")['Close'].dropna()

        if t10_series is not None and not t10_series.empty and t02_series is not None and not t02_series.empty:
            date_10 = t10_series.index[-1].to_pydatetime() if hasattr(t10_series.index[-1], 'to_pydatetime') else t10_series.index[-1]
            date_02 = t02_series.index[-1].to_pydatetime() if hasattr(t02_series.index[-1], 'to_pydatetime') else t02_series.index[-1]
            if date_10.tzinfo is not None: date_10 = date_10.replace(tzinfo=None)
            if date_02.tzinfo is not None: date_02 = date_02.replace(tzinfo=None)
            
            if abs((date_10 - date_02).days) > 3:
                raise Exception("美債數據不同步超過3天")
                
            t10_val = float(t10_series.iloc[-1])
            t02_val = float(t02_series.iloc[-1])
            if t10_val > 15: t10_val /= 10
            if t02_val > 15: t02_val /= 10
            
            data['yield_spread_bps'] = round((t10_val - t02_val) * 100, 1)
            min_len = min(len(t10_series), len(t02_series))
            s10 = t10_series.iloc[-min_len:].copy().apply(lambda x: x/10 if x > 15 else x)
            s02 = t02_series.iloc[-min_len:].copy().apply(lambda x: x/10 if x > 15 else x)
            data['yield_arrow'] = get_trend_arrow(s10 - s02)
        else:
            raise Exception("美債序列空值")
    except Exception as e:
        print("美債精算判定跳過:", e)
        data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    # --- 4. 高收益債變化率 (HYG 近30日變化) ---
    try:
        if df is not None and 'Close' in df and 'HYG' in df['Close'].columns:
            hyg_series = df['Close']['HYG'].dropna()
        else:
            hyg_series = yf.Ticker("HYG").history(period="50d")['Close'].dropna()
        current_hyg = hyg_series.iloc[-1]
        past_hyg = hyg_series.iloc[-30]
        data['hy_oas'] = round(((current_hyg - past_hyg) / past_hyg) * 100, 2)
        data['hy_arrow'] = get_trend_arrow(hyg_series)
    except:
        data['hy_oas'], data['hy_arrow'] = None, "⏳"

    # --- 5. 台幣兌美元匯率 ---
    try:
        if df is not None and 'Close' in df and 'TWD=X' in df['Close'].columns:
            twd_series = df['Close']['TWD=X'].dropna()
        else:
            twd_series = yf.Ticker("TWD=X").history(period="50d")['Close'].dropna()
        current_twd = float(twd_series.iloc[-1])
        ma_30_twd = twd_series.iloc[-30:].mean()
        data['twd_fx'] = current_twd
        data['twd_bias_pct'] = round(((current_twd - ma_30_twd) / ma_30_twd) * 100, 2)
        data['twd_arrow'] = get_trend_arrow(twd_series)
    except:
        data['twd_fx'], data['twd_bias_pct'], data['twd_arrow'] = None, None, "⏳"

    # --- 6. 台股加權指數 20日乖離率 ---
    try:
        if df is not None and 'Close' in df and '^TWII' in df['Close'].columns:
            twii_series = df['Close']['^TWII'].dropna()
        else:
            twii_series = yf.Ticker("^TWII").history(period="50d")['Close'].dropna()
        current_twii = twii_series.iloc[-1]
        ma_20 = twii_series.iloc[-20:].mean()
        bias_val = ((current_twii - ma_20) / ma_20) * 100
        bias_history = []
        for i in range(-5, 0):
            end_idx = i + 1 if i + 1 != 0 else len(twii_series)
            bias_history.append(((twii_series.iloc[i] - twii_series.iloc[i-19:end_idx].mean()) / twii_series.iloc[i-19:end_idx].mean()) * 100)
        data['tw_bias'] = round(bias_val, 2)
        data['tw_bias_arrow'] = get_trend_arrow(pd.Series(bias_history))
    except:
        data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"

    # =========================================================================
    # 🛠️ 修正 1 & 2 & 3：限縮至每月 1 號才觸發計算與連線的長週期指標
    # =========================================================================
    if is_monthly_check:
        # 🆕 --- 7. 席勒 CAPE 比率 (只在1號爬蟲) ---
        try:
            resp = requests.get("https://www.multpl.com/shiller-pe", timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            cape_text = soup.find('div', {'id': 'current'}).find('b').text
            data['shiller_cape'] = float(cape_text.strip())
        except Exception as e:
            print(f"席勒CAPE 1號抓取攔截: {e}")
            data['shiller_cape'] = None

        # 🆕 --- 8. 修正版巴菲特指標 (只在1號計算) ---
        try:
            if df is not None and 'Close' in df and '^W5000' in df['Close'].columns:
                w5000_series = df['Close']['^W5000'].dropna()
            else:
                w5000_series = yf.Ticker("^W5000").history(period="10d")['Close'].dropna()
            if not w5000_series.empty:
                current_w5000_val = w5000_series.iloc[-1]
                estimated_gdp = 28500.0
                data['buffett_indicator'] = round((current_w5000_val * 2.2 / estimated_gdp) * 100, 1)
            else:
                data['buffett_indicator'] = None
        except:
            data['buffett_indicator'] = None

        # 🆕 --- 9. 紐約聯準會衰退機率 (只在1號讀取) ---
        data['recession_prob'] = config_data.get("recession_probability_manual", None)


    # =========================================================================
    # 🚦 評分與燈號分層整合系統
    # =========================================================================
    total_score = 0

    # 1. VIX (0-2分)
    if data.get('vix') is not None:
        total_score += 2 if data['vix'] > 30 else (1 if data['vix'] > 20 else 0)
    # 2. 標普 PE (0-2分)
    if data.get('pe_ratio') is not None:
        total_score += 2 if data['pe_ratio'] > 30 else (1 if data['pe_ratio'] > 26 else 0)
    # 3. 美債利差 (0-2分)
    if data.get('yield_spread_bps') is not None:
        total_score += 2 if data['yield_spread_bps'] < -50 else (1 if data['yield_spread_bps'] < 0 else 0)
    # 4. HYG (0-2分)
    if data.get('hy_oas') is not None:
        total_score += 2 if data['hy_oas'] < -3.5 else (1 if data['hy_oas'] < -1.5 else 0)
    # 5. TWD匯率 (0-2分)
    if data.get('twd_bias_pct') is not None:
        total_score += 2 if data['twd_bias_pct'] > 1.5 else (1 if data['twd_bias_pct'] > 0.5 else 0)
    # 6. 台股乖離 (0-2分)
    if data.get('tw_bias') is not None:
        total_score += 2 if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else (1 if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else 0)

    # 🛠️ 修正 4：動態門檻判定 (平日最高12分 / 1號最高21分)
    if is_monthly_check:
        # 7. 席勒 CAPE 分數計算
        if data.get('shiller_cape') is not None:
            c_val = data['shiller_cape']
            c_s = 0 if c_val < 25 else (1 if c_val < 32 else (2 if c_val < 40 else 3))
            total_score += c_s
        # 8. 巴菲特指標分數計算
        if data.get('buffett_indicator') is not None:
            b_val = data['buffett_indicator']
            b_s = 0 if b_val < 100 else (1 if b_val < 150 else (2 if b_val < 200 else 3))
            total_score += b_s
        # 9. 衰退機率分數計算
        if data.get('recession_prob') is not None:
            r_val = data['recession_prob']
            r_s = 0 if r_val < 15 else (1 if r_val < 30 else (2 if r_val < 50 else 3))
            total_score += r_s

        # 1號專用：21分制門檻
        if total_score >= 15: status_light = "🔴 【四級極端風暴】停利回收現金"
        elif total_score >= 10: status_light = "🟠 【三級高風險】減碼/停止加碼"
        elif total_score >= 5: status_light = "🟡 【二級市場觀望】暫緩追高"
        else: status_light = "🟢 【一級安全綠燈】紀律扣款/大膽加碼"
    else:
        # 平日專用：12分制門檻
        if total_score >= 9: status_light = "🔴 【四級極端風暴】停利回收現金"
        elif total_score >= 6: status_light = "🟠 【三級高風險】減碼/停止加碼"
        elif total_score >= 3: status_light = "🟡 【二級市場觀望】暫緩追高"
        else: status_light = "🟢 【一級安全綠燈】紀律扣款/大膽加碼"


    # --- 歷史風險去重更新邏輯 ---
    risk_file = "risk_history.json"
    yesterday_score_text = "🔄 啟動"
    risk_history = {"records": []}

    if os.path.exists(risk_file):
        try:
            with open(risk_file, "r", encoding="utf-8") as f: risk_history = json.load(f)
            past_records = [r for r in risk_history.get("records", []) if r.get("date") != today_str]
            if past_records:
                last_score = past_records[-1].get("total_score", 0)
                diff = total_score - last_score
                ts = f"🔺+{diff}" if diff > 0 else (f"🔻{diff}" if diff < 0 else "➡️ 持平")
                yesterday_score_text = f"{last_score} → {total_score} ({ts})"
        except: pass

    try:
        records = risk_history.get("records", [])
        if records and records[-1].get("date") == today_str: records[-1]["total_score"] = total_score
        else: records.append({"date": today_str, "total_score": total_score})
        risk_history["records"] = records[-90:]
        with open(risk_file, "w", encoding="utf-8") as f: json.dump(risk_history, f, ensure_ascii=False, indent=4)
    except: pass

    # =========================================================================
    # 🖨️ 報告排版分層輸出
    # =========================================================================
    # 每日核心指標文本生成
    vix_txt = f"{data['vix']:.2f} {data['vix_arrow']}" if data.get('vix') is not None else "延遲 ⏳"
    vix_l = "🔴" if data.get('vix', 0) > 30 else ("🟡" if data.get('vix', 0) > 20 else "🟢") if data.get('vix') is not None else "⚪"
    
    pe_txt = f"{data['pe_ratio']:.1f}倍" if data.get('pe_ratio') is not None else "延遲 ⏳"
    pe_l = "🔴" if data.get('pe_ratio', 0) > 30 else ("🟡" if data.get('pe_ratio', 0) > 26 else "🟢") if data.get('pe_ratio') is not None else "⚪"
    
    yield_txt = f"{data['yield_spread_bps']:.1f} bps {data['yield_arrow']}" if data.get('yield_spread_bps') is not None else "延遲 ⏳"
    yield_l = "🔴" if data.get('yield_spread_bps', 0) < -50 else ("🟡" if data.get('yield_spread_bps', 0) < 0 else "🟢") if data.get('yield_spread_bps') is not None else "⚪"
    
    hy_txt = f"{data['hy_oas']:+.2f}% {data['hy_arrow']}" if data.get('hy_oas') is not None else "延遲 ⏳"
    hy_l = "🔴" if data.get('hy_oas', 0) < -3.5 else ("🟡" if data.get('hy_oas', 0) < -1.5 else "🟢") if data.get('hy_oas') is not None else "⚪"
    
    twd_txt = f"{data['twd_fx']:.2f} ({data['twd_bias_pct']:+.1f}%) {data['twd_arrow']}" if data.get('twd_bias_pct') is not None else "延遲 ⏳"
    twd_l = "🔴" if data.get('twd_bias_pct', 0) > 1.5 else ("🟡" if data.get('twd_bias_pct', 0) > 0.5 else "🟢") if data.get('twd_bias_pct') is not None else "⚪"
    
    tw_txt = f"{data['tw_bias']:.1f}% {data['tw_bias_arrow']}" if data.get('tw_bias') is not None else "延遲 ⏳"
    tw_l = "🔴" if (data.get('tw_bias', 0) > 6 or data.get('tw_bias', 0) < -8) else ("🟡" if (data.get('tw_bias', 0) > 3.5 or data.get('tw_bias', 0) < -5) else "🟢") if data.get('tw_bias') is not None else "⚪"

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

    # 🛠️ 修正 4：只有在 1 號時，才在下方追加獨立的「大盤月度長檢」區塊與手動更新提醒
    if is_monthly_check:
        if data.get('shiller_cape') is None: cape_txt, cape_l = "延遲 ⏳", "⚪"
        else:
            c_val = data['shiller_cape']
            cape_txt = f"{c_val:.1f}倍"; cape_l = "🟢 合理" if c_val < 25 else ("🟡 偏高" if c_val < 32 else ("🟠 警戒" if c_val < 40 else "🔴 危險"))

        if data.get('buffett_indicator') is None: bft_txt, bft_l = "延遲 ⏳", "⚪"
        else:
            b_val = data['buffett_indicator']
            bft_txt = f"{b_val:.1f}%"; bft_l = "🟢 合理" if b_val < 100 else ("🟡 偏高" if b_val < 150 else ("🟠 警戒" if b_val < 200 else "🔴 危險"))

        if data.get('recession_prob') is None: rec_txt, rec_l = "未設定 ⏳", "⚪"
        else:
            r_val = data['recession_prob']
            rec_txt = f"{r_val:.1f}%"; rec_l = "🟢 正常" if r_val < 15 else ("🟡 留意" if r_val < 30 else ("🟠 警戒" if r_val < 50 else "🔴 危險"))

        report += (
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📅 【每月1號大盤長檢指標】\n"
            f"• 席勒CAPE比率 : {cape_txt} | 狀態: {cape_l}\n"
            f"• 修正巴菲特指 : {bft_txt} | 狀態: {bft_l}\n"
            f"• 聯準會衰退率 : {rec_txt} | 狀態: {rec_l}\n"
            f"📌 提醒：請記得每月更新衰退機率數據\n"
            f"  (查詢: https://www.newyorkfed.org/research/capital_markets/ycfaq#/interactive)\n"
        )
        
    return report

# =========================================================================
# 📊 第二大核心：資產再平衡決策哨兵
# =========================================================================
def get_rebalance_report(df):
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f: config_data = json.load(f)
            shares_00713 = config_data.get("shares_00713", 10153)
            shares_voo = config_data.get("shares_voo", 28)
            shares_smh = config_data.get("shares_smh", 15)
        except: shares_00713, shares_voo, shares_smh = 10153, 28, 15
    else: shares_00713, shares_voo, shares_smh = 10153, 28, 15

    target_00713, target_voo, target_smh = 0.40, 0.40, 0.20

    def safe_get_price_v3(close_df, ticker):
        try:
            if close_df is not None and ticker in close_df.columns:
                series = close_df[ticker].dropna()
                if not series.empty: return float(series.iloc[-1])
        except: pass
        try:
            fallback_series = yf.Ticker(ticker).history(period="15d")['Close'].dropna()
            if not fallback_series.empty: return float(fallback_series.iloc[-1])
        except: pass
        return None

    close_df = df['Close'] if (df is not None and 'Close' in df) else None
    p_voo = safe_get_price_v3(close_df, 'VOO')
    p_smh = safe_get_price_v3(close_df, 'SMH')
    usd_to_twd = safe_get_price_v3(close_df, 'TWD=X') or 32.5

    t_00713 = yf.Ticker("00713.TW")
    p_00713 = t_00713.fast_info.get('last_price') or t_00713.info.get('regularMarketPrice')
    if p_00713 is None:
        try: p_00713 = float(t_00713.history(period="10d")['Close'].dropna().iloc[-1])
        except: p_00713 = None

    us_market_status = "正常 ✅" if p_voo and p_smh else "休市 💤"

    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    is_ex_dividend_day = (taiwan_time.month in [3, 6, 9, 12] and 15 <= taiwan_time.day <= 20)

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

    def judge_deviation_short(dev_val, is_00713=False):
        if is_00713 and is_ex_dividend_day: return "🟢 正常", "除息保護"
        abs_dev = abs(dev_val)
        if abs_dev > 5.0: return f"🔴 調整 ({dev_val:+.1f}%)", "超越風控線"
        elif abs_dev > 2.0: return f"⚠️ 觀察 ({dev_val:+.1f}%)", "常規波動"
        return f"🟢 正常 ({dev_val:+.1f}%)", "契合配置"

    status_00713, note_00713 = judge_deviation_short(dev_00713, is_00713=True)
    status_voo, note_voo = judge_deviation_short(dev_voo)
    status_smh, note_smh = judge_deviation_short(dev_smh)

    p_00713_txt = f"{p_00713:.1f} TWD" if p_00713 else "延遲"
    p_voo_txt = f"{p_voo:.1f} USD" if p_voo else "休市"
    p_smh_txt = f"{p_smh:.1f} USD" if p_smh else "休市"

    report = (
        f"📊 【unclelee 資產再平衡決策哨兵】\n"
        f"💵 匯率: {usd_to_twd:.2f} | 💰 總市值: NT$ {round(total_portfolio_value):,} 元 ({us_market_status})\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🔍 【核心配置分項指標體檢】\n"
        f"• 00713 ({shares_00713:,}股 × {p_00713_txt})\n"
        f"  💰 價值: NT$ {round(v_00713):,} 元 | 比率: {act_00713*100:.1f}% (目標 40%)\n"
        f"  🚦 風控: {status_00713} | {note_00713}\n"
        f"• VOO   ({shares_voo:,}股 × {p_voo_txt})\n"
        f"  💰 價值: NT$ {round(v_voo):,} 元 | 比率: {act_voo*100:.1f}% (目標 40%)\n"
        f"  🚦 風控: {status_voo} | {note_voo}\n"
        f"• SMH   ({shares_smh:,}股 × {p_smh_txt})\n"
        f"  💰 價值: NT$ {round(v_smh):,} 元 | 比率: {act_smh*100:.1f}% (目標 20%)\n"
        f"  🚦 風控: {status_smh} | {note_smh}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🛠️ 演算法一鍵指引修剪建議：\n"
    )

    if p_voo and p_smh and p_00713:
        trigger_00713 = abs(dev_00713) > 5.0 and not is_ex_dividend_day
        trigger_voo = abs(dev_voo) > 5.0
        trigger_smh = abs(dev_smh) > 5.0
        
        if trigger_00713 or trigger_voo or trigger_smh:
            def format_trade_msg(shares, cost):
                if shares > 0: return f"🟢 補進 +{shares} 股 (約 NT$ {round(cost):,})"
                elif shares < 0: return f"🔴 減碼 {shares} 股 (約 NT$ {round(abs(cost)):,})"
                return "➡️ 無需變動"
            
            t_shares_00713 = round((total_portfolio_value * target_00713 - v_00713) / p_00713)
            t_shares_voo = round((total_portfolio_value * target_voo - v_voo) / (p_voo * usd_to_twd))
            t_shares_smh = round((total_portfolio_value * target_smh - v_smh) / (p_smh * usd_to_twd))
            
            report += (
                f"🎯 偏離過大，建議執行再平衡交易：\n"
                f"1. 00713: {format_trade_msg(t_shares_00713, total_portfolio_value * target_00713 - v_00713)}\n"
                f"2. VOO  : {format_trade_msg(t_shares_voo, total_portfolio_value * target_voo - v_voo)}\n"
                f"3. SMH  : {format_trade_msg(t_shares_smh, total_portfolio_value * target_smh - v_smh)}\n"
            )
        else: report += "⚖️ 資產偏離度皆控制在 ±5% 內，【今日建議維持不動】。\n"
    else: report += "💤 部分市場未開盤，不提供具體交易股數建議。\n"

    history_file = "rebalance_history.json"
    history_data = {"total_count": 0, "total_cost": 0.0, "records": []}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f: history_data = json.load(f)
        except: pass

    report += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📊 本年再平衡: {history_data['total_count']} 次 | 累積成本: 約 NT$ {round(history_data['total_cost']):,} 元"
    return report

# =========================================================================
# 📤 第三區塊：自動分段發送服務
# =========================================================================
def send_line_message(message_text):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id: return
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    max_length = 4500
    chunks = [message_text[i:i+max_length] for i in range(0, len(message_text), max_length)]
    for chunk in chunks:
        payload = {"to": user_id, "messages": [{"type": "text", "text": chunk}]}
        try: requests.post(url, headers=headers, json=payload)
        except: pass

# =========================================================================
# 🚀 核心控制台
# =========================================================================
def main():
    shared_df = None
    try:
        # 僅下載平日核心與巴菲特指標所需之標的
        tickers = ["^VIX", "SPY", "^GSPC", "^TNX", "^2Y", "HYG", "TWD=X", "^TWII", "^W5000"]
        shared_df = yf.download(tickers, period="50d", progress=False)
        if shared_df is None or shared_df.empty or 'Close' not in shared_df: shared_df = None
    except: shared_df = None

    risk_report = get_risk_control_report(shared_df)
    rebalance_report = get_rebalance_report(shared_df)
    
    combined_report = f"{risk_report}\n\n═══════════════════════════\n\n{rebalance_report}"
    send_line_message(combined_report)

if __name__ == "__main__":
    main()
