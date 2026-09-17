"""坐标调试工具 - 用于调试OCR识别和点击坐标"""

import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from core import ADBTools, OCREngine
from utils import load_config


class ClickDebugger:
    """坐标调试器

    提供可视化界面用于：
    1. 实时查看模拟器截图
    2. 点击屏幕查看实际坐标
    3. OCR识别文字并显示位置
    4. 调试维度评分坐标
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("坐标调试工具")

        conf = load_config()
        self.screen_width = conf.get("screen_width", 720)
        self.screen_height = conf.get("screen_height", 1280)
        self.canvas_width = 360
        self.canvas_height = 640
        self.scale_x = self.screen_width / self.canvas_width
        self.scale_y = self.screen_height / self.canvas_height

        self.label = tk.Label(self.root, text="点击截图查看坐标")
        self.label.pack(pady=10)

        self.canvas = tk.Canvas(
            self.root, width=self.canvas_width, height=self.canvas_height
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)

        self.coord_label = tk.Label(self.root, text="点击位置坐标: 未点击")
        self.coord_label.pack(pady=10)

        self.btn_frame = tk.Frame(self.root)
        self.btn_frame.pack(pady=10)

        tk.Button(self.btn_frame, text="截图", command=self.take_screenshot).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(self.btn_frame, text="OCR识别文字", command=self.run_ocr).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(
            self.btn_frame, text="识别维度", command=self.recognize_dimensions
        ).pack(side=tk.LEFT, padx=5)

        self.info_text = tk.Text(self.root, height=15, width=50)
        self.info_text.pack(pady=10)

        self.ocr_engine = None
        self.adb = None
        self.current_image = None
        self.ocr_results = []
        self._image_refs = []

        self._init_devices()

    def _init_devices(self):
        """初始化设备连接"""
        try:
            conf = load_config()
            self.adb = ADBTools(
                conf["adb_path"], conf.get("device_id", "127.0.0.1:16416")
            )
            self.adb.connect()
            self.ocr_engine = OCREngine()
            self.info_text.insert(tk.END, "设备连接成功\n")
        except Exception as e:
            self.info_text.insert(tk.END, f"连接失败: {e}\n")

    def take_screenshot(self):
        """截取屏幕"""
        if self.adb:
            screenshot = self.adb.take_screenshot("debug_screen.png")
            self._display_image(screenshot)
            self.info_text.insert(tk.END, "截图已更新\n")
            self.info_text.see(tk.END)

    def _display_image(self, filepath: str):
        """在画布上显示图片"""
        try:
            img = Image.open(filepath)
            img = img.resize((360, 640), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._image_refs.append(photo)
            self.current_image = photo
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        except Exception as e:
            self.info_text.insert(tk.END, f"显示图片失败: {e}\n")

    def on_click(self, event):
        """处理画布点击事件"""
        x, y = event.x, event.y
        actual_x = int(x * self.scale_x)
        actual_y = int(y * self.scale_y)
        self.coord_label.config(
            text=f"点击位置坐标: ({x}, {y})  ->  实际坐标: ({actual_x}, {actual_y})"
        )
        self.info_text.insert(
            tk.END, f"点击: canvas=({x}, {y}), 实际=({actual_x}, {actual_y})\n"
        )
        self.info_text.see(tk.END)

    def run_ocr(self):
        """运行OCR识别"""
        if not self.ocr_engine or not self.adb:
            self.info_text.insert(tk.END, "请先连接设备\n")
            return

        screenshot = self.adb.take_screenshot("ocr_input.png")
        results = self.ocr_engine.find_text(screenshot, None)

        self.info_text.insert(tk.END, "\n=== OCR 识别结果 ===\n")
        self.ocr_results = []
        if results:
            for text, pos in results:
                self.info_text.insert(tk.END, f"文字: '{text}' -> 坐标: {pos}\n")
                self.ocr_results.append((text, pos))
        else:
            self.info_text.insert(tk.END, "未识别到文字\n")
        self.info_text.see(tk.END)

    def _save_click_region_screenshot(
        self, full_screenshot: str, tap_x: int, tap_y: int, dim_name: str, star: int
    ) -> None:
        """保存点击位置周围100x100像素范围的截图

        Args:
            full_screenshot: 完整截图路径
            tap_x: 点击位置X坐标
            tap_y: 点击位置Y坐标
            dim_name: 维度名称
            star: 星级
        """
        try:
            img = Image.open(full_screenshot)

            crop_size = 100
            half_crop = crop_size // 2

            left = max(0, tap_x - half_crop)
            top = max(0, tap_y - half_crop)
            right = min(img.width, tap_x + half_crop)
            bottom = min(img.height, tap_y + half_crop)

            cropped = img.crop((left, top, right, bottom))

            filename = f"debug_{dim_name}_{star}star_pos_{tap_x}_{tap_y}.png"
            cropped.save(filename)
            self.info_text.insert(tk.END, f"    📸 已保存: {filename}\n")
        except Exception as e:
            self.info_text.insert(tk.END, f"    ⚠️ 截图失败: {e}\n")

    def recognize_dimensions(self):
        """识别评分维度"""
        if not self.ocr_engine or not self.adb:
            self.info_text.insert(tk.END, "请先连接设备\n")
            return

        screenshot = self.adb.take_screenshot("dimensions_debug.png")

        dimensions = ["旋律", "演唱", "歌词"]
        self.info_text.insert(tk.END, "\n=== 维度识别结果 ===\n")

        star_positions = {2: 550, 3: 600, 4: 650, 5: 700}

        for dim in dimensions:
            pos = self.ocr_engine.find_text(screenshot, dim)
            if pos:
                self.info_text.insert(tk.END, f"'{dim}' 坐标: {pos}\n")
                for star in range(2, 6):
                    tap_x = pos[0] + star_positions[star]
                    tap_y = pos[1]
                    self.info_text.insert(
                        tk.END, f"  {star}星 点击位置: ({tap_x}, {tap_y})\n"
                    )
                    self._save_click_region_screenshot(
                        screenshot, tap_x, tap_y, dim, star
                    )
            else:
                self.info_text.insert(tk.END, f"'{dim}' 未识别到\n")

        self._display_image(screenshot)

    def run(self):
        """启动调试工具"""
        self.root.mainloop()


if __name__ == "__main__":
    debugger = ClickDebugger()
    debugger.run()
