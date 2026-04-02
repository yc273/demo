import json
import math
import re
import time
import socket
import sys
import os
from dataclasses import dataclass,field
from typing import List, Tuple, Optional, Dict
import asyncio
from typing import Union

from regex import F
from sympy import false


# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.vision import VisionApi
from tools.robots.Duco import DucoCobot
from .angle_calculations import RotationCalculator
from logs.logger_utils import logger


#region 数据结构
@dataclass
class Matrix3x3:
    m00: float = 1.0
    m01: float = 0.0
    m02: float = 0.0
    m10: float = 0.0
    m11: float = 1.0
    m12: float = 0.0
    m20: float = 0.0
    m21: float = 0.0
    m22: float = 1.0
    
    
    def identity() -> 'Matrix3x3':
        return Matrix3x3()

@dataclass
class CalibrationData:
    transform_matrix: Matrix3x3 = field(default_factory=Matrix3x3.identity())
    home_position: List[float] = None
    calib_depth: float = 0.0

@dataclass
class AngleCalibrationData:
    calibration_z_axis: List[float] = None
    # calibration_robot_pose: List[float] = None

#endregion


# 主应用类
class AlgorithmsApi:
    def __init__(self, brand: str):        
        # 状态变量
        self.transform_matrix = Matrix3x3.identity()
        # 机器人型号
        self.brand = brand
        # 工具型号
        self.tool = None

        self.is_load_calibration_data = False


        self.is_positon_calibrated = False
        self.is_depth_calibrated = False

        self.first_calib_image_points = []
        self.second_calib_image_points = []

        self.calib_robot_pos1 = []
        self.calib_robot_pos2 = []

        self.home_position = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.calib_depth = 0.0
        
        # 角度标定相关
        self.is_angle_calibrated = False
        self.calibration_z_axis = [0.0, 0.0, 1.0]
        
        # 常量
        # self.offset = [0.01, -0.008]
        # self.offset1 = [-0.02, -0.09, -0.13, 0, 0, 0]#115-215
        # self.offset2 = [self.offset[0], self.offset[1], 0, 0, 0, 0]

        self.offset = [0.01, -0.008]
        # self.offset1 = [-0.02, 0.035, -0.1, 0, 0, 0]#焊钉专用
        # self.offset1 = [0.09, 0.02, -0.1, 0, 0, 0]#拧螺套专用
        # self.offset1 = [-0.09, -0.02, -0.1, 0, 0, 0]#焊钉专用
        self.offset1 = [0.08, 0, -0.06, 0, 0, 0]
        self.offset2 = [self.offset[0], self.offset[1], 0, 0, 0, 0]
        #深度由200mm调整至270mm 49.7
        self.offset3 = [0,0,0,0,0,0]
        # self.offset4 = [0,0,0.12,0,0,0]#拧螺套专用
        self.offset4 = [0,0,0.18,0,0,0]#焊钉专用


        # 获取当前文件所在目录
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上两级目录，再进入config/calibration目录
        self.config_dir = os.path.abspath(os.path.join(self.current_dir, "..", "..", "config", "calibration"))        
        # 校准数据文件的完整路径
        if self.brand == "duco":
            self.calib_data_path = os.path.join(self.config_dir, "calibration_data_duco.json")
        elif self.brand == "ur":
            self.calib_data_path = os.path.join(self.config_dir, "calibration_data_ur.json")
        elif self.brand == "dazu":
            self.calib_data_path = os.path.join(self.config_dir, "calibration_data_duco_dazu.json")
        else:
            pass

        # 记录点位数据文件的完整路径
        self.recorded_points_data_path = os.path.join(self.config_dir, f"recorded_points_data.json")
        # 验证路径是否存在，不存在则创建
        if not os.path.exists(self.config_dir):
            logger.error(f"校准数据目录不存在: {self.config_dir}")
            try:
                # 创建目录（包括任何必要的父目录）
                os.makedirs(self.config_dir, exist_ok=True)
                logger.info(f"已自动创建校准数据目录: {self.config_dir}")
            except Exception as e:
                logger.error(f"创建校准数据目录失败: {str(e)} | 函数参数: {locals()}")
        


        # 检查数据文件是否存在
        if not os.path.exists(self.calib_data_path):
            logger.error(f"主校准数据文件不存在: {self.calib_data_path}")

        if not os.path.exists(self.recorded_points_data_path):
            logger.error(f"记录点位数据文件不存在: {self.recorded_points_data_path}")


        self.recorded_joint_points_data_path = os.path.join(self.config_dir, f"recorded_joint_points_data.json")
        # 验证路径是否存在，不存在则创建
        if not os.path.exists(self.config_dir):
            logger.error(f"校准数据目录不存在: {self.config_dir}")
            try:
                # 创建目录（包括任何必要的父目录）
                os.makedirs(self.config_dir, exist_ok=True)
                logger.info(f"已自动创建校准数据目录: {self.config_dir}")
            except Exception as e:
                logger.error(f"创建校准数据目录失败: {str(e)} | 函数参数: {locals()}")
        # 检查数据文件是否存在
        if not os.path.exists(self.calib_data_path):
            logger.error(f"主校准数据文件不存在: {self.calib_data_path}")

        if not os.path.exists(self.recorded_joint_points_data_path):
            logger.error(f"记录点位数据文件不存在: {self.recorded_joint_points_data_path}")

    
    def log(self, message: str):
        """日志输出（兼容中文编码）"""
        try:
            logger.info(message.encode('utf-8').decode('utf-8'))  # 强制UTF-8编码转换
        except UnicodeEncodeError:
            # 极端情况下替换非法字符
            logger.info(message.encode('utf-8', errors='replace').decode('utf-8'))

