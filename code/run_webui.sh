#!/bin/bash
cd "$(dirname "$0")/.."
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  source ~/mlx-audio-env/bin/activate
fi
uvicorn webui.app:app --reload --host 0.0.0.0 --port 8000
