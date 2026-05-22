# TTS 语音克隆系统

基于 **Qwen3-TTS**（Apple MLX）的语音克隆管线，支持人物性格注入和 Web UI 交互。

## 目录结构

```
textToSpeech/
├── config.json           # 全局配置（模型、音色、语速等）
├── code/                 # 核心脚本
│   ├── generate.py       # 主管线：LLM 润色 → TTS → ffmpeg 降速
│   ├── generate.sh       # CLI 启动脚本
│   ├── rewrite.py        # 人物性格注入（LLM 文本润色）
│   └── run_webui.sh      # Web UI 启动脚本
├── input/                # 输入文件
│   ├── text.txt          # 要转语音的文本
│   ├── ref_audio.wav     # 默认参考音频（config.json 指定）
│   ├── ref_text.txt      # 默认参考文本
│   ├── {name}.wav        # 用户上传的参考音频
│   ├── {name}.txt        # 对应的参考文本
│   └── test/             # 测试文件
├── output/               # 生成音频（.wav）
└── webui/                # Web UI
    ├── app.py            # FastAPI 后端
    └── templates/
        └── index.html    # 前端页面
```

## 首次初始化（分享给他人时）

需要 macOS Apple Silicon 和网络（首次运行需下载 ~4.9 GB 模型）。

```bash
# 一键初始化（安装 uv、ffmpeg、虚拟环境、依赖）
bash code/setup.sh

# 准备参考音频
# 把一段 3-10 秒的 WAV 录音放到 input/ref_audio.wav
# 并在 input/ref_text.txt 中写入录音的原文
```

初始化后，`setup.sh` 会在项目根目录创建 `.venv/` 虚拟环境。所有脚本会自动优先使用 `.venv/`，不存在时回退到 `~/mlx-audio-env/`。

模型首次运行时会自动从 HuggingFace 下载到 `~/.cache/huggingface/`。

## 快速开始

### CLI 模式

```bash
bash textToSpeech/code/generate.sh
```

### Web UI 模式

```bash
bash textToSpeech/code/run_webui.sh
```

浏览器打开 `http://localhost:8000`。

## 工作流程

```
输入文本
  │
  ▼ [可选] LLM 人格注入 ──── Qwen3-1.7B-MLX-8bit
  │                         （按段落拆 3 批润色，不足 3 段不拆分）
  ▼ TTS 声音克隆 ────────── Qwen3-TTS-12Hz-1.7B-Base-8bit
  │                         （参考音频 + 参考文本）
  ▼ ffmpeg 降速 ────────── atempo (speed 参数，如 0.85x)
  │
  ▶ 输出 output/*.wav
```

## 配置文件（config.json）

| 字段 | 说明 |
|------|------|
| `model` | TTS 模型名称 |
| `voice.speed` | 语速（1.0=正常，0.85=慢速，ffmpeg 后处理实现） |
| `voice.language` | 语言（如 English） |
| `personality.enabled` | 是否启用 LLM 人格注入 |
| `personality.model` | 人格注入 LLM 模型 |
| `personality.voice_description` | 音色描述 |
| `personality.character` | 人设描述 |

## Web UI 功能

| 功能 | 说明 |
|------|------|
| 声音选择 | 下拉列表选择已有声音，默认来自 config.json |
| 添加声音 | 上传新参考音频 + 名称 + 参考文本，自动转 24kHz WAV |
| 粘贴文本 | Tab 切换到"粘贴文本"输入 |
| 上传文件 | Tab 切换到"上传 .txt 文件" |
| 进度条 | SSE 实时推送生成进度 |
| 下载音频 | 生成后显示下载链接 |

## Web UI 状态

| 端 点 | 功能 |
|-------|------|
| `GET /` | 首页 |
| `GET /voices` | 列出所有可用声音 |
| `POST /voices` | 添加新声音（name + audio + ref_text）|
| `DELETE /voices/{name}` | 删除声音（移到 `~/.Trash/`）|
| `POST /generate` | 提交生成任务（text/file + voice）|
| `GET /progress/{task_id}` | SSE 进度推送 |
| `GET /download/{filename}` | 下载生成的 WAV |

## 概念澄清：Python 包 vs 模型权重

刚接触时常会搞混，简单说明：

| 角色 | 举例 | 大小 | 安装方式 |
|------|------|:----:|----------|
| **播放器** | `mlx-audio`、`mlx-lm` 等 Python 库 | 几 MB | `pip install` |
| **歌曲文件** | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit` 模型权重 | ~4.9 GB | 首次运行时自动从 HuggingFace 下载 |

- `setup.sh` 安装的是"播放器"（几 MB，很快）
- 第一次运行 `generate.sh` 时，代码会调用 `mlx-audio` 自动下载"歌曲文件"到 `~/.cache/huggingface/`（几 GB，根据网速需要几分钟）

**所以首次运行特别慢是正常的**，之后再跑就快了。

## 环境要求

- macOS Apple Silicon（arm64）
- [uv](https://docs.astral.sh/uv/) 包管理器
- [ffmpeg](https://ffmpeg.org/)（Homebrew 安装）
- Python 3.12（虚拟环境由 `setup.sh` 自动创建在 `.venv/`）

> `setup.sh` 会自动安装 uv 和 ffmpeg，无需手动准备。

## 依赖模型（HuggingFace 缓存）

| 模型 | 大小 | 用途 |
|------|:----:|:----:|
| `Qwen3-TTS-12Hz-1.7B-Base-8bit` | 3.1 GB | 主要 TTS 模型 |
| `Qwen3-1.7B-MLX-8bit` | 1.8 GB | LLM 人格注入 |
| `whisper-small-mlx` | 481 MB | 语音转文字（备用） |

## 注意事项

- Qwen3-TTS Base 模型不支持 `speed` 参数，降速由 ffmpeg `atempo` 后处理实现
- Web UI 不支持自动删除按钮（`DELETE /voices/` API 已就绪，前端未接入）
- 上传的音频自动转换为 24kHz mono WAV 格式存储
- 参考文本是声音克隆的关键输入，上传新声音时必须提供
