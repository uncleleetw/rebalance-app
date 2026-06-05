import streamlit as st
import json
import os
import yfinance as yf

# 設定網頁標題與風格
st.set_page_config(page_title="資產再平衡計算器", layout="centered")

DATA_FILE = "portfolio_data.json"
TARGET_RATIOS = {"00713": 0.40, "VOO": 0.40, "SMH": 0.20}
TOTAL_BUDGET = 1200000
THRESHOLD = 0.02  # 2% 的允許波動區間

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def save_data(shares):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(shares, f, ensure_ascii=False, indent=4)

# 獲取即時市價與匯率
def get_live_data():
    try:
        # 抓取台股、美股與匯率
        tickers = ["00713.TW", "VOO", "SMH", "TWD=X"]
        data = yf.download(tickers, period="1d")['Close'].iloc[-1]
        
        return {
            "00713": float(data["00713.TW"]),
            "VOO": float(data["VOO"]),
            "SMH": float(data["SMH"]),
            "fx": float(data["TWD=X"])
        }
    except Exception as e:
        st.error(f"無法取得即時股價，錯誤訊息: {e}")
        return None

# 讀取歷史資料
user_shares = load_data()

st.title("📊 自動化資產再平衡計算器")
st.write(f"設定總資產規模：{TOTAL_BUDGET:,} 元台幣 | 目標比例：40% : 40% : 20%")

# --- 區塊一：初始設定（免重複輸入） ---
with st.expander("⚙️ 初始投資金額設定 (00713用台幣，VOO/SMH用美元)", expanded=(user_shares is None)):
    st.write("請輸入您各檔標的當初投資的金額與買入價格，系統會自動換算為持有股數。")
    col1, col2 = st.columns(2)
    with col1:
        amt_713 = st.number_input("00713 投資金額 (NTD)", value=480000)
        amt_voo = st.number_input("VOO 投資金額 (USD)", value=14800)
        amt_smh = st.number_input("SMH 投資金額 (USD)", value=7400)
    with col2:
        pri_713 = st.number_input("00713 買入價格 (NTD)", value=50.0)
        pri_voo = st.number_input("VOO 買入價格 (USD)", value=500.0)
        pri_smh = st.number_input("SMH 買入價格 (USD)", value=250.0)
        
    if st.button("💾 儲存配置資料"):
        user_shares = {
            "00713": amt_713 / pri_713,
            "VOO": amt_voo / pri_voo,
            "SMH": amt_smh / pri_smh
        }
        save_data(user_shares)
        st.success("配置已成功儲存！")
        st.rerun()

# --- 區塊二：自動抓取現價與再平衡檢查 ---
if user_shares is not None:
    st.subheader("🚀 即時資產狀態 (自動更新)")
    
    if st.button("🔄 重新整理並計算", type="primary") or 'live_prices' not in st.session_state:
        with st.spinner("正在從 Yahoo Finance 獲取全球即時股價與匯率..."):
            st.session_state.live_prices = get_live_data()
            
    live_data = st.session_state.get('live_prices')
    
    if live_data:
        usd_to_twd = live_data["fx"]
        st.info(f" 💡 偵測到當前美金兌台幣匯率：**{usd_to_twd:.2f}**")
        
        current_prices = {"00713": live_data["00713"], "VOO": live_data["VOO"], "SMH": live_data["SMH"]}
        raw_values = {k: user_shares[k] * current_prices[k] for k in TARGET_RATIOS.keys()}
        
        # 統一換算台幣市值
        current_values = {
            "00713": raw_values["00713"],
            "VOO": raw_values["VOO"] * usd_to_twd,
            "SMH": raw_values["SMH"] * usd_to_twd
        }
        total_current_value = sum(current_values.values())
        
        st.markdown(f"### 目前資產總市值：**{total_current_value:,.0f}** 元台幣")
        
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
            st.warning("💡 **再平衡建議**：部分資產已偏離目標配置（超過 ±2%）。建議您可以調整回黃金比例。")
        else:
            st.success("💡 **再平衡建議**：目前各資產比例都在理想範圍內，繼續保持！")
