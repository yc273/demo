#!/usr/bin/env python3
"""
Robots MCP Client
MCP客户端，用于与MCP服务器和LLM交互
"""
import asyncio
import json
import logging
import sys
from time import sleep
import time
import traceback
import re
from contextlib import AsyncExitStack
from tracemalloc import start
from typing import List, Dict, Optional
import os
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fuzzywuzzy import fuzz
from regex import F, T
from sympy import false, true

root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  
sys.path.append(root_path)
from logs.logger_utils import logger, logger2

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取 prompt_flows 目录
ProcessMatching = os.path.abspath(os.path.join(current_dir, ".."))
# 添加到 Python 搜索路径
if ProcessMatching not in sys.path:
    sys.path.insert(0, ProcessMatching)
# 导入流程匹配类
from ProcessMatching.ProcessMatching import ProcessMatching

class MCPClient:
    def __init__(self):
        """Initialize MCP client with LLM connection"""
        self.exit_stack = AsyncExitStack()
        # 获取当前文件的绝对路径
        current_file_path = os.path.abspath(__file__)
        # 获取当前文件所在的目录
        current_dir = os.path.dirname(current_file_path)
        # 构建配置文件的绝对路径
        self.config_path = os.path.join(current_dir, "..", "config", "calibration", "LLM.json")  

        # MCP会话
        self.session: Optional[ClientSession] = None

        # 工具缓存列表
        self.all_available_tools: List[Dict] = []   # 所有MCP工具
        self.filtered_available_tools: List[Dict] = []  # 过滤后的工具（规划指定+必要工具）

        # 配置日志
        self.logger = logger
        self.logger2 = logger2
        # 流程文件相关配置
        self.flow_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompt_flows")
        self.process_matcher = ProcessMatching(self.flow_dir)
        

    async def connect_to_mcp_server_io(self, server_script_path: str):
        """通过标准I/O连接到MCP服务器"""
        self.logger.info(f"尝试通过标准I/O连接到MCP服务器: {server_script_path}")
        server_params = StdioServerParameters(
            command="python",
            args=[server_script_path],
            env=None
        )
        # 建立标准I/O传输通道
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        # 初始化MCP会话
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()

        # 列出可用工具
        response = await self.session.list_tools()
        tools = response.tools
        tool_names = [tool.name for tool in tools]
        print("\n已连接到服务器，支持以下工具:", tool_names)

    async def connect_to_mcp_server_http(self, mcp_server_url: str):
        """通过HTTP连接到MCP服务器"""
        # 自动补全协议前缀
        if not mcp_server_url.startswith(('http://', 'https://')):
            mcp_server_url = f"http://{mcp_server_url}"
        
        transport = StreamableHttpTransport(url=mcp_server_url)
        async with Client(transport) as client:
            print(f"成功连接到MCP服务: {mcp_server_url}")
            await client.ping()  # 测试连接
            print("服务心跳检测成功")
            # 列出可用工具
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]
            print(f"可用工具列表: {', '.join(tool_names)}")

    async def cleanup(self):
        """清理资源"""
        print("正在清理资源...")
        try:
            if self.exit_stack:
                await self.exit_stack.aclose()
        except Exception as e:
            print(f"关闭退出栈时出错：{e}")
        finally:
            self.session = None
            self.exit_stack = None
        print("资源清理完成")


