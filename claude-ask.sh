#!/usr/bin/env bash
# ===================================================================
#  claude-ask.sh — Claude 訂閱 CLI 啟動器（macOS / Linux）
#  安裝：chmod +x claude-ask.sh，並把本資料夾加入 PATH（或建立 symlink）
#  用法：
#      claude-ask.sh "把這段整理成重點：..."
#      claude-ask.sh --attach data.txt "整理成 JSON" --format json
#      claude-ask.sh --tools default --permission-mode acceptEdits --cwd . "..."
#      claude-ask.sh --check
# ===================================================================
set -euo pipefail
export PYTHONUTF8=1
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 挑一個「真的能跑」的直譯器。在 Git Bash for Windows 上 python3 往往是
# Microsoft Store 的空殼 stub（執行後直接回 exit 49），所以要實測而不是只看存在。
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "claude-ask: 找不到可用的 Python（試過 python3 / python）。請先安裝 Python 3.9+。" >&2
    exit 4
fi

exec "$PY" "$DIR/claude_subscription.py" "$@"
