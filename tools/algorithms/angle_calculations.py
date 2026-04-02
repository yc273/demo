import numpy as np
import math
import sys
import os
from typing import Tuple, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logs.logger_utils import logger

class RotationCalculator:
#region 角度和弧度转换，规范化
    # 度转弧度
    @staticmethod
    def deg_to_rad(degrees: float) -> float:
        return degrees * math.pi / 180.0

    # 弧度转度
    @staticmethod
    def rad_to_deg(radians: float) -> float:
        return radians * 180.0 / math.pi

    # 将角度规范化到指定范围（默认-180°~180°）
    @staticmethod
    def normalize_degrees(degrees: float, min_val: float = -180, max_val: float = 180) -> float:
        while degrees < min_val:
            degrees += 360
        while degrees > max_val:
            degrees -= 360
        return degrees

    # 将弧度规范化到指定范围（默认-π~π）
    @staticmethod
    def normalize_radians(radians: float, min_val: float = -math.pi, max_val: float = math.pi) -> float:
        while radians < min_val:
            radians += 2 * math.pi
        while radians > max_val:
            radians -= 2 * math.pi
        return radians
#endregion



#region 旋转矩阵计算
    # 从旋转轴和旋转角度计算旋转矩阵（罗德里格斯公式）
    @staticmethod
    def axis_angle_to_rotation_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
        # 归一化旋转轴
        norm = np.linalg.norm(axis)
        if norm < 1e-10:
            raise ValueError("旋转轴不能为零向量")

        normalized_axis = axis / norm
        a = math.cos(angle / 2.0)
        b = -normalized_axis[0] * math.sin(angle / 2.0)
        c = -normalized_axis[1] * math.sin(angle / 2.0)
        d = -normalized_axis[2] * math.sin(angle / 2.0)

        return np.array([
            [a*a + b*b - c*c - d*d, 2*(b*c - a*d), 2*(b*d + a*c)],
            [2*(b*c + a*d), a*a + c*c - b*b - d*d, 2*(c*d - a*b)],
            [2*(b*d - a*c), 2*(c*d + a*b), a*a + d*d - b*b - c*c]
        ])

    # 计算从实测Z轴到标定Z轴的旋转矩阵
    @staticmethod
    def get_rotation_matrix_from_z_axes(calibration_z: np.ndarray, measured_z: np.ndarray) -> np.ndarray:
        calib_z = calibration_z / np.linalg.norm(calibration_z)
        meas_z = measured_z / np.linalg.norm(measured_z)

        # 旋转轴为measZ × calibZ（右乘旋转的正确轴方向）
        rotation_axis = np.array([
            meas_z[1] * calib_z[2] - meas_z[2] * calib_z[1],  # x分量
            meas_z[2] * calib_z[0] - meas_z[0] * calib_z[2],  # y分量
            meas_z[0] * calib_z[1] - meas_z[1] * calib_z[0]   # z分量
        ])

        axis_norm = np.linalg.norm(rotation_axis)
        if axis_norm < 1e-10:
            if np.dot(meas_z, calib_z) > 0:
                return np.eye(3)
            else:
                if abs(meas_z[0]) > 1e-10 or abs(meas_z[1]) > 1e-10:
                    rot_axis = np.array([-meas_z[1], meas_z[0], 0.0])
                else:
                    rot_axis = np.array([1.0, 0.0, 0.0])
                return RotationCalculator.axis_angle_to_rotation_matrix(rot_axis, math.pi)

        rotation_axis = rotation_axis / axis_norm
        dot_product = np.dot(meas_z, calib_z)
        angle = math.acos(max(-1.0, min(1.0, dot_product)))
        # 右乘旋转需取负角度（关键修正）
        return RotationCalculator.axis_angle_to_rotation_matrix(rotation_axis, -angle)
#endregion



