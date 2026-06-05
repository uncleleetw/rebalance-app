import streamlit as st
import json
import os

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

# 讀取歷史資料
user_shares = load_data()

st.title("📊 資產再平衡計算器")
st.write(f"設定總資產規模：{TOTAL_BUDGET:,} 元 | 目標比例：40% : 40% : 20%")

# --- 區塊一：初始設定（如果沒有歷史資料，或想重新設定） ---
with st.expander("⚙️ 初始投資金額設定 (免重複輸入)", expanded=(user_shares is None)):
    st.write("請輸入您各檔標的當初投資的金額與買入價格，系統會自動換算為持有股數。")
    
    col1, col2 = st.columns(2)
    init_data = {}
    
    with col1:
        amt_713 = st.number_input("00713 投資金額 (元)", value=480000)
        amt_voo = st.number_input("VOO 投資金額 (元)", value=480000)
        amt_smh = st.number_input("SMH 投資金額 (元)", value=240000)
    with col2:
        pri_713 = st.number_input("00713 買入價格", value=50.0)
        pri_voo = st.number_input("VOO 買入價格", value=500.0)
        pri_smh = st.number_input("SMH 買入價格", value=250.0)
        
    if st.button("💾 儲存配置資料"):
        user_shares = {
            "00713": amt_713 / pri_713,
            "VOO": amt_voo / pri_voo,
            "SMH": amt_smh / pri_smh
        }
        save_data(user_shares)
        st.success("配置已成功儲存！未來不需重新輸入。")
        st.rerun()

# --- 區塊二：即時價格輸入與再平衡檢查 ---
if user_shares is not None:
    st.subheader("🚀 步驟二：輸入現價檢查再平衡")
    
    p_col1, p_col2, p_col3 = st.columns(3)
    with p_col1:
        now_713 = st.number_input("00713 現在價格", value=50.0)
    with p_col2:
        now_voo = st.number_input("VOO 現在價格", value=500.0)
    with p_col3:
        now_smh = st.number_input("SMH 現在價格", value=250.0)
        
    if st.button("🧮 開始計算再平衡", type="primary"):
        current_prices = {"00713": now_713, "VOO": now_voo, "SMH": now_smh}
        current_values = {k: user_shares[k] * current_prices[k] for k in TARGET_RATIOS.keys()}
        total_current_value = sum(current_values.values())
        
        st.markdown(f"### 目前資產總市值：**{total_current_value:,.0f}** 元")
        
        need_rebalance = False
        
        # 顯示結果表格
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
                
            st.markdown(
                f"**{ticker}**：當前市值 `{current_values[ticker]:,.0f}` 元 | "
                f"實際比例 `:{color}[{actual_ratio*100:.1f}%]` (目標 {target_ratio*100:.0f}%) -> **{status}**"
            )
            
        st.divider()
        
        if need_rebalance:
            st.warning("💡 **再平衡建議**：部分資產已偏離目標配置（超過 ±2%）。建議您可以透過『賣高買低』，或是利用『新資金優先買進比例落後的標的』來調整回 40% : 40% : 20% 的黃金比例。")
        else:
            st.success("💡 **再平衡建議**：目前各資產比例都在理想範圍內，繼續保持，定期檢查即可！")
else:
    st.info("請先在上方的『初始投資金額設定』中儲存您的資產配置。")