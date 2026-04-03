import asyncio
import struct
from typing import List, Tuple, Optional, Callable
import threading
import time
import queue
from collections import deque
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
# from cv2 import log
from logs.logger_utils import logger

class ThreadedHeartbeatManager:
    """线程化的心跳包管理器 - Linus式简洁设计"""

    def __init__(self, tcp_client):
        self.tcp_client = tcp_client
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.command_queue = queue.Queue(maxsize=100)  # 跨线程通信队列
        self.is_running = False

    def start(self):
        """启动心跳包线程"""
        if self.is_running:
            return

        self.stop_event.clear()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,  # 守护线程，主程序退出时自动结束
            name="HeartbeatThread"
        )
        self.heartbeat_thread.start()
        self.is_running = True
        logger.info("心跳包线程已启动")

    def stop(self):
        """停止心跳包线程"""
        if not self.is_running:
            return

        self.stop_event.set()
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2.0)
        self.is_running = False
        logger.info("心跳包线程已停止")

    def send_command_async(self, command_frame: bytes) -> None:
        """异步发送命令（从主线程调用）"""
        try:
            self.command_queue.put_nowait(command_frame)
            logger.debug(f"发送数据: {command_frame.hex()}")

        except queue.Full:
            logger.warning("警告：命令队列已满，丢弃命令")

    def _heartbeat_loop(self):
        """心跳包线程主循环 - 在独立线程中运行"""
        heartbeat_data = bytearray([0xF4, 0x03, 0x00, 0x03])
        last_heartbeat_time = 0
        heartbeat_interval = 0.5  # 500ms间隔

        logger.info("心跳包线程开始运行")

        while not self.stop_event.is_set():
            try:
                current_time = time.time()

                # 检查TCP连接状态，如果断开则停止心跳包
                if not self.tcp_client.is_connected:
                    logger.info("TCP连接已断开，心跳包线程自动停止")
                    break

                # 处理命令队列（优先级高于心跳包）
                command_processed = False
                try:
                    command_frame = self.command_queue.get_nowait()
                    # 发送前再次检查连接状态
                    if self.tcp_client.is_connected:
                        self._send_frame_sync(command_frame)
                        command_processed = True
                    # 发送命令后短暂等待，避免与心跳包冲突
                    time.sleep(0.1)
                except queue.Empty:
                    pass

                # 如果处理了命令，跳过本次心跳包发送
                if command_processed:
                    continue

                # 发送心跳包
                if current_time - last_heartbeat_time >= heartbeat_interval:
                    # 发送前检查连接状态
                    if self.tcp_client.is_connected:
                        self._send_frame_sync(heartbeat_data)
                        last_heartbeat_time = current_time
                    else:
                        logger.info("TCP连接已断开，心跳包线程自动停止")
                        break

                # 短暂休眠，避免CPU占用过高
                time.sleep(0.05)

            except Exception as ex:
                logger.error(f"心跳包线程异常: {ex}")
                time.sleep(1.0)  # 出错后等待更时间

    def _send_frame_sync(self, frame: bytes) -> bool:
        """同步发送数据帧（在心跳线程中使用）"""
        try:
            # 创建新的事件循环用于这个线程
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 在新循环中运行协程
            try:
                result = loop.run_until_complete(
                    self.tcp_client.send_data_async(frame)
                )
                return True
            finally:
                loop.close()

        except Exception as ex:
            logger.error(f"发送帧失败: {ex}")
            return False