#region ZYX分解
    # 将旋转矩阵分解为ZYX顺序的欧拉角 (RX, RY, RZ)，返回值单位为弧度
    @staticmethod
    def rotation_matrix_to_zyx(
        rot_matrix: np.ndarray,
        current_rx: float = 0,
        current_ry: float = 0,
        current_rz: float = 0,
        joint_limit: float = math.pi  # 默认关节限制±π
    ) -> Tuple[float, float, float]:
        # 基础欧拉角计算逻辑
        base_solution = RotationCalculator._calculate_base_euler_angles_zyx(rot_matrix)
        rx, ry, rz = base_solution

        # 生成可能的等价解（考虑角度周期性）
        possible_solutions = RotationCalculator._generate_equivalent_solutions(rx, ry, rz, joint_limit)

        logger.info("世界系等价解集：")
        for angle in possible_solutions:
            logger.info(f"欧拉角: X={RotationCalculator.rad_to_deg(angle[0]):.4f}, Y={RotationCalculator.rad_to_deg(angle[1]):.4f}, Z={RotationCalculator.rad_to_deg(angle[2]):.4f}")

        # 选择与当前姿态差异最小的解
        return RotationCalculator._select_optimal_solution(possible_solutions, current_rx, current_ry, current_rz)

    # 基础ZYX欧拉角计算逻辑
    @staticmethod
    def _calculate_base_euler_angles_zyx(rot_matrix: np.ndarray) -> Tuple[float, float, float]:
        # 使用SVD分解正交化矩阵
        u, _, vt = np.linalg.svd(rot_matrix)
        orthogonal_matrix = u @ vt

        # 确保旋转矩阵行列式为1（右手坐标系）
        if np.linalg.det(orthogonal_matrix) < 0:
            vt[-1, :] *= -1
            orthogonal_matrix = u @ vt

        # 提取ZYX欧拉角
        if abs(orthogonal_matrix[2, 0]) < 1 - 1e-10:
            ry = -math.asin(orthogonal_matrix[2, 0])
            cos_ry = math.cos(ry)

            # 处理cosRy接近零的情况
            if abs(cos_ry) < 1e-10:
                rz = 0.0
                rx = 0.0
            else:
                rz = math.atan2(orthogonal_matrix[2, 1] / cos_ry, orthogonal_matrix[2, 2] / cos_ry)
                rx = math.atan2(orthogonal_matrix[1, 0] / cos_ry, orthogonal_matrix[0, 0] / cos_ry)
        else:
            # 奇异情况处理
            rx = 0.0
            if orthogonal_matrix[2, 0] < 0:
                ry = math.pi / 2
                rz = rx + math.atan2(orthogonal_matrix[0, 1], orthogonal_matrix[0, 2])
            else:
                ry = -math.pi / 2
                rz = -rx + math.atan2(-orthogonal_matrix[0, 1], -orthogonal_matrix[0, 2])

        return (rx, ry, rz)
#endregion



#region XYZ分解
    # 将旋转矩阵分解为XYZ顺序的欧拉角 (RX, RY, RZ)，返回值单位为弧度
    @staticmethod
    def rotation_matrix_to_xyz(
        rot_matrix: np.ndarray,
        current_rx: float = 0,
        current_ry: float = 0,
        current_rz: float = 0,
        joint_limit: float = math.pi  # 默认关节限制±π
    ) -> Tuple[float, float, float]:
        # 基础欧拉角计算逻辑
        base_solution = RotationCalculator._calculate_base_euler_angles_xyz(rot_matrix)
        rx, ry, rz = base_solution

        # 生成可能的等价解（考虑角度周期性）
        possible_solutions = RotationCalculator._generate_equivalent_solutions(rx, ry, rz, joint_limit)

        logger.info("工具系等价解集：")
        for angle in possible_solutions:
            logger.info(f"欧拉角: X={RotationCalculator.rad_to_deg(angle[0]):.4f}, Y={RotationCalculator.rad_to_deg(angle[1]):.4f}, Z={RotationCalculator.rad_to_deg(angle[2]):.4f}")

        # 选择与当前姿态差异最小的解
        return RotationCalculator._select_optimal_solution(possible_solutions, current_rx, current_ry, current_rz)

    # 基础XYZ欧拉角计算逻辑
    @staticmethod
    def _calculate_base_euler_angles_xyz(rot_matrix: np.ndarray) -> Tuple[float, float, float]:
        # 使用SVD分解正交化矩阵
        u, _, vt = np.linalg.svd(rot_matrix)
        orthogonal_matrix = u @ vt

        # 确保旋转矩阵行列式为1（右手坐标系）
        if np.linalg.det(orthogonal_matrix) < 0:
            vt[-1, :] *= -1
            orthogonal_matrix = u @ vt

        # 提取XYZ欧拉角
        if abs(orthogonal_matrix[0, 2]) < 1 - 1e-10:
            ry = math.asin(orthogonal_matrix[0, 2])
            cos_ry = math.cos(ry)

            # 处理cosRy接近零的情况
            if abs(cos_ry) < 1e-10:
                rz = 0.0
                rx = math.atan2(-orthogonal_matrix[2, 1], orthogonal_matrix[1, 1])
            else:
                rx = math.atan2(-orthogonal_matrix[1, 2] / cos_ry, orthogonal_matrix[2, 2] / cos_ry)
                rz = math.atan2(-orthogonal_matrix[0, 1] / cos_ry, orthogonal_matrix[0, 0] / cos_ry)
        else:
            # 奇异情况处理 - 改进：基于当前姿态延续趋势
            rz = 0.0
            if orthogonal_matrix[0, 2] > 0:
                ry = math.pi / 2
                # 保持rx趋势（使用当前值作为初始点）
                rx = rz + math.atan2(orthogonal_matrix[1, 0], orthogonal_matrix[2, 0])
            else:
                ry = -math.pi / 2
                # 保持rx趋势
                rx = -rz + math.atan2(-orthogonal_matrix[1, 0], -orthogonal_matrix[2, 0])

        return (rx, ry, rz)
#endregion



