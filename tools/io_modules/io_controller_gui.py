#!/usr/bin/env python3
"""
IO Controller GUI应用程序
提供可视化界面控制电机控制器
"""

from calendar import c
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import sys
import os
import threading
import time
from typing import Optional

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)
try:
    from .io_controller import IoController

except ImportError:
    sys.path.append(os.path.dirname(current_dir))
    from io_controller import IoController
tools_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(tools_dir)
for path in [tools_dir, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from .io_controller import IoController
except ImportError:
    from io_controller import IoController

try:
    from ...logs.logger_utils import logger
except ImportError:
    try:
        from logs.logger_utils import logger
    except ImportError:
        import logging
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

class IoControllerGUI:
    """IO控制器GUI应用程序"""

    # 模式配置（包含设备IP）
    MODES = {
        1: {"name": "运料小车", "ip": "192.168.3.21"},
        2: {"name": "放料小车（机器人）", "ip": "192.168.3.22"},
        3: {"name": "电梯", "ip": "192.168.3.23"}
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IO Controller 电机控制面板")
        self.root.geometry("900x700")
        self.root.resizable(False, False)

        # 设置窗口图标和样式
        self.root.configure(bg='#f0f0f0')

        # 当前模式（默认为模式1）
        self.mode = 1

        # IO控制器实例
        self.controller: Optional[IoController] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None

        # 线程安全锁
        self.controller_lock = threading.RLock()
        self.shutdown_event = threading.Event()

        # DO状态缓存
        self.do1_states = [tk.BooleanVar() for _ in range(8)]
        self.do2_states = [tk.BooleanVar() for _ in range(8)]

        # 创建界面
        self.create_widgets()

        # 启动异步事件循环
        self.start_async_loop()

        # 设置关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """创建GUI组件"""
        # 主标题
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        title_frame.pack(fill='x', padx=5, pady=5)
        title_frame.pack_propagate(False)

        title_label = tk.Label(title_frame, text="🔧 IO Controller 控制面板",
                              font=('微软雅黑', 16, 'bold'),
                              bg='#2c3e50', fg='white')
        title_label.pack(expand=True)

        # 连接控制区域
        self.create_connection_frame()

        # 状态显示区域
        self.create_status_frame()

        # 控制按钮区域
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=5)

        # DO1控制标签页
        self.create_do1_frame(notebook)

        # DO2控制标签页
        self.create_do2_frame(notebook)

        # 电机控制标签页
        self.create_motor_frame(notebook)

        # 位置控制标签页
        self.create_position_frame(notebook)

    def create_connection_frame(self):
        """创建连接控制区域"""
        conn_frame = tk.LabelFrame(self.root, text="📡 连接控制", font=('微软雅黑', 10, 'bold'),
                                  bg='#f0f0f0', fg='#2c3e50')
        conn_frame.pack(fill='x', padx=10, pady=5)

        # 输入控件容器
        input_container = tk.Frame(conn_frame, bg='#f0f0f0')
        input_container.pack(side='left', padx=10, pady=5, fill='x', expand=True)

        # 第一行：模式选择
        mode_frame = tk.Frame(input_container, bg='#f0f0f0')
        mode_frame.pack(fill='x', pady=(0, 5))

        tk.Label(mode_frame, text="设备模式:", bg='#f0f0f0', font=('微软雅黑', 9, 'bold')).pack(side='left')

        # 创建模式下拉框
        self.mode_var = tk.StringVar()
        mode_options = [f"模式{mode} - {info['name']}" for mode, info in self.MODES.items()]
        self.mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var,
                                     values=mode_options, state='readonly', width=20)
        self.mode_combo.pack(side='left', padx=5)
        self.mode_combo.current(0)  # 默认选择第一个（模式1）
        self.mode_combo.bind('<<ComboboxSelected>>', self.on_mode_changed)

        # 第二行：IP和端口输入
        network_frame = tk.Frame(input_container, bg='#f0f0f0')
        network_frame.pack(fill='x')

        tk.Label(network_frame, text="IP地址:", bg='#f0f0f0').pack(side='left')
        self.ip_entry = tk.Entry(network_frame, width=15)
        self.ip_entry.pack(side='left', padx=5)
        self.ip_entry.insert(0, self.MODES[self.mode]["ip"])

        tk.Label(network_frame, text="端口:", bg='#f0f0f0').pack(side='left', padx=(10,0))
        self.port_entry = tk.Entry(network_frame, width=8)
        self.port_entry.pack(side='left', padx=5)
        self.port_entry.insert(0, "8899")

        # 连接按钮
        self.connect_btn = tk.Button(conn_frame, text="🔗 连接",
                                    command=self.toggle_connection,
                                    bg='#27ae60', fg='white',
                                    font=('微软雅黑', 10, 'bold'),
                                    width=12, height=2)
        self.connect_btn.pack(side='left', padx=20, pady=5)

        # 连接状态显示
        self.status_label = tk.Label(conn_frame, text="● 未连接",
                                    bg='#f0f0f0', fg='#e74c3c',
                                    font=('微软雅黑', 10, 'bold'))
        self.status_label.pack(side='left', padx=10, pady=5)

    def create_status_frame(self):
        """创建状态显示区域"""
        status_frame = tk.LabelFrame(self.root, text="📊 设备状态", font=('微软雅黑', 10, 'bold'),
                                    bg='#f0f0f0', fg='#2c3e50')
        status_frame.pack(fill='x', padx=10, pady=5)

        # 状态信息
        status_info_frame = tk.Frame(status_frame, bg='#f0f0f0')
        status_info_frame.pack(fill='x', padx=10, pady=5)

        self.connection_status = tk.Label(status_info_frame, text="连接状态: 未连接",
                                         bg='#f0f0f0', font=('微软雅黑', 9))
        self.connection_status.pack(side='left', padx=10)

        self.mode_status = tk.Label(status_info_frame,
                                   text=f"设备模式: 模式{self.mode} - {self.MODES[self.mode]['name']}",
                                   bg='#f0f0f0', font=('微软雅黑', 9), fg='#3498db')
        self.mode_status.pack(side='left', padx=10)

        self.motor_status = tk.Label(status_info_frame, text="电机状态: 未知",
                                    bg='#f0f0f0', font=('微软雅黑', 9))
        self.motor_status.pack(side='left', padx=10)

        self.position_status = tk.Label(status_info_frame, text="位置: 0.00",
                                       bg='#f0f0f0', font=('微软雅黑', 9))
        self.position_status.pack(side='left', padx=10)

        self.laser_distance_status = tk.Label(status_info_frame, text="激光深度: 0.000 m",
                                              bg='#f0f0f0', font=('微软雅黑', 9), fg='#e67e22')
        self.laser_distance_status.pack(side='left', padx=10)

    def create_do1_frame(self, notebook):
        """创建DO1控制标签页"""
        do1_frame = tk.Frame(notebook, bg='#f0f0f0')
        notebook.add(do1_frame, text="DO1 数字输出1")

        # 标题
        title = tk.Label(do1_frame, text="DO1 输出端口控制 (0-7)",
                        font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
        title.pack(pady=10)

        # DO1控制按钮网格
        do1_grid = tk.Frame(do1_frame, bg='#f0f0f0')
        do1_grid.pack(pady=10)

        for i in range(8):
            row, col = i // 4, i % 4

            button_frame = tk.Frame(do1_grid, bg='#f0f0f0')
            button_frame.grid(row=row, column=col, padx=10, pady=10)

            # 端口标签
            port_label = tk.Label(button_frame, text=f"DO1[{i}]",
                                font=('微软雅黑', 10, 'bold'), bg='#f0f0f0')
            port_label.pack()

            # 开关按钮
            btn = tk.Button(button_frame, text="关闭", width=8, height=2,
                          command=lambda idx=i: self.toggle_do1(idx),
                          bg='#e74c3c', fg='white',
                          font=('微软雅黑', 9, 'bold'))
            btn.pack(pady=5)

            # 保存按钮引用
            setattr(self, f'do1_btn_{i}', btn)

    def create_do2_frame(self, notebook):
        """创建DO2控制标签页"""
        do2_frame = tk.Frame(notebook, bg='#f0f0f0')
        notebook.add(do2_frame, text="DO2 数字输出2")

        # 标题
        title = tk.Label(do2_frame, text="DO2 输出端口控制 (0-7)",
                        font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
        title.pack(pady=10)

        # DO2控制按钮网格
        do2_grid = tk.Frame(do2_frame, bg='#f0f0f0')
        do2_grid.pack(pady=10)

        for i in range(8):
            row, col = i // 4, i % 4

            button_frame = tk.Frame(do2_grid, bg='#f0f0f0')
            button_frame.grid(row=row, column=col, padx=10, pady=10)

            # 端口标签
            port_label = tk.Label(button_frame, text=f"DO2[{i}]",
                                font=('微软雅黑', 10, 'bold'), bg='#f0f0f0')
            port_label.pack()

            # 开关按钮
            btn = tk.Button(button_frame, text="关闭", width=8, height=2,
                          command=lambda idx=i: self.toggle_do2(idx),
                          bg='#e74c3c', fg='white',
                          font=('微软雅黑', 9, 'bold'))
            btn.pack(pady=5)

            # 保存按钮引用
            setattr(self, f'do2_btn_{i}', btn)

    def create_motor_frame(self, notebook):
        """创建电机控制标签页"""
        motor_frame = tk.Frame(notebook, bg='#f0f0f0')
        notebook.add(motor_frame, text="⚙️ 电机控制")

        # 标题
        title = tk.Label(motor_frame, text="电机开关控制",
                        font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
        title.pack(pady=20)

        # 电机控制按钮
        button_frame = tk.Frame(motor_frame, bg='#f0f0f0')
        button_frame.pack(pady=20)

        # 开启按钮
        self.motor_on_btn = tk.Button(button_frame, text="🔛 电机开启",
                                     command=self.turn_motor_on,
                                     bg='#27ae60', fg='white',
                                     font=('微软雅黑', 12, 'bold'),
                                     width=15, height=3)
        self.motor_on_btn.pack(side='left', padx=20)

        # 关闭按钮
        self.motor_off_btn = tk.Button(button_frame, text="🔴 电机关闭",
                                      command=self.turn_motor_off,
                                      bg='#e74c3c', fg='white',
                                      font=('微软雅黑', 12, 'bold'),
                                      width=15, height=3)
        self.motor_off_btn.pack(side='left', padx=20)

        # 状态显示
        self.motor_state_label = tk.Label(motor_frame, text="电机状态: 未知",
                                         font=('微软雅黑', 11), bg='#f0f0f0')
        self.motor_state_label.pack(pady=20)

    def create_position_frame(self, notebook):
        """创建位置控制标签页"""
        position_frame = tk.Frame(notebook, bg='#f0f0f0')
        notebook.add(position_frame, text="📍 位置控制")

        # 标题
        title = tk.Label(position_frame, text="电机位置控制",
                        font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
        title.pack(pady=20)

        # 位置输入区域
        input_frame = tk.Frame(position_frame, bg='#f0f0f0')
        input_frame.pack(pady=10)

        tk.Label(input_frame, text="位置坐标:",
                font=('微软雅黑', 11), bg='#f0f0f0').pack(side='left', padx=5)

        self.position_entry = tk.Entry(input_frame, font=('微软雅黑', 11), width=15)
        self.position_entry.pack(side='left', padx=5)
        self.position_entry.insert(0, "0.0")

        # 设置按钮
        set_btn = tk.Button(input_frame, text="🎯 设置位置",
                          command=self.set_position,
                          bg='#3498db', fg='white',
                          font=('微软雅黑', 10, 'bold'),
                          width=12, height=2)
        set_btn.pack(side='left', padx=10)

        # 当前位置显示
        self.current_position_label = tk.Label(position_frame,
                                              text="当前位置: 0.00",
                                              font=('微软雅黑', 11),
                                              bg='#f0f0f0')
        self.current_position_label.pack(pady=20)

        # 位置预设按钮
        preset_frame = tk.Frame(position_frame, bg='#f0f0f0')
        preset_frame.pack(pady=10)

        tk.Label(preset_frame, text="快速预设:",
                font=('微软雅黑', 10, 'bold'), bg='#f0f0f0').pack()

        preset_buttons = tk.Frame(preset_frame, bg='#f0f0f0')
        preset_buttons.pack(pady=5)

        presets = [0, 10, 50, 100]
        for pos in presets:
            btn = tk.Button(preset_buttons, text=f"{pos}",
                          command=lambda p=pos: self.set_position_preset(p),
                          bg='#95a5a6', fg='white',
                          font=('微软雅黑', 9),
                          width=6)
            btn.pack(side='left', padx=2)

    def start_async_loop(self):
        """启动异步事件循环"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

        # 等待循环启动
        time.sleep(0.1)

    def run_async(self, coro):
        """在异步循环中运行协程"""
        if not self.loop:
            logger.info("错误: 异步事件循环未初始化")
            return None

        try:
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future
        except RuntimeError as e:
            logger.info(f"异步运行错误: {e}")
            return None

    def with_controller(self, operation):
        """线程安全的控制器访问"""
        with self.controller_lock:
            if self.controller and self.controller.is_connected:
                return operation(self.controller)
            else:
                raise RuntimeError("控制器未连接")

    def is_controller_connected(self):
        """线程安全地检查控制器连接状态"""
        with self.controller_lock:
            return self.controller is not None and self.controller.is_connected

    def toggle_connection(self):
        """切换连接状态"""
        if self.controller is None:
            # 连接
            self.run_async(self.connect_device())
        else:
            # 断开连接
            self.run_async(self.disconnect_device())
    async def connect_device(self):
        """连接设备"""
        try:
            ip = self.ip_entry.get().strip()
            port = int(self.port_entry.get().strip())

            self.update_ui_safely(lambda: self.connect_btn.config(
                text="连接中...", state='disabled', bg='#f39c12'))

            self.controller = IoController()
            await self.controller.connect_async(ip, port)

            if self.controller.is_connected:
                self.update_ui_safely(self.on_connected)
                self.start_status_monitoring()
            else:
                self.update_ui_safely(lambda error_msg="连接失败：无法建立连接": self.on_connection_error(error_msg))
        except ValueError as e:
            self.update_ui_safely(lambda error_msg=f"端口格式错误：{str(e)}": self.on_connection_error(error_msg))
        except RuntimeError as e:
            self.update_ui_safely(lambda error_msg=f"连接失败：{str(e)}": self.on_connection_error(error_msg))
        except Exception as e:
            self.update_ui_safely(lambda error_msg=f"未知错误：{str(e)}": self.on_connection_error(error_msg))
    async def disconnect_device(self):
        """断开设备连接"""
        try:
            if self.controller:
                await self.controller.close()
                self.controller = None
            self.update_ui_safely(self.on_disconnected)
        except RuntimeError as e:
            logger.error(f"断开连接运行时错误: {e}")
            self.update_ui_safely(self.on_disconnected)
        except Exception as e:
            logger.error(f"断开连接未知错误: {e}")
            self.update_ui_safely(self.on_disconnected)

    def on_connected(self):
        """连接成功的UI更新"""
        self.connect_btn.config(text="🔗 断开", bg='#e74c3c', state='normal')
        self.status_label.config(text="● 已连接", fg='#27ae60')
        self.connection_status.config(text=f"连接状态: 已连接到 {self.ip_entry.get()}")

    def on_disconnected(self):
        """断开连接的UI更新"""
        self.connect_btn.config(text="🔗 连接", bg='#27ae60', state='normal')
        self.status_label.config(text="● 未连接", fg='#e74c3c')
        self.connection_status.config(text="连接状态: 未连接")
        self.motor_status.config(text="电机状态: 未知")
        self.position_status.config(text="位置: 0.00")
        self.laser_distance_status.config(text="激光深度: 0.000 m")

    def on_connection_failed(self):
        """连接失败的UI更新"""
        self.connect_btn.config(text="🔗 连接", bg='#27ae60', state='normal')
        self.status_label.config(text="● 连接失败", fg='#e74c3c')
        messagebox.showerror("连接失败", "无法连接到设备，请检查IP地址和端口设置")

    def on_connection_error(self, error_msg):
        """连接错误的UI更新"""
        self.connect_btn.config(text="🔗 连接", bg='#27ae60', state='normal')
        messagebox.showerror("连接错误", f"连接时发生错误:\n{error_msg}")

    def on_mode_changed(self, event=None):
        """模式改变时的回调函数"""
        selected_text = self.mode_var.get()
        # 从选择的文本中提取模式编号
        for mode_num, mode_info in self.MODES.items():
            if f"模式{mode_num} - {mode_info['name']}" == selected_text:
                if self.mode != mode_num:
                    self.mode = mode_num
                    # 更新IP地址为新模式的IP
                    new_ip = self.MODES[self.mode]["ip"]
                    self.ip_entry.delete(0, tk.END)
                    self.ip_entry.insert(0, new_ip)

                    # 如果已经连接，提示用户重新连接
                    if self.is_controller_connected():
                        response = messagebox.askyesno("模式切换",
                            f"已切换到{mode_info['name']}模式（IP: {new_ip}）。\n\n是否重新连接以应用新模式？")
                        if response:
                            # 断开当前连接
                            self.run_async(self.disconnect_device())
                    # 更新状态显示中的模式信息
                    self.update_mode_display()
                break

    def update_mode_display(self):
        """更新模式显示信息"""
        if hasattr(self, 'mode_status'):
            self.mode_status.config(text=f"设备模式: 模式{self.mode} - {self.MODES[self.mode]['name']}")

    def start_status_monitoring(self):
        """启动状态监控"""
        def monitor():
            while not self.shutdown_event.is_set():
                if self.is_controller_connected():
                    try:
                        def get_status(controller):
                            motor_state = controller.get_di_motor_state()
                            position = controller.get_motor_absolute_position()
                            do1_states = controller.get_do1_states()
                            do2_states = controller.get_do2_states()
                            laser_distance = controller.get_laser_distance()
                            return motor_state, position, do1_states, do2_states, laser_distance

                        motor_state, position, do1_states, do2_states, laser_distance = self.with_controller(get_status)

                        self.update_ui_safely(lambda: self.update_status_display(
                            motor_state, position, do1_states, do2_states, laser_distance))

                    except Exception as e:
                        logger.error(f"状态监控错误: {e}")

                time.sleep(0.5)  # 每500ms更新一次

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

    def update_status_display(self, motor_state, position, do1_states, do2_states, laser_distance):
        """更新状态显示"""
        # 更新电机状态
        motor_text = "开启" if motor_state == 1 else "关闭"
        self.motor_status.config(text=f"电机状态: {motor_text}")
        self.motor_state_label.config(text=f"电机状态: {motor_text}")

        # 更新位置
        self.position_status.config(text=f"位置: {position:.2f}")
        self.current_position_label.config(text=f"当前位置: {position:.2f}")

        # 更新激光深度
        self.laser_distance_status.config(text=f"激光深度: {laser_distance:.3f} m")

        # 更新DO1按钮状态
        for i, state in enumerate(do1_states):
            btn = getattr(self, f'do1_btn_{i}')
            if state:
                btn.config(text="开启", bg='#27ae60')
            else:
                btn.config(text="关闭", bg='#e74c3c')

        # 更新DO2按钮状态
        for i, state in enumerate(do2_states):
            btn = getattr(self, f'do2_btn_{i}')
            if state:
                btn.config(text="开启", bg='#27ae60')
            else:
                btn.config(text="关闭", bg='#e74c3c')

    def toggle_do1(self, index):
        """切换DO1端口状态"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        # 对DO1[0]和DO1[3]进行快换操作确认
        if index ==7:
            confirm = messagebox.askyesno(
                "快换操作确认",
                "⚠️ 现在进行快换操作，请确认！\n\n是否继续执行？"
            )
            if not confirm:
                return  # 用户取消操作

        try:
            def toggle_operation(controller):
                current_state = controller.get_do1_state(index)
                controller.set_do1_command(index, not current_state)

            self.with_controller(toggle_operation)
            self.run_async(self.controller.send1_command())
        except Exception as e:
            self.handle_operation_error(f"控制DO1[{index}]", e)

    def toggle_do2(self, index):
        """切换DO2端口状态"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        try:
            def toggle_operation(controller):
                current_state = controller.get_do2_state(index)
                controller.set_do_command(index, not current_state)

            self.with_controller(toggle_operation)
            self.run_async(self.controller.send1_command())
        except Exception as e:
            self.handle_operation_error(f"控制DO2[{index}]", e)

    def turn_motor_on(self):
        """开启电机"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        try:
            def motor_on_operation(controller):
                controller.set_di_motor_command(1)

            self.with_controller(motor_on_operation)
            self.run_async(self.controller.send2_command())
        except Exception as e:
            self.handle_operation_error("开启电机", e)

    def turn_motor_off(self):
        """关闭电机"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        try:
            def motor_off_operation(controller):
                controller.set_di_motor_command(0)

            self.with_controller(motor_off_operation)
            self.run_async(self.controller.send2_command())
        except Exception as e:
            self.handle_operation_error("关闭电机", e)

    def set_position(self):
        """设置电机位置"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        try:
            position = float(self.position_entry.get())

            def set_position_operation(controller):
                controller.set_motor_absolute_position(position)

            self.with_controller(set_position_operation)
            # self.run_async(self.controller.send_command())
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的数字")
        except Exception as e:
            self.handle_operation_error("设置位置", e)

    def set_position_preset(self, position):
        """设置预设位置"""
        self.position_entry.delete(0, tk.END)
        self.position_entry.insert(0, str(position))
        self.set_position()

    def update_ui_safely(self, update_func):
        """安全地更新UI（从非主线程调用）"""
        self.root.after(0, update_func)

    def handle_operation_error(self, operation_name: str, error: Exception):
        """统一处理操作错误"""
        error_msg = f"{operation_name}失败: {str(error)}"
        logger.info(error_msg)  # 调试输出
        self.update_ui_safely(lambda: messagebox.showerror("操作错误", error_msg))

    def on_closing(self):
        """窗口关闭事件"""
        try:
            # 设置关闭事件，停止所有监控线程
            self.shutdown_event.set()

            # 断开连接
            if self.controller:
                future = self.run_async(self.disconnect_device())
                if future:
                    try:
                        future.result(timeout=2)  # 等待断开连接完成
                    except:
                        pass  # 忽略断开连接时的错误

            # 停止事件循环
            if self.loop:
                self.loop.call_soon_threadsafe(self.loop.stop)

            # 等待线程结束
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=3)  # 增加超时时间

        except Exception as e:
            logger.error(f"关闭时发生错误: {e}")
        finally:
            self.root.destroy()

    def create_do1_frame(self, notebook):
        """创建DO1控制标签页"""
        do1_frame = tk.Frame(notebook, bg='#f0f0f0')
        notebook.add(do1_frame, text="DO1 数字输出1")

        # 标题
        title = tk.Label(do1_frame, text="DO1 输出端口控制 (0-7)",
                        font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
        title.pack(pady=10)

        # DO1控制按钮网格
        do1_grid = tk.Frame(do1_frame, bg='#f0f0f0')
        do1_grid.pack(pady=10)

        for i in range(8):
            row, col = i // 4, i % 4

            button_frame = tk.Frame(do1_grid, bg='#f0f0f0')
            button_frame.grid(row=row, column=col, padx=10, pady=10)

            # 端口标签
            port_label = tk.Label(button_frame, text=f"DO1[{i}]",
                                font=('微软雅黑', 10, 'bold'), bg='#f0f0f0')
            port_label.pack()

            # 开关按钮
            btn = tk.Button(button_frame, text="关闭", width=8, height=2,
                          command=lambda idx=i: self.toggle_do1(idx),
                          bg='#e74c3c', fg='white',
                          font=('微软雅黑', 9, 'bold'))
            btn.pack(pady=5)

            # 保存按钮引用
            setattr(self, f'do1_btn_{i}', btn)

        # 添加自动顺序开启按钮
        auto_frame = tk.Frame(do1_frame, bg='#f0f0f0')
        auto_frame.pack(pady=10)
        
        self.auto_do1_btn = tk.Button(auto_frame, text="▶️ 自动顺序开启DO1",
                                     command=self.auto_sequence_do1,
                                     bg='#3498db', fg='white',
                                     font=('微软雅黑', 10, 'bold'),
                                     width=20, height=2)
        self.auto_do1_btn.pack(pady=5)
    def create_do2_frame(self, notebook):
        """创建DO2控制标签页"""
        do2_frame = tk.Frame(notebook, bg='#f0f0f0')
        notebook.add(do2_frame, text="DO2 数字输出2")

        # 标题
        title = tk.Label(do2_frame, text="DO2 输出端口控制 (0-7)",
                        font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
        title.pack(pady=10)

        # DO2控制按钮网格
        do2_grid = tk.Frame(do2_frame, bg='#f0f0f0')
        do2_grid.pack(pady=10)

        for i in range(8):
            row, col = i // 4, i % 4

            button_frame = tk.Frame(do2_grid, bg='#f0f0f0')
            button_frame.grid(row=row, column=col, padx=10, pady=10)

            # 端口标签
            port_label = tk.Label(button_frame, text=f"DO2[{i}]",
                                font=('微软雅黑', 10, 'bold'), bg='#f0f0f0')
            port_label.pack()

            # 开关按钮
            btn = tk.Button(button_frame, text="关闭", width=8, height=2,
                          command=lambda idx=i: self.toggle_do2(idx),
                          bg='#e74c3c', fg='white',
                          font=('微软雅黑', 9, 'bold'))
            btn.pack(pady=5)

            # 保存按钮引用
            setattr(self, f'do2_btn_{i}', btn)

        # 添加自动顺序开启按钮
        auto_frame = tk.Frame(do2_frame, bg='#f0f0f0')
        auto_frame.pack(pady=10)
        
        self.auto_do2_btn = tk.Button(auto_frame, text="▶️ 自动顺序开启DO2",
                                     command=self.auto_sequence_do2,
                                     bg='#3498db', fg='white',
                                     font=('微软雅黑', 10, 'bold'),
                                     width=20, height=2)
        self.auto_do2_btn.pack(pady=5)
    def set_position_preset(self, position):
        """设置预设位置"""
        self.position_entry.delete(0, tk.END)
        self.position_entry.insert(0, str(position))
        self.set_position()

    def auto_sequence_do1(self):
        """自动顺序开启DO1端口，每个间隔1秒"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        # 禁用按钮防止重复点击
        self.auto_do1_btn.config(state='disabled', text="执行中...")
        
        def sequence_operation():
            try:
                for i in range(8):
                    # 在主线程中更新UI
                    idx = i
                    self.update_ui_safely(lambda idx=idx: self.highlight_do1_button(idx))
                    
                    # 设置DO1状态
                    def set_do1_operation(controller):
                        controller.set_do1_command(idx, True)
                        return controller.send1_command()
                    
                    future = self.run_async(self.with_controller(set_do1_operation))
                    if future:
                        future.result()  # 等待发送完成
                    
                    # 等待1秒
                    time.sleep(1)
                
                # 完成后重新启用按钮
                self.update_ui_safely(lambda: self.auto_do1_btn.config(state='normal', text="▶️ 自动顺序开启DO1"))
                self.update_ui_safely(lambda: messagebox.showinfo("完成", "DO1端口已全部开启"))
            except Exception as e:
                self.update_ui_safely(lambda: self.auto_do1_btn.config(state='normal', text="▶️ 自动顺序开启DO1"))
                self.handle_operation_error("自动顺序开启DO1", e)

        # 在新线程中执行序列操作
        threading.Thread(target=sequence_operation, daemon=True).start()

    def auto_sequence_do2(self):
        """自动顺序开启DO2端口，每个间隔1秒"""
        if not self.is_controller_connected():
            messagebox.showwarning("警告", "请先连接设备")
            return

        # 禁用按钮防止重复点击
        self.auto_do2_btn.config(state='disabled', text="执行中...")
        
        def sequence_operation():
            try:
                for i in range(8):
                    # 在主线程中更新UI
                    idx = i
                    self.update_ui_safely(lambda idx=idx: self.highlight_do2_button(idx))
                    
                    # 设置DO2状态
                    def set_do2_operation(controller):
                        controller.set_do_command(idx, True)
                        return controller.send1_command()
                    
                    future = self.run_async(self.with_controller(set_do2_operation))
                    if future:
                        future.result()  # 等待发送完成
                    
                    # 等待1秒
                    time.sleep(1)
                
                # 完成后重新启用按钮
                self.update_ui_safely(lambda: self.auto_do2_btn.config(state='normal', text="▶️ 自动顺序开启DO2"))
                self.update_ui_safely(lambda: messagebox.showinfo("完成", "DO2端口已全部开启"))
            except Exception as e:
                self.update_ui_safely(lambda: self.auto_do2_btn.config(state='normal', text="▶️ 自动顺序开启DO2"))
                self.handle_operation_error("自动顺序开启DO2", e)

        # 在新线程中执行序列操作
        threading.Thread(target=sequence_operation, daemon=True).start()

    def highlight_do1_button(self, index):
        """高亮显示当前正在操作的DO1按钮"""
        btn = getattr(self, f'do1_btn_{index}')
        original_color = btn.cget('bg')
        btn.config(bg='#f39c12')  # 橙色表示正在操作
        
        # 1秒后恢复原色
        def restore_color():
            if btn.winfo_exists():  # 检查按钮是否仍然存在
                try:
                    current_state = self.do1_states[index].get() if index < len(self.do1_states) else False
                    color = '#27ae60' if current_state else '#e74c3c'
                    btn.config(bg=color)
                except:
                    btn.config(bg=original_color)
        
        self.root.after(1000, restore_color)

    def highlight_do2_button(self, index):
        """高亮显示当前正在操作的DO2按钮"""
        btn = getattr(self, f'do2_btn_{index}')
        original_color = btn.cget('bg')
        btn.config(bg='#f39c12')  # 橙色表示正在操作
        
        # 1秒后恢复原色
        def restore_color():
            if btn.winfo_exists():  # 检查按钮是否仍然存在
                try:
                    current_state = self.do2_states[index].get() if index < len(self.do2_states) else False
                    color = '#27ae60' if current_state else '#e74c3c'
                    btn.config(bg=color)
                except:
                    btn.config(bg=original_color)
        
        self.root.after(1000, restore_color)
    def run(self):
        """运行GUI应用程序"""
        self.root.mainloop()


def main():
    """主函数"""
    app = IoControllerGUI()
    app.run()


if __name__ == "__main__":
    main()