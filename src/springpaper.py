import base64
import json
import mimetypes
import os
import re
import sys
import threading
import time
from io import BytesIO
from pathlib import Path
from tkinter import (
    BooleanVar,
    Canvas,
    StringVar,
    Toplevel,
    filedialog,
    messagebox,
)

import customtkinter as ctk
import pyautogui
from PIL import Image
from openai import OpenAI


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = APP_DIR / "config.json"
PROMPT_PATH = APP_DIR / "scoring_prompt.md"
LAST_CAPTURE_PATH = APP_DIR / "last_essay_capture.png"
LOG_DIR = APP_DIR / "logs"
VISIBLE_LOG_MAX_CHARS = 10_000
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_RETENTION_DAYS = 3
SCROLL_UNITS_PER_NOTCH = 30
TEXTBOX_SCROLL_UNITS_PER_NOTCH = 14
PRODUCT_NAME_CN = "春笺"
PRODUCT_NAME_EN = "SpringPaper"
APP_VERSION = "1.2.0"
BRAND_TAGLINE = "AI 提高效率，判断仍属于老师。"
TAB_MARKING = "阅卷"
TAB_STANDARD = "AI与标准"
TAB_CALIBRATION = "校准"
TAB_LOG = "记录"
DAILY_WHISPERS = [
    "今天也请相信自己的判断。",
    "连评前，记得喝口水。",
    "每一篇作文，都有人认真写过。",
    "愿每一篇作文，都被温柔阅读。",
    "慢一点也没关系，准确比匆忙更重要。",
    "夜里的阅卷，也可以有一点温柔。",
    "分数是结果，理解才是老师的工作。",
]
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PRESENTATION_LEVELS = ["自动", "整洁", "较整洁", "欠整洁", "凌乱难辨"]
SUBMIT_MODE_BUTTON = "按钮打分"
SUBMIT_MODE_INPUT = "输入框打分"
SUBMIT_MODES = [SUBMIT_MODE_BUTTON, SUBMIT_MODE_INPUT]
OUTPUT_MODE_FAST = "极速"
OUTPUT_MODE_STANDARD = "标准"
OUTPUT_MODE_REVIEW = "复核"
OUTPUT_MODES = [OUTPUT_MODE_FAST, OUTPUT_MODE_STANDARD, OUTPUT_MODE_REVIEW]
OUTPUT_MODE_PROMPTS = {
    OUTPUT_MODE_FAST: """
输出模式：极速。
本输出模式优先级高于前文 JSON 字段要求。
只返回严格 JSON，不要 Markdown，不要自然语言，不要解释，不要理由。
JSON 必须且只能包含：
{
  "score": 0到50之间的整数,
  "confidence": "high/medium/low",
  "recheck": true或false
}
不要返回 strengths、weaknesses、notes、comment、reason 或任何其他字段。
""",
    OUTPUT_MODE_STANDARD: """
输出模式：标准。
本输出模式优先级高于前文 JSON 字段要求。
只返回严格 JSON，不要 Markdown，不要长篇分析。
JSON 必须且只能包含：
{
  "score": 0到50之间的整数,
  "confidence": "high/medium/low",
  "recheck": true或false,
  "reason": "不超过30个汉字的一句评分理由"
}
""",
    OUTPUT_MODE_REVIEW: """
输出模式：复核。
请保留完整评分 JSON，可包含 score、band、confidence、recheck、presentation_level、score_adjustment、reasons、strengths、weaknesses、notes 等字段。
仍然不要输出 Markdown，不要输出思考过程。
""",
}
MODEL_PRESETS = [
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen3-VL-30B-A3B-Instruct",
    "Qwen/Qwen3.6-35B-A3B",
    "Qwen/Qwen3.5-397B-A17B",
    "Qwen/Qwen3.5-122B-A10B",
    "Qwen/Qwen3.5-35B-A3B",
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3-VL-30B-A3B-Thinking",
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen3-VL-32B-Thinking",
    "deepseek-ai/DeepSeek-OCR",
]

PROVIDERS = {
    "openai": {
        "base_url": "",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "note": "OpenAI 视觉模型，适合直接看作文截图。",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-VL-32B-Instruct",
        "api_key_env": "SILICONFLOW_API_KEY",
        "note": "硅基流动 OpenAI 兼容接口；请选择支持视觉的 VLM 模型。",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "note": "DeepSeek 普通聊天模型偏文本；若模型不支持图片，会评分失败。",
    },
    "custom": {
        "base_url": "",
        "model": "",
        "api_key_env": "OPENAI_API_KEY",
        "note": "任意 OpenAI 兼容接口；必须支持 /chat/completions 和 image_url。",
    },
}


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rect_to_tuple(rect):
    return (int(rect["x"]), int(rect["y"]), int(rect["w"]), int(rect["h"]))


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("AI 没有返回 JSON")
    return json.loads(match.group(0))


class RegionSelector:
    def __init__(self, root, title, callback):
        self.root = root
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.rect_id = None

        self.win = Toplevel(root)
        self.win.title(title)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.28)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")

        import tkinter as tk

        self.canvas = tk.Canvas(self.win, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            30,
            30,
            anchor="nw",
            fill="white",
            font=("Microsoft YaHei UI", 18, "bold"),
            text="拖选区域。按 Esc 取消。",
        )
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.win.bind("<Escape>", lambda _: self.win.destroy())

    def on_press(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=3)

    def on_drag(self, event):
        if self.rect_id is not None:
            self.canvas.coords(
                self.rect_id,
                self.start_x,
                self.start_y,
                event.x_root,
                event.y_root,
            )

    def on_release(self, event):
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x_root, event.y_root
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        self.win.destroy()
        if w < 20 or h < 20:
            messagebox.showwarning("区域太小", "请重新拖选一个更大的区域。")
            return
        self.callback({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})


