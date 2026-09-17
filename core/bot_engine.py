"""音乐APP自动评分机器人核心引擎

该模块封装了评分子机器人的核心逻辑，负责：
1. 协调各子模块的工作
2. 管理评分流程的状态机
3. 处理用户交互和进度反馈

【整体架构】
┌─────────────────────────────────────────────────────────────┐
│                      BotEngine                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    主循环                            │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────┐  │   │
│  │  │ PageRec │→ │ScoreEnt │→ │ SongScr │→ │循环   │  │   │
│  │  │ 页面识别 │  │入口管理 │  │ 评分执行 │  │继续   │  │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └───────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import glob
import time
import threading
from typing import Callable, Optional, Dict, Any

from core import (
    ADBTools,
    OCREngine,
    PageRecognizer,
    PageType,
    ScoreEntrance,
    SongScorer,
)
from utils import load_config


class BotEngine:
    """评分机器人引擎

    协调所有子模块，按照状态机逻辑执行自动评分任务。
    """

    def __init__(self, custom_config: Optional[Dict[str, Any]] = None):
        """初始化机器人引擎

        Args:
            custom_config: 自定义配置，会覆盖默认配置
        """
        self._stop_event = threading.Event()
        self._custom_config = custom_config or {}
        self._songs_completed = 0

        # 加载配置
        self._config = load_config()
        self._config.update(self._custom_config)

        # 各子模块（延迟初始化）
        self._adb: Optional[ADBTools] = None
        self._ocr: Optional[OCREngine] = None
        self._page_recognizer: Optional[PageRecognizer] = None
        self._score_entrance: Optional[ScoreEntrance] = None
        self._scorer: Optional[SongScorer] = None

        # 评分流程状态
        self._in_rating_flow = False

    def _init_modules(self) -> None:
        """初始化所有子模块"""
        self._adb = ADBTools(self._config["adb_path"], self._config["device_id"])
        self._ocr = OCREngine()
        self._adb.connect()

        self._page_recognizer = PageRecognizer(self._ocr, self._adb)
        self._score_entrance = ScoreEntrance(self._ocr, self._adb)
        self._scorer = SongScorer(
            self._ocr,
            self._adb,
            self._config.get("min_star", 2),
            self._config.get("max_star", 4),
        )

    def stop(self) -> None:
        """停止评分任务"""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """检查是否已停止"""
        return self._stop_event.is_set()

    @staticmethod
    def cleanup_screenshots() -> None:
        """清理截图缓存文件"""
        folder = "screenshots"
        if not os.path.exists(folder):
            return

        images = glob.glob(os.path.join(folder, "*.png"))
        if not images:
            return

        print(f"[INFO] 正在清理缓存，共发现 {len(images)} 张图片...")
        for img in images:
            try:
                os.remove(img)
            except Exception as e:
                print(f"[WARNING] 无法删除 {img}: {e}")
        print("[INFO] 截图清理完成。")

    def run(self, progress_callback: Optional[Callable] = None) -> None:
        """运行评分任务

        【主循环流程】
        1. 识别当前页面类型
        2. 根据页面类型执行相应操作
        3. 重复直到用户停止或任务完成

        Args:
            progress_callback: 进度回调函数，签名: (已完成数, 总数, 消息)
        """
        self._stop_event.clear()
        self._songs_completed = 0

        # 初始化模块
        self._init_modules()

        # 识别初始页面
        print("[INFO] 正在识别当前页面...")
        current_page = self._page_recognizer.recognize_current_page()
        print(f"[INFO] 当前页面: {current_page['type'].value}")

        # 主循环
        while True:
            if self.is_stopped():
                print("[INFO] 用户停止了任务")
                return

            # 截取并识别当前页面
            screenshot = self._page_recognizer.capture_screenshot("loop_check.png")
            page_info = self._page_recognizer.recognize_current_page(screenshot)

            page_type = page_info["type"]
            print(f"[INFO] 识别页面: {page_type.value}")

            # 根据页面类型执行相应操作
            if page_type == PageType.ENTRY_PAGE:
                self._handle_entry_page(page_info)

            elif page_type == PageType.RATING_POPUP:
                self._handle_rating_popup(page_info, progress_callback)

            elif page_type == PageType.RATING_DIMENSION:
                self._handle_rating_dimension(page_info, progress_callback)

            elif page_type == PageType.MUSIC_PLAYING:
                self._handle_music_playing(progress_callback)

            elif page_type == PageType.UNKNOWN:
                print("[INFO] 未知页面，尝试向上滑动...")
                self._score_entrance.swipe_up(1)
                time.sleep(1)

    def _handle_entry_page(self, page_info: Dict[str, Any]) -> None:
        """处理入口页面"""
        print("[INFO] 检测到评分入口页面，点击进入...")
        entry_info = page_info["info"]
        self._score_entrance.enter_rating(
            entry_info["entry_pos"], entry_info["entry_type"]
        )
        time.sleep(2)
        self._in_rating_flow = True

    def _handle_rating_popup(
        self, page_info: Dict[str, Any], progress_callback: Optional[Callable]
    ) -> None:
        """处理评分弹窗"""
        print("[INFO] 检测到评分弹窗，执行评分...")
        rating_result = self._scorer.full_rating_cycle(page_info, progress_callback)
        if rating_result["submitted"]:
            print("[INFO] 评分完成，等待下一首")
            self._songs_completed += 1
            if progress_callback:
                progress_callback(
                    self._songs_completed, 0, f"已完成 {self._songs_completed} 首"
                )
            self._in_rating_flow = False
            time.sleep(2)
        else:
            print("[WARNING] 评分未提交，退出")
            self._stop_event.set()

    def _handle_rating_dimension(
        self, page_info: Dict[str, Any], progress_callback: Optional[Callable]
    ) -> None:
        """处理维度评分页面"""
        print("[INFO] 检测到评分维度页面...")
        rating_result = self._scorer.full_rating_cycle(page_info, progress_callback)
        if rating_result["submitted"]:
            print("[INFO] 评分完成，等待下一首")
            self._songs_completed += 1
            if progress_callback:
                progress_callback(
                    self._songs_completed, 0, f"已完成 {self._songs_completed} 首"
                )
            self._in_rating_flow = False
            time.sleep(2)

    def _handle_music_playing(self, progress_callback: Optional[Callable]) -> None:
        """处理听歌中状态"""
        if not self._in_rating_flow:
            print("[INFO] 正在听歌，等待评分弹窗...")
            if progress_callback:
                progress_callback(self._songs_completed, 0, "听歌中...")
        time.sleep(5)


def run_task(
    progress_callback: Optional[Callable] = None,
    custom_config: Optional[Dict[str, Any]] = None,
) -> None:
    """运行评分任务的便捷函数

    Args:
        progress_callback: 进度回调函数
        custom_config: 自定义配置
    """
    engine = BotEngine(custom_config)
    engine.run(progress_callback)


def stop_task() -> None:
    """停止当前运行的评分任务（需要通过全局方式调用）"""
    global _engine
    if "_engine" in globals() and _engine:
        _engine.stop()


# 全局引擎实例（用于stop_task函数）
_engine: Optional[BotEngine] = None


def _set_global_engine(engine: BotEngine) -> None:
    global _engine
    _engine = engine
