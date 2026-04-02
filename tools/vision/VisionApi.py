import json
import math
import socket
import time
import sys
import os
from typing import List, Tuple, Optional, Dict, Any
import asyncio

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger

#region 数据结构
class Vector3:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z

    @staticmethod
    def dot(a: 'Vector3', b: 'Vector3') -> float:
        return a.x * b.x + a.y * b.y + a.z * b.z

    def magnitude(self) -> float:
        return math.sqrt(self.x **2 + self.y** 2 + self.z ** 2)

    @staticmethod
    def angle_between(a: 'Vector3', b: 'Vector3') -> float:
        dot_product = Vector3.dot(a, b)
        magnitudes = a.magnitude() * b.magnitude()
        
        # 防止浮点数误差导致acos参数越界
        cos_theta = max(-1.0, min(1.0, dot_product / magnitudes))
        return math.acos(cos_theta)

    @staticmethod
    def angle_between_degrees(a: 'Vector3', b: 'Vector3') -> float:
        return Vector3.angle_between(a, b) * (180.0 / math.pi)


class CrossPointsResponse:
    def __init__(self, cross_points_pixels: List[List[float]], cross_points_camera: List[List[float]]):
        self.cross_points_pixels = cross_points_pixels
        self.cross_points_camera = cross_points_camera

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'CrossPointsResponse':
        return CrossPointsResponse(
            data.get('cross_points_pixels', []),
            data.get('cross_points_camera', [])
        )


class AngleResponse:
    def __init__(self, normal_vector: List[float]):
        self.normal_vector = normal_vector

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'AngleResponse':
        return AngleResponse(data.get('normal_vector', []))


class DepthResponse:
    def __init__(self, depth: float):
        self.depth = depth

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'DepthResponse':
        return DepthResponse(data.get('depth', 0.0))
class BoardAngleResponse:
    def __init__(self, board_angle: float):
        self.board_angle = board_angle

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'BoardAngleResponse':
        return BoardAngleResponse(data.get('board_angle', 0.0))
class BoardPositionResponse:
    def __init__(self, board_center: List[float]):
        self.board_center = board_center

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'BoardPositionResponse':
        # 服务器返回的字段是 board_position
        board_center_data = data.get('board_position', [])
        
        # 如果是字符串格式 "(x, y)"，解析为列表
        if isinstance(board_center_data, str):
            try:
                # 移除括号和空格，分割字符串
                board_center_data = board_center_data.strip('() ')
                parts = board_center_data.split(',')
                board_center_data = [float(parts[0].strip()), float(parts[1].strip())]
            except (ValueError, IndexError) as e:
                logger.warning(f"解析板中心字符串失败：{e}")
                board_center_data = []
        
        return BoardPositionResponse(board_center_data)

class ScrewPointsResponse:
    def __init__(self, screw_points_pixels: List[List[float]], screw_points_camera: List[List[float]]):
        self.screw_points_pixels = screw_points_pixels
        self.screw_points_camera = screw_points_camera

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ScrewPointsResponse':
        return ScrewPointsResponse(
            data.get('screw_points_pixels', []),
            data.get('screw_points_camera', [])
        )
    
class HexNutPointsResponse:
    def __init__(self, hex_nut_points_pixels: List[List[float]], hex_nut_points_camera: List[List[float]]):
        self.hex_nut_points_pixels = hex_nut_points_pixels
        self.hex_nut_points_camera = hex_nut_points_camera

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'HexNutPointsResponse':
        return HexNutPointsResponse(
            data.get('hex_nut_points_pixels', []),
            data.get('hex_nut_points_camera', [])
        )
#endregion



class VisionApi:
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.client: Optional[socket.socket] = None
        self.stream = None
        self.buffer_size = 16384
        self.logger = logger

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.fileno() != -1

    async def connect(self) -> bool:
        if self.is_connected:
            return

        self.logger.info(f"尝试连接到服务器：{self.ip}:{self.port}")
        loop = asyncio.get_event_loop()
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.setblocking(False)
        
        try:
            await loop.sock_connect(self.client, (self.ip, self.port))
            self.logger.info("连接成功！")
            return True
        except Exception as e:
            self.logger.info(f"连接失败：{e}")
            self.client.close()
            self.client = None
            return False



