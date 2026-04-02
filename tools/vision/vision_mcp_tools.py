#!/usr/bin/env python3
"""
Vision MCP Server Tools
MCP服务器工具，提供视觉检测功能
"""

import asyncio
import sys, os
import math
from typing import List, Optional, Tuple

from fastmcp import FastMCP

from .VisionApi import VisionApi

# Configuration
VISION_IP = "127.0.0.1"
VISION_PORT = 65432

# Global state
vision_api: Optional[VisionApi] = None

# Configure logger
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger

# 视觉MCP工具函数
def register_vision_tools(mcp: FastMCP):
    """注册视觉相关的MCP工具"""

#region 连接视觉
    @mcp.tool()
    async def Cam_connect_vision(ip_address: str = VISION_IP, port: int = VISION_PORT) -> str:
        """
        连接到视觉服务器，一般使用默认地址和端口
        :param ip_address: 视觉服务器IP地址
        :param port: 视觉服务器端口
        :return: 连接结果
        """
        global vision_api
        try:
            # 若已连接，先关闭旧连接
            if vision_api is not None and vision_api.is_connected:
                vision_api.close()
                logger.info("已关闭现有视觉服务器连接，准备重新连接")

            # 创建视觉API实例并连接
            vision_api = VisionApi(ip_address, port)
            success = await vision_api.connect()
            
            if success:
                return f"成功连接到视觉服务器 {ip_address}:{port}"
            else:
                vision_api = None
                return f"连接视觉服务器失败: {ip_address}:{port}"
                
        except Exception as e:
            error_msg = f"连接视觉服务器时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
#region 断连视觉
    @mcp.tool()
    def Cam_disconnect_vision() -> str:
        """断开与视觉服务器的连接"""
        global vision_api
        try:
            if vision_api is None:
                return "未连接到视觉服务器"
            
            vision_api.close()
            vision_api = None
            return "已断开与视觉服务器的连接"
        except Exception as e:
            error_msg = f"断开视觉服务器连接时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
#region 十字交叉点
    @mcp.tool()
    async def Cam_get_cross_points():
        """获取视觉系统检测到的十字交叉点"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            cross_points = await vision_api.get_cross_points_async()
            
            if not cross_points:
                return "未检测到十字交叉点"
            
            points_str = ", ".join([f"点{i+1}: ({x}, {y})" for i, (x, y) in enumerate(cross_points)])
            #return f"检测到 {len(cross_points)} 个十字交叉点: {points_str}"
            return cross_points
            
        except Exception as e:
            error_msg = f"获取十字交叉点时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg


#region 螺钉
    @mcp.tool()
    async def Cam_get_screw_points():
        """获取螺钉点信息"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            screw_points = await vision_api.get_screw_points_async()
            if not screw_points:
                return "未检测到螺钉"
            points_str = ", ".join([f"点{i+1}: ({x:.2f}, {y:.2f})" for i, (x, y) in enumerate(screw_points)])
            #return f"检测到 {len(screw_points)} 个螺钉: {points_str}"
            return screw_points
            
        except Exception as e:
            error_msg = f"获取螺钉时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

#region 法向量
    @mcp.tool()
    async def Cam_get_normal_vector():
        """获取视觉系统检测到的法向量"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            x, y, z = await vision_api.get_normal_async()
            
            #return f"法向量: ({x:.3f}, {y:.3f}, {z:.3f})"
            return (x, y, z)
            
        except Exception as e:
            error_msg = f"获取法向量时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

#region 深度
    @mcp.tool()
    async def Cam_get_depth():
        """获取视觉系统检测到的深度信息"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            depth = await vision_api.get_depth_async()
            
            #return f"深度: {depth:.2f}"
            return depth
            
        except Exception as e:
            error_msg = f"获取深度信息时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

#region 板角度
    @mcp.tool()
    async def Cam_get_board_angle():
        """获取视觉系统检测到的板角度信息"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            board_angle = await vision_api.get_board_angle_async()
            
            #return f"板角度: {board_angle:.2f}"
            return board_angle
            
        except Exception as e:
            error_msg = f"获取板角度信息时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
#region 板中心点
    @mcp.tool()
    async def Cam_get_board_center():
        """获取视觉系统检测到的板中心点坐标"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            board_center = await vision_api.get_board_position_async()
            
            if not board_center:
                return "未检测到板中心点"
            
            #return f"板中心点：({board_center[0]:.2f}, {board_center[1]:.2f})"
            return board_center
            
        except Exception as e:
            error_msg = f"获取板中心点时出错：{str(e)}"
            logger.error(error_msg)
            return error_msg
#region u型件螺套点
    @mcp.tool()
    async def Cam_get_u_points():
        """获取视觉系统检测到的十字交叉点"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            cross_points = await vision_api.get_hex_nut_points_async()
            
            if not cross_points:
                return "未检测到u型件螺套点"
            
            points_str = ", ".join([f"点{i+1}: ({x}, {y})" for i, (x, y) in enumerate(cross_points)])
            #return f"检测到 {len(cross_points)} 个u型件螺套点: {points_str}"
            return cross_points
            
        except Exception as e:
            error_msg = f"获取十字交叉点时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
#region 视觉系统状态
    @mcp.tool()
    def Cam_get_vision_status() -> str:
        """获取视觉系统的连接状态"""
        global vision_api
        if vision_api is None:
            return "视觉系统实例未创建"
        
        status = "已连接" if vision_api.is_connected else "未连接"
        ip_port = f"{vision_api.ip}:{vision_api.port}" if vision_api.is_connected else "N/A"
        
        return f"视觉系统状态: {status}"

#region 检测并计算角度
    @mcp.tool()
    async def Cam_detect_surface_angle() -> str:
        """检测表面相对于水平面的角度"""
        global vision_api
        try:
            if vision_api is None or not vision_api.is_connected:
                return "未连接到视觉服务器，请先连接"
            
            # 获取法向量
            x, y, z = await vision_api.get_normal_async()
            
            # 计算法向量与垂直向量(0,0,1)的夹角
            # 使用点积公式: cos(θ) = (a·b) / (|a||b|)
            dot_product = z  # 因为垂直向量是(0,0,1)，点积就是z分量
            angle_rad = math.acos(max(-1, min(1, dot_product)))  # 确保在有效范围内
            angle_deg = math.degrees(angle_rad)
            
            # 计算倾斜方向
            tilt_direction = "水平"
            if abs(x) > abs(y):
                tilt_direction = "X轴方向" if x > 0 else "-X轴方向"
            elif abs(y) > abs(x):
                tilt_direction = "Y轴方向" if y > 0 else "-Y轴方向"
            
            return f"表面角度: {angle_deg:.2f}°, 倾斜方向: {tilt_direction}, 法向量: ({x:.3f}, {y:.3f}, {z:.3f})"
            
        except Exception as e:
            error_msg = f"检测表面角度时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
