import os
import requests
import yfinance as yf

# ==========================================
# ⚙️ 內建持股與目標比例 (與 App 同步)
# ==========================================
PORTFOLIO_CONFIG = {
    "00713": {"shares": 10153, "buy_price_twd": 51.45},
    "VOO":   {"shares": 25,    "buy_price_usd": 611.64},
    "SMH":   {"shares": 18,    "buy_price_usd": 396.47}
}

TARGET_RATIOS = {"00713": 0.40, "VOO": 0.40, "SMH": 0.20}
THRESHOLD = 0.02  # 2% 的允許波動區間

def get_single_ticker_price(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="1d")
        if not df.empty:
            return float(df['Close'].iloc[-1])
        return float(ticker.fast_info['last_price'])
    except:
        return None

def send_line_message(access_token, user_id, message_text):
    """使用新版 Messaging API 推播訊息給指定用戶"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"LINE 發送失敗，狀態碼: {response.status_code}, 回應: {response.text}")

def main():
    # 從 GitHub Secrets 中讀取密鑰
    access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not access_token or not user_id:
        print("錯誤: 找不到 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID 密鑰設定")
        return

    # 抓取即時數據
    price_713 = get_single_ticker_price("00713.TW")
    price_voo = get_single_ticker_price("VOO")
    price_smh = get_single_ticker_price("SMH")
    fx = get_single_ticker_price("TWD=X")

    if not all([price_713, price_voo, price_smh, fx]):
        print("錯誤: 抓取部分即時股價或匯率失敗")
        return

    # 計算市值
    val_713 = PORTFOLIO_CONFIG["00713"]["shares"] * price_713
    val_voo = (PORTFOLIO_CONFIG["VOO"]["shares"] * price_voo) * fx
    val_smh = (PORTFOLIO_CONFIG["SMH"]["shares"] * price_smh) * fx
    total_val = val_713 + val_voo + val_smh

    # 計算比例
    r_713 = val_713 / total_val
    r_voo = val_voo / total_val
    r_smh = val_smh / total_val

    diff_713 = r_713 - TARGET_RATIOS["00713"]
    diff_voo = r_voo - TARGET_RATIOS["VOO"]
    diff_smh = r_smh - TARGET_RATIOS["SMH"]

    need_rebalance = abs(diff_713) > THRESHOLD or abs(diff_voo) > THRESHOLD or abs(diff_smh) > THRESHOLD

    # 組裝 LINE 訊息內容
    msg = f"📊 每日資產再平衡定期回報\n"
    msg += f"💵 當前美金匯率: {fx:.2f}\n"
    msg += f"💰 組合總市值: {total_val:,.0f} 元台幣\n"
    msg += f"------------------------\n"
    msg += f"📈 實際比例 (目標):\n"
    msg += f"• 00713: {r_713*100:.1f}% ({TARGET_RATIOS['00713']*100:.0f}%)\n"
    msg += f"• VOO: {r_voo*100:.1f}% ({TARGET_RATIOS['VOO']*100:.0f}%)\n"
    msg += f"• SMH: {r_smh*100:.1f}% ({TARGET_RATIOS['SMH']*100:.0f}%)\n"
    msg += f"------------------------\n"

    if need_rebalance:
        msg += "⚠️ 警告：部分資產比例已偏離超過 ±2%！建議找時間進行再平衡調整。"
    else:
        msg += "✅ 狀態：目前各資產比例都在理想範圍內，表現正常！"

    send_line_message(access_token, user_id, msg)
    print("LINE 機器人每日通知發送成功！")

if __name__ == "__main__":
    main()
