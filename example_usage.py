# -*- coding: utf-8 -*-
"""
example_usage.py — 示範你的「另一支程式」如何用訂閱方案呼叫 Claude 做資料整理。

這是「直接 import」的用法（最推薦）：純 Python 字串進出，沒有任何編碼地雷。
執行：  python example_usage.py            # 跑示範 1~4（純文字，很便宜）
       python example_usage.py --agent    # 額外跑示範 5（agent 模式，會寫檔且較貴）
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from claude_subscription import ClaudeError, ask


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
    """多輪對話：第一輪記住資訊，第二輪 resume 接續，驗證 Claude 記得上下文。

    注意 resume 每輪都會重送完整歷史，所以第二輪通常比第一輪貴不少。
    """
    print("【示範4：session 延續對話】")
    r1 = ask("記住一個資訊：我的專案代號是『獵戶座』。只回覆 OK。", persist=True)
    print(f"  第一輪 -> {r1.text.strip()}（session={r1.session_id[:8]}…，${r1.cost_usd:.5f}）")
    r2 = ask("我的專案代號是什麼？只回代號。", resume=r1.session_id)
    print(f"  第二輪 -> {r2.text.strip()}（${r2.cost_usd:.5f}，重送了完整歷史所以較貴）")
    print(f"（合計花費 ${r1.cost_usd + r2.cost_usd:.5f}）\n")


def demo_5_agent模式寫檔():
    """讓 Claude 真的動手改檔案——這才是完整 agent 的樣子。

    三個缺一不可的條件：
      1. tools="default"（或指定像 "Read,Write"）→ 把工具打開
      2. permission_mode="acceptEdits"      → 沒有這個，寫檔會被權限機制擋下
                                              （headless 沒辦法跳出來問你同意）
      3. cwd=某個資料夾                      → 不指定的話，Claude 會在「呼叫這支程式的
                                              目錄」裡讀寫檔案

    另外：因為我們覆寫了系統提示，Claude 不知道自己在哪個資料夾，
    所以提示裡要給**絕對路徑**。

    成本警告：agent 模式要跑好幾個 turn，實測是純文字模式的 15～45 倍。
    """
    print("【示範5：agent 模式（真的會寫檔）】")
    with tempfile.TemporaryDirectory() as workdir:
        target = Path(workdir) / "report.txt"
        r = ask(
            f"Create a file at the absolute path {target} containing exactly the text "
            f"HELLO-FROM-CLAUDE. Then reply with just DONE.",
            model="haiku",
            tools="default",
            permission_mode="acceptEdits",
            cwd=workdir,
            max_budget_usd=0.15,  # agent 模式一定要設上限
        )
        print(f"  回應 -> {r.text.strip()}（{r.num_turns} 個 turn，${r.cost_usd:.5f}）")
        if target.exists():
            print(f"  檔案內容 -> {target.read_text(encoding='utf-8').strip()!r}")
        else:
            print("  檔案沒有被建立（可能是權限模式或路徑問題）")
    print()


if __name__ == "__main__":
    try:
        demo_1_純文字整理()
        demo_2_結構化JSON()
        demo_3_批次處理()
        demo_4_session延續()
        if "--agent" in sys.argv:
            demo_5_agent模式寫檔()
        else:
            print("（想看 agent 真的動手寫檔，加上 --agent 再跑一次；那個示範比較貴）")
    except ClaudeError as e:
        print(f"呼叫失敗：{e}", file=sys.stderr)
        raise SystemExit(1)
