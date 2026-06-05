import streamlit as st
import yfinance as yf

# 設定網頁標題與風格
st.set_page_config(page_title="資產再平衡計算器", layout="centered")

# ==========================================
# ⚙️ 內建您的真實精確持股與均價成本
# ==========================================
PORTFOLIO_CONFIG = {
    "00713": {"shares": 10153, "buy_price_twd": 51.45},  # 台幣計價
    "VOO":   {"shares": 25,    "buy_price_usd": 611.64}, # 美元計價
    "SMH":   {"shares": 18,    "buy_price_usd": 396.47}  # 美元計價
}

TARGET_RATIOS = {"00713": 0.40, "VOO": 0.40, "SMH": 0.20}
TOTAL_BUDGET = 1200000
THRESHOLD = 0.02  # 2% 的允許波動區間

# 直接讀取內建股數
USER_SHARES = {
    "00713": PORTFOLIO_CONFIG["00713"]["shares"],
    "VOO":   PORTFOLIO_CONFIG["VOO"]["shares"],
    "SMH":   PORTFOLIO_CONFIG["SMH"]["shares"]
}

# 逐一獲取即時市價與匯率（確保穩定度）
def get_single_ticker_price(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="1d")
        if not df.empty:
            return float(df['Close'].iloc[-1])
        return float(ticker.fast_info['last_price'])
    except:
        return None

def get_live_data():
    prices = {}
    prices["00713"] = get_single_ticker_price("00713.TW")
    prices["VOO"] = get_single_ticker_price("VOO")
    prices["SMH"] = get_single_ticker_price("SMH")
    prices["fx"] = get_single_ticker_price("TWD=X")
    return prices

# --- 網頁主畫面 ---
st.title("📊 自動化資產再平衡計算器")
#st.write(f"設定總資產規模：{TOTAL_BUDGET:,} 元台幣 | 目標比例：40% : 40% : 20%")

st.subheader("🚀 即時資產狀態 (自動更新)")

# 預設一打開就自動計算，或點擊按鈕手動整理
if st.button("🔄 重新整理並計算", type="primary") or 'live_prices' not in st.session_state:
    with st.spinner("正在從 Yahoo Finance 獲取全球即時股價與匯率..."):
        st.session_state.live_prices = get_live_data()
        
live_data = st.session_state.get('live_prices')

# 檢查資料完整性
if live_data and all(v is not None for v in live_data.values()):
    usd_to_twd = live_data["fx"]
    st.info(f"💡 偵測到當前美金兌台幣匯率：**{usd_to_twd:.2f}**")
    
    current_prices = {"00713": live_data["00713"], "VOO": live_data["VOO"], "SMH": live_data["SMH"]}
    raw_values = {k: USER_SHARES[k] * current_prices[k] for k in TARGET_RATIOS.keys()}
    
    # 計算原本投入的總台幣成本（供未來對比參考，美股部分以當前匯率換算粗估）
    cost_713_twd = PORTFOLIO_CONFIG["00713"]["shares"] * PORTFOLIO_CONFIG["00713"]["buy_price_twd"]
    cost_voo_twd = (PORTFOLIO_CONFIG["VOO"]["shares"] * PORTFOLIO_CONFIG["VOO"]["buy_price_usd"]) * usd_to_twd
    cost_smh_twd = (PORTFOLIO_CONFIG["SMH"]["shares"] * PORTFOLIO_CONFIG["SMH"]["buy_price_usd"]) * usd_to_twd
    total_cost_twd = cost_713_twd + cost_voo_twd + cost_smh_twd
    
    # 統一換算台幣現值
    current_values = {
        "00713": raw_values["00713"],
        "VOO": raw_values["VOO"] * usd_to_twd,
        "SMH": raw_values["SMH"] * usd_to_twd
    }
    total_current_value = sum(current_values.values())
    
    # 計算整體總報酬率
    total_profit_rate = ((total_current_value - total_cost_twd) / total_cost_twd) * 100
    
    st.markdown(f"### 目前資產總市值：**{total_current_value:,.0f}** 元台幣 (預估總投報率: `{total_profit_rate:+.2f}%`)")
    
    need_rebalance = False
    
    for ticker in TARGET_RATIOS.keys():
        actual_ratio = current_values[ticker] / total_current_value
        target_ratio = TARGET_RATIOS[ticker]
        diff = actual_ratio - target_ratio
        
        if abs(diff) > THRESHOLD:
            status = "⚠️ 需要調整"
            need_rebalance = True
            color = "red"
        else:
            status = "✅ 正常"
            color = "green"
        
        currency_unit = "NTD" if ticker == "00713" else "USD"
        st.markdown(
            f"**{ticker}** (現價: `{current_prices[ticker]:,.2f}`): 市值 `{raw_values[ticker]:,.1f}` {currency_unit} "
            f"(折合台幣 `{current_values[ticker]:,.0f}` 元) | "
            f"實際比例 `:{color}[{actual_ratio*100:.1f}%]` (目標 {target_ratio*100:.0f}%) -> **{status}**"
        )
        
    st.divider()
    
    if need_rebalance:
        st.warning("💡 **再平衡建議**：部分資產獲利或波動已偏離目標配置（超過 ±2%）。建議您可以透過『賣高買低』調整回黃金比例。")
    else:
        st.success("💡 **再平衡建議**：目前各資產比例都在理想範圍內，繼續保持！")
else:
    st.error("⚠️ 暫時無法取得完整股價資訊，請稍候幾秒再按一次『重新整理並計算』。")