class MarkingAssistant:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{PRODUCT_NAME_CN} {PRODUCT_NAME_EN}")
        self.root.attributes("-topmost", True)

        self.config = load_json(
            CONFIG_PATH,
            {
                "provider": "openai",
                "base_url": "",
                "api_key_env": "OPENAI_API_KEY",
                "model": "gpt-4o-mini",
                "extra_prompt": "",
                "support_material_paths": [],
                "max_image_side": 1600,
                "request_timeout_seconds": 180,
                "max_output_tokens": 800,
                "single_output_mode": OUTPUT_MODE_STANDARD,
                "auto_output_mode": OUTPUT_MODE_FAST,
                "presentation_override": "自动",
                "max_score": 50,
                "essay_region": None,
                "score_grid": None,
                "score_input": None,
                "submit_button": None,
                "submit_mode": SUBMIT_MODE_BUTTON,
                "auto_submit_after_confirm": True,
                "auto_loop_max_count": 20,
                "auto_loop_delay_seconds": 1.5,
                "auto_loop_pause_on_recheck": True,
                "click_pause_seconds": 0.15,
            },
        )

        provider = self.config.get("provider", "openai")
        profile = PROVIDERS.get(provider, PROVIDERS["openai"])
        env_name = self.config.get("api_key_env") or profile["api_key_env"]
        self.provider = StringVar(value=provider)
        self.base_url = StringVar(value=self.config.get("base_url", profile["base_url"]))
        self.api_key_env = StringVar(value=env_name)
        self.api_key = StringVar(value=os.environ.get(env_name, ""))
        self.model = StringVar(value=self.config.get("model", "gpt-4o-mini"))
        self.model_preset = StringVar(value=self.config.get("model", "gpt-4o-mini"))
        self.status = StringVar(value=self.startup_status_text())
        self.materials_status = StringVar(value="")
        self.auto_submit = BooleanVar(value=bool(self.config.get("auto_submit_after_confirm", True)))
        self.auto_loop_max = StringVar(value=str(self.config.get("auto_loop_max_count", 20)))
        self.auto_loop_delay = StringVar(value=str(self.config.get("auto_loop_delay_seconds", 1.5)))
        self.auto_loop_pause_on_recheck = BooleanVar(value=bool(self.config.get("auto_loop_pause_on_recheck", True)))
        self.presentation_override = StringVar(value=self.config.get("presentation_override", "自动"))
        self.submit_mode = StringVar(value=self.config.get("submit_mode", SUBMIT_MODE_BUTTON))
        if self.submit_mode.get() not in SUBMIT_MODES:
            self.submit_mode.set(SUBMIT_MODE_BUTTON)
        self.single_output_mode = StringVar(value=self.config.get("single_output_mode", OUTPUT_MODE_STANDARD))
        if self.single_output_mode.get() not in OUTPUT_MODES:
            self.single_output_mode.set(OUTPUT_MODE_STANDARD)
        self.auto_output_mode = StringVar(value=self.config.get("auto_output_mode", OUTPUT_MODE_FAST))
        if self.auto_output_mode.get() not in OUTPUT_MODES:
            self.auto_output_mode.set(OUTPUT_MODE_FAST)
        self.support_material_paths = list(self.config.get("support_material_paths", []))
        self.task_started_at = None
        self.last_result = None
        self.active_scroll_canvas = None
        self.compact_ui = None
        self.auto_loop_stop = threading.Event()
        self.auto_loop_running = False
        self.daily_whisper = DAILY_WHISPERS[int(time.strftime("%j")) % len(DAILY_WHISPERS)]
        LOG_DIR.mkdir(exist_ok=True)
        self.log_path = LOG_DIR / f"marking_{time.strftime('%Y%m%d')}.log"
        self.cleanup_old_logs()
        self.trim_log_file()

        self.build_ui()
        self.refresh_config_labels()

    def startup_status_text(self):
        essay_ready = bool(self.config.get("essay_region"))
        if self.config.get("submit_mode") == SUBMIT_MODE_INPUT:
            score_ready = bool(self.config.get("score_input"))
        else:
            score_ready = bool(self.config.get("score_grid"))
        submit_ready = bool(self.config.get("submit_button"))
        if essay_ready and score_ready and submit_ready:
            return "今日准备完成，可以直接开始阅卷。"
        if essay_ready and score_ready:
            return "作文区域和提交位置已校准；建议记录提交按钮后开始。"
        if essay_ready:
            return "已校准作文区域；还需要校准分数网格或分数输入框。"
        return "首次使用建议先完成校准。"

    def build_ui(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root.geometry("860x900")
        self.root.minsize(360, 280)
        self.root.resizable(True, True)

        self.ui_bg = "#FDF8F3"
        self.ui_card = "#FFFFFF"
        self.ui_ink = "#2F3747"
        self.ui_muted = "#6F7285"
        self.ui_button_text = "#3F4658"
        self.ui_line = "#ECDDD7"
        self.ui_cream = "#FFFDF8"
        self.ui_primary = "#F8C8DC"
        self.ui_primary_hover = "#F3B6D0"
        self.ui_success = "#B9DEC9"
        self.ui_success_hover = "#A8D2BB"
        self.ui_auto = "#D8CCFF"
        self.ui_auto_hover = "#C8B9F2"
        self.ui_danger = "#F3A7A4"
        self.ui_danger_hover = "#EA928E"
        self.ui_secondary = "#F7F4F1"
        self.ui_secondary_hover = "#EFE8E2"
        self.ui_info = "#CFE3FF"
        self.ui_info_hover = "#BDD6FA"
        self.ui_font = ("Microsoft YaHei UI", 15)
        self.ui_font_small = ("Microsoft YaHei UI", 13)
        self.ui_font_title = ("Microsoft YaHei UI", 22, "bold")
        self.ui_font_card = ("Microsoft YaHei UI", 17, "bold")
        self.ui_button_font = ("Microsoft YaHei UI", 15)
        self.ui_button_font_compact = ("Microsoft YaHei UI", 13)
        self.space_page_x = 18
        self.space_page_y = 10
        self.space_card_x = 8
        self.space_card_y = 6
        self.space_card_inner_x = 14
        self.space_card_inner_y = 10
        self.space_control_y = 6
        self.space_compact_x = 4
        self.space_compact_y = 3
        self.ui_button_height = 46
        self.ui_button_height_prominent = 52
        self.ui_button_radius = 22
        self.ui_button_radius_compact = 18
        self.button_roles = {
            "primary": (self.ui_primary, self.ui_primary_hover),
            "success": (self.ui_success, self.ui_success_hover),
            "auto": (self.ui_auto, self.ui_auto_hover),
            "danger": (self.ui_danger, self.ui_danger_hover),
            "secondary": (self.ui_secondary, self.ui_secondary_hover),
            "info": (self.ui_info, self.ui_info_hover),
        }
        self.responsive_cards = []
        self.responsive_card_titles = []
        self.responsive_card_subtitles = []
        self.responsive_buttons = []

        self.root.configure(fg_color=self.ui_bg)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        def make_card(parent, title=None, subtitle=None):
            frame = ctk.CTkFrame(
                parent,
                fg_color=self.ui_card,
                corner_radius=24,
                border_width=1,
                border_color=self.ui_line,
            )
            frame.pack(fill="x", padx=self.space_card_x, pady=self.space_card_y)
            self.responsive_cards.append(frame)
            self.bind_scroll_activation(frame)
            if title:
                title_label = ctk.CTkLabel(
                    frame,
                    text=title,
                    text_color=self.ui_ink,
                    font=self.ui_font_card,
                    anchor="w",
                )
                title_label.pack(fill="x", padx=self.space_card_inner_x, pady=(self.space_card_inner_y, 2))
                self.responsive_card_titles.append(title_label)
            if subtitle:
                subtitle_label = ctk.CTkLabel(
                    frame,
                    text=subtitle,
                    text_color=self.ui_muted,
                    font=self.ui_font_small,
                    anchor="w",
                    justify="left",
                    wraplength=700,
                )
                subtitle_label.pack(fill="x", padx=self.space_card_inner_x, pady=(0, self.space_control_y))
                self.responsive_card_subtitles.append(subtitle_label)
            return frame

        def field(parent, label, widget):
            ctk.CTkLabel(
                parent,
                text=label,
                text_color=self.ui_muted,
                font=self.ui_font_small,
                anchor="w",
            ).pack(fill="x", padx=self.space_card_inner_x, pady=(self.space_control_y, 3))
            widget.pack(fill="x", padx=self.space_card_inner_x, pady=(0, self.space_control_y))
            self.bind_scroll_activation(widget)
            return widget

        def button_colors(role):
            return self.button_roles.get(role, self.button_roles["secondary"])

        def bind_button_press_feedback(button, role, height):
            color, hover = button_colors(role)
            button._springpaper_role = role
            button._springpaper_height = height

            def on_press(_event):
                normal_height = getattr(button, "_springpaper_height", height)
                button.configure(height=max(30, normal_height - 1), border_width=1, border_color=self.ui_line, fg_color=hover)

            def on_release(_event):
                normal_height = getattr(button, "_springpaper_height", height)
                normal_color, _normal_hover = button_colors(getattr(button, "_springpaper_role", role))
                button.configure(height=normal_height, border_width=0, fg_color=normal_color)

            button.bind("<ButtonPress-1>", on_press, add="+")
            button.bind("<ButtonRelease-1>", on_release, add="+")
            button.bind("<Leave>", on_release, add="+")

        def soft_button(parent, text, command, role="secondary", text_color=None, pady=(8, 8), height=None):
            color, hover = button_colors(role)
            height = height or self.ui_button_height
            text_color = text_color or self.ui_button_text
            button = ctk.CTkButton(
                parent,
                text=text,
                command=command,
                height=height,
                corner_radius=self.ui_button_radius,
                fg_color=color,
                hover_color=hover,
                border_width=0,
                border_color=self.ui_line,
                text_color=text_color,
                font=self.ui_button_font,
                cursor="hand2",
            )
            button.pack(fill="x", padx=self.space_card_inner_x, pady=pady)
            self.responsive_buttons.append((button, height, pady, role))
            bind_button_press_feedback(button, role, height)
            self.bind_scroll_activation(button)
            return button

        def small_button(parent, text, command, role="secondary", width=82):
            color, hover = button_colors(role)
            button = ctk.CTkButton(
                parent,
                text=text,
                command=command,
                width=width,
                height=26,
                corner_radius=13,
                fg_color=color,
                hover_color=hover,
                border_width=0,
                border_color=self.ui_line,
                text_color=self.ui_button_text,
                font=self.ui_font_small,
                cursor="hand2",
            )
            bind_button_press_feedback(button, role, 26)
            return button

        self.header_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=self.space_page_x, pady=(8, 2))
        self.header_frame.grid_columnconfigure(0, weight=1)
        self.header_text_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_text_frame.grid(row=0, column=0, sticky="ew")
        self.title_label = ctk.CTkLabel(
            self.header_text_frame,
            text=f"{PRODUCT_NAME_CN} {PRODUCT_NAME_EN}",
            text_color=self.ui_ink,
            font=("Microsoft YaHei UI", 18, "bold"),
            anchor="w",
        )
        self.title_label.pack(fill="x")
        self.product_label = ctk.CTkLabel(
            self.header_text_frame,
            text=BRAND_TAGLINE,
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 12),
            anchor="w",
        )
        self.product_label.pack(fill="x", pady=(1, 0))
        self.tagline_label = ctk.CTkLabel(
            self.header_text_frame,
            text="",
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 13),
            anchor="w",
        )
        self.greeting_label = ctk.CTkLabel(
            self.header_text_frame,
            text="",
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 15),
            anchor="w",
        )
        self.about_button = small_button(self.header_frame, "关于", self.show_about, role="secondary", width=58)
        self.about_button.grid(row=0, column=1, sticky="ne", padx=(12, 0), pady=(2, 0))

        self.status_card = ctk.CTkFrame(
            self.root,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        self.status_card.grid(row=2, column=0, sticky="ew", padx=self.space_page_x, pady=(0, 6))
        self.status_card.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(
            self.status_card,
            textvariable=self.status,
            text_color=self.ui_ink,
            font=("Microsoft YaHei UI", 12),
            anchor="w",
            justify="left",
            wraplength=780,
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(2, 12), pady=2)
        self.daily_label = ctk.CTkLabel(
            self.status_card,
            text=self.daily_whisper,
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 12),
            anchor="e",
        )
        self.daily_label.grid(row=0, column=1, sticky="e", padx=(8, 2), pady=2)

        self.notebook = ctk.CTkTabview(
            self.root,
            fg_color=self.ui_bg,
            segmented_button_fg_color="#F8F2ED",
            segmented_button_selected_color=self.ui_primary,
            segmented_button_selected_hover_color=self.ui_primary_hover,
            segmented_button_unselected_color="#FFFDF8",
            segmented_button_unselected_hover_color=self.ui_secondary_hover,
            text_color=self.ui_ink,
            corner_radius=26,
            border_width=0,
            border_color=self.ui_line,
        )
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=self.space_page_x, pady=(2, self.space_page_y))
        self.notebook.add(TAB_MARKING)
        self.notebook.add(TAB_STANDARD)
        self.notebook.add(TAB_CALIBRATION)
        self.notebook.add(TAB_LOG)

        marking_tab = ctk.CTkScrollableFrame(self.notebook.tab(TAB_MARKING), fg_color="transparent", corner_radius=0)
        settings_tab = ctk.CTkScrollableFrame(self.notebook.tab(TAB_STANDARD), fg_color="transparent", corner_radius=0)
        calibrate_tab = ctk.CTkScrollableFrame(self.notebook.tab(TAB_CALIBRATION), fg_color="transparent", corner_radius=0)
        log_tab = ctk.CTkFrame(self.notebook.tab(TAB_LOG), fg_color="transparent")
        marking_tab.pack(fill="both", expand=True, padx=2, pady=2)
        settings_tab.pack(fill="both", expand=True, padx=2, pady=2)
        calibrate_tab.pack(fill="both", expand=True, padx=2, pady=2)
        log_tab.pack(fill="both", expand=True, padx=2, pady=2)
        for scroll_frame in (marking_tab, settings_tab, calibrate_tab):
            self.bind_scroll_activation(scroll_frame, scroll_frame)
        self.root.bind_all("<MouseWheel>", self.on_mousewheel, add="+")

        action_card = make_card(marking_tab, "阅卷操作", "先单篇试跑，稳定后再开自动连评。")
        soft_button(action_card, "截图并评分", self.score_current_essay, role="primary", height=self.ui_button_height_prominent)
        soft_button(action_card, "采纳并提交", self.accept_and_submit, role="success", height=self.ui_button_height_prominent)

        loop_card = make_card(marking_tab, "自动连评", "像温柔的小助手一样一篇篇往前走；遇到疑问会停下来等你。")
        loop_row = ctk.CTkFrame(loop_card, fg_color="transparent")
        loop_row.pack(fill="x", padx=self.space_card_inner_x, pady=(2, self.space_card_inner_y))
        loop_row.grid_columnconfigure(1, weight=1)
        loop_row.grid_columnconfigure(3, weight=1)
        self.bind_scroll_activation(loop_row)
        self.loop_max_label = ctk.CTkLabel(loop_row, text="最多连评", text_color=self.ui_muted, font=self.ui_font)
        self.loop_max_label.grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=6
        )
        self.loop_max_entry = ctk.CTkEntry(
            loop_row,
            textvariable=self.auto_loop_max,
            height=38,
            corner_radius=18,
            fg_color=self.ui_cream,
            border_color="#F2D6CC",
            text_color=self.ui_ink,
            font=self.ui_font,
        )
        self.loop_max_entry.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=6)
        self.loop_delay_label = ctk.CTkLabel(loop_row, text="提交等待", text_color=self.ui_muted, font=self.ui_font)
        self.loop_delay_label.grid(
            row=0, column=2, sticky="w", padx=(0, 10), pady=6
        )
        self.loop_delay_entry = ctk.CTkEntry(
            loop_row,
            textvariable=self.auto_loop_delay,
            height=38,
            corner_radius=18,
            fg_color=self.ui_cream,
            border_color="#F2D6CC",
            text_color=self.ui_ink,
            font=self.ui_font,
        )
        self.loop_delay_entry.grid(row=0, column=3, sticky="ew", pady=6)
        ctk.CTkCheckBox(
            loop_card,
            text="遇到低置信/疑问卷时自动暂停",
            variable=self.auto_loop_pause_on_recheck,
            command=self.save_config,
            fg_color=self.ui_primary,
            hover_color=self.ui_primary_hover,
            border_color="#E9B8C9",
            text_color=self.ui_ink,
            font=self.ui_font_small,
            corner_radius=8,
        ).pack(anchor="w", padx=self.space_card_inner_x, pady=(0, self.space_card_inner_y))
        soft_button(loop_card, "开始自动连评", self.start_auto_loop, role="auto", height=self.ui_button_height_prominent)
        soft_button(loop_card, "停止自动连评", self.stop_auto_loop, role="danger", height=self.ui_button_height_prominent)

        review_card = make_card(marking_tab, "人工接管", "你永远拥有最后判断权。")
        field(
            review_card,
            "卷面判断",
            ctk.CTkOptionMenu(
                review_card,
                variable=self.presentation_override,
                values=PRESENTATION_LEVELS,
                command=lambda _: self.save_config(),
                height=40,
                corner_radius=18,
                fg_color=self.ui_secondary,
                button_color=self.ui_secondary_hover,
                button_hover_color="#E5DDD6",
                text_color=self.ui_ink,
                font=self.ui_font,
            ),
        )
        field(
            review_card,
            "提交方式",
            ctk.CTkOptionMenu(
                review_card,
                variable=self.submit_mode,
                values=SUBMIT_MODES,
                command=lambda _: self.save_config(),
                height=40,
                corner_radius=18,
                fg_color=self.ui_secondary,
                button_color=self.ui_secondary_hover,
                button_hover_color="#E5DDD6",
                text_color=self.ui_ink,
                font=self.ui_font,
            ),
        )
        ctk.CTkCheckBox(
            review_card,
            text="确认后自动点击提交分数",
            variable=self.auto_submit,
            command=self.save_config,
            fg_color=self.ui_success,
            hover_color=self.ui_success_hover,
            border_color="#A4DCC8",
            text_color=self.ui_ink,
            font=self.ui_font_small,
            corner_radius=8,
        ).pack(anchor="w", padx=self.space_card_inner_x, pady=(4, self.space_card_inner_y))

        model_card = make_card(settings_tab, "AI 模型", "模型是笔，标准是尺；先测连通，再放心阅卷。")
        field(
            model_card,
            "API 供应商",
            ctk.CTkOptionMenu(
                model_card,
                variable=self.provider,
                values=list(PROVIDERS.keys()),
                command=lambda _: self.apply_provider_defaults(),
                height=40,
                corner_radius=18,
                fg_color=self.ui_secondary,
                button_color=self.ui_secondary_hover,
                button_hover_color="#E5DDD6",
                text_color=self.ui_ink,
                font=self.ui_font,
            ),
        )
        field(model_card, "模型名称", self.soft_entry(model_card, self.model))
        field(
            model_card,
            "快速选择模型",
            ctk.CTkOptionMenu(
                model_card,
                variable=self.model_preset,
                values=MODEL_PRESETS,
                command=lambda value: self.apply_model_preset(value),
                height=40,
                corner_radius=18,
                fg_color=self.ui_secondary,
                button_color=self.ui_secondary_hover,
                button_hover_color="#E5DDD6",
                text_color=self.ui_ink,
                font=("Microsoft YaHei UI", 13),
                dropdown_font=("Microsoft YaHei UI", 12),
            ),
        )
        soft_button(model_card, "测试 API 连接", self.test_api_connection)
        soft_button(model_card, "测试视觉输入", self.test_vision_connection)
        soft_button(model_card, "列出可用模型", self.list_available_models)

        strategy_card = make_card(settings_tab, "AI 输出模式", "单篇要有一句理由，连评只要分数；少说一点，阅卷就快一点。")
        field(
            strategy_card,
            "单篇试评",
            ctk.CTkOptionMenu(
                strategy_card,
                variable=self.single_output_mode,
                values=OUTPUT_MODES,
                command=lambda _: self.save_config(),
                height=40,
                corner_radius=18,
                fg_color=self.ui_secondary,
                button_color=self.ui_secondary_hover,
                button_hover_color="#E5DDD6",
                text_color=self.ui_ink,
                font=self.ui_font,
            ),
        )
        field(
            strategy_card,
            "自动连评",
            ctk.CTkOptionMenu(
                strategy_card,
                variable=self.auto_output_mode,
                values=OUTPUT_MODES,
                command=lambda _: self.save_config(),
                height=40,
                corner_radius=18,
                fg_color=self.ui_secondary,
                button_color=self.ui_secondary_hover,
                button_hover_color="#E5DDD6",
                text_color=self.ui_ink,
                font=self.ui_font,
            ),
        )

        api_card = make_card(settings_tab, "接口设置")
        field(api_card, "Base URL（OpenAI 官方可留空）", self.soft_entry(api_card, self.base_url))
        field(api_card, "API Key 环境变量名", self.soft_entry(api_card, self.api_key_env))
        field(api_card, "API Key（可留空使用环境变量）", self.soft_entry(api_card, self.api_key, show="*"))

        material_card = make_card(settings_tab, "题目与评分标准", "把题目、评分标准和你的尺度放在这里，AI 才知道要如何温柔而准确地判断。")
        self.extra_prompt = ctk.CTkTextbox(
            material_card,
            height=210,
            wrap="word",
            fg_color=self.ui_cream,
            text_color=self.ui_ink,
            border_color="#F2D6CC",
            border_width=1,
            corner_radius=20,
            font=("Microsoft YaHei UI", 14),
        )
        self.extra_prompt.pack(fill="both", expand=True, padx=self.space_card_inner_x, pady=(2, self.space_card_inner_y))
        self.extra_prompt.insert("end", self.config.get("extra_prompt", ""))
        self.bind_textbox_wheel(self.extra_prompt)
        self.bind_scroll_activation(self.extra_prompt, settings_tab)
        soft_button(material_card, "添加材料图片", self.add_support_materials)
        soft_button(material_card, "清空材料图片", self.clear_support_materials)
        ctk.CTkLabel(
            material_card,
            textvariable=self.materials_status,
            text_color=self.ui_muted,
            font=self.ui_font_small,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=self.space_card_inner_x, pady=(0, self.space_card_inner_y))

        calibrate_card = make_card(
            calibrate_tab,
            "页面校准",
            "这些坐标通常只需要校准一次；浏览器缩放或页面布局变化后再重做。",
        )
        soft_button(calibrate_card, "校准作文区域", self.calibrate_essay_region)
        soft_button(calibrate_card, "校准分数网格", self.calibrate_score_grid)
        soft_button(calibrate_card, "校准分数输入框", self.record_score_input)
        soft_button(calibrate_card, "记录提交按钮", self.record_submit_button)
        soft_button(calibrate_card, "测试提交按钮", self.click_submit_only)

        info_card = make_card(calibrate_tab, "当前配置")
        self.config_label = ctk.CTkLabel(
            info_card,
            text="",
            text_color=self.ui_ink,
            font=("Microsoft YaHei UI", 13),
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self.config_label.pack(fill="x", padx=self.space_card_inner_x, pady=(0, self.space_card_inner_y))

        log_tab.grid_columnconfigure(0, weight=1)
        log_tab.grid_rowconfigure(1, weight=1)
        log_toolbar = ctk.CTkFrame(log_tab, fg_color="transparent")
        log_toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(2, 3))
        log_toolbar.grid_columnconfigure(0, weight=1)
        log_action_row = ctk.CTkFrame(log_toolbar, fg_color="transparent")
        log_action_row.grid(row=0, column=0, sticky="ew")
        log_action_row.grid_columnconfigure((0, 1), weight=1)
        small_button(log_action_row, "采纳提交", self.accept_and_submit, role="success", width=82).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        small_button(log_action_row, "继续连评", self.start_auto_loop, role="auto", width=82).grid(row=0, column=1, sticky="ew", padx=(5, 5))
        small_button(log_action_row, "停止", self.stop_auto_loop, role="danger", width=56).grid(row=0, column=2, sticky="ew", padx=(5, 0))

        log_utility_row = ctk.CTkFrame(log_toolbar, fg_color="transparent")
        log_utility_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        log_utility_row.grid_columnconfigure((0, 1), weight=1)
        small_button(log_utility_row, "复制可见记录", self.copy_log, width=104).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        small_button(log_utility_row, "清空界面", self.clear_log, width=82).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.output = ctk.CTkTextbox(
            log_tab,
            wrap="word",
            fg_color="#FFFDF8",
            text_color=self.ui_ink,
            border_color="#F2D6CC",
            border_width=1,
            corner_radius=18,
            font=("Microsoft YaHei UI", 12),
        )
        self.output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.bind_textbox_wheel(self.output)
        self.output.insert("end", f"轻量日志：界面只显示最近 10000 字，本地日志自动保留 {LOG_RETENTION_DAYS} 天。\n")
        self.root.bind("<Configure>", self.on_root_resize, add="+")
        self.apply_responsive_layout(force=True)

    def show_about(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(f"关于 {PRODUCT_NAME_CN}")
        dialog.geometry("360x300")
        dialog.resizable(False, False)
        dialog.configure(fg_color=self.ui_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        card = ctk.CTkFrame(
            dialog,
            fg_color=self.ui_card,
            corner_radius=24,
            border_width=1,
            border_color=self.ui_line,
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            card,
            text=PRODUCT_NAME_CN,
            text_color=self.ui_ink,
            font=("Microsoft YaHei UI", 28, "bold"),
        ).pack(pady=(26, 2))
        ctk.CTkLabel(
            card,
            text=PRODUCT_NAME_EN,
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 16),
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            card,
            text=f"Version {APP_VERSION}",
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 13),
        ).pack(pady=(0, 16))

        ctk.CTkFrame(card, height=1, fg_color=self.ui_line).pack(fill="x", padx=42, pady=(0, 18))

        ctk.CTkLabel(
            card,
            text=BRAND_TAGLINE,
            text_color=self.ui_ink,
            font=("Microsoft YaHei UI", 14),
            wraplength=280,
        ).pack(pady=(0, 16))
        ctk.CTkLabel(
            card,
            text="© 2026",
            text_color=self.ui_muted,
            font=("Microsoft YaHei UI", 12),
        ).pack()

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")

    def soft_entry(self, parent, textvariable, show=None):
        return ctk.CTkEntry(
            parent,
            textvariable=textvariable,
            show=show,
            height=42,
            corner_radius=20,
            fg_color=self.ui_cream,
            border_color="#F2D6CC",
            border_width=1,
            text_color=self.ui_ink,
            font=self.ui_font,
        )

    def copy_log(self):
        if not hasattr(self, "output"):
            return
        text = self.output.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("当前可见阅卷记录已复制到剪贴板。")

    def clear_log(self):
        if not hasattr(self, "output"):
            return
        self.output.delete("1.0", "end")
        message = "界面记录已清空，本地短期日志会自动管理。\n"
        self.output.insert("end", message)
        self.append_log_file(f"\n[{time.strftime('%H:%M:%S')}] 界面记录已清空。\n")
        self.status.set("界面记录已清空。")

    def append_log_file(self, text):
        try:
            LOG_DIR.mkdir(exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as file:
                file.write(text)
            self.trim_log_file()
        except Exception:
            pass

    def trim_log_file(self):
        try:
            if not hasattr(self, "log_path") or not self.log_path.exists():
                return
            if self.log_path.stat().st_size <= LOG_FILE_MAX_BYTES:
                return
            data = self.log_path.read_bytes()[-LOG_FILE_MAX_BYTES:]
            line_start = data.find(b"\n")
            if line_start >= 0:
                data = data[line_start + 1 :]
            self.log_path.write_bytes(data)
        except Exception:
            pass

    def cleanup_old_logs(self):
        try:
            cutoff = time.time() - LOG_RETENTION_DAYS * 24 * 60 * 60
            for path in LOG_DIR.glob("marking_*.log"):
                if path.stat().st_mtime < cutoff:
                    path.unlink()
        except Exception:
            pass

    def trim_visible_log(self):
        if not hasattr(self, "output"):
            return
        try:
            text = self.output.get("1.0", "end-1c")
            overflow = len(text) - VISIBLE_LOG_MAX_CHARS
            if overflow <= 0:
                return
            self.output.delete("1.0", f"1.0+{overflow}c")
            self.output.insert("1.0", "… 更早的界面记录已折叠，本地短期日志会自动保留。\n")
        except Exception:
            pass

    def on_root_resize(self, event):
        if event.widget is self.root:
            self.apply_responsive_layout()

    def apply_responsive_layout(self, force=False):
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        compact = width < 1500 or height < 1500
        if not force and compact == self.compact_ui:
            return
        self.compact_ui = compact

        if compact:
            self.header_frame.grid_configure(padx=10, pady=(4, 0))
            self.title_label.configure(text=PRODUCT_NAME_CN)
            self.title_label.configure(font=("Microsoft YaHei UI", 14, "bold"))
            self.about_button._springpaper_height = 24
            self.about_button.configure(width=48, height=24, corner_radius=12, font=("Microsoft YaHei UI", 11))
            self.product_label.pack_forget()
            self.tagline_label.pack_forget()
            self.greeting_label.pack_forget()
            self.status_card.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 3))
            self.daily_label.grid_remove()
            self.status_label.configure(font=("Microsoft YaHei UI", 11), wraplength=max(240, width - 28))
            self.notebook.grid_configure(padx=self.space_compact_x, pady=(1, self.space_compact_y))
            self.notebook.configure(corner_radius=18)
            for card in self.responsive_cards:
                card.configure(corner_radius=14, fg_color="transparent", border_width=0)
                card.pack_configure(padx=self.space_compact_x, pady=self.space_compact_y)
            for title in self.responsive_card_titles:
                title.configure(font=("Microsoft YaHei UI", 13, "bold"))
                title.pack_configure(padx=10, pady=(4, 0))
            for subtitle in self.responsive_card_subtitles:
                if not hasattr(subtitle, "_full_text"):
                    subtitle._full_text = subtitle.cget("text")
                subtitle.configure(text="", font=("Microsoft YaHei UI", 1))
                subtitle.pack_configure(padx=10, pady=0)
            for button, _height, _pady, _role in self.responsive_buttons:
                button._springpaper_height = 36
                button.configure(height=36, corner_radius=self.ui_button_radius_compact, font=self.ui_button_font_compact)
                button.pack_configure(padx=10, pady=(3, 3))
            self.apply_loop_row_layout(compact=True)
        else:
            self.header_frame.grid_configure(padx=self.space_page_x, pady=(8, 2))
            self.title_label.configure(text=f"{PRODUCT_NAME_CN} {PRODUCT_NAME_EN}", font=("Microsoft YaHei UI", 18, "bold"))
            self.about_button._springpaper_height = 26
            self.about_button.configure(width=58, height=26, corner_radius=13, font=self.ui_font_small)
            if not self.product_label.winfo_ismapped():
                self.product_label.pack(fill="x", pady=(1, 0), after=self.title_label)
            self.tagline_label.pack_forget()
            self.greeting_label.pack_forget()
            self.status_card.grid(row=2, column=0, sticky="ew", padx=self.space_page_x, pady=(0, 6))
            if not self.daily_label.winfo_ismapped():
                self.daily_label.grid(row=0, column=1, sticky="e", padx=(8, 2), pady=2)
            self.status_label.configure(font=("Microsoft YaHei UI", 12), wraplength=max(360, width - 260))
            self.notebook.grid_configure(padx=self.space_page_x, pady=(2, self.space_page_y))
            self.notebook.configure(corner_radius=26)
            for card in self.responsive_cards:
                card.configure(corner_radius=24, fg_color=self.ui_card, border_width=1)
                card.pack_configure(padx=self.space_card_x, pady=self.space_card_y)
            for title in self.responsive_card_titles:
                title.configure(font=self.ui_font_card)
                title.pack_configure(padx=self.space_card_inner_x, pady=(self.space_card_inner_y, 2))
            for subtitle in self.responsive_card_subtitles:
                subtitle.configure(text=getattr(subtitle, "_full_text", subtitle.cget("text")), font=self.ui_font_small)
                subtitle.pack_configure(padx=self.space_card_inner_x, pady=(0, self.space_control_y))
            for button, height, pady, _role in self.responsive_buttons:
                button._springpaper_height = height
                button.configure(height=height, corner_radius=self.ui_button_radius, font=self.ui_button_font)
                button.pack_configure(padx=self.space_card_inner_x, pady=pady)
            self.apply_loop_row_layout(compact=False)

    def apply_loop_row_layout(self, compact):
        if not all(hasattr(self, name) for name in ("loop_max_label", "loop_max_entry", "loop_delay_label", "loop_delay_entry")):
            return
        if compact:
            self.loop_max_label.grid_configure(row=0, column=0, sticky="w", padx=(0, 8), pady=(3, 3))
            self.loop_max_entry.grid_configure(row=0, column=1, sticky="ew", padx=0, pady=(3, 3))
            self.loop_delay_label.grid_configure(row=1, column=0, sticky="w", padx=(0, 8), pady=(3, 3))
            self.loop_delay_entry.grid_configure(row=1, column=1, sticky="ew", padx=0, pady=(3, 3))
            self.loop_max_label.configure(font=("Microsoft YaHei UI", 13))
            self.loop_delay_label.configure(font=("Microsoft YaHei UI", 13))
            self.loop_max_entry.configure(height=34, font=("Microsoft YaHei UI", 13))
            self.loop_delay_entry.configure(height=34, font=("Microsoft YaHei UI", 13))
        else:
            self.loop_max_label.grid_configure(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
            self.loop_max_entry.grid_configure(row=0, column=1, sticky="ew", padx=(0, 18), pady=6)
            self.loop_delay_label.grid_configure(row=0, column=2, sticky="w", padx=(0, 10), pady=6)
            self.loop_delay_entry.grid_configure(row=0, column=3, sticky="ew", padx=0, pady=6)
            self.loop_max_label.configure(font=self.ui_font)
            self.loop_delay_label.configure(font=self.ui_font)
            self.loop_max_entry.configure(height=38, font=self.ui_font)
            self.loop_delay_entry.configure(height=38, font=self.ui_font)

    def bind_scroll_activation(self, widget, scroll_frame=None):
        target = scroll_frame or self.find_scroll_parent(widget)
        try:
            widget.bind("<Enter>", lambda event, t=target: self.set_active_scroll_canvas(t), add="+")
            widget.bind("<MouseWheel>", self.on_mousewheel, add="+")
        except Exception:
            pass

    def bind_textbox_wheel(self, textbox):
        try:
            textbox.bind("<MouseWheel>", self.on_textbox_mousewheel, add="+")
            inner = getattr(textbox, "_textbox", None)
            if inner is not None:
                inner.bind("<MouseWheel>", self.on_textbox_mousewheel, add="+")
        except Exception:
            pass

    def on_textbox_mousewheel(self, event):
        if event.state & 0x0004:
            return None
        widget = event.widget
        delta = getattr(event, "delta", 0)
        if not delta:
            return None
        units = int(round(-delta / 120 * TEXTBOX_SCROLL_UNITS_PER_NOTCH))
        if units == 0:
            units = -1 if delta > 0 else 1
        try:
            widget.yview_scroll(units, "units")
        except Exception:
            textbox = getattr(widget, "master", None)
            if hasattr(textbox, "yview_scroll"):
                textbox.yview_scroll(units, "units")
        return "break"

    def find_scroll_parent(self, widget):
        current = widget
        while current is not None:
            if isinstance(current, ctk.CTkScrollableFrame):
                return current
            current = getattr(current, "master", None)
        return None

    def find_scroll_parent_from_pointer(self):
        try:
            x, y = self.root.winfo_pointerxy()
            widget = self.root.winfo_containing(x, y)
        except Exception:
            return None
        while widget is not None:
            if isinstance(widget, ctk.CTkTextbox):
                return None
            if isinstance(widget, ctk.CTkScrollableFrame):
                return widget
            widget = getattr(widget, "master", None)
        return None

    def set_active_scroll_canvas(self, scroll_frame):
        self.active_scroll_canvas = scroll_frame

    def on_mousewheel(self, event):
        if event.state & 0x0004:
            return None
        scroll_frame = self.find_scroll_parent_from_pointer() or getattr(self, "active_scroll_canvas", None)
        canvas = getattr(scroll_frame, "_parent_canvas", None)
        if not canvas or not canvas.winfo_exists() or not canvas.winfo_ismapped():
            return None
        delta = getattr(event, "delta", 0)
        if not delta:
            return None
        units = int(round(-delta / 120 * SCROLL_UNITS_PER_NOTCH))
        if units == 0:
            units = -1 if delta > 0 else 1
        canvas.yview_scroll(units, "units")
        return "break"

    def save_config(self):
        self.config["provider"] = self.provider.get().strip() or "openai"
        self.config["base_url"] = self.base_url.get().strip()
        self.config["api_key_env"] = self.api_key_env.get().strip() or "OPENAI_API_KEY"
        self.config["model"] = self.model.get().strip() or "gpt-4o-mini"
        if hasattr(self, "extra_prompt"):
            self.config["extra_prompt"] = self.extra_prompt.get("1.0", "end").strip()
        self.config["support_material_paths"] = self.support_material_paths
        self.config["auto_submit_after_confirm"] = bool(self.auto_submit.get())
        try:
            self.config["auto_loop_max_count"] = max(1, int(self.auto_loop_max.get().strip()))
        except Exception:
            self.config["auto_loop_max_count"] = 20
        try:
            self.config["auto_loop_delay_seconds"] = max(0.5, float(self.auto_loop_delay.get().strip()))
        except Exception:
            self.config["auto_loop_delay_seconds"] = 1.5
        self.config["auto_loop_pause_on_recheck"] = bool(self.auto_loop_pause_on_recheck.get())
        self.config["presentation_override"] = self.presentation_override.get()
        submit_mode = self.submit_mode.get()
        self.config["submit_mode"] = submit_mode if submit_mode in SUBMIT_MODES else SUBMIT_MODE_BUTTON
        single_output_mode = self.single_output_mode.get()
        auto_output_mode = self.auto_output_mode.get()
        self.config["single_output_mode"] = (
            single_output_mode if single_output_mode in OUTPUT_MODES else OUTPUT_MODE_STANDARD
        )
        self.config["auto_output_mode"] = auto_output_mode if auto_output_mode in OUTPUT_MODES else OUTPUT_MODE_FAST
        save_json(CONFIG_PATH, self.config)
        self.refresh_config_labels()

    def apply_provider_defaults(self):
        provider = self.provider.get().strip()
        profile = PROVIDERS.get(provider, PROVIDERS["openai"])
        self.base_url.set(profile["base_url"])
        self.model.set(profile["model"])
        self.model_preset.set(profile["model"])
        self.api_key_env.set(profile["api_key_env"])
        self.api_key.set(os.environ.get(profile["api_key_env"], ""))
        self.status.set(profile["note"])
        self.save_config()

    def apply_model_preset(self, value):
        self.model.set(value)
        self.status.set(f"已切换模型：{value}")
        self.save_config()

    def refresh_config_labels(self):
        essay = self.config.get("essay_region")
        grid = self.config.get("score_grid")
        score_input = self.config.get("score_input")
        submit = self.config.get("submit_button")
        provider = self.config.get("provider", "openai")
        note = PROVIDERS.get(provider, PROVIDERS["custom"])["note"]
        self.materials_status.set(
            "已添加材料图片："
            + (str(len(self.support_material_paths)) + " 张" if self.support_material_paths else "0 张")
        )
        lines = [
            f"供应商：{provider} | 模型：{self.config.get('model', '')}",
            f"Base URL：{self.config.get('base_url') or 'OpenAI 默认'}",
            f"提示：{note}",
            f"作文区域：{essay if essay else '未校准'}",
            f"分数网格：{grid if grid else '未校准'}",
            f"分数输入框：{score_input if score_input else '未记录'}",
            f"网页提交分数按钮：{submit if submit else '未记录'}",
            f"提交方式：{self.submit_mode.get()}",
            f"单篇输出：{self.single_output_mode.get()}",
            f"连评输出：{self.auto_output_mode.get()}",
            f"人工卷面判断：{self.presentation_override.get()}",
        ]
        self.config_label.configure(text="\n".join(lines))

    def apply_presentation_override(self, score):
        level = self.presentation_override.get()
        if level == "整洁":
            return score, "人工卷面判断：整洁，不调整。"
        if level == "较整洁":
            return min(score, 44), "人工卷面判断：较整洁，最高不超过44。"
        if level == "欠整洁":
            return min(score, 40), "人工卷面判断：欠整洁，最高不超过40。"
        if level == "凌乱难辨":
            return min(score, 36), "人工卷面判断：凌乱难辨，最高不超过36。"
        return score, "人工卷面判断：自动，未额外修正。"

    def result_text_for_rules(self, result):
        parts = []
        for key in [
            "band",
            "presentation_level",
            "score_adjustment",
            "reason",
            "notes",
            "manual_adjustment",
        ]:
            value = result.get(key)
            if value:
                parts.append(str(value))
        for key in ["reasons", "strengths", "weaknesses"]:
            value = result.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
        return "；".join(parts)

    def apply_auto_guardrails(self, score, result):
        text = self.result_text_for_rules(result)
        caps = []
        notes = []

        def has_any(words):
            return any(word in text for word in words)

        severe_short = has_any(["严重不足", "不足300", "低于300", "少于300", "篇幅太短", "像提纲"])
        short = severe_short or has_any(["字数不足", "不足400", "少于400", "未达600", "明显少于"])
        off_topic = has_any(["跑题", "偏题", "文不对题", "不符合题意", "套作", "抄袭"])
        very_messy = has_any(["严重难辨", "无法辨认", "字迹不清", "凌乱难辨"])
        messy = very_messy or has_any(["欠整洁", "涂改较多", "涂改明显", "潦草", "辨认吃力"])
        thin_content = has_any(["内容空泛", "内容空洞", "材料不具体", "叙事不具体", "缺乏细节", "细节不足"])

        if off_topic:
            caps.append(29)
            notes.append("疑似跑题/套作，最高按四类上限处理")
        if severe_short:
            caps.append(32)
            notes.append("篇幅或字数明显不足，建议不超过32")
        elif short:
            caps.append(35)
            notes.append("存在字数不足风险，建议不超过35")
        if very_messy:
            caps.append(36)
            notes.append("字迹或卷面严重影响辨认，建议不超过36")
        elif messy:
            caps.append(40)
            notes.append("卷面欠整洁，建议不超过40")
        if thin_content and short:
            caps.append(32)
            notes.append("字数不足且材料偏薄，建议下压到三类上段")
        elif thin_content:
            caps.append(40)
            notes.append("内容或细节偏薄，建议不自动上靠")

        if not caps:
            return score, "自动规则复核：未触发硬伤封顶。"

        adjusted = min(score, min(caps))
        if adjusted < score:
            result["recheck"] = True
            return adjusted, "自动规则复核：" + "；".join(notes)
        return score, "自动规则复核：触发提示但未低于模型原分；" + "；".join(notes)

    def add_support_materials(self):
        paths = filedialog.askopenfilenames(
            title="选择题目、参考答案或评分标准图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("所有文件", "*.*"),
            ],
        )
        if not paths:
            return
        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix in SUPPORTED_IMAGE_EXTENSIONS and path not in self.support_material_paths:
                self.support_material_paths.append(path)
        self.save_config()
        self.log(f"已添加材料图片 {len(paths)} 个；当前共 {len(self.support_material_paths)} 个。")

    def clear_support_materials(self):
        self.support_material_paths = []
        self.save_config()
        self.log("已清空题目/答案/评分标准图片。")

    def log(self, message):
        def append():
            stamp = time.strftime("%H:%M:%S")
            self.status.set(message)
            if hasattr(self, "output"):
                line = f"[{stamp}] {message}\n"
                self.output.insert("end", line)
                self.append_log_file(line)
                self.trim_visible_log()
                self.output.see("end")

        self.root.after(0, append)

    def current_client(self):
        env_name = self.api_key_env.get().strip() or "OPENAI_API_KEY"
        key = self.api_key.get().strip() or os.environ.get(env_name)
        if not key:
            raise RuntimeError(f"没有 API Key。请在输入框填写，或设置环境变量 {env_name}。")
        base_url = self.base_url.get().strip()
        return OpenAI(api_key=key, base_url=base_url or None)

    def encoded_image_data_url(self, image_path):
        path = Path(image_path)
        max_side = int(self.config.get("max_image_side", 1600))
        try:
            with Image.open(path) as image:
                image = image.convert("RGB")
                width, height = image.size
                longest = max(width, height)
                if longest > max_side:
                    scale = max_side / longest
                    image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=86, optimize=True)
                image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
                return f"data:image/jpeg;base64,{image_b64}", (width, height), image.size
        except Exception:
            image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
            return f"data:{mime_type};base64,{image_b64}", None, None

    def image_content_item(self, image_path):
        data_url, original_size, final_size = self.encoded_image_data_url(image_path)
        if original_size and final_size and original_size != final_size:
            self.log(f"已压缩图片 {Path(image_path).name}: {original_size[0]}x{original_size[1]} -> {final_size[0]}x{final_size[1]}")
        return {
            "type": "image_url",
            "image_url": {"url": data_url, "detail": "high"},
        }

    def normalized_output_mode(self, output_mode):
        return output_mode if output_mode in OUTPUT_MODES else OUTPUT_MODE_STANDARD

    def max_tokens_for_output_mode(self, output_mode):
        configured = int(self.config.get("max_output_tokens", 800))
        output_mode = self.normalized_output_mode(output_mode)
        if output_mode == OUTPUT_MODE_FAST:
            return min(configured, 120)
        if output_mode == OUTPUT_MODE_STANDARD:
            return min(configured, 240)
        return configured

    def build_scoring_messages(self, essay_image_path, output_mode=None):
        output_mode = self.normalized_output_mode(output_mode)
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        extra = self.config.get("extra_prompt", "").strip()
        if extra:
            prompt += "\n\n教师补充说明：\n" + extra
        prompt += "\n\n" + OUTPUT_MODE_PROMPTS[output_mode].strip()
        prompt += "\n\n下面先给出题目、参考答案或评分标准图片；最后一张是当前学生作文截图。"

        content = [{"type": "text", "text": prompt}]
        valid_materials = []
        for path in self.support_material_paths:
            if Path(path).exists():
                valid_materials.append(path)
                content.append({"type": "text", "text": f"材料图片：{Path(path).name}"})
                content.append(self.image_content_item(path))
        content.append({"type": "text", "text": "当前学生作文截图："})
        content.append(self.image_content_item(essay_image_path))
        return [{"role": "user", "content": content}], len(valid_materials)

    def test_api_connection(self):
        self.save_config()
        self.output.delete("1.0", "end")
        self.log("开始测试 API 连接。")
        threading.Thread(target=self._test_api_worker, daemon=True).start()

    def _test_api_worker(self):
        try:
            client = self.current_client()
            self.log("已创建客户端，正在发送一条最小文本请求。")
            response = client.chat.completions.create(
                model=self.model.get().strip() or "gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": "请只回复 JSON：{\"ok\": true, \"message\": \"connected\"}",
                    }
                ],
                temperature=0,
                max_tokens=200,
                timeout=float(self.config.get("request_timeout_seconds", 180)),
            )
            text = response.choices[0].message.content or ""
            self.log("API 文本连接成功。返回：" + text[:200])
            self.log("注意：文本连接成功不等于视觉模型一定可用；截图评分会进一步验证图片输入。")
        except Exception as exc:
            self.log("API 连接失败：" + str(exc))

    def list_available_models(self):
        self.save_config()
        self.output.delete("1.0", "end")
        self.log("正在读取当前账号可用模型列表。")
        threading.Thread(target=self._list_models_worker, daemon=True).start()

    def _list_models_worker(self):
        try:
            client = self.current_client()
            models = client.models.list()
            ids = sorted([model.id for model in models.data])
            vision_keywords = ("VL", "vl", "vision", "Vision", "glm-4v", "OCR", "ocr", "omni", "Omni")
            likely_vision = [model_id for model_id in ids if any(key in model_id for key in vision_keywords)]
            self.log(f"可用模型共 {len(ids)} 个。疑似视觉/多模态模型 {len(likely_vision)} 个：")
            recommended = [
                "Qwen/Qwen3-VL-32B-Instruct",
                "Qwen/Qwen3.5-397B-A17B",
                "Qwen/Qwen3.6-35B-A3B",
                "Qwen/Qwen3-VL-30B-A3B-Instruct",
                "Qwen/Qwen3.5-35B-A3B",
                "Qwen/Qwen3-VL-8B-Instruct",
            ]
            available_recommended = [model_id for model_id in recommended if model_id in ids]
            if available_recommended:
                self.log("推荐先试：" + available_recommended[0])
            for model_id in likely_vision[:80]:
                self.log("  " + model_id)
            if not likely_vision:
                self.log("没有从模型列表里识别到视觉模型。请到硅基流动模型广场确认账号是否开通视觉模型。")
        except Exception as exc:
            self.log("读取模型列表失败：" + str(exc))

    def test_vision_connection(self):
        self.save_config()
        self.output.delete("1.0", "end")
        self.log("开始测试视觉输入。")
        threading.Thread(target=self._test_vision_worker, daemon=True).start()

    def _test_vision_worker(self):
        try:
            image_path = self.capture_essay()
            client = self.current_client()
            self.log("正在发送一张作文截图测试模型是否支持图片输入。")
            image_item = self.image_content_item(image_path)
            Path(image_path).unlink(missing_ok=True)
            response = client.chat.completions.create(
                model=self.model.get().strip() or "gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "这是一次视觉输入连通性测试，不要评分。"
                                    "请观察图片中的手写作文，必须摘录你实际看见的 3-8 个中文词语或短句。"
                                    "如果看不清，就如实说明。请只返回严格 JSON，不要输出 Markdown："
                                    "{"
                                    "\"vision_ok\": true或false, "
                                    "\"readable\": true或false, "
                                    "\"visible_text_samples\": [\"从图片中实际看见的词句1\", \"词句2\", \"词句3\"], "
                                    "\"image_quality\": \"clear/medium/poor\", "
                                    "\"message\": \"简短说明\""
                                    "}"
                                ),
                            },
                            image_item,
                        ],
                    }
                ],
                temperature=0,
                max_tokens=400,
                timeout=float(self.config.get("request_timeout_seconds", 180)),
            )
            text = response.choices[0].message.content or ""
            self.log("视觉输入测试完成。返回：" + text[:800])
            try:
                result = extract_json(text)
                samples = result.get("visible_text_samples") or []
                if result.get("vision_ok") and result.get("readable") and len(samples) >= 3:
                    self.log("视觉测试通过：模型返回了可见文字样本。")
                else:
                    self.log("视觉测试不充分：模型未返回足够的可见文字样本，建议换模型或缩小/重校准作文区域。")
            except Exception as parse_exc:
                self.log("视觉测试返回无法解析为 JSON：" + str(parse_exc))
        except Exception as exc:
            self.log("视觉输入测试失败：" + str(exc))

    def calibrate_essay_region(self):
        self.root.withdraw()
        self.root.after(
            300,
            lambda: RegionSelector(self.root, "校准作文区域", self.set_essay_region),
        )

    def set_essay_region(self, rect):
        self.root.deiconify()
        self.config["essay_region"] = rect
        self.save_config()
        self.status.set("作文区域已校准。")

    def calibrate_score_grid(self):
        self.root.withdraw()
        self.root.after(
            300,
            lambda: RegionSelector(self.root, "校准分数网格", self.set_score_grid),
        )

    def set_score_grid(self, rect):
        self.root.deiconify()
        self.config["score_grid"] = rect
        self.save_config()
        self.status.set("分数网格已校准。")

    def record_score_input(self):
        self.status.set("请在 3 秒内把鼠标移到智学网网页右侧的分数输入框中心。")
        self.root.after(3000, self.capture_score_input_position)

    def capture_score_input_position(self):
        x, y = pyautogui.position()
        self.config["score_input"] = {"x": int(x), "y": int(y)}
        self.save_config()
        self.status.set(f"分数输入框已记录：{x}, {y}")

    def record_submit_button(self):
        self.status.set("请在 3 秒内把鼠标移到智学网网页右侧的“提交分数”按钮中心。")
        self.root.after(3000, self.capture_submit_position)

    def capture_submit_position(self):
        x, y = pyautogui.position()
        self.config["submit_button"] = {"x": int(x), "y": int(y)}
        self.save_config()
        self.status.set(f"网页提交分数按钮已记录：{x}, {y}")

    def click_submit_only(self):
        submit = self.config.get("submit_button")
        if not submit:
            messagebox.showwarning("未记录", "请先点击“记录网页上的提交分数按钮”。")
            return
        self.root.withdraw()
        time.sleep(0.2)
        pyautogui.click(int(submit["x"]), int(submit["y"]))
        self.root.deiconify()
        self.status.set("已点击网页上的“提交分数”按钮。")

    def capture_essay(self):
        region = self.config.get("essay_region")
        if not region:
            raise RuntimeError("请先校准作文区域。")
        self.log("正在截图作文区域。")
        self.root.withdraw()
        time.sleep(0.25)
        img = pyautogui.screenshot(region=rect_to_tuple(region))
        img.save(LAST_CAPTURE_PATH)
        self.root.deiconify()
        self.log(f"作文截图完成：{LAST_CAPTURE_PATH.name}")
        return LAST_CAPTURE_PATH

    def score_current_essay(self):
        self.save_config()
        self.task_started_at = time.time()
        self.output.delete("1.0", "end")
        self.log("开始截图并评分。")
        threading.Thread(target=self._score_worker, daemon=True).start()

    def _score_worker(self):
        try:
            result = self.request_score_for_current_essay(self.single_output_mode.get())
            self.last_result = result
            self.root.after(0, lambda: self.show_result(result))
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.show_error(exc))

    def request_score_for_current_essay(self, output_mode=None):
        output_mode = self.normalized_output_mode(output_mode)
        image_path = self.capture_essay()
        try:
            messages, material_count = self.build_scoring_messages(image_path, output_mode)
        finally:
            Path(image_path).unlink(missing_ok=True)
        self.log(f"已加入材料图片 {material_count} 张。")
        self.log(f"正在发送请求给模型；输出模式：{output_mode}。")
        client = self.current_client()
        response = client.chat.completions.create(
            model=self.model.get().strip() or "gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=self.max_tokens_for_output_mode(output_mode),
            timeout=float(self.config.get("request_timeout_seconds", 180)),
        )
        self.log("模型已返回，正在解析评分结果。")
        text = response.choices[0].message.content or ""
        self.log(f"模型返回文本长度：{len(text)} 字。")
        result = extract_json(text)
        score = int(result["score"])
        score = max(0, min(int(self.config.get("max_score", 50)), score))
        result["score"] = score
        auto_score, auto_note = self.apply_auto_guardrails(score, result)
        adjusted_score, adjustment_note = self.apply_presentation_override(auto_score)
        result["auto_adjusted_score"] = auto_score
        result["auto_rule_adjustment"] = auto_note
        result["adjusted_score"] = adjusted_score
        result["manual_adjustment"] = adjustment_note
        return result

    def show_result(self, result):
        elapsed = ""
        if self.task_started_at:
            elapsed = f"，耗时 {time.time() - self.task_started_at:.1f} 秒"
        adjusted = result.get("adjusted_score", result.get("score"))
        if adjusted != result.get("score"):
            self.status.set(
                f"AI 建议分：{result.get('score')}，修正后：{adjusted}，置信度：{result.get('confidence')}{elapsed}"
            )
        else:
            self.status.set(f"AI 建议分：{result.get('score')}，置信度：{result.get('confidence')}{elapsed}")
        text = "\n--- 评分结果 ---\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        self.output.insert("end", text)
        self.append_log_file(text)
        self.trim_visible_log()
        self.output.see("end")

    def show_error(self, exc):
        self.root.deiconify()
        self.status.set("评分失败。")
        text = "\n--- 错误 ---\n" + str(exc) + "\n"
        self.output.insert("end", text)
        self.append_log_file(text)
        self.trim_visible_log()
        self.output.see("end")

    def score_point(self, score):
        grid = self.config.get("score_grid")
        if not grid:
            raise RuntimeError("请先校准分数网格。")
        self.validate_score_range(score)
        cols = 5
        rows = 11
        cell_w = grid["w"] / cols
        cell_h = grid["h"] / rows
        row = score // cols
        col = score % cols
        if score == 50:
            row = 10
            col = 0
        return int(grid["x"] + (col + 0.5) * cell_w), int(grid["y"] + (row + 0.5) * cell_h)

    def validate_score_range(self, score):
        if score < 0 or score > int(self.config.get("max_score", 50)):
            raise RuntimeError(f"分数超出范围：{score}")

    def accept_and_submit(self):
        if not self.last_result:
            messagebox.showwarning("没有建议分", "请先点击“截图并评分”。")
            return
        try:
            score = int(self.last_result.get("adjusted_score", self.last_result["score"]))
            self.click_score_and_maybe_submit(score, submit=self.auto_submit.get())
            action = "已输入" if self.submit_mode.get() == SUBMIT_MODE_INPUT else "已点击"
            self.status.set(f"{action} {score} 分" + ("并提交。" if self.auto_submit.get() else "。"))
        except Exception as exc:
            self.root.deiconify()
            messagebox.showerror("提交失败", str(exc))

    def click_score_and_maybe_submit(self, score, submit=True):
        self.validate_score_range(score)
        pause = float(self.config.get("click_pause_seconds", 0.15))
        self.root.withdraw()
        try:
            time.sleep(0.2)
            if self.submit_mode.get() == SUBMIT_MODE_INPUT:
                self.input_score(score, pause)
            else:
                x, y = self.score_point(score)
                pyautogui.click(x, y)
            time.sleep(pause)
            if submit:
                self.click_recorded_submit_button()
        finally:
            self.root.deiconify()

    def input_score(self, score, pause):
        score_input = self.config.get("score_input")
        if not score_input:
            raise RuntimeError("请先校准分数输入框，或切回按钮打分模式。")
        pyautogui.click(int(score_input["x"]), int(score_input["y"]))
        time.sleep(pause)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(pause)
        pyautogui.write(str(score), interval=0.02)

    def click_recorded_submit_button(self):
        submit_button = self.config.get("submit_button")
        if not submit_button:
            raise RuntimeError("请先记录网页上的“提交分数”按钮。")
        pyautogui.click(int(submit_button["x"]), int(submit_button["y"]))

    def should_pause_auto_loop(self, result):
        if not self.auto_loop_pause_on_recheck.get():
            return False, ""
        confidence = str(result.get("confidence", "")).lower()
        if result.get("recheck"):
            return True, "模型标记为需要复核"
        if confidence == "low":
            return True, "模型置信度为 low"
        if int(result.get("adjusted_score", result.get("score", 0))) != int(result.get("score", 0)):
            return True, "自动规则或人工卷面判断修正了模型原分"
        return False, ""

    def start_auto_loop(self):
        if self.auto_loop_running:
            messagebox.showinfo("自动连评", "自动连评已经在运行。")
            return
        if not self.config.get("essay_region"):
            messagebox.showwarning("未校准", "请先校准作文区域。")
            return
        if self.submit_mode.get() == SUBMIT_MODE_INPUT:
            if not self.config.get("score_input"):
                messagebox.showwarning("未记录", "输入框打分模式需要先校准分数输入框。")
                return
        elif not self.config.get("score_grid"):
            messagebox.showwarning("未校准", "请先校准分数网格。")
            return
        if not self.config.get("submit_button"):
            messagebox.showwarning("未记录", "请先记录网页上的“提交分数”按钮。")
            return
        self.save_config()
        self.output.delete("1.0", "end")
        self.auto_loop_stop.clear()
        self.auto_loop_running = True
        self.log("自动连评已启动。看到异常可随时点“停止自动连评”。")
        threading.Thread(target=self._auto_loop_worker, daemon=True).start()

    def stop_auto_loop(self):
        self.auto_loop_stop.set()
        self.log("已请求停止自动连评；如果模型正在返回中，会在当前这一份结束后停止。")

    def _auto_loop_worker(self):
        completed = 0
        try:
            max_count = max(1, int(self.config.get("auto_loop_max_count", 20)))
            delay = max(0.5, float(self.config.get("auto_loop_delay_seconds", 1.5)))
            while completed < max_count and not self.auto_loop_stop.is_set():
                self.task_started_at = time.time()
                self.log(f"自动连评第 {completed + 1}/{max_count} 份：开始截图评分。")
                result = self.request_score_for_current_essay(self.auto_output_mode.get())
                self.last_result = result
                self.root.after(0, lambda r=result: self.show_result(r))
                pause, reason = self.should_pause_auto_loop(result)
                if pause:
                    self.log(f"自动连评已暂停：{reason}。请人工确认后再继续。")
                    break
                score = int(result.get("adjusted_score", result["score"]))
                self.log(f"自动提交 {score} 分。")
                self.click_score_and_maybe_submit(score, submit=True)
                completed += 1
                if self.auto_loop_stop.wait(delay):
                    break
            if completed >= max_count:
                self.log(f"自动连评完成：已处理 {completed} 份，达到本轮上限。")
            elif self.auto_loop_stop.is_set():
                self.log(f"自动连评已停止：本轮已处理 {completed} 份。")
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.show_error(exc))
        finally:
            self.auto_loop_running = False


if __name__ == "__main__":
    pyautogui.FAILSAFE = True
    root = ctk.CTk()
    app = MarkingAssistant(root)
    root.mainloop()
