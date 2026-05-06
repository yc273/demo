#!/usr/bin/env python3
"""
IO Modules MCP Server Tools
MCP服务器工具，提供IO模块控制功能
"""

import asyncio
import sys, os
from typing import List, Optional

from fastmcp import FastMCP

# Import IO modules
from .io_controller import IoController
from .device_controllers import Liyou

# Configuration
IO_CONTROLLER_IP = "10.10.100.254"
IO_CONTROLLER_PORT = 2317
CONNECT_TIMEOUT = 10

# Global state
io_controller: Optional[IoController] = None
liyou_instance: Optional[Liyou] = None


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger


# IO模块MCP工具函数
def register_io_tools(mcp: FastMCP):
    """注册IO模块相关的MCP工具"""

    #region 电机控制器连接工具
    @mcp.tool()
    async def Io_connect_motor() -> str:
        """连接到电机控制器
        功能：连接电机控制器（默认IP：10.10.100.254:2317）；触发词：连接电机、启动电机控制器、电机连接；参数：无（默认使用配置IP和端口"""
        global io_controller
        try:
            # 若已连接，先关闭旧连接
            if io_controller is not None and io_controller.is_connected:
                await io_controller.close()
                logger.info("已关闭现有电机控制器连接，准备重新连接")

            # 初始化控制器并连接（不使用async with，避免自动关闭）
            io_controller = IoController()
            
            # 带超时的连接
            try:
                await asyncio.wait_for(
                    io_controller.connect_async(IO_CONTROLLER_IP, IO_CONTROLLER_PORT),
                    timeout=CONNECT_TIMEOUT
                )
            except asyncio.TimeoutError:
                return f"连接超时（{CONNECT_TIMEOUT}秒），请检查电机控制器是否在线"

            # 验证连接状态
            if io_controller.is_connected:
                success_msg = f"成功连接到电机控制器 {IO_CONTROLLER_IP}:{IO_CONTROLLER_PORT}"
                logger.info(success_msg)
                return success_msg
            else:
                error_msg = f"连接失败：电机控制器未确认连接，IP={IO_CONTROLLER_IP}:{IO_CONTROLLER_PORT}"
                logger.error(error_msg)
                return error_msg

        except Exception as e:
            error_msg = f"连接电机控制器失败：{str(e)}（IP={IO_CONTROLLER_IP}:{IO_CONTROLLER_PORT}）"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @mcp.tool()
    async def Io_disconnect_motor() -> str:
        """断开与电机控制器的连接
        功能：断开与电机控制器的连接；触发词：断开电机连接、关闭电机控制器、电机断开；参数：无"""
        global io_controller
        try:
            if io_controller is None:
                return "未连接到电机控制器"
            
            await io_controller.close()
            io_controller = None
            msg = f"已断开与电机控制器 {IO_CONTROLLER_IP}:{IO_CONTROLLER_PORT} 的连接"
            logger.info(msg)
            return msg
        except Exception as e:
            error_msg = f"断开电机控制器连接时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region 数字输出控制工具
    @mcp.tool()
    async def Io_set_do_output(index: int, value: bool) -> str:
        """
        设置指定数字输出口的状态
        功能：控制数字输出口开关状态；触发词：设置输出口、打开X号DO口、关闭X号输出口；参数：需提供输出口索引（0-7）和状态（True=开启/False=关闭）
        :param index: 输出口索引（0-7）
        :param value: 输出状态（True=开启，False=关闭）
        :return: 操作结果
        """
        global io_controller
        try:
            # 检查连接状态
            if io_controller is None or not io_controller.is_connected:
                return "未连接到电机控制器，请先连接"
            
            # 验证索引范围
            if not (0 <= index <= 7):
                return f"输出口索引错误，必须在0-7之间，当前值: {index}"
            
            # 设置输出口状态并发送命令
            io_controller.set_do_command(index, value)
            await io_controller.send_command()
            
            msg = f"已设置输出口 {index} 为 {'开启' if value else '关闭'}"
            logger.info(msg)
            return msg
        except IndexError as e:
            error_msg = f"输出口索引错误: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"设置输出口状态时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @mcp.tool()
    def Io_get_do_states() -> str:
        """获取所有数字输出口的当前状态
        功能：查询所有数字输出口当前状态；触发词：查看输出口状态、DO口状态查询、输出口状态；参数：无，返回8个输出口的开关状态
        """
        global io_controller
        try:
            if io_controller is None or not io_controller.is_connected:
                return "未连接到电机控制器，请先连接"
            
            states = io_controller.do_state
            state_str = ", ".join([f"DO{i}: {'开' if state else '关'}" for i, state in enumerate(states)])
            return f"当前输出口状态: {state_str}"
        except Exception as e:
            error_msg = f"获取输出口状态时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion
    #region 电机控制工具
    @mcp.tool()
    async def Io_set_tool_state(state: bool) -> bool:
        """
        功能：设置电机工具开关（开/关）；触发词：工具（开/关）；参数：需提供状态（true=开启，false=关闭）
转）
        设置电机工具状态
        :param state: 电机工具状态（true=开启，false=关闭）
        :return: 操作结果
        """

        global io_controller
        try:
            if io_controller is None or not io_controller.is_connected:
                return "未连接到电机控制器，请先连接"
            if io_controller is None or not getattr(io_controller, 'is_connected', False):
                raise Exception("未连接到电机控制器，请先连接")

            io_controller.set_tool_command(state)
            await io_controller.send_command()

            return True
        except ValueError as e:
            error_msg = f"电机状态值错误: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"设置电机状态时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #region 电机控制工具
    @mcp.tool()
    async def Io_set_motor_state(state: int) -> str:
        """
        功能：设置电机运行状态（停止/正转/反转）；触发词：电机正转、电机反转、停止电机；参数：需提供状态码（0=停止、100=正转、200=反转）
        设置电机工具状态
        :param state: 电机工具状态（0=停止，100=正转，200=反转）
        :return: 操作结果
        """
        global io_controller
        try:
            if io_controller is None or not io_controller.is_connected:
                return "未连接到电机控制器，请先连接"
            
            io_controller.set_motor_command(state)
            await io_controller.send_command()
            
            state_desc = "停止" if state == 0 else "正转" if state == 100 else "反转"
            msg = f"已设置电机工具状态为: {state_desc}({state})"
            logger.info(msg)
            return msg
        except ValueError as e:
            error_msg = f"电机状态值错误: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"设置电机状态时出错: {str(e)}"
            logger.error(error_msg)
            return error_msg
    #endregion

    #region Liyou控制器工具
    @mcp.tool()
    async def Io_liyou_connect() -> str:
        """连接到Liyou控制器，拧螺丝机器，返回连接结果
        功能：连接Liyou拧螺丝控制器；触发词：连接Liyou、启动拧螺丝设备、Liyou连接；参数：无（默认使用配置IP和端口）
        """
        global liyou_instance
        try:
            # 如果已连接则先断开
            if liyou_instance and liyou_instance.is_connected:
                await liyou_instance.disconnect()
            
            # 创建实例并连接
            liyou_instance = Liyou()
            connect_success = await liyou_instance.connect()
            
            if connect_success:
                return "成功连接到Liyou控制器"
            else:
                return "连接Liyou控制器失败"
        except Exception as e:
            return f"连接过程出错: {str(e)}"

    @mcp.tool()
    async def Io_liyou_disconnect() -> str:
        """断开与Liyou控制器/拧螺丝机器的连接，返回断开结果
        功能：断开与Liyou控制器的连接；触发词：断开Liyou、关闭拧螺丝机、Liyou断开；参数：无
        """
        global liyou_instance
        try:
            if not liyou_instance or not liyou_instance.is_connected:
                return "未连接到Liyou控制器"
            
            await liyou_instance.disconnect()
            return "已成功断开与Liyou控制器的连接"
        except Exception as e:
            return f"断开连接出错: {str(e)}"

    @mcp.tool()
    async def Io_liyou_read_status() -> str:
        """读取Liyou控制器/拧螺丝机器的当前状态码和状态描述
        功能：查询Liyou控制器当前状态；触发词：Liyou状态查询、拧螺丝机状态、查看Liyou状态；参数：无，返回状态码及描述（如"0x0001=拧紧成功"）
        """
        global liyou_instance
        try:
            if not liyou_instance or not liyou_instance.is_connected:
                return "未连接到Liyou控制器，请先连接"
            
            # 读取状态寄存器
            await liyou_instance.read_register(liyou_instance.REG_STATUS)
            await asyncio.sleep(0.2)  # 等待响应
            
            status_code = liyou_instance.x
            status_text = liyou_instance.get_status_text(status_code)
            return f"当前状态 - 状态码: 0x{status_code:04X}, 描述: {status_text}"
        except Exception as e:
            return f"读取状态出错: {str(e)}"

    @mcp.tool()
    async def Io_liyou_start() -> str:
        """发送启动命令到Liyou控制器/拧螺丝机器，并返回执行结果
        功能：发送启动命令到Liyou控制器（执行拧螺丝）；触发词：开始拧螺丝、启动Liyou、Liyou工作；参数：无（需先通过liyou_connect连接）
        """
        global liyou_instance
        try:
            if not liyou_instance or not liyou_instance.is_connected:
                return "未连接到Liyou控制器，请先连接"
            
            # 发送启动命令
            await liyou_instance.write_register(liyou_instance.REG_START, 1)
            await asyncio.sleep(0.5)  # 等待控制器响应
            
            # 读取状态确认
            await liyou_instance.read_register(liyou_instance.REG_STATUS)
            await asyncio.sleep(0.2)
            
            status_code = liyou_instance.x
            status_text = liyou_instance.get_status_text(status_code)
            return f"启动命令已发送 - 状态码: 0x{status_code:04X}, 描述: {status_text}"
        except Exception as e:
            return f"发送启动命令出错: {str(e)}"

    @mcp.tool()
    async def Io_liyou_stop() -> str:
        """发送停止命令到Liyou控制器/拧螺丝机器，并返回执行结果
        功能：发送停止命令到Liyou控制器；触发词：停止拧螺丝、Liyou停止、终止拧螺丝；参数：无（需先连接Liyou）
        """
        global liyou_instance
        try:
            if not liyou_instance or not liyou_instance.is_connected:
                return "未连接到Liyou控制器，请先连接"
            
            # 发送停止命令
            await liyou_instance.write_register(liyou_instance.REG_STOP, 1)
            await asyncio.sleep(0.5)  # 等待控制器响应
            
            # 读取状态确认
            await liyou_instance.read_register(liyou_instance.REG_STATUS)
            await asyncio.sleep(0.2)
            
            status_code = liyou_instance.x
            status_text = liyou_instance.get_status_text(status_code)
            return f"停止命令已发送 - 状态码: 0x{status_code:04X}, 描述: {status_text}"
        except Exception as e:
            return f"发送停止命令出错: {str(e)}"

    @mcp.tool()
    def Io_liyou_get_connection_status() -> str:
        """获取当前Liyou控制器/拧螺丝机器的连接状态
        功能：查询Liyou控制器的连接状态；触发词：Liyou是否连接、检查拧螺丝机连接、Liyou在线状态；参数：无，返回"已连接"或"未连接"
        """
        global liyou_instance
        if not liyou_instance:
            return "Liyou控制器实例未创建"
        return f"当前连接状态: {'已连接' if liyou_instance.is_connected else '未连接'}"
    #endregion

    #region 通用工具
    @mcp.tool()
    def Io_wait(seconds: int) -> str:
        """延迟指定秒数后继续执行后续指令
        功能：延迟指定秒数后继续执行；触发词：等待X秒、暂停X秒、延迟X秒；参数：需提供等待秒数（非负数，如5）
        """
        try:
            if seconds < 0:
                raise ValueError("等待时间不能为负数")
            import time
            time.sleep(seconds)  # 同步等待
            return f"已等待 {seconds} 秒"
        except Exception as e:
            return f"等待失败: {str(e)}"
    #endregion