"""
ai_commentary.py — 為「unclelee 總經加權風控塔台」加上 Claude AI 解讀（第 1 層升級）

cron_check.py 在推送 LINE 前呼叫：
    commentary = get_ai_commentary(combined_report, score_history)
    combined_report = append_commentary(combined_report, commentary)

設計原則：
- 只用 requests（requirements.txt 已有），不需另外安裝套件
- 失敗安全：沒有 ANTHROPIC_API_KEY、逾時或 API 錯誤時回傳 None，原本的 LINE 通知照常送出
- 分數與燈號仍由 cron_check.py 的規則引擎負責，AI 只負責「解讀」，不改動任何數字
"""

import os

import requests

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """你是一位審慎的投資風險分析助理，服務對象是一位台灣的個人投資者。
你會收到他的規則引擎產生的「總經加權風控塔台」每日報告（含長線戰略層、短線防護層、資產再平衡），
以及近期每日風險總分的軌跡。請用繁體中文寫一段簡短解讀，讓他在手機 LINE 上 30 秒內讀完。

格式（純文字，不要用 Markdown 符號如 ** 或 #）：
【一句話總結】一句話說明今天整體風險狀態，與報告的指揮燈號一致。
【長線戰略層】1–2 句，解讀趨勢格局、殖利率曲線與估值的意義。
【短線防護層】1–2 句，點出短線指標中最需要注意的一項，沒有就說沒有。
【再平衡】1 句，轉述報告的再平衡結論。
【值得留意】1–3 點：指標之間的背離、與近期軌跡相比的變化，或標示「延遲」、資料時效警示的項目。

規則：
- 只根據報告內容解讀，不要編造報告中沒有的數字、新聞或事件。
- 數字、分數、燈號以報告為準，不要自行重新計算，也不要推翻燈號。
- 不給具體的買賣指令或價位，可以提示「可留意的方向」。
- 總長度控制在 250 字以內。"""


def load_score_history(path="risk_history.json", days=30):
    """讀取近 N 天的風險總分軌跡，讀不到就回傳空字串。"""
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f).get("records", [])[-days:]
        return "、".join(f"{r['date'][5:]}:{r['total_score']}" for r in records)
    except Exception:
        return ""


def get_ai_commentary(report_text, score_history="", timeout=60):
    """把當日報告交給 Claude 解讀，回傳文字；任何失敗都回傳 None。"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[AI解讀] 未設定 ANTHROPIC_API_KEY，略過")
        return None
    print(f"[AI解讀] 呼叫 Claude（{DEFAULT_MODEL}）…")

    content = f"以下是今天的風控塔台報告：\n\n{report_text}"
    if score_history:
        content += f"\n\n近期每日風險總分軌跡（月-日:分數）：\n{score_history}"

    body = {
        "model": DEFAULT_MODEL,
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=body, timeout=timeout)
        if resp.status_code != 200:
            print(f"[AI解讀] HTTP {resp.status_code} | {resp.text[:200]}，略過")
            return None
        data = resp.json()
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks
                       if b.get("type") == "text").strip()
        if not text:
            print(f"[AI解讀] 回應沒有文字內容，略過｜模型 {data.get('model')}｜"
                  f"stop_reason={data.get('stop_reason')}｜"
                  f"區塊={[b.get('type') for b in blocks]}")
            return None
        print(f"[AI解讀] 成功｜模型 {data.get('model')}｜{len(text)} 字")
        return text
    except Exception as e:  # 失敗安全：不讓 AI 這一步拖垮通知
        print(f"[AI解讀] 呼叫失敗，略過：{e}")
        return None


def append_commentary(report_text, commentary):
    """把 AI 解讀接在報告最後（send_line_message 已會自動分段，不必另外截斷）。"""
    if not commentary:
        return report_text
    return (
        f"{report_text}\n\n═══════════════════════════\n\n"
        f"🤖 【AI 解讀】\n{commentary}\n"
        f"（AI 解讀僅供參考，非投資建議）"
    )