#region 数据存储和加载 
    def load_calibration_data(self):
        """加载标定数据"""
        try:
            with open(self.calib_data_path, 'r') as f:
                all_data = json.load(f)
                # 获取指定工具的数据
                data = all_data.get(self.tool)
                if not data:
                    raise KeyError(f"未找到工具 '{self.tool}' 的校准数据")
                # 解析矩阵数据
                matrix_data = data['transform_matrix']
                self.transform_matrix = Matrix3x3(
                    matrix_data['m00'], matrix_data['m01'], matrix_data['m02'],
                    matrix_data['m10'], matrix_data['m11'], matrix_data['m12'],
                    matrix_data['m20'], matrix_data['m21'], matrix_data['m22']
                )
                self.home_position = data['home_position']
                self.calib_depth = data['calib_depth']
                self.calibration_z_axis = data.get('calibration_z_axis', [0.0, 0.0, 1.0])  # 添加默认值
                self.is_positon_calibrated = True
                self.is_depth_calibrated = True
                self.is_angle_calibrated = data.get('is_angle_calibrated', False)  # 从文件读取角度标定状态
                self.is_load_calibration_data = True
                self.log("已加载历史标定数据")
        except Exception as e:
            self.log(f"加载标定数据失败: {str(e)} | 函数参数: {locals()}")
            self.is_positon_calibrated = False
            self.is_depth_calibrated = False
            self.is_angle_calibrated = False
            self.home_position = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            self.calibration_z_axis = [0.0, 0.0, 1.0]
            self.is_load_calibration_data = False
    
    def save_calibration_data(self):
        """保存标定数据"""
        try:
            # 如果文件存在，先读取现有数据
            all_data = {}
            if os.path.exists(self.calib_data_path):
                with open(self.calib_data_path, 'r') as f:
                    all_data = json.load(f)
            # 准备当前工具的数据
            tool_data = {
                'transform_matrix': {
                    'm00': self.transform_matrix.m00,
                    'm01': self.transform_matrix.m01,
                    'm02': self.transform_matrix.m02,
                    'm10': self.transform_matrix.m10,
                    'm11': self.transform_matrix.m11,
                    'm12': self.transform_matrix.m12,
                    'm20': self.transform_matrix.m20,
                    'm21': self.transform_matrix.m21,
                    'm22': self.transform_matrix.m22
                },
                'home_position': self.home_position,
                'calib_depth': self.calib_depth,
                'calibration_z_axis': self.calibration_z_axis,
                'is_angle_calibrated': self.is_angle_calibrated
            }
            
            # 更新指定工具的数据
            all_data[self.tool] = tool_data
            
            # 保存所有数据
            with open(self.calib_data_path, 'w') as f:
                json.dump(all_data, f, indent=4)
            self.log(f"工具 '{self.tool}' 的标定数据已保存")
        except Exception as e:
            self.log(f"保存标定数据失败: {str(e)} | 函数参数: {locals()}")  
#endregion

#region 工具选择
    def select_tool(self, tool_name: str) -> bool:
        """选择并加载指定工具的标定数据
        :param tool_name: 工具名称
        :return: 选择是否成功
        """
        try:
            if not tool_name:
                self.log("工具名称不能为空")
                return False
                
            self.log(f"选择工具: {tool_name}")
            self.tool = tool_name
            self.load_calibration_data()
            self.is_load_calibration_data = True
            return True
        except Exception as e:
            self.log(f"选择工具失败: {str(e)} | 函数参数: {locals()}")
            return False
#endregion



