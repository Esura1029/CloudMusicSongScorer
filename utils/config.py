import json
import os
from typing import Dict, Any


CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "adb_path": r"E:\MuMu Player 12\shell\adb.exe",
    "device_id": "127.0.0.1:16448",
    "screen_width": 720,
    "screen_height": 1280,
    "min_star": 2,
    "max_star": 4,
    "wait_music_seconds": 18,
}


def load_config() -> Dict[str, Any]:
    """读取配置文件

    优先从config.json读取配置，如果文件不存在或读取失败，
    则返回默认配置。

    Returns:
        配置字典，包含以下键：
        - adb_path: ADB可执行文件路径
        - device_id: 模拟器设备ID
        - min_star: 最低评分星级
        - max_star: 最高评分星级
        - wait_music_seconds: 听歌等待时间（秒）
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # 合并默认配置，确保所有键都存在
                return {**DEFAULT_CONFIG, **config}
        except Exception as e:
            print(f"读取配置失败，使用默认值: {e}")

    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """保存配置到JSON文件

    Args:
        config: 要保存的配置字典
    """
    # 只保存必要的配置项
    save_data = {
        "adb_path": config.get("adb_path", DEFAULT_CONFIG["adb_path"]),
        "device_id": config.get("device_id", DEFAULT_CONFIG["device_id"]),
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=4, ensure_ascii=False)

    print("配置已保存。")


def get_default_device() -> str:
    """获取默认的设备ID

    Returns:
        默认设备ID字符串
    """
    return DEFAULT_CONFIG["device_id"]
