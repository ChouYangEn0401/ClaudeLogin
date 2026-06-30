# -*- coding: utf-8 -*-
"""
example_usage.py — 示範你的「另一支程式」如何用訂閱方案呼叫 Claude 做資料整理。

這是「直接 import」的用法（最推薦）：純 Python 字串進出，沒有任何編碼地雷。
執行：  python example_usage.py
"""

from claude_subscription import ask, ClaudeError


def demo_1_純文字整理():
    """把一段雜亂中文整理成條列重點。"""
    messy = (
        "今天開會討論了三件事，第一是下週要交季報所以禮拜三前大家把數字給我，"
        "另外行銷預算砍了 15%，還有就是新人 Amy 下週一報到要有人帶。"
    )
    r = ask(f"把這段會議記錄整理成不超過三點的待辦清單，每點以動詞開頭：\n{messy}", model="haiku")
    print("【示範1：重點整理】")
    print(r.text)
    print(f"（花費 ${r.cost_usd:.5f}）\n")


def demo_2_結構化JSON():
    """把雜亂聯絡資料抽成嚴格的 JSON 結構（用 json_schema 保證格式）。"""
    raw = "小明 0912345678 住台北；阿華電話 0922-333-444 在高雄；David 0955 666 777 台中"
    schema = {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "city": {"type": "string"},
                    },
                    "required": ["name", "phone", "city"],
                },
            }
        },
        "required": ["people"],
    }
    r = ask(
        f"把以下聯絡資料整理成 JSON，電話只保留數字：\n{raw}",
        model="haiku",
        json_schema=schema,
        max_budget_usd=0.10,  # 安全上限：單次最多花 $0.10
    )
    print("【示範2：結構化 JSON】")
    data = r.data  # 已解析成 Python dict
    for p in data["people"]:
        print(f"  - {p['name']} / {p['phone']} / {p['city']}")
    print(f"（花費 ${r.cost_usd:.5f}）\n")


def demo_3_批次處理():
    """模擬一批資料逐筆處理，並累計花費（讓你掌握額度消耗）。"""
    items = ["The weather is nice", "我很生氣", "這產品還行啦", "退貨流程有夠爛"]
    total = 0.0
    print("【示範3：批次情緒分類】")
    for text in items:
        r = ask(
            f"判斷這句話的情緒，只回 positive / neutral / negative 其中一個字：{text}",
            model="haiku",
        )
        print(f"  {text!r:<28} -> {r.text.strip()}")
        total += r.cost_usd
    print(f"（本批共 {len(items)} 筆，合計花費 ${total:.5f}）\n")


def demo_4_session延續():
    """多輪對話：第一輪記住資訊，第二輪 resume 接續，驗證 Claude 記得上下文。"""
    print("【示範4：session 延續對話】")
    r1 = ask("記住一個資訊：我的專案代號是『獵戶座』。只回覆 OK。", persist=True)
    print(f"  第一輪 -> {r1.text.strip()}（session={r1.session_id[:8]}…）")
    r2 = ask("我的專案代號是什麼？只回代號。", resume=r1.session_id)
    print(f"  第二輪 -> {r2.text.strip()}")
    print(f"（合計花費 ${r1.cost_usd + r2.cost_usd:.5f}）\n")


if __name__ == "__main__":
    try:
        demo_1_純文字整理()
        demo_2_結構化JSON()
        demo_3_批次處理()
        demo_4_session延續()
    except ClaudeError as e:
        print(f"呼叫失敗：{e}")
