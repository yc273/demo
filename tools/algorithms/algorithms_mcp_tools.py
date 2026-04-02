#!/usr/bin/env python3
"""
Algorithms MCP Server Tools
MCP服务器工具，提供数据处理与存储功能
"""

import asyncio
import math
import re

from sympy import im
import sys, os
from typing import List, Optional, Tuple, Union, Dict
from fastmcp import FastMCP

from .algorithms import AlgorithmsApi

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger

# Global state
algorithms_api: Optional[AlgorithmsApi] = None




# 算法MCP工具函数
def register_algorithms_tools(mcp: FastMCP):
    """注册算法相关的MCP工具"""


#region 初始化
    @mcp.tool()
    async def Alg_init_algorithms(brand: str) -> str:
        """
        初始化算法工具
        该工具在连接机器人后立即自动调用
        
        Returns:
            str: 初始化结果描述信息
                - "算法初始化成功" 表示初始化成功
                - "算法初始化失败" 表示初始化失败
                - 包含错误信息的字符串表示发生异常
        """
        try:
            global algorithms_api
            algorithms_api = AlgorithmsApi(brand)
            return "算法初始化成功"
        except Exception as e:
            logger.error(f"算法初始化失败：{str(e)} | 函数参数: {locals()}")
            return "算法初始化失败"

#region 工具选择
    @mcp.tool()
    async def Alg_select_tool(tool_name: str) -> str:
        """选择并加载指定工具的标定数据
        :param tool_name: 已实现的工具名称匹配
        'screw_sleeve'-关键词：拧螺套、上螺套等
        'nail_bumping'-关键词：碰钉等
        :return: 执行结果
        """
        global algorithms_api
        try:
            success = algorithms_api.select_tool(tool_name)
            if success:
                return "选择工具成功"
            else:
                return "选择工具失败"
        except Exception as e:
            logger.error(f"选择工具工具出错：{str(e)} | 参数: {locals()}")
            return f"选择工具失败: {str(e)}"
#region 十字交叉点
    @mcp.tool()
    async def Alg_position_calibration(
        first_image_point: List[float],
        second_image_point: List[float],
        first_robot_point: List[float],
        second_robot_point: List[float],
        third_robot_point: List[float]
    ) -> str:
        """
        位置标定算法工具
        
        通过两个图像点和对应的机器人位置进行位置标定，计算并保存图像坐标到机器人坐标的转换矩阵。
        
        Args:
            first_image_point (List[float]): 第一个标定点的图像坐标 [x, y]
            second_image_point (List[float]): 第二个标定点的图像坐标 [x, y]
            first_robot_point (List[float]): 第一个标定点对应的机器人位置 [x, y, z, rx, ry, rz]
            second_robot_point (List[float]): 第二个标定点对应的机器人位置 [x, y, z, rx, ry, rz]
            third_robot_point (List[float]): 第三个标定点对应的机器人位置 [x, y, z, rx, ry, rz]
            
        Returns:
            str: 标定结果描述信息
                - "位置标定成功" 表示标定成功
                - "位置标定失败" 表示标定失败
                - 包含错误信息的字符串表示发生异常
        """
        global algorithms_api
        try:
            success = algorithms_api.position_calibration(
                first_image_point, 
                second_image_point, 
                first_robot_point, 
                second_robot_point,
                third_robot_point
            )
            if success:
                return "位置标定成功"
            else:
                return "位置标定失败"
        except Exception as e:
            logger.error(f"位置标定算法工具出错：{str(e)} | 参数: {locals()}")
            return f"位置标定算法工具出错：{str(e)}" 

    @mcp.tool()
    async def Alg_position_adjust(
        pos: List[float]
    ):#TODO
        """
        位置调整工具
        
        根据视觉识别到的十字交叉点位置，计算机器人需要移动的偏移量以实现精确对齐。
        
        Args:
            pos (List[float]): 十字交叉点的图像坐标 [x, y]   
        Returns:
            str: 机器人末端movetcp需要的偏移量 [x, y, z, rx, ry, rz] 或错误信息
                - 包含偏移量的列表表示计算成功
                - "位置校准算法异常" 表示算法执行异常
        """
    # 参数验证
        validate_point(pos, "pos", 2)

        try:
            global algorithms_api
            align_offset = algorithms_api.position_adjust(pos)
            if align_offset:
                return align_offset
            else:
                raise Exception(f"align_offset返回为空")
        except Exception as e:
            logger.error(f"位置调整工具出错：{str(e)} | 参数: {locals()}")
            return f"位置调整工具出错：{str(e)}"
        
    @mcp.tool()
    async def Alg_position_adjust_estimate(pos: List[float]) -> str:
        """
        评估十字交叉点坐标对齐状态
        
        Args:
            pos (List[float]): 检测到的测量十字点像素坐标 [x, y]
            
        Returns:
            str: 检查结果
                - "是": 十字交叉点已在允许误差范围内，可以进行后续操作
                - "否": 十字交叉点超出允许误差范围，需要继续位置调整
                - 包含错误信息的字符串: 执行过程中发生异常
        """
        # 参数验证
        validate_point(pos, "pos", 2)
        
        try:
            global algorithms_api
            is_success = algorithms_api.is_position_adjusted_perfectly(pos)
            if is_success:
                return "是"
            else:
                return "否"
        except Exception as e:
            logger.error(f"Alg_position_adjust_estimate出错：{str(e)} | 参数: {locals()}")
            return f"Alg_position_adjust_estimate出错：{str(e)}"

