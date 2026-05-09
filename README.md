# FFmpeg 批处理工具（GUI）

基于 CustomTkinter UI和FFmpeg打造的频压制工具，为高性能 PC 优化，支持硬件感知、多任务并发调度与双轨日志。

## 特性 
* **现代GUI**：摒弃传统 Tkinter 的老旧感，适配 4K/2K 高 DPI 屏幕。
* **硬件感知**：启动时自动探测本机 NVIDIA/AMD/Intel 显卡型号。针对 NVIDIA RTX 等旗舰级硬件，自动挂载 CUDA 加速与 NVENC 编码预设。
* **无并发限制**：支持多任务同时启动渲染，充分榨干PC的每一分性能。
* **元数据解析**：集成探针引擎，实时提取分辨率、色彩空间（YUV/10-bit）、码率、帧率及音频轨道详情。

## 日志监控
* **系统日志 (左)**：监控交互、硬件识别及调度逻辑。
* **引擎日志 (右)**：实时滚动 FFmpeg 底层原始数据流，精准排查错误。

## 快速开始

### 方案 A：直接运行 (推荐)
* 进入 Releases 页面。
* 下载最新的 ffmpeg_gui.exe。
* 双击即用，无需安装 Python 或配置环境变量（内置 FFmpeg 核心）。

### 方案 B：源码运行 (开发者模式)
```bash
git clone [https://github.com/你的用户名/ffmpeg_gui-ffmpeg-.git](https://github.com/你的用户名/ffmpeg_gui-ffmpeg-.git)
cd ffmpeg_gui-ffmpeg-
pip install customtkinter psutil wmi
python ffmpeg_gui.py

```

## 使用指南

1. **选择媒体源**：点击“选择并分析”，软件将自动读取视频信息。
2. **配置参数**：在选项卡中快速设置编码器（NVENC/H.264/AV1）、分辨率、码率及滤镜。
3. **加入队列**：点击“➕ 建立配置并加入队列”。
4. **并发启动**：在列表中框选一个或多个任务，点击“▶ 启动选中任务”。
5. **实时监控**：通过双栏日志实时观察渲染进度与硬件负载。

## 架构与技术栈

* **Core**: Python 3.14 (Preview)
* **GUI**: CustomTkinter
* **Processing**: FFmpeg & FFprobe Binary
* **Process Management**: Psutil
* **Hardware Probing**: Windows WMI API
