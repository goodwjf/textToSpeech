import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import mlx.core as mx

def get_project_root():
    return Path(__file__).resolve().parent.parent

def load_config():
    config_path = get_project_root() / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def resolve_path(relative_path):
    return get_project_root() / relative_path

def validate_file(filepath, label):
    if not filepath.exists():
        print(f"错误: 找不到{label}文件 → {filepath}")
        sys.exit(1)
    return filepath

def read_text(filepath):
    return filepath.read_text(encoding="utf-8").strip()

def ensure_wav(filepath):
    import miniaudio
    try:
        miniaudio.get_file_info(str(filepath))
        return filepath
    except Exception:
        pass
    dst = filepath.with_suffix(".wav").parent / f"{filepath.stem}_temp.wav"
    print(f"音频格式转换中: {dst.name}")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(filepath), "-ac", "1", "-ar", "24000", str(dst)],
        capture_output=True, check=True,
    )
    return dst

def main():
    config = load_config()
    model_name = config["model"]

    text_file = validate_file(resolve_path(config["input"]["text_file"]), "文本")
    ref_audio_path = validate_file(resolve_path(config["input"]["ref_audio"]), "参考音频")
    ref_text_file = resolve_path(config["input"]["ref_text"])
    output_dir = validate_file(resolve_path(config["output"]["dir"]), "输出目录")
    speed = config["voice"]["speed"]
    language = config["voice"]["language"]
    output_filename = config["output"]["filename"]

    text = read_text(text_file)
    if not text:
        print("错误: 文本文件为空")
        sys.exit(1)

    personality_config = config.get("personality", {})
    if personality_config.get("enabled"):
        from rewrite import rewrite_text

        print("正在注入人物设定...")
        text = rewrite_text(text, personality_config)
        if not text:
            print("错误: 润色后文本为空")
            sys.exit(1)

    if ref_text_file.exists():
        ref_text = read_text(ref_text_file)
    else:
        ref_text = None

    ref_audio = ensure_wav(ref_audio_path)

    name, ext = os.path.splitext(output_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{name}_{timestamp}{ext}"

    print(f"正在加载模型: {model_name}")
    sys.stdout.flush()

    from mlx_audio.tts.utils import load_model
    model = load_model(model_name)

    print(f"正在生成语音 (语速: {speed}x, 语言: {language})")
    if ref_text:
        print("使用声音克隆 (参考音频 + 原文)")
    else:
        print("使用声音克隆 (参考音频, 无原文)")
    sys.stdout.flush()

    results = list(model.generate(
        text=text,
        ref_audio=str(ref_audio),
        ref_text=ref_text,
        speed=speed,
        lang_code=language,
    ))

    audio = results[0].audio
    sample_rate = getattr(model, "sample_rate", 24000)

    from mlx_audio.audio_io import write as audio_write
    audio_write(str(output_path), mx.array(audio), sample_rate)

    # Qwen3-TTS Base 模型的 speed 参数不生效，用 ffmpeg 后处理降速
    if speed != 1.0:
        temp_path = output_path.with_suffix(".tmp.wav")
        output_path.rename(temp_path)
        print(f"正在用 ffmpeg 调整语速至 {speed}x...")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(temp_path), "-filter:a", f"atempo={speed}", str(output_path)],
            capture_output=True, check=True,
        )
        temp_path.unlink()
        print(f"语速调整完成: {speed}x")

    if ref_audio != ref_audio_path:
        ref_audio.unlink()

    print(f"完成: {output_path}")

if __name__ == "__main__":
    main()