#region 螺钉
    @mcp.tool()
    async def Alg_screw_calibration(
        first_image_point: List[float],
        second_image_point: List[float],
        first_robot_point: List[float],
        second_robot_point: List[float],
        third_robot_point: List[float]
    ) -> str:
        """
        螺钉标定算法工具
        
        通过两个图像点和对应的机器人位置进行位置标定，计算并保存图像坐标到机器人坐标的转换矩阵。
        
        Args:
            first_image_point (List[float]): 第一个标定点的图像坐标 [x, y]
            second_image_point (List[float]): 第二个标定点的图像坐标 [x, y]
            first_robot_point (List[float]): 第一个标定点对应的机器人位置 [x, y, z, rx, ry, rz]
            second_robot_point (List[float]): 第二个标定点对应的机器人位置 [x, y, z, rx, ry, rz]
            third_robot_point (List[float]): 第三个标定点对应的机器人位置 [x, y, z, rx, ry, rz]
        Returns:
            str: 标定结果描述信息
                - "螺钉标定成功" 表示标定成功
                - "螺钉标定失败" 表示标定失败
                - 包含错误信息的字符串表示发生异常
        """
        global algorithms_api
        try:
            success = algorithms_api.screw_calibration(
                first_image_point, 
                second_image_point, 
                first_robot_point, 
                second_robot_point,
                third_robot_point
            )
            if success:
                return "螺钉标定成功"
            else:
                return "螺钉标定失败"
        except Exception as e:
            logger.error(f"螺钉标定算法工具出错：{str(e)} | 参数: {locals()}")
            return f"螺钉标定算法工具出错：{str(e)}" 


    @mcp.tool()
    async def Alg_screw_adjust(pos: List[float]):#TODO
        """
        螺钉调整工具
        
        根据视觉识别到的螺钉位置，计算机器人需要移动的偏移量以实现精确对齐。
    
        Args:
            pos (List[float]): 螺钉的像素坐标 [x, y]   
        Returns:
            str: 机器人末端movetcp需要的偏移量 [x, y, z, rx, ry, rz] 或错误信息
                - 包含偏移量的列表表示计算成功
                - 螺钉调整算法异常
        """
    # 参数验证
        validate_point(pos, "pos", 2)
        try:
            global algorithms_api
            align_offset = algorithms_api.screw_adjust(pos)
            if align_offset:
                #return str(align_offset)
                return align_offset#TODO
            else:
                raise Exception(f"align_offset返回为空")
        except Exception as e:
            logger.error(f"螺钉调整工具出错：{str(e)} | 参数: {locals()}")
            return f"螺钉调整工具出错：{str(e)}"


    @mcp.tool()
    async def Alg_screw_adjust_estimate(pos: List[float]) -> str:
        """
        评估螺钉是否正确对齐  
        Args:
            pos (List[float]): 检测到的测量螺钉像素坐标 [x, y]
            
        Returns:
            str: 检查结果
                - "是": 螺钉已在允许误差范围内，可以进行后续操作
                - "否": 螺钉超出允许误差范围，需要继续螺钉调整
                - 包含错误信息的字符串
        """
        # 参数验证
        validate_point(pos, "pos", 2)
        try:
            global algorithms_api
            is_success = algorithms_api.is_screw_adjusted_perfectly(pos)
            if is_success:
                return "是"
            else:
                return "否"
        except Exception as e:
            logger.error(f"Alg_screw_adjust_estimate出错：{str(e)} | 参数: {locals()}")
            return f"Alg_screw_adjust_estimate出错：{str(e)}"


