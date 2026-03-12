"""
ai/llm.py — Core AI calling logic (DeepSeek via OpenRouter).
"""

import sys
from pathlib import Path
from openai import OpenAI
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, DEEPSEEK_MODEL
)

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)

def _call_ai(system_prompt: str, user_content: str, max_tokens: int = 500,
             temperature: float = 0.3) -> str:
    """Helper: panggil DeepSeek via OpenRouter dengan temperature control."""
    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        usage = response.usage
        cost_in = (usage.prompt_tokens / 1_000_000) * 0.27
        cost_out = (usage.completion_tokens / 1_000_000) * 1.10
        logger.info(f"AI: {usage.total_tokens} tokens (${cost_in + cost_out:.6f}) temp={temperature}")

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"AI error: {e}")
        return f"Error: {e}"
