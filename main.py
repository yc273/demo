#!/usr/bin/env python3
"""
简化版调试测试脚本
直接调用底层函数，无需MCP/Agent框架
完整实现 mcp_client.py 的所有功能
"""

import asyncio
import sys
import os
import math
import json
from typing import List

# 添加路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools.robots.robot_abstraction import (
    RobotBrand,
    RobotController,
    UniversalRobotsRobot,
    DucocobotRobot,
    DaZuRobot
)
from tools.algorithms.algorithms import AlgorithmsApi
from tools.io_modules.io_controller import IoController
from tools.io_modules.device_controllers import Liyou
from tools.vision.VisionApi import VisionApi
from logs.logger_utils import logger


# ==================== 配置 ====================
ROBOT_IP = {
    "ur": "192.168.0.128",
    "duco": "192.168.0.6",
    "dazu": "192.168.0.10",
}

VISION_IP = "127.0.0.1"
VISION_PORT = 65432

IO_IP = "192.168.0.21"
IO_PORT = 2317

PAYLOAD_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "payload_data.json")
JOINT_POSES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "joint_poses.json")
# ================================================


class DirectRobotControl:
    """直接调用底层函数的机器人控制类"""

    def __init__(self):
        self.robot_brand = None
        self.robot_controller = RobotController.get_instance()
        self.algorithms = None
        self.io_controller = None
        self.liyou = None
        self.vision_api = None
        self.robot_connected = False
        self.vision_connected = False
        self.payload_data = self.load_payload_config()
        self.joint_poses = self.load_joint_poses()

    # ==================== 1. 机器人连接 ====================
    async def connect_robot(self, brand: str = "ur"):
        """连接机器人并初始化算法"""
        print(f"\n=== 连接 {brand.upper()} 机器人 ===")
        try:
            ip = ROBOT_IP.get(brand)
            if not ip:
                print(f"不支持的机器人品牌: {brand}")
                return False

            # 创建机器人实例
            if brand == "ur":
                robot = UniversalRobotsRobot(ip)
            elif brand == "duco":
                robot = DucocobotRobot(ip)
            elif brand == "dazu":
                robot = DaZuRobot(ip)
            else:
                return False

            self.robot_controller.set_robot(robot)
            success = await self.robot_controller.connect_robot()

            if success:
                # 初始化标定算法
                self.robot_brand = brand
                self.algorithms = AlgorithmsApi(brand=brand)
                self.robot_connected = True
                print(f"机器人连接成功: {ip}")
                print(f"算法初始化完成")
            else:
                print(f"机器人连接失败")

            return success
        except Exception as e:
            print(f"连接异常: {e}")
            return False

    async def disconnect_robot(self):
        """断开机器人连接"""
        try:
            if self.robot_connected:
                success = await self.robot_controller.disconnect_robot()
                if success:
                    self.robot_connected = False
                    print("已断开机器人连接")
                return success
            else:
                print(" 机器人未连接")
                return False
        except Exception as e:
            print(f"断开异常: {e}")
            return False

    # ==================== 2. 视觉连接 ====================
    async def connect_vision(self):
        """连接视觉服务器"""
        print("\n=== 连接视觉服务器 ===")
        try:
            self.vision_api = VisionApi(VISION_IP, VISION_PORT)
            success = await self.vision_api.connect()

            if success:
                self.vision_connected = True
                print(f"视觉服务器连接成功: {VISION_IP}:{VISION_PORT}")
            else:
                print(f"视觉服务器连接失败")

            return success
        except Exception as e:
            print(f"视觉连接异常: {e}")
            return False

    async def disconnect_vision(self):
        """断开视觉连接"""
        try:
            if self.vision_connected and self.vision_api:
                await self.vision_api.disconnect()
                self.vision_connected = False
                print("已断开视觉连接")
                return True
            else:
                print(" 视觉未连接")
                return False
        except Exception as e:
            print(f"断开视觉异常: {e}")
            return False

    # ==================== 3. 加载工具 ====================
    def select_tool(self, tool_name: str):
        """选择工具"""
        print(f"\n=== 加载工具: {tool_name} ===")
        try:
            if not self.algorithms:
                print("算法未初始化，请先连接机器人")
                return False

            success = self.algorithms.select_tool(tool_name)

            if success:
                print(f"工具加载成功: {tool_name}")

                # 显示原点位置
                home = self.algorithms.get_home_position()
                if home:
                    print(f" 原点位置: X={home[0]:.3f}, Y={home[1]:.3f}, Z={home[2]:.3f}")
            else:
                print(f"工具加载失败")

            return success
        except Exception as e:
            print(f"加载工具异常: {e}")
            return False

    # ==================== 4. 螺钉标定 ====================
    async def screw_calibration(self):
        """螺钉标定流程"""
        print("\n=== 螺钉标定流程 ===")
        try:
            if not self.algorithms or not self.algorithms.tool:
                print("请先加载工具 (screw_sleeve)")
                return False

            robot = self.robot_controller.robot

            print(" 步骤1: 移动到第一个标定点")
            print("   请手动控制机器人对准第一个螺钉")
            input("   对准后按 Enter 继续...")

            pose1 = await robot.get_current_tcp_pos()
            print(f"   当前位姿: {pose1}")

            print("\n 步骤2: 从视觉获取第一个螺钉坐标")
            if self.vision_connected:
                result1 = await self.vision_api.detect_screw()
                if result1 and "points" in result1:
                    img_point1 = result1["points"][0]
                    print(f"   图像坐标: {img_point1}")
                else:
                    print("    视觉检测失败，请手动输入图像坐标")
                    x1 = float(input("   请输入X坐标: "))
                    y1 = float(input("   请输入Y坐标: "))
                    img_point1 = [x1, y1]
            else:
                print("    视觉未连接，请手动输入图像坐标")
                x1 = float(input("   请输入X坐标: "))
                y1 = float(input("   请输入Y坐标: "))
                img_point1 = [x1, y1]

            print("\n 步骤3: 移动到第二个标定点")
            await robot.movetcp([0.01, -0.02, 0, 0, 0, 0], acceleration=0.2, velocity=0.1)
            await asyncio.sleep(1)
            input("   微调对准第二个螺钉后按 Enter 继续...")

            pose2 = await robot.get_current_tcp_pos()
            print(f"   当前位姿: {pose2}")

            print("\n 步骤4: 从视觉获取第二个螺钉坐标")
            if self.vision_connected:
                result2 = await self.vision_api.detect_screw()
                if result2 and "points" in result2:
                    img_point2 = result2["points"][0]
                    print(f"   图像坐标: {img_point2}")
                else:
                    x2 = float(input("   请输入X坐标: "))
                    y2 = float(input("   请输入Y坐标: "))
                    img_point2 = [x2, y2]
            else:
                x2 = float(input("   请输入X坐标: "))
                y2 = float(input("   请输入Y坐标: "))
                img_point2 = [x2, y2]

            print("\n 步骤5: 移动到原点位置")
            input("   移动到原点后按 Enter 继续...")
            pose3 = await robot.get_current_tcp_pos()

            # 执行标定
            print("\n  执行螺钉标定...")
            success = self.algorithms.screw_calibration(
                img_point1, img_point2, pose1, pose2, pose3
            )

            if success:
                print("螺钉标定成功！")
            else:
                print("螺钉标定失败")

            return success
        except Exception as e:
            print(f"螺钉标定异常: {e}")
            return False

    # ==================== 5. 角度标定 ====================
    async def angle_calibration(self):
        """角度标定流程"""
        print("\n=== 角度标定流程 ===")
        try:
            if not self.algorithms:
                print("算法未初始化")
                return False

            print(" 步骤1: 移动机器人使工具垂直向下")
            input("   调整完成后按 Enter 继续...")

            print("\n 步骤2: 从视觉获取法向量")
            if self.vision_connected:
                result = await self.vision_api.get_normal_vector()
                if result and "normal" in result:
                    normal = result["normal"]
                    print(f"   法向量: [{normal[0]:.4f}, {normal[1]:.4f}, {normal[2]:.4f}]")
                else:
                    print("    视觉检测失败，请手动输入法向量")
                    nx = float(input("   请输入NX: "))
                    ny = float(input("   请输入NY: "))
                    nz = float(input("   请输入NZ: "))
                    normal = [nx, ny, nz]
            else:
                print("   默认垂直向下 [0, 0, 1]")
                normal = [0, 0, 1]

            # 执行角度标定
            print("\n  执行角度标定...")
            success = self.algorithms.angle_calibration(tuple(normal))

            if success:
                print("角度标定成功！")
            else:
                print("角度标定失败")

            return success
        except Exception as e:
            print(f"角度标定异常: {e}")
            return False

    # ==================== 6. 深度标定 ====================
    async def depth_calibration(self):
        """深度标定流程"""
        print("\n=== 深度标定流程 ===")
        try:
            if not self.algorithms:
                print("算法未初始化")
                return False

            print(" 步骤1: 移动机器人到标定深度位置")
            input("   移动到位后按 Enter 继续...")

            print("\n 步骤2: 从视觉获取深度信息")
            if self.vision_connected:
                result = await self.vision_api.get_depth()
                if result and "depth" in result:
                    depth = result["depth"]
                    print(f"   深度: {depth:.3f} mm")
                else:
                    print("    视觉检测失败，请手动输入深度")
                    depth = float(input("   请输入深度(mm): "))
            else:
                depth = float(input("   请输入深度(mm): "))

            # 执行深度标定
            print("\n  执行深度标定...")
            success = self.algorithms.depth_calibrate(depth)

            if success:
                print("深度标定成功！")
            else:
                print("深度标定失败")

            return success
        except Exception as e:
            print(f"深度标定异常: {e}")
            return False

    # ==================== 7. 螺钉调整 ====================
    async def screw_adjustment(self):
        """螺钉调整流程"""
        print("\n=== 螺钉调整流程 ===")
        try:
            if not self.algorithms or not self.robot_connected:
                print("请先连接机器人并加载工具")
                return False

            robot = self.robot_controller.robot

            print(" 步骤1: 从视觉检测螺钉位置")
            if self.vision_connected:
                result = await self.vision_api.detect_screw()
                if result and "points" in result:
                    img_point = result["points"][0]
                    print(f"   检测到螺钉: {img_point}")
                else:
                    print("    未检测到螺钉")
                    return False
            else:
                print("    视觉未连接，请手动输入坐标")
                x = float(input("   请输入X坐标: "))
                y = float(input("   请输入Y坐标: "))
                img_point = [x, y]

            # 计算调整量
            print("\n  计算调整量...")
            offset = self.algorithms.screw_adjust(img_point)

            if offset:
                print(f"   调整偏移: [{offset[0]:.4f}, {offset[1]:.4f}, {offset[2]:.4f}]")

                # 检查是否已对齐
                if self.algorithms.is_screw_adjusted_perfectly(img_point):
                    print("螺钉已对齐，无需调整")
                    return True

                # 执行调整
                print("\n 执行位置调整...")
                success = await robot.movetcp(offset, acceleration=0.3, velocity=0.2)

                if success:
                    print("位置调整完成")
                else:
                    print("位置调整失败")

                return success
            else:
                print("计算调整量失败")
                return False
        except Exception as e:
            print(f"螺钉调整异常: {e}")
            return False

    # ==================== 8. 角度调整 ====================
    async def angle_adjustment(self):
        """角度调整流程"""
        print("\n=== 角度调整流程 ===")
        try:
            if not self.algorithms or not self.robot_connected:
                print("请先连接机器人")
                return False

            robot = self.robot_controller.robot

            print(" 步骤1: 从视觉获取法向量")
            if self.vision_connected:
                result = await self.vision_api.get_normal_vector()
                if result and "normal" in result:
                    measured_z = result["normal"]
                    print(f"   测量法向量: [{measured_z[0]:.4f}, {measured_z[1]:.4f}, {measured_z[2]:.4f}]")
                else:
                    print("    视觉检测失败")
                    return False
            else:
                print("    视觉未连接，请手动输入法向量")
                nx = float(input("   请输入NX: "))
                ny = float(input("   请输入NY: "))
                nz = float(input("   请输入NZ: "))
                measured_z = [nx, ny, nz]

            # 计算调整量
            print("\n  计算角度调整量...")
            offset = self.algorithms.angle_adjust(measured_z)

            if offset:
                print(f"   角度调整: RX={math.degrees(offset[3]):.2f}°, RY={math.degrees(offset[4]):.2f}°")

                # 检查是否已对齐
                if self.algorithms.is_angle_adjusted_perfectly(measured_z):
                    print("角度已对齐，无需调整")
                    return True

                # 执行调整
                print("\n 执行角度调整...")
                success = await robot.movetcp(offset, acceleration=0.3, velocity=0.2)

                if success:
                    print("角度调整完成")
                else:
                    print("角度调整失败")

                return success
            else:
                print("计算调整量失败")
                return False
        except Exception as e:
            print(f"角度调整异常: {e}")
            return False

    # ==================== 9. 深度调整 ====================
    async def depth_adjustment(self):
        """深度调整流程"""
        print("\n=== 深度调整流程 ===")
        try:
            if not self.algorithms or not self.robot_connected:
                print("请先连接机器人")
                return False

            robot = self.robot_controller.robot

            print(" 步骤1: 从视觉获取深度")
            if self.vision_connected:
                result = await self.vision_api.get_depth()
                if result and "depth" in result:
                    current_depth = result["depth"]
                    print(f"   当前深度: {current_depth:.3f} mm")
                else:
                    print("    视觉检测失败")
                    return False
            else:
                current_depth = float(input("   请输入当前深度(mm): "))

            # 计算调整量
            print("\n  计算深度调整量...")
            offset = self.algorithms.depth_adjust(current_depth)

            if offset:
                print(f"   深度调整: Z={offset[2]*1000:.3f} mm")

                # 检查是否已对齐
                if self.algorithms.is_depth_adjusted_perfectly(current_depth):
                    print("深度已对齐，无需调整")
                    return True

                # 执行调整
                print("\n 执行深度调整...")
                success = await robot.movetcp(offset, acceleration=0.3, velocity=0.2)

                if success:
                    print("深度调整完成")
                else:
                    print("深度调整失败")

                return success
            else:
                print("计算调整量失败")
                return False
        except Exception as e:
            print(f"深度调整异常: {e}")
            return False

    # ==================== 10. 读取当前TCP位置 ====================
    async def get_current_tcp(self):
        """读取当前TCP位置"""
        print("\n=== 读取当前TCP位置 ===")
        try:
            if not self.robot_connected:
                print("X 机器人未连接")
                return False

            robot = self.robot_controller.robot
            pose = await robot.get_current_tcp_pos()

            if pose:
                print("\n当前TCP位姿:")
                print(f"  X = {pose[0]:.6f} m")
                print(f"  Y = {pose[1]:.6f} m")
                print(f"  Z = {pose[2]:.6f} m")
                print(f"  RX = {pose[3]:.6f} rad ({math.degrees(pose[3]):.2f} deg)")
                print(f"  RY = {pose[4]:.6f} rad ({math.degrees(pose[4]):.2f} deg)")
                print(f"  RZ = {pose[5]:.6f} rad ({math.degrees(pose[5]):.2f} deg)")
                return True
            else:
                print("X 获取TCP位置失败")
                return False
        except Exception as e:
            print(f"X 读取TCP位置异常: {e}")
            return False

    # ==================== 11. 读取当前关节位置 ====================
    async def get_current_joints(self):
        """读取当前关节位置"""
        print("\n=== 读取当前关节位置 ===")
        try:
            if not self.robot_connected:
                print("X 机器人未连接")
                return False

            robot = self.robot_controller.robot
            joints = await robot.get_current_joint_pos()

            if joints:
                print("\n当前关节角度:")
                for i, angle in enumerate(joints, 1):
                    print(f"  J{i} = {angle:.6f} rad ({math.degrees(angle):.2f} deg)")
                return True
            else:
                print("X 获取关节位置失败")
                return False
        except Exception as e:
            print(f"X 读取关节位置异常: {e}")
            return False

    # ==================== 12. 移动指令 ====================
    async def execute_move_command(self, command_str: str):
        """执行移动命令"""
        print(f"\n=== 执行移动命令: {command_str} ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            robot = self.robot_controller.robot

            # 解析命令
            parts = command_str.split()
            if len(parts) < 2:
                print("命令格式错误")
                print("   正确格式: movel/movej/movej_2/movetcp x y z rx ry rz")
                return False

            cmd_type = parts[0].lower()
            params = [float(x) for x in parts[1:]]

            if len(params) != 6:
                print("参数数量错误，需要6个参数")
                return False

            # 执行对应命令
            if cmd_type == "movel":
                success = await robot.movel(params, acceleration=0.5, velocity=0.3)
            elif cmd_type == "movetcp":
                success = await robot.movetcp(params, acceleration=0.3, velocity=0.2)
            elif cmd_type == "movej":
                success = await robot.movej(params, acceleration=0.5, velocity=0.3)
            elif cmd_type == "movej_2":
                success = await robot.movej_2(params, acceleration=0.5, velocity=0.3)
            
            else:
                print(f"不支持的命令类型: {cmd_type}")
                return False

            if success:
                print(f"{cmd_type} 执行成功")
            else:
                print(f"{cmd_type} 执行失败")

            return success
        except ValueError:
            print("参数格式错误，请输入数字")
            return False
        except Exception as e:
            print(f"执行命令异常: {e}")
            return False

    # ==================== 12. 保存位姿 ====================
    async def save_pose(self, point_name: str):
        """保存当前位姿"""
        print(f"\n=== 保存当前位姿: {point_name} ===")
        try:
            if not self.algorithms or not self.robot_connected:
                print("机器人未连接")
                return False

            robot = self.robot_controller.robot
            pose = await robot.get_current_tcp_pos()

            if pose:
                success = self.algorithms.record_point(point_name, pose)
                if success:
                    print(f"位姿已保存: {point_name}")
                    print(f"   位置: X={pose[0]:.3f}, Y={pose[1]:.3f}, Z={pose[2]:.3f}")
                else:
                    print(f"保存失败")
                return success
            else:
                print("获取当前位姿失败")
                return False
        except Exception as e:
            print(f"保存位姿异常: {e}")
            return False

    # ==================== 13. 移动到保存的位姿 ====================
    async def move_to_saved_pose(self):
        """移动到保存的位姿"""
        print("\n=== 移动到保存的位姿 ===")
        try:
            if not self.algorithms or not self.robot_connected:
                print("机器人未连接")
                return False

            # 列出所有保存的位姿
            points = self.algorithms.list_recorded_points()

            if not points:
                print(" 没有保存的位姿")
                return False

            print(" 已保存的位姿:")
            for i, (name, pose) in enumerate(points.items(), 1):
                print(f"   {i}. {name}: X={pose[0]:.3f}, Y={pose[1]:.3f}, Z={pose[2]:.3f}")

            # 选择位姿
            choice = input("\n请输入位姿名称或编号: ").strip()

            # 如果是数字，转换为名称
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(points):
                    point_name = list(points.keys())[idx]
                else:
                    print("无效的编号")
                    return False
            else:
                point_name = choice

            # 获取位姿
            pose = self.algorithms.get_recorded_point(point_name)

            if pose:
                robot = self.robot_controller.robot
                print(f" 移动到: {point_name}")

                success = await robot.movel(pose, acceleration=0.5, velocity=0.3)

                if success:
                    print(f"移动完成")
                else:
                    print(f"移动失败")

                return success
            else:
                print(f"位姿不存在: {point_name}")
                return False
        except Exception as e:
            print(f"移动异常: {e}")
            return False

    # ==================== 14. 保存关节位姿 ====================
    async def save_joint_pose(self, pose_name: str):
        """保存当前关节位姿"""
        print(f"\n=== 保存关节位姿: {pose_name} ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            robot = self.robot_controller.robot
            joints = await robot.get_current_joint_pos()

            if joints:
                # 保存关节角度（弧度）
                self.joint_poses[pose_name] = {
                    "joints": joints,
                    "joints_deg": [math.degrees(j) for j in joints]  # 同时保存角度制
                }
                # 保存到文件
                if self.save_joint_poses_to_file():
                    print(f"关节位姿已保存: {pose_name}")
                    print(f"   关节角度(度): {[f'{j:.2f}°' for j in self.joint_poses[pose_name]['joints_deg']]}")
                    return True
                else:
                    print("保存到文件失败")
                    return False
            else:
                print("获取关节位姿失败")
                return False
        except Exception as e:
            print(f"保存关节位姿异常: {e}")
            return False

    # ==================== 15. 移动到保存的关节位姿 ====================
    async def move_to_saved_joint_pose(self):
        """移动到保存的关节位姿"""
        print("\n=== 移动到保存的关节位姿 ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            if not self.joint_poses:
                print(" 没有保存的关节位姿")
                return False

            # 列出所有保存的关节位姿
            print(" 已保存的关节位姿:")
            pose_list = list(self.joint_poses.items())
            for i, (name, data) in enumerate(pose_list, 1):
                joints_deg = data['joints_deg']
                print(f"   {i}. {name}: {[f'{j:.1f}°' for j in joints_deg]}")

            # 选择位姿
            choice = input("\n请输入位姿名称或编号: ").strip()

            # 如果是数字，转换为名称
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(pose_list):
                    pose_name = pose_list[idx][0]
                else:
                    print("无效的编号")
                    return False
            else:
                pose_name = choice

            # 获取关节位姿
            if pose_name not in self.joint_poses:
                print(f"位姿不存在: {pose_name}")
                return False

            joints = self.joint_poses[pose_name]['joints']
            robot = self.robot_controller.robot
            print(f" 移动到: {pose_name}")
            print(f"   关节角度(度): {[f'{j:.1f}°' for j in self.joint_poses[pose_name]['joints_deg']]}")

            # 使用 movej 移动到关节位姿
            success = await robot.movej(joints, acceleration=0.5, velocity=0.3)

            if success:
                print(f"移动完成")
            else:
                print(f"移动失败")

            return success
        except Exception as e:
            print(f"移动异常: {e}")
            return False

    # ==================== 16. 删除保存的关节位姿 ====================
    def delete_saved_joint_pose(self):
        """删除保存的关节位姿"""
        print("\n=== 删除保存的关节位姿 ===")
        try:
            if not self.joint_poses:
                print(" 没有保存的关节位姿")
                return False

            # 列出所有保存的关节位姿
            print(" 已保存的关节位姿:")
            pose_list = list(self.joint_poses.items())
            for i, (name, data) in enumerate(pose_list, 1):
                joints_deg = data['joints_deg']
                print(f"   {i}. {name}: {[f'{j:.1f}°' for j in joints_deg]}")

            # 选择位姿
            choice = input("\n请输入要删除的位姿名称或编号 (0返回): ").strip()

            if choice == "0":
                return True

            # 如果是数字，转换为名称
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(pose_list):
                    pose_name = pose_list[idx][0]
                else:
                    print("无效的编号")
                    return False
            else:
                pose_name = choice

            # 删除位姿
            if pose_name in self.joint_poses:
                del self.joint_poses[pose_name]
                # 保存到文件
                if self.save_joint_poses_to_file():
                    print(f"已删除位姿: {pose_name}")
                    return True
                else:
                    print("保存到文件失败")
                    return False
            else:
                print(f"位姿不存在: {pose_name}")
                return False
        except Exception as e:
            print(f"删除异常: {e}")
            return False

    # ==================== 17. 气泵io控制 ====================
    async def pneumatic_gripper_control(self):
        """气泵io控制"""
        print("\n=== 气泵io控制 ===")
        try:
            if not self.io_controller:
                print("IO控制器未连接")
                return False

            while True:
                print("\n1. 打开io口  2. 关闭io口  0. 返回")
                choice = input("请选择: ").strip()

                if choice == "1":
                    print("\n输入打开几号io：")
                    choice2 = input("请选择: ").strip()                   
                    self.io_controller.set_do_command(int(choice2), True)
                    await self.io_controller.send_command()

                elif choice == "2":
                    print("\n输入关闭几号io：")
                    choice2 = input("请选择: ").strip()                   
                    self.io_controller.set_do_command(int(choice2), False)
                    await self.io_controller.send_command()
                elif choice == "0":
                    break
                else:
                    print("无效选择")

            return True
        except Exception as e:
            print(f"气泵io控制异常: {e}")
            return False

    # ==================== 15. 拖动示教 ====================
    async def teach_mode_control(self):
        """拖动示教控制"""
        print("\n=== 拖动示教模式 ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            robot = self.robot_controller.robot

            while True:
                print("\n1. 进入示教模式  2. 退出示教模式  0. 返回")
                choice = input("请选择: ").strip()

                if choice == "1":
                    success = await robot.enter_teach_mode()
                    if success:
                        print("已进入示教模式，可以手动拖动机器人")
                    else:
                        print("进入示教模式失败")
                elif choice == "2":
                    success = await robot.exit_teach_mode()
                    if success:
                        print("已退出示教模式")
                    else:
                        print("退出示教模式失败")
                elif choice == "0":
                    break
                else:
                    print("无效选择")

            return True
        except Exception as e:
            print(f"示教模式异常: {e}")
            return False

    # ==================== 系统状态 ====================
    def get_status(self):
        """获取系统状态"""
        status = {
            "机器人品牌": self.robot_brand.upper() if self.robot_brand else "未连接",
            "机器人连接": "已连接" if self.robot_connected else "未连接",
            "视觉连接": "已连接" if self.vision_connected else "未连接",
            "IO控制器": "已连接" if self.io_controller and self.io_controller.is_connected else "未连接",
        }

        if self.algorithms and self.algorithms.tool:
            status["当前工具"] = self.algorithms.tool
            status["位置标定"] = "已标定" if self.algorithms.is_positon_calibrated else "未标定"
            status["角度标定"] = "已标定" if self.algorithms.is_angle_calibrated else "未标定"
            status["深度标定"] = "已标定" if self.algorithms.is_depth_calibrated else "未标定"

        print("\n=== 系统状态 ===")
        for key, value in status.items():
            print(f"{key}: {value}")
        print("="*40)

    async def emergency_stop(self):
        """紧急停止"""
        print("\n 紧急停止！")
        try:
            if self.robot_connected:
                await self.robot_controller.stop_robot()
                print("机器人已紧急停止")
        except Exception as e:
            print(f"紧急停止异常: {e}")

    # ==================== 获取墙壁法向量 ====================
    async def get_wall_normal(self):
        """获取墙壁法向量"""
        print("\n=== 获取墙壁法向量 ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            robot = self.robot_controller.robot

            # 简单的传感器读取函数（手动输入距离，单位：毫米）
            async def sensor_read():
                try:
                    dist = float(input("请输入当前测量距离: "))
                    return dist / 1000.0  # 转换为米
                except ValueError:
                    print("输入格式错误，请输入数字")
                    raise

            print("提示：将测量3个点的距离来计算墙壁法向量")

            # 调用robot的自动测量法向量方法

            wall_normal, angle = await robot.auto_measure_wall_normal(sensor_read)

            if wall_normal:
                print(f"墙壁法向量: {wall_normal}")
                print(f"与墙壁夹角: {angle:.2f}°")
                return True
            else:
                print("墙壁法向量计算失败")
                return False

        except Exception as e:
            print(f"获取墙壁法向量异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ==================== 对齐墙壁 ====================
    async def align_to_wall(self):
        """对齐墙壁"""
        print("\n=== 对齐墙壁 ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            robot = self.robot_controller.robot
            wall_normal_input = input("请输入墙壁法向量 (格式: nx,ny,nz): ")
            wall_normal = [float(x.strip()) for x in wall_normal_input.split(",")]
            # 调用robot的对齐墙壁方法
            success = await robot.adjust_to_wall(wall_normal)

            if success:
                print("对齐墙壁完成")
            return success

        except Exception as e:
            print(f"对齐墙壁异常: {e}")
            return False

    # ==================== 加载负载数据 ====================
    def load_payload_config(self):
        """从文件加载负载数据"""
        try:
            if os.path.exists(PAYLOAD_CONFIG_FILE):
                with open(PAYLOAD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data
            else:
                print(f"负载数据文件不存在: {PAYLOAD_CONFIG_FILE}")
                return {}
        except Exception as e:
            print(f"加载负载数据失败: {e}")
            return {}

    # ==================== 加载关节位姿数据 ====================
    def load_joint_poses(self):
        """从文件加载关节位姿数据"""
        try:
            if os.path.exists(JOINT_POSES_FILE):
                with open(JOINT_POSES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data
            else:
                # 文件不存在时创建空字典
                return {}
        except Exception as e:
            print(f"加载关节位姿数据失败: {e}")
            return {}

    # ==================== 保存关节位姿数据 ====================
    def save_joint_poses_to_file(self):
        """保存关节位姿数据到文件"""
        try:
            with open(JOINT_POSES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.joint_poses, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存关节位姿数据失败: {e}")
            return False

    # ==================== 设置负载 ====================
    async def set_robot_payload(self):
        """设置机器人负载"""
        print("\n=== 设置负载 ===")
        try:
            if not self.robot_connected:
                print("机器人未连接")
                return False

            if not self.payload_data:
                print("负载数据未加载")
                return False

            # 显示预设型号
            print("\n预设型号:")
            payload_list = list(self.payload_data.keys())
            for i, name in enumerate(payload_list, 1):
                data = self.payload_data[name]
                print(f"  {i}. {name} - 质量: {data['mass']}kg, 重心: {data['cog']}")
            print(f"  6. 手动输入")

            # 选择型号
            choice = input("\n请选择型号 (1-6): ").strip()

            if choice == "6":
                # 手动输入
                try:
                    mass = float(input("请输入负载质量（kg）: "))
                    print("请输入负载重心 (米):")
                    cog_x = float(input("  X: "))
                    cog_y = float(input("  Y: "))
                    cog_z = float(input("  Z: "))
                    mass_data = mass
                    cog_data = [cog_x, cog_y, cog_z]
                except ValueError:
                    print("输入格式错误")
                    return False
            elif choice.isdigit() and 1 <= int(choice) <= 5:
                # 选择预设型号
                idx = int(choice) - 1
                name = payload_list[idx]
                data = self.payload_data[name]
                mass_data = data['mass']
                cog_data = data['cog']
                print(f"已选择: {name}")
            else:
                print("无效选择")
                return False

            # 设置负载
            robot = self.robot_controller.robot
            success = await robot.set_payload(mass_data, cog_data)

            if success:
                print(f"负载设置成功 - 质量: {mass_data}kg, 重心: {cog_data}")
            else:
                print("负载设置失败")

            return success
        except Exception as e:
            print(f"设置负载异常: {e}")
            return False


# ==================== 主菜单 ====================
def print_menu():
    """打印完整菜单"""
    print("\n" + "="*60)
    print("        机器人调试测试系统 (直接调用版)")
    print("="*60)
    print("  1. 机器人连接           2. 视觉连接         3. 加载工具")
    print("  4. 螺钉标定             5. 角度标定         6. 深度标定")
    print("  7. 螺钉调整             8. 角度调整         9. 深度调整")
    print(" 10. 设置负载             11. 获取墙壁法向量  12. 对齐墙壁")
    print(" 13. 气泵io控制         14. 移动指令        15. 移动到保存位姿")
    print(" 16. 保存当前位姿         17. 保存关节位姿    18. 移动到关节位姿")
    print(" 19. 删除关节位姿         20. 拖动示教        21. 读取TCP位置")
    print(" 22. 读取关节位置         23. 查看系统状态    24. 紧急停止")
    print("  0. 退出")
    print("="*60)


# ==================== 主函数 ====================
async def main():
    """主函数"""
    controller = DirectRobotControl()

    while True:
        print_menu()
        choice = input("\n请选择操作 (0-24): ").strip()

        try:
            if choice == "0":
                print("\n退出测试系统")
                await controller.disconnect_robot()
                await controller.disconnect_vision()
                break

            # 连接与配置
            elif choice == "1":
                brand = input("请输入机器人品牌 (ur/duco/dazu, 默认ur): ").strip().lower()
                if not brand:
                    brand = "ur"
                await controller.connect_robot(brand)

            elif choice == "2":
                await controller.connect_vision()

            elif choice == "3":
                tool_name = input("请输入工具名称 (screw_sleeve/nail_bumping): ").strip()
                if tool_name:
                    controller.select_tool(tool_name)

            # 标定功能
            elif choice == "4":
                await controller.screw_calibration()

            elif choice == "5":
                await controller.angle_calibration()

            elif choice == "6":
                await controller.depth_calibration()

            # 调整功能
            elif choice == "7":
                await controller.screw_adjustment()

            elif choice == "8":
                await controller.angle_adjustment()

            elif choice == "9":
                await controller.depth_adjustment()

            # 操作功能
            elif choice == "10":
                await controller.set_robot_payload()

            elif choice == "11":
                await controller.get_wall_normal()

            elif choice == "12":
                await controller.align_to_wall()

            elif choice == "13":
                await controller.pneumatic_gripper_control()

            elif choice == "14":
                cmd = input("请输入移动命令 (movel/movetcp x y z rx ry rz): ").strip()
                if cmd:
                    await controller.execute_move_command(cmd)

            elif choice == "15":
                await controller.move_to_saved_pose()

            elif choice == "16":
                name = input("请输入位姿名称: ").strip()
                if name:
                    await controller.save_pose(name)

            elif choice == "17":
                name = input("请输入关节位姿名称: ").strip()
                if name:
                    await controller.save_joint_pose(name)

            elif choice == "18":
                await controller.move_to_saved_joint_pose()

            elif choice == "19":
                controller.delete_saved_joint_pose()

            elif choice == "20":
                await controller.teach_mode_control()

            # 读取功能
            elif choice == "21":
                await controller.get_current_tcp()

            elif choice == "22":
                await controller.get_current_joints()

            elif choice == "23":
                controller.get_status()

            elif choice == "24":
                await controller.emergency_stop()

            else:
                print("X 无效选择，请重新输入")

        except KeyboardInterrupt:
            print("\n! 操作被中断")
            continue
        except Exception as e:
            print(f"X 执行异常: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n! 用户中断，退出测试系统")
