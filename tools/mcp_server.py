#!/usr/bin/env python3
"""
Main entry point for Nonead Universal Robots MCP
启动脚本，用于启动MCP服务器
"""

import asyncio
from atexit import register
import os
import sys

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from fastmcp import FastMCP

# Import tool modules from three independent MCP libraries
from tools.io_modules.io_tools import register_io_tools
from tools.robots.robot_tools import register_robot_tools
from tools.vision import register_vision_tools
from tools.algorithms.algorithms_mcp_tools import register_algorithms_tools



# Initialize MCP server
mcp = FastMCP("NoneadUniversalRobotsMCP")

# Register all tools from three independent libraries
register_io_tools(mcp)
register_robot_tools(mcp)
register_vision_tools(mcp)
register_algorithms_tools(mcp)

if __name__ == "__main__":
    """运行MCP服务器"""
    print("启动Nonead通用机器人MCP服务器...")
    print("已从三个独立的MCP工具库导入:")
    print("  - IO模块库: 电机控制、数字输出口、Liyou拧螺丝机等")
    print("  - 机器人模块库: UR机器人控制、多品牌机器人抽象层等")
    print("  - 视觉模块库: 十字交叉点检测、法向量检测、深度检测等")
    print("  - 算法模块库: 十字交叉点算法、法向量算法、深度算法等")
    print("MCP服务器已启动，等待连接...")
    
    # Run the MCP server
    mcp.run()