class TcpClient:
    """TCP客户端类，用于异步连接、发送和接收数据"""
    
    def __init__(self):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._is_connected: bool = False
        self._packet_received_callback: Optional[Callable[[bytes, int], None]] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._cancellationToken: Optional[asyncio.Event] = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def set_packet_received_callback(self, callback: Callable[[bytes, int], None]) -> None:
        """设置数据包接收回调函数"""
        self._packet_received_callback = callback

    # async def connect_async(self, ip: str = "10.10.100.254", port: int = 2317, timeout: float = 10.0) -> None:
    async def connect_async(self, ip: str = "192.168.0.21", port: int = 8899, timeout: float = 10.0) -> None:
        """异步连接到指定服务器，带超时参数"""
        if self._is_connected:
            await self.disconnect_async()

        try:
            # 带超时的连接
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout
            )
            self._is_connected = True
            self._cancellationToken = asyncio.Event()
            # 启动接收任务
            self._receive_task = asyncio.create_task(self._start_receiving())
        except asyncio.TimeoutError:
            raise RuntimeError(f"连接超时（{timeout}秒），请检查设备是否在线")
        except Exception as ex:
            raise RuntimeError(f"连接失败: {str(ex)}") from ex

    async def _start_receiving(self) -> None:
        """后台接收数据循环，增加错误处理"""
        assert self._reader is not None, "未初始化读取器"
        assert self._cancellationToken is not None, "未初始化取消令牌"

        while not self._cancellationToken.is_set() and self._is_connected:
            try:
                # 读取数据（设置超时避免无限阻塞）
                data = await asyncio.wait_for(
                    self._reader.read(50),  # 与C#缓冲区大小一致
                    timeout=0.05
                )
                if data:
                    # 触发回调
                    if self._packet_received_callback:
                        self._packet_received_callback(data, len(data))
                else:
                    # 服务器断开连接
                    await self.disconnect_async()
            except asyncio.TimeoutError:
                # 超时继续循环
                continue
            except Exception as ex:
                logger.error(f"接收数据错误: {str(ex)}")
                await self.disconnect_async()

    async def send_data_async(self, data: bytes) -> None:
        """异步发送数据，增加错误处理"""
        if not self._is_connected:
            raise RuntimeError("未连接到服务器")
        if not self._writer:
            raise RuntimeError("写入器未初始化")

        try:
            self._writer.write(data)
            await self._writer.drain()
        except Exception as ex:
            await self.disconnect_async()
            raise RuntimeError(f"发送数据失败: {str(ex)}") from ex

    async def disconnect_async(self) -> None:
        """异步断开连接，确保资源释放"""
        if not self._is_connected:
            return

        self._is_connected = False
        if self._cancellationToken:
            self._cancellationToken.set()

        try:
            if self._writer:
                self._writer.close()
                await self._writer.wait_closed()
            self._reader = None
            self._writer = None
        except Exception as ex:
            logger.error(f"断开连接错误: {str(ex)}")

        # 等待接收任务结束
        if self._receive_task:
            await asyncio.wait([self._receive_task], timeout=0.1)

        # 关键修复：断开连接时停止心跳包线程
        # 这里不能直接调用，因为我们在TCP客户端中，需要通知IoController
        # 但我们可以检查是否有心跳管理器正在运行
        logger.info("TCP连接已断开，心跳包线程会自动检测到连接状态变化")


