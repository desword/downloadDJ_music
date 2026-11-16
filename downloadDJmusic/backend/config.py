"""配置管理模块：管理默认下载路径等配置，持久化到 config.json"""
import json
import os
from typing import Any, Dict

# 配置文件路径（项目根目录下的 config.json）
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json",
)

# 默认配置
DEFAULT_CONFIG: Dict[str, Any] = {
    "default_download_path": r"D:\Music\SoundCloud",
    "default_format": "wav",
    "sleep_interval": 2,
}


def load_config() -> Dict[str, Any]:
    """读取 config.json，不存在则创建默认配置并返回。"""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        # 合并默认值，确保新增字段有默认值
        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        return merged
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """保存配置到 config.json。"""
    # 只保留已知的键，避免写入未知字段
    clean = {k: config.get(k, DEFAULT_CONFIG.get(k)) for k in DEFAULT_CONFIG.keys()}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