#region 十字坐标
    def position_adjust(self, pos: List[float]) -> Union[List[float], None]:
        """对齐十字点算法"""
        try:
            # 检查标定状态
            if not self.is_load_calibration_data:
                self.log("请先加载配置数据")
                return
            # if self.tool != 'nail_bumping':
            #     self.log("请选择 nails_bumping工具")
            #     return
            self.log("开始执行position_adjust算法...")
            # 检测十字点
            if not pos:
                self.log("未收到有效十字点，操作终止")
                return
            self.log(f"成功接收十字点坐标: X={pos[0]}, Y={pos[1]}")

            # 坐标转换
            target_tool_pos = self.transform_point_to_base(pos)
            #检验是否转换成功
            if not target_tool_pos:
                self.log("坐标转换失败")
                return
            # 计算补正偏移            
            align_offset = [
                -target_tool_pos[0],
                -target_tool_pos[1],
                0, 0, 0, 0
            ]
            self.log(f"调整偏移量：{align_offset}")
            # 返回补正偏移
            return align_offset


        except Exception as e:
            self.log(f"position_adjust异常: {str(e)} | 函数参数: {locals()}")
            return

    def is_position_adjusted_perfectly(self,pos: List[float]) -> bool:
        print('is_position_adjusted_perfectly pos:', pos)

        """判断是否已对齐"""
        try:
            # 坐标转换
            target_tool_pos = self.transform_point_to_base(pos)
            # 计算补正偏移            
            align_offset = [
                -target_tool_pos[0],
                -target_tool_pos[1],
                0, 0, 0, 0
            ]
            print('is_position_adjusted_perfectly: offset_X:{}, offset_Y:{}'.format(abs(align_offset[0]), abs(align_offset[1])))
            if abs(align_offset[0]) < 0.0008 and abs(align_offset[1]) < 0.0008:
                self.log(f"偏移量已小于阈值，无需移动")
                return True
            else:
                self.log(f"仍需调整")
                return False
        except Exception as e:
            self.log(f"is_position_adjusted_perfectly异常: {str(e)} | 函数参数: {locals()}")
            return False


    def position_calibration(self,first_image_point: List[float], second_image_point: List[float],
            first_robot_point: List[float], second_robot_point: List[float], third_robot_point: List[float]) -> bool:
        """位置标定算法"""
        try:
            if not first_image_point or not second_image_point:
                raise Exception("无效十字点坐标")
            else:
                self.log(f"第1个点的坐标：X={first_image_point[0]:.2f}, Y={first_image_point[1]:.2f}")
                self.log(f"第2个点的坐标：X={second_image_point[0]:.2f}, Y={second_image_point[1]:.2f}")

            # if self.tool != 'nail_bumping':
            #     self.log("请选择 nails_bumping工具")
            #     return False  
            # 记录当前机器人位置和图像坐标
            self.calib_robot_pos1 = first_robot_point
            self.first_calib_image_points.append(first_image_point)

            # 记录机器人位置和图像坐标
            self.calib_robot_pos2 = second_robot_point
            self.second_calib_image_points.append(second_image_point)
            # 计算转换矩阵
            self.calculate_full_transform_matrix()
            # 记录原点位置
            self.home_position = third_robot_point
            self.log(f"初始原点已记录：X={self.home_position[0]}, Y={self.home_position[1]}, Z={self.home_position[2]}")
            # 标定完成
            self.is_positon_calibrated = True
            self.save_calibration_data()
            self.log("标定成功！转换矩阵已保存")
            return True
        except Exception as e:
            self.log(f"标定异常: {str(e)} | 函数参数: {locals()}")
            return False

#endregion

