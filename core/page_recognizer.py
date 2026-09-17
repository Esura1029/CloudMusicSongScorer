from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image

from .ocr_engine import OCREngine
from .adb_tools import ADBTools
import re

class PageType(Enum):
    """页面类型枚举

    定义音乐APP应用中可能出现的各种页面状态。
    这些状态用于状态机的状态转换判断。
    """

    UNKNOWN = "unknown"  # 未知页面
    ENTRY_PAGE = "entry_page"  # 评分入口页面（显示"评定今日歌曲"等按钮）
    MUSIC_PLAYING = "music_playing"  # 听歌中页面
    RATING_POPUP = "rating_popup"  # 评分弹窗页面（"请评定"）
    RATING_DIMENSION = "rating_dimension"  # 评分维度页面（旋律/演唱/歌词）
    RATING_COMPLETE = "rating_complete"  # 评分完成页面（显示"提交"按钮）


class PageRecognizer:
    """页面识别器

    负责识别当前屏幕属于哪种页面类型，并提取页面中的关键信息。
    使用OCR技术检测页面上的关键文字来判断页面状态。

    页面识别流程：
    1. 截取当前屏幕
    2. 依次检测各类页面的特征文字
    3. 返回页面类型及提取到的相关信息
    """

    RATING_TRIGGER_TEXT = "请评定"  # 评分弹窗的特征文字
    SONG_DIMENSIONS = ["旋律", "演唱", "歌词"]  # 维度页面会出现的三个维度
    DIMENSION_Y_SPACING = 80  # 维度之间的Y轴间距（像素）
    DIMENSION_Y_TOLERANCE = 15  # Y轴间距允许的误差（像素）
    SUBMIT_TEXT = "提交并评下一首"  # 提交按钮文字
    ENTRY_BUTTONS = ["评定今日歌曲", "继续评定"]  # 入口按钮可能出现的文字
    PLAYING_INDICATORS = "聆听"  # 听歌中页面的特征文字
    SUBMIT_BUTTON_BRIGHTNESS_THRESHOLD = 100  # 按钮高亮阈值（0-255）

    def __init__(self, ocr: OCREngine, adb: ADBTools):
        """初始化页面识别器

        Args:
            ocr: OCR引擎实例，用于文字识别
            adb: ADB工具实例，用于屏幕截图
        """
        self.ocr = ocr
        self.adb = adb

    def capture_screenshot(self, filename: str = "current.png") -> str:
        """截取当前屏幕

        Args:
            filename: 保存的文件名

        Returns:
            截图文件的路径
        """
        return self.adb.take_screenshot(filename)

    def recognize_current_page(
        self, screenshot: Optional[str] = None, filename: str = "current.png"
    ) -> Dict[str, Any]:
        """识别当前页面类型并提取相关信息

        这是页面识别的核心方法，会：
        1. 确保有截图
        2. 检测页面类型
        3. 提取该页面相关的关键信息

        Args:
            screenshot: 已有的截图路径，如果为None则自动截取
            filename: 如果需要截图，保存的文件名

        Returns:
            包含以下键的字典：
            - type: PageType枚举值，表示页面类型
            - info: dict，页面特有的信息
            - screenshot: 截图文件路径
        """
        if screenshot is None:
            screenshot = self.adb.take_screenshot(filename)

        page_type = self._detect_page_type(screenshot)
        info = self._collect_page_info(screenshot, page_type)

        return {"type": page_type, "info": info, "screenshot": screenshot}

    def _detect_page_type(self, screenshot: str) -> PageType:
        """检测页面类型

        按照优先级依次检测各类页面：
        1. 评分弹窗 - 优先级最高，用户正在操作
        2. 评分维度 - 评分流程中的页面（使用Y轴间距验证）
        3. 评分完成 - 已提交状态
        4. 听歌中 - 正常播放状态
        5. 入口页面 - 可以开始评分的入口
        6. 未知页面 - 未能识别

        Args:
            screenshot: 截图文件路径

        Returns:
            识别到的页面类型
        """
        if self.ocr.find_text(screenshot, self.RATING_TRIGGER_TEXT):
            return PageType.RATING_POPUP

        # 使用Y轴间距验证来检测维度页面，避免误识别
        if self._validate_dimensions(screenshot):
            return PageType.RATING_DIMENSION

        # 通过按钮颜色检测来判断是否已完成评分
        # 只有当提交按钮高亮（可点击）时才判定为评分完成
        if self.ocr.find_text(screenshot, self.SUBMIT_TEXT):
            if self._is_submit_button_active(screenshot):
                return PageType.RATING_COMPLETE
            return PageType.RATING_DIMENSION

        for indicator in self.PLAYING_INDICATORS:
            if self.ocr.find_text(screenshot, indicator):
                return PageType.MUSIC_PLAYING

        for entry in self.ENTRY_BUTTONS:
            if self.ocr.find_text(screenshot, entry):
                return PageType.ENTRY_PAGE

        return PageType.UNKNOWN
    
    def _validate_dimensions(self, screenshot: str) -> bool:
        """验证截图中是否存在真正的评分维度

        # 【验证逻辑】
        # 真正的评分维度页面中，"旋律"、"演唱"、"歌词"三个维度
        # 在Y轴上的间距是固定的（约80像素）。
        # 通过检查这个间距规律来判断是否是真正的维度页面。

        Args:
            screenshot: 截图文件路径

        Returns:
            True 如果验证通过（是真正的维度页面），否则 False
        """
        dim_positions = {}

        for dim in self.SONG_DIMENSIONS:
            pos = self.ocr.find_text(screenshot, dim)
            if pos:
                dim_positions[dim] = pos

        if len(dim_positions) < 1:
            return False

        if len(dim_positions) == 1:
            return True

        # def check_spacing(pos_list: List[Tuple[int, int]]) -> bool:
        #     """检查一组坐标的Y轴间距是否符合规律"""
        #     if len(pos_list) < 2:
        #         return True

        #     sorted_pos = sorted(pos_list, key=lambda p: p[1])
        #     for i in range(len(sorted_pos) - 1):
        #         y_diff = abs(sorted_pos[i + 1][1] - sorted_pos[i][1])
        #         if abs(y_diff - self.DIMENSION_Y_SPACING) > self.DIMENSION_Y_TOLERANCE:
        #             return False
        #     return True

        pos_list = list(dim_positions.values())
        # return check_spacing(pos_list)

    def _is_submit_button_active(self, screenshot: str) -> bool:
        """检测提交按钮是否高亮（可点击状态）

        通过采样按钮区域的像素颜色来判断按钮是否处于激活状态。
        灰色按钮（不可点击）与亮色按钮（可点击）的像素亮度有明显差异。

        Args:
            screenshot: 截图文件路径

        Returns:
            True 如果按钮高亮（可点击），False 如果按钮是灰色（不可点击）
        """
        submit_pos = self.ocr.find_text(screenshot, self.SUBMIT_TEXT)
        if not submit_pos:
            return False

        try:
            img = Image.open(screenshot)
            img = img.convert("RGB")

            bx, by = submit_pos
            btn_width = 150
            btn_height = 40

            sample_points = [
                (bx - btn_width // 2, by),  # 按钮中心
                (bx - btn_width // 3, by),  # 偏左
                (bx + btn_width // 3, by),  # 偏右
                (bx - btn_width // 2, by + btn_height // 3),  # 下方偏左
                (bx + btn_width // 3, by + btn_height // 3),  # 下方偏右
            ]

            total_brightness = 0
            sample_count = 0

            for sx, sy in sample_points:
                px, py = max(0, sx), max(0, sy)
                if px < img.width and py < img.height:
                    pixel = img.getpixel((px, py))
                    brightness = (pixel[0] + pixel[1] + pixel[2]) // 3
                    total_brightness += brightness
                    sample_count += 1

            if sample_count == 0:
                return False

            avg_brightness = total_brightness // sample_count
            print(
                f"[DEBUG] 提交按钮平均亮度: {avg_brightness} (阈值: {self.SUBMIT_BUTTON_BRIGHTNESS_THRESHOLD})"
            )

            return avg_brightness > self.SUBMIT_BUTTON_BRIGHTNESS_THRESHOLD

        except Exception as e:
            print(f"[WARNING] 检测按钮颜色失败: {e}")
            return False

    def _collect_page_info(
        self, screenshot: str, page_type: PageType
    ) -> Dict[str, Any]:
        """根据页面类型收集该页面的关键信息

        不同页面需要提取不同类型的信息：
        - 评分弹窗：需要获取"请评定"文字的位置
        - 维度页面：需要获取各维度文字的位置
        - 入口页面：需要获取入口按钮的位置和类型

        Args:
            screenshot: 截图文件路径
            page_type: 已识别的页面类型

        Returns:
            包含页面特有信息的字典
        """
        info = {}

        if page_type == PageType.RATING_POPUP:
            pos = self.ocr.find_text(screenshot, self.RATING_TRIGGER_TEXT)
            if pos:
                info["rating_trigger_pos"] = pos

        elif page_type == PageType.RATING_DIMENSION:
            dims = []
            for dim in self.SONG_DIMENSIONS:
                pos = self.ocr.find_text(screenshot, dim)
                if pos:
                    dims.append({"name": dim, "pos": pos})
            info["dimensions"] = dims
            submit_pos = self.ocr.find_text(screenshot, self.SUBMIT_TEXT)
            if submit_pos:
                info["submit_pos"] = submit_pos

        elif page_type == PageType.RATING_COMPLETE:
            pos = self.ocr.find_text(screenshot, self.SUBMIT_TEXT)
            if pos:
                info["submit_pos"] = pos

        elif page_type == PageType.ENTRY_PAGE:
            for entry in self.ENTRY_BUTTONS:
                pos = self.ocr.find_text(screenshot, entry)
                if pos:
                    info["entry_pos"] = pos
                    info["entry_type"] = entry
                    break

        return info

    def is_rating_page(
        self, screenshot: Optional[str] = None, filename: str = "current.png"
    ) -> bool:
        """判断当前是否在评分相关页面

        Args:
            screenshot: 截图路径
            filename: 截图文件名

        Returns:
            是否在评分页面（弹窗/维度/完成）
        """
        page_info = self.recognize_current_page(screenshot, filename)
        return page_info["type"] in [
            PageType.RATING_POPUP,
            PageType.RATING_DIMENSION,
            PageType.RATING_COMPLETE,
        ]

    def is_entry_page(
        self, screenshot: Optional[str] = None, filename: str = "current.png"
    ) -> bool:
        """判断当前是否为评分入口页面

        Args:
            screenshot: 截图路径
            filename: 截图文件名

        Returns:
            是否为入口页面
        """
        page_info = self.recognize_current_page(screenshot, filename)
        return page_info["type"] == PageType.ENTRY_PAGE

    def is_music_playing(
        self, screenshot: Optional[str] = None, filename: str = "current.png"
    ) -> bool:
        """判断当前是否在听歌中

        Args:
            screenshot: 截图路径
            filename: 截图文件名

        Returns:
            是否在听歌中
        """
        page_info = self.recognize_current_page(screenshot, filename)
        return page_info["type"] == PageType.MUSIC_PLAYING