#region 角度

    @mcp.tool()
    async def Alg_angle_calibration(normal: Tuple[float, float, float]) -> str:
        """
        角度标定工具
        
        使用视觉工具测量到的法向量进行角度标定，保存标定数据用于后续的角度调整。
        
        Args:
            normal (Tuple[float, float, float]): 测量得到的表面法向量 (nx, ny, nz)
            
        Returns:
            str: 标定结果描述信息
                - "角度标定成功，已保存数据" 表示标定成功
                - "角度标定失败" 表示标定失败
                - 包含错误信息的字符串表示发生异常
        """
        # 参数验证
        validate_point(list(normal), "normal", 3)

        try:
            global algorithms_api
            success = algorithms_api.angle_calibration(normal)
            if success:
                return "角度标定成功，已保存数据"
            else:
                return "角度标定失败"
        except Exception as e:
            logger.error(f"角度标定工具出错：{str(e)} | 参数: {locals()}")
            return f"角度标定工具出错：{str(e)}"

    @mcp.tool()
    async def Alg_angle_adjust(
        measured_z: List[float]
    ) -> Union[List[float], str]:
        """
        角度调整工具
        
        根据视觉工具测量到的Z轴向量与标定的Z轴向量差异，计算机器人需要调整的角度。
        
        Args:
            measured_z (List[float]): 当前测量得到的Z轴向量 [x, y, z]
                
        Returns:
            Union[List[float], str]: 调整结果
                - List[float]: 调整后的机器人角度偏移量 [x, y, z, rx, ry, rz]
                - str: 错误信息或状态描述
        """
        # 参数验证
        validate_point(measured_z, "measured_z", 3)

        try:
            global algorithms_api
            adjust_result = algorithms_api.angle_adjust(measured_z)
            if adjust_result is not None:
                return adjust_result
            else:
                raise Exception(f"adjust_result返回值为空")
        except Exception as e:
            logger.error(f"角度调整工具出错：{str(e)} | 参数: {locals()}")
            return f"角度调整工具出错：{str(e)}"

    @mcp.tool()
    async def Alg_angle_adjust_estimate(measured_z: List[float]) -> str:
        """
        判断当前测量的Z轴是否已经调整到指定状态
        
        检查视觉识别到的Z轴向量与标定的Z轴向量差异是否在允许的误差范围内
        
        Args:
            measured_z (List[float]): 当前测量得到的Z轴向量 [x, y, z]
            
        Returns:
            str: 检查结果
                - "是": Z轴向量已在允许误差范围内，可以执行后续操作
                - "否": Z轴向量超出允许误差范围，需要继续角度调整
                - 包含错误信息的字符串
        """
        # 参数验证
        validate_point(measured_z, "measured_z", 3)
        
        try:
            global algorithms_api
            is_success = algorithms_api.is_angle_adjusted_perfectly(measured_z)
            if is_success:
                return "是"
            else:
                return "否"
        except Exception as e:
            logger.error(f"Alg_angle_adjust_estimate出错：{str(e)} | 参数: {locals()}")
            return f"Alg_angle_adjust_estimate出错：{str(e)}"