#region 螺钉
    def screw_calibration(self,first_image_point: List[float], second_image_point: List[float],
            first_robot_point: List[float], second_robot_point: List[float], third_robot_point: List[float]) -> bool:
        """螺钉标定算法"""
        try:
            if not first_image_point or not second_image_point:
                raise Exception("无效螺钉坐标")
            else:
                self.log(f"第1个点的坐标：X={first_image_point[0]:.2f}, Y={first_image_point[1]:.2f}")
                self.log(f"第2个点的坐标：X={second_image_point[0]:.2f}, Y={second_image_point[1]:.2f}")

            # if self.tool != 'screw_sleeve':
            #     self.log("请选择 screw_sleeve工具")
            #     return False
            
            # 记录当前机器人位置和图像坐标
            self.calib_robot_pos1 = first_robot_point
            self.first_calib_image_points.append(first_image_point)

            # 记录机器人位置和图像坐标
            self.calib_robot_pos2 = second_robot_point
            self.second_calib_image_points.append(second_image_point)
            # 计算转换矩阵
            self.calculate_full_transform_matrix()
            # 记录原点位置
            self.home_position = third_robot_point
            self.log(f"初始原点已记录：X={self.home_position[0]}, Y={self.home_position[1]}, Z={self.home_position[2]}")
            # 标定完成
            self.is_positon_calibrated = True
            self.save_calibration_data()
            self.log("标定成功！转换矩阵已保存")
            return True
        except Exception as e:
            self.log(f"标定异常: {str(e)} | 函数参数: {locals()}")
            return False

    def screw_adjust(self, pos: List[float]) -> Union[List[float], None]:
        """对齐螺钉算法"""
        try:
            # 检查标定状态
            if not self.is_load_calibration_data:
                self.log("请先加载配置数据")
                return
            # if self.tool != 'screw_sleeve':
            #     self.log("请选择 screw_sleeve工具")
            #     return
            self.log("开始执行screw_adjust算法...")
            # 检测螺钉
            if not pos:
                self.log("未收到有效螺钉坐标，操作终止")
                return
            self.log(f"成功接收螺钉坐标: X={pos[0]}, Y={pos[1]}")

            # 坐标转换
            target_tool_pos = self.transform_point_to_base(pos)
            #检验是否转换成功
            if not target_tool_pos:
                self.log("坐标转换失败")
                return
            # 计算补正偏移            
            align_offset = [
                -target_tool_pos[0],
                -target_tool_pos[1],
                0, 0, 0, 0
            ]
            self.log(f"调整偏移量：{align_offset}")
            # 返回补正偏移
            return align_offset


        except Exception as e:
            self.log(f"screw_adjust异常: {str(e)} | 函数参数: {locals()}")
            return
        

    def is_screw_adjusted_perfectly(self,pos: List[float]) -> bool:
        """判断是否已对齐"""
        try:
            # 坐标转换
            target_tool_pos = self.transform_point_to_base(pos)
            # 计算补正偏移            
            align_offset = [
                -target_tool_pos[0],
                -target_tool_pos[1],
                0, 0, 0, 0
            ]
            if abs(align_offset[0]) < 0.0003 and abs(align_offset[1]) < 0.0003:#TODO
                self.log(f"偏移量已小于阈值，无需移动")
                return True
            else:
                self.log(f"仍需调整")
                return False
        except Exception as e:
            self.log(f"is_screw_adjusted_perfectly异常: {str(e)} | 函数参数: {locals()}")
            return False

#endregion

#region 旋转矩阵辅助函数
    def calculate_full_transform_matrix(self):
        """计算完整的转换矩阵"""
        if not self.first_calib_image_points or not self.second_calib_image_points or \
           not self.calib_robot_pos1 or not self.calib_robot_pos2:
            raise Exception("缺少标定数据")

        # 像素坐标
        img1 = self.first_calib_image_points[0]
        img2 = self.second_calib_image_points[0]
        img_diff = [img2[0] - img1[0], img2[1] - img1[1]]

        # 机器人移动向量
        robot_diff = self.offset

        # 计算缩放因子
        robot_dist = math.sqrt(robot_diff[0]**2 + robot_diff[1]** 2)
        img_dist = math.sqrt(img_diff[0]**2 + img_diff[1]** 2)
        
        if img_dist < 1e-10:
            raise Exception("像素移动距离过小，无法计算缩放因子")
            
        scale_factor = robot_dist / img_dist

        # 计算旋转矩阵
        rotation_matrix = self.calculate_rotation_matrix(img_diff, robot_diff)

        # 计算偏移量
        # offset_x = self.offset1[0] - img1[0] * rotation_matrix[0] * scale_factor - img1[1] * rotation_matrix[1] * scale_factor
        # offset_y = self.offset1[1] - img1[0] * rotation_matrix[2] * scale_factor - img1[1] * rotation_matrix[3] * scale_factor
        offset_x =  - img1[0] * rotation_matrix[0] * scale_factor - img1[1] * rotation_matrix[1] * scale_factor
        offset_y =  - img1[0] * rotation_matrix[2] * scale_factor - img1[1] * rotation_matrix[3] * scale_factor
        self.log(f"缩放因子：{scale_factor}")
        self.log(f"旋转矩阵：{rotation_matrix}")
        self.log(f"偏移量：{offset_x}, {offset_y}")
        # 构建转换矩阵
        self.transform_matrix = Matrix3x3(
            m00=rotation_matrix[0] * scale_factor,
            m01=rotation_matrix[1] * scale_factor,
            m02=offset_x,
            m10=rotation_matrix[2] * scale_factor,
            m11=rotation_matrix[3] * scale_factor,
            m12=offset_y
        )
    
    def calculate_rotation_matrix(self, vector_a: List[float], vector_b: List[float]) -> List[float]:
        """计算向量A到向量B的旋转矩阵"""
        if len(vector_a) != 2 or len(vector_b) != 2:
            raise ValueError("输入向量必须为二维向量")

        # 计算向量长度
        len_a = math.sqrt(vector_a[0]**2 + vector_a[1]** 2)
        len_b = math.sqrt(vector_b[0]**2 + vector_b[1]** 2)

        if len_a < 1e-10 or len_b < 1e-10:
            raise ValueError("向量长度不能为零")

        # 归一化向量
        ax = vector_a[0] / len_a
        ay = vector_a[1] / len_a
        bx = vector_b[0] / len_b
        by = vector_b[1] / len_b

        # 计算旋转角的余弦和正弦
        cos_theta = ax * bx + ay * by
        sin_theta = ax * by - ay * bx

        # 修正数值计算误差
        cos_theta = max(min(cos_theta, 1.0), -1.0)

        return [cos_theta, -sin_theta, sin_theta, cos_theta]
    
    def transform_point_to_base(self, image_point: List[float]) -> Optional[List[float]]:
        """像素坐标转换为机器人坐标系坐标"""
        if not image_point or len(image_point) < 2:
            return None
            
        x = self.transform_matrix.m00 * image_point[0] + self.transform_matrix.m01 * image_point[1] + self.transform_matrix.m02
        y = self.transform_matrix.m10 * image_point[0] + self.transform_matrix.m11 * image_point[1] + self.transform_matrix.m12
        return [x, y]
