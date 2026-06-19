import os
import json
import datetime
import requests
import yfinance as yf

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
# 🧠 第一大核心：總經加權風控塔台 (原風控指標通知程式邏輯)
# =========================================================================
def get_risk_control_report():
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    is_monthly_check = (taiwan_time.day == 1)
    
    data = {}
    
    # 同時下載所有需要的歷史K線，設定40天大緩衝，極大化降低被 Yahoo 阻擋的機率
    try:
        tickers = ["^VIX", "SPY", "^GSPC", "^TNX", "^2Y", "HYG", "TWD=X", "^TWII"]
        df = yf.download(tickers, period="40d", progress=False)
    except Exception:
        df = None

    # --- 1. VIX 恐慌指數 ---
    try:
        vix_series = df['Close']['^VIX'].dropna() if df is not None else yf.Ticker("^VIX").history(period="5d")['Close'].dropna()
        data['vix'] = float(vix_series.iloc[-1])
        data['vix_arrow'] = get_trend_arrow(vix_series)
    except Exception:
        data['vix'], data['vix_arrow'] = None, "⏳"

    # --- 2. S&P 500 本益比 ---
    try:
        spy = yf.Ticker("SPY")
        pe_val = spy.info.get('trailingPE') or spy.fast_info.get('trailing_pe') or spy.info.get('forwardPE')
        if pe_val and pe_val > 0:
            data['pe_ratio'] = float(pe_val)
        else:
            sp500_close = df['Close']['^GSPC'].dropna() if df is not None else yf.Ticker("^GSPC").history(period="5d")['Close'].dropna()
            data['pe_ratio'] = round(float(sp500_close.iloc[-1]) / 238.5, 1)
    except Exception:
        data['pe_ratio'] = None

    # --- 3. 10Y-2Y 美債利差 ---
    try:
        t10_series = df['Close']['^TNX'].dropna() if df is not None else yf.Ticker("^TNX").history(period="5d")['Close'].dropna()
        t02_series = df['Close']['^2Y'].dropna() if df is not None else yf.Ticker("^2Y").history(period="5d")['Close'].dropna()
        
        spread_series = (t10_series - t02_series).dropna()
        val = spread_series.iloc[-1]
        if val > 15: val /= 10  # 修正 yfinance 10倍放大BUG
        
        spread_bps_series = spread_series * (10 if spread_series.iloc[-1] > 15 else 100)
        data['yield_spread_bps'] = round(val * (1 if val > 15 else 100), 1)
        data['yield_arrow'] = get_trend_arrow(spread_bps_series)
    except Exception:
        data['yield_spread_bps'], data['yield_arrow'] = None, "⏳"

    # --- 4. 高收益債利差 (HY OAS 逆向推導模型) ---
    try:
        hyg_series = df['Close']['HYG'].dropna() if df is not None else yf.Ticker("HYG").history(period="5d")['Close'].dropna()
        hy_oas_series = (100 - hyg_series) * 0.15 + 2.2
        data['hy_oas'] = round(float(hy_oas_series.iloc[-1]), 2)
        data['hy_arrow'] = get_trend_arrow(hy_oas_series)
    except Exception:
        data['hy_oas'], data['hy_arrow'] = None, "⏳"

    # --- 5. 台幣兌美元匯率 ---
    try:
        twd_series = df['Close']['TWD=X'].dropna() if df is not None else yf.Ticker("TWD=X").history(period="5d")['Close'].dropna()
        data['twd_fx'] = round(float(twd_series.iloc[-1]), 3)
        data['twd_arrow'] = get_trend_arrow(twd_series)
    except Exception:
        data['twd_fx'], data['twd_arrow'] = None, "⏳"

    # --- 6. 台股加權指數 20日乖離率 ---
    try:
        twii_series = df['Close']['^TWII'].dropna() if df is not None else yf.Ticker("^TWII").history(period="35d")['Close'].dropna()
        current_twii = twii_series.iloc[-1]
        ma_20 = twii_series.iloc[-20:].mean()
        bias_val = ((current_twii - ma_20) / ma_20) * 100
        
        bias_history = []
        for i in range(-5, 0):
            day_twii = twii_series.iloc[i]
            day_ma20 = twii_series.iloc[i-19 : i+1 if i+1 != 0 else None].mean()
            bias_history.append(((day_twii - day_ma20) / day_ma20) * 100)
            
        import pandas as pd
        data['tw_bias'] = round(bias_val, 2)
        data['tw_bias_arrow'] = get_trend_arrow(pd.Series(bias_history))
    except Exception:
        data['tw_bias'], data['tw_bias_arrow'] = None, "⏳"

    # 【每月長週期慢指標】
    if is_monthly_check:
        try:
            w5000 = df['Close']['^W5000'].dropna().iloc[-1] if df is not None else yf.Ticker("^W5000").history(period="5d")['Close'].dropna().iloc[-1]
            data['buffett_indicator'] = (w5000 / 25000) * 100 
        except Exception:
            data['buffett_indicator'] = 185.0
            
        try:
            gspc_series = df['Close']['^GSPC'].dropna() if df is not None else yf.Ticker("^GSPC").history(period="2y")['Close'].dropna()
            data['sp500_ma_bias'] = ((gspc_series.iloc[-1] - gspc_series.mean()) / gspc_series.mean()) * 100
        except Exception:
            data['sp500_ma_bias'] = 12.5

    total_score = 0
    
    # --- 評分邏輯 (每項 0 - 2 分) ---
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
        hy_text = f"{data['hy_oas']:.2f}% {data['hy_arrow']}"
        if data['hy_oas'] > 5.0: total_score += 2; hy_alert = "🔴 信用風險極高 (2分)"
        elif data['hy_oas'] > 4.0: total_score += 1; hy_alert = "🟡 風險溢價攀升 (1分)"
        else: hy_alert = "🟢 信用穩健 (0分)"

    if data['twd_fx'] is None: twd_text, twd_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        twd_text = f"{data['twd_fx']:.3f} {data['twd_arrow']}"
        if data['twd_fx'] > 32.8: total_score += 2; twd_alert = "🔴 強烈貶值外資出逃 (2分)"
        elif data['twd_fx'] > 32.2: total_score += 1; twd_alert = "🟡 趨貶觀望 (1分)"
        else: twd_alert = "🟢 台幣強勢/資產吸金 (0分)"

    if data['tw_bias'] is None: tw_text, tw_alert = "數據擷取延遲 ⏳", "⚪ 觀測中"
    else:
        tw_text = f"{data['tw_bias']:.2f}% {data['tw_bias_arrow']}"
        if data['tw_bias'] > 6.0 or data['tw_bias'] < -8.0: total_score += 2; tw_alert = "🔴 短線極端過熱/超跌 (2分)"
        elif data['tw_bias'] > 3.5 or data['tw_bias'] < -5.0: total_score += 1; tw_alert = "🟡 乖離偏大注意修正 (1分)"
        else: tw_alert = "🟢 正常軌道內 (0分)"

    if total_score >= 9: status_light = f"🔴 【四級總經極端風暴紅燈】停利回收現金 (總分: {total_score}分)"
    elif total_score >= 6: status_light = f"🟠 【三級總經高風險橘燈】減碼/停止不定期加碼 (總分: {total_score}分)"
    elif total_score >= 3: status_light = f"🟡 【二級總經市場觀望黃燈】暫緩用大資金盲目追高 (總分: {total_score}分)"
    else: status_light = f"🟢 【一級總經安全綠燈】紀律扣款/大膽執行加碼 (總分: {total_score}分)"
        
    report = (
        f"🚨 【unclelee 總經加權風控塔台】\n"
        f"⏰ 觀測時間 (台灣): {taiwan_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🚦 風控總指揮燈號：\n"
        f"{status_light}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📊 核心量化指標多維體檢 (🔺代表風險上升/🔻代表風險下降)：\n"
        f"• VIX 恐慌指數: {vix_text} -> {vix_alert}\n"
        f"• S&P500 本益比: {pe_text} -> {pe_alert}\n"
        f"• 10Y-2Y美債利差: {yield_text} -> {yield_alert}\n"
        f"• 高收益債利差(HY OAS): {hy_text} -> {hy_alert}\n"
        f"• 台幣兌美元匯率: {twd_text} -> {twd_alert}\n"
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
        
    report += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n💡 哨兵提示：本系統已全面活化「跨市場分數加權制」，協助您排除單一雜訊、落實極致冷靜的科學紀律。"
    return report

# =========================================================================
# 📊 第二大核心：資產再平衡決策哨兵 (原資產再平衡通知程式邏輯)
# =========================================================================
def get_rebalance_report():
    # --- 從 config.json 讀取持股 ---
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            shares_00713 = config_data.get("shares_00713", 10153)
            shares_voo = config_data.get("shares_voo", 28)
            shares_smh = config_data.get("shares_smh", 15)
        except Exception as e:
            return f"❌ 系統錯誤：讀取 config.json 失敗。\n原因: {str(e)}"
    else:
        shares_00713, shares_voo, shares_smh = 10153, 28, 15

    target_00713 = 0.40
    target_voo = 0.40      
    target_smh = 0.20      

    try:
        tickers = ["00713.TW", "VOO", "SMH", "TWD=X"]
        df = yf.download(tickers, period="8d", progress=False)
        if df.empty or 'Close' not in df: raise Exception("Yahoo Finance API 讀取失敗")
            
        close_df = df['Close']
        p_00713 = float(close_df['00713.TW'].dropna().iloc[-1])
        p_voo = float(close_df['VOO'].dropna().iloc[-1])
        p_smh = float(close_df['SMH'].dropna().iloc[-1])
        usd_to_twd = float(close_df['TWD=X'].dropna().iloc[-1])
    except Exception as e:
        return f"❌ 系統錯誤：無法取得即時市場價格，再平衡計算中止。\n原因: {str(e)}"

    def calc_5d_pct(ticker_name):
        try:
            series = close_df[ticker_name].dropna()
            if len(series) >= 6:
                pct = ((series.iloc[-1] - series.iloc[-6]) / series.iloc[-6]) * 100
                return f"{'+' if pct >= 0 else ''}{pct:.1f}%"
        except: pass
        return "暫無數據"

    pct_00713 = calc_5d_pct('00713.TW')
    pct_voo = calc_5d_pct('VOO')
    pct_smh = calc_5d_pct('SMH')

    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    is_ex_dividend_day = False
    try:
        t_00713 = yf.Ticker("00713.TW")
        divs = t_00713.dividends
        if not divs.empty:
            latest_div_date = divs.index[-1].date()
            today_date = taiwan_time.date()
            if 0 <= (today_date - latest_div_date).days <= 2: is_ex_dividend_day = True
    except:
        if taiwan_time.month in [3, 6, 9, 12] and 15 <= taiwan_time.day <= 20: is_ex_dividend_day = True

    v_00713 = shares_00713 * p_00713
    v_voo = shares_voo * p_voo * usd_to_twd
    v_smh = shares_smh * p_smh * usd_to_twd
    total_portfolio_value = v_00713 + v_voo + v_smh

    act_00713 = v_00713 / total_portfolio_value
    act_voo = v_voo / total_portfolio_value
    act_smh = v_smh / total_portfolio_value

    dev_00713 = (act_00713 - target_00713) * 100
    dev_voo = (act_voo - target_voo) * 100
    dev_smh = (act_smh - target_smh) * 100

    def judge_deviation(dev_val, pct_5d, is_00713=False):
        if is_00713 and is_ex_dividend_day:
            return "🟢 正常 (除息日保護中)", "今日為00713除息，比例變化為正常現象，暫不計入偏離判斷", False
            
        abs_dev = abs(dev_val)
        if abs_dev > 5.0:
            try:
                numeric_pct = float(pct_5d.replace('%', ''))
                is_up = numeric_pct >= 0
            except (ValueError, AttributeError):
                is_up = True
            reason = "主因為股價劇烈上漲被動稀釋" if (dev_val * (1 if is_up else -1)) > 0 else "真實資金配置失衡"
            return f"🔴 建議調整 (偏離 {dev_val:+.1f}%)", f"近5日漲跌: {pct_5d}，{reason}", True
        elif abs_dev > 2.0:
            return f"⚠️ 觀察中 (偏離 {dev_val:+.1f}%)", f"近5日漲跌: {pct_5d}，常規市場波動", False
        else:
            return f"🟢 正常 (偏離 {dev_val:+.1f}%)", "資產比例高度契合目標", False

    status_00713, note_00713, trigger_00713 = judge_deviation(dev_00713, pct_00713, is_00713=True)
    status_voo, note_voo, trigger_voo = judge_deviation(dev_voo, pct_voo)
    status_smh, note_smh, trigger_smh = judge_deviation(dev_smh, pct_smh)

    any_trigger = trigger_00713 or trigger_voo or trigger_smh

    def calc_trade(target_ratio, actual_value, current_price, is_usd=False):
        target_value = total_portfolio_value * target_ratio
        diff_twd = target_value - actual_value
        price_twd = current_price * (usd_to_twd if is_usd else 1)
        trade_shares = round(diff_twd / price_twd)
        actual_trade_twd = trade_shares * price_twd
        return trade_shares, actual_trade_twd

    t_shares_00713, t_cost_00713 = calc_trade(target_00713, v_00713, p_00713)
    t_shares_voo, t_cost_voo = calc_trade(target_voo, v_voo, p_voo, is_usd=True)
    t_shares_smh, t_cost_smh = calc_trade(target_smh, v_smh, p_smh, is_usd=True)

    estimated_current_cost = abs(t_cost_00713) + abs(t_cost_voo) + abs(t_cost_smh)

    # --- JSON 本地歷史記錄與「股數真實變動才累加」功能 ---
    history_file = "rebalance_history.json"
    history_data = {"total_count": 0, "total_cost": 0.0, "records": []}

    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f: history_data = json.load(f)
        except: pass

    is_first_report_after_trade = False
    if history_data["records"]:
        last_record = history_data["records"][-1]
        last_shares = last_record.get("shares_snapshot", {})
        if last_shares:
            if (last_shares.get("00713") != shares_00713 or 
                last_shares.get("voo") != shares_voo or 
                last_shares.get("smh") != shares_smh):
                is_first_report_after_trade = True

    if is_first_report_after_trade:
        history_data["total_count"] += 1
        if history_data["records"]:
            history_data["total_cost"] += history_data["records"][-1].get("estimated_cost", 0)

    new_record = {
        "date": taiwan_time.strftime("%Y-%m-%d"),
        "shares_snapshot": {"00713": shares_00713, "voo": shares_voo, "smh": shares_smh},
        "ratios": {"00713": round(act_00713*100,1), "voo": round(act_voo*100,1), "smh": round(act_smh*100,1)},
        "triggered": any_trigger,
        "estimated_cost": round(estimated_current_cost) if any_trigger else 0
    }
    history_data["records"].append(new_record)

    try:
        with open(history_file, "w", encoding="utf-8") as f: json.dump(history_data, f, ensure_ascii=False, indent=4)
    except: pass

    report = (
        f"📊 【unclelee 資產再平衡決策哨兵】\n"
        f"⏰ 觀測時間 (台灣): {taiwan_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"💵 即時美金匯率: {usd_to_twd:.2f} TWD\n"
        f"💰 組合總市值：NT$ {round(total_portfolio_value):,} 元\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🔍 【核心量化分項指標體檢】\n\n"
        f"• 00713 元大高息低波:\n"
        f"  🧮 算式: {shares_00713:,} 股 × {p_00713:.2f} TWD\n"
        f"  💎 實際台幣價值: NT$ {round(v_00713):,} 元\n"
        f"  📊 實際比例 (目標): {act_00713*100:.1f}% ({target_00713*100:.0f}%)\n"
        f"  🚦 風控狀態: {status_00713}\n"
        f"  💡 {note_00713}\n\n"
        f"• VOO 標普500:\n"
        f"  🧮 算式: {shares_voo:,} 股 × {p_voo:.2f} USD\n"
        f"  💎 實際台幣價值: NT$ {round(v_voo):,} 元\n"
        f"  📊 實際比例 (目標): {act_voo*100:.1f}% ({target_voo*100:.0f}%)\n"
        f"  🚦 風控狀態: {status_voo}\n"
        f"  💡 {note_voo}\n\n"
        f"• SMH 費城半導體:\n"
        f"  🧮 算式: {shares_smh:,} 股 × {p_smh:.2f} USD\n"
        f"  💎 實際台幣價值: NT$ {round(v_smh):,} 元\n"
        f"  📊 實際比例 (目標): {act_smh*100:.1f}% ({target_smh*100:.0f}%)\n"
        f"  🚦 風控狀態: {status_smh}\n"
        f"  💡 {note_smh}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🛠️ 演算法一鍵指引建議：\n"
    )

    if any_trigger:
        def format_trade_msg(shares, cost):
            if shares > 0: return f"🟢 應補進 +{shares} 股 (約需投入 NT$ {round(cost):,})"
            elif shares < 0: return f"🔴 應減碼 {shares} 股 (約可回收 NT$ {round(abs(cost)):,})"
            return "➡️ 比例精準，無需變動"
        report += (
            f"🎯 偵測到配置偏離度大於 5%，請執行以下精確平衡交易：\n"
            f"1. 00713: {format_trade_msg(t_shares_00713, t_cost_00713)}\n"
            f"2. VOO  : {format_trade_msg(t_shares_voo, t_cost_voo)}\n"
            f"3. SMH  : {format_trade_msg(t_shares_smh, t_cost_smh)}\n"
        )
    else:
        report += "⚖️ 當前全資產偏離度皆控制在 ±5% 內，配置非常穩健，【今日建議不執行任何交易】。\n"

    report += (
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📊 本年度已執行再平衡：{history_data['total_count']} 次\n"
        f"📊 本年度累積已實現成本：約 NT$ {round(history_data['total_cost']):,}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"💡 決策大腦：資產數據與程式邏輯已完美抽離；現在只有在您實際修正 config.json 中的持股數時，系統才會正式結算再平衡的執行次數與成本。"
    )
    return report

# =========================================================================
# 📤 第三區塊：單次 LINE 訊息整合發送服務
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
# 🚀 核心控制台：依序讀取並執行一次性打包發送
# =========================================================================
def main():
    # 1. 取得第一部分：總經風控報告文字
    risk_report = get_risk_control_report()
    
    # 2. 取得第二部分：資產再平衡報告文字
    rebalance_report = get_rebalance_report()
    
    # 3. 使用您指定的高規雙層厚實分隔線進行字串串接
    combined_report = f"{risk_report}\n\n═══════════════════════════\n\n{rebalance_report}"
    
    # 4. 只呼叫一次 LINE 傳輸服務，完成完美的一次性回報
    send_line_message(combined_report)

if __name__ == "__main__":
    main()
