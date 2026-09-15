# -*- coding: utf-8 -*-
"""DocAssistant 后端包。

同时支持两种启动方式（模块内部用平级绝对导入，如 `from config import ...`）：
- python api/server.py    ：脚本模式，sys.path[0]=api/，平级导入天然可用
- uvicorn api.server:app  ：包模式，这里把 api/ 注入 sys.path，平级导入同样可解析
"""
import os
import sys

_API_DIR = os.path.dirname(os.path.abspath(__file__))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)