# endregion

 #region 角度

    def angle_calibration(self, normal: Tuple[float, float, float]) -> bool:
        """角度标定算法"""
        try:
            nx, ny, nz = normal
            if nx == 0 and ny == 0 and nz == 0:
                raise Exception("无效法向量")
            self.calibration_z_axis = [nx, ny, nz]
            self.log(f"已记录标定Z轴: [{nx:.4f}, {ny:.4f}, {nz:.4f}]")
            # 保存数据
            self.is_angle_calibrated = True
            self.save_calibration_data()
            self.log("角度标定成功！数据已保存")
            return True
        except Exception as e:
            self.log(f"角度标定异常: {str(e)} | 函数参数: {locals()}")
            return False
    

    def angle_adjust(self, measured_z: List[float]) -> Union[List[float], None]:
        """角度调整算法"""
        try:
            # 检查标定状态
            if not self.is_load_calibration_data:
                self.log("请先加载标定数据")
                return
            
            self.log("开始执行：角度调整算法...")
            
            # 检查输入有效性
            if not measured_z or len(measured_z) != 3 or all(v == 0 for v in measured_z):
                self.log("未收到有效法向量，操作终止")
                return
                
            self.log(f"成功接收法向量: X={measured_z[0]:.4f}, Y={measured_z[1]:.4f}, Z={measured_z[2]:.4f}")
                

            self.log("角度调整执行...")
            # 计算角度偏差
            dot_product = sum(a * b for a, b in zip(self.calibration_z_axis, measured_z))
            angle_diff = math.acos(min(1.0, max(-1.0, dot_product))) * 180 / math.pi
            self.log(f"当前角度偏差: {angle_diff:.2f}°")                
            
            # 计算补正调整量
            return self.calculate_angle_adjustment(measured_z)
                
        except Exception as e:
            self.log(f"angle_adjust算法异常: {str(e)} | 函数参数: {locals()}")
            return


    def calculate_angle_adjustment(self, measured_z: List[float]) -> List[float]:
        """计算角度调整量"""
        # 计算调整角度
        rx_tcp, ry_tcp, rz_tcp = RotationCalculator.tcp_rotation_calculation(
            self.calibration_z_axis,measured_z, self.tool )
        
        self.log(f"计算结果-------工具系下调整角度: RX={math.degrees(rx_tcp):.2f}°, RY={math.degrees(ry_tcp):.2f}°, RZ={math.degrees(rz_tcp):.2f}°")
        
        # 返回角度调整量 (dx, dy, dz, rx, ry, rz)
        return [0, 0, 0, rx_tcp, ry_tcp, rz_tcp]

    def is_angle_adjusted_perfectly(self, measured_z: List[float]) -> bool:
        """判断当前角度是否已经完全调整"""
        try: 
            angle_offset = self.calculate_angle_adjustment(measured_z)
            result = abs(angle_offset[3]) < 0.001 and abs(angle_offset[4]) < 0.01#TODO
            if result: 
                self.log("当前角度已经完全调整！")
                return True
            else:
                self.log("当前角度尚未完全调整！")
                return False
        except Exception as e:
            self.log(f"is_angle_adjusted_perfectly异常: {str(e)} | 函数参数: {locals()}")
            return False

#endregion