#region深度
    @mcp.tool()
    async def Alg_depth_calibration(current_depth: float) -> str:
        """
        深度标定工具
        
        使用视觉工具测量到的当前深度值进行深度标定，保存标定数据用于后续的深度调整。
        
        Args:
            current_depth (float): 当前测量的深度值（单位：毫米）
            
        Returns:
            str: 标定结果描述信息
                - "深度标定成功，已保存数据" 表示标定成功
                - "深度标定失败" 表示标定失败
                - 包含错误信息的字符串表示发生异常
        """
        # 参数验证
        validate_positive_number(current_depth, "current_depth")

        try:
            global algorithms_api
            success = algorithms_api.depth_calibrate(current_depth)
            if success:
                return "深度标定成功，已保存数据"
            else:
                return "深度标定失败"
        except Exception as e:
            logger.error(f"深度标定工具出错：{str(e)} | 参数: {locals()}")
            return f"深度标定工具出错：{str(e)}"


    @mcp.tool()
    async def Alg_depth_adjust(current_depth: float) -> Union[List[float], str]:
        """
        深度调整工具
        根据视觉工具测量到的当前深度与标定深度的差异，计算机器人在Z轴方向需要调整的偏移量。
        
        Args:
            current_depth (float): 当前测量的深度值（单位：毫米）
                
        Returns:
            Union[List[float], str]: 调整结果
                - List[float]: 深度调整量 [x, y, z, rx, ry, rz]，其中只有z轴有值
                - str: 错误信息或状态描述
        """
        # 参数验证
        validate_positive_number(current_depth, "current_depth")

        try:
            global algorithms_api
            adjust_result = algorithms_api.depth_adjust(current_depth)
            if adjust_result is not None:
                return adjust_result
            else:
                raise Exception(f"adjust_result返回为空")
        except Exception as e:
            logger.error(f"Alg_depth_adjust出错：{str(e)} | 参数: {locals()}")
            return f"Alg_depth_adjust出错：{str(e)}"
    

    @mcp.tool()
    async def Alg_depth_adjust_estimate(current_depth: float) -> str:
        """
        评估当前深度是否已经调整到指定状态 
        Args:
            current_depth (float): 当前测量的深度值（单位：毫米）
        Returns:
            str: 检查结果
                - "是": 深度值已在允许误差范围内，可以进行后续操作
                - "否": 深度值超出允许误差范围，需要继续深度调整
                - 包含错误信息的字符串
        """
        # 参数验证
        validate_positive_number(current_depth, "current_depth")
        
        try:
            global algorithms_api
            is_success = algorithms_api.is_depth_adjusted_perfectly(current_depth)
            if is_success:
                return "是"
            else:
                return "否"
        except Exception as e:
            logger.error(f"Alg_depth_adjust_estimate异常: {str(e)} | 参数: {locals()}")
            return f"Alg_depth_adjust_estimate异常: {str(e)}"


#region 获取偏移信息
    @mcp.tool()
    async def Alg_get_offset_info() -> Dict[str, List[float]]:
        """
        获取标定时需要的偏移量信息工具
        包括offset1，offset2，offset3和offset4 共四个偏移量列表
        
        Returns:
            Dict[str, List[float]]: 包含两个偏移量列表的字典
                - "offset1": 第一个偏移量列表
                - "offset2": 第二个偏移量列表
                - "offset3": 第三个偏移量列表
                - "offset4": 第四个偏移量列表
        """
        global algorithms_api
        try:
            # 获取偏移量信息
            offset_info = algorithms_api.get_offset_info()
            return offset_info
        except Exception as e:
            logger.error(f"获取工具偏移信息工具出错：{str(e)}")
            return {"error": f"获取工具偏移信息工具出错：{str(e)}"}


#region 获取初始位置
    @mcp.tool()
    async def Alg_get_home_position() -> Union[List[float],str]:
        """
        获取初始位置工具
        
        获取已保存的机器人初始位置
        返回的位姿包含完整的6个自由度坐标：[x, y, z, rx, ry, rz]

        Returns:
            Union[List[float], str]: 执行结果
                - List[float]: 机器人初始位置坐标 [x, y, z, rx, ry, rz]（单位：米和弧度）
                - str: 错误信息字符串
        """
        global algorithms_api
        try:
            # 获取工具初始位置
            home_position = algorithms_api.get_home_position()
            if home_position is None:
                raise {f"未定义工具初始位置"}
            else:
                return home_position
        except Exception as e:
            error_msg = f"获取工具初始位置工具出错：{str(e)}"
            logger.error(error_msg)
            return error_msg