#region 等价解生成和选择
    # 生成等价解集合（考虑角度周期性和关节限制）
    @staticmethod
    def _generate_equivalent_solutions(
        rx: float, ry: float, rz: float, joint_limit: float
    ) -> List[Tuple[float, float, float]]:
        solutions = []

        # 基础解
        solutions.append((
            RotationCalculator._clamp_angle(rx, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(ry, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(rz, -joint_limit, joint_limit)
        ))

        # 考虑±2π的等价解
        solutions.append((
            RotationCalculator._clamp_angle(rx + 2 * math.pi, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(ry, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(rz, -joint_limit, joint_limit)
        ))

        solutions.append((
            RotationCalculator._clamp_angle(rx, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(ry + 2 * math.pi, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(rz, -joint_limit, joint_limit)
        ))

        solutions.append((
            RotationCalculator._clamp_angle(rx, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(ry, -joint_limit, joint_limit),
            RotationCalculator._clamp_angle(rz + 2 * math.pi, -joint_limit, joint_limit)
        ))

        return solutions

    # 选择与当前姿态差异最小的解
    @staticmethod
    def _select_optimal_solution(
        solutions: List[Tuple[float, float, float]],
        current_rx: float, current_ry: float, current_rz: float
    ) -> Tuple[float, float, float]:
        min_diff = float('inf')
        best_solution = None

        for sol in solutions:
            # 计算与当前姿态的平方差
            diff = (sol[0] - current_rx)**2 + \
                   (sol[1] - current_ry)** 2 + \
                   (sol[2] - current_rz)**2

            if diff < min_diff:
                min_diff = diff
                best_solution = sol

        logger.info("最佳解:")
        logger.info(f"欧拉角: X={RotationCalculator.rad_to_deg(best_solution[0]):.4f}, Y={RotationCalculator.rad_to_deg(best_solution[1]):.4f}, Z={RotationCalculator.rad_to_deg(best_solution[2]):.4f}")

        return best_solution

    # 角度规范化（将角度折叠到指定范围内）
    @staticmethod
    def _clamp_angle(angle: float, min_val: float, max_val: float) -> float:
        while angle < min_val:
            angle += 2 * math.pi
        while angle > max_val:
            angle -= 2 * math.pi
        return angle
    
#endregion



#region 主函数
    # 完整流程：计算旋转矩阵并应用于TCP，返回新的ZYX角度
    @staticmethod
    def tcp_rotation_calculation(
        calibration_z: np.ndarray,  # 相机坐标系下的标定Z轴
        measured_z: np.ndarray,
        tool: str = "nail_bumping",     # 相机坐标系下的测量Z轴
        tcp_rx: float=0, tcp_ry: float=0, tcp_rz: float=0, 
        is_use_tcp: bool = True
        
    ) -> Tuple[float, float, float]:
        # 转换为工具系


        # 修正矩阵
        if tool == "screw_sleeve":
            camera_rotation_matrix = np.array([
            [0, 1, 0],
            [-1, 0, 0],
            [0, 0, 1]
        ])
        elif tool == "nail_bumping":
            camera_rotation_matrix = np.array([
            [0, 1, 0],
            [-1, 0, 0],
            [0, 0, 1]
            ])
        else:
            raise ValueError("Invalid tool in FUN tcp_rotation_calculation!")

        calibration_z2 = camera_rotation_matrix @ np.array([calibration_z[0], calibration_z[1], calibration_z[2]])
        measured_z2 = camera_rotation_matrix @ np.array([measured_z[0], measured_z[1], measured_z[2]])

        r = RotationCalculator.get_rotation_matrix_from_z_axes(calibration_z2, measured_z2) 

        # TCP当前姿态的旋转矩阵（ZYX顺序）
        rx_rad = tcp_rx
        ry_rad = tcp_ry
        rz_rad = tcp_rz
        
        # X轴旋转矩阵
        rx_mat = np.array([
            [1, 0, 0],
            [0, math.cos(rx_rad), -math.sin(rx_rad)],
            [0, math.sin(rx_rad), math.cos(rx_rad)]
        ])
        
        # Y轴旋转矩阵
        ry_mat = np.array([
            [math.cos(ry_rad), 0, math.sin(ry_rad)],
            [0, 1, 0],
            [-math.sin(ry_rad), 0, math.cos(ry_rad)]
        ])
        
        # Z轴旋转矩阵
        rz_mat = np.array([
            [math.cos(rz_rad), -math.sin(rz_rad), 0],
            [math.sin(rz_rad), math.cos(rz_rad), 0],
            [0, 0, 1]
        ])
        
        tcp_rot_matrix = rx_mat @ ry_mat @ rz_mat  # ZYX顺序

        # 关键：TCP姿态右乘修正矩阵R（符合tcp_new = tcp * R）
        new_tcp_rot_matrix = tcp_rot_matrix @ r

        # 分解为ZYX欧拉角
        if is_use_tcp:
            logger.info(f"工具系下旋转矩阵为：\n{r}")
            return RotationCalculator.rotation_matrix_to_xyz(r)
        else:
            return RotationCalculator.rotation_matrix_to_xyz(new_tcp_rot_matrix)
#endregion