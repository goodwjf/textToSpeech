#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "=============================="
echo " TTS 语音克隆系统 - 一键初始化"
echo "=============================="

# ── 1. 检查 uv ──
if ! command -v uv &>/dev/null; then
  echo "[1/4] 正在安装 uv（包管理器）..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # 尝试重新加载 PATH
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "uv 安装完成，请重启终端后重新运行此脚本。"
    exit 1
  fi
else
  echo "[1/4] ✓ uv 已就绪"
fi

# ── 2. 检查 ffmpeg ──
if ! command -v ffmpeg &>/dev/null; then
  echo "[2/4] 正在安装 ffmpeg（Homebrew）..."
  if ! command -v brew &>/dev/null; then
    echo "请先安装 Homebrew: https://brew.sh"
    exit 1
  fi
  brew install ffmpeg
else
  echo "[2/4] ✓ ffmpeg 已就绪"
fi

# ── 3. 创建虚拟环境 ──
echo "[3/4] 创建 Python 虚拟环境 (.venv)..."
uv venv "$VENV_DIR" --python 3.12

# ── 4. 安装 Python 依赖 ──
echo "[4/4] 安装 Python 依赖..."
source "$VENV_DIR/bin/activate"

uv pip install mlx-audio==0.4.3
uv pip install mlx-whisper==0.4.3
uv pip install mlx-lm
uv pip install fastapi uvicorn miniaudio

# ── 5. 创建示例输入文件（如不存在）──
if [ ! -f "$PROJECT_ROOT/input/ref_audio.wav" ]; then
  echo ""
  echo "⚠  未检测到参考音频 (input/ref_audio.wav)"
  echo "   请准备一段 3-10 秒的清晰人声录音（WAV 格式），"
  echo "   放到 input/ 目录下，命名为 ref_audio.wav"
  echo "   并创建 ref_text.txt 记录录音的原文。"
fi

if [ ! -f "$PROJECT_ROOT/input/text.txt" ]; then
  echo "test" > "$PROJECT_ROOT/input/text.txt"
  echo "已创建示例 input/text.txt（测试用）"
fi

echo ""
echo "⚠  首次运行需要下载 AI 模型（共 ~4.9 GB）"
echo "   会自动从 HuggingFace 下载到 ~/.cache/huggingface/"
echo "   所以首次运行会比较慢，耐心等待即可。"
echo ""
echo "   需要下载的模型："
echo "   · Qwen3-TTS-12Hz-1.7B-Base-8bit  (3.1 GB)  ← 主要 TTS"
echo "   · Qwen3-1.7B-MLX-8bit             (1.8 GB)  ← 人格注入 LLM"
echo "   · whisper-small-mlx               (481 MB)  ← 语音识别（备用）"
echo ""
echo "=============================="
echo " 初始化完成！"
echo "=============================="
echo ""
echo "使用方式："
echo ""
echo "  CLI 模式："
echo "    bash code/generate.sh"
echo ""
echo "  Web UI 模式："
echo "    bash code/run_webui.sh"
echo "    然后浏览器打开 http://localhost:8000"
echo ""