class IoController:
    """IO控制器类，管理工业设备的IO状态和命令发送"""
    # 通信协议相关常量
    FRAME_HEADER: int = 0xF4
    SEND_FRAME_LENGTH: int = 9        # 发送帧长度(不含帧头)
    RECEIVE_FRAME_LENGTH: int = 14    # 接收帧长度（新增4字节激光距离）
    SEND_DATA_LENGTH: int = 0x09      # 发送帧长度字段
    RECEIVE_DATA_LENGTH: int = 0x0D   # 接收帧长度字段（13字节数据 = 0x0D）
    SEND_CHECKSUM_RANGE: int = 8      # 发送帧校验和计算范围(位置0-7)
    RECEIVE_CHECKSUM_RANGE: int = 13  # 接收帧校验和计算范围(位置1-12，新增激光距离后)
    FORCE_SENSOR_COUNT: int = 0       # 力传感器数量
    DO_COUNT: int = 8                 # DO2通道数量(原DO)
    
    def __init__(self):      # 控制器模式(1为小车/2为机器人/3为电梯)
        # 初始化TCP客户端
        self._tcp_client = TcpClient()
        self._tcp_client.set_packet_received_callback(self._handle_data_received)
        self.is_connected: bool = False

        # 初始化状态缓存
        self._initialize_states()

        # 释放标志
        self._disposed: bool = False

        # 初始化心跳线程管理器
        self._heartbeat_manager: Optional[ThreadedHeartbeatManager] = None
        
        # 指令发送队列和相关变量
        self._send_queue = deque()  # 发送指令队列
        self._queue_lock = asyncio.Lock()  # 队列操作锁
        self._sending_from_queue = False  # 是否正在从队列发送

        # ACK确认相关变量
        self._ack_event: Optional[asyncio.Event] = None  # ACK等待事件
        self._command_lock = asyncio.Lock()  # 命令串行锁
        self._last_received_time = None

    def _initialize_states(self) -> None:
        """初始化状态和命令缓存"""
        # DO状态
        self._do1_state: List[bool] = [False] * 8
        self._do1_command: List[bool] = [False] * 8
        self._do2_state: List[bool] = [False] * self.DO_COUNT  # 原DO
        self._do2_command: List[bool] = [False] * self.DO_COUNT

        # DI电机状态
        self._di_motor_state: int = 0
        self._di_motor_command: int = 0

        # 电机绝对位置(float类型)
        self._motor_absolute_position: float = 0.0
        self._motor_absolute_position_command: float = 0.0

        # 激光传感器距离(float类型，单位：毫米)
        self._laser_distance: float = 0.0

    def float_to_bytes(self, value: float) -> bytes:
        """将float转换为4字节数组(大端序)"""
        return struct.pack('>f', value)

    def bytes_to_float(self, data: bytes) -> float:
        """将4字节数组转换为float(大端序)"""
        if len(data) < 4:
            raise ValueError("数据长度不足4字节")
        return struct.unpack('>f', data[:4])[0]

    def int_to_byte(self, value: int) -> int:
        """将整数限制在字节范围内"""
        return value & 0xFF

    @property
    def do_state(self) -> List[bool]:
        """只读DO状态访问接口(映射到DO2，保持向后兼容)"""
        return self._do2_state.copy()

    def get_do2_state(self, index: int) -> bool:
        """获取DO2指定通道状态"""
        if index < 0 or index >= 8:
            raise IndexError(f"DO2通道索引超出范围（0-7）")
        return self._do2_state[index]

    def get_do2_states(self) -> List[bool]:
        """获取DO2所有通道状态"""
        return self._do2_state.copy()

    # 电机绝对位置控制
    def set_motor_absolute_position(self, position: float) -> None:
        """设置电机绝对位置(float类型)"""
        self._motor_absolute_position_command = position

    def get_motor_absolute_position(self) -> float:
        """获取当前电机绝对位置"""
        return self._motor_absolute_position

    # 激光传感器距离接口（只读）
    def get_laser_distance(self) -> float:
        """获取激光传感器距离（单位：毫米）"""
        return self._laser_distance

    # DO1控制接口
    def set_do1_command(self, index: int, value: bool) -> None:
        """设置DO1指定通道的命令状态"""
        if index < 0 or index >= 8:
            raise IndexError(f"DO1通道索引超出范围（0-7）")
        self._do1_command[index] = value
        self._do1_state[index] = value  # 同步状态

    def set_do1_command_by_byte(self, value: int) -> None:
        """通过字节值设置DO1命令"""
        for i in range(8):
            bit_value = (value & (1 << i)) != 0
            self._do1_command[i] = bit_value
            self._do1_state[i] = bit_value  # 同步状态

    def get_do1_state(self, index: int) -> bool:
        """获取DO1指定通道状态"""
        if index < 0 or index >= 8:
            raise IndexError(f"DO1通道索引超出范围（0-7）")
        return self._do1_state[index]

    def get_do1_states(self) -> List[bool]:
        """获取DO1所有通道状态"""
        return self._do1_state.copy()

    # DO2控制接口(原DO，保持向后兼容)
    def set_do_command(self, index: int, value: bool) -> None:
        """设置DO2通道的命令状态(原DO功能，保持向后兼容)"""
        if index < 0 or index >= self.DO_COUNT:
            raise IndexError(f"DO2通道索引超出范围（0-{self.DO_COUNT-1}）")
        self._do2_command[index] = value

    def set_do_command_by_byte(self, value: int) -> None:
        """通过字节值设置DO2命令(原DO功能，保持向后兼容)"""
        for i in range(8):
            self._do2_command[i] = (value & (1 << i)) != 0

    # DI电机状态接口
    def get_di_motor_state(self) -> int:
        """获取DI电机状态"""
        return self._di_motor_state

    def set_di_motor_command(self, state: int) -> None:
        """设置DI电机控制命令"""
        self._di_motor_command = self.int_to_byte(state)

