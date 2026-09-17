import os
import random
import subprocess
import sys
from typing import Optional


class ADBTools:
    """ADB设备交互工具类

    封装与Android模拟器通过ADB协议进行交互的所有操作，
    包括连接设备、截图、点击、滑动等基本操作。
    """

    def __init__(self, adb_path: str, device_id: str):
        """初始化ADB工具

        Args:
            adb_path: adb.exe文件的完整路径
            device_id: 目标设备ID，如 "127.0.0.1:16416"
        """
        self.adb_path = adb_path
        self.device_id = device_id

    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        """获取资源文件的绝对路径（兼容PyInstaller打包）

        Args:
            relative_path: 相对路径

        Returns:
            资源文件的绝对路径
        """
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def _run(self, cmd: str) -> subprocess.CompletedProcess:
        """执行ADB命令的内部方法

        Args:
            cmd: ADB命令参数（不包含adb路径和设备ID）

        Returns:
            subprocess.CompletedProcess对象
        """
        full_cmd = f'"{self.adb_path}" -s {self.device_id} {cmd}'
        return subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def connect(self) -> bool:
        """连接到指定的模拟器设备

        Returns:
            连接是否成功
        """
        print(f"[INFO] 正在连接模拟器: {self.device_id}...")
        result = self._run(f"connect {self.device_id}")
        return result.returncode == 0

    def tap(self, x: int, y: int, offset: int = 3) -> None:
        """在指定坐标位置执行点击操作

        Args:
            x: 点击的X坐标
            y: 点击的Y坐标
            offset: 点击偏移范围，会在[-offset, +offset]范围内随机偏移
        """
        random_x = x + random.randint(-offset, offset)
        random_y = y + random.randint(-offset, offset)
        print(
            f"[DEBUG] 点击坐标: ({random_x}, {random_y}) (原始: {x}, {y}, 偏移: {random_x - x}, {random_y - y})"
        )
        self._run(f"shell input tap {random_x} {random_y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 500) -> None:
        """执行滑动操作

        Args:
            x1: 起始点X坐标
            y1: 起始点Y坐标
            x2: 结束点X坐标
            y2: 结束点Y坐标
            duration: 滑动持续时间（毫秒）
        """
        self._run(f"shell input swipe {x1} {y1} {x2} {y2} {duration}")

    def take_screenshot(self, filename: str) -> str:
        """截取当前屏幕并保存到本地

        截图流程：
        1. 使用screencap命令在模拟器内截图
        2. 通过adb pull将截图拉到本地

        Args:
            filename: 保存的文件名

        Returns:
            截图文件的本地完整路径
        """
        folder = "screenshots"
        if not os.path.exists(folder):
            os.makedirs(folder)
        local_path = os.path.join(os.getcwd(), folder, filename)
        self._run("shell screencap -p /sdcard/screen.png")
        self._run(f"pull /sdcard/screen.png {local_path}")
        return local_path
