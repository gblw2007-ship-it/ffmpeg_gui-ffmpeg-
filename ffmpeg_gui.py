import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import json
import os
import threading
import time
import re
from queue import Queue

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

import sys

def get_resource_path(relative_path):
    """ 获取资源绝对路径，兼容 PyInstaller 单文件打包模式 """
    if hasattr(sys, '_MEIPASS'):
        # 如果是打包后的运行环境，走这里
        return os.path.join(sys._MEIPASS, relative_path)
    # 如果是本地代码开发环境，走这里
    return os.path.join(os.path.abspath("."), relative_path)

FFMPEG_EXE = get_resource_path("ffmpeg.exe")
FFPROBE_EXE = get_resource_path("ffprobe.exe")

class FFmpegModernWorkstation(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("FFmpeg 批处理工具 (v1.0测试版)")
        self.geometry("1100x800")
        self.minsize(850, 650)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # --- 数据状态 ---
        self.current_duration = 0.0 
        self.tasks = [] 
        
        # --- 双日志队列 ---
        self.log_queue = Queue()         
        self.ffmpeg_log_queue = Queue()  
        
        self.active_processes = {} 
        self.paused_tasks = set()  

        # --- 属性绑定变量 ---
        self.var_format_info = ctk.StringVar(value="未知")
        self.var_size = ctk.StringVar(value="未知")
        self.var_duration = ctk.StringVar(value="未知")
        self.var_resolution = ctk.StringVar(value="未知")
        self.var_vcodec_info = ctk.StringVar(value="未知")
        self.var_fps_info = ctk.StringVar(value="未知")
        self.var_vbitrate_info = ctk.StringVar(value="未知") 
        self.var_color_info = ctk.StringVar(value="未知")    
        self.var_audio_info = ctk.StringVar(value="未知")    
        self.var_out_dir = ctk.StringVar()
        
        self.var_hw = ctk.StringVar(value="None")
        self.var_vc = ctk.StringVar(value="libx264 (H.264通用)")

        self.setup_ui()
        self.start_log_listener()

        self.log_msg("="*80)
        self.log_msg("[系统自检] 软件引擎已加载...")
        self.log_msg(f"[系统自检] 核心路径检查: FFMPEG = {'正常' if os.path.exists(FFMPEG_EXE) else '缺失'}")
        
        self.detect_and_apply_hardware()
        self.log_msg("="*80)

        # 延迟 300 毫秒展示公告弹窗
        self.after(300, self.show_modern_popup)

    def show_modern_popup(self):
        """启动弹窗 (独立的方法，缩进与 __init__ 齐平)"""
        popup = ctk.CTkToplevel(self)
        popup.title("系统公告")
        popup.geometry("550x250")
        
        # 强制悬浮与模态锁定
        popup.transient(self) 
        popup.grab_set() 

        ctk.CTkLabel(popup, text="⚠️ 工具使用说明", font=("Microsoft YaHei", 18, "bold"), text_color="#FFB000").pack(pady=(20, 10))
        
        info_text = (
            "1. 【并发限制】软件无并发限制，支持多任务并发渲染。但请注意您的GPU性能。\n"
            "2. 【日志系统】软件日志和 FFmpeg 引擎底层双监控窗格。方便查看运行状态。\n"
            "3. 【硬件嗅探】软件会扫描您的硬件信息，仅自动选择码器，不会发送至网络。\n"
            "4. 【版权声明】本软件仅提供GUI图形化界面，底层处理引擎使用FFmpeg软件。\n"
            "5. 【发布说明】软件开源在github上，如果你是付费购买的恭喜你你被诈骗了。"
        )
        ctk.CTkLabel(popup, text=info_text, font=("Microsoft YaHei", 13), justify="left").pack(padx=20, pady=10)

        btn_close = ctk.CTkButton(popup, text="确认使用", font=("Microsoft YaHei", 13, "bold"), width=150, fg_color="#2EA043", hover_color="#237932", command=popup.destroy)
        btn_close.pack(pady=(15, 0))

    def detect_and_apply_hardware(self):
        self.log_msg("[硬件嗅探] 正在探测处理器...")
        if not HAS_WMI:
            self.log_msg("[硬件嗅探失败] 缺少 WMI 模块。请在终端运行 'pip install WMI'。")
            return
            
        try:
            w = wmi.WMI()
            gpus = w.Win32_VideoController()
            if not gpus:
                self.log_msg("[硬件嗅探] 未能探测到独立物理显卡。")
                return

            detected_gpus = [gpu.Name for gpu in gpus]
            self.log_msg(f"[硬件嗅探成功] 发现本机显卡: {', '.join(detected_gpus)}")

            best_gpu = ""
            for name in detected_gpus:
                name_upper = name.upper()
                if "NVIDIA" in name_upper or "GEFORCE" in name_upper:
                    best_gpu = "NVIDIA"
                    break 
                elif "AMD" in name_upper or "RADEON" in name_upper:
                    best_gpu = "AMD"
                elif "INTEL" in name_upper and best_gpu == "":
                    best_gpu = "INTEL"

            if best_gpu == "NVIDIA":
                self.log_msg("[处理器选择] 检测到 NVIDIA GPU。自动使用 CUDA 加速与 硬件NVENC！")
                self.var_hw.set("cuda")
                self.var_vc.set("h264_nvenc (N卡H.264)")
            elif best_gpu == "AMD":
                self.log_msg("[处理器选择] 检测到 AMD 显卡。自动开启 DXVA2 硬件加速。")
                self.var_hw.set("dxva2")
            elif best_gpu == "INTEL":
                self.log_msg("[处理器选择] 检测到 Intel 核显。自动开启 QSV 加速。")
                self.var_hw.set("qsv")

        except Exception as e:
            self.log_msg(f"[硬件嗅探崩溃] 无法读取底层硬件表: {e}")

    def on_closing(self):
        if self.active_processes:
            if messagebox.askokcancel("警告", f"当前有 {len(self.active_processes)} 个任务正在渲染！\n强行退出将导致文件损坏。\n\n确定要退出吗？"):
                for pid, process in self.active_processes.items():
                    try: process.kill()
                    except: pass
                self.destroy()
        else:
            self.destroy()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1) 
        self.grid_columnconfigure(1, weight=0) 
        self.grid_rowconfigure(2, weight=1)    

        # ==================== 顶部输入区 ====================
        frame_top_left = ctk.CTkFrame(self, corner_radius=10)
        frame_top_left.grid(row=0, column=0, padx=(15, 10), pady=(15, 10), sticky="nsew")
        frame_top_left.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame_top_left, text="媒体源:", font=("Microsoft YaHei", 13, "bold")).grid(row=0, column=0, padx=15, pady=15, sticky="e")
        self.entry_input = ctk.CTkEntry(frame_top_left, placeholder_text="请选择原始视频文件...")
        self.entry_input.grid(row=0, column=1, padx=(0, 10), pady=15, sticky="we")
        btn_select = ctk.CTkButton(frame_top_left, text="选择并分析", width=100, command=self.select_and_analyze)
        btn_select.grid(row=0, column=2, padx=10, pady=15)

        ctk.CTkLabel(frame_top_left, text="保存至:", font=("Microsoft YaHei", 13, "bold")).grid(row=1, column=0, padx=15, pady=(0, 15), sticky="e")
        self.entry_out_dir = ctk.CTkEntry(frame_top_left, textvariable=self.var_out_dir, placeholder_text="输出文件夹路径...")
        self.entry_out_dir.grid(row=1, column=1, padx=(0, 10), pady=(0, 15), sticky="we")
        btn_dir = ctk.CTkButton(frame_top_left, text="浏览...", width=100, fg_color="#555555", hover_color="#333333", command=lambda: self.var_out_dir.set(filedialog.askdirectory()))
        btn_dir.grid(row=1, column=2, padx=10, pady=(0, 15))

        # ==================== 顶部右侧公告/信息栏 ====================
        frame_info = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E") 
        frame_info.grid(row=0, column=1, rowspan=2, padx=(0, 15), pady=(15, 10), sticky="nsew")
        
        ctk.CTkLabel(frame_info, text="媒体元数据", text_color="#A984FF", font=("Microsoft YaHei", 16, "bold")).pack(pady=(15, 10))
        
        info_inner = ctk.CTkFrame(frame_info, fg_color="transparent")
        info_inner.pack(fill="both", expand=True, padx=20)
        
        infos = [
            ("格式", self.var_format_info), ("大小", self.var_size), ("时长", self.var_duration),
            ("编码", self.var_vcodec_info), ("分辨", self.var_resolution), ("帧率", self.var_fps_info),
            ("码率", self.var_vbitrate_info), ("色彩", self.var_color_info), ("音频", self.var_audio_info)
        ]
        for i, (label, var) in enumerate(infos):
            ctk.CTkLabel(info_inner, text=f"{label}:", text_color="#888888", font=("Microsoft YaHei", 12)).grid(row=i, column=0, sticky="e", pady=3, padx=(0, 10))
            ctk.CTkLabel(info_inner, textvariable=var, text_color="#E0E0E0", font=("Consolas", 12, "bold")).grid(row=i, column=1, sticky="w", pady=3)

        # ==================== 中部参数选项卡 ====================
        self.tabview = ctk.CTkTabview(frame_top_left, height=180)
        self.tabview.grid(row=2, column=0, columnspan=3, padx=15, pady=(0, 15), sticky="nsew")
        
        self.tab_basic = self.tabview.add("基础与切片")
        self.tab_video = self.tabview.add("视频与硬件")
        self.tab_audio = self.tabview.add("音频与滤镜")

        self._build_tabs()

        # ==================== 操作按钮区 ====================
        frame_actions = ctk.CTkFrame(self, fg_color="transparent")
        frame_actions.grid(row=1, column=0, padx=15, pady=0, sticky="we")

        self.btn_add = ctk.CTkButton(frame_actions, text="➕ 建立配置并加入队列", font=("Microsoft YaHei", 13, "bold"), height=35, command=self.add_to_queue)
        self.btn_add.pack(side="left", padx=(0, 10))

        self.btn_start = ctk.CTkButton(frame_actions, text="▶ 启动选中任务", font=("Microsoft YaHei", 13, "bold"), fg_color="#2EA043", hover_color="#237932", height=35, command=self.start_selected_tasks)
        self.btn_start.pack(side="left", padx=10)

        self.btn_pause = ctk.CTkButton(frame_actions, text="暂停/恢复", font=("Microsoft YaHei", 13), fg_color="#555555", hover_color="#333333", height=35, command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=10)

        self.btn_del = ctk.CTkButton(frame_actions, text="删除选中任务", font=("Microsoft YaHei", 13, "bold"), fg_color="#DA3633", hover_color="#A32826", height=35, command=self.delete_selected_task)
        self.btn_del.pack(side="left", padx=10)

        # ==================== 数据表格 ====================
        self.style_treeview()
        
        frame_table = ctk.CTkFrame(self, corner_radius=10)
        frame_table.grid(row=2, column=0, columnspan=2, padx=15, pady=10, sticky="nsew")

        columns = ("ID", "File", "Status", "Progress", "Time")
        self.tree = ttk.Treeview(frame_table, columns=columns, show="headings", style="Dark.Treeview")
        self.tree.heading("ID", text="任务ID")
        self.tree.heading("File", text="输出专属目录与文件名")
        self.tree.heading("Status", text="状态")
        self.tree.heading("Progress", text="渲染详情 (进度 | 剩余 | 速度)")
        self.tree.heading("Time", text="耗时")
        
        self.tree.column("ID", width=60, anchor="center")
        self.tree.column("File", width=400, anchor="w")
        self.tree.column("Status", width=80, anchor="center")
        self.tree.column("Progress", width=450, anchor="w") 
        self.tree.column("Time", width=70, anchor="center")

        tree_scroll = ctk.CTkScrollbar(frame_table, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        self.tree.pack(side="left", fill="both", expand=True, padx=(10,0), pady=10)
        tree_scroll.pack(side="right", fill="y", padx=(0,10), pady=10)

        # ==================== 双窗格底部日志 ====================
        frame_log_container = ctk.CTkFrame(self, corner_radius=10, fg_color="transparent")
        frame_log_container.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="nsew")
        
        frame_log_container.grid_columnconfigure(0, weight=1)
        frame_log_container.grid_columnconfigure(1, weight=1)
        frame_log_container.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame_log_container, text="系统与审计日志:", text_color="#00FF00", font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=(0,5))
        self.text_log_sys = ctk.CTkTextbox(frame_log_container, height=140, fg_color="#0D0D0D", text_color="#00FF00", font=("Consolas", 11), corner_radius=5)
        self.text_log_sys.grid(row=1, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(frame_log_container, text="FFmpeg 引擎底层日志:", text_color="#FFB000", font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=1, sticky="w", padx=5, pady=(0,5))
        self.text_log_ffmpeg = ctk.CTkTextbox(frame_log_container, height=140, fg_color="#0D0D0D", text_color="#FFB000", font=("Consolas", 11), corner_radius=5)
        self.text_log_ffmpeg.grid(row=1, column=1, sticky="nsew", padx=(5, 0))

    def style_treeview(self):
        style = ttk.Style()
        style.theme_use("default")
        bg_color = "#242424" 
        text_color = "#DCE4EE"
        selected_color = "#1F538D"
        style.configure("Dark.Treeview", background=bg_color, foreground=text_color, fieldbackground=bg_color, borderwidth=0, rowheight=30, font=("Microsoft YaHei", 10))
        style.map('Dark.Treeview', background=[('selected', selected_color)])
        style.configure("Dark.Treeview.Heading", background="#333333", foreground=text_color, relief="flat", font=("Microsoft YaHei", 11, "bold"), padding=5)
        style.map("Dark.Treeview.Heading", background=[('active', '#444444')])

    def _build_tabs(self):
        # --- 基础 Tab ---
        self.var_format = ctk.StringVar(value="mp4")
        self.var_trim = ctk.BooleanVar(value=False)
        ctk.CTkLabel(self.tab_basic, text="封装格式:").grid(row=0, column=0, padx=10, pady=10)
        ctk.CTkOptionMenu(self.tab_basic, variable=self.var_format, values=["mp4", "mkv", "mov", "webm", "ts", "m3u8 (HLS流)", "flv", "gif"]).grid(row=0, column=1, padx=10)
        ctk.CTkSwitch(self.tab_basic, text="启用剪切", variable=self.var_trim).grid(row=1, column=0, padx=10, pady=10)
        ctk.CTkLabel(self.tab_basic, text="开始:").grid(row=1, column=1, padx=5, sticky="e")
        self.entry_start = ctk.CTkEntry(self.tab_basic, width=100)
        self.entry_start.insert(0, "00:00:00")
        self.entry_start.grid(row=1, column=2)
        ctk.CTkLabel(self.tab_basic, text="结束:").grid(row=1, column=3, padx=5, sticky="e")
        self.entry_end = ctk.CTkEntry(self.tab_basic, width=100)
        self.entry_end.insert(0, "00:00:00")
        self.entry_end.grid(row=1, column=4)

        # --- 视频 Tab ---
        self.var_res = ctk.StringVar(value="保持原画质")
        self.var_fps = ctk.StringVar(value="保持原帧率")
        self.var_bitrate = ctk.StringVar(value="")
        self.var_pixfmt = ctk.StringVar(value="auto")
        ctk.CTkLabel(self.tab_video, text="硬件加速:").grid(row=0, column=0, padx=10, pady=10)
        ctk.CTkOptionMenu(self.tab_video, variable=self.var_hw, values=["None", "cuda", "qsv", "dxva2"]).grid(row=0, column=1)
        ctk.CTkLabel(self.tab_video, text="视频编码:").grid(row=0, column=2, padx=10)
        ctk.CTkOptionMenu(self.tab_video, variable=self.var_vc, values=["libx264 (H.264通用)", "libx265 (HEVC高压)", "h264_nvenc (N卡H.264)", "hevc_nvenc (N卡H.265)", "libsvtav1 (AV1)", "copy (不转码)"]).grid(row=0, column=3)
        ctk.CTkLabel(self.tab_video, text="分辨率:").grid(row=1, column=0, padx=10, pady=10)
        ctk.CTkComboBox(self.tab_video, variable=self.var_res, values=["保持原画质", "3840x2160", "2560x1440", "1920x1080", "1280x720"]).grid(row=1, column=1)
        ctk.CTkLabel(self.tab_video, text="帧率(FPS):").grid(row=1, column=2, padx=10)
        ctk.CTkComboBox(self.tab_video, variable=self.var_fps, values=["保持原帧率", "24", "30", "60", "120"]).grid(row=1, column=3)
        ctk.CTkLabel(self.tab_video, text="视频码率(kbps):").grid(row=2, column=0, padx=10)
        self.entry_bitrate = ctk.CTkEntry(self.tab_video, textvariable=self.var_bitrate, placeholder_text="例如: 5000")
        self.entry_bitrate.grid(row=2, column=1)
        ctk.CTkLabel(self.tab_video, text="像素格式:").grid(row=2, column=2, padx=10)
        ctk.CTkOptionMenu(self.tab_video, variable=self.var_pixfmt, values=["auto", "yuv420p", "yuv420p10le (10bit)", "yuv444p"]).grid(row=2, column=3)

        # --- 音频滤镜 Tab ---
        self.var_acodec = ctk.StringVar(value="aac")
        self.var_abitrate = ctk.StringVar(value="192")
        self.var_rotate = ctk.StringVar(value="无")
        self.var_speed = ctk.StringVar(value="1.0x")
        ctk.CTkLabel(self.tab_audio, text="音频编码:").grid(row=0, column=0, padx=10, pady=10)
        ctk.CTkOptionMenu(self.tab_audio, variable=self.var_acodec, values=["aac", "libmp3lame", "flac", "copy", "an"]).grid(row=0, column=1)
        ctk.CTkLabel(self.tab_audio, text="音频码率(kbps):").grid(row=0, column=2, padx=10)
        ctk.CTkEntry(self.tab_audio, textvariable=self.var_abitrate).grid(row=0, column=3)
        ctk.CTkLabel(self.tab_audio, text="画面旋转:").grid(row=1, column=0, padx=10, pady=10)
        ctk.CTkOptionMenu(self.tab_audio, variable=self.var_rotate, values=["无", "顺时针90度", "逆时针90度", "旋转180度"]).grid(row=1, column=1)
        ctk.CTkLabel(self.tab_audio, text="视频倍速:").grid(row=1, column=2, padx=10)
        ctk.CTkOptionMenu(self.tab_audio, variable=self.var_speed, values=["1.0x", "0.5x", "2.0x"]).grid(row=1, column=3)

    # ========================== 双线日志系统 ==========================
    def log_msg(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"{timestamp} {msg}")
        
    def ffmpeg_log_msg(self, msg):
        self.ffmpeg_log_queue.put(msg)

    def start_log_listener(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.text_log_sys.insert(tk.END, msg + "\n")
                self.text_log_sys.see(tk.END)
        except: pass
        
        try:
            while True:
                msg = self.ffmpeg_log_queue.get_nowait()
                self.text_log_ffmpeg.insert(tk.END, msg + "\n")
                self.text_log_ffmpeg.see(tk.END)
        except: pass
        
        self.after(30, self.start_log_listener)

    # ========================== 核心业务逻辑 ==========================
    def select_and_analyze(self):
        filepath = filedialog.askopenfilename()
        if not filepath: return
        self.entry_input.delete(0, tk.END)
        self.entry_input.insert(0, filepath)
        self.var_out_dir.set(os.path.dirname(filepath))
        self.log_msg(f"[INFO] 探针正在分析: {os.path.basename(filepath)}")

        cmd = [FFPROBE_EXE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", filepath]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            data = json.loads(result.stdout)
            format_info = data.get('format', {})
            self.current_duration = float(format_info.get('duration', 0))
            size_mb = int(format_info.get('size', 0)) / (1024 * 1024)

            self.var_format_info.set(format_info.get('format_name', '未知').upper()[:10])
            self.var_size.set(f"{size_mb:.1f} MB")
            
            h, m, s = int(self.current_duration // 3600), int((self.current_duration % 3600) // 60), int(self.current_duration % 60)
            self.var_duration.set(f"{h:02d}:{m:02d}:{s:02d}")

            video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
            if video_stream:
                self.var_vcodec_info.set(f"{video_stream.get('codec_name', '').upper()}")
                self.var_resolution.set(f"{video_stream.get('width', '-')}x{video_stream.get('height', '-')}")
                fps_str = video_stream.get('r_frame_rate', '0/1')
                try:
                    num, den = map(int, fps_str.split('/'))
                    self.var_fps_info.set(f"{num/den:.1f} FPS" if den!=0 else "-")
                except: pass
                v_bitrate = int(video_stream.get('bit_rate', 0))
                if v_bitrate == 0: v_bitrate = int(format_info.get('bit_rate', 0))
                self.var_vbitrate_info.set(f"{v_bitrate / 1000:.0f} k" if v_bitrate > 0 else "未知")
                pix_fmt = video_stream.get('pix_fmt', '未知')
                self.var_color_info.set(f"{pix_fmt}")

            audio_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), None)
            if audio_stream:
                a_codec = audio_stream.get('codec_name', '').upper()
                self.var_audio_info.set(f"{a_codec} {audio_stream.get('channels', 2)}ch")

            self.entry_end.delete(0, tk.END)
            self.entry_end.insert(0, f"{h:02d}:{m:02d}:{s:02d}")
            self.log_msg(f"[SUCCESS] 解析成功。")
        except Exception as e:
            self.log_msg(f"[ERROR] 解析失败: {e}")

    def add_to_queue(self):
        input_file = self.entry_input.get()
        out_dir = self.var_out_dir.get()
        if not input_file or not out_dir: return

        base_name = os.path.basename(input_file)
        name_no_ext = os.path.splitext(base_name)[0]
        ext_clean = self.var_format.get().split()[0].replace('.', '')
        
        vcodec_clean = self.var_vc.get().split()[0]
        res_clean = "Orig" if "保持" in self.var_res.get() else self.var_res.get().split()[0]

        folder_name = f"{name_no_ext}_{vcodec_clean}_{res_clean}_{ext_clean}"
        folder_name = re.sub(r'[\\/*?:"<>|]', "", folder_name)
        target_dir = os.path.join(out_dir, folder_name)
        output_file = os.path.join(target_dir, f"output.{ext_clean}")

        command = [FFMPEG_EXE, "-y"]
        
        hw = self.var_hw.get().split()[0]
        rotate = self.var_rotate.get()
        speed_val = self.var_speed.get().split("x")[0]
        is_pure_gpu = (hw == "cuda" and rotate == "无" and speed_val == "1.0")

        if hw != "None": 
            command.extend(["-hwaccel", hw])
            if is_pure_gpu: command.extend(["-hwaccel_output_format", "cuda"]) 
        
        if self.var_trim.get(): command.extend(["-ss", self.entry_start.get(), "-to", self.entry_end.get()])
        command.extend(["-i", input_file])
        
        vcodec = self.var_vc.get().split()[0]
        command.extend(["-c:v", vcodec])
        
        if vcodec not in ["copy", "vn"]:
            fps = self.var_fps.get()
            if "保持" not in fps: command.extend(["-r", fps])
            vbitrate = self.var_bitrate.get().strip()
            if vbitrate:
                if vbitrate.isdigit(): command.extend(["-b:v", f"{vbitrate}k"])
                else: command.extend(["-b:v", vbitrate])
            pixfmt = self.var_pixfmt.get().split()[0]
            if pixfmt != "auto": command.extend(["-pix_fmt", pixfmt])

            vf_filters = []
            res = self.var_res.get().split()[0]
            if res != "保持原画质": 
                vf_filters.append(f"scale_cuda={res.replace('x', ':')}" if is_pure_gpu else f"scale={res.replace('x', ':')}")
            if rotate == "顺时针90度": vf_filters.append("transpose=1")
            elif rotate == "逆时针90度": vf_filters.append("transpose=2")
            elif rotate == "旋转180度": vf_filters.append("transpose=2,transpose=2")
            if speed_val != "1.0": vf_filters.append(f"setpts={1.0/float(speed_val)}*PTS")
            if vf_filters: command.extend(["-vf", ",".join(vf_filters)])

        acodec = self.var_acodec.get().split()[0]
        if acodec == "an": command.extend(["-an"])
        else:
            command.extend(["-c:a", acodec])
            if acodec != "copy":
                abitrate = self.var_abitrate.get().strip()
                if abitrate: command.extend(["-b:a", f"{abitrate}k" if abitrate.isdigit() else abitrate])
                if speed_val != "1.0": command.extend(["-af", f"atempo={speed_val}"])

        if ext_clean == "m3u8": command.extend(["-f", "hls", "-hls_time", "10", "-hls_list_size", "0"])
        command.append(output_file)

        task_duration = self.current_duration
        if self.var_trim.get():
            try:
                def t_to_s(t_str):
                    h, m, s = map(float, t_str.split(":"))
                    return h*3600 + m*60 + s
                task_duration = t_to_s(self.entry_end.get()) - t_to_s(self.entry_start.get())
            except: pass

        task_id = len(self.tasks) + 1
        task_info = {"id": task_id, "output": output_file, "cmd": command, "duration": task_duration, "status": "等待中"}
        self.tasks.append(task_info)
        
        self.tree.insert("", "end", iid=str(task_id), values=(task_id, folder_name, "等待中", "-", "-"))
        self.log_msg(f"[INFO] 任务 #{task_id} 已入队。")

    def toggle_pause(self):
        if not HAS_PSUTIL: return
        selected = self.tree.selection()
        if not selected: return
            
        for item_id in selected:
            task_id = int(item_id)
            if task_id in self.active_processes:
                try:
                    p = psutil.Process(self.active_processes[task_id].pid)
                    if task_id in self.paused_tasks:
                        p.resume()
                        self.paused_tasks.remove(task_id)
                        self.log_msg(f"[RESUME] 任务 #{task_id} 恢复运行。")
                    else:
                        p.suspend()
                        self.paused_tasks.add(task_id)
                        self.log_msg(f"[PAUSE] 任务 #{task_id} 已强制挂起。")
                except: pass

    def delete_selected_task(self):
        selected = self.tree.selection()
        if not selected: return
            
        for item_id in selected:
            task_id = int(item_id)
            task = next((t for t in self.tasks if t["id"] == task_id), None)
            if not task: continue
            
            if task_id in self.active_processes:
                try:
                    self.active_processes[task_id].kill()
                    self.log_msg(f"[KILL] 已强制阻断并抹除运行中的任务 #{task_id}")
                except: pass
                
            self.tree.delete(item_id)
            if task in self.tasks: self.tasks.remove(task)

    def start_selected_tasks(self):
        selected = self.tree.selection()
        if not selected: return

        target_ids = [int(item) for item in selected]
        valid_targets = [t for t in self.tasks if t["id"] in target_ids and t["status"] not in ["处理中", "✅ 完成"]]
        
        if not valid_targets: return

        self.log_msg(f"[START] 发射 {len(valid_targets)} 个并发渲染线程...")
        
        for task in valid_targets:
            task["status"] = "处理中"
            self.update_tree_item(task["id"], status="处理中", progress="初始化...")
            threading.Thread(target=self.run_single_task_thread, args=(task,), daemon=True).start()

    def update_tree_item(self, task_id, status=None, progress=None, time_elapsed=None):
        try:
            item = self.tree.item(str(task_id))
            if not item: return
            values = list(item['values'])
            if status: values[2] = status
            if progress: values[3] = progress
            if time_elapsed: values[4] = time_elapsed
            self.tree.item(str(task_id), values=values)
        except: pass 

    def create_progress_bar(self, percent):
        length = 15
        filled = int(length * percent // 100)
        return '█' * filled + '░' * (length - filled)

    def run_single_task_thread(self, task):
        task_id = task["id"]
        target_dir_path = os.path.dirname(task['output'])
        os.makedirs(target_dir_path, exist_ok=True)
        
        start_time = time.time()
        last_log_time = time.time() 
        
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(
                task["cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, encoding='utf-8', errors='ignore', creationflags=creation_flags
            )
            self.active_processes[task_id] = process
            
            self.ffmpeg_log_msg(f"[Task #{task_id} START] " + " ".join(task["cmd"]))
            
            time_regex = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            speed_regex = re.compile(r"speed=\s*([\d\.]+)x")
            
            for line in process.stdout:
                if task["status"] in ["强制终止", "已取消"]: break
                
                clean_line = line.strip()
                if clean_line:
                    self.ffmpeg_log_msg(f"[T{task_id}] {clean_line}")
                
                time_match = time_regex.search(line)
                if time_match and task["duration"] > 0:
                    h, m, s = float(time_match.group(1)), float(time_match.group(2)), float(time_match.group(3))
                    current_sec = h * 3600 + m * 60 + s
                    percent = min(100.0, (current_sec / task["duration"]) * 100)
                    
                    speed_m = speed_regex.search(line)
                    speed_val = float(speed_m.group(1)) if speed_m else 0
                    
                    if speed_val > 0: eta_sec = max(0, (task["duration"] - current_sec) / speed_val)
                    else: eta_sec = 0
                        
                    eta_m, eta_s = divmod(int(eta_sec), 60)
                    eta_str = f"{eta_m:02d}m{eta_s:02d}s"

                    elapsed = time.time() - start_time
                    progress_display = f"[{self.create_progress_bar(percent)}] {percent:.1f}% | 剩:{eta_str} | {speed_val}x"
                    self.update_tree_item(task_id, progress=progress_display, time_elapsed=f"{elapsed:.1f}s")
                    
                    if time.time() - last_log_time >= 1.0:
                        self.log_msg(f"[HEARTBEAT] 任务 #{task_id} 进度: {percent:.1f}%, 速度: {speed_val}x")
                        last_log_time = time.time()

            process.wait() 
            
            if task["status"] in ["强制终止", "已取消"]: 
                self.ffmpeg_log_msg(f"[Task #{task_id} KILLED] 进程已被物理强杀。")
            elif process.returncode == 0:
                task["status"] = "✅ 完成"
                final_time = time.time() - start_time
                self.update_tree_item(task_id, status="✅ 完成", progress=f"[{self.create_progress_bar(100)}] 100% | 完成", time_elapsed=f"{final_time:.1f}s")
                self.log_msg(f"[SUCCESS] 任务 #{task_id} 圆满结束。")
                self.ffmpeg_log_msg(f"[Task #{task_id} FINISH] 渲染管道正常关闭。")
            else:
                raise Exception(f"Exit code: {process.returncode}")

        except Exception as e:
            if task["status"] not in ["强制终止", "已取消"]: 
                task["status"] = "❌ 失败"
                self.update_tree_item(task_id, status="❌ 失败", progress="错误")
                self.log_msg(f"[ERROR] 任务 #{task_id} 崩溃。")
                self.ffmpeg_log_msg(f"[Task #{task_id} ERROR] {e}")
        finally:
            if task_id in self.active_processes: del self.active_processes[task_id]
            if task_id in self.paused_tasks: self.paused_tasks.remove(task_id)

if __name__ == "__main__":
    if os.name == 'nt': 
        import ctypes
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try: ctypes.windll.user32.SetProcessDPIAware()
            except Exception: pass

    app = FFmpegModernWorkstation()
    app.mainloop()
    #打包命令示例（需在项目根目录终端执行）：
    #python -m PyInstaller -F -w --collect-all customtkinter --add-data "ffmpeg.exe;." --add-data "ffprobe.exe;." ffmpeg_gui.py
    #说明：--add-data 参数格式为 "源路径;目标路径"，多个文件需要重复使用 --add-data。打包后可在 dist/ffmpeg_gui/ 目录下找到生成的 ffmpeg.exe 和 ffprobe.exe。
    #注意：打包时请确保 ffmpeg.exe 和 ffprobe.exe 与 ffmpeg_gui.py 在同一目录下，且命令中的路径正确。
