import time
import random
from typing import Dict, Optional, Any, Callable, Tuple

from .ocr_engine import OCREngine
from .adb_tools import ADBTools


class SongScorer:
    """歌曲评分执行器

    职责：完成网易云音乐评分流程中的所有评分操作。

    【评分流程说明】
    网易云音乐的评分分为两个阶段：

    ┌─────────────────────────────────────────────────────────┐
    │ 阶段1: 总评分弹窗                                        │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │           🎵 请评定这首歌曲                       │   │
    │  │           ★ ★ ★ ☆ ☆                            │   │
    │  │           [2星] [3星] [4星] [5星]                 │   │
    │  └─────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────┘
                            ↓ (点击星级后自动进入)
    ┌─────────────────────────────────────────────────────────┐
    │ 阶段2: 维度评分页面                                      │
    │  ┌─────────────────────────────────────────────────┐   │
    │  │  旋律: ★ ★ ★ ☆ ☆  [点击选择星级]                │   │
    │  │  演唱: ★ ★ ★ ★ ☆                              │   │
    │  │  歌词: ★ ★ ☆ ☆ ☆                              │   │
    │  │                                                │   │
    │  │           [提交并评下一首]                       │   │
    │  └─────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────┘

    【星级评分机制】
    - 星级范围: 1-5星
    - 可配置范围: min_star 到 max_star（如2-4星）
    - 每个维度随机选择配置范围内的星级
    """

    # 评分维度列表：旋律（曲调）、演唱（歌声）、歌词（词内容）
    DIMENSIONS = ["旋律", "演唱", "歌词"]

    # 维度之间的Y轴间距（像素）和允许误差
    DIMENSION_Y_SPACING = 80
    DIMENSION_Y_TOLERANCE = 15

    # 维度评分星级权重：2、3、4星权重相近，5星权重最低
    DIMENSION_STAR_WEIGHTS = {2: 30, 3: 33, 4: 30, 5: 7}

    # 【重要】星级位置配置
    #
    # 【阶段1 - 弹窗中的星级位置】
    # 弹窗中"请评定"文字下方会显示星级评分选项。
    # 这些offset是相对于"请评定"文字位置的偏移量。
    # 由于星级是横向排列的，所以只需要调整X坐标。
    #
    #  offset: X轴偏移量（正值表示向右移动）
    #  注意：这里用负数表示星级选项在文字左侧
    STAR_POSITIONS_POPUP = {
        2: -100,  # 2星：向左偏移100像素
        3: -20,  # 3星：向左偏移20像素
        4: 70,  # 4星：向右偏移70像素
        5: 150,  # 5星：向右偏移150像素
    }

    # 【阶段2 - 维度页面中的星级位置】
    # 维度页面中，每个维度文字（如"旋律"）右侧会有5颗星星，
    # 需要点击对应的星星位置来选择星级。
    # 这些offset是相对于维度文字位置的X轴偏移量。
    #
    #  界面布局示意（以"旋律"维度为例）：
    #  ┌──────────────────────────────────────────────────┐
    #  │  旋律: ★ ★ ★ ★ ★                             │
    #  │  ↑      ↑  ↑  ↑  ↑                               │
    #  │ 文字   1星 2星 3星 4星 5星                        │
    #  │       │   │   │   │                              │
    #  │       └───┴───┴───┴───→ X轴偏移量                │
    #  └──────────────────────────────────────────────────┘
    #
    #  实际坐标 = 维度文字X坐标 + offset
    STAR_POSITIONS_DIMENSION = {
        2: 315,  # 点击第2颗星
        3: 385,  # 点击第3颗星
        4: 455,  # 点击第4颗星
        5: 525,  # 点击第5颗星
    }

    def __init__(
        self, ocr: OCREngine, adb: ADBTools, min_star: int = 2, max_star: int = 5
    ):
        """初始化评分器

        Args:
            ocr: OCR引擎实例，用于识别界面文字和位置
            adb: ADB工具实例，用于执行点击操作
            min_star: 最低评分星级（默认2星）
            max_star: 最高评分星级（默认5星）
        """
        self.ocr = ocr
        self.adb = adb
        self.min_star = min_star
        self.max_star = max_star

    def _validate_dimension_position(
        self, screenshot: str, dim_name: str, dim_pos: Tuple[int, int]
    ) -> bool:
        """验证识别到的维度位置是否符合真实的维度间距规律

        【验证逻辑】
        真正的评分维度页面上，"旋律"、"演唱"、"歌词"三个维度
        在Y轴上的间距固定约80像素。
        如果识别到的"歌词"不在这个间距范围内，则可能是误识别。

        Args:
            screenshot: 截图文件路径
            dim_name: 维度名称
            dim_pos: 该维度的坐标 (x, y)

        Returns:
            True 如果位置合理，否则 False
        """
        all_positions = {}
        for dim in self.DIMENSIONS:
            pos = self.ocr.find_text(screenshot, dim)
            if pos:
                all_positions[dim] = pos

        if len(all_positions) < 2:
            return True

        y_ref = dim_pos[1]
        for other_name, other_pos in all_positions.items():
            if other_name == dim_name:
                continue
            y_diff = abs(other_pos[1] - y_ref)
            expected_diff = self.DIMENSION_Y_SPACING
            if abs(y_diff - expected_diff) <= self.DIMENSION_Y_TOLERANCE:
                return True

        if len(all_positions) >= 2:
            y_values = [p[1] for p in all_positions.values()]
            y_values.sort()
            if len(y_values) >= 2:
                gaps = [y_values[i + 1] - y_values[i] for i in range(len(y_values) - 1)]
                for gap in gaps:
                    if (
                        abs(gap - self.DIMENSION_Y_SPACING)
                        <= self.DIMENSION_Y_TOLERANCE
                    ):
                        return True

        return False

    def rate_overall(self, rating_pos: Optional[tuple] = None) -> int:
        """执行阶段1：总评分（弹窗中的星级选择）

        【工作原理】
        1. 定位"请评定"文字的位置
        2. 根据随机生成的星级，计算点击位置
        3. 点击对应位置完成星级选择

        【点击坐标计算】
        点击位置 = (文字X坐标 + X轴偏移量, 文字Y坐标 + 100)
        - X轴偏移量：决定点击哪颗星
        - Y轴偏移量(+100)：因为星级在文字下方约100像素处

        Args:
            rating_pos: "请评定"文字的坐标 (x, y)，如果为None则自动查找

        Returns:
            选择的星级数（2-5）
        """
        star = random.randint(self.min_star, self.max_star)
        offset = self.STAR_POSITIONS_POPUP.get(star, 70)

        if rating_pos:
            # 直接使用传入的位置
            self.adb.tap(rating_pos[0] + offset, rating_pos[1] + 100)
        else:
            # 自动查找"请评定"文字
            screenshot = self.adb.take_screenshot("popup.png")
            pos = self.ocr.find_text(screenshot, "请评定")
            if pos:
                self.adb.tap(pos[0] + offset, pos[1] + 100)

        return star

    def rate_dimensions(self) -> Dict[str, Optional[int]]:
        """执行阶段2：维度评分（旋律/演唱/歌词）

        【工作原理】
        1. 向上滑动屏幕，展开维度评分区域
        2. 对每个维度文字进行定位
        3. 根据随机生成的星级，计算并点击对应位置
        4. 每个维度独立评分

        【界面布局变化】
        维度评分区域初始可能不在屏幕可见范围内，
        需要向上滑动才能看到"旋律"、"演唱"、"歌词"三个维度。
        滑动后这些维度的文字会出现在屏幕上方区域。

        【坐标计算详解】
        对于每个维度（如"旋律"）：
        1. OCR识别返回文字中心坐标 (dim_x, dim_y)
        2. 星级选项在该文字右侧水平排列
        3. 点击位置 = (dim_x + 星位偏移量, dim_y)

        例如选择3星：
        - 维度文字位置：假设OCR返回 (100, 300)
        - 3星偏移量：600
        - 点击位置：(100 + 600, 300) = (700, 300)

        Args:
            无参数（使用类属性中的维度列表）

        Returns:
            包含各维度评分的字典：
            {
                "旋律": 3,   # 3星
                "演唱": 4,   # 4星
                "歌词": 2    # 2星
            }
            未识别到的维度值为 None
        """
        results = {}

        # 【关键步骤】滑动到维度评分区域
        # 维度区域初始不在可见范围，需要从当前位置向上滑动
        # 起始点 (360, 1000)：屏幕中下方
        # 结束点 (360, 250)：屏幕中上方
        # 持续时间 500ms：自然的滑动速度
        self.adb.swipe(360, 1000, 360, 250, 500)
        time.sleep(1)

        # 截取滑动后的屏幕
        screenshot = self.adb.take_screenshot("dimensions.png")

        # 遍历每个维度进行评分
        for dim in self.DIMENSIONS:
            dim_pos = self.ocr.find_text(screenshot, dim)
            if dim_pos:
                # 【Y轴间距验证】避免误识别
                # 只有符合维度间距规律的位置才认为是真正的维度
                if not self._validate_dimension_position(screenshot, dim, dim_pos):
                    print(f"[WARNING] '{dim}' 位置验证失败，可能是误识别")
                    results[dim] = None
                    continue

                # 【加权随机星级选择】
                # 维度评分固定为2-5星，5星权重最低，2/3/4星权重相近
                stars = list(self.DIMENSION_STAR_WEIGHTS.keys())
                weights = list(self.DIMENSION_STAR_WEIGHTS.values())
                dim_star = random.choices(stars, weights=weights, k=1)[0]

                # 【计算点击位置】
                # 根据星级获取对应的X轴偏移量
                star_offset = self.STAR_POSITIONS_DIMENSION.get(dim_star, 315)

                # 最终点击坐标 = 维度文字X + 星级偏移量
                tap_x = dim_pos[0] + star_offset

                # 点击该位置
                self.adb.tap(tap_x, dim_pos[1] + 3)
                results[dim] = dim_star
                time.sleep(0.5)  # 等待评分动画
            else:
                # 该维度文字未能识别（可能界面有变化）
                results[dim] = None

        return results

    def submit_rating(self) -> bool:
        """提交评分

        【工作原理】
        1. 截取当前屏幕
        2. 查找"提交并评下一首"按钮
        3. 点击按钮完成提交

        Args:
            无参数

        Returns:
            是否提交成功
        """
        screenshot = self.adb.take_screenshot("submit.png")
        submit_pos = self.ocr.find_text(screenshot, "提交并评下一首")

        if submit_pos:
            self.adb.tap(submit_pos[0], submit_pos[1])
            return True

        return False

    def full_rating_cycle(
        self,
        page_info: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """执行完整的评分周期

        【完整评分流程】
        ┌────────────────────────────────────────────────────────┐
        │                                                        │
        │  1. 定位"请评定"文字位置                                │
        │           ↓                                            │
        │  2. 执行总评分（阶段1）                                 │
        │           ↓                                            │
        │  3. 执行维度评分（阶段2）                               │
        │      - 旋律: 随机2-4星                                  │
        │      - 演唱: 随机2-4星                                  │
        │      - 歌词: 随机2-4星                                  │
        │           ↓                                            │
        │  4. 点击提交按钮                                        │
        │           ↓                                            │
        │  5. 返回评分结果                                        │
        │                                                        │
        └────────────────────────────────────────────────────────┘

        Args:
            page_info: 页面识别器返回的页面信息字典
            progress_callback: 进度回调函数，用于更新UI

        Returns:
            包含完整评分结果的字典：
            {
                "overall_star": 3,        # 总评分星级
                "dimensions": {          # 各维度评分
                    "旋律": 4,
                    "演唱": 3,
                    "歌词": 2
                },
                "submitted": True         # 是否提交成功
            }
        """
        results = {"overall_star": None, "dimensions": {}, "submitted": False}

        # 获取"请评定"文字位置
        if page_info is None:
            screenshot = self.adb.take_screenshot("rating_popup.png")
            rating_pos = self.ocr.find_text(screenshot, "请评定")
        else:
            rating_pos = page_info.get("info", {}).get("rating_trigger_pos")

        # 【阶段1】执行总评分
        if rating_pos:
            results["overall_star"] = self.rate_overall(rating_pos)
            print(f"已点击总评分 ({results['overall_star']}星)")

        # 【阶段2】执行维度评分
        results["dimensions"] = self.rate_dimensions()

        # 打印各维度评分结果
        for dim, star in results["dimensions"].items():
            if star:
                print(f"已评分: {dim} ({star}星)")

        # 更新进度
        if progress_callback:
            progress_callback(0, 0, "提交评分中...")

        # 【阶段3】提交评分
        results["submitted"] = self.submit_rating()

        return results

    def rate_if_on_rating_page(
        self, page_info: Dict[str, Any], progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """条件评分：根据页面类型决定是否执行评分

        【使用场景】
        在主循环中判断当前页面是否为评分相关页面，
        如果是则执行评分，不是则跳过。

        Args:
            page_info: 页面识别器返回的页面信息
            progress_callback: 进度回调函数

        Returns:
            评分结果或跳过提示
        """
        page_type = page_info["type"]

        if page_type.value == "rating_popup":
            print("检测到评分弹窗，执行评分...")
            return self.full_rating_cycle(page_info, progress_callback)

        return {"action": "none", "page_type": page_type.value}