#region 深度

    def depth_calibrate(self, current_depth: float) -> bool:
        """深度标定算法
        基于当前深度数据完成标定
        :param current_depth: 当前深度测量值
        :return: 标定是否成功
        """
        try:
            # 检查输入有效性
            if current_depth <= 0:
                raise Exception("无效的深度数据，标定失败")

            # 记录标定深度
            self.calib_depth = current_depth
            self.log(f"深度标定成功，标定深度: {self.calib_depth:.3f}mm")
            
            # 保存标定数据并更新状态
            self.save_calibration_data()
            self.is_depth_calibrated = True
            return True
            
        except Exception as e:
            self.log(f"深度标定异常: {str(e)} | 函数参数: {locals()}")
            return False


    def depth_adjust(self, current_depth: float) -> Union[List[float], None]:
        """深度调整算法
        基于当前深度与标定深度的差异计算补正量
        :param current_depth: 当前深度测量值
        :return: 深度调整量 [dx, dy, dz, rx, ry, rz]，None表示失败
        """
        try:
            # 检查前置条件
            if not self.is_load_calibration_data:
                self.log("请先加载标定数据")
                return

            # 检查输入有效性
            if current_depth <= 0:
                self.log("未收到有效深度信息，操作终止")
                return

            self.log("开始深度调整算法...")
            self.log(f"当前测量深度: {current_depth:.3f}mm，标定深度: {self.calib_depth:.3f}mm")

            # 计算深度偏差
            depth_diff = current_depth - self.calib_depth
            self.log(f"深度偏差: {depth_diff:.3f}mm")
            self.log(f"执行深度补正...")
            # 计算补正调整量
            return self.calculate_depth_adjustment(current_depth)
                
        except Exception as e:
            self.log(f"深度调整算法异常: {str(e)} | 函数参数: {locals()}")
            return


    def calculate_depth_adjustment(self, current_depth: float) -> List[float]:
        """计算深度调整量
        :param current_depth: 当前深度测量值
        :return: 深度调整量 [dx, dy, dz, rx, ry, rz]
        """
        # 计算Z轴调整量（转换为米单位）
        z_adjust = (current_depth-self.calib_depth) / 1000
        
        self.log(f"计算结果------深度调整量: Z方向 {z_adjust*1000:.3f}mm")
        
        # 返回调整量（仅Z轴有变化，其余维度为0）
        return [0, 0, z_adjust, 0, 0, 0]

    def is_depth_adjusted_perfectly(self, current_depth: float) -> bool:
        """判断当前深度是否已经完全调整完毕"""
        try:
            depth_diff = abs(current_depth - self.calib_depth)
            if depth_diff < 0.5:#TODO
                self.log(f"补正深度偏差已小于阈值，无需调整")
                return True
            else:
                self.log(f"补正深度偏差大于阈值，继续调整")
                return False
        except Exception as e:
            self.log(f"is_depth_adjusted_perfectly错误: {e}")
            return False

#endregion


