import asyncio
import struct
from typing import List, Tuple, Optional, Callable, AsyncIterable
from pathlib import Path
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger

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

    async def connect_async(self, ip: str = "10.10.100.254", port: int = 2317, timeout: float = 10.0) -> None:
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


class IoController:
    """IO控制器类，管理工业设备的IO状态和命令发送"""
    # 通信协议相关常量
    FRAME_HEADER: int = 0xF4  # 数据帧头
    DO_COUNT: int = 8         # DO通道数量
    FRAME_LENGTH: int = 0x05  # 数据帧长度（不含帧头和校验）

    def __init__(self):
        # 初始化TCP客户端
        self._tcp_client = TcpClient()
        self._tcp_client.set_packet_received_callback(self._handle_data_received)
        self.is_connected: bool = False

        # 初始化状态缓存
        self._initialize_states()

        # 释放标志
        self._disposed: bool = False

    def _initialize_states(self) -> None:
        """初始化状态和命令缓存"""
        self._do_state: List[bool] = [False] * self.DO_COUNT
        self._do_command: List[bool] = [False] * self.DO_COUNT
        self.tool_state: bool = False  # 工具状态（True=打开）
        self.motor_state: int = 0      # 电机状态（0=停止，100=正转，200=反转）
        self._tool_command: bool = False
        self._motor_command: int = 0

    @property
    def do_state(self) -> List[bool]:
        """只读DO状态访问接口"""
        return self._do_state.copy()

# 在IoController类的connect_async方法中添加状态同步逻辑
    async def connect_async(self, ip: str = "10.10.100.254", port: int = 2317, timeout: float = 10.0) -> None:
        self._throw_if_disposed()
        await self._tcp_client.connect_async(ip, port, timeout)
        self.is_connected = self._tcp_client.is_connected
    
        # 新增：连接后等待设备返回当前状态
        if self.is_connected:
            # 等待设备发送状态数据（最多等待1秒）
            for _ in range(10):  # 重试10次，每次间隔100ms
                if any(self._do_state):  # 检测到有非默认状态，说明已同步
                    break
                await asyncio.sleep(0.1)
    def set_do_command_by_byte(self, value: int) -> None:
        """通过字节值设置DO命令（映射到8个通道）"""
        if len(self._do_command) < 8:
            raise RuntimeError("输出口数量不足8个，无法使用字节控制")
        # 将字节的每一位映射到对应的输出口
        for i in range(8):
            self._do_command[i] = (value & (1 << i)) != 0

    def set_do_command(self, index: int, value: bool) -> None:
        """设置单个DO通道的命令状态"""
        if index < 0 or index >= self.DO_COUNT:
            raise IndexError(f"DO通道索引超出范围（0-{self.DO_COUNT-1}）")
        self._do_command[index] = value

    def set_motor_command(self, state: int) -> None:
        """设置电机控制命令"""
        if state not in (0, 100, 200):
            raise ValueError("无效的电机状态值（必须是0、100或200）")
        self._motor_command = state

    def set_tool_command(self, state: bool) -> None:
        """设置工具控制命令"""
        self._tool_command = state

    def inner_update(self) -> None:
        """内部状态刷新，确保命令与状态一致"""
        for i in range(len(self._do_command)):
            self._do_command[i] = self._do_state[i]
        self._tool_command = self.tool_state
        self._motor_command = self.motor_state

    def _handle_data_received(self, buffer: bytes, length: int) -> None:
        """处理接收到的数据包，增加日志和错误处理"""
        # 验证数据帧格式
        if length < 2:
            logger.warning(f"接收到不完整的数据帧，长度: {length}")
            return
        if buffer[0] != self.FRAME_HEADER:
            logger.warning(f"无效的数据帧头，预期: {self.FRAME_HEADER}, 实际: {buffer[0]}")
            return  # 帧头检查
        if length != buffer[1] + 1:
            logger.warning(f"数据帧长度不匹配，预期: {buffer[1]+1}, 实际: {length}")
            return  # 长度检查

        # 校验和检查
        check_sum = self._calculate_checksum(buffer, 1, buffer[1])
        if check_sum != buffer[buffer[1]]:
            logger.warning(f"校验和不匹配，预期: {check_sum}, 实际: {buffer[buffer[1]]}")
            return

        # 解析DO状态（每位表示一个DO的状态）
        if len(buffer) >= 3:
            do_byte = buffer[2]
            for i in range(self.DO_COUNT):
                self._do_state[i] = ((do_byte >> i) & 1) == 1

        # 同步命令缓存与状态
        for i in range(8):
            self._do_command[i] = self._do_state[i]

        # 解析工具和电机状态
        if len(buffer) >= 4:
            self.tool_state = buffer[3] == 1
        if len(buffer) >= 5:
            self.motor_state = buffer[4]

    def _calculate_checksum(self, buffer: bytes, start: int, end: int) -> int:
        """计算数据帧的校验和"""
        check_sum = 0
        for i in range(start, end):
            if i < len(buffer):
                check_sum += buffer[i]
        return check_sum & 0xFF  # 确保是字节范围

    async def send_command(self) -> None:
        """发送控制命令到设备，增加错误处理"""
        self._throw_if_disposed()

        # 构建命令数据帧
        buffer = bytearray(6)
        buffer[0] = self.FRAME_HEADER          # 帧头
        buffer[1] = self.FRAME_LENGTH          # 数据长度
        buffer[2] = self._build_do_command_byte()  # DO命令字节
        buffer[3] = 1 if self._tool_command else 0  # 工具命令
        buffer[4] = self._motor_command & 0xFF  # 电机命令（取低8位）
        buffer[5] = self._calculate_checksum(buffer, 1, buffer[1])  # 校验和

        try:
            await self._tcp_client.send_data_async(buffer)
        except Exception as ex:
            logger.error(f"发送命令失败: {str(ex)}")
            raise

    def _build_do_command_byte(self) -> int:
        """将DO命令状态转换为命令字节"""
        do_command_byte = 0
        for i in range(self.DO_COUNT):
            if self._do_command[i]:
                do_command_byte |= 1 << i
        return do_command_byte

    def _throw_if_disposed(self) -> None:
        """检查对象是否已释放"""
        if self._disposed:
            raise RuntimeError("IoController已被释放")

    async def close(self) -> None:
        """释放资源，确保连接关闭"""
        if not self._disposed:
            await self._tcp_client.disconnect_async()
            self._disposed = True
            self.is_connected = False

    async def __aenter__(self) -> 'IoController':
        """异步上下文管理器进入"""
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """异步上下文管理器退出"""
        await self.close()

    def __del__(self) -> None:
        """析构函数，确保资源释放"""
        if not self._disposed:
            # 非异步环境下尽量释放资源
            asyncio.run(self.close())