#region 新加



    # 标记变量
    global robot_connected, vision_connected, io_connected, is_tool_set
    robot_connected = False
    vision_connected = False
    io_connected = False
    is_tool_set = False


    #region 机器人连接
    async def test_robot_connection(self, brand: str = "dazu"):
        """
        测试机器人连接功能
        传入品牌，连接机器人后初始化算法
        """
        print(f"=== 测试 {brand} 机器人连接 ===")
        global robot_connected
        try:
            
            # 连接指定品牌的机器人
            result = await self.session.call_tool("Rob_connect_robot", {"brand": brand})
            result_text = result.content[0].text if result.content else "连接失败"
            print(f"连接 {brand} 机器人结果: {result_text}")
            
            if "成功" in result_text:
                # 连接成功后初始化算法
                alg_result = await self.session.call_tool("Alg_init_algorithms", {"brand": brand})
                alg_result_text = alg_result.content[0].text if alg_result.content else "初始化失败"
                print(f"初始化算法结果: {alg_result_text}")
                robot_connected = True
                return True
            else:
                print(f"机器人连接失败，跳过算法初始化")
                return False
                
        except Exception as e:
            print(f"测试机器人连接时出错: {e}")
            return False

    #region 视觉连接
    async def test_vision_connection(self):
        """
        测试视觉连接功能
        """
        print("=== 测试视觉连接 ===")
        global vision_connected
        # 连接视觉服务器
        try:
            result = await self.session.call_tool("Cam_connect_vision", {"ip_address": "127.0.0.1", "port": 65432})
            result_text = result.content[0].text if result.content else "连接失败"
            print(f"连接视觉服务器结果: {result_text}")
            vision_connected = True
            return True

        except Exception as e:
            print(f"测试视觉连接时出错: {e}")
            return False

    #region 加载工具
    async def test_select_tools(self, tool_name: str = "screw_sleeve"):
        """
        测试加载工具标定数据功能
        """
        print("=== 测试加载工具标定数据功能 ===")
        global is_tool_set
        try:
            result = await self.session.call_tool("Alg_select_tool", {"tool_name": tool_name})
            result_text = result.content[0].text if result.content else "加载失败"
            print(f"加载工具结果: {result_text}")
            is_tool_set = True
            return True

        except Exception as e:
            print(f"测试加载工具时出错: {e}")
            return False

    #region 螺钉标定
    async def test_screw_calibration(self):
        """
        测试螺钉标定流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试螺钉标定流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False

            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False
            
            # 获取偏移量
            print("获取偏移量信息...")
            offset_result = await self.session.call_tool("Alg_get_offset_info", {})
            offset_result_text = offset_result.content[0].text if offset_result.content else "{}"
            print(f"获取偏移量结果: {offset_result_text}")
            
            # 解析偏移量结果
            import json
            try:
                offset_result_dict = json.loads(offset_result_text) if offset_result_text else {}
            except json.JSONDecodeError:
                print("解析偏移量失败，无法继续标定流程")
                return False
                
            # 提取偏移量
            offset1 = offset_result_dict.get("offset1", [0, 0, 0, 0, 0, 0])
            offset2 = offset_result_dict.get("offset2", [0, 0, 0, 0, 0, 0])
            offset3 = offset_result_dict.get("offset3", [0, 0, 0, 0, 0, 0])
            
            # 记录标定点数据
            first_image_point = None
            first_robot_point = None
            second_image_point = None
            second_robot_point = None
            third_robot_point = None
            
            # 移动到标定位置1
            print(f"移动到标定位置1，偏移量: {offset1}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset1})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置1结果: {result_text}")
            await asyncio.sleep(5)

            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            first_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            first_robot_point_text = first_robot_point_result.content[0].text if first_robot_point_result.content else "获取失败"
            print(f"当前机器人TCP位置结果: {first_robot_point_text}")
            
            # 解析机器人位置
            try:
                first_robot_point = json.loads(first_robot_point_text)
                print(f"第一标定点机器人位置: {first_robot_point}")
            except json.JSONDecodeError:
                first_robot_point = first_robot_point_text
                print(f"第一标定点机器人位置: {first_robot_point}")
            await asyncio.sleep(1)
            # 获取螺钉像素坐标
            print("获取螺钉像素坐标...")
            screw_points_result1 = await self.session.call_tool("Cam_get_screw_points", {})
            screw_points_result1_text = screw_points_result1.content[0].text if screw_points_result1.content else "获取失败"
            print(f"获取螺钉像素坐标结果: {screw_points_result1_text}")
            await asyncio.sleep(1)

            # 解析螺钉坐标
            try:
                first_image_point = json.loads(screw_points_result1_text)
                # 如果是列表且有元素，取第一个点
                if isinstance(first_image_point, list) and len(first_image_point) > 0:
                    if isinstance(first_image_point[0], list):
                        first_image_point = first_image_point[0]
                    print(f"第一标定点图像坐标: {first_image_point}")
            except json.JSONDecodeError:
                first_image_point = screw_points_result1_text
                print(f"第一标定点图像坐标: {first_image_point}")
            
            # 移动到标定位置2
            print(f"移动到标定位置2，偏移量: {offset2}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset2})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置2结果: {result_text}")
            
            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            second_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            second_robot_point_text = second_robot_point_result.content[0].text if second_robot_point_result.content else "获取失败"
            print(f"当前机器人TCP位置结果: {second_robot_point_text}")
            
            # 解析机器人位置
            try:
                second_robot_point = json.loads(second_robot_point_text)
                print(f"第二标定点机器人位置: {second_robot_point}")
            except json.JSONDecodeError:
                second_robot_point = second_robot_point_text
                print(f"第二标定点机器人位置: {second_robot_point}")
            await asyncio.sleep(5)
            # 获取螺钉像素坐标
            print("获取螺钉像素坐标...")
            screw_points_result2 = await self.session.call_tool("Cam_get_screw_points", {})
            screw_points_result2_text = screw_points_result2.content[0].text if screw_points_result2.content else "获取失败"
            print(f"获取螺钉像素坐标结果: {screw_points_result2_text}")
            
            # 解析螺钉坐标
            try:
                second_image_point = json.loads(screw_points_result2_text)
                # 如果是列表且有元素，取第一个点
                if isinstance(second_image_point, list) and len(second_image_point) > 0:
                    if isinstance(second_image_point[0], list):
                        second_image_point = second_image_point[0]
                    print(f"第二标定点图像坐标: {second_image_point}")
            except json.JSONDecodeError:
                second_image_point = screw_points_result2_text
                print(f"第二标定点图像坐标: {second_image_point}")
            
            # 移动到标定位置3
            print(f"移动到标定位置3，偏移量: {offset3}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset3})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置3结果: {result_text}")
            
            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            third_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            third_robot_point_text = third_robot_point_result.content[0].text if third_robot_point_result.content else "获取失败"
            print(f"当前机器人TCP位置结果: {third_robot_point_text}")
            
            # 解析机器人位置
            try:
                third_robot_point = json.loads(third_robot_point_text)
                print(f"第三标定点机器人位置: {third_robot_point}")
            except json.JSONDecodeError:
                third_robot_point = third_robot_point_text
                print(f"第三标定点机器人位置: {third_robot_point}")
            
            # 检查所有必需的数据是否都已获取
            if not all([first_image_point, first_robot_point, second_image_point, 
                        second_robot_point, third_robot_point]):
                print("未能获取所有必需的标定数据，无法执行标定")
                return False
            
            # 执行螺钉标定
            print("执行螺钉标定...")
            print(f"标定点数据:")
            print(f"  first_image_point: {first_image_point}")
            print(f"  second_image_point: {second_image_point}")
            print(f"  first_robot_point: {first_robot_point}")
            print(f"  second_robot_point: {second_robot_point}")
            print(f"  third_robot_point: {third_robot_point}")
            
            # 调用标定算法（实际参数可能需要根据工具定义调整）
            calibration_result = await self.session.call_tool("Alg_screw_calibration", {
                "first_image_point": first_image_point,
                "second_image_point": second_image_point,
                "first_robot_point": first_robot_point,
                "second_robot_point": second_robot_point,
                "third_robot_point": third_robot_point
            })
            calibration_result_text = calibration_result.content[0].text if calibration_result.content else "标定失败"
            print(f"螺钉标定结果: {calibration_result_text}")
            
            print("螺钉标定流程测试完成")
            return True
            
        except Exception as e:
            print(f"测试螺钉标定流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 角度标定
    async def test_angle_calibration(self):
        """
        测试角度标定流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试角度标定流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            # # 获取初始位置
            # print("获取初始位置...")
            # home_position_result = await self.session.call_tool("Alg_get_home_position", {})
            # home_position_text = home_position_result.content[0].text if home_position_result.content else "获取失败"
            # print(f"获取初始位置结果: {home_position_text}")
            
            # # 解析初始位置
            # import json
            # try:
            #     home_position = json.loads(home_position_text)
            #     print(f"初始位置: {home_position}")
            # except json.JSONDecodeError:
            #     home_position = home_position_text
            #     print(f"初始位置: {home_position}")
            
            # # 检查是否获取到初始位置
            # if not home_position or "失败" in str(home_position):
            #     print("获取初始位置失败，无法继续标定流程")
            #     return False
            
            # # 移动到初始位置
            # print(f"移动到初始位置: {home_position}")
            # move_result = await self.session.call_tool("Rob_movej_2", {"tcp_pos": home_position})
            # move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            # print(f"移动到初始位置结果: {move_result_text}")
            
            # 获取法向量
            print("获取法向量...")
            normal_vector_result = await self.session.call_tool("Cam_get_normal_vector", {})
            normal_vector_text = normal_vector_result.content[0].text if normal_vector_result.content else "获取失败"
            print(f"获取法向量结果: {normal_vector_text}")
            
            # 解析法向量
            try:
                normal_vector = json.loads(normal_vector_text)
                print(f"法向量: {normal_vector}")
            except json.JSONDecodeError:
                normal_vector = normal_vector_text
                print(f"法向量: {normal_vector}")
            
            # 检查是否获取到法向量
            if not normal_vector:
                print("未能获取法向量，无法执行标定")
                return False
            
            # 执行角度标定
            print("执行角度标定...")
            print(f"标定数据:")
            print(f"  normal_vector: {normal_vector}")
            
            # 调用角度标定算法
            calibration_result = await self.session.call_tool("Alg_angle_calibration", {"normal": normal_vector})
            calibration_result_text = calibration_result.content[0].text if calibration_result.content else "标定失败"
            print(f"角度标定结果: {calibration_result_text}")
            
            print("角度标定流程测试完成")
            return True
            
        except Exception as e:
            print(f"测试角度标定流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 深度标定
    async def test_depth_calibration(self):
        """
        测试深度标定流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试深度标定流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            # # 获取初始位置
            # print("获取初始位置...")
            # home_position_result = await self.session.call_tool("Alg_get_home_position", {})
            # home_position_text = home_position_result.content[0].text if home_position_result.content else "获取失败"
            # print(f"获取初始位置结果: {home_position_text}")
            
            # # 解析初始位置
            # import json
            # try:
            #     home_position = json.loads(home_position_text)
            #     print(f"初始位置: {home_position}")
            # except json.JSONDecodeError:
            #     home_position = home_position_text
            #     print(f"初始位置: {home_position}")
            
            # # 检查是否获取到初始位置
            # if not home_position or "失败" in str(home_position):
            #     print("获取初始位置失败，无法继续标定流程")
            #     return False
            
            # # 移动到初始位置
            # print(f"移动到初始位置: {home_position}")
            # move_result = await self.session.call_tool("Rob_movej_2", {"tcp_pos": home_position})
            # move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            # print(f"移动到初始位置结果: {move_result_text}")
            
            # 获取深度
            print("获取深度...")
            depth_result = await self.session.call_tool("Cam_get_depth", {})
            depth_text = depth_result.content[0].text if depth_result.content else "获取失败"
            print(f"获取深度结果: {depth_text}")
            
            # 解析深度值
            try:
                depth_value = float(depth_text)
                print(f"深度值: {depth_value}")
            except ValueError:
                depth_value = depth_text
                print(f"深度值: {depth_value}")
            
            # 检查是否获取到深度值
            if depth_value is None:
                print("未能获取深度值，无法执行标定")
                return False
            
            # 执行深度标定
            print("执行深度标定...")
            print(f"标定数据:")
            print(f"  depth_value: {depth_value}")
            
            # 调用深度标定算法
            calibration_result = await self.session.call_tool("Alg_depth_calibration", {"current_depth": depth_value})
            calibration_result_text = calibration_result.content[0].text if calibration_result.content else "标定失败"
            print(f"深度标定结果: {calibration_result_text}")
            
            print("深度标定流程测试完成")
            return True
            
        except Exception as e:
            print(f"测试深度标定流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 螺钉调整
    async def test_screw_adjustment(self):
        """
        测试螺钉调整流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试螺钉调整流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            max_steps = 7  # 最大调整步数
            adjustment_completed = False
            current_pos_result = await self.session.call_tool("Rob_get_current_joint_pos", {})
            current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
            if "失败" in current_pos_text or not current_pos_text:
                print("获取当前关节位置失败，无法进行调整")
                return False
           # 解析当前位置
            import json
            try:
                current_pos = json.loads(current_pos_text)
                # 修改第6个元素（索引5）
                current_pos[5] = 0
            except json.JSONDecodeError:
                print("解析关节位置数据失败")
                return False
            except IndexError:
                print("关节位置数据长度不足，无法修改第6个元素")
                return False
            
            move_result = await self.session.call_tool("Rob_movej", {
                    "joint_angles": current_pos
                })
            
            for step in range(1, max_steps + 1):
                joint_pos = await self.session.call_tool("Rob_get_current_joint_pos")
                
                print(f"\n--- 螺钉调整步骤 {step} ---")
                await asyncio.sleep(5)
                # 获取螺钉像素坐标
                print("获取螺钉像素坐标...")
                screw_points_result = await self.session.call_tool("Cam_get_screw_points", {})
                screw_points_text = screw_points_result.content[0].text if screw_points_result.content else "获取失败"
                print(f"获取螺钉像素坐标结果: {screw_points_text}")
                
                # 解析螺钉坐标
                try:
                    screw_point = json.loads(screw_points_text)
                    # 如果是列表且有元素，取第一个点
                    if isinstance(screw_point, list) and len(screw_point) > 0:
                        if isinstance(screw_point[0], list):
                            screw_point = screw_point[0]
                        else:
                            screw_point = screw_point
                    print(f"螺钉坐标: {screw_point}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    screw_point = screw_points_text
                    print(f"螺钉坐标: {screw_point}")
                
                # 检查是否获取到螺钉坐标
                if not screw_point:
                    print("未能获取螺钉坐标，跳过本次调整")
                    continue
                
                # 判断是否完成调整
                print("判断是否完成螺钉调整...")
                estimate_result = await self.session.call_tool("Alg_screw_adjust_estimate", {"pos": screw_point})
                estimate_result_text = estimate_result.content[0].text if estimate_result.content else "判断失败"
                print(f"判断调整状态结果: {estimate_result_text}")
                
                # 如果完成调整则退出循环
                if "是" in str(estimate_result_text):
                    print("螺钉调整完成")
                    adjustment_completed = True
                    break
                
                # 计算移动偏移量
                print("计算移动偏移量...")
                offset_result = await self.session.call_tool("Alg_screw_adjust", {"pos": screw_point})
                offset_result_text = offset_result.content[0].text if offset_result.content else "计算失败"
                print(f"计算移动偏移量结果: {offset_result_text}")
                
                # 解析偏移量
                try:
                    offset_value = json.loads(offset_result_text)
                    print(f"解析后的偏移量: {offset_value}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    offset_value = offset_result_text
                    print(f"偏移量: {offset_value}")
                
                # 检查是否获取到偏移量
                if not offset_value:
                    print("未能计算出移动偏移量，跳过本次调整")
                    continue
                    
                # 移动机器人
                print(f"移动机器人，偏移量: {offset_value}")
                move_result = await self.session.call_tool("Rob_movetcp", {"offset": offset_value})
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动机器人结果: {move_result_text}")
            
            if adjustment_completed:
                print("螺钉调整流程测试完成")
                return True
            else:
                print(f"螺钉调整流程测试未完成，达到最大调整步数 {max_steps}")
                return False
            
        except Exception as e:
            print(f"测试螺钉调整流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 角度调整
    async def test_angle_adjustment(self):
        """
        测试角度调整流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试角度调整流程 ===")
        start_time1 = time.time()
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            max_steps = 6  # 最大调整步数
            adjustment_completed = False
            
            for step in range(1, max_steps + 1):
                print(f"\n--- 角度调整步骤 {step} ---")
                # 获取法向量
                # await asyncio.sleep(5)
                start_time = time.time()
                print("获取法向量...")
                normal_vector_result = await self.session.call_tool("Cam_get_normal_vector", {})
                normal_vector_text = normal_vector_result.content[0].text if normal_vector_result.content else "获取失败"
                print(f"获取法向量结果: {normal_vector_text}")
                end_time = time.time()
                print(f"获取法向量耗时: {end_time - start_time:.2f} 秒")
                # await asyncio.sleep(5)
                # 解析法向量
                try:
                    normal_vector = json.loads(normal_vector_text)
                    print(f"法向量: {normal_vector}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    normal_vector = normal_vector_text
                    print(f"法向量: {normal_vector}")
                
                # 检查是否获取到法向量
                if not normal_vector:
                    print("未能获取法向量，跳过本次调整")
                    continue
                
                # 判断是否完成调整
                print("判断是否完成角度调整...")
                estimate_result = await self.session.call_tool("Alg_angle_adjust_estimate", {"measured_z": normal_vector})
                estimate_result_text = estimate_result.content[0].text if estimate_result.content else "判断失败"
                print(f"判断调整状态结果: {estimate_result_text}")
                
                # 如果完成调整则退出循环
                if "是" in str(estimate_result_text):
                    print("角度调整完成")
                    adjustment_completed = True
                    break
                
                # 计算调整量
                print("计算角度调整量...")
                offset_result = await self.session.call_tool("Alg_angle_adjust", {"measured_z": normal_vector})
                offset_result_text = offset_result.content[0].text if offset_result.content else "计算失败"
                print(f"计算角度调整量结果: {offset_result_text}")
                
                # 解析调整量
                try:
                    offset_value = json.loads(offset_result_text)
                    print(f"解析后的调整量: {offset_value}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    offset_value = offset_result_text
                    print(f"调整量: {offset_value}")
                
                # 检查是否获取到调整量
                if not offset_value:
                    print("未能计算出角度调整量，跳过本次调整")
                    continue
                    
                # 移动机器人
                print(f"移动机器人，调整量: {offset_value}")
                move_result = await self.session.call_tool("Rob_movetcp", {"offset": offset_value})
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动机器人结果: {move_result_text}")
                # await asyncio.sleep(2)
            if adjustment_completed:
                print("角度调整流程测试完成")
                end_time1 = time.time()
                print(f"螺钉调整总耗时: {end_time1 - start_time1:.2f} 秒")
                return True
            else:
                print(f"角度调整流程测试未完成，达到最大调整步数 {max_steps}")
                return False
            
        except Exception as e:
            print(f"测试角度调整流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 深度调整
    async def test_depth_adjustment(self):
        """
        测试深度调整流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试深度调整流程 ===")
        start_time = time.time()
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            max_steps = 6  # 最大调整步数
            adjustment_completed = False
            
            for step in range(1, max_steps + 1):
                print(f"\n--- 深度调整步骤 {step} ---")
                # 获取深度
                print("获取深度...")
                start1_time = time.time()
                depth_result = await self.session.call_tool("Cam_get_depth", {})
                depth_text = depth_result.content[0].text if depth_result.content else "获取失败"
                print(f"获取深度结果: {depth_text}")
                end1_time = time.time()
                print(f"获取深度耗时: {end1_time - start1_time:.2f} 秒")
                # 解析深度值
                try:
                    depth_value = float(depth_text)
                    print(f"深度值: {depth_value}")
                except ValueError:
                    print(f"无法解析深度值: {depth_text}")
                    depth_value = None
                
                # 检查是否获取到深度值
                if not depth_value:
                    print("未能获取深度值，跳过本次调整")
                    continue
                
                # 判断是否完成调整
                print("判断是否完成深度调整...")
                estimate_result = await self.session.call_tool("Alg_depth_adjust_estimate", {"current_depth": depth_value})
                estimate_result_text = estimate_result.content[0].text if estimate_result.content else "判断失败"
                print(f"判断调整状态结果: {estimate_result_text}")
                
                # 如果完成调整则退出循环
                if "是" in str(estimate_result_text):
                    print("深度调整完成")
                    adjustment_completed = True
                    break
                
                # 计算调整量
                print("计算深度调整量...")
                pos_result = await self.session.call_tool("Alg_depth_adjust", {"current_depth": depth_value})
                pos_result_text = pos_result.content[0].text if pos_result.content else "计算失败"
                print(f"计算深度调整量结果: {pos_result_text}")
                
                # 解析调整量
                try:
                    pos_value = json.loads(pos_result_text)
                    print(f"解析后的调整量: {pos_value}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    pos_value = pos_result_text
                    print(f"调整量: {pos_value}")
                
                # 检查是否获取到调整量
                if not pos_value:
                    print("未能计算出深度调整量，跳过本次调整")
                    continue
                    
                # 移动机器人
                print(f"移动机器人，调整量: {pos_value}")
                move_result = await self.session.call_tool("Rob_movetcp", {"offset": pos_value})
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动机器人结果: {move_result_text}")
            end_time = time.time()
            print(f"单次深度调整总耗时: {end_time - start_time:.2f} 秒")
            return True
            # if adjustment_completed:
            #     offset_text = await self.session.call_tool("Alg_get_offset_info",{})
            #     offset_text = json.loads(offset_text.content[0].text) if offset_text.content else "获取失败"
            #     offset4 = offset_text["offset4"]
            #     print(f"偏移量4: {offset4}")
            #     move_result = await self.session.call_tool("Rob_movetcp", {"offset": offset4})
            #     print(f"移动机器人结果: {move_result_text}")
            #     print("深度调整流程测试完成")
            #     return True
            # else:
            #     print(f"深度调整流程测试未完成，达到最大调整步数 {max_steps}")
            #     return False
            
        except Exception as e:
            print(f"测试深度调整流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 移动指令
    async def test_move_command(self, command_str: str):
        """
        测试移动指令功能
        解析并执行移动命令，如: "movetcp 1 2 3 4 5 6"
        """
        global robot_connected
        
        print("=== 测试移动指令功能 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
            
            # 解析命令字符串
            parts = command_str.strip().split()
            if len(parts) < 7:
                print("命令格式错误，需要至少7个参数: movetcp x y z rx ry rz")
                return False
                
            command = parts[0].lower()
            if command not in ["movetcp", "movej", "movej_2", "movel" ,"movetcp_position_to"]:
                print("不支持的命令，仅支持: movetcp, movej, movej_2, movel")
                return False
                
            # 解析位置参数
            try:
                position = [float(x) for x in parts[1:7]]
            except ValueError:
                print("位置参数必须是数字")
                return False
                
            print(f"执行 {command} 命令，目标位置: {position}")
            
            # 执行相应的移动命令
            if command == "movetcp":
                result = await self.session.call_tool("Rob_movetcp", {"offset": position})
                result_text = result.content[0].text if result.content else "执行失败"
                print(f"Rob_movetcp 执行结果: {result_text}")
            elif command == "movej":
                result = await self.session.call_tool("Rob_movej", {"joint_pos": position})
                result_text = result.content[0].text if result.content else "执行失败"
                print(f"Rob_movej 执行结果: {result_text}")
            elif command == "movej_2":
                result = await self.session.call_tool("Rob_movej_2", {"tcp_pos": position})
                result_text = result.content[0].text if result.content else "执行失败"
                print(f"Rob_movej_2 执行结果: {result_text}")
            elif command == "movel":
                result = await self.session.call_tool("Rob_movel", {"tcp_pose": position})
                result_text = result.content[0].text if result.content else "执行失败"
                print(f"Rob_movel 执行结果: {result_text}")
            elif command == "movetcp_position_to":
                result = await self.session.call_tool("movetcp_position_to", {"offset": position})
                result_text = result.content[0].text if result.content else "执行失败"
                print(f"Rob_moveb 执行结果: {result_text}")
            return True
            
        except Exception as e:
            print(f"测试移动指令功能时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 拧螺套演示
    async def test_screw_demo(self):
        """
        测试拧螺套演示流程
        """
        global io_connected, robot_connected
        
        print("=== 测试拧螺套演示流程 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
            
            # 连接电机
            print("连接电机...")
            motor_result = await self.session.call_tool("Io_connect_motor", {})
            motor_result_text = motor_result.content[0].text if motor_result.content else "连接失败"
            print(f"连接电机结果: {motor_result_text}")
            if "失败" in motor_result_text or not motor_result_text:
                print("连接电机失败，停止演示")
                return False
            
            # 打开2号输出口
            print("打开2号输出口...")
            do_result = await self.session.call_tool("Io_set_do_output", {"index": 2, "value": True})
            do_result_text = do_result.content[0].text if do_result.content else "操作失败"
            print(f"打开2号输出口结果: {do_result_text}")
            if "失败" in do_result_text or not do_result_text:
                print("打开2号输出口失败，停止演示")
                return False
            

            print("等待0.5秒...")
            await asyncio.sleep(0.5)

            # 机器人移动: z=+125mm
            print("机器人移动: z=+125mm...")
            move_result = await self.session.call_tool("Rob_movetcp", {"offset": [0, 0, 0.125, 0, 0, 0]})
            move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            print(f"机器人移动结果: {move_result_text}")
            if "失败" in move_result_text or not move_result_text:
                print("机器人移动失败，停止演示")
                return False
            
            print("等待0.5秒...")
            await asyncio.sleep(0.5)

            # 电机正转
            print("电机正转...")
            motor_forward_result = await self.session.call_tool("Io_set_motor_state", {"state": 100})
            motor_forward_text = motor_forward_result.content[0].text if motor_forward_result.content else "操作失败"
            print(f"电机正转结果: {motor_forward_text}")
            if "失败" in motor_forward_text or not motor_forward_text:
                print("电机正转失败，停止演示")
                return False
            
            # 等待14秒
            print("等待14秒...")
            await asyncio.sleep(14)
            
            # 电机停止
            print("电机停止...")
            motor_stop_result = await self.session.call_tool("Io_set_motor_state", {"state": 0})
            motor_stop_text = motor_stop_result.content[0].text if motor_stop_result.content else "操作失败"
            print(f"电机停止结果: {motor_stop_text}")
            if "失败" in motor_stop_text or not motor_stop_text:
                print("电机停止失败，停止演示")
                return False
            
            print("等待0.5秒...")
            await asyncio.sleep(0.5)


            # 关闭2号输出口
            print("关闭2号输出口...")
            do_close_result = await self.session.call_tool("Io_set_do_output", {"index": 2, "value": False})
            do_close_text = do_close_result.content[0].text if do_close_result.content else "操作失败"
            print(f"关闭2号输出口结果: {do_close_text}")
            if "失败" in do_close_text or not do_close_text:
                print("关闭2号输出口失败，停止演示")
                return False
            
            print("等待0.5秒...")
            await asyncio.sleep(0.5)
            
            # 机器人移动: z=-125mm
            print("机器人移动: z=-125mm...")
            move_back_result = await self.session.call_tool("Rob_movetcp", {"offset": [0, 0, -0.125, 0, 0, 0]})
            move_back_text = move_back_result.content[0].text if move_back_result.content else "移动失败"
            print(f"机器人移动结果: {move_back_text}")
            if "失败" in move_back_text or not move_back_text:
                print("机器人移动失败，停止演示")
                return False
            
            print("拧螺套演示流程测试完成")
            return True
            
        except Exception as e:
            print(f"测试拧螺套演示流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 保存位姿
    async def save_current_pose(self, point_name: str):
        """
        保存当前机器人位姿
        """
        global robot_connected
        
        print(f"=== 保存当前位姿 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法保存位姿")
                return False
                
            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            current_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
            print(f"当前机器人TCP位置: {current_pos_text}")
            
            if "失败" in current_pos_text or not current_pos_text:
                print("获取机器人位置失败，无法保存位姿")
                return False
                
            # 解析位置数据
            import json
            try:
                current_pos = json.loads(current_pos_text)
                print(f"解析后的位置数据: {current_pos}")
            except json.JSONDecodeError:
                current_pos = current_pos_text
                print(f"位置数据: {current_pos}")
                
            # 保存位置数据
            print(f"保存位姿 '{point_name}'...")
            save_result = await self.session.call_tool("Alg_record_point", {
                "point_name": point_name,
                "robot_position": current_pos
            })
            save_result_text = save_result.content[0].text if save_result.content else "保存失败"
            print(f"保存结果: {save_result_text}")
            
            if "失败" in save_result_text or not save_result_text:
                print("保存位姿失败")
                return False
                
            print(f"成功保存位姿 '{point_name}'")
            return True
            
        except Exception as e:
            print(f"保存当前位姿时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 移动到已保存的位姿
    async def move_to_saved_pose(self):
        """
        移动到已保存的位姿
        """
        global robot_connected
        
        print("=== 移动到保存位姿 ===")
        
        while True:
            try:
                # 确保机器人已连接
                if not robot_connected:
                    print("机器人未连接，无法移动")
                    return False
                    
                # 获取所有保存的点位
                print("获取已保存的位姿列表...")
                points_result = await self.session.call_tool("Alg_get_recorded_point", {})
                points_text = points_result.content[0].text if points_result.content else "获取失败"
                print(f"已保存的位姿: {points_text}")
                
                if "失败" in points_text or not points_text:
                    print("获取保存位姿失败")
                    return False
                    
                # 解析点位数据
                import json
                try:
                    points_data = json.loads(points_text)
                    if not isinstance(points_data, dict):
                        print("点位数据格式错误")
                        return False
                        
                    if not points_data:
                        print("没有保存的位姿")
                        return False
                        
                    print("可用的位姿:")
                    for i, (name, pos) in enumerate(points_data.items(), 1):
                        print(f"  {i}. {name}: {pos}")
                    print("  0. 退出")
                        
                except json.JSONDecodeError:
                    print("解析点位数据失败")
                    return False
                    
                # 让用户选择一个点位
                try:
                    choice = input("请选择要移动到位姿的编号 (输入0退出): ").strip()
                    
                    # 检查是否为退出
                    if choice == "0":
                        print("退出移动到保存位姿功能")
                        return True
                    
                    choice = int(choice)
                    if choice < 1 or choice > len(points_data):
                        print("无效选择")
                        continue
                        
                    # 获取选中的点位
                    point_name = list(points_data.keys())[choice - 1]
                    target_position = points_data[point_name]
                    print(f"选择位姿: {point_name}")
                    print(f"目标位置: {target_position}")
                    
                except (ValueError, IndexError):
                    print("选择无效")
                    continue
                except KeyboardInterrupt:
                    print("用户取消操作")
                    return False
                    
                # 移动到指定位置
                print(f"移动到 '{point_name}'...")
                move_result = await self.session.call_tool("Rob_movel", {
                    "tcp_pose": target_position
                })
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动结果: {move_result_text}")
                
                if "失败" in move_result_text or not move_result_text:
                    print("移动失败")
                    continue
                    
                print("成功移动到指定位置")
                
            except Exception as e:
                print(f"移动到保存位姿时出错: {e}")
                import traceback
                traceback.print_exc()
                continue

    #region 气夹控制    
    async def pneumatic_gripper_control(self):
        """
        气夹控制功能
        通过控制数字输出口来控制气夹的开关
        """
        global io_connected
            
        print("=== 气夹控制 ===")
        
        try:
            # 连接电机控制器（如果尚未连接）
            print("检查电机控制器连接状态...")
            connect_result = await self.session.call_tool("Io_connect_motor", {})
            connect_result_text = connect_result.content[0].text if connect_result.content else "连接检查失败"
            print(f"连接状态: {connect_result_text}")
            
            if "失败" in connect_result_text:
                print("无法连接到电机控制器，无法控制气夹")
                return False
            
            while True:
                print("\n气夹控制选项:")
                print("1. 打开气夹 (DO2=ON)")
                print("2. 关闭气夹 (DO2=OFF)")
                print("3. 打开输出口(0-7)")
                print("4. 返回主菜单")
                
                gripper_choice = input("请选择操作 (1-3): ").strip()
                
                if gripper_choice == "1":
                    # 打开气夹 - 设置DO2为ON
                    print("打开气夹...")
                    do_result = await self.session.call_tool("Io_set_do_output", {"index": 2, "value": True})
                    do_result_text = do_result.content[0].text if do_result.content else "操作失败"
                    print(f"操作结果: {do_result_text}")
                    
                    if "失败" not in do_result_text:
                        print("气夹已打开")
                    else:
                        print("打开气夹失败")
                        
                elif gripper_choice == "2":
                    # 关闭气夹 - 设置DO2为OFF
                    print("关闭气夹...")
                    do_result = await self.session.call_tool("Io_set_do_output", {"index": 2, "value": False})
                    do_result_text = do_result.content[0].text if do_result.content else "操作失败"
                    print(f"操作结果: {do_result_text}")
                    
                    if "失败" not in do_result_text:
                        print("气夹已关闭")
                    else:
                        print("关闭气夹失败")

                elif gripper_choice == "3":
                    while True:
                        print("\n输出口控制选项:")
                        print("\n1.打开输出口")
                        print("\n2.关闭输出口")
                        print("\n3.返回")
                        _choice = input("请选择操作 (1-3): ").strip()
                
                        if _choice == "1":
                            _choice2 = input("请选择打开输出口号 (0-7): ").strip()
                            # 打开指定输出口
                            index = int(_choice2)
                            do_result = await self.session.call_tool("Io_set_do_output", {"index": index, "value": True})
                            do_result_text = do_result.content[0].text if do_result.content else "操作失败"
                            print(f"操作结果: {do_result_text}")
                            
                            if "失败" not in do_result_text:
                                print(f"输出口{index}已打开")
                            else:
                                print("打开失败")
                                
                        elif _choice == "2":
                            # 关闭指定输出口
                            _choice3 = input("请选择打关闭输出口号 (0-7): ").strip()
                            index = int(_choice3)
                            do_result = await self.session.call_tool("Io_set_do_output", {"index": index, "value": False})
                            do_result_text = do_result.content[0].text if do_result.content else "操作失败"
                            print(f"操作结果: {do_result_text}")
                            
                            if "失败" not in do_result_text:
                                print(f"输出口{index}已关闭")
                            else:
                                print("关闭失败")
                        elif _choice == "3":
                            print("返回上一层菜单")
                            break

                elif gripper_choice == "4":
                    print("返回主菜单")
                    break
                    
                else:
                    print("无效选择，请重新输入")
                    
            return True
            
        except Exception as e:
            print(f"气夹控制出错: {e}")
            import traceback
            traceback.print_exc()
            return False
            

    #region 电机控制
    async def motor_control(self):
        """
        电机控制功能
        控制电机的启停和正反转
        """
        global io_connected
        
        print("=== 电机控制 ===")
        
        try:
            # 连接电机控制器（如果尚未连接）
            print("检查电机控制器连接状态...")
            connect_result = await self.session.call_tool("Io_connect_motor", {})
            connect_result_text = connect_result.content[0].text if connect_result.content else "连接检查失败"
            print(f"连接状态: {connect_result_text}")
            
            if "失败" in connect_result_text:
                print("无法连接到电机控制器，无法控制电机")
                return False
            
            while True:
                print("\n电机控制选项:")
                print("1. 电机正转")
                print("2. 电机反转")
                print("3. 停止电机")
                print("4. 返回主菜单")
                
                motor_choice = input("请选择操作 (1-4): ").strip()
                
                if motor_choice == "1":
                    # 电机正转
                    print("电机正转...")
                    motor_result = await self.session.call_tool("Io_set_motor_state", {"state": 100})
                    motor_result_text = motor_result.content[0].text if motor_result.content else "操作失败"
                    print(f"操作结果: {motor_result_text}")
                    
                    if "失败" not in motor_result_text:
                        print("电机开始正转")
                    else:
                        print("电机正转失败")
                        
                elif motor_choice == "2":
                    # 电机反转
                    print("电机反转...")
                    motor_result = await self.session.call_tool("Io_set_motor_state", {"state": 200})
                    motor_result_text = motor_result.content[0].text if motor_result.content else "操作失败"
                    print(f"操作结果: {motor_result_text}")
                    
                    if "失败" not in motor_result_text:
                        print("电机开始反转")
                    else:
                        print("电机反转失败")
                        
                elif motor_choice == "3":
                    # 停止电机
                    print("停止电机...")
                    motor_result = await self.session.call_tool("Io_set_motor_state", {"state": 0})
                    motor_result_text = motor_result.content[0].text if motor_result.content else "操作失败"
                    print(f"操作结果: {motor_result_text}")
                    
                    if "失败" not in motor_result_text:
                        print("电机已停止")
                    else:
                        print("停止电机失败")
                        
                elif motor_choice == "4":
                    print("返回主菜单")
                    break
                    
                else:
                    print("无效选择，请重新输入")
                    
            return True
            
        except Exception as e:
            print(f"电机控制出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        

    #region 拖动示教
    async def teach_mode_control(self):
        """
        拖动示教功能
        进入示教模式后，用户可以手动拖动机器人进行示教
        退出函数时自动退出拖动示教模式
        """
        global robot_connected
        
        print("=== 拖动示教 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法进入示教模式")
                return False
                
            # 进入示教模式
            print("进入拖动示教模式...")
            enter_result = await self.session.call_tool("Rob_enter_teach_mode", {})
            enter_result_text = enter_result.content[0].text if enter_result.content else "进入示教模式失败"
            print(f"进入示教模式结果: {enter_result_text}")
            
            if "失败" in enter_result_text or "未连接" in enter_result_text:
                print("无法进入示教模式")
                return False
                
            print("\n已进入拖动示教模式")
            print("您可以手动拖动机器人进行示教")
            print("按回车键退出示教模式...")
            
            # 等待用户按键退出
            try:
                input()
            except KeyboardInterrupt:
                print("\n检测到中断信号")
                
            # 退出示教模式
            print("退出拖动示教模式...")
            exit_result = await self.session.call_tool("Rob_exit_teach_mode", {})
            exit_result_text = exit_result.content[0].text if exit_result.content else "退出示教模式失败"
            print(f"退出示教模式结果: {exit_result_text}")
            
            if "失败" in exit_result_text:
                print("警告：退出示教模式可能失败")
                return False
                
            print("已退出拖动示教模式")
            return True
            
        except Exception as e:
            print(f"拖动示教出错: {e}")
            import traceback
            traceback.print_exc()
            
            # 尝试退出示教模式
            try:
                print("尝试强制退出示教模式...")
                exit_result = await self.session.call_tool("Rob_exit_teach_mode", {})
                exit_result_text = exit_result.content[0].text if exit_result.content else "退出示教模式失败"
                print(f"强制退出示教模式结果: {exit_result_text}")
            except:
                pass
                
            return False
    #region 焊钉演示
    async def test_hanqiang(self):
        """
        焊钉演示
        """
        global io_connected, robot_connected
        
        print("=== 测试焊钉演示流程 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
            # 连接电机
            print("连接电机...")
            motor_result = await self.session.call_tool("Io_connect_motor", {})
            motor_result_text = motor_result.content[0].text if motor_result.content else "连接失败"
            print(f"连接电机结果: {motor_result_text}")
            if "失败" in motor_result_text or not motor_result_text:
                print("连接电机失败，停止演示")
                return False    
            # #机器人移动
            # print("机器人移动: x=+50mm...")
            # move_result = await self.session.call_tool("Rob_movetcp", {"offset": [-0.05, 0 , 0, 0, 0, 0]})
            # move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            # print(f"机器人移动结果: {move_result_text}")
            
            # 打开7号输出口摇摆
            print("打开7号输出口...")
            do_result = await self.session.call_tool("Io_set_do_output", {"index": 7, "value": True})
            do_result_text = do_result.content[0].text if do_result.content else "操作失败"
            print(f"打开7号输出口结果: {do_result_text}")
            if "失败" in do_result_text or not do_result_text:
                print("打开7号输出口失败，停止演示")
                return False
            print("等待1秒...")
            await asyncio.sleep(1)

            # 打开6号输出口激光
            print("打开6号输出口...")
            do_result = await self.session.call_tool("Io_set_do_output", {"index": 6, "value": True})
            do_result_text = do_result.content[0].text if do_result.content else "操作失败"
            print(f"打开6号输出口结果: {do_result_text}")
            if "失败" in do_result_text or not do_result_text:
                print("打开6号输出口失败，停止演示")
                return False
            print("等待4秒...")
            await asyncio.sleep(3)

            # 关闭6,7号输出口
            print("关闭6号输出口...")
            do_close_result = await self.session.call_tool("Io_set_do_output", {"index": 6, "value": False})
            do_close_text = do_close_result.content[0].text if do_close_result.content else "操作失败"
            print(f"关闭6号输出口结果: {do_close_text}")
            if "失败" in do_close_text or not do_close_text:
                print("关闭6号输出口失败，停止演示")
                return False
            print("关闭7号输出口...")
            do_close_result = await self.session.call_tool("Io_set_do_output", {"index": 7, "value": False})
            do_close_text = do_close_result.content[0].text if do_close_result.content else "操作失败"
            print(f"关闭7号输出口结果: {do_close_text}")
            if "失败" in do_close_text or not do_close_text:
                print("关闭7号输出口失败，停止演示")
                return False
            await asyncio.sleep(1)

            #机器人移动
            print("机器人移动: x=+50mm...")#对齐
            move_result = await self.session.call_tool("Rob_movetcp", {"offset": [-0.007, -0.115, 0, 0, 0, 0]})
            move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            print(f"机器人移动结果: {move_result_text}")
            await asyncio.sleep(2)
            #机器人移动
            print("机器人移动: z=+75mm...")#向前顶准备焊
            move_result = await self.session.call_tool("Rob_movetcp", {"offset": [0, 0, 0.094, 0, 0, 0]})
            move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            print(f"机器人移动结果: {move_result_text}")

            await asyncio.sleep(2)
            # 打开5号输出口焊枪
            user_input = input("是否打开5号输出口焊枪？(输入'y'继续，其他任意键取消): ")
            if user_input.lower() != 'y':
                print("操作已取消")
                return False
            print("打开5号输出口...")#焊枪
            do_result = await self.session.call_tool("Io_set_do_output", {"index": 5, "value": True})#TODO
            do_result_text = do_result.content[0].text if do_result.content else "操作失败"
            print(f"打开5号输出口结果: {do_result_text}")
            if "失败" in do_result_text or not do_result_text:
                print("打开5号输出口失败，停止演示")
                return False
            print("等待4秒...")
            await asyncio.sleep(4)
            print("关闭5号输出口...")
            do_close_result = await self.session.call_tool("Io_set_do_output", {"index": 5, "value": False})
            do_close_text = do_close_result.content[0].text if do_close_result.content else "操作失败"
            print(f"关闭5号输出口结果: {do_close_text}")
            #机器人移动（向后退到激光的深度
            print("机器人移动: z=-75mm...")#向前顶准备焊

            move_result = await self.session.call_tool("Rob_movetcp", {"offset": [0, 0, -0.094, 0, 0, 0]})
            move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            print(f"机器人移动结果: {move_result_text}")
            await asyncio.sleep(1)

            #机器人移动
            print("机器人移动: 回到原位")#对齐
            move_result = await self.session.call_tool("Rob_movetcp", {"offset": [0.007, 0.115, 0, 0, 0, 0]})
            move_result_text = move_result.content[0].text if move_result.content else "移动失败"
            print(f"机器人移动结果: {move_result_text}")
            await asyncio.sleep(2)

        except Exception as e:
            print(f"测试拧螺套演示流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

# ... existing code ...
    #region 获取法向量
    async def get_normal(self):
        """
        获取法向量
        """
        print("获取法向量...")
        normal_vector_result = await self.session.call_tool("Cam_get_normal_vector", {})
        normal_vector_text = normal_vector_result.content[0].text if normal_vector_result.content else "获取失败"
        print(f"获取法向量结果: {normal_vector_text}")
        return true    
        
    #region 示教取钉位置
    async def teach_nail_positions(self):
        """
        示教50个位置点用于取钉操作
        25个取钉位置 + 25个预取钉位置
        """
        global robot_connected
        
        print("=== 示教取钉位置 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法进行示教")
                return False
                
            # 创建存储位置的数组
            pick_positions = []      # 取钉位置
            prepick_positions = []   # 预取钉位置
            
            print("开始示教50个位置点 (25个取钉位置 + 25个预取钉位置)")
            print("请确保机器人已处于安全状态，并且有足够空间进行示教")
            
            # 获取当前点位作为起始点
            print("获取当前位置...")
            current_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
            
            if "失败" in current_pos_text or not current_pos_text:
                print("获取当前位置失败，无法开始示教")
                return False
                
            print(f"当前位置: {current_pos_text}")
            
            # 示教25个取钉位置和25个预取钉位置
            for i in range(25):
                print(f"\n--- 示教第 {i+1} 个钉子的位置 ---")
                
                # 示教取钉位置
                print(f"请将机器人移动到第 {i+1} 个钉子的取钉位置")
                input("按回车键确认已到达取钉位置...")
                
                # 获取当前位置
                print("获取取钉位置坐标...")
                pick_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
                pick_pos_text = pick_pos_result.content[0].text if pick_pos_result.content else "获取失败"
                
                if "失败" in pick_pos_text or not pick_pos_text:
                    print("获取取钉位置失败，跳过此位置")
                    continue
                    
                # 解析位置数据
                import json
                try:
                    pick_pos = json.loads(pick_pos_text)
                    pick_positions.append(pick_pos)
                    print(f"第 {i+1} 个取钉位置已记录: {pick_pos}")
                except json.JSONDecodeError:
                    pick_positions.append(pick_pos_text)
                    print(f"第 {i+1} 个取钉位置已记录: {pick_pos_text}")
                
                # 示教预取钉位置
                print(f"请将机器人移动到第 {i+1} 个钉子的预取钉位置")
                input("按回车键确认已到达预取钉位置...")
                
                # 获取当前位置
                print("获取预取钉位置坐标...")
                prepick_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
                prepick_pos_text = prepick_pos_result.content[0].text if prepick_pos_result.content else "获取失败"
                
                if "失败" in prepick_pos_text or not prepick_pos_text:
                    print("获取预取钉位置失败，跳过此位置")
                    continue
                    
                # 解析位置数据
                try:
                    prepick_pos = json.loads(prepick_pos_text)
                    prepick_positions.append(prepick_pos)
                    print(f"第 {i+1} 个预取钉位置已记录: {prepick_pos}")
                except json.JSONDecodeError:
                    prepick_positions.append(prepick_pos_text)
                    print(f"第 {i+1} 个预取钉位置已记录: {prepick_pos_text}")
            
            # 显示收集到的所有位置
            print(f"\n示教完成！共记录 {len(pick_positions)} 个取钉位置和 {len(prepick_positions)} 个预取钉位置")
            print("\n取钉位置:")
            for i, pos in enumerate(pick_positions):
                print(f"  {i+1}. {pos}")
                
            print("\n预取钉位置:")
            for i, pos in enumerate(prepick_positions):
                print(f"  {i+1}. {pos}")
            
            # 保存位置到本地文件
            import os
            positions_data = {
                "pick_positions": pick_positions,
                "prepick_positions": prepick_positions
            }
            
            # 构建保存文件路径
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "calibration")
            save_path = os.path.join(save_dir, "nail_positions_data.json")
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 保存到文件
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(positions_data, f, ensure_ascii=False, indent=4)
            
            print(f"\n位置数据已保存到: {save_path}")
            return True
            
        except Exception as e:
            print(f"示教取钉位置时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 示教焊钉位置
    async def teach_welding_nail_positions(self):
        """
        示教25个焊钉点位并存储到本地
        """
        global robot_connected
        
        print("=== 示教焊钉位置 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法进行示教")
                return False
                
            # 创建存储焊钉位置的数组
            welding_nail_positions = []
            
            print("开始示教25个焊钉点位")
            print("请确保机器人已处于安全状态，并且有足够空间进行示教")
            
            # 获取当前点位作为起始点
            print("获取当前位置...")
            current_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
            
            if "失败" in current_pos_text or not current_pos_text:
                print("获取当前位置失败，无法开始示教")
                return False
                
            print(f"当前位置: {current_pos_text}")
            
            # 示教25个焊钉位置
            for i in range(25):
                print(f"\n--- 示教第 {i+1} 个焊钉位置 ---")
                
                # 示教焊钉位置
                print(f"请将机器人移动到第 {i+1} 个焊钉位置")
                input("按回车键确认已到达焊钉位置...")
                
                # 获取当前位置
                print("获取焊钉位置坐标...")
                weld_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
                weld_pos_text = weld_pos_result.content[0].text if weld_pos_result.content else "获取失败"
                
                if "失败" in weld_pos_text or not weld_pos_text:
                    print("获取焊钉位置失败，跳过此位置")
                    continue
                    
                # 解析位置数据
                import json
                try:
                    weld_pos = json.loads(weld_pos_text)
                    welding_nail_positions.append(weld_pos)
                    print(f"第 {i+1} 个焊钉位置已记录: {weld_pos}")
                except json.JSONDecodeError:
                    welding_nail_positions.append(weld_pos_text)
                    print(f"第 {i+1} 个焊钉位置已记录: {weld_pos_text}")
            
            # 显示收集到的所有位置
            print(f"\n示教完成！共记录 {len(welding_nail_positions)} 个焊钉位置")
            print("\n焊钉位置:")
            for i, pos in enumerate(welding_nail_positions):
                print(f"  {i+1}. {pos}")
            
            # 保存位置到本地文件
            import os
            positions_data = {
                "welding_nail_positions": welding_nail_positions
            }
            
            # 构建保存文件路径
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "calibration")
            save_path = os.path.join(save_dir, "welding_nail_positions_data.json")
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 保存到文件
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(positions_data, f, ensure_ascii=False, indent=4)
            
            print(f"\n位置数据已保存到: {save_path}")
            return True
            
        except Exception as e:
            print(f"示教焊钉位置时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
        

    #region连续25个焊钉演示
    async def  Welding_Studs_Demonstration(self):
        """
        连续焊钉演示
        """
        global robot_connected
        
        print("=== 连续25个焊钉演示 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法进行演示")
                return False
                
            # 读取预取钉、取钉位置和焊钉位置
            import os
            import json
            
            # 构建文件路径
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "calibration")
            nail_positions_file = os.path.join(config_dir, "nail_positions_data.json")
            welding_positions_file = os.path.join(config_dir, "welding_nail_positions_data.json")
            
            # 读取取钉和预取钉位置
            if not os.path.exists(nail_positions_file):
                print("未找到取钉位置文件，请先执行示教取钉位置")
                return False
                
            with open(nail_positions_file, 'r', encoding='utf-8') as f:
                nail_data = json.load(f)
                
            pick_positions = nail_data.get("pick_positions", [])
            prepick_positions = nail_data.get("prepick_positions", [])
            
            # 读取焊钉位置
            if not os.path.exists(welding_positions_file):
                print("未找到焊钉位置文件，请先执行示教焊钉位置")
                return False
                
            with open(welding_positions_file, 'r', encoding='utf-8') as f:
                welding_data = json.load(f)
                
            welding_positions = welding_data.get("welding_nail_positions", [])
            
            # 检查数据完整性
            if len(pick_positions) < 25 or len(prepick_positions) < 25 or len(welding_positions) < 25:
                print(f"位置数据不完整: 取钉位置{len(pick_positions)}个, 预取钉位置{len(prepick_positions)}个, 焊钉位置{len(welding_positions)}个")
                print("请重新示教位置数据")
                return False
            
            print(f"成功加载位置数据: 取钉位置{len(pick_positions)}个, 预取钉位置{len(prepick_positions)}个, 焊钉位置{len(welding_positions)}个")
            
            # 开始循环演示25个焊钉
            for i in range(25):
                print(f"\n--- 处理第 {i+1} 个焊钉 ---")
                
                # 1. 先移动到预取钉位置
                print(f"移动到第 {i+1} 个钉子的预取钉位置...")
                prepick_pos = prepick_positions[i]
                if isinstance(prepick_pos, str):
                    prepick_pos = json.loads(prepick_pos)
                    
                move_prepick_result = await self.session.call_tool("Rob_movej_2", {"tcp_pos": prepick_pos})
                move_prepick_text = move_prepick_result.content[0].text if move_prepick_result.content else "移动失败"
                print(f"移动到预取钉位置结果: {move_prepick_text}")
                
                if "失败" in move_prepick_text or not move_prepick_text:
                    print(f"移动到第 {i+1} 个钉子的预取钉位置失败，跳过此钉")
                    continue
                
                # 2. 移动到取钉位置
                print(f"移动到第 {i+1} 个钉子的取钉位置...")
                pick_pos = pick_positions[i]
                if isinstance(pick_pos, str):
                    pick_pos = json.loads(pick_pos)
                    
                move_pick_result = await self.session.call_tool("Rob_movel", {"tcp_pose": pick_pos})
                move_pick_text = move_pick_result.content[0].text if move_pick_result.content else "移动失败"
                print(f"移动到取钉位置结果: {move_pick_text}")
                
                if "失败" in move_pick_text or not move_pick_text:
                    print(f"移动到第 {i+1} 个钉子的取钉位置失败，跳过此钉")
                    continue
                
                # 3. 利用movetcp向上移动z+100mm
                print("向上移动100mm...")
                move_up_result = await self.session.call_tool("Rob_movetcp", {"offset": [0, 0, -0.2, 0, 0, 0]})
                move_up_text = move_up_result.content[0].text if move_up_result.content else "移动失败"
                print(f"向上移动结果: {move_up_result}")
                
                if "失败" in move_up_text or not move_up_text:
                    print(f"向上移动失败，跳过此钉")
                    continue
                
                # 4. 移动到示教焊钉位置1
                print(f"移动到第 {i+1} 个焊钉位置...")
                weld_pos = welding_positions[i]
                if isinstance(weld_pos, str):
                    weld_pos = json.loads(weld_pos)
                    
                move_weld_result = await self.session.call_tool("Rob_movej_2", {"tcp_pos": weld_pos})
                move_weld_text = move_weld_result.content[0].text if move_weld_result.content else "移动失败"
                print(f"移动到焊钉位置结果: {move_weld_text}")
                
                if "失败" in move_weld_text or not move_weld_text:
                    print(f"移动到第 {i+1} 个焊钉位置失败，跳过此钉")
                    continue
                
                # 5. 开始焊钉演示
                print("开始焊钉演示...")
                await self.test_hanqiang()
                
                print(f"第 {i+1} 个焊钉处理完成")
            
            print("\n=== 25个焊钉连续演示完成 ===")
            return True
            
        except Exception as e:
            print(f"连续焊钉演示出错: {e}")
            import traceback
            traceback.print_exc()
            return False

#region 测试预取钉取钉

    async def ceshi(self):
        """
        测试点位是否正确
        """
        global robot_connected
        
        print("=== 测试点位 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法进行测试")
                return False
                
            # 读取预取钉和取钉位置
            import os
            import json
            
            # 构建文件路径
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "calibration")
            nail_positions_file = os.path.join(config_dir, "nail_positions_data.json")
            
            # 读取取钉和预取钉位置
            if not os.path.exists(nail_positions_file):
                print("未找到取钉位置文件，请先执行示教取钉位置")
                return False
                
            with open(nail_positions_file, 'r', encoding='utf-8') as f:
                nail_data = json.load(f)
                
            pick_positions = nail_data.get("pick_positions", [])
            prepick_positions = nail_data.get("prepick_positions", [])
            
            # 合并位置到一个列表中（预取钉位置和取钉位置交替）
            all_positions = []
            for i in range(min(len(pick_positions), len(prepick_positions))):
                all_positions.append(("预取钉", prepick_positions[i]))
                all_positions.append(("取钉", pick_positions[i]))
            
            # 检查数据完整性
            if len(all_positions) < 50:
                print(f"位置数据不完整: 总共只有 {len(all_positions)} 个位置")
                return False
            
            print(f"成功加载 {len(all_positions)} 个位置点")
            print("输入数字以移动到对应位置，输入 'quit' 退出")
            print("位置点说明: 奇数点为预取钉位置，偶数点为取钉位置")
            
            # 循环处理用户输入
            while True:
                user_input = input(f"\n请输入位置编号 (1-{len(all_positions)}) 或 '0' 退出: ").strip()
                
                if user_input.lower() == '0':
                    print("退出测试点位功能")
                    break
                
                try:
                    index = int(user_input)
                    if index < 1 or index > len(all_positions):
                        print(f"位置编号超出范围，请输入 1 到 {len(all_positions)} 之间的数字")
                        continue
                    
                    # 获取位置信息
                    pos_type, position = all_positions[index-1]
                    if isinstance(position, str):
                        position = json.loads(position)
                    
                    print(f"移动到第 {index} 个位置 ({pos_type}位置)...")
                    
                    # 移动到指定位置
                    move_result = await self.session.call_tool("Rob_movel", {"tcp_pose": position})
                    move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                    print(f"移动结果: {move_result_text}")
                    
                    if "失败" in move_result_text or not move_result_text:
                        print("移动失败，请检查位置数据和机器人状态")
                        continue
                        
                    print(f"成功移动到第 {index} 个位置 ({pos_type})")
                    
                except ValueError:
                    print("无效输入，请输入数字或 'quit'")
                except Exception as e:
                    print(f"移动过程中出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            return True
            
        except Exception as e:
            print(f"测试点位时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_move_to_welding_positions(self):
        """
        测试移动到示教焊钉位置
        """
        global robot_connected
        
        print("=== 测试移动到示教焊钉位置 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法进行测试")
                return False
                
            # 读取焊钉位置
            import os
            import json
            
            # 构建文件路径
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "calibration")
            welding_positions_file = os.path.join(config_dir, "welding_nail_positions_data.json")
            
            # 读取焊钉位置
            if not os.path.exists(welding_positions_file):
                print("未找到焊钉位置文件，请先执行示教焊钉位置")
                return False
                
            with open(welding_positions_file, 'r', encoding='utf-8') as f:
                welding_data = json.load(f)
                
            welding_positions = welding_data.get("welding_nail_positions", [])
            
            # 检查数据完整性
            if len(welding_positions) < 25:
                print(f"焊钉位置数据不完整: 总共只有 {len(welding_positions)} 个位置")
                return False
            
            print(f"成功加载 {len(welding_positions)} 个焊钉位置点")
            print("输入数字以移动到对应焊钉位置，输入 'quit' 退出")
            
            # 循环处理用户输入
            while True:
                user_input = input(f"\n请输入焊钉位置编号 (1-{len(welding_positions)}) 或 'quit' 退出: ").strip()
                
                if user_input.lower() == 'quit':
                    print("退出测试焊钉位置功能")
                    break
                
                try:
                    index = int(user_input)
                    if index < 1 or index > len(welding_positions):
                        print(f"位置编号超出范围，请输入 1 到 {len(welding_positions)} 之间的数字")
                        continue
                    
                    # 获取位置信息
                    position = welding_positions[index-1]
                    if isinstance(position, str):
                        position = json.loads(position)
                    
                    print(f"移动到第 {index} 个焊钉位置...")
                    
                    # 移动到指定焊钉位置
                    move_result = await self.session.call_tool("Rob_movej_2", {"tcp_pose": position})
                    move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                    print(f"移动结果: {move_result_text}")
                    
                    if "失败" in move_result_text or not move_result_text:
                        print("移动失败，请检查位置数据和机器人状态")
                        continue
                        
                    print(f"成功移动到第 {index} 个焊钉位置")
                    
                except ValueError:
                    print("无效输入，请输入数字或 'quit'")
                except Exception as e:
                    print(f"移动过程中出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            return True
            
            
        except Exception as e:
            print(f"测试移动到焊钉位置时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    async def tcp_jog_control(self):
        """
        TCP点动控制功能
        输入1为movetcp x+50mm，2为x-50mm，3为y+50mm，4为y-50mm，0为退出
        """
        print("=== TCP点动控制 ===")
        print("1. X+50mm  2. X-50mm  3. Y+50mm  4. Y-50mm  0. 退出")
        
        while True:
            choice = input("请选择移动方向: ").strip()
            
            if choice == "0":
                print("退出TCP点动控制")
                break
            elif choice == "1":
                # X+50mm
                move_command = "movetcp 0.03 0 0 0 0 0"
                print(f"执行移动命令: {move_command}")
                await self.test_move_command(move_command)
            elif choice == "2":
                # X-50mm
                move_command = "movetcp -0.03 0 0 0 0 0"
                print(f"执行移动命令: {move_command}")
                await self.test_move_command(move_command)
            elif choice == "3":
                # Y+50mm
                move_command = "movetcp 0 0.03 0 0 0 0"
                print(f"执行移动命令: {move_command}")
                await self.test_move_command(move_command)
            elif choice == "4":
                # Y-50mm
                move_command = "movetcp 0 -0.03 0 0 0 0"
                print(f"执行移动命令: {move_command}")
                await self.test_move_command(move_command)
            elif choice =="5":
                # Y-50mm
                move_command = "movetcp -0.097 0.064 0 0 0 0"
                print(f"执行移动命令: {move_command}")
                await self.test_move_command(move_command)
            else:
                print("无效选择，请输入0-4之间的数字")

    async def tools(self):
        """
        电机工具开、关
        """
        print("=== 电机工具控制 ===")
                # 连接电机控制器（如果尚未连接）
        print("检查电机控制器连接状态...")
        connect_result = await self.session.call_tool("Io_connect_motor", {})
        connect_result_text = connect_result.content[0].text if connect_result.content else "连接检查失败"
        print(f"连接状态: {connect_result_text}")
        
        if "失败" in connect_result_text:
            print("无法连接到电机控制器，无法控制电机")
            return False
        while True:
            choice = input("请选择工具开关: (1:开/  2:关/   0:退出到主菜单)").strip()
            
            if choice == "0":
                print("退出")
                break
            elif choice == "1":
                # 电机工具开
                print("电机工具开...")
                motor_forward_result = await self.session.call_tool("Io_set_tool_state", {"state": True})
                motor_forward_text = motor_forward_result.content[0].text if motor_forward_result.content else "操作失败"
                print(f"电机开关结果: {motor_forward_text}")
                if "失败" in motor_forward_text or not motor_forward_text:
                    print("电机工具开启失败")
                    return False
            elif choice == "2":
                # 电机工具关
                print("电机工具关...")
                motor_forward_result = await self.session.call_tool("Io_set_tool_state", {"state": False})
                motor_forward_text = motor_forward_result.content[0].text if motor_forward_result.content else "操作失败"
                print(f"电机开关结果: {motor_forward_text}")
                if "失败" in motor_forward_text or not motor_forward_text:
                    print("电机工具关闭失败")
                    return False

    async def test_move_to_welding_positions(self):
        """
        角度调平2
        """
        global robot_connected
        
        print("=== 测试移动到焊钉位置 ===")
        # 确保机器人已连接
        if not robot_connected:
            print("机器人未连接，无法进行测试")
            return False
            
        # 设定预设的姿态值
        p = [1, 1, 1]

        # 获取当前机器人位置
        current_pos_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
        current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"

        if "失败" not in current_pos_text and current_pos_text:
            try:
                # 解析当前位置
                import json
                current_pos = json.loads(current_pos_text)
                
                # 创建新位置：保留xyz，替换rx ry rz
                new_position = [
                    current_pos[0],  # x
                    current_pos[1],  # y
                    current_pos[2],  # z
                    p[0],            # rx (来自预设值)
                    p[1],            # ry (来自预设值)
                    p[2]              # rz (来自预设值)
                ]
                
                # 移动到新位置
                move_result = await self.session.call_tool("Rob_movel", {"tcp_pose": new_position})
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动结果: {move_result_text}")
                
            except json.JSONDecodeError:
                print("解析位置数据失败")
            except Exception as e:
                print(f"执行过程中出错: {e}")
        else:
            print("获取当前位置失败")
#region 位置调整
    async def position_adjustment(self):
        """
        测试位置调整流程
        """
        global robot_connected, vision_connected, is_tool_set
        start_time = time.time()
        print("=== 测试十字交叉点调整流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            max_steps = 5  # 最大调整步数
            adjustment_completed = False
            current_pos_result = await self.session.call_tool("Rob_get_current_joint_pos", {})
            current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
            if "失败" in current_pos_text or not current_pos_text:
                print("获取当前关节位置失败，无法进行调整")
                return False
            
            # 解析当前位置
            import json
            try:
                current_pos = json.loads(current_pos_text)
                # 修改第6个元素（索引5）
                current_pos[5] = 0
            except json.JSONDecodeError:
                print("解析关节位置数据失败")
                return False
            except IndexError:
                print("关节位置数据长度不足，无法修改第6个元素")
                return False
            
            move_result = await self.session.call_tool("Rob_movej", {
                    "joint_angles": current_pos
                })
            for step in range(1, max_steps + 1):
                print(f"\n--- 位置调整步骤 {step} ---")
                await asyncio.sleep(2)  # 等待机器人移动完成
                # 获取十字交叉点像素坐标
                print("获取十字交叉点像素坐标...")
                start_step_time = time.time()
                screw_points_result = await self.session.call_tool("Cam_get_cross_points", {})
                screw_points_text = screw_points_result.content[0].text if screw_points_result.content else "获取失败"
                print(f"获取十字交叉点像素坐标结果: {screw_points_text}")
                end_time_step = time.time()
                print(f"获取十字交叉点像素坐标耗时: {end_time_step - start_step_time:.2f} 秒")
                # 解析十字交叉点坐标
                try:
                    screw_point = json.loads(screw_points_text)
                    # 如果是列表且有元素，取第一个点
                    if isinstance(screw_point, list) and len(screw_point) > 0:
                        if isinstance(screw_point[0], list):
                            screw_point = screw_point[0]
                        else:
                            screw_point = screw_point
                    print(f"十字交叉点坐标: {screw_point}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    screw_point = screw_points_text
                    print(f"十字交叉点坐标: {screw_point}")
                
                # 检查是否获取到十字交叉点坐标
                if not screw_point:
                    print("未能获取十字交叉点坐标，跳过本次调整")
                    continue
                
                # 判断是否完成调整
                print("判断是否完成位置调整...")
                estimate_result = await self.session.call_tool("Alg_position_adjust_estimate", {"pos": screw_point})
                estimate_result_text = estimate_result.content[0].text if estimate_result.content else "判断失败"
                print(f"判断调整状态结果: {estimate_result_text}")
                
                # 如果完成调整则退出循环
                if "是" in str(estimate_result_text):
                    print("位置调整完成")
                    adjustment_completed = True
                    break
                
                # 计算移动偏移量
                print("计算移动偏移量...")
                offset_result = await self.session.call_tool("Alg_position_adjust", {"pos": screw_point})
                offset_result_text = offset_result.content[0].text if offset_result.content else "计算失败"
                print(f"计算移动偏移量结果: {offset_result_text}")
                
                # 解析偏移量
                try:
                    offset_value = json.loads(offset_result_text)
                    print(f"解析后的偏移量: {offset_value}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用文本
                    offset_value = offset_result_text
                    print(f"偏移量: {offset_value}")
                
                # 检查是否获取到偏移量
                if not offset_value:
                    print("未能计算出移动偏移量，跳过本次调整")
                    continue
                    
                # 移动机器人
                print(f"移动机器人，偏移量: {offset_value}")
                move_result = await self.session.call_tool("Rob_movetcp", {"offset": offset_value})
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动机器人结果: {move_result_text}")
                await asyncio.sleep(5)  # 等待机器人移动完成
            end_time= time.time()
            print(f"位置调整总耗时: {end_time - start_time:.2f} 秒")
            if adjustment_completed:
                print("位置调整流程测试完成")
                return True
            else:
                print(f"位置调整流程测试未完成，达到最大调整步数 {max_steps}")
                return False
            
        except Exception as e:
            print(f"测试位置调整流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 位置标定
    async def position_calibration(self):
        """
        测试位置标定流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试位置标定流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False

            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False
            
            # 获取偏移量
            print("获取偏移量信息...")
            offset_result = await self.session.call_tool("Alg_get_offset_info", {})
            offset_result_text = offset_result.content[0].text if offset_result.content else "{}"
            print(f"获取偏移量结果: {offset_result_text}")
            
            # 解析偏移量结果
            import json
            try:
                offset_result_dict = json.loads(offset_result_text) if offset_result_text else {}
            except json.JSONDecodeError:
                print("解析偏移量失败，无法继续标定流程")
                return False
                
            # 提取偏移量
            offset1 = offset_result_dict.get("offset1", [0, 0, 0, 0, 0, 0])
            offset2 = offset_result_dict.get("offset2", [0, 0, 0, 0, 0, 0])
            offset3 = offset_result_dict.get("offset3", [0, 0, 0, 0, 0, 0])
            
            # 记录标定点数据
            first_image_point = None
            first_robot_point = None
            second_image_point = None
            second_robot_point = None
            third_robot_point = None
            
            # 移动到标定位置1
            print(f"移动到标定位置1，偏移量: {offset1}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset1})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置1结果: {result_text}")
            await asyncio.sleep(2)

            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            first_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            first_robot_point_text = first_robot_point_result.content[0].text if first_robot_point_result.content else "获取失败"
            print(f"当前机器人TCP位置结果: {first_robot_point_text}")
            
            # 解析机器人位置
            try:
                first_robot_point = json.loads(first_robot_point_text)
                print(f"第一标定点机器人位置: {first_robot_point}")
            except json.JSONDecodeError:
                first_robot_point = first_robot_point_text
                print(f"第一标定点机器人位置: {first_robot_point}")
            await asyncio.sleep(7)
            # 获取十字交叉点像素坐标
            print("获取十字交叉点像素坐标...")
            screw_points_result1 = await self.session.call_tool("Cam_get_cross_points", {})
            screw_points_result1_text = screw_points_result1.content[0].text if screw_points_result1.content else "获取失败"
            print(f"获取十字交叉点像素坐标结果: {screw_points_result1_text}")
            
            # 解析十字交叉点坐标
            try:
                first_image_point = json.loads(screw_points_result1_text)
                # 如果是列表且有元素，取第一个点
                if isinstance(first_image_point, list) and len(first_image_point) > 0:
                    if isinstance(first_image_point[0], list):
                        first_image_point = first_image_point[0]
                    print(f"第一标定点图像坐标: {first_image_point}")
            except json.JSONDecodeError:
                first_image_point = screw_points_result1_text
                print(f"第一标定点图像坐标: {first_image_point}")
            
            # 移动到标定位置2
            print(f"移动到标定位置2，偏移量: {offset2}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset2})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置2结果: {result_text}")
            await asyncio.sleep(2)

            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            second_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            second_robot_point_text = second_robot_point_result.content[0].text if second_robot_point_result.content else "获取失败"
            print(f"当前机器人TCP位置结果: {second_robot_point_text}")
            
            # 解析机器人位置
            try:
                second_robot_point = json.loads(second_robot_point_text)
                print(f"第二标定点机器人位置: {second_robot_point}")
            except json.JSONDecodeError:
                second_robot_point = second_robot_point_text
                print(f"第二标定点机器人位置: {second_robot_point}")
            await asyncio.sleep(7)

            # 获取十字交叉点像素坐标
            print("获取十字交叉点像素坐标...")
            screw_points_result2 = await self.session.call_tool("Cam_get_cross_points", {})
            screw_points_result2_text = screw_points_result2.content[0].text if screw_points_result2.content else "获取失败"
            print(f"获取十字交叉点像素坐标结果: {screw_points_result2_text}")
            
            # 解析十字交叉点坐标
            try:
                second_image_point = json.loads(screw_points_result2_text)
                # 如果是列表且有元素，取第一个点
                if isinstance(second_image_point, list) and len(second_image_point) > 0:
                    if isinstance(second_image_point[0], list):
                        second_image_point = second_image_point[0]
                    print(f"第二标定点图像坐标: {second_image_point}")
            except json.JSONDecodeError:
                second_image_point = screw_points_result2_text
                print(f"第二标定点图像坐标: {second_image_point}")
            
            # 移动到标定位置3
            print(f"移动到标定位置3，偏移量: {offset3}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset3})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置3结果: {result_text}")
            
            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            third_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            third_robot_point_text = third_robot_point_result.content[0].text if third_robot_point_result.content else "获取失败"
            print(f"当前机器人TCP位置结果: {third_robot_point_text}")
            
            # 解析机器人位置
            try:
                third_robot_point = json.loads(third_robot_point_text)
                print(f"第三标定点机器人位置: {third_robot_point}")
            except json.JSONDecodeError:
                third_robot_point = third_robot_point_text
                print(f"第三标定点机器人位置: {third_robot_point}")
            
            # 检查所有必需的数据是否都已获取
            if not all([first_image_point, first_robot_point, second_image_point, 
                        second_robot_point, third_robot_point]):
                print("未能获取所有必需的标定数据，无法执行标定")
                return False
            
            # 执行位置标定
            print("执行位置标定...")
            print(f"标定点数据:")
            print(f"  first_image_point: {first_image_point}")
            print(f"  second_image_point: {second_image_point}")
            print(f"  first_robot_point: {first_robot_point}")
            print(f"  second_robot_point: {second_robot_point}")
            print(f"  third_robot_point: {third_robot_point}")
            
            # 调用标定算法（实际参数可能需要根据工具定义调整）
            calibration_result = await self.session.call_tool("Alg_position_calibration", {
                "first_image_point": first_image_point,
                "second_image_point": second_image_point,
                "first_robot_point": first_robot_point,
                "second_robot_point": second_robot_point,
                "third_robot_point": third_robot_point
            })
            calibration_result_text = calibration_result.content[0].text if calibration_result.content else "标定失败"
            print(f"位置标定结果: {calibration_result_text}")
            
            print("位置标定流程测试完成")
            return True
            
        except Exception as e:
            print(f"测试位置标定流程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_cross(self):
        print("获取十字交叉点...")
        normal_vector_result = await self.session.call_tool("Cam_get_cross_points", {})
        normal_vector_text = normal_vector_result.content[0].text if normal_vector_result.content else "获取失败"
        print(f"获取十字交叉点结果: {normal_vector_text}")
        return 
    

#region 保存位姿
    async def save_current_joint_pose(self, joint_point_name: str):
        """
        保存当前机器人位姿
        """
        global robot_connected
        
        print(f"=== 保存当前位姿 ===")
        
        try:
            # 确保机器人已连接
            if not robot_connected:
                print("机器人未连接，无法保存位姿")
                return False
                
            # 获取当前机器人TCP位置
            print("获取当前机器人TCP位置...")
            current_pos_result = await self.session.call_tool("Rob_get_current_joint_pos", {})
            current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
            print(f"当前机器人TCP位置: {current_pos_text}")
            
            if "失败" in current_pos_text or not current_pos_text:
                print("获取机器人位置失败，无法保存位姿")
                return False
                
            # 解析位置数据
            import json
            try:
                current_pos = json.loads(current_pos_text)
                print(f"解析后的位置数据: {current_pos}")
            except json.JSONDecodeError:
                current_pos = current_pos_text
                print(f"位置数据: {current_pos}")
                
            # 保存位置数据
            print(f"保存位姿 '{joint_point_name}'...")
            save_result = await self.session.call_tool("Alg_record_joint_point", {
                "joint_point_name": joint_point_name,
                "robot_position": current_pos
            })
            save_result_text = save_result.content[0].text if save_result.content else "保存失败"
            print(f"保存结果: {save_result_text}")
            
            if "失败" in save_result_text or not save_result_text:
                print("保存位姿失败")
                return False
                
            print(f"成功保存位姿 '{joint_point_name}'")
            return True
            
        except Exception as e:
            print(f"保存当前位姿时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    #region 移动到已保存的位姿
    async def move_to_saved_joint_pose(self):
        """
        移动到已保存的位姿
        """
        global robot_connected
        
        print("=== 移动到保存位姿 ===")
        
        while True:
            try:
                # 确保机器人已连接
                if not robot_connected:
                    print("机器人未连接，无法移动")
                    return False
                    
                # 获取所有保存的点位
                print("获取已保存的位姿列表...")
                joint_points_result = await self.session.call_tool("Alg_get_recorded_joint_point", {})
                joint_points_text = joint_points_result.content[0].text if joint_points_result.content else "获取失败"
                print(f"已保存的位姿: {joint_points_text}")
                
                if "失败" in joint_points_text or not joint_points_text:
                    print("获取保存位姿失败")
                    return False
                    
                # 解析点位数据
                import json
                try:
                    joint_points_data = json.loads(joint_points_text)
                    if not isinstance(joint_points_data, dict):
                        print("点位数据格式错误")
                        return False
                        
                    if not joint_points_data:
                        print("没有保存的位姿")
                        return False
                        
                    print("可用的位姿:")
                    for i, (name, pos) in enumerate(joint_points_data.items(), 1):
                        print(f"  {i}. {name}: {pos}")
                    print("  0. 退出")
                        
                except json.JSONDecodeError:
                    print("解析点位数据失败")
                    return False
                    
                # 让用户选择一个点位
                try:
                    choice = input("请选择要移动到位姿的编号 (输入0退出): ").strip()
                    
                    # 检查是否为退出
                    if choice == "0":
                        print("退出移动到保存位姿功能")
                        return True
                    
                    choice = int(choice)
                    if choice < 1 or choice > len(joint_points_data):
                        print("无效选择")
                        continue
                        
                    # 获取选中的点位
                    joint_point_name = list(joint_points_data.keys())[choice - 1]
                    target_position = joint_points_data[joint_point_name]
                    print(f"选择位姿: {joint_point_name}")
                    print(f"目标位置: {target_position}")
                    
                except (ValueError, IndexError):
                    print("选择无效")
                    continue
                except KeyboardInterrupt:
                    print("用户取消操作")
                    return False
                    
                # 移动到指定位置
                print(f"移动到 '{joint_point_name}'...")
                move_result = await self.session.call_tool("Rob_movej", {
                    "joint_angles": target_position
                })
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动结果: {move_result_text}")
                
                if "失败" in move_result_text or not move_result_text:
                    print("移动失败")
                    continue
                    
                print("成功移动到指定位置")
                
            except Exception as e:
                print(f"移动到保存位姿时出错: {e}")
                import traceback
                traceback.print_exc()
                continue
    async def cross_points_adjust(self):
        """
        获取十字交叉点并进行位置调整
        """
        print("=== 获取十字交叉点并进行位置调整 ===")
        global robot_connected
        start_time = time.time()
        await self.test_angle_adjustment()
        current_pos_result = await self.session.call_tool("Rob_get_current_joint_pos", {})
        current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
        current_pos_text= json.loads(current_pos_text)
        current_pos_text[5] = 1.5708137800874167
        move_result = await self.session.call_tool("Rob_movej", {
                "joint_angles": current_pos_text
            })
        await self.test_depth_adjustment()
        await self.test_angle_adjustment()
        current_pos_result = await self.session.call_tool("Rob_get_current_joint_pos", {})
        current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
        current_pos_text= json.loads(current_pos_text)
        current_pos_text[5] = 1.5708137800874167
        move_result = await self.session.call_tool("Rob_movej", {
                "joint_angles": current_pos_text
            })
        await self.test_depth_adjustment()
        result = await self.session.call_tool("Rob_movetcp", {"offset": [0, 0, 0.18, 0, 0, 0]})
        await self.position_adjustment()
        result = await self.session.call_tool("Rob_movetcp", {"offset": [0.09,0.02,0.1, 0, 0, 0]})
        end_time = time.time()
        print(f"十字交叉点调整总耗时: {end_time - start_time:.2f} 秒")
        return True
#region 板角度调整
    async def board_angle_adjust(self):
        """
        板角度调整，最大 5 步，当需调整角度小于 0.2 度时结束
        """
        global robot_connected, vision_connected
        
        print("=== 板角度调整流程 ===")
        start_time = time.time()
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            max_steps = 5  # 最大调整步数
            angle_threshold = 0.004  # 角度阈值（度）
            adjustment_completed = False
            
            for step in range(1, max_steps + 1):
                print(f"\n--- 板角度调整步骤 {step}/{max_steps} ---")
                
                # 获取当前角度
                print("获取板角度...")
                start_step_time = time.time()
                angle_adjust_result = await self.session.call_tool("Cam_get_board_angle", {})
                angle_adjust_text = angle_adjust_result.content[0].text if angle_adjust_result.content else "获取失败"
                print(f"获取角度结果：{angle_adjust_text}")
                
                # 检查是否获取到有效数据
                if not angle_adjust_text or angle_adjust_text == "获取失败":
                    print("未能获取到角度数据，跳过本次调整")
                    continue
                
                import json
                try:
                    angle_adjust = float(json.loads(angle_adjust_text))
                    print(f"当前需要调整的角度：{angle_adjust:.4f} 度")
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"解析角度数据失败：{e}")
                    print(f"原始数据：{angle_adjust_text}")
                    continue
                
                # 判断是否需要继续调整
                if abs(angle_adjust) < angle_threshold:
                    print(f"角度调整完成（当前角度偏差 {abs(angle_adjust):.4f} < 阈值 {angle_threshold}）")
                    adjustment_completed = True
                    break
                
                # 获取当前关节位置
                print("获取当前关节位置...")
                current_pos_result = await self.session.call_tool("Rob_get_current_joint_pos", {})
                current_pos_text = current_pos_result.content[0].text if current_pos_result.content else "获取失败"
                
                if "失败" in current_pos_text or not current_pos_text:
                    print("获取当前关节位置失败，无法进行调整")
                    continue
                
                # 解析当前位置并修改第 6 个元素（索引 5）
                try:
                    current_pos = json.loads(current_pos_text)
                    current_pos[5] += angle_adjust
                    print(f"调整后的关节位置：{current_pos}")
                except json.JSONDecodeError:
                    print("解析关节位置数据失败")
                    continue
                except IndexError:
                    print("关节位置数据长度不足，无法修改第 6 个元素")
                    continue
                
                # 移动机器人
                print(f"执行关节移动，调整角度：{angle_adjust:.4f} 度")
                move_result = await self.session.call_tool("Rob_movej", {
                    "joint_angles": current_pos
                })
                move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                print(f"移动结果：{move_result_text}")
                
                # 等待机器人移动完成
                await asyncio.sleep(3)
                
                end_step_time = time.time()
                print(f"单步调整耗时：{end_step_time - start_step_time:.2f} 秒")
            
            end_time = time.time()
            print(f"\n板角度调整总耗时：{end_time - start_time:.2f} 秒")
            
            if adjustment_completed:
                print("板角度调整流程测试完成（达到精度要求）")
                return True
            else:
                print(f"板角度调整流程测试未完成，达到最大调整步数 {max_steps}")
                return False
            
        except Exception as e:
            print(f"板角度调整流程出错：{e}")
            import traceback
            traceback.print_exc()
            return False



    #region 板中心调整
    async def board_center_adjustment(self):
        """
        测试板中心调整流程
        """
        global robot_connected, vision_connected, is_tool_set
        start_time = time.time()
        print("=== 测试板中心调整流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False

            max_steps = 5  # 最大调整步数
            adjustment_completed = False
            
            for step in range(1, max_steps + 1):
                print(f"\n--- 板中心调整步骤 {step} ---")
                try:
                    await asyncio.sleep(1)  # 等待机器人移动完成
                    await self.board_angle_adjust()  # 每次位置调整前进行一次角度调整
                except asyncio.CancelledError:
                    print("等待被取消")
                    raise
                except Exception as e:
                    print(f"等待时出错：{e}")
                    continue
                    
                # 获取板中心点坐标
                print("获取板中心点坐标...")
                start_step_time = time.time()
                try:
                    board_center_result = await asyncio.wait_for(
                        self.session.call_tool("Cam_get_board_center", {}),
                        timeout=30.0  # 设置 30 秒超时
                    )
                except asyncio.TimeoutError:
                    print("获取板中心点坐标超时")
                    continue
                except asyncio.CancelledError:
                    print("获取板中心点坐标被取消")
                    raise
                except Exception as e:
                    print(f"调用 Cam_get_board_center 失败：{type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                board_center_text = board_center_result.content[0].text if board_center_result.content else "获取失败"
                print(f"获取板中心点坐标结果：{board_center_text}")
                end_time_step = time.time()
                print(f"获取板中心点坐标耗时：{end_time_step - start_step_time:.2f} 秒")
                
                # 解析板中心点坐标
                try:
                    board_center = json.loads(board_center_text)
                    # 如果是列表且有元素，取第一个点
                    if isinstance(board_center, list) and len(board_center) > 0:
                        if isinstance(board_center[0], list):
                            board_center = board_center[0]
                        else:
                            board_center = board_center
                    print(f"板中心点坐标：{board_center}")
                except json.JSONDecodeError:
                    # 如果不是 JSON 格式，直接使用文本
                    board_center = board_center_text
                    print(f"板中心点坐标：{board_center}")
                
                # 检查是否获取到板中心点坐标
                if not board_center:
                    print("未能获取板中心点坐标，跳过本次调整")
                    continue
                
                # 判断是否完成调整
                print("判断是否完成位置调整...")
                try:
                    estimate_result = await asyncio.wait_for(
                        self.session.call_tool("Alg_position_adjust_estimate", {"pos": board_center}),
                        timeout=30.0
                    )
                    estimate_result_text = estimate_result.content[0].text if estimate_result.content else "判断失败"
                    print(f"判断调整状态结果：{estimate_result_text}")
                except asyncio.TimeoutError:
                    print("判断调整状态超时")
                    continue
                except Exception as e:
                    print(f"判断调整状态失败：{type(e).__name__}: {e}")
                    continue
                
                # 如果完成调整则退出循环
                if "是" in str(estimate_result_text):
                    print("板中心调整完成")
                    adjustment_completed = True
                    break
                
                # 计算移动偏移量
                print("计算移动偏移量...")
                try:
                    offset_result = await asyncio.wait_for(
                        self.session.call_tool("Alg_position_adjust", {"pos": board_center}),
                        timeout=30.0
                    )
                    offset_result_text = offset_result.content[0].text if offset_result.content else "计算失败"
                    print(f"计算移动偏移量结果：{offset_result_text}")
                except asyncio.TimeoutError:
                    print("计算移动偏移量超时")
                    continue
                except Exception as e:
                    print(f"计算移动偏移量失败：{type(e).__name__}: {e}")
                    continue
                
                # 解析偏移量
                try:
                    offset_value = json.loads(offset_result_text)
                    print(f"解析后的偏移量：{offset_value}")
                except json.JSONDecodeError:
                    # 如果不是 JSON 格式，直接使用文本
                    offset_value = offset_result_text
                    print(f"偏移量：{offset_value}")
                
                # 检查是否获取到偏移量
                if not offset_value:
                    print("未能计算出移动偏移量，跳过本次调整")
                    continue
                    
                # 移动机器人
                print(f"移动机器人，偏移量：{offset_value}")
                try:
                    move_result = await asyncio.wait_for(
                        self.session.call_tool("Rob_movetcp", {"offset": offset_value}),
                        timeout=60.0  # 移动操作可能需要更长时间
                    )
                    move_result_text = move_result.content[0].text if move_result.content else "移动失败"
                    print(f"移动机器人结果：{move_result_text}")
                except asyncio.TimeoutError:
                    print("移动机器人超时")
                    continue
                except asyncio.CancelledError:
                    print("移动机器人被取消")
                    raise
                except Exception as e:
                    print(f"移动机器人失败：{type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                await asyncio.sleep(1)  # 等待机器人移动完成
            end_time= time.time()
            print(f"板中心调整总耗时：{end_time - start_time:.2f} 秒")
            if adjustment_completed:
                print("板中心调整流程测试完成")
                return True
            else:
                print(f"板中心调整流程测试未完成，达到最大调整步数 {max_steps}")
                return False
            
        except asyncio.CancelledError:
            print("板中心调整流程被取消")
            return False
        except Exception as e:
            print(f"测试板中心调整流程时出错：{type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    #region 板中心标定
    async def board_center_calibration(self):
        """
        测试板中心标定流程
        """
        global robot_connected, vision_connected, is_tool_set
        
        print("=== 测试板中心标定流程 ===")
        
        try:
            # 确保机器人和视觉已连接
            if not robot_connected:
                print("机器人未连接，跳过测试")
                return False
                    
            if not vision_connected:
                print("视觉未连接，跳过测试")
                return False
            
            if not is_tool_set:
                print("未选择工具，跳过测试")
                return False
            
            # 获取偏移量
            print("获取偏移量信息...")
            offset_result = await self.session.call_tool("Alg_get_offset_info", {})
            offset_result_text = offset_result.content[0].text if offset_result.content else "{}"
            print(f"获取偏移量结果：{offset_result_text}")
            
            # 解析偏移量
            import json
            try:
                offsets = json.loads(offset_result_text)
                offset1 = offsets.get("offset1", [0, 0, 0.02, 0, 0, 0])
                offset2 = offsets.get("offset2", [0, 0, 0.05, 0, 0, 0])
                offset3 = offsets.get("offset3", [0, 0, 0.08, 0, 0, 0])
                print(f"解析后的偏移量:")
                print(f"  offset1: {offset1}")
                print(f"  offset2: {offset2}")
                print(f"  offset3: {offset3}")
            except json.JSONDecodeError:
                print("无法解析偏移量，使用默认值")
                offset1 = [0, 0, 0.02, 0, 0, 0]
                offset2 = [0, 0, 0.05, 0, 0, 0]
                offset3 = [0, 0, 0.08, 0, 0, 0]
            
            # 移动到标定位置 1
            print(f"移动到标定位置 1，偏移量：{offset1}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset1})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置 1 结果：{result_text}")
            await asyncio.sleep(5)
            
            # 获取板中心点坐标
            print("获取板中心点坐标...")
            board_center_result1 = await self.session.call_tool("Cam_get_board_center", {})
            board_center_result1_text = board_center_result1.content[0].text if board_center_result1.content else "获取失败"
            print(f"获取板中心点坐标结果：{board_center_result1_text}")
            
            # 解析板中心点坐标
            try:
                first_image_point = json.loads(board_center_result1_text)
                # 如果是列表且有元素，取第一个点
                if isinstance(first_image_point, list) and len(first_image_point) > 0:
                    if isinstance(first_image_point[0], list):
                        first_image_point = first_image_point[0]
                    print(f"第一标定点图像坐标：{first_image_point}")
            except json.JSONDecodeError:
                first_image_point = board_center_result1_text
                print(f"第一标定点图像坐标：{first_image_point}")
            
            # 获取当前机器人 TCP 位置
            print("获取当前机器人 TCP 位置...")
            first_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            first_robot_point_text = first_robot_point_result.content[0].text if first_robot_point_result.content else "获取失败"
            print(f"当前机器人 TCP 位置结果：{first_robot_point_text}")
            
            # 解析机器人位置
            try:
                first_robot_point = json.loads(first_robot_point_text)
                print(f"第一标定点机器人位置：{first_robot_point}")
            except json.JSONDecodeError:
                first_robot_point = first_robot_point_text
                print(f"第一标定点机器人位置：{first_robot_point}")
            await asyncio.sleep(7)
            
            # 移动到标定位置 2
            print(f"移动到标定位置 2，偏移量：{offset2}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset2})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置 2 结果：{result_text}")
            await asyncio.sleep(5)
            
            # 获取板中心点坐标
            print("获取板中心点坐标...")
            board_center_result2 = await self.session.call_tool("Cam_get_board_center", {})
            board_center_result2_text = board_center_result2.content[0].text if board_center_result2.content else "获取失败"
            print(f"获取板中心点坐标结果：{board_center_result2_text}")
            
            # 解析板中心点坐标
            try:
                second_image_point = json.loads(board_center_result2_text)
                # 如果是列表且有元素，取第一个点
                if isinstance(second_image_point, list) and len(second_image_point) > 0:
                    if isinstance(second_image_point[0], list):
                        second_image_point = second_image_point[0]
                    print(f"第二标定点图像坐标：{second_image_point}")
            except json.JSONDecodeError:
                second_image_point = board_center_result2_text
                print(f"第二标定点图像坐标：{second_image_point}")
            
            # 获取当前机器人 TCP 位置
            print("获取当前机器人 TCP 位置...")
            second_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            second_robot_point_text = second_robot_point_result.content[0].text if second_robot_point_result.content else "获取失败"
            print(f"当前机器人 TCP 位置结果：{second_robot_point_text}")
            
            # 解析机器人位置
            try:
                second_robot_point = json.loads(second_robot_point_text)
                print(f"第二标定点机器人位置：{second_robot_point}")
            except json.JSONDecodeError:
                second_robot_point = second_robot_point_text
                print(f"第二标定点机器人位置：{second_robot_point}")
            await asyncio.sleep(7)
            
            # 移动到标定位置 3
            print(f"移动到标定位置 3，偏移量：{offset3}")
            result = await self.session.call_tool("Rob_movetcp", {"offset": offset3})
            result_text = result.content[0].text if result.content else "移动失败"
            print(f"移动到标定位置 3 结果：{result_text}")
            
            # 获取当前机器人 TCP 位置
            print("获取当前机器人 TCP 位置...")
            third_robot_point_result = await self.session.call_tool("Rob_get_current_tcp_pos", {})
            third_robot_point_text = third_robot_point_result.content[0].text if third_robot_point_result.content else "获取失败"
            print(f"当前机器人 TCP 位置结果：{third_robot_point_text}")
            
            # 解析机器人位置
            try:
                third_robot_point = json.loads(third_robot_point_text)
                print(f"第三标定点机器人位置：{third_robot_point}")
            except json.JSONDecodeError:
                third_robot_point = third_robot_point_text
                print(f"第三标定点机器人位置：{third_robot_point}")
            
            # 检查所有必需的数据是否都已获取
            if not all([first_image_point, first_robot_point, second_image_point, 
                        second_robot_point, third_robot_point]):
                print("未能获取所有必需的标定数据，无法执行标定")
                return False
            
            # 执行板中心标定
            print("执行板中心标定...")
            print(f"标定点数据:")
            print(f"  first_image_point: {first_image_point}")
            print(f"  second_image_point: {second_image_point}")
            print(f"  first_robot_point: {first_robot_point}")
            print(f"  second_robot_point: {second_robot_point}")
            print(f"  third_robot_point: {third_robot_point}")
            
            # 调用标定算法（实际参数可能需要根据工具定义调整）
            calibration_result = await self.session.call_tool("Alg_position_calibration", {
                "first_image_point": first_image_point,
                "second_image_point": second_image_point,
                "first_robot_point": first_robot_point,
                "second_robot_point": second_robot_point,
                "third_robot_point": third_robot_point
            })
            calibration_result_text = calibration_result.content[0].text if calibration_result.content else "标定失败"
            print(f"板中心标定结果：{calibration_result_text}")
            
            print("板中心标定流程测试完成")
            return True
            
        except Exception as e:
            print(f"测试板中心标定流程时出错：{e}")
            import traceback
            traceback.print_exc()
            return False
#region 获取六角螺套点
    async def get_u_cross(self):
        print("获取六角螺套点...")
        normal_vector_result = await self.session.call_tool("Cam_get_u_points", {})
        normal_vector_text = normal_vector_result.content[0].text if normal_vector_result.content else "获取失败"
        print(f"获取六角螺套点结果: {normal_vector_text}")
        return 


    #region 交互菜单
    async def interactive_menu(self):
        """
        交互式菜单
        """
        while True:
            print("\n=== MCP工具测试菜单 ===")
            print(" 1. 机器人连接           2. 视觉连接         3. 加载工具")
            print("\n")
            print(" 4. 螺钉标定             5. 角度标定         6. 深度标定")
            print("\n")
            print(" 7. 螺钉调整             8. 角度调整         9. 深度调整")
            print("\n")
            print("10. 拧螺套演示           11. 气夹控制        12. 电机控制")
            print("\n")
            print("13. 移动指令             14.移动到保存位姿    15. 保存位姿")
            print("\n")
            print("16. 拖动示教             17.焊钉演示         18.获取法向量")
            print("\n")
            print("19. 示教取钉位置         20.示教焊钉位置      21.连续焊钉演示")
            print("\n")
            print("22.测试位置              23.移动到焊钉位      24.上下左右移动")
            print("\n")
            print("25.电机工具开关          26.位置标定         27.位置调整   28.获取十字交叉点 ")
            print("\n")
            print("29.关节移动              30.移动到保存的关节位姿        31.十字线调整全流程  ")
            print("\n")
            print("32.板角度调整            33.板中心调整        34.板中心标定  ")
            print("\n")
            print("35.获取六角螺套点            0.退出")
            print("\n")


            choice = input("请选择操作: ").strip()
            
            if choice == "1":
                brand = input("请输入机器人品牌 (ur/duco/dazu, 默认ur): ").strip()
                if not brand:
                    brand = "dazu"
                await self.test_robot_connection(brand)
            elif choice == "2":
                await self.test_vision_connection()
            elif choice == "3":
                tool_name = input("请输入工具名称 (1为焊枪(nail_bumping 2为拧螺套(screw_sleeve, 默认焊枪工具): ").strip()
                if not tool_name:
                    tool_name = "nail_bumping"
                if tool_name=="1":
                    tool_name = "nail_bumping"
                if tool_name=="2":
                    tool_name = "screw_sleeve"

                await self.test_select_tools(tool_name)
            elif choice == "4":
                await self.test_screw_calibration()
            elif choice == "5":
                await self.test_angle_calibration()
            elif choice == "6":
                await self.test_depth_calibration()
            elif choice == "7":
                await self.test_screw_adjustment()
            elif choice == "8":
                await self.test_angle_adjustment()
            elif choice == "9":
                await self.test_depth_adjustment()
            elif choice == "10":
                await self.test_screw_demo()
            elif choice == "13":
                move_command = input("请输入移动命令 (例如: movetcp 0.1 -0.2 0.3 0 3.14 0): ").strip()
                if move_command:
                    await self.test_move_command(move_command)
            elif choice == "15":
                point_name = input("请输入要保存的位姿名称: ").strip()
                if point_name:
                    await self.save_current_pose(point_name)
                else:
                    print("位姿名称不能为空")
            elif choice == "14":
                await self.move_to_saved_pose()
            elif choice == "11":
                await self.pneumatic_gripper_control()
            elif choice == "12":
                await self.motor_control()
            elif choice == "16":
                await self.teach_mode_control()
            elif choice == "17":
                await self.test_hanqiang()
            elif choice == "18":
                await self.get_normal()
            elif choice == "19":
                await self.teach_nail_positions()
            elif choice == "20":
                await self.teach_welding_nail_positions()
            elif choice == "21":
                await self.Welding_Studs_Demonstration()
            elif choice == "22":
                await self.ceshi()
            elif choice == "23":
                await self.test_move_to_welding_positions()
            elif choice == "24":
                await self.tcp_jog_control()
            elif choice == "25":
                await self.tools()
            elif choice == "26":
                await self.position_calibration()
            elif choice == "27":
                await self.position_adjustment()
            elif choice == "28":
                await self.get_cross()
            elif choice == "29":
                await self.move_to_saved_joint_pose()
            elif choice == "30":
                joint_point_name = input("请输入要保存的位姿名称: ").strip()
                if joint_point_name:
                    await self.save_current_joint_pose(joint_point_name)
                else:
                    print("位姿名称不能为空")
            elif choice == "31":
                await self.cross_points_adjust()
            elif choice == "32":
                await self.board_angle_adjust()
            elif choice == "33":
                await self.board_center_adjustment()
            elif choice == "34":
                await self.board_center_calibration()
            elif choice == "35":
                await self.get_u_cross()
            elif choice == "0":
                print("退出程序")
                break
            else:
                print("无效选择，请重新输入")

    


async def main():
    """主函数：初始化客户端并启动交互"""

    client = MCPClient()
    try:
        # 获取当前文件的绝对路径
        current_file_path = os.path.abspath(__file__)
        # 获取当前文件所在的目录
        current_dir = os.path.dirname(current_file_path)
        # 构建 mcp_server.py 的绝对路径
        server_script_path = os.path.join(current_dir, "mcp_server.py")

        # 连接到MCP服务器（通过IO方式，需指定服务器脚本）
        await client.connect_to_mcp_server_io(server_script_path)

        print("MCP工具测试程序")
        print("此程序可以直接访问现有的MCP工具，用于测试各种功能组合")
        
        # 进入交互式菜单
        await client.interactive_menu()


    finally:    
        # 确保资源释放
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