#region 记录点位

    def record_point(self, point_name: str, robot_position: List[float]) -> bool:
        """
        记录指定序号的点位数据
        
        :param point_name: 点位名字 (如 2, 3, '焊接点1')
        :param robot_position: 机器人位置 [x, y, z, rx, ry, rz]
        :return: 是否记录成功
        """
        try:
            if not isinstance(point_name, str):
                self.log("无效的点位名字")
                return False
                
            if not robot_position or len(robot_position) != 6:
                self.log("无效的机器人位置数据")
                return False
            
            # 加载现有数据
            recorded_points = self._load_recorded_points()
            
            # 更新或添加点位
            recorded_points[point_name] = robot_position
            
            # 保存数据
            if self._save_recorded_points(recorded_points):
                self.log(f"成功记录点位-{point_name}: X={robot_position[0]:.3f}, Y={robot_position[1]:.3f}, "
                        f"Z={robot_position[2]:.3f}, RX={robot_position[3]:.3f}, RY={robot_position[4]:.3f}, "
                        f"RZ={robot_position[5]:.3f}")
                return True
            else:
                self.log(f"记录点位-{point_name} 失败")
                return False
                
        except Exception as e:
            self.log(f"记录点位异常: {str(e)} | 函数参数: {locals()}")
            return False
        
    def delete_point(self, point_name: str) -> bool:
        """
        删除指定序号的点位数据
        
        :param point_name: 点位名字 (如 2, 3, '焊接点1')
        :return: 是否删除成功
        """
        try:
            if not isinstance(point_name, str):
                self.log("无效的点位序号")
                return False
            
            # 加载现有数据
            recorded_points = self._load_recorded_points()
            
            # 检查点位是否存在
            point_key = point_name
            if point_key not in recorded_points:
                self.log(f"点位-{point_name} 不存在")
                return False
            
            # 删除点位
            deleted_position = recorded_points.pop(point_key)
            
            # 保存数据
            if self._save_recorded_points(recorded_points):
                self.log(f"成功删除点位-{point_name}: X={deleted_position[0]:.3f}, Y={deleted_position[1]:.3f}, "
                        f"Z={deleted_position[2]:.3f}, RX={deleted_position[3]:.3f}, RY={deleted_position[4]:.3f}, "
                        f"RZ={deleted_position[5]:.3f}")
                return True
            else:
                self.log(f"删除点位-{point_name} 失败")
                return False
                
        except Exception as e:
            self.log(f"删除点位异常: {str(e)} | 函数参数: {locals()}")
            return False

    def _load_recorded_points(self) -> Dict[str, List[float]]:
        """
        从文件中加载已记录的点位数据
        
        :return: 点位数据字典 {point_name: [x, y, z, rx, ry, rz]}
        """
        try:
            with open(self.recorded_points_data_path, 'r') as f:
                data = json.load(f)
                return data.get('recorded_points', {})
        except Exception:
            # 如果文件不存在或解析失败，返回空字典
            return {}


    def _save_recorded_points(self, recorded_points: Dict[str, List[float]]) -> bool:
        """
        将点位数据保存到文件中
        
        :param recorded_points: 点位数据字典 {point_name: [x, y, z, rx, ry, rz]}
        :return: 是否保存成功
        """
        try:
            # 读取现有数据
            try:
                with open(self.recorded_points_data_path, 'r') as f:
                    data = json.load(f)
            except FileNotFoundError:
                # 如果文件不存在，创建新数据结构
                data = {}
            
            # 更新点位数据
            data['recorded_points'] = recorded_points
            
            # 保存数据
            with open(self.recorded_points_data_path, 'w') as f:
                json.dump(data, f, indent=4)
            
            return True
        except Exception as e:
            self.log(f"保存点位数据异常: {str(e)} | 函数参数: {locals()}")
            return False

    def get_recorded_point(self, point_name: str) -> Union[List[float], None]:
        """
        获取指定名字的记录点位
        :param point_name: 点位名字
        :return: 点位数据 [x, y, z, rx, ry, rz] 或 None（如果不存在）
        """
        try:
            if not isinstance(point_name, str):
                self.log("无效的点位名字")
                return None
            
            recorded_points = self._load_recorded_points()
            point_data = recorded_points.get(point_name)
            
            if point_data:
                self.log(f"获取点位-{point_name} 成功")
                return point_data.copy()  # 返回副本避免外部修改
            else:
                self.log(f"点位-{point_name} 不存在")
                return None
                
        except Exception as e:
            self.log(f"获取记录点位异常: {str(e)} | 函数参数: {locals()}")
            return None

    def list_recorded_points(self) -> Dict[str, List[float]]:
        """
        列出所有已记录的点位
        
        :return: 所有点位数据字典 {point_name: [x, y, z, rx, ry, rz]}
        """
        try:
            recorded_points = self._load_recorded_points()
            self.log(f"共找到 {len(recorded_points)} 个记录点位")
            return recorded_points
        except Exception as e:
            self.log(f"列出记录点位异常: {str(e)} | 函数参数: {locals()}")
            return {}

#endregion