#region 十字交叉点
    async def get_cross_points_async(self) -> List[List[float]]:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")
        try:
            # 发送指令
            command = "cross_points_without_granding\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令: '{command.strip()}' (字节数: {len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到响应: {json_str}")

            if not json_str.strip():
                self.logger.info("警告：服务器返回空响应")
                return []

            data = json.loads(json_str)
            response = CrossPointsResponse.from_dict(data)

            if not response.cross_points_pixels:
                self.logger.info("警告：未检测到十字交叉点")
                return []

            self.logger.info(f"成功获取 {len(response.cross_points_pixels)} 个十字交叉点")
            return response.cross_points_pixels
        except Exception as ex:
            self.logger.info(f"获取十字交叉点异常：{ex}")
            return []
#endregion

#region 螺钉中心
    async def get_screw_points_async(self) -> List[float]:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")  
            
        try:
            # 发送指令
            command = "screw_points\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令: '{command.strip()}' (字节数: {len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到响应: {json_str}")

            if not json_str.strip():
                self.logger.info("警告：服务器返回空响应")
                return []

            data = json.loads(json_str)
            response = ScrewPointsResponse.from_dict(data)

            if not response.screw_points_pixels:
                self.logger.info("警告：未检测到螺钉")
                return []

            self.logger.info(f"成功获取 {len(response.screw_points_pixels)} 个螺钉")
            return response.screw_points_pixels
        except Exception as ex:
            self.logger.info(f"获取螺钉异常：{ex}")
            return []




#endregion

#region 法向量
    async def get_normal_async(self) -> Tuple[float, float, float]:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")

        try:
            # 发送指令
            command = "normal_vector\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令: '{command.strip()}' (字节数: {len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到法向量响应: {json_str}")

            if not json_str.strip():
                self.logger.info("警告：服务器返回空法向量响应")
                return (0, 0, 0)

            data = json.loads(json_str)
            response = AngleResponse.from_dict(data)

            if not response.normal_vector:
                self.logger.info("警告：无法解析法向量响应")
                return (0, 0, 0)

            # 确保z分量为正
            z = response.normal_vector[2]
            if z < 0:
                response.normal_vector = [
                    -response.normal_vector[0],
                    -response.normal_vector[1],
                    -response.normal_vector[2]
                ]

            self.logger.info(f"成功获取法向量 - normal_vector: {response.normal_vector}")

            v1 = Vector3(response.normal_vector[0], response.normal_vector[1], response.normal_vector[2])
            v2 = Vector3(0, 0, 1)
            radians = Vector3.angle_between(v1, v2)
            degrees = Vector3.angle_between_degrees(v1, v2)
            self.logger.info(f"夹角（弧度）: {radians:.6f}")
            self.logger.info(f"夹角（角度）: {degrees:.2f}°")

            return (response.normal_vector[0], response.normal_vector[1], response.normal_vector[2])
        except Exception as ex:
            self.logger.info(f"获取法向量异常：{ex}")
            return (0.0, 0.0, 0.0)

#endregion









#region 深度
    async def get_depth_async(self) -> float:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")

        try:
            # 发送指令
            command = "depth\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令: '{command.strip()}' (字节数: {len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到深度响应: {json_str}")

            if not json_str.strip():
                self.logger.info("警告：服务器返回空深度响应")
                return 0

            data = json.loads(json_str)
            response = DepthResponse.from_dict(data)

            if response is None:
                self.logger.info("警告：无法解析深度响应")
                return 0

            self.logger.info(f"成功获取深度: {response.depth}")
            return response.depth
        except Exception as ex:
            self.logger.info(f"获取深度异常：{ex}")
            return 0

