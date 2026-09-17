import time
from typing import Dict, Optional, Any, Tuple

from .ocr_engine import OCREngine
from .adb_tools import ADBTools


class ScoreEntrance:
    """评分入口管理器

    职责：检测并进入音乐APP的评分入口。

    【入口类型说明】
    音乐APP的评分入口可能有以下几种形式：
    1. "评定今日歌曲" - 每日首次评分的入口
    2. "继续评定" - 中断了评分后继续的入口
    3. "每日听歌" - 日常听歌评分的入口

    【工作流程】
    1. 在当前页面查找评分入口按钮
    2. 如果未找到，向上滑动页面继续查找
    3. 找到后点击进入评分流程

    【坐标系统说明】
    - 音乐APP界面为 1080x1920 标准分辨率
    - 坐标原点为屏幕左上角
    - OCR识别返回的是文字区域的中心点坐标
    """

    # 评分入口按钮的可能文字（按优先级排列）
    ENTRY_TARGETS = ["评定今日歌曲", "继续评定", "每日听歌"]

    def __init__(self, ocr: OCREngine, adb: ADBTools):
        """初始化评分入口管理器

        Args:
            ocr: OCR引擎实例，用于识别界面文字
            adb: ADB工具实例，用于执行点击和滑动操作
        """
        self.ocr = ocr
        self.adb = adb

    def find_entry_button(self, screenshot: str) -> Dict[str, Any]:
        """在截图中查找评分入口按钮的位置

        【查找逻辑】
        遍历预定义的入口按钮文字列表，找到第一个匹配的按钮位置。
        一旦找到就立即返回，不再继续查找。

        Args:
            screenshot: 截图文件的路径

        Returns:
            包含以下键的字典：
            - found: bool，是否找到
            - pos: tuple (x, y)，按钮中心坐标（仅在found=True时）
            - type: str，按钮文字类型（仅在found=True时）
        """
        for target in self.ENTRY_TARGETS:
            pos = self.ocr.find_text(screenshot, target)
            if pos:
                return {"found": True, "pos": pos, "type": target}
        return {"found": False}

    def enter_rating(self, entry_pos: Tuple[int, int], entry_type: str) -> bool:
        """点击进入评分流程

        【点击原理】
        根据OCR返回的文字位置坐标进行点击。由于返回的是文字中心点，
        而入口按钮通常较大，直接点击文字中心即可触发按钮。

        Args:
            entry_pos: 入口按钮的坐标 (x, y)
            entry_type: 入口按钮的文字类型

        Returns:
            是否点击成功
        """
        self.adb.tap(entry_pos[0], entry_pos[1])
        time.sleep(1)  # 等待页面切换
        return True

    def swipe_up(self, times: int = 1) -> None:
        """向上滑动屏幕

        【滑动原理】
        当入口按钮不在当前屏幕可见区域时，需要滑动屏幕来寻找入口。
        从屏幕下方（y=1000）滑动到上方（y=400），每次滑动约半个屏幕高度。

        【参数说明】
        - 起始点 (360, 1000)：屏幕中下方位置
        - 结束点 (360, 400)：屏幕中上方位置
        - 持续时间 500ms：模拟自然的滑动速度

        Args:
            times: 滑动的次数
        """
        for _ in range(times):
            self.adb.swipe(360, 1000, 360, 400, 500)
            time.sleep(0.3)

    def find_and_click_entry(
        self, screenshot: Optional[str] = None, max_swipe: int = 3
    ) -> Dict[str, Any]:
        """查找并点击评分入口（带滑动搜索）

        【完整工作流程】
        1. 获取当前屏幕截图
        2. 在截图中查找入口按钮
        3. 如果找到，点击进入并返回成功
        4. 如果未找到，向上滑动后重复步骤2
        5. 最多滑动 max_swipe 次后仍找不到则返回失败

        【典型场景】
        - 入口在屏幕可见范围内：立即找到并点击
        - 入口在屏幕下方：滑动1-2次后可见
        - 入口被遮挡或不存在：滑动max_swipe次后放弃

        Args:
            screenshot: 初始截图路径，如果为None则自动截取
            max_swipe: 最大滑动次数

        Returns:
            包含以下键的字典：
            - success: bool，操作是否成功
            - type: str，成功时为匹配的入口文字
            - attempts: int，尝试的次数
            - reason: str，失败时的原因（仅在success=False时）
        """
        if screenshot is None:
            screenshot = self.adb.take_screenshot("entry_scan.png")

        # 尝试在当前屏幕和滑动后的屏幕中查找入口
        for attempt in range(max_swipe + 1):
            result = self.find_entry_button(screenshot)
            if result["found"]:
                self.enter_rating(result["pos"], result["type"])
                return {"success": True, "type": result["type"], "attempts": attempt}

            # 未找到入口，向上滑动继续搜索
            if attempt < max_swipe:
                self.swipe_up(2)  # 每次滑动两下，覆盖更大范围
                time.sleep(1)
                screenshot = self.adb.take_screenshot("entry_scan.png")

        return {"success": False, "reason": "未找到评分入口"}

    def wait_for_rating_popup(
        self, timeout: int = 60, check_interval: int = 2
    ) -> Dict[str, Any]:
        """等待评分弹窗出现

        【使用场景】
        点击入口按钮后，需要等待评分弹窗出现。
        在某些网络或设备条件下，弹窗可能出现较慢。

        【等待逻辑】
        1. 持续检查屏幕是否出现"请评定"文字
        2. 每次检查间隔 check_interval 秒
        3. 超过 timeout 秒则放弃等待

        Args:
            timeout: 最大等待时间（秒）
            check_interval: 每次检查的间隔（秒）

        Returns:
            包含以下键的字典：
            - found: bool，是否等到弹窗出现
            - stage: str，找到时的页面阶段（仅在found=True时）
            - reason: str，超时原因（仅在found=False时）
        """
        elapsed = 0

        while elapsed < timeout:
            screenshot = self.adb.take_screenshot("wait_popup.png")

            if self.ocr.find_text(screenshot, "请评定"):
                return {"found": True, "stage": "popup"}

            time.sleep(check_interval)
            elapsed += check_interval

        return {"found": False, "reason": "等待超时"}
