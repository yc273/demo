"""
Robots module containing robot-specific implementations and interfaces.
Supports Universal Robots (UR) and Duco robot platforms.
"""

__all__ = []

# Optional imports to avoid circular dependencies
try:
    from . import URBasic
    __all__.append('URRobot')
except ImportError:
    pass

try:
    from .Duco.DucoCobot import DucoCobot
    __all__.append('DucoCobot')
except ImportError:
    pass

try:
    from .Duco.DucoCobot import DucoCobot
    __all__.append('DucoCobot')
except ImportError:
    pass

try:
    from .robot_tools import register_robot_tools
    __all__.append('register_robot_tools')
except ImportError:
    pass