#!/usr/bin/env python3
"""
Robot Abstraction Layer
机器人抽象层，提供统一接口支持不同品牌的机器人
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Self
from enum import Enum
import json


from logs.logger_utils import logger
from regex import T


class RobotBrand(Enum):
    """机器人品牌枚举"""
    UNIVERSAL_ROBOTS = "ur"
    DUCOCOBOT = "duco"
    FANUC = "fanuc"
    KUKA = "kuka"
    ABB = "abb"
    DAZU = "dazu"

class RobotState(Enum):
    """机器人状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    MOVING = "moving"
    ERROR = "error"
    STOPPED = "stopped"

#region 机器人抽象类
class RobotAbstraction(ABC):
    """机器人抽象基类"""
    
    def __init__(self, ip_address: str, **kwargs):
        self.ip_address = ip_address
        self.state = RobotState.DISCONNECTED
        self.logger = logger

    @abstractmethod
    async def connect(self) -> bool:
        """连接机器人"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """断开连接"""
        pass
    
    @abstractmethod
    async def movej(self, joint_angles: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """关节运动"""
        pass
    
    @abstractmethod
    async def movej_2(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """关节运动_2"""
        pass

    @abstractmethod
    async def movel(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """直线运动"""
        pass

    @abstractmethod
    async def movetcp(self, offset: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """tcp运动"""
        pass

    @abstractmethod
    async def movetcp_position_to(self, offset: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """tcp运动"""
        pass
    @abstractmethod
    async def get_current_tcp_pos(self) -> Optional[List[float]]:
        """获取当前TCP位置"""
        pass
    
    @abstractmethod
    async def get_current_joint_pos(self) -> Optional[List[float]]:
        """获取当前关节角度"""
        pass
    
    @abstractmethod
    async def set_tool(self, tcp: List[float]) -> bool:
        """设置TCP"""
        pass
    
    @abstractmethod
    async def set_payload(self, mass: float, cog: List[float]) -> bool:
        """设置负载"""
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """紧急停止"""
        pass
    
    @abstractmethod
    async def wait_for_movement_completion(self) -> bool:
        """等待运动完成"""
        pass

    @abstractmethod
    async def enter_teach_mode(self) -> bool:
        """进入示教模式"""
        pass

    @abstractmethod
    async def exit_teach_mode(self) -> bool:
        """退出示教模式"""
        pass

    @abstractmethod
    async def movel_nonblocking(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """非阻塞直线运动"""
        pass

#############################################################################################################################################################
#############################################################################################################################################################
#############################################################################################################################################################
#############################################################################################################################################################
#region ur工具
import time
import json
import logging
import math
from pathlib import Path
from typing import List, Optional
import numpy as np
import asyncio  # 确保导入asyncio
# 导入URBasic模块
from . import URBasic




class UniversalRobotsRobot(RobotAbstraction):
    """Universal Robots 机器人实现"""
    def __init__(self, ip_address: str, **kwargs):
        super().__init__(ip_address, **kwargs)
        self.robot_ip = ip_address
        self.robot_list = {}  # 存储机器人连接实例
        self._setup_imports()
    
    def _setup_imports(self):
        """设置UR机器人相关的导入"""

        # 工具坐标系移动相关属性
        self._current_pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # [X, Y, Z, rx, ry, rz]
        self._rotation_matrix = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0]
        ]  # 3x3旋转矩阵
        
    async def connect(self) -> bool:
        """连接UR机器人"""
        try:
           # 创建机器人模型和连接
            robot_model = URBasic.robotModel.RobotModel()
            robot = URBasic.urScriptExt.UrScriptExt(
                host=self.robot_ip, 
                robotModel=robot_model
            )
            
            # 检查连接状态
            if not robot.robotConnector.RTDE.isRunning():
                self.logger.error(f"连接机器人 {self.robot_ip} 失败: RTDE未运行")
                return False
            
            # 检查远程控制模式
            robot.robotConnector.DashboardClient.ur_is_remote_control()
            remote_mode = robot.robotConnector.DashboardClient.last_respond.lower()
            if remote_mode != 'true' and not remote_mode.startswith('could not understand'):
                robot.close()
                self.logger.error(f"机器人 {self.robot_ip} 未处于远程控制模式")
                return False
            
            self.robot_list[self.robot_ip] = (robot, robot_model)
            self.state = RobotState.CONNECTED  # 更新状态为已连接

            # self.logger.info(f"成功连接到机器人 {self.robot_ip}")
            return True
        
        except Exception as e:
            self.logger.error(f"连接机器人 {self.robot_ip} 时出错: {str(e)}")
            return False
    
    async def disconnect(self) -> bool:
        """断开UR机器人连接"""
        try:
            if self.robot_ip in self.robot_list:
                robot, _ = self.robot_list[self.robot_ip]
                robot.close()
                del self.robot_list[self.robot_ip]
                # self.logger.info(f"已断开与机器人 {self.robot_ip} 的连接")
                return True
            else:
                self.logger.warning(f"未找到机器人 {self.robot_ip} 的连接")
                return False
        except Exception as e:
            self.logger.error(f"断开连接时出错: {str(e)}")
            return False
    
    async def movej_2(self, tcp_pose: List[float], acceleration: float = 0.2, velocity: float = 0.2) -> bool:
        """UR机器人关节运动_2，传入参数为tcp坐标"""
        if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
        
        try:
            robot, _ = self.robot_list[self.robot_ip]
            # self.logger.info(f"movej_2运动：{tcp_pose}")
            robot.movej(None, acceleration, velocity,0,0,True,tcp_pose)  # 修正参数传递方式
            await self.Rob_move_and_wait()
            return True
        except Exception as e:
            self.logger.error(f"关节运动_2出错: {str(e)}")
            return False

    async def movej(self, joint_angles: List[float], acceleration: float = 0.2, velocity: float = 0.2) -> bool:
        """UR机器人关节运动，传入参数为关节角度"""
        if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
        
        try:
            robot, _ = self.robot_list[self.robot_ip]
            robot.movej(joint_angles, acceleration, velocity)  # 修正参数传递方式
            await self.Rob_move_and_wait()
            return True
        except Exception as e:
            self.logger.error(f"关节运动出错: {str(e)}")
            return False

    async def movel(self, tcp_pose: List[float], acceleration: float = 0.2, velocity: float = 0.2) -> bool:
        """UR机器人直线运动"""
        if self.robot_ip not in self.robot_list:
            self.logger.warning(f"机器人 {self.robot_ip} 未连接")
            return False
        
        try:
  
            robot, _ = self.robot_list[self.robot_ip]
            # self.logger.info(f"movel运动: {tcp_pose}")
            robot.movel(tcp_pose, acceleration, velocity) 
            # await self.Rob_move_and_wait()
            return True
            
        except Exception as e:
            self.logger.error(f"TCP直线移动出错: {str(e)}")
            return False
    
    async def get_current_tcp_pos(self) -> Optional[List[float]]:
        """获取UR机器人当前TCP位置"""
        if self.robot_ip not in self.robot_list:
            self.logger.warning(f"机器人 {self.robot_ip} 未连接")
            return None
        try:
            robot, _ = self.robot_list[self.robot_ip]
            tcp_pose = robot.get_actual_tcp_pose()
            # 处理NumPy数组的判断和转换
            if tcp_pose is not None:
                # 如果是NumPy数组，转换为Python列表
                if isinstance(tcp_pose, np.ndarray):
                    tcp_pose = tcp_pose.tolist()
                if len(tcp_pose) == 6:
                    self._current_pose = tcp_pose
                    self._update_rotation_matrix()
                    return tcp_pose
            
            # 如果不符合条件，返回None
            self.logger.warning("获取的TCP位姿格式不正确")
            return None
            
        except Exception as e:
            self.logger.error(f"获取TCP位置信息出错: {str(e)}")
            return None
    
    async def get_current_joint_pos(self) -> Optional[List[float]]:
        """获取UR机器人当前关节角度"""
        if self.robot_ip not in self.robot_list:
            self.logger.warning(f"机器人 {self.robot_ip} 未连接")
            return None

        try:
            robot, _ = self.robot_list[self.robot_ip]
            joint_angles = robot.get_actual_joint_positions()
            
            # 将可能的NumPy数组转换为Python列表
            if isinstance(joint_angles, np.ndarray):
                joint_angles = joint_angles.tolist()
                
            return joint_angles
        except Exception as e:
            self.logger.error(f"获取关节角度信息出错: {str(e)}")
            return None
    
    # async  def set_tool_data(self,tool_offset: List[float], 
    #                  payload: List[float], inertia_tensor: List[float]) -> bool:
    #     """设置工具数据（工具偏移、负载、惯性张量）"""
    #     try:
    #         if self.robot_ip not in self.robot_list:
    #             self.logger.warning(f"机器人 {self.robot_ip} 未连接")
    #             return False
                
    #         robot, _ = self.robot_list[self.robot_ip]
    #         mass = payload[0]
    #         cog = payload[1:4]
    #         robot.set_payload_mass(mass)
    #         robot.set_payload_cog(cog)
    #         # self.logger.info(f"负载设置为: 质量={mass}kg, 重心={cog}")
    #         return True
    #     except Exception as e:
    #         self.logger.error(f"设置负载失败: {str(e)}")
    #         return False

    async def set_tool(self,tcp: list):
        """设置TCP坐标系的原点位置
        tcp: TCP位置 [x, y, z, rx, ry, rz]
        """
        if self.robot_ip not in self.robot_list:
            self.logger.warning(f"机器人 {self.robot_ip} 未连接")
            return None
        try:
        
            
            robot, _ = self.robot_list[self.robot_ip]
            robot.set_tcp(tcp)
            # self.logger.info(f"TCP坐标设置为: {tcp}")
            return True
        except Exception as e:
            self.logger.error(f"设置TCP坐标失败: {str(e)}")
            return False

    async def set_payload(self,mass: float, cog: list):
        """设置机器人的负载和重心
        mass: 负载质量(kg)
        cog: 重心坐标 [x, y, z]
        """
        try:
            # 修正访问字典的方式
            if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
                
            robot, _ = self.robot_list[self.robot_ip]
            # URBasic中需要分别设置质量与重心
            robot.set_payload_mass(mass)
            robot.set_payload_cog(cog)
            # self.logger.info(f"负载设置为: 质量={mass}kg, 重心={cog}")
            return True
        except Exception as e:
            self.logger.error(f"设置负载失败: {str(e)}")
            return False
    
        
    async def stop(self) -> bool:
        """UR机器人紧急停止"""
        try:
            if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
            robot, _ = self.robot_list[self.robot_ip]
            robot.robotConnector.DashboardClient.ur_stop()
            # self.logger.info("紧急停止命令已发送")
            return True
        except Exception as e:
            self.logger.error(f"紧急停止失败: {str(e)}")
            return False
    async def wait_for_movement_completion(self) -> bool:
        """等待UR机器人运动完成"""
        try:
            if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
                
            robot, _ = self.robot_list[self.robot_ip]
            robot.robotConnector.DashboardClient.ur_running()
            response = robot.robotConnector.DashboardClient.last_respond.lower()
            return 'true' in response
        except Exception as e:
            self.logger.error(f"检查机器人运动状态失败: {str(e)}")
            return False
    # 工具坐标系移动相关方法
    def _rot_vec_to_rot_mat(self, rx: float, ry: float, rz: float) -> List[List[float]]:
        """将旋转矢量转换为旋转矩阵"""
        theta = math.sqrt(rx **2 + ry** 2 + rz ** 2)
        
        if theta < 1e-6:
            return [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0]
            ]
            
        kx = rx / theta
        ky = ry / theta
        kz = rz / theta
        
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        one_minus_cos = 1 - cos_theta
        
        return [
            [
                cos_theta + kx * kx * one_minus_cos,
                kx * ky * one_minus_cos - kz * sin_theta,
                kx * kz * one_minus_cos + ky * sin_theta
            ],
            [
                ky * kx * one_minus_cos + kz * sin_theta,
                cos_theta + ky * ky * one_minus_cos,
                ky * kz * one_minus_cos - kx * sin_theta
            ],
            [
                kz * kx * one_minus_cos - ky * sin_theta,
                kz * ky * one_minus_cos + kx * sin_theta,
                cos_theta + kz * kz * one_minus_cos
            ]
        ]

    def _update_rotation_matrix(self) -> None:
        """更新旋转矩阵（基于当前位姿的旋转分量）"""
        self._rotation_matrix = self._rot_vec_to_rot_mat(
            self._current_pose[3],  # rx
            self._current_pose[4],  # ry
            self._current_pose[5]   # rz
        )

    def _tool_to_base_offset(self, tool_offset: List[float]) -> List[float]:
        """将工具坐标系下的偏移转换为基座坐标系下的偏移"""
        if len(tool_offset) != 3:
            raise ValueError("工具坐标系偏移必须包含3个元素（dx, dy, dz）")
            
        base_offset = [0.0, 0.0, 0.0]
        
        base_offset[0] = (self._rotation_matrix[0][0] * tool_offset[0] +
                         self._rotation_matrix[0][1] * tool_offset[1] +
                         self._rotation_matrix[0][2] * tool_offset[2])
                         
        base_offset[1] = (self._rotation_matrix[1][0] * tool_offset[0] +
                         self._rotation_matrix[1][1] * tool_offset[1] +
                         self._rotation_matrix[1][2] * tool_offset[2])
                         
        base_offset[2] = (self._rotation_matrix[2][0] * tool_offset[0] +
                         self._rotation_matrix[2][1] * tool_offset[1] +
                         self._rotation_matrix[2][2] * tool_offset[2])
                         
        return base_offset
#region ur movetcp
    async def movetcp(self, offset: List[float], acceleration: float = 0.2, velocity: float = 0.2, 
                    radius: float = 0, block: bool = True) -> bool:
        """
        沿工具坐标系移动（支持位置和方向偏移）
        :param offset: 工具坐标系下的偏移量 [dx, dy, dz, drx, dry, drz]，前3项为位置偏移（米），后3项为旋转偏移（弧度）
        :param velocity: 工具速度（米/秒）
        :param acceleration: 工具加速度（米/秒²）
        :param radius: 混合半径（米）
        :param block: 是否阻塞等待运动完成
        :return: 运动是否成功
        """
        if self.robot_ip not in self.robot_list:
            print(f"机器人 {self.robot_ip} 未连接")
            return False
            
        try:
            # 校验偏移量格式（必须包含6个元素：位置3项+旋转3项）
            if offset is None or len(offset) != 6:
                raise ValueError("偏移量必须包含6个元素 [dx, dy, dz, drx, dry, drz]")
            
            # 获取当前TCP位姿（包含位置和方向）
            current_pose = await self.get_current_tcp_pos()
            if current_pose is None:
                self.logger.warning("无法获取当前位姿，移动失败")
                return False
            
            # 解析偏移量（位置偏移+旋转偏移）
            dx, dy, dz = offset[0], offset[1], offset[2]
            drx, dry, drz = offset[3], offset[4], offset[5]
            
            # 1. 计算位置偏移（基于工具坐标系转换到基座坐标系）
            base_pos_offset = self._tool_to_base_offset([dx, dy, dz])
            
            # 2. 计算旋转偏移（工具坐标系下的旋转增量转换为绝对旋转）
            # 2.1 将当前旋转矢量转换为旋转矩阵
            current_rot_mat = self._rot_vec_to_rot_mat(
                current_pose[3],  # 当前Rx
                current_pose[4],  # 当前Ry
                current_pose[5]   # 当前Rz
            )
            # 2.2 将旋转偏移转换为旋转矩阵
            delta_rot_mat = self._rot_vec_to_rot_mat(drx, dry, drz)
            # 2.3 计算新的旋转矩阵（当前旋转 × 偏移旋转）
            new_rot_mat = self._mat_mult(current_rot_mat, delta_rot_mat)
            # 2.4 将新旋转矩阵转换回旋转矢量（Rx, Ry, Rz）
            new_rx, new_ry, new_rz = self._rot_mat_to_rot_vec(new_rot_mat)
            
            # 3. 构造目标位姿（新位置+新方向）
            target_pose = [
                current_pose[0] + base_pos_offset[0],  # X
                current_pose[1] + base_pos_offset[1],  # Y
                current_pose[2] + base_pos_offset[2],  # Z
                new_rx,  # 新Rx
                new_ry,  # 新Ry
                new_rz   # 新Rz
            ]
            
            # 4. 执行直线运动到目标位姿
            # self.logger.info(f"tcp运动：{offset}")
            success = await self.movel(target_pose, acceleration, velocity)
            await self.Rob_move_and_wait()
            if not success:
                self.logger.warning("移动到目标位姿失败")
                return False
            
            # 5. 若需要阻塞，等待运动完成
            if block:
                await self.wait_for_movement_completion()
                
            return True
            
        except Exception as e:
            self.logger.error(f"工具坐标系移动失败: {str(e)}")
            return False

    # 新增辅助方法：矩阵乘法（用于旋转矩阵合成）
    def _mat_mult(self, mat1: List[List[float]], mat2: List[List[float]]) -> List[List[float]]:
        """计算两个3x3矩阵的乘积"""
        result = [[0.0 for _ in range(3)] for _ in range(3)]
        for i in range(3):
            for j in range(3):
                result[i][j] = sum(mat1[i][k] * mat2[k][j] for k in range(3))
        return result

    # 新增辅助方法：旋转矩阵转旋转矢量
    def _rot_mat_to_rot_vec(self, rot_mat: List[List[float]]) -> List[float]:
        """将3x3旋转矩阵转换为旋转矢量（Rx, Ry, Rz）"""
        # 从旋转矩阵提取旋转角和旋转轴
        theta = math.acos((rot_mat[0][0] + rot_mat[1][1] + rot_mat[2][2] - 1) / 2)
        if theta < 1e-6:
            return [0.0, 0.0, 0.0]  # 无旋转
        
        # 计算旋转轴（单位向量）
        rx = (rot_mat[2][1] - rot_mat[1][2]) / (2 * math.sin(theta))
        ry = (rot_mat[0][2] - rot_mat[2][0]) / (2 * math.sin(theta))
        rz = (rot_mat[1][0] - rot_mat[0][1]) / (2 * math.sin(theta))
        
        # 旋转矢量 = 旋转轴 × 旋转角
        return [rx * theta, ry * theta, rz * theta]
    


    async def enter_teach_mode(self) -> bool:
        """ur机器人进入示教模式"""
        try:
            if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
            robot, _ = self.robot_list[self.robot_ip]
            # 使用 URScript 的 teach_mode 方法
            robot.teach_mode(False)
            # self.logger.info("进入示教模式命令已发送")
            return True
        except Exception as e:
            self.logger.error(f"进入示教模式失败: {str(e)}")
            return False
    async def exit_teach_mode(self) -> bool:
        """ur机器人退出示教模式"""
        try:
            if self.robot_ip not in self.robot_list:
                self.logger.warning(f"机器人 {self.robot_ip} 未连接")
                return False
            robot, _ = self.robot_list[self.robot_ip]
            # 使用 URScript 的 end_teach_mode 方法
            robot.end_teach_mode(False)
            self.logger.info("退出示教模式命令已发送")
            return True
        except Exception as e:
            self.logger.error(f"退出示教模式失败: {str(e)}")
            return False
    async def Rob_move_and_wait(self) -> bool:
        """
        机器人移动并等待到位后再返回
        通过读取位置并间隔100ms再次读取位置，对比两个位置差异，超过1mm继续判断，
        直到不动了则返回true
        """

        # 等待机器人到位
        timeout = 30.0  # 30秒超时
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # 获取当前机器人位置
            current_pose1 = await self.get_current_tcp_pos()
            
            # 等待100ms
            await asyncio.sleep(0.1)
            
            # 再次获取当前机器人位置
            current_pose2 = await self.get_current_tcp_pos()
            
            # 计算两个位置之间的距离
            distance = calculate_distance(current_pose1, current_pose2)
            
            # 如果距离小于5mm，认为机器人已经停止移动
            if distance < 0.005:  # 1mm
                return True
                
        raise Exception(f"机器人未在{timeout}秒内停止移动")

    async def movel_nonblocking(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """非阻塞直线运动 - 真正的异步实现"""
        if self.robot_ip not in self.robot_list:
            self.logger.warning(f"机器人 {self.robot_ip} 未连接")
            return False

        try:
            robot, _ = self.robot_list[self.robot_ip]
            self.logger.info(f"movel_nonblocking非阻塞运动: {tcp_pose}")

            # 将阻塞操作放到线程池中执行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._blocking_movel, robot, tcp_pose, acceleration, velocity)
            return True

        except Exception as e:
            self.logger.error(f"非阻塞TCP直线移动出错: {str(e)}")
            return False

    def _blocking_movel(self, robot, tcp_pose: List[float], acceleration: float, velocity: float) -> None:
        """在线程池中执行的阻塞movel操作"""
        """这个方法在线程池中执行，不会阻塞主协程"""
        robot.movel(tcp_pose, acceleration, velocity)

def calculate_distance(pose1: List[float], pose2: List[float]) -> float:
    """计算两个位姿之间的距离"""
    return math.sqrt(sum((p1 - p2) ** 2 for p1, p2 in zip(pose1[:3], pose2[:3])))



##################################################################################################################################################
##################################################################################################################################################
##################################################################################################################################################
##################################################################################################################################################
#region duco工具
from tools.robots.Duco.gen_py.robot.ttypes import StateRobot, StateProgram, OperationMode,TaskState,Op,MoveJogTaskParam,PointOp
from tools.robots.Duco.DucoCobot import DucoCobot





class DucocobotRobot(RobotAbstraction):
    """Ducocobot 机器人实现"""
    
    def __init__(self, ip_address: str, **kwargs):
        super().__init__(ip_address, **kwargs)
        self.robot = None
        self.state = None
        self._op = Op(0, 1, False, 0, 0, "", 0, 1, False, 0, 0, "", 0, 1, False, 0, 0, "")
        
    async def connect(self) -> bool:
        """连接到机器人"""
        try:
            self.robot = DucoCobot(self.ip_address, port=7003)
            connect_status = self.robot.open()
            if connect_status == 0:
                self.state= RobotState.CONNECTED
                # self.logger.info("连接机器人 {self.ip_address}成功")
                await self.set_speed_ratio(100)  # 设置默认速度为100%
                return True
            else:
                raise Exception(f"错误代码: {connect_status}")
        except Exception as ex:
            self.logger.error(f"连接机器人 {self.ip_address}失败: {str(ex)}")
            return False

    async def disconnect(self) -> bool:
        """断开与机器人的连接"""
        if self.state==RobotState.CONNECTED:
            try:
                self.robot.close()
                self.state = RobotState.DISCONNECTED
                # self.logger.info("断开机器人 {self.ip_address}成功")
                return True
            except Exception as ex:
                self.logger.error(f"断开机器人{self.ip_address}失败: {str(ex)}")
                return False
        else:
            self.logger.error("机器人未连接")
            return False

    async def set_speed_ratio(self, speed_ratio: float) -> bool:
        """
        设置duco机器人运动速度比例（百分比）
        """
        if self.state==RobotState.CONNECTED:
            try:
                if speed_ratio < 0 or speed_ratio > 100:
                    raise ValueError("速度比例必须在0.0~100范围内")
                self.robot.speed(speed_ratio)
                # self.logger.info(f"设置机器人 {self.ip_address} 速度比例为: {speed_ratio}%")
                return True
            except Exception as ex:
                self.logger.error(f"设置速度比例失败: {str(ex)}")
                return False
        else:
            self.logger.error("机器人未连接")
            return False

    async def movej_2(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """duco机器人关节运动_2"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
    
        try:
            self.state = RobotState.MOVING
            radius = 0.0  # 设置为0表示不使用圆弧运动
            block= True  # 设置为阻塞模式
            # self.logger.info(f"movej_2运动：{tcp_pose}")
            self.robot.movej_pose2(tcp_pose, velocity, acceleration, radius, [], "", "", block, self._op, False)
            await self.wait_for_movement_completion()
            return True
        except Exception as e:
            self.logger.error(f"duco机器人关节移动_2出错: {str(e)}")
            return False
    
    async def movej(self, joint_angles: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """duco机器人关节运动_2"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
    
        try:
            self.state = RobotState.MOVING
            radius = 0.0  # 设置为0表示不使用圆弧运动
            block= True  # 设置为阻塞模式
            # self.logger.info(f"movej运动：{joint_angles}")
            self.robot.movej(joint_angles, velocity, acceleration, radius, block, self._op, False)
            await self.wait_for_movement_completion()
            return True
        except Exception as e:
            self.logger.error(f"duco机器人关节移动出错: {str(e)}")
            return False

    async def movel(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """duco机器人直线运动"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
        
        try:
            self.state = RobotState.MOVING
            radius = 0.0  # 设置为0表示不使用圆弧运动
            block = True  # 设置为阻塞模式
            # self.logger.info(f"movel运动: {tcp_pose}")
            self.robot.movel(tcp_pose, velocity, acceleration, radius, [], "", "", block, self._op, False)
            await self.wait_for_movement_completion()
            return True
        except Exception as e:
            self.logger.error(f"duco机器人直线移动出错: {str(e)}")
            return False

    async def movetcp(self, offset: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """duco机器人TCP运动"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
        
        try:
            self.state = RobotState.MOVING
            radius = 0.0  # 设置为0表示不使用圆弧运动
            block = True  # 设置为阻塞模式
            # self.logger.info(f"movetcp运动：{offset}")
            self.robot.tcp_move(offset, velocity, acceleration, radius, "", block, self._op, False)
            await self.wait_for_movement_completion()
            return True
        except Exception as e:
            self.logger.error(f"duco机器人TCP移动出错: {str(e)}")
            return False

    async def get_current_tcp_pos(self) -> Optional[List[float]]:
        """获取duco机器人当前TCP位置"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return None
        
        try:
            return self.robot.get_tcp_pose()
        except Exception as e:
            # self.logger.error(f"获取duco机器人TCP位置信息出错: {str(e)}")
            return None

    async def get_current_joint_pos(self) -> Optional[List[float]]:
        """获取duco机器人当前关节角度"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return None
        
        try:
            return self.robot.get_actual_joints_position()
        except Exception as e:
            self.logger.error(f"获取duco机器人关节角度信息出错: {str(e)}")
            return None
        

    async def set_tool(self, tcp: List[float]) -> bool:
        """设置duco机器人TCP"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
        
        try:
            self.robot.set_wobj_offset(tcp)
            # self.logger.info(f"duco机器人TCP坐标设置为: {tcp}")
            return True
        except Exception as e:
            self.logger.error(f"设置duco机器人TCP坐标失败: {str(e)}")
            return False
        
    async def set_payload(self, mass: float, cog: List[float]) -> bool:
        """设置duco机器人负载"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
        
        try:
            self.robot.set_load_data([mass] + cog)
            # self.logger.info(f"duco机器人负载设置为: 质量={mass}kg, 重心={cog}")
            return True
        except Exception as e:
            self.logger.error(f"设置duco机器人负载失败: {str(e)}")
            return False

    
    async def stop(self) -> bool:
        """duco机器人紧急停止"""
        if not self.robot:
            return False
        
        try:
            self.robot.stop(False)
            self.state = RobotState.STOPPED
            # self.logger.info("duco机器人已停止")
            return True
        except Exception as e:
            self.logger.error(f"duco机器人紧急停止失败: {str(e)}")
            return False
        
    async def wait_for_movement_completion(self) -> bool:
        """等待duco机器人运动完成"""
        if not self.robot:
            return False
        
        try:
            time.sleep(0.5)
            while self.robot.robotmoving():
                time.sleep(1)

            
            self.state = RobotState.CONNECTED
            return True
        except Exception as e:
            self.logger.error(f"等待duco机器人运动完成时出错: {str(e)}")
            return False
        
    async def enter_teach_mode(self) -> bool:
        """duco机器人进入示教模式"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
        
        try:
            self.robot.teach_mode(False)#直接返回
            # self.logger.info("进入示教模式")
            return True
        except Exception as e:
            self.logger.error(f"进入示教模式失败: {str(e)}")
            return False

    async def exit_teach_mode(self) -> bool:
        """duco机器人退出示教模式"""
        if not self.robot or self.state != RobotState.CONNECTED:
            return False
        try:
            self.robot.end_teach_mode(False)#直接返回
            # self.logger.info("退出示教模式")
            return True
        except Exception as e:
            self.logger.error(f"退出示教模式失败: {str(e)}")
            return False

    async def movel_nonblocking(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """非阻塞直线运动 - Ducocobot实现"""
        if not self.robot or self.state != RobotState.CONNECTED:
            self.logger.warning("Ducocobot机器人未连接")
            return False

        try:
            # Ducocobot需要转换为MoveL指令
            move_command = {
                "command": "MoveL",
                "target": tcp_pose,
                "acceleration": acceleration,
                "velocity": velocity
            }

            self.logger.info(f"Ducocobot movel_nonblocking: {move_command}")

            # 将阻塞操作放到线程池中执行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._blocking_movel, move_command)
            return True

        except Exception as e:
            self.logger.error(f"Ducocobot非阻塞直线移动出错: {str(e)}")
            return False

    def _blocking_movel(self, robot, tcp_pose: List[float], acceleration: float, velocity: float) -> None:
        """在线程池中执行的阻塞movel操作"""
        self.state = RobotState.MOVING
        radius = 0.0  # 设置为0表示不使用圆弧运动
        block = True  # 设置为阻塞模式
        # self.logger.info(f"movel运动: {tcp_pose}")
        self.robot.movel(tcp_pose, velocity, acceleration, radius, [], "", "", block, self._op, False)

#################################################################################################################################
#################################################################################################################################
#################################################################################################################################
#region Dazu工具

# robot_abstraction.py

# 从当前目录的 Dazu 子目录导入 CPS.pyd
from .Dazu.CPS import CPSClient

import math



class DaZuRobot(RobotAbstraction):
    """Dazu机器人抽象类"""
    def __init__(self, ip_address: str, **kwargs):
        #调用父类的构造函数
        super().__init__(ip_address, **kwargs)
        #初始化ip
        self.robot_ip = ip_address
        self.cps = CPSClient()
        self.state = None
        # 工具坐标系移动相关属性
        self._current_pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # [X, Y, Z, rx, ry, rz]
        self._rotation_matrix = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0]
        ]  # 3x3旋转矩阵

     
     
    async def Isconnect(self) -> bool:
        """判断是否连接"""
        if self.cps.HRIF_IsConnected(0):
            self.state = RobotState.CONNECTED
            return True
        else:
            return False
         
    async def connect(self) -> bool:
        """连接机器人"""
        if self.state == RobotState.CONNECTED  and  self.cps.HRIF_IsConnected(0):

            print("机器人已连接")
            return True

        try:
            nRet = self.cps.HRIF_Connect(0,self.robot_ip,10003)
            if nRet != 0:
                self.state = RobotState.DISCONNECTED
                raise Exception("连接失败")
            
            self.state = RobotState.CONNECTED
            await self.set_speed_ratio(100)
            return True

        except Exception as e:
            print(e)
            return False

    async def disconnect(self) -> bool:
        """断开连接"""
        if self.state == RobotState.DISCONNECTED:
            print("机器人未连接")
            return True

        try:    
            nRet = self.cps.HRIF_DisConnect(0)     
            if nRet != 0:
                self.state = RobotState.CONNECTED
                raise Exception("断开连接失败")
            self.state = RobotState.DISCONNECTED
            return True
        except Exception as e:
            print(e)
            return False

    async def set_speed_ratio(self, speed_ratio: float) -> bool:
        """
        设置大族机器人运动速度比例（百分比）
        """
        if self.state!=RobotState.DISCONNECTED:
            try:
                if speed_ratio < 0 or speed_ratio > 100:
                    raise ValueError("速度比例必须在0.0~100范围内")
                
                #需要设置的速度比(0.01~1
                speed_ratio = speed_ratio/100
                print("1111111111111111111111111111111111111111")
                nRet = self.cps.HRIF_SetOverride(0,0, speed_ratio)
                if nRet != 0:
                    raise Exception("设置速度比例失败")
                return True
            except Exception  as e:
                print(e)
                return False
        else:
            print("机器人未连接")
            return False

    async def run_script(self, script: str) -> bool:
        """运行示教器自定义脚本"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            logger.info("机器人未连接")
            return False
        
        try:
            if(script):
                nRet = await self.cps.HRIF_SwitchScript(0,0,script)
                if nRet != 0:
                    raise Exception("运行脚本失败")
            return True
        except Exception as e:
            logger.error(e)
            return False
                        
        
    # 参数概念:关节角度     加速度     速度    
    async def movej(self, joint_angles: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """关节运动"""
        
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            logger.info("机器人未连接")
            return False
        
        try:
            v=velocity
            a=acceleration
            self.state = RobotState.MOVING
            #自定义默认空间位置
            Point=[0,0,0,0,0,0]   
            sTcpName ="TCP"
            sUcsName = "Base"
            velocity = velocity/math.pi*180
            acceleration = acceleration/math.pi*180
            joint_angles = [j/math.pi*180 for j in joint_angles]
            
            dRadius =  50     #过度半径
            nIsUseJoint= 1 # 定义是否使用关节角度
            nIsSeek = 0 # 定义是否使用检测DI停止
            nIOBit = 0  # 定义检测的DI索引
            nIOState = 0 # 定义检测的DI状态 
            strCmdID = "0" # 定义路点ID
            
            await self.set_speed_ratio(100)  # 设置默认速度为100%

            nRet = self.cps.HRIF_MoveJ(0,0, Point, joint_angles, sTcpName , sUcsName, velocity, acceleration,dRadius,nIsUseJoint, nIsSeek, nIOBit, nIOState, strCmdID)
            if nRet != 0:
                logger.error(f"关节运动失败，错误代码: {nRet}")
                raise Exception("关节运动失败")
            if nRet ==40082:
                await self.movej(joint_angles, acceleration, velocity)
            
            await self.wait_for_movement_completion()
            return True

            
        except Exception as e:
            print(e)
            return False

    #使用tcp参数,来进行关节移动  
    #参数概念:TCP角度     加速度     速度
    async def movej_2(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:

        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            print("机器人未连接")
            return False
        try:
            await self.set_speed_ratio(100)  # 设置默认速度为100%

            self.state = RobotState.MOVING        
            tcp_pose = [tcp_pose[0]*1000, tcp_pose[1]*1000, tcp_pose[2]*1000, tcp_pose[3]/math.pi*180, tcp_pose[4]/math.pi*180, tcp_pose[5]/math.pi*180]
            #自定义默认关节角度位置
            joint=[0,0,0,0,0,0]   
            sTcpName ="TCP"
            sUcsName = "Base"
            velocity = velocity/math.pi*180
            acceleration = acceleration/math.pi*180

            
            dRadius =  50     #过度半径
            nIsUseJoint= 0 # 定义是否使用关节角度
            nIsSeek = 0 # 定义是否使用检测DI停止
            nIOBit = 0  # 定义检测的DI索引
            nIOState = 0 # 定义检测的DI状态 
            strCmdID = "0" # 定义路点ID        
        
            nRet = self.cps.HRIF_MoveJ(0,0, tcp_pose, joint, sTcpName , sUcsName, velocity, acceleration,dRadius,nIsUseJoint, nIsSeek, nIOBit, nIOState, strCmdID)
            if nRet != 0:
                self.state = RobotState.CONNECTED
                raise Exception("关节运动失败")
            await self.wait_for_movement_completion()
            return True
  
            
        except Exception as e:
            print(e)
            return False
                    
    async def movel(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """dazu机器人直线运动"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            return False
        try:
            self.state = RobotState.MOVING    
            await self.set_speed_ratio(100)  # 设置默认速度为100%

            #自定义默认关节角度位置
            joint=[0,0,0,0,0,0]   
            sTcpName ="TCP"
            sUcsName = "Base"
            velocity = velocity*1000
            acceleration = acceleration*1000
            tcp_pose = [tcp_pose[0]*1000, tcp_pose[1]*1000, tcp_pose[2]*1000, tcp_pose[3]/math.pi*180, tcp_pose[4]/math.pi*180, tcp_pose[5]/math.pi*180]

            
            dRadius =  50     #过度半径
            nIsSeek = 0 # 定义是否使用检测DI停止
            nIOBit = 0  # 定义检测的DI索引
            nIOState = 0 # 定义检测的DI状态 
            strCmdID = "0" # 定义路点ID        
        
            nRet = self.cps.HRIF_MoveL(0,0, tcp_pose, joint, sTcpName , sUcsName, velocity, acceleration,dRadius, nIsSeek, nIOBit, nIOState, strCmdID)
            if nRet != 0:
                self.state = RobotState.CONNECTED
                raise Exception("直线运动失败")
            await self.wait_for_movement_completion()
            return True
  
            
        except Exception as e:
            print(e)
            return False

#region movetcp工具
    async def movetcp(self, offset, acceleration = 1, velocity = 0.5) -> bool:
        """
        大族机器人沿工具坐标系移动（不依赖HRIF_UcsTcp2Base，手动实现坐标转换）
        :param offset: 工具坐标系下的偏移量 [dx, dy, dz, drx, dry, drz]，前3项为位置偏移（米），后3项为旋转偏移（弧度）
        :param velocity: 工具速度（米/秒）
        :param acceleration: 工具加速度（米/秒²）
        :return: 运动是否成功
        """
        if await self.Isconnect() != True:
            print(f"机器人 {self.robot_ip} 未连接")
            return False
            
        try:
            # 校验偏移量格式
            if offset is None or len(offset) != 6:
                raise ValueError("偏移量必须包含6个元素 [dx, dy, dz, drx, dry, drz]")
            
            # 获取当前TCP位姿（基座系下，单位：米，弧度）
            current_pose = await self.get_current_tcp_pos()
            if current_pose is None:
                print("无法获取当前位姿，移动失败")
                return False
            self._current_pose = current_pose
            print(f"当前TCP位置：{current_pose}")
            
            # 解析当前位置和姿态
            current_x, current_y, current_z = current_pose[0], current_pose[1], current_pose[2]
            rx, ry, rz = current_pose[3], current_pose[4], current_pose[5]  # 旋转分量（弧度）
            
            # 步骤1：将当前姿态（rx, ry, rz）转换为旋转矩阵（工具系到基座系）
            # 采用Z-Y-X欧拉角旋转顺序（机器人常用）
            R = self._euler_to_rot_matrix(rx, ry, rz)
            
            # 步骤2：工具系下的位置偏移（米）
            tool_dx, tool_dy, tool_dz = offset[0], offset[1], offset[2]
            
            # 步骤3：通过旋转矩阵将工具系位置偏移转换为基座系偏移
            base_dx = R[0][0] * tool_dx + R[0][1] * tool_dy + R[0][2] * tool_dz
            base_dy = R[1][0] * tool_dx + R[1][1] * tool_dy + R[1][2] * tool_dz
            base_dz = R[2][0] * tool_dx + R[2][1] * tool_dy + R[2][2] * tool_dz
            
            # 步骤4：计算基座系下的目标位置（当前位置 + 基座系偏移）
            target_x = current_x + base_dx
            target_y = current_y + base_dy
            target_z = current_z + base_dz
            
            # 步骤5：处理旋转偏移（工具系旋转转换为基座系）
            tool_drx, tool_dry, tool_drz = offset[3], offset[4], offset[5]

            # 如果有旋转偏移，需要将工具坐标系下的旋转转换为基座坐标系下的旋转
            if abs(tool_drx) < 1e-10 and abs(tool_dry) < 1e-10 and abs(tool_drz) < 1e-10:
                # 无旋转偏移，保持当前角度
                target_rx, target_ry, target_rz = rx, ry, rz
            else:
                # 将工具坐标系下的旋转偏移转换为基座坐标系下的旋转偏移
                base_drx, base_dry, base_drz = self._tool_rotation_to_base_rotation(
                    tool_drx, tool_dry, tool_drz, rx, ry, rz
                )
                target_rx = rx + base_drx
                target_ry = ry + base_dry
                target_rz = rz + base_drz
            
            # 组装目标位姿
            target_pose = [target_x, target_y, target_z, target_rx, target_ry, target_rz]
            print(f"目标TCP位置：{target_pose}")
            print(f"工具系偏移：{offset}")
            
            # 执行直线运动
            success = await self.movel(target_pose, acceleration, velocity)
            if not success:
                print("移动到目标位姿失败")
                return False
            
            # 等待运动完成
            await self.wait_for_movement_completion()
            return True
            
        except Exception as e:
            print(f"工具坐标系移动失败: {str(e)}")
            print(f"工具坐标系移动失败: {str(e)}")
            return False
    
    async def movetcp_position_to(self, position: List[float], offset: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """
        大族机器人跳过过渡点运动到过渡点沿工具坐标系移动（不依赖HRIF_UcsTcp2Base，手动实现坐标转换）
        :param position: 目标基坐标系位置 [x, y, z, rx, ry, rz]，前3项为位置（米），后3项为旋转（弧度）
        :param offset: 工具坐标系下的偏移量 [dx, dy, dz, drx, dry, drz]，前3项为位置偏移（米），后3项为旋转偏移（弧度）
        :param velocity: 工具速度（米/秒）
        :param acceleration: 工具加速度（米/秒²）
        :return: 运动是否成功
        """
        if await self.Isconnect() != True:
            print(f"机器人 {self.robot_ip} 未连接")
            return False
            
        try:
            # 校验偏移量格式
            if offset is None or len(offset) != 6:
                raise ValueError("偏移量必须包含6个元素 [dx, dy, dz, drx, dry, drz]")
            if position is None or len(position) != 6:
                raise ValueError("位置必须包含6个元素 [x, y, z, rx, ry, rz]")
                        
            # 获取当前TCP位姿（基座系下，单位：米，弧度）            
            # 解析当前位置和姿态
            current_x, current_y, current_z = position[0], position[1], position[2]
            rx, ry, rz = position[3], position[4], position[5]  # 旋转分量（弧度）
            
            # 步骤1：将当前姿态（rx, ry, rz）转换为旋转矩阵（工具系到基座系）
            # 采用Z-Y-X欧拉角旋转顺序（机器人常用）
            R = self._euler_to_rot_matrix(rx, ry, rz)
            
            # 步骤2：工具系下的位置偏移（米）
            tool_dx, tool_dy, tool_dz = offset[0], offset[1], offset[2]
            
            # 步骤3：通过旋转矩阵将工具系位置偏移转换为基座系偏移
            base_dx = R[0][0] * tool_dx + R[0][1] * tool_dy + R[0][2] * tool_dz
            base_dy = R[1][0] * tool_dx + R[1][1] * tool_dy + R[1][2] * tool_dz
            base_dz = R[2][0] * tool_dx + R[2][1] * tool_dy + R[2][2] * tool_dz
            
            # 步骤4：计算基座系下的目标位置（当前位置 + 基座系偏移）
            target_x = current_x + base_dx
            target_y = current_y + base_dy
            target_z = current_z + base_dz
            
            # 步骤5：处理旋转偏移（工具系旋转转换为基座系）
            tool_drx, tool_dry, tool_drz = offset[3], offset[4], offset[5]

            # 如果有旋转偏移，需要将工具坐标系下的旋转转换为基座坐标系下的旋转
            if abs(tool_drx) < 1e-10 and abs(tool_dry) < 1e-10 and abs(tool_drz) < 1e-10:
                # 无旋转偏移，保持当前角度
                target_rx, target_ry, target_rz = rx, ry, rz
            else:
                # 将工具坐标系下的旋转偏移转换为基座坐标系下的旋转偏移
                base_drx, base_dry, base_drz = self._tool_rotation_to_base_rotation(
                    tool_drx, tool_dry, tool_drz, rx, ry, rz
                )
                target_rx = rx + base_drx
                target_ry = ry + base_dry
                target_rz = rz + base_drz
            
            # 组装目标位姿
            target_pose = [target_x, target_y, target_z, target_rx, target_ry, target_rz]
            print(f"目标TCP位置：{target_pose}")
            print(f"工具系偏移：{offset}")
            
            # 执行直线运动
            success = await self.movel(target_pose, acceleration, velocity)
            if not success:
                print("移动到目标位姿失败")
                return False
            
            # 等待运动完成
            await self.wait_for_movement_completion()
            return True
            
        except Exception as e:
            print(f"工具坐标系移动失败: {str(e)}")
            print(f"工具坐标系移动失败: {str(e)}")
            return False
    def _euler_to_rot_matrix(self, rx, ry, rz):
        """
        将欧拉角（rx, ry, rz，弧度）转换为旋转矩阵（Z-Y-X顺序）
        返回3x3旋转矩阵：工具系到基座系的转换矩阵
        """
        # 计算三角函数值
        cr = math.cos(rx)
        sr = math.sin(rx)
        cp = math.cos(ry)
        sp = math.sin(ry)
        cy = math.cos(rz)
        sy = math.sin(rz)

        # 构造旋转矩阵（Z-Y-X顺序）
        return [
            [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
            [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
            [-sp,    cp*sr,           cp*cr          ]
        ]

    def _tool_rotation_to_base_rotation(self, tool_drx, tool_dry, tool_drz, base_rx, base_ry, base_rz):
        """
        将工具坐标系下的旋转偏移转换为基座坐标系下的旋转偏移
        统一使用精确计算，确保高精度要求

        参数:
        - tool_drx, tool_dry, tool_drz: 工具坐标系下的旋转偏移（弧度）
        - base_rx, base_ry, base_rz: 当前基座坐标系下的旋转角度（弧度）

        返回:
        - base_drx, base_dry, base_drz: 基座坐标系下的旋转偏移（弧度）
        """
        # 步骤1: 将基座系当前姿态转换为旋转矩阵 R_base
        R_base = self._euler_to_rot_matrix(base_rx, base_ry, base_rz)

        # 步骤2: 将工具系旋转偏移转换为旋转矩阵 R_tool（精确计算）
        R_tool = self._euler_to_rot_matrix(tool_drx, tool_dry, tool_drz)

        # 步骤3: 基座系下的总旋转矩阵 R_total = R_base * R_tool
        R_total = self._matrix_multiply(R_base, R_tool)

        # 步骤4: 将R_total转换回欧拉角
        total_rx, total_ry, total_rz = self._rot_matrix_to_euler(R_total)

        # 步骤5: 计算基座系下的旋转偏移
        base_drx = self._normalize_angle(total_rx - base_rx)
        base_dry = self._normalize_angle(total_ry - base_ry)
        base_drz = self._normalize_angle(total_rz - base_rz)

        return base_drx, base_dry, base_drz

    def _matrix_multiply(self, A, B):
        """
        两个3x3矩阵相乘
        """
        result = [[0.0 for _ in range(3)] for _ in range(3)]
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    result[i][j] += A[i][k] * B[k][j]
        return result

    def _rot_matrix_to_euler(self, R):
        """
        将旋转矩阵转换为欧拉角（Z-Y-X顺序）
        使用高精度算法，避免数值不稳定问题

        参数:
        - R: 3x3旋转矩阵

        返回:
        - rx, ry, rz: 欧拉角（弧度）
        """
        # 确保旋转矩阵的有效性（正交性检查）
        # 这里可以添加正交性检查和修正代码，为了简化暂时跳过

        # 使用更稳定的算法计算欧拉角
        # 方法1: 使用atan2来避免数值不稳定
        sy = math.sqrt(R[0][0] * R[0][0] + R[1][0] * R[1][0])

        singular = sy < 1e-10  # 更严格的阈值

        if not singular:
            # 常规情况，使用更稳定的公式
            x = math.atan2(R[2][1], R[2][2])
            y = math.atan2(-R[2][0], sy)
            z = math.atan2(R[1][0], R[0][0])
        else:
            # 奇异情况（万向节死锁）
            # 当仰角接近±90度时的处理
            x = math.atan2(-R[1][2], R[1][1])
            y = math.atan2(-R[2][0], sy)
            z = 0

        # 角度归一化到[-π, π]范围
        rx = self._normalize_angle(x)
        ry = self._normalize_angle(y)
        rz = self._normalize_angle(z)

        return rx, ry, rz

    def _normalize_angle(self, angle):
        """
        将角度归一化到[-π, π]范围
        """
        while angle > math.pi:
            angle -= 2 * math.pi
        while angle < -math.pi:
            angle += 2 * math.pi
        return angle
#endregion
    async def get_current_tcp_pos(self) -> Optional[List[float]]:  
        """获取大族机器人当前tcp位置"""
        if not await self.Isconnect() :#or self.state != RobotState.CONNECTED
                return None
        try:
            result=[]
            
            nRet=self.cps.HRIF_ReadActTcpPos(0,0,result)
            result = [float(i) for i in result]
            if nRet != 0:
                raise Exception("读取tcp实际位置失败")
            result = [result[0]/1000, result[1]/1000, result[2]/1000, result[3]/180*math.pi, result[4]/180*math.pi, result[5]/180*math.pi]
            return result
        except Exception as e:
            print(e)
            return None

    async def get_current_joint_pos(self) -> Optional[List[float]]:
        """获取大族机器人当前关节角度"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            return None
        
        try:
            result=[]
            nRet=self.cps.HRIF_ReadActJointPos(0,0,result)
            result = [float(i) for i in result]
            if nRet != 0:
                raise Exception("读取关节实际位置失败")
            result = [result[0]/180*math.pi, result[1]/180*math.pi, result[2]/180*math.pi, result[3]/180*math.pi, result[4]/180*math.pi, result[5]/180*math.pi]
            return result
        except Exception as e:
            print(e)
            return None

    async def set_tool(self, tcp: List[float]) -> bool:
        """设置大族机器人TCP"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            return False
        
        try:
            nRet = self.cps.HRIF_SetTCP(0,0,tcp)
            if nRet != 0:
                raise Exception("设置tcp失败")
            return True
        except Exception as e:
            print(e)
            return False
     
    #mass 负载(kg)        cog :dX ,dY ,dZ  (质心朝x轴的偏移量)(mm)
    async def set_payload(self, mass: float, cog: List[float]) -> bool:
        """设置大族机器人负载"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            return False
        
        try:   
            
            # 定义负载参数
            dX = cog[0]  # 负载质心X坐标
            dY = cog[1]  # 负载质心Y坐标
            dZ = cog[2]  # 负载质心Z坐标

            nRet = self.cps.HRIF_SetPayload(0,0,mass,dX,dY,dZ)

            if nRet != 0:
                raise Exception("设置负载失败")
            return True
        except Exception as e:
            print(e)
            return False
    
    async def stop(self) -> bool:
        """大族机器人紧急停止"""
        if not await self.Isconnect():
            return False
        
        try:
            self.state = RobotState.STOPPED
            nRet = self.cps.HRIF_GrpStop(0,0)
            if nRet != 0:
                raise Exception("紧急停止失败")
            return True
        except Exception as e:
            print(e)
            return False

  
    async def wait_for_movement_completion(self) -> bool:
        """等待机器人运动完成"""
        # if  not await  self.Isconnect():
        #     return False
        # try:
        #     await asyncio.sleep(0.5)

        #     while await self.robotmoving():
        #         await asyncio.sleep(1)

        #     if self.state == RobotState.MOVING:
        #         self.state = RobotState.CONNECTED
        #     return True    
        # except Exception as e:
        #     print(e)
        return True
      
      

    async def enter_teach_mode(self) -> bool:
        """大族机器人进入自由驱动"""
        if not self.Isconnect or self.state == RobotState.DISCONNECTED:
            return False
        
        try: 
            
            
            nRet = self.cps.HRIF_GrpOpenFreeDriver(0,0)
            if nRet != 0:
                raise Exception("进入自由驱动失败")
            
            print("进入自由驱动成功")
            return True
        except Exception as e:
            print(e)
            return False
        
        
 
    async def exit_teach_mode(self) -> bool:
        """大族机器人退出自由驱动"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            return False

        try:

            nRet = self.cps.HRIF_GrpCloseFreeDriver(0,0)
            if nRet != 0:
                raise Exception("退出自由驱动失败")

            print("退出自由驱动成功")
            return True
        except Exception as e:
            print(e)
            return False

    async def movel_nonblocking(self, tcp_pose: List[float], acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """非阻塞直线运动 - DaZu机器人实现"""
        if not await self.Isconnect() or self.state == RobotState.DISCONNECTED:
            print("DaZu机器人未连接")
            return False

        try:
            print(f"DaZu movel_nonblocking: {tcp_pose}")

            # 将阻塞操作放到线程池中执行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._blocking_movel, tcp_pose, acceleration, velocity)
            return True

        except Exception as e:
            print(f"DaZu非阻塞直线移动出错: {str(e)}")
            return False

    def _blocking_movel(self, tcp_pose: List[float], acceleration: float, velocity: float) -> None:
        """在线程池中执行的阻塞movel操作"""
        #自定义默认关节角度位置
        joint=[0,0,0,0,0,0]   
        sTcpName ="TCP"
        sUcsName = "Base"
        velocity = velocity*1000
        acceleration = acceleration*1000
        tcp_pose = [tcp_pose[0]*1000, tcp_pose[1]*1000, tcp_pose[2]*1000, tcp_pose[3]/math.pi*180, tcp_pose[4]/math.pi*180, tcp_pose[5]/math.pi*180]

        
        dRadius =  50     #过度半径
        nIsSeek = 0 # 定义是否使用检测DI停止
        nIOBit = 0  # 定义检测的DI索引
        nIOState = 0 # 定义检测的DI状态 
        strCmdID = "0" # 定义路点ID        
    
        nRet = self.cps.HRIF_MoveL(0,0, tcp_pose, joint, sTcpName , sUcsName, velocity, acceleration,dRadius, nIsSeek, nIOBit, nIOState, strCmdID)

    async def robotmoving(self) -> bool:
        """当前机器人是否在移动"""
        if  not await self.Isconnect():
            return False
        
        try:
            result = [ ]
            nRet = self.cps.HRIF_IsMotionDone(0,0,result)
            if nRet != 0:
                raise Exception("查询机器人移动状态失败") 
            
            return not result[0]

                   
        except Exception as e:
            print(e)
            return False






##################################################################################################################################################
##################################################################################################################################################
##################################################################################################################################################
##################################################################################################################################################



#region 机器人工厂类

class RobotFactory:
    """机器人工厂类"""
    
    @staticmethod
    def create_robot(brand: RobotBrand, **kwargs) -> RobotAbstraction:
        """创建机器人实例"""
        if brand == RobotBrand.UNIVERSAL_ROBOTS:
            return UniversalRobotsRobot("192.168.0.128", **kwargs)
        elif brand == RobotBrand.DUCOCOBOT:
            return DucocobotRobot("192.168.0.6", **kwargs)
        elif brand == RobotBrand.DAZU:
            return DaZuRobot("192.168.0.10", **kwargs)
            pass
        elif brand == RobotBrand.KUKA:
            raise NotImplementedError("KUKA 机器人尚未实现")
        elif brand == RobotBrand.ABB:
            raise NotImplementedError("ABB 机器人尚未实现")
        else:
            raise ValueError(f"不支持的机器人品牌: {brand}")

class RobotController:
    """单机器人控制器，遵循KISS原则"""
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RobotController, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 防止重复初始化
        if RobotController._initialized:
            return
            
        self.robot: Optional[RobotAbstraction] = None
        self.logger = logger
        
        RobotController._initialized = True
    
    @classmethod
    def get_instance(cls):
        """获取 RobotController 单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_robot(self, robot: RobotAbstraction):
        """设置机器人实例"""
        self.robot = robot
        # self.logger.info(f"已设置机器人: {robot.__class__.__name__}")
    
    def clear_robot(self):
        """清除机器人实例"""
        if self.robot:
            self.robot = None
            # self.logger.info("已清除机器人实例")
    
    async def connect_robot(self) -> bool:
        """连接机器人"""
        if self.robot:
            return await self.robot.connect()
        return False
    
    async def disconnect_robot(self) -> bool:
        """断开机器人连接"""
        if self.robot:
            return await self.robot.disconnect()
        return False
    
    async def stop_robot(self) -> bool:
        """停止机器人"""
        if self.robot:
            return await self.robot.stop()
        return False
    
    def get_robot_status(self) -> dict:
        """获取机器人状态"""
        if not self.robot:
            return {'status': 'no_robot'}
        
        return {
            'brand': self.robot.__class__.__name__,
            'ip_address': self.robot.ip_address,
            'state': self.robot.state.value,
            'connected': self.robot.state != RobotState.DISCONNECTED
        }
    
    def is_connected(self) -> bool:
        """检查机器人是否已连接"""
        return self.robot is not None and self.robot.state != RobotState.DISCONNECTED