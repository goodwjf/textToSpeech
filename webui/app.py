import asyncio
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.responses import StreamingResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"

app = FastAPI(title="TTS Web UI")
tasks: dict[str, dict] = {}

INDEX_HTML = (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


def _load_config() -> dict:
    config_path = PROJECT_ROOT / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_default_voice_info() -> tuple[str, str]:
    config = _load_config()
    ref_path = config["input"]["ref_audio"]
    name = Path(ref_path).stem
    label = f"默认 ({name})"
    return name, label


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


@app.get("/voices")
async def list_voices():
    config = _load_config()
    default_name, default_label = _get_default_voice_info()

    voices = []
    default_ref_audio = PROJECT_ROOT / config["input"]["ref_audio"]
    default_ref_text = PROJECT_ROOT / config["input"]["ref_text"]
    voices.append({
        "name": default_name,
        "label": default_label,
        "is_default": True,
        "has_ref_audio": default_ref_audio.exists(),
        "has_ref_text": default_ref_text.exists(),
    })

    for wav in sorted(INPUT_DIR.glob("*.wav")):
        name = wav.stem
        if name == default_name:
            continue
        txt = INPUT_DIR / f"{name}.txt"
        voices.append({
            "name": name,
            "label": name,
            "is_default": False,
            "has_ref_audio": True,
            "has_ref_text": txt.exists(),
        })

    return voices


@app.post("/voices")
async def add_voice(
    name: str = Form(...),
    audio: UploadFile = File(...),
    ref_text: str = Form(...),
):
    safe_name = name.strip()
    if not safe_name:
        raise HTTPException(400, "声音名称不能为空")
    if not re.match(r"^[\w\u4e00-\u9fff]+$", safe_name):
        raise HTTPException(400, "声音名称只能包含字母、数字、下划线和中文")
    if not ref_text.strip():
        raise HTTPException(400, "参考文本不能为空")

    wav_path = INPUT_DIR / f"{safe_name}.wav"
    txt_path = INPUT_DIR / f"{safe_name}.txt"

    if wav_path.exists():
        raise HTTPException(409, f"声音名称 '{safe_name}' 已存在，请换一个名称")

    default_name, _ = _get_default_voice_info()
    if safe_name == default_name:
        raise HTTPException(409, f"不能使用系统默认名称 '{safe_name}'")

    suffix = Path(audio.filename).suffix if audio.filename else ".tmp"
    temp_path = INPUT_DIR / f"__upload_temp{suffix}"
    try:
        with open(temp_path, "wb") as f:
            f.write(await audio.read())

        subprocess.run(
            ["ffmpeg", "-y", "-i", str(temp_path),
             "-ac", "1", "-ar", "24000", str(wav_path)],
            check=True, capture_output=True,
        )
    finally:
        if temp_path.exists():
            temp_path.unlink()

    txt_path.write_text(ref_text.strip(), encoding="utf-8")

    return {"success": True, "name": safe_name}


def _trash(path: Path) -> bool:
    """Move file to macOS Trash (instead of permanent delete).

    NOTE: 这个函数目前仅 DELETE /voices/{name} API 会调用，
    前端 UI 没有删除按钮，后续如果需要加上，记得先确认 _trash 的权限问题。
    """
    try:
        trash_dir = Path.home() / ".Trash"
        trash_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = trash_dir / f"{path.stem}_{ts}{path.suffix}"
        import shutil
        shutil.move(str(path), str(dest))
        return True
    except Exception:
        return False


@app.delete("/voices/{name}")
async def delete_voice(name: str):
    default_name, _ = _get_default_voice_info()
    if name == default_name:
        raise HTTPException(400, "不能删除默认声音")

    wav_path = INPUT_DIR / f"{name}.wav"
    txt_path = INPUT_DIR / f"{name}.txt"
    deleted = False

    for p in [wav_path, txt_path]:
        if p.exists():
            if not _trash(p):
                p.unlink()
            deleted = True

    if not deleted:
        raise HTTPException(404, f"声音 '{name}' 不存在")

    return {"success": True, "name": name}


@app.post("/generate")
async def generate(
    text: str = Form(None),
    file: UploadFile = None,
    voice: str = Form(None),
):
    if not text and not file:
        raise HTTPException(400, "请粘贴文本或上传文件")

    if file:
        content = await file.read()
        text = content.decode("utf-8")

    if not text or not text.strip():
        raise HTTPException(400, "文本内容不能为空")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"progress": 0, "status": "排队中...", "filename": None}

    asyncio.create_task(_run_pipeline(task_id, text.strip(), voice or None))

    return {"task_id": task_id}


