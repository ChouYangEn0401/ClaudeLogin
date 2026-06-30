#!/usr/bin/env bash
# ===================================================================
#  claude-ask.sh — Claude 訂閱 CLI 啟動器（macOS / Linux）
#  安裝：chmod +x claude-ask.sh，並把本資料夾加入 PATH（或建立 symlink）
#  用法：
#      claude-ask.sh "把這段整理成重點：..."
#      claude-ask.sh --attach data.txt "整理成 JSON" --format json
#      claude-ask.sh --check
# ===================================================================
export PYTHONUTF8=1
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/claude_subscription.py" "$@"