#endregion

#region 板角度
    async def get_board_angle_async(self) -> float:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")

        try:
            # 发送指令
            command = "board_angle\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令：'{command.strip()}' (字节数：{len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到板角度响应：{json_str}")
            print(f"收到板角度响应：{json_str}")
            if not json_str.strip():
                self.logger.info("警告：服务器返回空板角度响应")
                return 0

            data = json.loads(json_str)
            response = BoardAngleResponse.from_dict(data)

            if response is None:
                self.logger.info("警告：无法解析板角度响应")
                return 0

            self.logger.info(f"成功获取板角度：{response.board_angle}")
            return response.board_angle
        except Exception as ex:
            self.logger.info(f"获取板角度异常：{ex}")
            return 0
#endgion
#region 板中心点
#region 板中心点
    async def get_board_position_async(self) -> List[float]:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")

        try:
            # 发送指令
            command = "board_position\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令：'{command.strip()}' (字节数：{len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到板中心响应：{json_str}")
            print(f"收到板中心响应：{json_str}")
            if not json_str.strip():
                self.logger.info("警告：服务器返回空板中心响应")
                return []

            data = json.loads(json_str)
            response = BoardPositionResponse.from_dict(data)

            if not response.board_center:
                self.logger.info("警告：无法解析板中心响应")
                return []

            self.logger.info(f"成功获取板中心坐标：{response.board_center}")
            return response.board_center
        except Exception as ex:
            self.logger.info(f"获取板中心异常：{ex}")
            return []

#region 六角螺套点
    async def get_hex_nut_points_async(self) -> List[List[float]]:
        if not self.is_connected:
            raise RuntimeError("未连接到服务器")
        try:
            # 发送指令
            command = "u\n"
            command_bytes = command.encode('utf-8')
            self.logger.info(f"发送指令：'{command.strip()}' (字节数：{len(command_bytes)})")

            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.client, command_bytes)

            # 读取完整响应
            json_str = await self._read_full_response()
            self.logger.info(f"收到响应：{json_str}")

            if not json_str.strip():
                self.logger.info("警告：服务器返回空响应")
                return []

            data = json.loads(json_str)
            response = HexNutPointsResponse.from_dict(data)

            if not response.hex_nut_points_pixels:
                self.logger.info("警告：未检测到六角螺套点")
                return []

            self.logger.info(f"成功获取 {len(response.hex_nut_points_pixels)} 个六角螺套点")
            return response.hex_nut_points_pixels
        except Exception as ex:
            self.logger.info(f"获取六角螺套点异常：{ex}")
            return []
#endregion


#region 辅助方法

    async def _read_full_response(self) -> str:
        loop = asyncio.get_event_loop()
        buffer = bytearray()
        timeout = time.time() + 20  # 10秒超时

        while time.time() < timeout:
            if self.client is None:
                break

            # 检查是否有数据可读取
            try:
                data = await asyncio.wait_for(
                    loop.sock_recv(self.client, self.buffer_size),
                    timeout=0.1
                )
                if not data:
                    break  # 连接关闭
                buffer.extend(data)

                # 检查是否是完整的JSON对象
                current_json = buffer.decode('utf-8')
                if self._is_valid_json(current_json):
                    self.logger.info(f"读取完成（字节数: {len(buffer)}）")
                    return current_json
            except asyncio.TimeoutError:
                continue  # 超时继续等待
            except Exception as e:
                self.logger.info(f"读取数据异常: {e}")
                break

        # 超时处理
        result = buffer.decode('utf-8')
        self.logger.info(f"读取超时（字节数: {len(buffer)}）：{result}")
        return result

    @staticmethod
    def _is_valid_json(json_str: str) -> bool:
        json_str = json_str.strip()
        return json_str.startswith('{') and json_str.endswith('}')

    def close(self) -> None:
        self.logger.info("释放VisionApi资源...")
        if self.client:
            self.client.close()
            self.client = None
#endregion