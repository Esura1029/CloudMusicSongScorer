import logging
from typing import Optional, Tuple, List, Callable
from paddleocr import PaddleOCR


logging.getLogger("ppocr").setLevel(logging.ERROR)


class OCREngine:
    """基于PaddleOCR的文字识别引擎

    封装PaddleOCR的使用，提供文字识别和定位功能。
    主要用于识别音乐APP界面中的关键文字和按钮位置。
    """

    def __init__(self):
        """初始化OCR引擎

        使用中文语言模型，启用方向分类以提高识别准确率。
        """
        print("[INFO] 视觉引擎初始化中...")
        self.reader = PaddleOCR(use_angle_cls=True, lang="ch")
        # 文字过滤器列表
        self._filters: List[Callable[[str], str]] = []
        # 是否启用过滤器
        self._filters_enabled: bool = True
        # 注册内置过滤器：去除"暂无歌词，沉浸享受"
        self.add_filter(self._filter_no_lyrics_placeholder)

    @staticmethod
    def _filter_no_lyrics_placeholder(text: str) -> str:
        """内置过滤器：去除音乐APP的无歌词占位提示文字

        将 '暂无歌词，沉浸享受' 替换为空串，避免干扰目标文字匹配，
        同时保留 '歌词' 等其他文字不受影响。
        """
        return text.replace("暂无歌词，沉浸享受", "")

    # ==================== 过滤器管理 ====================

    def add_filter(self, filter_func: Callable[[str], str]) -> None:
        """添加文字过滤器

        过滤器会在每次文字匹配前被调用，用于预处理识别到的文字。

        Args:
            filter_func: 过滤函数，接收识别到的文字字符串，返回处理后的字符串
                        例如: lambda text: text.replace(" ", "")

        Example:
            # 去除所有空格
            ocr.add_filter(lambda text: text.replace(" ", ""))
            # 去除换行符
            ocr.add_filter(lambda text: text.replace("\n", ""))
            # 统一英文字母大小写
            ocr.add_filter(lambda text: text.lower())
        """
        self._filters.append(filter_func)
        print(f"[INFO] 已添加文字过滤器: {filter_func.__name__ if hasattr(filter_func, '__name__') else 'anonymous'}")

    def remove_filter(self, filter_func: Callable[[str], str]) -> bool:
        """移除文字过滤器

        Args:
            filter_func: 要移除的过滤器函数

        Returns:
            True 如果成功移除，否则 False
        """
        if filter_func in self._filters:
            self._filters.remove(filter_func)
            print(f"[INFO] 已移除文字过滤器")
            return True
        return False

    def clear_filters(self) -> None:
        """清空所有过滤器"""
        self._filters.clear()
        print("[INFO] 已清空所有文字过滤器")

    def enable_filters(self, enabled: bool = True) -> None:
        """启用或禁用过滤器

        Args:
            enabled: True 启用过滤器，False 禁用过滤器
        """
        self._filters_enabled = enabled
        print(f"[INFO] 过滤器已{'启用' if enabled else '禁用'}")

    def get_filters(self) -> List[Callable[[str], str]]:
        """获取当前所有过滤器"""
        return self._filters.copy()

    # ==================== 核心OCR方法 ====================

    def _apply_filters(self, text: str) -> str:
        """应用所有过滤器到文字上

        Args:
            text: 原始识别文字

        Returns:
            过滤后的文字
        """
        if not self._filters_enabled or not self._filters:
            return text

        filtered_text = text
        for filter_func in self._filters:
            try:
                filtered_text = filter_func(filtered_text)
            except Exception as e:
                print(f"[WARNING] 文字过滤器执行失败: {e}")
                continue
        return filtered_text

    def find_text(
        self, img_path: str, target: str, min_confidence: float = 0.6
    ) -> Optional[Tuple[int, int]]:
        """在截图中查找指定文字的位置

        Args:
            img_path: 截图文件的路径
            target: 要查找的目标文字（支持模糊匹配，只要包含即可）
            min_confidence: 最小置信度阈值，低于此值的识别结果将被忽略

        Returns:
            文字中心的坐标 (x, y)，如果未找到则返回 None

        Note:
            - 采用模糊匹配：只要识别到的文字包含目标文字即可
            - 置信度阈值默认0.6，过滤掉识别不准确的结果
            - 返回的是文字区域的中心点坐标
        """
        result = self.reader.ocr(img_path)
        if not result or not result[0]:
            return None

        for line in result[0]:
            text, conf = line[1][0], line[1][1]
            if conf > min_confidence:
                # 应用过滤器
                filtered_text = self._apply_filters(text)
                # 对目标文字也应用过滤器进行匹配
                if target in filtered_text:
                    box = line[0]
                    cx = int((box[0][0] + box[2][0]) / 2)
                    cy = int((box[0][1] + box[2][1]) / 2)
                    print(f"[DEBUG] 识别到: {text} -> 过滤后: {filtered_text} ({conf:.2f}) 坐标: {cx}, {cy}")
                    return cx, cy
        return None

    def find_all_text(self, img_path: str, min_confidence: float = 0.6) -> list:
        """查找截图中所有文字及其位置

        Args:
            img_path: 截图文件的路径
            min_confidence: 最小置信度阈值

        Returns:
            识别结果列表，每项包含 (文字, 置信度, 坐标x, 坐标y)
        """
        result = self.reader.ocr(img_path)
        if not result or not result[0]:
            return []

        results = []
        for line in result[0]:
            text, conf = line[1][0], line[1][1]
            if conf > min_confidence:
                # 应用过滤器
                filtered_text = self._apply_filters(text)
                box = line[0]
                cx = int((box[0][0] + box[2][0]) / 2)
                cy = int((box[0][1] + box[2][1]) / 2)
                results.append((filtered_text, conf, cx, cy))
        return results

    def find_text_exact(
        self, img_path: str, target: str, min_confidence: float = 0.6
    ) -> Optional[Tuple[int, int]]:
        """精确查找文字（完整匹配）

        Args:
            img_path: 截图文件的路径
            target: 要查找的目标文字（需要完全匹配）
            min_confidence: 最小置信度阈值

        Returns:
            文字中心的坐标 (x, y)，如果未找到则返回 None
        """
        result = self.reader.ocr(img_path)
        if not result or not result[0]:
            return None

        for line in result[0]:
            text, conf = line[1][0], line[1][1]
            if conf > min_confidence:
                filtered_text = self._apply_filters(text)
                if filtered_text == target:
                    box = line[0]
                    cx = int((box[0][0] + box[2][0]) / 2)
                    cy = int((box[0][1] + box[2][1]) / 2)
                    print(f"[DEBUG] 精确识别到: {text} -> 过滤后: {filtered_text} ({conf:.2f}) 坐标: {cx}, {cy}")
                    return cx, cy
        return None