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
# 🧠 第一大核心：總經加權風控塔台 (🛠️ 終極強化：使用 hasattr 封殺所有結構突變錯誤)
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

    # 安全提取全域矩陣中的 Close 欄位
    close_df = None
    if df is not None and hasattr(df, 'get'):
        close_df = df.get('Close')

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

    # --- 3. 10Y-2Y 美債利差 (FRED 優先通道機制) ---
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
                    date_str = parts[0].strip()
                    return val, f"FRED({series_id}, {date_str})"
            return None, f"FRED {series_id} 資料皆為空值"
        except Exception as e:
            print(f"FRED {series_id} 抓取失敗: {e}")
            return None, f"FRED {series_id} 連線失敗"

    # 第一層：嘗試從 FRED 獲取權威數據
    t10_val, t10_src = get_treasury_yield_from_fred("DGS10")
    t02_val, t02_src = get_treasury_yield_from_fred("DGS2")

    # 第二層：若 FRED 失敗，退回原本的 Yahoo Finance 三層備援
    # 【10Y Yahoo 備援線路】
    if t10_val is None:
        try:
            t10_tk = yf.Ticker("^TNX")
            t10_val = t10_tk.fast_info.get('last_price')
            if t10_val is not None: t10_src = "Yahoo備援(^TNX快照 fast_info)"
            
            if t10_val is None:
                t10_val = t10_tk.info.get('regularMarketPrice') or t10_tk.info.get('previousClose')
                if t10_val is not None: t10_src = "Yahoo備援(^TNX快照 info)"
                
            if t10_val is None:
                t10_hist = t10_tk.history(period="15d")['Close'].dropna()
                if not t10_hist.empty:
                    t10_val = float(t10_hist.iloc[-1])
                    t10_src = "Yahoo備援(^TNX歷史線 history)"
            
            if t10_val is not None and t10_val > 15: t10_val /= 10
        except Exception as ex:
            print(f"Yahoo 10Y 備援線路異常: {ex}")

    # 【2Y Yahoo 備援線路】
    if t02_val is None:
        try:
            t02_tk = yf.Ticker("2YY=F")
            t02_val = t02_tk.fast_info.get('last_price')
            if t02_val is not None: t02_src = "Yahoo備援(2YY=F快照 fast_info)"
            
            if t02_val is None:
                t02_val = t02_tk.info.get('regularMarketPrice') or t02_tk.info.get('previousClose')
                if t02_val is not None: t02_src = "Yahoo備援(2YY=F快照 info)"
                
            if t02_val is None:
                t02_hist = t02_tk.history(period="15d")['Close'].dropna()
                if not t02_hist.empty:
                    t02_val = float(t02_hist.iloc[-1])
                    t02_src = "Yahoo備援(2YY=F歷史線 history)"
            
            if t02_val is not None and t02_val > 15: t02_val /= 10
        except Exception as ex:
            print(f"Yahoo 2Y 備援線路異常: {ex}")

    # 標註除錯 Log
    print(f"📊 [美債利差診斷儀] 10Y最終來源: {t10_src} | 數值: {t10_val}")
    print(f"📊 [美債利差診斷儀] 2Y最終來源: {t02_src} | 數值: {t02_val}")

    try:
        if t10_val is not None and t02_val is not None:
            calc_spread_bps = round((t10_val - t02_val) * 100, 1)
            
            if abs(calc_spread_bps) > 300.0:
                raise ValueError(f"利差數值離譜防呆觸發: {calc_spread_bps} bps")
                
            data['yield_spread_bps'] = calc_spread_bps
            
            try:
                t10_arrow_series = yf.Ticker("^TNX").history(period="15d")['Close'].dropna()
                t02_arrow_series = yf.Ticker("2YY=F").history(period="15d")['Close'].dropna()
                if not t10_arrow_series.empty and not t02_arrow_series.empty:
                    min_len = min(len(t10_arrow_series), len(t02_arrow_series))
                    s10 = t10_arrow_series.iloc[-min_len:].copy().apply(lambda x: x/10 if x > 15 else x)
                    s02 = t02_arrow_series.iloc[-min_len:].copy().apply(lambda x: x/10 if x > 15 else x)
                    spread_series = s10 - s02
                    if abs(spread_series.iloc[-1] - spread_series.iloc[-2]) > 3.0: 
                        data['yield_arrow'] = "➡️"
                    else:
                        data['yield_arrow'] = get_trend_arrow(spread_series)
                else: data['yield_arrow'] = "➡️"
            except: data['yield_arrow'] = "➡️"
        else:
            raise Exception("官方FRED與備援Yahoo全線斷訊")
    except Exception as e:
        print(f"🚨 [美債利差核心報警] 計算中止。原因: {e}")
        data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    # --- 4. 高收益債變化率 ---
    try:
        if close_df is not None and hasattr(close_df, 'columns') and 'HYG' in close_df.columns:
            hyg_series = close_df['HYG'].dropna()
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
        if close_df is not None and hasattr(close_df, 'columns') and 'TWD=X' in close_df.columns:
            twd_series = close_df['TWD=X'].dropna()
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
        if close_df is not None and hasattr(close_df, 'columns') and '^TWII' in close_df.columns:
            twii_series = close_df['^TWII'].dropna()
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
    # 📆 月度核心量化指標數據抓取 (僅限每月 1 號)
    # =========================================================================
    if is_monthly_check:
        try:
            resp = requests.get("https://www.multpl.com/shiller-pe", timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            cape_text = soup.find('div', {'id': 'current'}).find('b').text
            data['shiller_cape'] = float(cape_text.strip())
        except Exception as e:
            print(f"席勒CAPE 1號抓取攔截: {e}")
            data['shiller_cape'] = None

        try:
            if close_df is not None and hasattr(close_df, 'columns') and '^W5000' in close_df.columns:
                w5000_series = close_df['^W5000'].dropna()
            else:
                w5000_series = yf.Ticker("^W5000").history(period="10d")['Close'].dropna()
            if not w5000_series.empty:
                current_w5000_val = w5000_series.iloc[-1]
                baseline_w5000 = 75000.0
                baseline_buffett_pct = 225.0
                data['buffett_indicator'] = round(baseline_buffett_pct * (current_w5000_val / baseline_w5000), 1)
            else:
                data['buffett_indicator'] = None
        except:
            data['buffett_indicator'] = None

        data['recession_prob'] = config_data.get("recession_probability_manual", None)

    # =========================================================================
    # 🚦 燈號級距與加權總分計算
    # =========================================================================
    total_score = 0

    if data.get('vix') is not None:
        vix_txt = f"{data['vix']:.2f} {data['vix_arrow']}"
        vix_l = "🔴" if data['vix'] > 30 else ("🟡" if data['vix'] > 20 else "🟢")
        total_score += 2 if data['vix'] > 30 else (1 if data['vix'] > 20 else 0)
    else: vix_txt, vix_l = "延遲 ⏳", "⚪"

    if data.get('pe_ratio') is not None:
        pe_txt = f"{data['pe_ratio']:.1f}倍"
        pe_l = "🔴" if data['pe_ratio'] > 30 else ("🟡" if data['pe_ratio'] > 26 else "🟢")
        total_score += 2 if data['pe_ratio'] > 30 else (1 if data['pe_ratio'] > 26 else 0)
    else: pe_txt, pe_l = "延遲 ⏳", "⚪"

    if data.get('yield_spread_bps') is not None:
        yield_txt = f"{data['yield_spread_bps']:.1f} bps {data['yield_arrow']}"
        yield_l = "🔴" if data['yield_spread_bps'] < -50 else ("🟡" if data['yield_spread_bps'] < 0 else "🟢")
        total_score += 2 if data['yield_spread_bps'] < -50 else (1 if data['yield_spread_bps'] < 0 else 0)
    else:
        yield_txt = f"延遲 ⏳ (10Y:{t10_src} | 2Y:{t02_src})"
        yield_l = "⚪"

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
        tw_txt = f"{data['tw_bias']:.1f}% {data['tw_bias_arrow']}"
        tw_l = "🔴" if (data['tw_bias'] > 6 or data['tw_bias'] < -8) else ("🟡" if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5) else "🟢")
        total_score += 2 if (data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0) else (1 if (data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0) else 0)
    else: tw_txt, tw_l = "延遲 ⏳", "⚪"

    if is_monthly_check:
        if data.get('shiller_cape') is not None:
            c_val = data['shiller_cape']
            total_score += 0 if c_val < 25 else (1 if c_val < 32 else (2 if c_val < 40 else 3))
        if data.get('buffett_indicator') is not None:
            b_val = data['buffett_indicator']
            total_score += 0 if b_val < 100 else (1 if b_val < 150 else (2 if b_val < 200 else 3))
        if data.get('recession_prob') is not None:
            r_val = data['recession_prob']
            total_score += 0 if r_val < 15 else (1 if r_val < 30 else (2 if r_val < 50 else 3))

        if total_score >= 15: status_light = "🔴 【四級極端風暴】停利回收現金"
        elif total_score >= 10: status_light = "🟠 【三級高風險】減碼/停止加碼"
        elif total_score >= 5: status_light = "🟡 【二級市場觀望】暫緩追高"
        else: status_light = "🟢 【一級安全綠燈】紀律扣款/大膽加碼"
    else:
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
        cape_txt = f"{data['shiller_cape']:.1f}倍" if data.get('shiller_cape') is not None else "延遲 ⏳"
        cape_l = ("🟢 合理" if data['shiller_cape'] < 25 else ("🟡 偏高" if data['shiller_cape'] < 32 else ("🟠 警戒" if data['shiller_cape'] < 40 else "🔴 危險"))) if data.get('shiller_cape') is not None else "⚪"

        bft_txt = f"{data['buffett_indicator']:.1f}%" if data.get('buffett_indicator') is not None else "延遲 ⏳"
        bft_l = ("🟢 合理" if data['buffett_indicator'] < 100 else ("🟡 偏高" if data['buffett_indicator'] < 150 else ("🟠 警戒" if data['buffett_indicator'] < 200 else "🔴 危險"))) if data.get('buffett_indicator') is not None else "⚪"

        rec_txt = f"{data['recession_prob']:.1f}%" if data.get('recession_prob') is not None else "未設定 ⏳"
        rec_l = ("🟢 正常" if data['recession_prob'] < 15 else ("🟡 留意" if data['recession_prob'] < 30 else ("🟠 警戒" if data['recession_prob'] < 50 else "🔴 危險"))) if data.get('recession_prob') is not None else "⚪"

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
    is_ex_dividend_day = False 

    # 安全提取全域矩陣中的 Close 欄位
    close_df = None
    if df is not None and hasattr(df, 'get'):
        close_df = df.get('Close')

    def safe_get_price_v3(close_df, ticker):
        try:
            if close_df is not None and hasattr(close_df, 'columns') and ticker in close_df.columns:
                series = close_df[ticker].dropna()
                if not series.empty: return float(series.iloc[-1])
        except: pass
        try:
            fallback_series = yf.Ticker(ticker).history(period="15d")['Close'].dropna()
            if not fallback_series.empty: return float(fallback_series.iloc[-1])
        except: pass
        return None

    p_voo = safe_get_price_v3(close_df, 'VOO')
    p_smh = safe_get_price_v3(close_df, 'SMH')
    usd_to_twd = safe_get_price_v3(close_df, 'TWD=X') or 32.5

    t_00713 = yf.Ticker("00713.TW")
    p_00713 = t_00713.fast_info.get('last_price') or t_00713.info.get('regularMarketPrice')
    if p_00713 is None:
        try: p_00713 = float(t_00713.history(period="10d")['Close'].dropna().iloc[-1])
        except: p_00713 = None

    us_market_status = "正常交易 ✅" if p_voo and p_smh else "休市 💤"

    def calc_5d_pct(ticker_name, is_tw=False):
        try:
            if is_tw:
                series = yf.Ticker(ticker_name).history(period="8d")['Close'].dropna()
            elif close_df is not None and hasattr(close_df, 'columns') and ticker_name in close_df.columns:
                series = close_df[ticker_name].dropna()
            else:
                series = yf.Ticker(ticker_name).history(period="8d")['Close'].dropna()
            if len(series) >= 6:
                pct = ((series.iloc[-1] - series.iloc[-6]) / series.iloc[-6]) * 100
                return f"{'+' if pct >= 0 else ''}{pct:.1f}%"
        except: pass
        return "暫無"

    pct_00713 = calc_5d_pct('00713.TW', is_tw=True)
    pct_voo = calc_5d_pct('VOO') if p_voo else "暫停"
    pct_smh = calc_5d_pct('SMH') if p_smh else "暫停"

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
        tickers = ["^VIX", "SPY", "^GSPC", "^TNX", "HYG", "TWD=X", "^TWII", "^W5000"]
        shared_df = yf.download(tickers, period="50d", progress=False)
        if shared_df is None or shared_df.empty or 'Close' not in shared_df: shared_df = None
    except: shared_df = None

    risk_report = get_risk_control_report(shared_df)
    rebalance_report = get_rebalance_report(shared_df)
    
    combined_report = f"{risk_report}\n\n═══════════════════════════\n\n{rebalance_report}"
    send_line_message(combined_report)

if __name__ == "__main__":
    main()
