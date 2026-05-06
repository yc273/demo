# __init__.py

"""
Duco 机器人模块初始化文件
"""

# 导入主要的机器人控制类
from .DucoCobot import DucoCobot

# 定义包的公开接口
__all__ = ['DucoCobot']