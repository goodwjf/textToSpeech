import os
import re
import sys


SYSTEM_PROMPT = """你是一个播客脚本润色助手。你的工作是让文本读起来更像一个亲切的播客主持人在说话。

严格规则：
1. 保留原文的每一句话和所有核心信息，不增删任何内容
2. 不改变原文的句子顺序和段落结构
3. 只在原文基础上做极轻度润色，输出必须仍可清晰识别为原文
4. 可以做的修改（每种最多用一次）：
   - 在某个句首加入 1 个语气词（well, you know, hey, right）
   - 在 1-2 个适当位置加省略号（...）表示自然停顿
   - 在 1 个适当位置加破折号（—）表示语气转折
5. 绝对禁止：
   - 不要添加原文没有的新句子或新观点
   - 不要删除或改写原文的任何句子
   - 不要改变原文的意思
   - 禁止使用 "Trust me, I know right" 这个短语
   - 不要重复使用同一个语气词
   - 不要加入舞台指示、动作描述或 Markdown 格式
   - 不要输出解释或说明
6. 直接输出润色后的文本，不要有任何其他内容

角色设定：
- 音色：{voice_description}
- 人设：{character}

请根据以上设定，对以下文本做极轻度润色。"""


def remove_duplicate_paragraphs(text):
    """移除重复的段落。"""
    paragraphs = text.split("\n\n")
    seen = set()
    unique = []
    for para in paragraphs:
        normalized = re.sub(r'\s+', ' ', para.strip().lower())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(para)
    return "\n\n".join(unique)


def inject_personality(text, voice_description, character, model_path, temperature=0.3):
    """用 LLM 对全文做轻度人格注入。

    策略：
    - 按空行分段后，分为 3 批（开头/正文/结尾）
    - 每批一次 LLM 调用，减少调用次数
    - 严格 prompt 控制改写幅度
    - 去重防止 LLM 输出重复内容
    """
    from mlx_lm import load, generate

    full_path = os.path.expanduser(model_path)
    print(f"正在加载人格注入模型: {model_path}")
    sys.stdout.flush()

    model, tokenizer = load(full_path)

    # 按空行分段
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        return text

    # 分为 3 批：开头 15%、正文 70%、结尾 15%
    # 不足 3 段时不拆分，避免段落重复
    n = len(paragraphs)

    if n < 3:
        batches = ["\n\n".join(paragraphs)]
        labels = ["全文"]
    else:
        intro_end = max(1, n // 6)
        outro_start = n - max(1, n // 6)
        batches = []
        labels = []

        if intro_end > 0:
            batches.append("\n\n".join(paragraphs[:intro_end]))
            labels.append("开头")

        if outro_start > intro_end:
            batches.append("\n\n".join(paragraphs[intro_end:outro_start]))
            labels.append("正文")

        if outro_start < n:
            batches.append("\n\n".join(paragraphs[outro_start:]))
            labels.append("结尾")

    enhanced_batches = []

    for i, batch in enumerate(batches):
        print(f"  润色{labels[i]}...")
        sys.stdout.flush()

        prompt = SYSTEM_PROMPT.format(
            voice_description=voice_description,
            character=character,
        ) + f"\n\n原文：\n{batch}\n\n润色后："

        messages = [
            {"role": "system", "content": "你是一个播客脚本润色助手。直接输出润色结果，不要解释。"},
            {"role": "user", "content": prompt},
        ]

        if tokenizer.chat_template:
            chat_prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        else:
            chat_prompt = prompt

        result = generate(
            model,
            tokenizer,
            prompt=chat_prompt,
            verbose=False,
            max_tokens=8192,
        )

        # 清理思考标签
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL).strip()

        # 提取润色后的文本
        if "润色后：" in result:
            result = result.split("润色后：")[-1].strip()
        elif "原文：" in result:
            parts = result.split("原文：")
            result = parts[-1].strip() if len(parts) > 1 else result.strip()

        # 去重
        result = remove_duplicate_paragraphs(result)

        enhanced_batches.append(result)

    # 重新组合
    result = "\n\n".join(enhanced_batches)

    print(f"人格注入完成: 原文 {len(text)} 字 → 润色后 {len(result)} 字")
    return result


def rewrite_text(text, config):
    """主入口：根据配置调用 LLM 人格注入。"""
    if not config.get("enabled"):
        return text

    voice_desc = config.get("voice_description", "")
    character = config.get("character", "")
    model_path = config.get("model", "")
    temperature = config.get("temperature", 0.3)

    if voice_desc and character and model_path:
        return inject_personality(text, voice_desc, character, model_path, temperature)
    else:
        return text
