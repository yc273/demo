#!/usr/bin/env python3
"""
Robots MCP Server Tools
MCP服务器工具，提供机器人控制功能
"""

import asyncio
import math
import time
import sys, os
from typing import List, Optional

from fastmcp import FastMCP

# Import robot abstraction layer
from .robot_abstraction import RobotFactory, RobotController, RobotBrand

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger
# Global state
robot_controller = RobotController()


# Tool frame movement state
current_pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
rotation_matrix = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

# 机器人MCP工具函数
def register_robot_tools(mcp: FastMCP):
    """注册机器人相关的MCP工具"""

    #region 连接管理工具
    @mcp.tool()
    async def Rob_connect_robot(brand: str) -> str:
        """
        连接到指定品牌的机器人，调用后绑定调用init_algorithms方法
        :param brand: 机器人品牌，支持 "ur", "duco", "dazu" 等
        :return: 连接结果
        功能：建立与brand机器人的连接；触发词：连接brand机器人、brand机器人连接、启动brand机器人控制器；参数：无
        """
        try:
            # 如果机器人已存在，先断开连接
            if robot_controller.is_connected():
                await robot_controller.disconnect_robot()
                robot_controller.clear_robot()
            
            # 创建机器人实例
            robot_brand = RobotBrand(brand)
            robot = RobotFactory.create_robot(robot_brand)
            robot_controller.set_robot(robot)
            
            # 连接机器人
            success = await robot_controller.connect_robot()
            
            if success:
                return f"成功连接到{brand}机器人"
            else:
                robot_controller.clear_robot()
                return f"连接{brand}机器人失败"
        
        except ValueError as e:
            error_msg = f"机器人品牌错误: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"连接机器人时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool()
    async def Rob_disconnect_robot() -> str:
        """
        断开与机器人的连接
        :return: 断开连接结果
        功能：断开与机器人的连接；触发词：断开机器人连接、关闭机器人控制器、断开机器人；参数：无
        """
        try:
            success = await robot_controller.disconnect_robot()
            if success:
                robot_controller.clear_robot()
                return "已断开与机器人的连接"
            else:
                return "未找到机器人的连接"
        except Exception as e:
            error_msg = f"断开连接时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region 运动控制工具
    @mcp.tool()
    async def Rob_movej_2(tcp_pos: List[float], acceleration: float = 0.3, velocity: float = 0.3) -> str:
        
        """
        控制机器人向目标tcp位姿进行关节移动_2
        :param tcp_pos: 6元tcp位姿列表，长度为6，单位：m，rad
        :param acceleration: 加速度，默认0.1
        :param velocity: 速度，默认0.1
        :return: 运动结果
        功能：控制机器人按tcp位姿运动；触发词：关节运动_2、movej_2等；参数：需提供tcp位姿列表（[x,y,z,rx,ry,rz]），可选加速度a（默认0.1）、速度v（默认0.3）
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        if len(tcp_pos) != 6:
            return f"目标位姿列表长度必须为6，当前长度: {len(tcp_pos)}"
        
        try:
            success = await robot_controller.robot.movej_2(tcp_pos, acceleration, velocity)
            if success:
                return f"机器人关节移动_2完成，目标位姿: {[round(j, 3) for j in tcp_pos]}"
            else:
                return "机器人关节移动_2失败"
        except Exception as e:
            error_msg = f"机器人关节移动_2出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
        
    @mcp.tool()
    async def Rob_movej(joint_angles: List[float], acceleration: float = 0.5, velocity: float = 0.5) -> str:
        """
        控制机器人按关节角度进行关节移动
        :param joint_angles: 6元关节角度列表，长度为6，单位：rad
        :param acceleration: 加速度，默认0.1
        :param velocity: 速度，默认0.1
        :return: 运动结果
        功能：控制机器人按关节角度运动；触发词：关节运动、movej等；参数：需提供关节角度列表（[j1,j2,j3,j4,j5,j6]），可选加速度
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        if len(joint_angles) != 6:
            return f"关节角度列表长度必须为6，当前长度: {len(joint_angles)}"
        
        try:
            success = await robot_controller.robot.movej(joint_angles, acceleration, velocity)
            if success:
                return f"机器人关节移动完成，目标关节角度: {[round(j, 3) for j in joint_angles]}"
            else:
                return "机器人关节移动失败"
        except Exception as e:
            error_msg = f"机器人关节移动出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool()
    async def Rob_movel(tcp_pose: List[float], acceleration: float = 0.2, velocity: float = 0.1) -> str:
        """
        控制机器人按TCP位置直线移动
        :param tcp_pose: 6元TCP位置列表 [x, y, z, rx, ry, rz]，单位：m，rad
        :param acceleration: 加速度，默认0.1
        :param velocity: 速度，默认0.1
        :return: 运动结果
        功能：控制机器人按TCP位置直线运动；触发词：直线移动机器人、TCP位置移动、直线调整机械臂；参数：需提供TCP目标位置（[x,y,z,rx,ry,rz]），可选加速度a（默认0.1）、速度v（默认0.3）
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        if len(tcp_pose) != 6:
            return f"TCP位置列表长度必须为6，当前长度: {len(tcp_pose)}"
        
        try:
            success = await robot_controller.robot.movel(tcp_pose, acceleration, velocity)
            if success:
                return f"机器人TCP移动完成，目标位置: {[round(p, 3) for p in tcp_pose]}"
            else:
                return "机器人TCP移动失败"
        except Exception as e:
            error_msg = f"机器人TCP移动出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
        
    @mcp.tool()
    async def Rob_movetcp(offset: List[float], acceleration: float = 0.2, velocity: float = 0.1) -> str:
        """
        沿工具坐标系移动机器人
        :param offset： 工具坐标系偏移量，6元位姿列表[dx, dy, dz， drx, dry, drz]，单位：m，rad
        :param acceleration: 加速度，默认0.1
        :param velocity: 速度，默认0.1
        :return: 移动结果
        功能：获取机器人当前TCP（工具末端）位置；触发词：获取当前TCP位置、查询工具末端位置、机械臂末端位置；参数：无，返回TCP位姿（[x,y,z,rx,ry,rz]）
        """
        if not robot_controller.is_connected():
            return "机器人未连接，请先连接"
 
        try:
            radius: float = 0
            block: bool = True
            success = await robot_controller.robot.movetcp(offset, acceleration, velocity)
            if success:
                return f"机器人移动完成"
            else:
                return "机器人移动失败"
        except Exception as e:
            logger.error(f"机器人移动失败：{e}")
            return f"机器人移动失败：{e}"
    #endregion
    @mcp.tool()
    async def movetcp_position_to(offset: List[float], position: List[float]=[-0.869371,-0.034908999999999996,0.388382,-2.2421023169894756,-1.5676023742637468,2.6711566070072417],  acceleration: float = 1.0, velocity: float = 0.5) -> bool:
        """
        沿工具坐标系移动机器人到指定位置
        :param position: 目标位置，6元位姿列表[x, y, z， rx, ry, rz]，单位：m，rad
        :param offset： 工具坐标系偏移量，6元位姿列表[dx, dy, dz， drx, dry, drz]，单位：m，rad
        :param acceleration: 加速度，默认1.0
        :param velocity: 速度，默认0.5
        :return: 移动结果
        功能：沿工具坐标系移动机器人到指定位置
        """
        if not robot_controller.is_connected():
            return "机器人未连接，请先连接"
 
        try:
            radius: float = 0
            block: bool = True
            success = await robot_controller.robot.movetcp_position_to(position, offset, acceleration, velocity)
            if success:
                return f"机器人移动完成"
            else:
                return "机器人移动失败"
        except Exception as e:
            logger.error(f"机器人移动失败：{e}")
            return f"机器人移动失败：{e}"
    #region 位置信息工具
    @mcp.tool()
    async def Rob_get_current_tcp_pos():
        """
        获取当前机器人的TCP位置，单位：m，rad
        :return: 当前TCP位置的字符串表示
        功能：获取机器人当前TCP（工具末端）位置；触发词：获取当前TCP位置、查询工具末端位置、机械臂末端位置；参数：无，返回TCP位姿（[x,y,z,rx,ry,rz]）
        """
        if not robot_controller.is_connected():
            return "机器人未连接"

        try:
            tcp_pose = await robot_controller.robot.get_current_tcp_pos()
            if tcp_pose:
                #return f"机器人当前TCP位置: {tcp_pose}"
                return tcp_pose
            else:
                return "机器人无法获取TCP位置"
        except Exception as e:
            error_msg = f"机器人获取TCP位置信息出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool()
    async def Rob_get_current_joint_pos():#TODO
        """
        获取当前机器人的关节角度，单位rad
        :return: 当前关节角度的字符串表示
        功能：获取机器人当前各关节角度；触发词：获取关节角度、查询关节位置、关节状态；参数：无，返回关节角度（[j1,j2,j3,j4,j5,j6]）
        """
        if not robot_controller.is_connected():
            return "机器人未连接"

        try:
            joint_angles = await robot_controller.robot.get_current_joint_pos()
            if joint_angles:
                #return f"机器人当前关节角度: {joint_angles}"
                return joint_angles
            else:
                return "机器人无法获取关节角度"
        except Exception as e:
            error_msg = f"机器人获取关节角度信息出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region TCP设置工具
    @mcp.tool()
    async def Rob_set_tcp(tcp: List[float]) -> str:
        """
        临时设置TCP偏移信息，单位：m，rad
        :param tcp: TCP位置 [x, y, z, rx, ry, rz]
        :return: 设置结果
        功能：设置TCP坐标系原点位置；触发词：设置工具坐标、定义工具末端、TCP设置；参数：需提供TCP位置（[x,y,z,rx,ry,rz]）
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        if len(tcp) != 6:
            return f"TCP位置列表长度必须为6，当前长度: {len(tcp)}"
        
        try:
            success = await robot_controller.robot.set_tool(tcp)
            if success:
                return f"机器人TCP坐标设置为: {tcp}"
            else:
                return "机器人设置TCP坐标失败"
        except Exception as e:
            error_msg = f"机器人设置TCP坐标失败: {str(e)}"
            logger.error(error_msg)
            return error_msg
        
    @mcp.tool()
    async def Rob_choose_tcp_offset(tcp_name: str) -> str:
        """
        选择设置已保存的机器人tcp偏移信息
        :param tcp_name: 工具名称
        :return: 执行结果
        功能：选择并应用已保存的机器人工具坐标系；触发词：选择tcp'xx'、切换tcp'xx'、应用tcp'xx'、设置TCP偏置方案'xx'，不同于set_tcp
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        try:
            # 调用机器人的choose_tcp方法
            success = await robot_controller.robot.choose_tcp(tcp_name)
            if success:
                return f"工具 '{tcp_name}' 切换成功"
            else:
                return f"工具 '{tcp_name}' 切换失败"
        except Exception as e:
            error_msg = f"工具切换时发生错误: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region 负载设置工具
    @mcp.tool()
    async def Rob_set_payload(mass: float, cog: List[float]) -> str:
        """
        临时设置机器人的负载和重心
        :param mass: 负载质量(kg)
        :param cog: 重心坐标列表 [x, y, z]，单位：m
        :return: 设置结果
        功能：设置机器人负载质量和重心；触发词：设置负载、负载参数配置、重心设置；参数：需提供质量（kg）和重心坐标（[x,y,z]）
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        if len(cog) != 3:
            return f"重心坐标列表长度必须为3，当前长度: {len(cog)}"
        
        try:
            success = await robot_controller.robot.set_payload(mass,cog)
            if success:
                return f"机器人负载设置为: 质量={mass}kg, 重心={cog}"
            else:
                return "机器人设置负载失败"
        except Exception as e:
            error_msg = f"机器人设置负载失败: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region 紧急控制工具
    @mcp.tool()
    async def Rob_stop_robot() -> str:
        """
        紧急停止机器人
        :return: 停止命令执行结果
        功能：紧急停止机器人所有运动；触发词：停止机器人、紧急停止、终止机械臂运动；参数：无
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        try:
            success = await robot_controller.robot.stop()
            if success:
                return "机器人已停止"
            else:
                return "机器人停止命令执行失败"
        except Exception as e:
            error_msg = f"机器人紧急停止失败: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region 状态查询工具
    @mcp.tool()
    async def Rob_get_robot_status() -> str:
        """获取机器人的连接状态"""
        status = robot_controller.get_robot_status()
        
        if status.get('status') == 'no_robot':
            return "当前没有连接的机器人"
        
        tcp_pos = await robot_controller.robot.get_current_tcp_pos()
        joint_pos = await robot_controller.robot.get_current_joint_pos()
        
        status_lines = [
            f"  品牌: {status['brand']}",
            f"  连接状态: {'已连接' if status['connected'] else '未连接'}",
            f"  joint_pos: {joint_pos}",
            f"  tcp_pos: {tcp_pos}"
        ]
        return "\n".join(status_lines)
    #endregion

    #region 示教模式工具
    @mcp.tool()
    async def Rob_enter_teach_mode() -> str:
        """
        进入机器人示教模式，同一时间不多次调用
        :return: 进入示教模式结果
        功能：使机器人进入示教模式，允许手动拖动；触发词：进入示教模式、开启示教、示教模式启动；参数：无
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        try:
            success = await robot_controller.robot.enter_teach_mode()
            if success:
                return "机器人成功进入示教模式"
            else:
                return "进入示教模式失败"
        except Exception as e:
            error_msg = f"进入示教模式时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool()
    async def Rob_exit_teach_mode() -> str:
        """
        退出机器人示教模式
        :return: 退出示教模式结果
        功能：使机器人退出示教模式，恢复正常控制；触发词：退出示教模式、关闭示教、结束示教模式；参数：无
        """
        if not robot_controller.is_connected():
            return "机器人未连接"
        
        try:
            success = await robot_controller.robot.exit_teach_mode()
            if success:
                return "机器人成功退出示教模式"
            else:
                return "退出示教模式失败"
        except Exception as e:
            error_msg = f"退出示教模式时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion