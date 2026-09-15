# -*- coding: utf-8 -*-
"""环境变量与 GLM 配置：.env 加载、Key 状态检查、glm_config。"""
import logging
import os
from typing import Optional

DEMO_ROOT = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger("docassistant")


# ============================== 环境变量加载 ==============================

def _load_env():
    for p in [os.path.join(DEMO_ROOT, ".env"),
              r"D:\AI_Project\AIPM\demo\.env"]:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


# ============================== 配置 ==============================

def _key_status(api_key: Optional[str]) -> str:
    """Key 配置状态：missing / invalid_format / ok（供 health 与诊断脚本共用）"""
    if not api_key:
        return "missing"
    # 智谱 API Key 固定格式为 "32位hex.16位字符"（含一个点号，约 49 字符）。
    # 不含点号 = 只复制了点号前半段，永远无法通过认证。
    if "." not in api_key:
        return "invalid_format"
    return "ok"


def glm_config():
    api_key = (os.environ.get("ZHIPU_API_KEY") or "").strip()
    status = _key_status(api_key)
    if status == "missing":
        return None
    if status == "invalid_format":
        # 格式残缺的 Key 在配置层直接按未配置处理（Mock 模式 + 警告日志），
        # 它不是"调用失败"而是"必然失败的配置错误"，与运行期 502 不静默降级是两条边界。
        logger.warning(
            "[config] ZHIPU_API_KEY 格式异常（长度=%d · 不含点号）——疑似只复制了 Key 前半段，"
            "按未配置处理进入 Mock 模式。请到 https://open.bigmodel.cn/ 重新复制完整 Key。",
            len(api_key),
        )
        return None
    return {
        "api_key": api_key,
        "base_url": (os.environ.get("LLM_BASE_URL") or "https://open.bigmodel.cn").rstrip("/"),
        # 默认用免费档 VLM（glm-4v-flash），充值后可在 .env 设 ZHIPU_VLM_MODEL=glm-4.6v-flashx
        "model": os.environ.get("ZHIPU_VLM_MODEL") or "glm-4v-flash",
    }


def is_mock_mode():
    return glm_config() is None
