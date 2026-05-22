#!/bin/bash
cd "$(dirname "$0")/.."
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  source ~/mlx-audio-env/bin/activate
fi
python code/generate.py