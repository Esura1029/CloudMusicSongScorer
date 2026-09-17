"""音乐APP自动评分助手 - GUI界面"""

import threading
import sys
import io
from typing import Optional

import customtkinter as ctk

from main_bot import run_main_task, stop_task, set_config

ctk.set_appearance_mode("dark")


class LogRedirector(io.StringIO):
    """日志重定向器

    将标准输出重定向到GUI的文本控件，
    实现日志实时显示功能。
    """

    def __init__(self, text_widget: ctk.CTkTextbox):
        super().__init__()
        self.text_widget = text_widget
        self.original_stdout = sys.stdout

    def write(self, msg: str) -> None:
        self.original_stdout.write(msg)
        self.original_stdout.flush()
        if msg and msg.strip():
            self.text_widget.master.after(0, self._update_ui, msg)

    def _update_ui(self, msg: str) -> None:
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        except Exception:
            pass

    def flush(self) -> None:
        pass


class MusicBotGUI(ctk.CTk):
    """评分助手主界面

    提供可视化的操作界面，包括：
    - 参数配置区域
    - 开始/停止控制
    - 实时日志显示
    - 进度跟踪
    """

    def __init__(self):
        super().__init__()
        self.title("音乐APP评分助手 v2.0")
        self.geometry("650x850")

        self.songs_rated = 0
        self.is_running = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """初始化UI组件"""
        # 状态标签
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=15, padx=20, fill="x")

        self.status_label = ctk.CTkLabel(
            self.header_frame, text="状态: 等待启动", font=("微软雅黑", 20, "bold")
        )
        self.status_label.pack(pady=5)

        # 参数配置区域
        self.config_frame = ctk.CTkFrame(self, fg_color=("#2B2B2B", "#1a1a1a"))
        self.config_frame.pack(pady=10, padx=20, fill="x")

        self.config_label = ctk.CTkLabel(
            self.config_frame, text="参数配置", font=("微软雅黑", 14, "bold")
        )
        self.config_label.pack(pady=(10, 5), padx=10, anchor="w")

        self.config_grid = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.config_grid.pack(pady=5, padx=15, fill="x")

        # 听歌等待时间
        self.wait_var = ctk.StringVar(value="18")
        ctk.CTkLabel(self.config_grid, text="听歌等待(秒):").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.wait_entry = ctk.CTkEntry(
            self.config_grid, width=80, textvariable=self.wait_var
        )
        self.wait_entry.grid(row=0, column=1, sticky="w", pady=5, padx=(5, 20))

        # 最低星级
        self.min_star_var = ctk.StringVar(value="2")
        ctk.CTkLabel(self.config_grid, text="最低星级:").grid(
            row=0, column=2, sticky="w", pady=5
        )
        self.min_star_menu = ctk.CTkOptionMenu(
            self.config_grid,
            width=70,
            values=["1", "2", "3", "4", "5"],
            variable=self.min_star_var,
        )
        self.min_star_menu.grid(row=0, column=3, sticky="w", pady=5)

        # 最高星级
        self.max_star_var = ctk.StringVar(value="4")
        ctk.CTkLabel(self.config_grid, text="最高星级:").grid(
            row=1, column=2, sticky="w", pady=5
        )
        self.max_star_menu = ctk.CTkOptionMenu(
            self.config_grid,
            width=70,
            values=["1", "2", "3", "4", "5"],
            variable=self.max_star_var,
        )
        self.max_star_menu.grid(row=1, column=3, sticky="w", pady=5)

        # 进度显示
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(pady=5, padx=20, fill="x")

        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="进度: 0 首歌曲已评分", font=("微软雅黑", 12)
        )
        self.progress_label.pack(anchor="w", padx=5)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=15)
        self.progress_bar.pack(fill="x", padx=5, pady=5)
        self.progress_bar.set(0)

        # 控制按钮
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(pady=10, fill="x")

        self.start_button = ctk.CTkButton(
            self.button_frame,
            text="开始自动评分",
            font=("微软雅黑", 16, "bold"),
            height=45,
            fg_color="#18C440",
            hover_color="#15A536",
            command=self.start_bot,
        )
        self.start_button.pack(side="left", expand=True, padx=5)

        self.stop_button = ctk.CTkButton(
            self.button_frame,
            text="停止任务",
            font=("微软雅黑", 16, "bold"),
            height=45,
            fg_color="#E05454",
            hover_color="#C74444",
            command=self.stop_bot,
            state="disabled",
        )
        self.stop_button.pack(side="left", expand=True, padx=5)

        # 日志区域
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.pack(pady=10, padx=20, fill="both", expand=True)

        self.log_label = ctk.CTkLabel(
            self.log_frame, text="运行日志", font=("微软雅黑", 12, "bold")
        )
        self.log_label.pack(pady=(5, 0), padx=10, anchor="w")

        self.log_text = ctk.CTkTextbox(self.log_frame, font=("Consolas", 11))
        self.log_text.pack(pady=10, padx=10, fill="both", expand=True)
        self.log_text.configure(state="disabled")

        # 页脚
        self.footer_frame = ctk.CTkFrame(self, height=30, fg_color="transparent")
        self.footer_frame.pack(pady=(0, 10), fill="x")

        self.info_label = ctk.CTkLabel(
            self.footer_frame,
            text="提示: 关闭窗口即可停止程序 | 评分随机2-4星",
            font=("微软雅黑", 10),
            text_color="gray",
        )
        self.info_label.pack()

        self.log_redirector = LogRedirector(self.log_text)

    def _get_config(self) -> dict:
        """获取当前配置"""
        try:
            wait_time = int(self.wait_var.get())
            min_star = int(self.min_star_var.get())
            max_star = int(self.max_star_var.get())
            if min_star > max_star:
                min_star, max_star = max_star, min_star
            return {"wait_time": wait_time, "min_star": min_star, "max_star": max_star}
        except ValueError:
            return {"wait_time": 18, "min_star": 2, "max_star": 4}

    def clear_log(self) -> None:
        """清空日志"""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def start_bot(self) -> None:
        """启动评分任务"""
        config = self._get_config()
        set_config(config)

        self.is_running = True
        self.songs_rated = 0
        self.status_label.configure(text="状态: 正在运行...", text_color="#18C440")
        self.start_button.configure(state="disabled", text="运行中...")
        self.stop_button.configure(state="normal")
        self.clear_log()
        self.progress_bar.set(0)
        self.progress_label.configure(text="进度: 0 首歌曲已评分")

        thread = threading.Thread(target=self.run_with_log_capture, daemon=True)
        thread.start()

    def stop_bot(self) -> None:
        """停止评分任务"""
        stop_task()
        self.stop_button.configure(state="disabled")
        self.status_label.configure(text="状态: 正在停止...", text_color="#FFA500")

    def update_progress(self, current: int, total: int, message: str = "") -> None:
        """更新进度显示"""
        self.songs_rated = current
        self.progress_label.configure(text=f"进度: {current} 首歌曲已评分 | {message}")
        if total > 0:
            self.progress_bar.set(current / total)

    def run_with_log_capture(self) -> None:
        """在日志捕获模式下运行任务"""
        old_stdout = sys.stdout
        try:
            sys.stdout = self.log_redirector
            print("[INFO] 正在检查 ADB 连接及APP环境...")
            run_main_task(self.update_progress)
            self.after(
                0,
                lambda: self.status_label.configure(
                    text="状态: 任务完成 ✅", text_color="#18C440"
                ),
            )
        except Exception as e:
            import traceback

            error_msg = f"[ERROR] 运行失败: {e}\n{traceback.format_exc()}"
            print(error_msg)
            self.after(
                0,
                lambda: self.status_label.configure(
                    text="状态: 发生异常 ❌", text_color="#E05454"
                ),
            )
        finally:
            self.is_running = False
            sys.stdout = old_stdout
            self.after(
                0,
                lambda: self.start_button.configure(
                    state="normal", text="重新开始评分"
                ),
            )
            self.after(0, lambda: self.stop_button.configure(state="disabled"))


if __name__ == "__main__":
    app = MusicBotGUI()
    app.mainloop()
