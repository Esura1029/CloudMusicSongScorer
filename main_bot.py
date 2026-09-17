"""音乐APP自动评分助手 - 主入口

用法:
    python main_bot.py          # 直接运行，使用默认配置
    或通过 gui_main.py 启动 GUI 版本
"""

from core.bot_engine import BotEngine, run_task
from core.bot_engine import BotEngine as _BotEngine

# 默认配置
DEFAULT_CONFIG = {
    "adb_path": r"E:\MuMu Player 12\shell\adb.exe",
    "device_id": "127.0.0.1:16448",
    "min_star": 2,
    "max_star": 4,
    "wait_music_seconds": 18,
}

_stop_event = None
_current_engine = None


def set_config(config: dict) -> None:
    """设置运行时配置（供GUI调用）"""
    global _custom_config
    _custom_config = config


_custom_config = {}


def stop_task() -> None:
    """停止当前评分任务"""
    global _current_engine
    if _current_engine:
        _current_engine.stop()


def check_stop() -> bool:
    """检查是否已停止"""
    global _current_engine
    if _current_engine:
        return _current_engine.is_stopped()
    return False


def run_main_task(progress_callback=None):
    """运行评分任务的主函数"""
    global _current_engine

    BotEngine.cleanup_screenshots()

    _current_engine = BotEngine(_custom_config)
    _current_engine.run(progress_callback)
    _current_engine = None


if __name__ == "__main__":
    run_main_task()
