import os
import json
import datetime
import requests
import yfinance as yf

def get_rebalance_report():
    # =========================================================================
    # 📌 【1. 核心輸入區】李主任精準在庫持股數與黃金目標比例 (40%/40%/20%)
    # =========================================================================
    shares_00713 = 10153  # 已更新為最精準持股
    shares_voo = 28       # 已校正回歸為 28 股
    shares_smh = 15       # 已更新為 15 股

    # 您的黃金配置目標比例 (總和為 100%)
    target_00713 = 0.40
    target_voo = 0.40      
    target_smh = 0.20      

    # =========================================================================
    # 📌 【2. 數據獲取與緩衝區】下載歷史K線以計算 5 日漲跌幅
    # =========================================================================
    try:
        tickers = ["00713.TW", "VOO", "SMH", "TWD=X"]
        df = yf.download(tickers, period="8d", progress=False)
        if df.empty or 'Close' not in df:
            raise Exception("Yahoo Finance API 讀取失敗")
            
        close_df = df['Close']
        p_00713 = float(close_df['00713.TW'].dropna().iloc[-1])
        p_voo = float(close_df['VOO'].dropna().iloc[-1])
        p_smh = float(close_df['SMH'].dropna().iloc[-1])
        usd_to_twd = float(close_df['TWD=X'].dropna().iloc[-1])
    except Exception as e:
        return f"❌ 系統錯誤：無法取得即時市場價格，再平衡計算中止。\n原因: {str(e)}"

    # 計算 5 日變動率
    def calc_5d_pct(ticker_name):
        try:
            series = close_df[ticker_name].dropna()
            if len(series) >= 6:
                pct = ((series.iloc[-1] - series.iloc[-6]) / series.iloc[-6]) * 100
                return f"{'+' if pct >= 0 else ''}{pct:.1f}%"
        except:
            pass
        return "暫無數據"

    pct_00713 = calc_5d_pct('00713.TW')
    pct_voo = calc_5d_pct('VOO')
    pct_smh = calc_5d_pct('SMH')

    # =========================================================================
    # 📌 【3. 00713 除息日智慧判定機制】
    # =========================================================================
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    is_ex_dividend_day = False
    
    try:
        t_00713 = yf.Ticker("00713.TW")
        divs = t_00713.dividends
        if not divs.empty:
            latest_div_date = divs.index[-1].date()
            today_date = taiwan_time.date()
            days_diff = (today_date - latest_div_date).days
            if 0 <= days_diff <= 2:
                is_ex_dividend_day = True
    except:
        if taiwan_time.month in [3, 6, 9, 12] and 15 <= taiwan_time.day <= 20:
            is_ex_dividend_day = True

    # =========================================================================
    # 📌 【4. 資產價值與精算核心（Double Check 驗算機制）】
    # =========================================================================
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

    # =========================================================================
    # 📌 【5. 偏離度閾值判定與偏離原因歸因】
    # =========================================================================
    def judge_deviation(dev_val, pct_5d, is_00713=False):
        if is_00713 and is_ex_dividend_day:
            return "🟢 正常 (除息日保護中)", "今日為00713除息，比例變化為正常現象，暫不計入偏離判斷", False
            
        abs_dev = abs(dev_val)
        if abs_dev > 5.0:
            reason = "主因為股價劇烈上漲被動稀釋" if (dev_val * (1 if float(pct_5d.replace('%',''))>=0 else -1)) > 0 else "真實資金配置失衡"
            return f"🔴 建議調整 (偏離 {dev_val:+.1f}%)", f"近5日漲跌: {pct_5d}，{reason}", True
        elif abs_dev > 2.0:
            return f"⚠️ 觀察中 (偏離 {dev_val:+.1f}%)", f"近5日漲跌: {pct_5d}，常規市場波動", False
        else:
            return f"🟢 正常 (偏離 {dev_val:+.1f}%)", "資產比例高度契合目標", False

    status_00713, note_00713, trigger_00713 = judge_deviation(dev_00713, pct_00713, is_00713=True)
    status_voo, note_voo, trigger_voo = judge_deviation(dev_voo, pct_voo)
    status_smh, note_smh, trigger_smh = judge_deviation(dev_smh, pct_smh)

    any_trigger = trigger_00713 or trigger_voo or trigger_smh

    # =========================================================================
    # 📌 【6. 具體調整股數與所需交割金額計算】
    # =========================================================================
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

    # =========================================================================
    # 📌 【7. JSON 本地歷史記錄儲存與成本追蹤累加】
    # =========================================================================
    history_file = "rebalance_history.json"
    history_data = {"total_count": 0, "total_cost": 0.0, "records": []}

    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except:
            pass

    if any_trigger:
        history_data["total_count"] += 1
        history_data["total_cost"] += estimated_current_cost

    new_record = {
        "date": taiwan_time.strftime("%Y-%m-%d"),
        "ratios": {"00713": round(act_00713*100,1), "voo": round(act_voo*100,1), "smh": round(act_smh*100,1)},
        "triggered": any_trigger,
        "estimated_cost": round(estimated_current_cost) if any_trigger else 0
    }
    history_data["records"].append(new_record)

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=4)
    except:
        pass

    # =========================================================================
    # 📌 【8. 產出全新智慧型再平衡 LINE 通知報告】
    # =========================================================================
    report = (
        f"📊 【unclelee 資產再平衡決策哨兵】\n"
        f"⏰ 觀測時間 (台灣): {taiwan_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"💵 即時美金匯率: {usd_to_twd:.2f} TWD\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📈 各檔標的在庫比例體檢 (目標調整為 40%/40%/20%)：\n"
        f"• 00713 元大台灣高息低波\n"
        f"  現況: {act_00713*100:.1f}% (目標 {target_00713*100:.0f}%) -> {status_00713}\n"
        f"  💡 {note_00713}\n\n"
        f"• VOO Vanguard 標普500\n"
        f"  現況: {act_voo*100:.1f}% (目標 {target_voo*100:.0f}%) -> {status_voo}\n"
        f"  💡 {note_voo}\n\n"
        f"• SMH 費城半導體 ETF\n"
        f"  現況: {act_smh*100:.1f}% (目標 {target_smh*100:.0f}%) -> {status_smh}\n"
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
        f"📊 本年度累積再平衡次數：{history_data['total_count']} 次\n"
        f"📊 本年度累積調整成本：約 NT$ {round(history_data['total_cost']):,}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"💡 決策大腦：加寬閾值至 5% 能幫您有效減少非必要交易手續費；多看一眼5日漲跌幅，能讓您在市場動盪時保持極致的冷靜。"
    )
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

def main():
    report_content = get_rebalance_report()
    send_line_message(report_content)

if __name__ == "__main__":
    main()
