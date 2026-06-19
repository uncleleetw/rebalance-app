import os
import json
import datetime
import requests
import yfinance as yf
import pandas as pd

# =========================================================================
# 🛠️ 共通工具函式：趨勢箭頭判定
# =========================================================================
def get_trend_arrow(series):
    """根據過去 5 天數據計算最新一天相較於前幾天的趨勢箭頭"""
    if len(series) < 2:
        return "➡️"
    current = series.iloc[-1]
    prev = series.iloc[-2]
    if current > prev:
        return "🔺"
    elif current < prev:
        return "🔻"
    return "➡️"

# =========================================================================
# 🧠 第一大核心：總經加權風控塔台 (修正台股切片、納入歷史風險軌跡)
# =========================================================================
def get_risk_control_report(df):
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    is_monthly_check = (taiwan_time.day == 1)
    
    data = {}
    
    # --- 1. VIX 恐慌指數 ---
    try:
        vix_series = df['Close']['^VIX'].dropna()
        data['vix'] = float(vix_series.iloc[-1])
        data['vix_arrow'] = get_trend_arrow(vix_series)
    except Exception as e:
        print("VIX 擷取失敗:", e)
        data['vix'], data['vix_arrow'] = None, "⏳"

    # --- 2. S&P 500 本益比 ---
    try:
        spy = yf.Ticker("SPY")
        pe_val = spy.info.get('trailingPE') or spy.fast_info.get('trailing_pe') or spy.info.get('forwardPE')
        if pe_val and pe_val > 0:
            data['pe_ratio'] = float(pe_val)
        else:
            sp500_close = df['Close']['^GSPC'].dropna()
            data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / 238.5, 1)
    except Exception as e:
        print("PE 擷取失敗，啟動標普回推備援:", e)
        try:
            sp500_close = df['Close']['^GSPC'].dropna()
            data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / 238.5, 1)
        except Exception as ex:
            print("PE 備援線路亦失敗:", ex)
            data['pe_ratio'] = None

    # --- 3. 10Y-2Y 美債利差 ---
    try:
        t10_val, t02_val = None, None
        t10_series, t02_series = None, None

        if df is not None and 'Close' in df:
            t10_series = df['Close']['^TNX'].dropna()
            t02_series = df['Close']['^2Y'].dropna()
            if not t10_series.empty and not t02_series.empty:
                t10_val = float(t10_series.iloc[-1])
                t02_val = float(t02_series.iloc[-1])

        if t10_val is None or t02_val is None:
            t10_ticker = yf.Ticker("^TNX")
            t02_ticker = yf.Ticker("^2Y")
            t10_val = t10_ticker.fast_info.get('last_price') or t10_ticker.info.get('regularMarketPrice')
            t02_val = t02_ticker.fast_info.get('last_price') or t02_ticker.info.get('regularMarketPrice')
            
            if t10_series is None or t10_series.empty: t10_series = t10_ticker.history(period="5d")['Close'].dropna()
            if t02_series is None or t02_series.empty: t02_series = t02_ticker.history(period="5d")['Close'].dropna()

        if t10_val is not None and t02_val is not None:
            if t10_val > 15: t10_val /= 10
            if t02_val > 15: t02_val /= 10
            
            current_spread = t10_val - t02_val
            data['yield_spread_bps'] = round(current_spread * 100, 1)
            
            min_len = min(len(t10_series), len(t02_series))
            s10 = t10_series.iloc[-min_len:].copy()
            s02 = t02_series.iloc[-min_len:].copy()
            s10 = s10.apply(lambda x: x/10 if x > 15 else x)
            s02 = s02.apply(lambda x: x/10 if x > 15 else x)
            
            spread_history_bps = (s10 - s02) * 100
            data['yield_arrow'] = get_trend_arrow(spread_history_bps)
        else:
            raise Exception("未取得有效美債價格")
    except Exception as e:
        print("美債利差精算失敗:", e)
        data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    # --- 4. 高收益債變化率 (HYG 近30日變化) ---
    try:
        hyg_series = df['Close']['HYG'].dropna()
        if len(hyg_series) >= 30:
            current_hyg = hyg_series.iloc[-1]
            past_hyg = hyg_series.iloc[-30]
            hyg_pct_30d = ((current_hyg - past_hyg) / past_hyg) * 100
            data['hy_oas'] = round(hyg_pct_30d, 2)  
            data['hy_arrow'] = get_trend_arrow(hyg_series)
        else:
            raise Exception("HYG 歷史長度不足 30 天")
    except Exception as e:
        print("HYG 近30日變動率擷取失敗:", e)
        data['hy_oas'], data['hy_arrow'] = None, "⏳"

    # --- 5. 台幣兌美元匯率 (近30日均值動態偏離度) ---
    try:
        twd_series = df['Close']['TWD=X'].dropna()
        current_twd = float(twd_series.iloc[-1])
        if len(twd_series) >= 30:
            ma_30_twd = twd_series.iloc[-30:].mean()
            twd_bias_pct = ((current_twd - ma_30_twd) / ma_30_twd) * 100
            data['twd_fx'] = current_twd
            data['twd_bias_pct'] = round(twd_bias_pct, 2)
            data['twd_arrow'] = get_trend_arrow(twd_series)
        else:
            raise Exception("台幣匯率歷史長度不足 30 天")
    except Exception as e:
        print("台幣匯率動態偏離率計算失敗:", e)
        data['twd_fx'], data['twd_bias_pct'], data['twd_arrow'] = None, None, "⏳"

    # --- 6. 台股加權指數 20日乖離率 (🛠️ 修正負數索引切片邊界) ---
    try:
        twii_series = df['Close']['^TWII'].dropna()
        current_twii = twii_series.iloc[-1]
        ma_20 = twii_series.iloc[-20:].mean()
        bias_val = ((current_twii - ma_20) / ma_20) * 100
        
        bias_history = []
        for i in range(-5, 0):
            day_twii = twii_series.iloc[i]
            # 🛠️ 導入主任指導的 end_idx 修正，防止 i = -1 時切出空矩陣
            end_idx = i + 1 if i + 1 != 0 else len(twii_series)
            day_ma20 = twii_series.iloc[i-19 : end_idx].mean()
            bias_history.append(((day_twii - day_ma20) / day_ma20) * 100)
            
        data['tw_bias'] = round(bias_val, 2)
        data['tw_bias_arrow'] = get_trend_arrow(pd.Series(bias_history))
    except Exception as e:
        print("台股20日乖離率計算失敗:", e)
        data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"

    # 【每月長週期慢指標】(🛠️ 移除獨立下載，直接由共用大數據 df 提取)
    if is_monthly_check:
        try:
            w5000 = df['Close']['^W5000'].dropna().iloc[-1]
            data['buffett_indicator'] = (w5000 / 25000) * 100 
        except Exception as e:
            print("自共用矩陣提取巴菲特指數延遲，啟動防禦估算:", e)
            data['buffett_indicator'] = 185.0
            
        try:
            gspc_series = df['Close']['^GSPC'].dropna()
            data['sp500_ma_bias'] = ((gspc_series.iloc[-1] - gspc_series.mean()) / gspc_series.mean()) * 100
        except Exception as e:
            print("標普2年乖離率精算延遲:", e)
            data['sp500_ma_bias'] = 12.5

    total_score = 0
    
    # --- 評分與個別燈號判定 ---
    if data['vix'] is None: vix_text, vix_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        vix_text = f"{data['vix']:.2f} {data['vix_arrow']}"
        if data['vix'] > 30: total_score += 2; vix_alert = "🔴 恐慌 (2分)"
        elif data['vix'] > 20: total_score += 1; vix_alert = "🟡 警戒 (1分)"
        else: vix_alert = "🟢 正常 (0分)"

    if data['pe_ratio'] is None: pe_text, pe_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        pe_text = f"{data['pe_ratio']:.1f} 倍"
        if data['pe_ratio'] > 30: total_score += 2; pe_alert = "🔴 極高 (2分)"
        elif data['pe_ratio'] > 26: total_score += 1; pe_alert = "🟡 偏高 (1分)"
        else: pe_alert = "🟢 合理 (0分)"

    if data['yield_spread_bps'] is None: yield_text, yield_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        yield_text = f"{data['yield_spread_bps']:.1f} bps {data['yield_arrow']}"
        if data['yield_spread_bps'] < -50: total_score += 2; yield_alert = "🔴 深層倒掛 (2分)"
        elif data['yield_spread_bps'] < 0: total_score += 1; yield_alert = "🟡 倒掛 (1分)"
        else: yield_alert = "🟢 正常 (0分)"

    if data['hy_oas'] is None: hy_text, hy_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        hy_text = f"{data['hy_oas']:+.2f}% {data['hy_arrow']}"
        if data['hy_oas'] < -3.5: total_score += 2; hy_alert = "🔴 信用市場劇烈重挫 (2分)"
        elif data['hy_oas'] < -1.5: total_score += 1; hy_alert = "🟡 信用動能趨緩跌幅過大 (1分)"
        else: hy_alert = "🟢 信用穩健/溫和擴張 (0分)"

    if data['twd_bias_pct'] is None: twd_text, twd_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        twd_text = f"{data['twd_fx']:.3f} ({data['twd_bias_pct']:+.2f}% 偏離) {data['twd_arrow']}"
        if data['twd_bias_pct'] > 1.5: total_score += 2; twd_alert = "🔴 資金極端外流/大幅超貶 (2分)"
        elif data['twd_bias_pct'] > 0.5: total_score += 1; twd_alert = "🟡 匯率趨貶/偏離常軌 (1分)"
        else: twd_alert = "🟢 匯率穩健/資金回流區間 (0分)"

    if data['tw_bias'] is None: tw_text, tw_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        tw_text = f"{data['tw_bias']:.2f}% {data['tw_bias_arrow']}"
        if data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0: total_score += 2; tw_alert = "🔴 短線極端過熱/超跌 (2分)"
        elif data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0: total_score += 1; tw_alert = "🟡 乖離偏大注意修正 (1分)"
        else: tw_alert = "🟢 正常軌道內 (0分)"

    # 🛠️ --- 3. 新增 risk_history.json 歷史風險動態比對邏輯 ---
    risk_file = "risk_history.json"
    yesterday_score_text = "🔄 初次觀測啟動"
    
    # 讀取昨日紀錄
    if os.path.exists(risk_file):
        try:
            with open(risk_file, "r", encoding="utf-8") as f:
                risk_history = json.load(f)
            if risk_history.get("records"):
                last_score = risk_history["records"][-1].get("total_score", 0)
                if total_score > last_score:
                    trend_sign = f"升 {total_score - last_score} 分 🔺"
                elif total_score < last_score:
                    trend_sign = f"降 {last_score - total_score} 分 🔻"
                else:
                    trend_sign = "持平 ➡️"
                yesterday_score_text = f"{last_score} 分 → 今日 {total_score} 分 ({trend_sign})"
        except Exception as e:
            print("讀取 risk_history.json 異常:", e)
    else:
        risk_history = {"records": []}

    # 寫入今日新紀錄
    try:
        risk_history["records"].append({
            "date": taiwan_time.strftime("%Y-%m-%d"),
            "total_score": total_score
        })
        # 僅保留最近 90 天紀錄，防範檔案肥大
        risk_history["records"] = risk_history["records"][-90:]
        with open(risk_file, "w", encoding="utf-8") as f:
            json.dump(risk_history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("儲存 risk_history.json 失敗:", e)

    # 決定核心總燈號
    if total_score >= 9: status_light = f"🔴 【四級總經極端風暴紅燈】停利回收現金"
    elif total_score >= 6: status_light = f"🟠 【三級總經高風險橘燈】減碼/停止不定期加碼"
    elif total_score >= 3: status_light = f"🟡 【二級總經市場觀望黃燈】暫緩用大資金盲目追高"
    else: status_light = f"🟢 【一級總經安全綠燈】紀律扣款/大膽執行加碼"
        
    report = (
        f"🚨 【unclelee 總經加權風控塔台】\n"
        f"⏰ 觀測時間 (台灣): {taiwan_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"📉 風險軌跡: 昨日 {yesterday_score_text}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🚦 風控總指揮燈號：\n"
        f"{status_light}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📊 核心量化指標多維體檢 (🔺代表風險上升/🔻代表風險下降)：\n"
        f"• VIX 恐慌指數: {vix_text} -> {vix_alert}\n"
        f"• S&P500 本益比: {pe_text} -> {pe_alert}\n"
        f"• 10Y-2Y美債利差: {yield_text} -> {yield_alert}\n"
        f"• 高收益債動能 (HYG近30日變化): {hy_text} -> {hy_alert}\n"
        f"• 台幣兌美元匯率 (近30日動態偏離): {twd_text} -> {twd_alert}\n"
        f"• 台股20日乖離率: {tw_text} -> {tw_alert}\n"
    )
    
    if is_monthly_check:
        buffett_alert = "🟢 安全" if data['buffett_indicator'] < 190 else "🟡 歷史高位"
        bias_alert = "🟢 正常" if data['sp500_ma_bias'] < 15 else "🟡 乖離過大"
        report += (
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📅 【每月 1 號大盤長週期體檢】\n"
            f"• 巴菲特指數: {data['buffett_indicator']:.1f}% -> {buffett_alert}\n"
            f"• 標普500 2年均線乖離率: {data['sp500_ma_bias']:.1f}% -> {bias_alert}\n"
        )
        
    report += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n💡 哨兵提示：本系統已全面活化「跨市場
