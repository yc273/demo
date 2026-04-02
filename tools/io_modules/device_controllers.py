import asyncio
import struct
from typing import Optional, Dict

# 定义全局变量
liyou = None  # 初始化 liyou 为 None

class Liyou:
    def __init__(self):
        # 控制器参数
        self.SERVER_IP = "192.168.0.10"
        self.SERVER_PORT = 5000
        self.SLAVE_ID = 0x01
        
        # 寄存器地址常量
        self.REG_TARGET_TORQUE = 0x0031  # 目标扭矩
        self.max = 0x0001  # 当前最大总角度
        self.REG_STATUS = 0x004A  # 状态码
        self.REG_START = 0x0040  # 启动
        self.REG_STOP = 0x0041  # 停止
        
        # 存储寄存器返回值
        self.x = 22
        # 连接状态
        self.is_connected = False
        # TCP流对象
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        # 接收任务控制
        self.receive_task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()
        # 事务ID计数器
        self.transaction_id_counter = 0

    async def connect(self) -> bool:
        """异步连接到服务器"""
        try:
            print(f"尝试连接到 {self.SERVER_IP}:{self.SERVER_PORT}")
            self.reader, self.writer = await asyncio.open_connection(
                self.SERVER_IP, self.SERVER_PORT
            )
            print("连接成功")
            self.is_connected = True
            self.stop_event.clear()
            # 启动接收任务
            self.receive_task = asyncio.create_task(self.receive_data())
            self.update_status("连接成功")
            return True
        except Exception as ex:
            print(f"连接失败: {str(ex)}")
            self.update_status(f"连接失败: {str(ex)}")
            self.is_connected = False
            return False

    async def receive_data(self) -> None:
        """异步接收数据循环"""
        while not self.stop_event.is_set() and self.is_connected:
            try:
                # 等待数据（设置超时避免无限阻塞）
                data = await asyncio.wait_for(
                    self.reader.read(1024),  # 读取缓冲区
                    timeout=0.1
                )
                if data:
                    self.process_response(data)
                else:
                    # 服务器断开连接
                    await self.disconnect()
            except asyncio.TimeoutError:
                continue  # 超时继续等待
            except Exception as ex:
                self.update_status(f"接收数据错误: {str(ex)}")
                await self.disconnect()

    def process_response(self, response: bytes) -> int:
        """处理接收到的响应数据"""
        if len(response) < 9:
            return 0
        
        # 解析MBAP头
        transaction_id = (response[0] << 8) | response[1]
        function_code = response[7]
        data_length = response[8]
        
        if function_code == 0x03:  # 读寄存器响应
            if data_length >= 2 and len(response) >= 9 + data_length:
                # 解析寄存器值（大端模式）
                self.x = (response[9] << 8) | response[10]
                return self.x
            return 0
        elif function_code == 0x06:  # 写寄存器响应
            self.update_status("写操作成功")
            self.x = 100
            return self.x
        return 0

    def get_next_transaction_id(self) -> int:
        """生成下一个事务ID"""
        self.transaction_id_counter += 1
        return self.transaction_id_counter

    def build_read_request(self, transaction_id: int, register_address: int) -> bytes:
        """构建读寄存器请求报文"""
        # MBAP头（7字节） + PDU（5字节） = 共12字节
        request = bytearray(12)
        # MBAP头
        request[0] = (transaction_id >> 8) & 0xFF  # 事务ID高8位
        request[1] = transaction_id & 0xFF         # 事务ID低8位
        request[2] = 0x00                          # 协议ID高8位（Modbus为0）
        request[3] = 0x00                          # 协议ID低8位
        request[4] = 0x00                          # 长度高8位
        request[5] = 0x06                          # 长度低8位（PDU长度）
        # PDU
        request[6] = self.SLAVE_ID                 # 从站地址
        request[7] = 0x03                          # 功能码（读寄存器）
        request[8] = (register_address >> 8) & 0xFF  # 寄存器地址高8位
        request[9] = register_address & 0xFF         # 寄存器地址低8位
        request[10] = 0x00                         # 读取数量高8位（1个寄存器）
        request[11] = 0x01                         # 读取数量低8位
        return request

    def build_write_request(self, transaction_id: int, register_address: int, value: int) -> bytes:
        """构建写寄存器请求报文"""
        # MBAP头（7字节） + PDU（5字节） = 共12字节
        request = bytearray(12)
        # MBAP头
        request[0] = (transaction_id >> 8) & 0xFF
        request[1] = transaction_id & 0xFF
        request[2] = 0x00
        request[3] = 0x00
        request[4] = 0x00
        request[5] = 0x06
        # PDU
        request[6] = self.SLAVE_ID
        request[7] = 0x06                          # 功能码（写单个寄存器）
        request[8] = (register_address >> 8) & 0xFF
        request[9] = register_address & 0xFF
        request[10] = (value >> 8) & 0xFF           # 写入值高8位
        request[11] = value & 0xFF                  # 写入值低8位
        return request

    async def read_register(self, register_address: int) -> int:
        """读寄存器"""
        if not self.is_connected:
            return 0
        
        transaction_id = self.get_next_transaction_id()
        request = self.build_read_request(transaction_id, register_address)
        
        try:
            self.writer.write(request)
            await self.writer.drain()  # 确保数据发送
            return transaction_id
        except Exception as ex:
            self.update_status(f"发送读取请求失败: {str(ex)}")
            return 0

    async def write_register(self, register_address: int, value: int) -> None:
        """写寄存器"""
        if not self.is_connected:
            return
        
        request = self.build_write_request(
            self.get_next_transaction_id(),
            register_address,
            value
        )
        
        try:
            self.writer.write(request)
            await self.writer.drain()
        except Exception as ex:
            self.update_status(f"发送写入请求失败: {str(ex)}")

    async def disconnect(self) -> None:
        """断开连接"""
        self.is_connected = False
        self.stop_event.set()
        
        if self.receive_task:
            # 等待接收任务结束
            await asyncio.wait([self.receive_task], timeout=1.0)
        
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        
        self.update_status("已断开连接")

    def update_status(self, message: str) -> None:
        """更新状态信息"""
        print(f"[状态更新] {message}")

    def get_status_text(self, status_code: int) -> str:
        """状态码转文本"""
        status_map: Dict[int, str] = {
            0x0000: "待机",
            0x0001: "拧紧成功",
            0x0002: "滑牙",
            0x0003: "断裂",
            0x0004: "扭矩偏高",
            0x0005: "扭矩偏低",
            0x0006: "角度超上限",
            0x0007: "角度超下限",
            0x0008: "超时未完成",
            0x0009: "压力偏大",
            0x000A: "扭矩偏大",
            0x000B: "紧急停止",
            0x000C: "拧紧失败"
        }
        return status_map.get(status_code, f"未知状态: {status_code}")

    async def zhuangtai(self) -> bool:
        """检查设备状态"""
        if not self.is_connected:
            print("请先连接设备")
            return False
        
        await self.read_register(self.REG_STATUS)
        await asyncio.sleep(0.1)  # 等待响应
        
        if self.x == 22:
            self.update_status("未读取到，请再次操作")
            return False
        elif self.x == 0x0001:
            return True
        return False