#region 记录关节点位

    def record_joint_point(self, joint_point_name: str, robot_position: List[float]) -> bool:
        """
        记录指定序号的点位数据
        
        :param joint_point_name: 点位名字 (如 2, 3, '焊接点1')
        :param robot_position: 机器人位置 [x, y, z, rx, ry, rz]
        :return: 是否记录成功
        """
        try:
            if not isinstance(joint_point_name, str):
                self.log("无效的点位名字")
                return False
                
            if not robot_position or len(robot_position) != 6:
                self.log("无效的机器人位置数据")
                return False
            
            # 加载现有数据
            recorded_joint_points = self._load_recorded_joint_points()
            
            # 更新或添加点位
            recorded_joint_points[joint_point_name] = robot_position
            
            # 保存数据
            if self._save_recorded_joint_points(recorded_joint_points):
                self.log(f"成功记录点位-{joint_point_name}: X={robot_position[0]:.3f}, Y={robot_position[1]:.3f}, "
                        f"Z={robot_position[2]:.3f}, RX={robot_position[3]:.3f}, RY={robot_position[4]:.3f}, "
                        f"RZ={robot_position[5]:.3f}")
                return True
            else:
                self.log(f"记录点位-{joint_point_name} 失败")
                return False
                
        except Exception as e:
            self.log(f"记录点位异常: {str(e)} | 函数参数: {locals()}")
            return False


    def delete_joint_point(self, joint_point_name: str) -> bool:
        """
        删除指定序号的点位数据
        
        :param joint_point_name: 点位名字 (如 2, 3, '焊接点1')
        :return: 是否删除成功
        """
        try:
            if not isinstance(joint_point_name, str):
                self.log("无效的点位序号")
                return False
            
            # 加载现有数据
            recorded_joint_points = self._load_recorded_joint_points()
            
            # 检查点位是否存在
            joint_point_key = joint_point_name
            if joint_point_key not in recorded_joint_points:
                self.log(f"点位-{joint_point_name} 不存在")
                return False
            
            # 删除点位
            deleted_position = recorded_joint_points.pop(joint_point_key)
            
            # 保存数据
            if self._save_recorded_joint_points(recorded_joint_points):
                self.log(f"成功删除点位-{joint_point_name}: X={deleted_position[0]:.3f}, Y={deleted_position[1]:.3f}, "
                        f"Z={deleted_position[2]:.3f}, RX={deleted_position[3]:.3f}, RY={deleted_position[4]:.3f}, "
                        f"RZ={deleted_position[5]:.3f}")
                return True
            else:
                self.log(f"删除点位-{joint_point_name} 失败")
                return False
                
        except Exception as e:
            self.log(f"删除点位异常: {str(e)} | 函数参数: {locals()}")
            return False

    def _load_recorded_joint_points(self) -> Dict[str, List[float]]:
        """
        从文件中加载已记录的点位数据
        
        :return: 点位数据字典 {joint_point_name: [x, y, z, rx, ry, rz]}
        """
        try:
            with open(self.recorded_joint_points_data_path, 'r') as f:
                data = json.load(f)
                return data.get('recorded_joint_points', {})
        except Exception:
            # 如果文件不存在或解析失败，返回空字典
            return {}


    def _save_recorded_joint_points(self, recorded_joint_points: Dict[str, List[float]]) -> bool:
        """
        将点位数据保存到文件中
        
        :param recorded_joint_points: 点位数据字典 {joint_point_name: [x, y, z, rx, ry, rz]}
        :return: 是否保存成功
        """
        try:
            # 读取现有数据
            try:
                with open(self.recorded_joint_points_data_path, 'r') as f:
                    data = json.load(f)
            except FileNotFoundError:
                # 如果文件不存在，创建新数据结构
                data = {}
            
            # 更新点位数据
            data['recorded_joint_points'] = recorded_joint_points
            
            # 保存数据
            with open(self.recorded_joint_points_data_path, 'w') as f:
                json.dump(data, f, indent=4)
            
            return True
        except Exception as e:
            self.log(f"保存点位数据异常: {str(e)} | 函数参数: {locals()}")
            return False

    def get_recorded_joint_point(self, joint_point_name: str) -> Union[List[float], None]:
        """
        获取指定名字的记录点位
        :param joint_point_name: 点位名字
        :return: 点位数据 [x, y, z, rx, ry, rz] 或 None（如果不存在）
        """
        try:
            if not isinstance(joint_point_name, str):
                self.log("无效的点位名字")
                return None
            
            recorded_joint_points = self._load_recorded_joint_points()
            joint_point_data = recorded_joint_points.get(joint_point_name)
            
            if joint_point_data:
                self.log(f"获取点位-{joint_point_name} 成功")
                return joint_point_data.copy()  # 返回副本避免外部修改
            else:
                self.log(f"点位-{joint_point_name} 不存在")
                return None
                
        except Exception as e:
            self.log(f"获取记录点位异常: {str(e)} | 函数参数: {locals()}")
            return None

    def list_recorded_joint_points(self) -> Dict[str, List[float]]:
        """
        列出所有已记录的点位
        
        :return: 所有点位数据字典 {joint_point_name: [x, y, z, rx, ry, rz]}
        """
        try:
            recorded_joint_points = self._load_recorded_joint_points()
            self.log(f"共找到 {len(recorded_joint_points)} 个记录点位")
            return recorded_joint_points
        except Exception as e:
            self.log(f"列出记录点位异常: {str(e)} | 函数参数: {locals()}")
            return {}

#region 其他
    def get_home_position(self) -> Union[List[float], None]:
        """获取初始原点位置
        直接返回已保存的初始原点，不进行计算和运动控制
        :return: 初始原点位姿 [x, y, z, rx, ry, rz]，None表示未设置
        """
        # 检查标定状态和原点设置
        if not self.is_positon_calibrated:
            self.log("未完成标定，无法确定初始原点")
            return None
            
        if not self.home_position or len(self.home_position) != 6:
            self.log("未设置初始原点，请先完成标定")
            return None

        try:
            self.log(f"成功获取初始原点位置: X={self.home_position[0]:.3f}, Y={self.home_position[1]:.3f}, "
                    f"Z={self.home_position[2]:.3f}, RX={self.home_position[3]:.3f}, "
                    f"RY={self.home_position[4]:.3f}, RZ={self.home_position[5]:.3f}")
            return self.home_position.copy()  # 返回副本避免外部修改内部数据
        except Exception as ex:
            self.log(f"获取初始原点异常: {str(ex)}")
            return None
    
    def get_offset_info(self) -> Dict[str, List[float]]:
        return {
            "offset1": self.offset1,
            "offset2": self.offset2,
            "offset3": self.offset3,
            "offset4": self.offset4

        }

#endregion