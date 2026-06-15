import os
import datetime
import requests
import yfinance as yf

def get_rebalance_report():
    # 1. 固定輸入李主任目前的精準在庫持股數
    shares_00713 = 10153
    shares_voo = 25
    shares_smh = 18
    
    # 2. 設定原始大盤資產配置目標比例
    target_00713_ratio = 0.40
    target_voo_ratio = 0.40
    target_smh_ratio = 0.20
    
    # 3. 透過 yfinance 抓取台美股最新收盤價與匯率
    try:
        price_00713 = yf.Ticker("00713.TW").history(period="1d")['Close'].iloc[-1]
        price_voo = yf.Ticker("VOO").history(period="1d")['Close'].iloc[-1]
        price_smh = yf.Ticker("SMH").history(period="1d")['Close'].iloc[-1]
        
        # 抓取美金兌台幣最新匯率，以便整合計算總資產
        usdtwd = yf.Ticker("TWD=X").history(period="1d")['Close'].iloc[-1]
    except Exception as e:
        return f"❌ 數據擷取失敗，原因: {str(e)}"
        
    # 4. 計算各資產目前的台幣市值與總資產
    value_00713_twd = shares_00713 * price_00713
    value_voo_twd = shares_voo * price_voo * usdtwd
    value_smh_twd = shares_smh * price_smh * usdtwd
    
    total_assets_twd = value_00713_twd + value_voo_twd + value_smh_twd
    
    # 5. 計算目前的實際資產比例
    actual_00713_ratio = value_00713_twd / total_assets_twd
    actual_voo_ratio = value_voo_twd / total_assets_twd
    actual_smh_ratio = value_smh_twd / total_assets_twd
    
    # 6. 獨立計算美股海外部位的內部再平衡股數與預估交割差價
    total_us_value_usd = (shares_voo * price_voo) + (shares_smh * price_smh)
    
    # 根據 40% : 20% 的權重分配，VOO 應佔美股內部的 2/3，SMH 應佔 1/3
    target_voo_value_usd = total_us_value_usd * (target_voo_ratio / (target_voo_ratio + target_smh_ratio))
    target_smh_value_usd = total_us_value_usd * (target_smh_ratio / (target_voo_ratio + target_smh_ratio))
    
    # 計算美金價值差距
    voo_diff_usd = target_voo_value_usd - (shares_voo * price_voo)
    smh_diff_usd = target_smh_value_usd - (shares_smh * price_smh)
    
    # 換算成建議交易股數 (四捨五入取整數)
    voo_suggest_shares = round(voo_diff_usd / price_voo)
    smh_suggest_shares = round(smh_diff_usd / price_smh)
    
    # 計算買賣應補/應退差價 (買進花費減去賣出收入)
    # 若為正值代表買大於賣，需要補現金；若為負值代表賣大於買，會多出閒置現金
    buy_voo_cost_usd = abs(voo_suggest_shares) * price_voo if voo_suggest_shares > 0 else 0
    sell_smh_revenue_usd = abs(smh_suggest_shares) * price_smh if smh_suggest_shares < 0 else 0
    
    buy_smh_cost_usd = abs(smh_suggest_shares) * price_smh if smh_suggest_shares > 0 else 0
    sell_voo_revenue_usd = abs(voo_suggest_shares) * price_voo if voo_suggest_shares < 0 else 0
    
    if (smh_suggest_shares < 0 and voo_suggest_shares > 0): # 賣 SMH 買 VOO
        est_gap_usd = buy_voo_cost_usd - sell_smh_revenue_usd
    elif (voo_suggest_shares < 0 and smh_suggest_shares > 0): # 賣 VOO 買 SMH
        est_gap_usd = buy_smh_cost_usd - sell_voo_revenue_usd
    else:
        est_gap_usd = 0
        
    est_gap_twd = est_gap_usd * usdtwd
    
    # 7. 判定是否觸發 2% 閾值的警報文字與狀態顯示
    def check_status(actual, target):
        diff = actual - target
        if abs(diff) > 0.02:
            return f"{actual*100:.1f}% ({target*100:.0f}%) -> 偏離 {diff*100:+.1f}% ⚠️"
        return f"{actual*100:.1f}% ({target*100:.0f}%) -> 安全 🟢"

    status_00713 = check_status(actual_00713_ratio, target_00713_ratio)
    status_voo = check_status(actual_voo_ratio, target_voo_ratio)
    status_smh = check_status(actual_smh_ratio, target_smh_ratio)
    
    # 8. 校正台灣時區 (手動加上 8 小時)
    taiwan_time = datetime.datetime.now() + datetime.timedelta(hours=8)
    current_time = taiwan_time.strftime("%Y-%m-%d %H:%M")
    
    # 建立調整建議與差價結算區塊文字
    trade_advice_text = ""
    gap_info = ""
    if est_gap_usd > 0:
        gap_info = f"💰 本次調整預估【需補交割款】: {est_gap_usd:.2f} 美元 (約 NT$ {est_gap_twd:,.0f} 元)"
    elif est_gap_usd < 0:
        gap_info = f"💰 本次調整預估【將多出退款】: {abs(est_gap_usd):.2f} 美元 (約 NT$ {abs(est_gap_twd):,.0f} 元)"
    else:
        gap_info = "💰 本次調整預估【零摩擦免補錢】"

    if smh_suggest_shares < 0 and voo_suggest_shares > 0:
        trade_advice_text = (
            f"🔄 【美股內部再平衡一鍵指引】\n"
            f"👉 進入複委託券商，【賣出】 SMH : {abs(smh_suggest_shares)} 股\n"
            f"👉 賣出資金直接，【買進】 VOO : {voo_suggest_shares} 股\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"{gap_info}"
        )
    elif smh_suggest_shares > 0 and voo_suggest_shares < 0:
        trade_advice_text = (
            f"🔄 【美股內部再平衡一鍵指引】\n"
            f"👉 進入複委託券商，【賣出】 VOO : {abs(voo_suggest_shares)} 股\n"
            f"👉 賣出資金直接，【買進】 SMH : {smh_suggest_shares} 股\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"{gap_info}"
        )
    else:
        trade_advice_text = "🔄 【美股內部再平衡一鍵指引】\n🟢 目前海外部位權重極為平衡，無需手動調整股數。"

    report = (
        f"📈 【每日資產再平衡定期回報】\n"
        f"⏰ 觀測時間: {current_time}\n"
        f"💵 當前美金匯率: {usdtwd:.2f}\n"
        f"💰 組合總市值: {total_assets_twd:,.0f} 元台幣\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🔍 【即時價格 × 股數 ＝ 當前市值】(Double Check)\n"
        f"• 00713: {price_00713:.2f} TWD × {shares_00713} 股 ＝ NT$ {value_00713_twd:,.0f}\n"
        f"• VOO  : {price_voo:.2f} USD × {shares_voo} 股 ＝ US$ {shares_voo*price_voo:,.2f}\n"
        f"• SMH  : {price_smh:.2f} USD × {shares_smh} 股 ＝ US$ {shares_smh*price_smh:,.2f}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📊 實際比例 (目標配置):\n"
        f"• 00713: {status_00713}\n"
        f"• VOO  : {status_voo}\n"
        f"• SMH  : {status_smh}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"{trade_advice_text}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"💡 哨兵提示: 本報告已自動計算複委託圈存差額。若偏離度超過 ±2%，可依指引微調以落實投資紀律。"
    )
    return report

def send_line_message(message_text):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message_text}]
    }
    requests.post(url, headers=headers, json=payload)

def main():
    report_content = get_rebalance_report()
    send_line_message(report_content)

if __name__ == "__main__":
    main()