# 在IoController类的connect_async方法中添加状态同步逻辑
    async def ping_device(self, ip: str = "192.168.0.21", port: int = 8899, timeout: float = 3.0) -> bool:
        """在连接前ping设备以检查是否可达"""
        try:
            # 尝试建立一个连接来测试设备可达性
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout
            )
            # 立即关闭连接
            writer.close()
            await writer.wait_closed()
            logger.info(f"设备 {ip}:{port} 可达")
            return True
        except Exception as e:
            logger.warning(f"设备 {ip}:{port} 不可达: {str(e)}")
            return False

    async def connect_async(self, ip: str = "192.168.0.21", port: int = 8899, timeout: float = 10.0) -> None:
        self._throw_if_disposed()

        # 移除多余的ping检查，直接尝试连接
        # 连接本身就能验证设备可达性，ping反而制造TIME_WAIT问题

        # 尝试连接，如果失败则重试
        max_retries = 10
        for attempt in range(max_retries):
            try:
                await self._tcp_client.connect_async(ip, port, timeout)
                self.is_connected = self._tcp_client.is_connected
                
                if self.is_connected:
                    self._start_heartbeat_task()
                    # 发送一个心跳包来确认设备连接正常
                    heartbeat_data = bytearray([0xF4, 0x03, 0x00, 0x03])
                    if self._heartbeat_manager:
                        self._heartbeat_manager.send_command_async(heartbeat_data)
                    
                    # 等待设备发送状态数据（最多等待1.5秒）
                    for _ in range(30):  # 30次重试，每次间隔50ms
                        # 检查是否接收到有效的设备数据
                        if (hasattr(self, '_last_received_time') and 
                            self._last_received_time is not None):
                            import time
                            if time.time() - self._last_received_time < 1.5:  # 1.5秒内接收到数据
                                logger.info("成功接收到设备状态数据，连接正常")
                                return  # 成功连接，直接返回
                        await asyncio.sleep(0.05)
                    else:
                        logger.warning(f"第{attempt + 1}次连接：建立成功，但未能在预期时间内接收到设备状态数据")
                        # 如果连接建立但没有收到数据，尝试断开并重连
                        await self.disconnect_async()
                        
            except Exception as e:
                logger.error(f"第{attempt + 1}次连接尝试失败: {str(e)}")
                if attempt < max_retries - 1:  # 不是最后一次尝试
                    await asyncio.sleep(0.5)  # 等待0.5秒后重试
                else:
                    raise  # 最后一次尝试失败，抛出异常
        
        # 如果所有尝试都失败了
        raise RuntimeError(f"经过{max_retries}次尝试后仍然无法建立稳定连接")

    async def disconnect_async(self) -> None:
        """异步断开连接，确保心跳包停止"""
        if not self.is_connected:
            return

        # 关键修复：先停止心跳包线程
        self._stop_heartbeat_task()

        # 然后断开TCP连接
        await self._tcp_client.disconnect_async()
        self.is_connected = False

        logger.info("IO控制器已断开连接，心跳包已停止")
    def _start_heartbeat_task(self) -> None:
        """启动心跳包发送任务"""
        if self._heartbeat_manager is None:
            self._heartbeat_manager = ThreadedHeartbeatManager(self._tcp_client)

        if not self._heartbeat_manager.is_running:
            self._heartbeat_manager.start()

    def _stop_heartbeat_task(self) -> None:
        """停止心跳包任务"""
        if self._heartbeat_manager and self._heartbeat_manager.is_running:
            self._heartbeat_manager.stop()

    def inner_update(self) -> None:
        """内部状态刷新，确保命令与状态一致"""
        # DO1同步
        for i in range(8):
            self._do1_command[i] = self._do1_state[i]

        # DO2同步(原DO)
        for i in range(len(self._do2_command)):
            self._do2_command[i] = self._do2_state[i]

        # DI电机同步
        self._di_motor_command = self._di_motor_state

        # 电机绝对位置同步
        self._motor_absolute_position_command = self._motor_absolute_position

    def _handle_data_received(self, buffer: bytes, length: int) -> None:
        """处理接收到的数据包(新帧结构22字节)"""
        # 更新最后接收时间
        import time
        self._last_received_time = time.time()
        # 新增：首先识别3字节ACK确认帧 [0xF4][0x02][0x02]
        if length == 3 and buffer[0] == 0xF4 and buffer[1] == 0x02 and buffer[2] == 0x02:
            logger.info("收到ACK确认帧 [0xF4][0x02][0x02]")
            if hasattr(self, '_ack_event') and self._ack_event:
                self._ack_event.set()  # 立即唤醒等待
            return  # 处理完ACK帧就返回，不继续处理数据帧

        # 定义可能的帧头
        # header_mode1 = bytearray.fromhex("001CB943")
        # header_mode2 = bytearray.fromhex("001C7CDB")
        # header_mode3 = bytearray.fromhex("001D84B3")
        # original_header_length = 4  # 新帧头长度

        # # 检查并移除帧头
        # if self.mode ==1 and buffer.startswith(header_mode1):
        #     # 移除帧头
        #     buffer = buffer[original_header_length:]
        #     length -= original_header_length
        # elif self.mode ==2 and buffer.startswith(header_mode2):
        #     # 移除帧头
        #     buffer = buffer[original_header_length:]
        #     length -= original_header_length
        # elif self.mode ==3 and buffer.startswith(header_mode3):
        #     # 移除帧头
        #     buffer = buffer[original_header_length:]
        #     length -= original_header_length


        # logger.info(f"接收到数据帧: {buffer.hex()}"+"/n")
        # logger.info(f"接收到数据帧: {buffer}")
        # 验证数据帧格式

            
        if length < self.RECEIVE_FRAME_LENGTH:
            # logger.warning(f"接收到不完整的数据帧，长度: {length}, 期望: {self.RECEIVE_FRAME_LENGTH}")
            return

        if buffer[0] != self.FRAME_HEADER:
            logger.warning(f"无效的数据帧头，预期: {self.FRAME_HEADER}, 实际: {buffer[0]}")
            return

        if buffer[1] != self.RECEIVE_DATA_LENGTH:
            # logger.warning(f"数据帧长度不匹配，预期: {self.RECEIVE_DATA_LENGTH}, 实际: {buffer[1]}")
            return
        #logger.info(f"{buffer.hex()}")
        # 校验和检查(校验位置1-8的和)
        check_sum = self._calculate_checksum(buffer, 1, self.RECEIVE_CHECKSUM_RANGE)
        if check_sum != buffer[self.RECEIVE_CHECKSUM_RANGE]:
            logger.warning(f"校验和不匹配，预期: {check_sum}, 实际: {buffer[self.RECEIVE_CHECKSUM_RANGE]}")
            return

        # 解析数据部分(跳过帧头和帧长)
        # DO1状态(8位)
        do1_byte = buffer[2]
        for i in range(8):
            self._do1_state[i] = ((do1_byte >> i) & 1) == 1
            self._do1_command[i] = self._do1_state[i]

        # DO2状态(原DO)
        do2_byte = buffer[3]
        for i in range(self.DO_COUNT):
            self._do2_state[i] = ((do2_byte >> i) & 1) == 1
            self._do2_command[i] = self._do2_state[i]

        # DI电机状态
        self._di_motor_state = buffer[4]
        self._di_motor_command = self._di_motor_state

        # 电机绝对位置(4字节float)
        motor_bytes = buffer[5:9]
        # logger.info(f"电机绝对位置: {motor_bytes}")
        self._motor_absolute_position = self.bytes_to_float(motor_bytes)
        # logger.info(f"电机绝对位置: {self._motor_absolute_position}")
        self._motor_absolute_position = self._motor_absolute_position
        # 激光传感器距离(4字节float，单位：毫米)
        laser_bytes = buffer[9:13]
        self._laser_distance = self.bytes_to_float(laser_bytes)
        self._laser_distance+=250
        self._laser_distance = self._laser_distance/1000
        # logger.info(f"激光传感器距离: {self._laser_distance:.4f} m")

    def _calculate_checksum(self, buffer: bytes, start: int, end: int) -> int:
        """计算数据帧的校验和"""
        check_sum = 0
        for i in range(start, end):
            if i < len(buffer):
                check_sum += buffer[i]
        return check_sum & 0xFF  # 确保是字节范围

    # async def send_command(self) -> None:
    #     """发送控制命令到设备(新帧结构9字节)"""
    #     self._throw_if_disposed()

    #     # 构建9字节命令数据帧
    #     buffer = bytearray(self.SEND_FRAME_LENGTH)
    #     buffer[0] = self.SEND_DATA_LENGTH               # 帧长(0x09)
    #     buffer[1] = self._build_do1_command_byte()       # DO1状态(8位)
    #     buffer[2] = self._build_do2_command_byte()       # DO2状态(原DO)
    #     buffer[3] = self.int_to_byte(self._di_motor_command)        # DI电机状态

    #     # 电机绝对位置(4字节float)
    #     motor_bytes = self.float_to_bytes(self._motor_absolute_position_command)
    #     buffer[4] = motor_bytes[0]
    #     buffer[5] = motor_bytes[1]
    #     buffer[6] = motor_bytes[2]
    #     buffer[7] = motor_bytes[3]

    #     buffer[8] = self._calculate_checksum(buffer, 0, self.SEND_CHECKSUM_RANGE)  # 校验和(位置1-8的和)

    #     # 在帧前添加帧头发送
    #     full_frame = bytearray(self.SEND_FRAME_LENGTH + 1)
    #     full_frame[0] = self.FRAME_HEADER
    #     full_frame[1:] = buffer
    #     # # 根据mode值添加额外的帧头
    #     # if self.mode == 1:
    #     #     # 添加帧头001CB943
    #     #     header = bytearray.fromhex("001CB943")
    #     #     full_frame = header + full_frame
    #     # elif self.mode == 2:
    #     #     # 添加帧头001C7CDB
    #     #     header = bytearray.fromhex("001C7CDB")
    #     #     full_frame = header + full_frame
    #     # elif self.mode == 3:
    #     #     # 添加帧头001D84B3
    #     #     header = bytearray.fromhex("001D84B3")
    #     #     full_frame = header + full_frame

    #     # 通过心跳线程管理器发送命令，避免与心跳包冲突
    #     if self._heartbeat_manager:
    #         self._heartbeat_manager.send_command_async(full_frame)

    #         # 短暂等待确保命令发送完成
    #         await asyncio.sleep(0.05)
    #     else:
    #         # 如果心跳管理器未启动，使用原来的方式（降级处理）
    #         await self._tcp_client.send_data_async(full_frame)


    async def send1_command(self) -> None:
        """发送控制命令到设备(新帧结构9字节) - 带ACK确认重试机制"""
        self._throw_if_disposed()

        # 构建命令数据帧
        def build_frame():
            buffer = bytearray(5)
            buffer[0] = 0x05               # 帧长(0x05)
            buffer[1] = 0x01                # 帧类型(0x01)
            buffer[2] = self._build_do1_command_byte()       # DO1状态(8位)
            buffer[3] = self._build_do2_command_byte()       # DO2状态(原DO)
            buffer[4] = self._calculate_checksum(buffer, 0, 5)       # DI电机状态
            # 在帧前添加帧头发送
            full_frame = bytearray(6)
            full_frame[0] = self.FRAME_HEADER
            full_frame[1:] = buffer
            return full_frame

        full_frame = build_frame()
        logger.info(f"发送数据: {full_frame.hex()}")

        # ACK确认重试机制（最多5次）
        async with self._command_lock:  # 确保命令串行发送
            for attempt in range(10):
                try:
                    # 创建ACK等待事件
                    self._ack_event = asyncio.Event()

                    # 发送命令
                    if self._heartbeat_manager:
                        self._heartbeat_manager.send_command_async(full_frame)
                        await asyncio.sleep(0.05)  # 确保命令发送完成
                    else:
                        await self._tcp_client.send_data_async(full_frame)

                    # 等待ACK确认，最长0.5秒
                    await asyncio.wait_for(self._ack_event.wait(), timeout=0.2)
                    logger.info("send1命令ACK确认成功")
                    return  # 成功则返回

                except asyncio.TimeoutError:
                    logger.warning(f"send1命令ACK超时，重试 {attempt + 1}/10")
                    if attempt < 10:  # 前10次重试
                        await asyncio.sleep(0.1)  # 重试前短暂等待
                        continue
                    else:  # 第10次失败
                        raise RuntimeError("send1命令发送失败：10次重试后未收到ACK确认")
                finally:
                    self._ack_event = None
    
    async def send2_command(self) -> None:
        """发送控制命令到设备(新帧结构9字节) - 带ACK确认重试机制"""
        self._throw_if_disposed()

        # 构建命令数据帧
        def build_frame():
            buffer = bytearray(8)
            buffer[0] = 0x08              # 帧长(0x08)
            buffer[1] = 0x02               # 帧类型(0x02)
            buffer[2] = self.int_to_byte(self._di_motor_command)        # DI电机状态

            # 电机绝对位置(4字节float)
            motor_bytes = self.float_to_bytes(self._motor_absolute_position_command)
            print(f"电机绝对位置命令: {self._motor_absolute_position_command}, 转换为字节: {motor_bytes.hex()}")
            test=self.bytes_to_float(motor_bytes)
            print(f"从字节转换回float: {test}")
            
            buffer[3] = motor_bytes[0]
            buffer[4] = motor_bytes[1]
            buffer[5] = motor_bytes[2]
            buffer[6] = motor_bytes[3]

            buffer[7] = self._calculate_checksum(buffer, 0, 8)  # 校验和(位置1-8的和)
            print(f"send2命令帧内容: {buffer.hex()}")

            # 在帧前添加帧头发送
            full_frame = bytearray(9)
            full_frame[0] = self.FRAME_HEADER
            full_frame[1:] = buffer
            return full_frame

        full_frame = build_frame()
        logger.info(f"发送数据: {full_frame.hex()}")

        # ACK确认重试机制（最多3次）
        async with self._command_lock:  # 确保命令串行发送
            for attempt in range(10):
                try:
                    # 创建ACK等待事件
                    self._ack_event = asyncio.Event()

                    # 发送命令
                    if self._heartbeat_manager:
                        self._heartbeat_manager.send_command_async(full_frame)
                        await asyncio.sleep(0.05)  # 确保命令发送完成
                    else:
                        await self._tcp_client.send_data_async(full_frame)

                    # 等待ACK确认，最长0.5秒
                    await asyncio.wait_for(self._ack_event.wait(), timeout=0.2)
                    #logger.info("send2命令ACK确认成功")
                    return  # 成功则返回

                except asyncio.TimeoutError:
                    logger.warning(f"send2命令ACK超时，重试 {attempt + 1}/10")
                    if attempt < 10:  # 前两次重试
                        await asyncio.sleep(0.1)  # 重试前短暂等待
                        continue
                    else:  # 第10次失败
                        raise RuntimeError("send2命令发送失败：10次重试后未收到ACK确认")
                finally:
                    self._ack_event = None

    
    async def _process_send_queue(self) -> None:
        """处理发送队列中的指令"""
        async with self._queue_lock:
            # 如果已经在处理队列，则直接返回
            if self._sending_from_queue:
                return
            self._sending_from_queue = True

        try:
            while True:
                # 获取队列中的下一个指令
                await asyncio.sleep(0.05)  # 短暂等待，等待心跳包发送的回执到达后在发送下一个指令
                async with self._queue_lock:
                    if not self._send_queue:
                        break
                    frame_to_send = self._send_queue.popleft()
                
                # 发送指令
                logger.info(f"发送命令帧: {frame_to_send.hex()}")
                await self._tcp_client.send_data_async(frame_to_send)
                
                # # 指令之间添加短暂延迟
                # await asyncio.sleep(0.5)
        finally:
            async with self._queue_lock:
                self._sending_from_queue = False

    def _build_do1_command_byte(self) -> int:
        """将DO1命令状态转换为命令字节"""
        do1_command_byte = 0
        for i in range(8):
            if self._do1_command[i]:
                do1_command_byte |= 1 << i
        return do1_command_byte

    def _build_do2_command_byte(self) -> int:
        """将DO2命令状态转换为命令字节(原DO功能)"""
        do2_command_byte = 0
        for i in range(self.DO_COUNT):
            if self._do2_command[i]:
                do2_command_byte |= 1 << i
        return do2_command_byte

    def _throw_if_disposed(self) -> None:
        """检查对象是否已释放"""
        if self._disposed:
            raise RuntimeError("IoController已被释放")


    async def close(self) -> None:
        """释放资源，确保连接关闭"""
        if not self._disposed:
            self._disposed = True

            # 停止心跳线程管理器
            if self._heartbeat_manager:
                self._stop_heartbeat_task()
                self._heartbeat_manager = None

            # 兼容性：确保旧的异步心跳任务也被清理
            if hasattr(self, '_heartbeat_task') and self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            await self._tcp_client.disconnect_async()
            self.is_connected = False

    async def __aenter__(self) -> 'IoController':
        """异步上下文管理器进入"""
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """异步上下文管理器退出"""
        await self.close()

    def __del__(self) -> None:
        """析构函数，确保资源释放"""
        try:
            # 检查是否在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 如果在事件循环中，安排清理任务但不等待
                if not self._disposed:
                    loop.create_task(self._async_cleanup())
            except RuntimeError:
                # 没有运行中的事件循环，可以安全使用 asyncio.run
                if not self._disposed:
                    asyncio.run(self.close())
        except Exception:
            # 忽略析构函数中的异常
            pass

    async def _async_cleanup(self):
        """异步清理方法"""
        try:
            await self.close()
        except Exception:
            pass