@app.get("/progress/{task_id}")
async def progress(task_id: str):
    async def event_generator():
        while True:
            task = tasks.get(task_id)
            if not task:
                yield f"data: {json.dumps({'progress': -1, 'status': '任务不存在'})}\n\n"
                break
            yield f"data: {json.dumps(task)}\n\n"
            if task["progress"] >= 100 or task["progress"] < 0:
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/download/{filename}")
async def download(filename: str):
    filepath = OUTPUT_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "文件不存在或已过期")
    return FileResponse(filepath, media_type="audio/wav", filename=filename)


async def _run_pipeline(task_id: str, input_text: str, voice_name: str | None = None):
    def update(progress: int, status: str, filename: str | None = None):
        tasks[task_id] = {"progress": progress, "status": status, "filename": filename}

    try:
        update(5, "加载配置...")
        await asyncio.sleep(0)

        config = _load_config()
        default_name, _ = _get_default_voice_info()
        model_name = config["model"]
        speed = config["voice"]["speed"]
        language = config["voice"]["language"]
        output_dir = PROJECT_ROOT / config["output"]["dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        personality_config = config.get("personality", {})

        # ── Resolve ref audio/text ──
        use_default = not voice_name or voice_name == default_name

        if use_default:
            ref_audio_path = PROJECT_ROOT / config["input"]["ref_audio"]
            from code.generate import ensure_wav
            ref_audio = ensure_wav(ref_audio_path)
            ref_text_path = PROJECT_ROOT / config["input"]["ref_text"]
            ref_text = ref_text_path.read_text(encoding="utf-8").strip() if ref_text_path.exists() else None
        else:
            ref_audio_path = INPUT_DIR / f"{voice_name}.wav"
            if not ref_audio_path.exists():
                raise FileNotFoundError(f"声音 '{voice_name}' 的音频文件不存在")
            ref_audio = ref_audio_path
            ref_text_path = INPUT_DIR / f"{voice_name}.txt"
            if not ref_text_path.exists():
                raise FileNotFoundError(f"声音 '{voice_name}' 的参考文本不存在")
            ref_text = ref_text_path.read_text(encoding="utf-8").strip()

        text = input_text

        # ── Personality injection ──
        if personality_config.get("enabled"):
            update(20, "注入人物设定...")
            await asyncio.sleep(0)

            from code.rewrite import rewrite_text
            text = await asyncio.to_thread(rewrite_text, text, personality_config)

        # ── Load TTS model ──
        update(40, "加载 TTS 模型...")
        await asyncio.sleep(0)

        import mlx.core as mx
        from mlx_audio.tts.utils import load_model as load_tts_model

        model = await asyncio.to_thread(load_tts_model, model_name)

        # ── Generate audio ──
        update(60, "生成语音中...")
        await asyncio.sleep(0)

        results = await asyncio.to_thread(
            lambda: list(model.generate(
                text=text,
                ref_audio=str(ref_audio),
                ref_text=ref_text,
                speed=speed,
                lang_code=language,
            ))
        )
        audio = results[0].audio
        sample_rate = getattr(model, "sample_rate", 24000)

        # ── Save ──
        update(85, "保存音频...")
        await asyncio.sleep(0)

        from mlx_audio.audio_io import write as audio_write

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"webui_output_{timestamp}.wav"
        output_path = output_dir / output_filename

        await asyncio.to_thread(
            lambda: audio_write(str(output_path), mx.array(audio), sample_rate)
        )

        # ── ffmpeg speed ──
        if speed != 1.0:
            update(92, f"调整语速至 {speed}x...")
            await asyncio.sleep(0)

            temp_path = output_path.with_suffix(".tmp.wav")
            output_path.rename(temp_path)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(temp_path),
                 "-filter:a", f"atempo={speed}", str(output_path)],
                capture_output=True, check=True,
            )
            temp_path.unlink()

        # ── Cleanup temp wav ──
        if ref_audio != ref_audio_path:
            ref_audio.unlink()

        update(100, "生成完成!", output_filename)

    except Exception as e:
        update(-1, f"错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