#region 记录点位

    @mcp.tool()
    async def Alg_record_point(point_name: str, robot_position: List[float]) -> str:
        """记录点坐标到文件
        :param point_name: 点的名字
        :param robot_position: 机器人位置 [x, y, z, rx, ry, rz]
        :return: 是否成功记录或异常信息
        """
        global algorithms_api
        try:
            is_success = algorithms_api.record_point(point_name, robot_position)
            if is_success:
                return "成功记录点位"
            else:
                return "记录点位失败"
        except Exception as e:
            return f"记录点位异常: {str(e)}"
    

    @mcp.tool()
    async def Alg_record_joint_point(joint_point_name: str, robot_position: List[float]) -> str:
        """记录点坐标到文件
        :param joint_point_name: 点的名字
        :param robot_position: 机器人位置 [x, y, z, rx, ry, rz]
        :return: 是否成功记录或异常信息
        """
        global algorithms_api
        try:
            is_success = algorithms_api.record_joint_point(joint_point_name, robot_position)
            if is_success:
                return "成功记录点位"
            else:
                return "记录点位失败"
        except Exception as e:
            return f"记录点位异常: {str(e)}"
        

    @mcp.tool()
    async def Alg_get_recorded_joint_point(joint_point_name: str = None) -> Union[Dict[str, List[float]], List[float], str]:
        """获取指定名字的记录点坐标，若没有指定名字，返回所有点坐标列表
        :param joint_point_name: 点的名字，如果为None则返回所有点坐标
        :return: 点坐标数据或错误信息
        """
        global algorithms_api
        try:
            if joint_point_name is None:
                joint_points = algorithms_api.list_recorded_joint_points()
                return joint_points if joint_points else "暂无记录点位"
            else:
                joint_point = algorithms_api.get_recorded_joint_point(joint_point_name)
                if joint_point is not None:
                    return joint_point
                else:
                    return f"点位-{joint_point_name} 不存在"
        except Exception as e:
            return f"获取记录点位异常: {str(e)}"

    @mcp.tool()
    async def Alg_delete_point(point_name: str) -> str:
        """从文件中删除指定点坐标
        :param point_name: 要删除的点名字
        :return: 是否成功删除
        """
        global algorithms_api
        try:
            is_success = algorithms_api.delete_point(point_name)
            if is_success:
                return "成功删除点位"
            else:
                return "删除点位失败"
                
        except Exception as e:
            return f"删除点位异常: {str(e)}"


    @mcp.tool()
    async def Alg_get_recorded_point(point_name: str = None) -> Union[Dict[str, List[float]], List[float], str]:
        """获取指定名字的记录点坐标，若没有指定名字，返回所有点坐标列表
        :param point_name: 点的名字，如果为None则返回所有点坐标
        :return: 点坐标数据或错误信息
        """
        global algorithms_api
        try:
            if point_name is None:
                points = algorithms_api.list_recorded_points()
                return points if points else "暂无记录点位"
            else:
                point = algorithms_api.get_recorded_point(point_name)
                if point is not None:
                    return point
                else:
                    return f"点位-{point_name} 不存在"
        except Exception as e:
            return f"获取记录点位异常: {str(e)}"

#endregion

#region 验证合法性

    def validate_point(point: List[float], name: str, dimensions: int):
        """验证点坐标的合法性"""
        if not isinstance(point, list):
            raise ValueError(f"{name} 必须是列表类型")
        if len(point) != dimensions:
            raise ValueError(f"{name} 必须包含 {dimensions} 个坐标值")
        if not all(isinstance(p, (int, float)) for p in point):
            raise ValueError(f"{name} 中的所有元素必须是数值类型")

    def validate_positive_number(value, name: str):
        """验证正数类型的参数"""
        if not isinstance(value, (int, float)):
            raise ValueError(f"{name} 必须是数值类型")
        if value <= 0:
            raise ValueError(f"{name} 必须是正值")

    def validate_non_negative_integer(value, name: str):
        """验证非负整数类型的参数"""
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} 必须是非负整数")
        
        