#region Lift升降机
    def _build_do2_command_byte(self) -> int:
        """将DO2命令状态转换为命令字节(原DO功能)"""
        do2_command_byte = 0
        for i in range(self.DO_COUNT):
            if self._do2_command[i]:
                do2_command_byte |= 1 << i
        return do2_command_byte

    def get_elevator_floor(self) -> int:
        """
        通过获取电梯实例中的_do2_command属性值来判断电梯在第几层
        _do2_command前3位代表楼层，是一个8进制数
        100为0层 000为1层 001为2层 010为3层 011为4层
        
        Returns:
            int: 电梯当前所在楼层 (0-4层)
        """
        # 获取_do2_command的前3位状态
        floor_bits = 0
        for i in range(3):
            if self._do2_command[i]:
                floor_bits |= (1 << i)
        
        # 将二进制转换为八进制并映射到楼层
        floor_map = {
            0b100: 0,  # 100(二进制) => 4(十进制) => 0层
            0b000: 1,  # 000(二进制) => 0(十进制) => 1层
            0b001: 2,  # 001(二进制) => 1(十进制) => 2层
            0b010: 3,  # 010(二进制) => 2(十进制) => 3层
            0b011: 4   # 011(二进制) => 3(十进制) => 4层
        }
        
        return floor_map.get(floor_bits, -1)  # 返回-1表示未知楼层
        