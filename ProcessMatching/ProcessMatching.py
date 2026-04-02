import logging
import sys, os
from typing import Dict, Tuple, List
from fuzzywuzzy import fuzz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.logger_utils import logger, logger2



class ProcessMatching:
    """流程匹配处理类：支持多流程匹配与内容拼接"""
    def __init__(self, flow_dir: str):
        self.flow_dir = flow_dir
        self._init_flow_directory()
        self.strong_mapping = self._initialize_strong_mapping()
        self.fuzzy_threshold = 80  # 模糊匹配阈值
        self.logger = logger

    def _init_flow_directory(self) -> None:
        """初始化流程文件目录（若不存在则创建）"""
        os.makedirs(self.flow_dir, exist_ok=True)


    def _initialize_strong_mapping(self) -> Dict[Tuple[str, ...], str]:
        """初始化强匹配关键词映射表（支持多流程）"""
        return {
            ("深度调整",): "深度调整流程.txt",
            ("角度调整",): "角度调整流程.txt",
            ("位置调整",): "位置调整流程.txt",
            ("螺钉调整",): "螺钉调整流程.txt",
            ("位置标定", "十字交叉点标定"): "位置标定流程.txt",
            ("深度标定",): "深度标定流程.txt",
            ("角度标定",): "角度标定流程.txt",
            ("螺钉标定",): "螺钉标定流程.txt",
            ("到初始点", "回家"): "到初始点流程.txt",
            ("记录点'name'", "记录"): "记录点流程.txt",
            ("到记录点'name'","到点"): "到记录点流程.txt",
            ("连接",): "连接流程.txt",
            ("screw-demo", "拧螺套演示"): "拧螺套演示流程.txt",
            # 支持一个关键词对应多个流程
            ("校准",): ["位置调整流程.txt", "角度调整流程.txt"],  
        }

    def load_flow_content(self, filename: str) -> str:
        """加载指定流程文件的内容"""
        file_path = os.path.join(self.flow_dir, filename)
        if not os.path.exists(file_path):
            self.logger.info(f"流程文件 {filename} 不存在")
            return ""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def _strong_match(self, query: str) -> List[str]:
        """强匹配：返回所有匹配的流程文件名（支持多流程）"""
        matched_files = []
        query_lower = query.lower().strip()
        for keywords, filename in self.strong_mapping.items():
            # 只要查询中包含任一关键词即匹配
            if any(keyword.lower() in query_lower for keyword in keywords):
                if isinstance(filename, list):
                    matched_files.extend(filename)
                else:
                    matched_files.append(filename)

        # 去重并保持顺序
        return list(dict.fromkeys(matched_files))

    def _fuzzy_match(self, query: str) -> List[str]:
        """模糊匹配：返回所有匹配的流程文件名（支持多流程）"""
        matched_files = []
        best_scores = {}  # 记录每个文件的最高匹配分
        query_lower = query.lower()
        
        for keywords, filename in self.strong_mapping.items():
            for keyword in keywords:
                score = fuzz.partial_ratio(keyword.lower(), query_lower)
                # 处理“多流程列表”的情况
                if isinstance(filename, list):
                    for file in filename:
                        if file not in best_scores or score > best_scores[file]:
                            best_scores[file] = score
                else:
                    if filename not in best_scores or score > best_scores[filename]:
                        best_scores[filename] = score
        
        # 筛选出符合阈值的文件并按分数排序
        sorted_files = sorted(
            best_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        for file, score in sorted_files:
            if score >= self.fuzzy_threshold:
                matched_files.append(file)

        return matched_files

    def get_matched_flow(self, query: str) -> str:
        """主匹配方法：先强匹配后模糊匹配，返回多流程拼接内容"""
        # 1. 强匹配（优先级更高）
        strong_matched = self._strong_match(query)
        # 2. 模糊匹配（补充强匹配未覆盖的结果）
        fuzzy_matched = self._fuzzy_match(query)
        # 3. 合并结果（去重，强匹配结果在前）
        all_matched = strong_matched + [f for f in fuzzy_matched if f not in strong_matched]
        
        # 4. 加载并拼接所有匹配的流程内容
        combined_content = ""
        for filename in all_matched:
            content = self.load_flow_content(filename)
            if content:
                combined_content += f"\n\n=== {filename} ===\n{content}\n"
        
        # 5. 返回结果（去除首尾空行）
        result = combined_content.strip()
        if result:
            self.logger.info(f"匹配到 {len(all_matched)} 个流程,分别为{all_matched}")
        else:
            self.logger.info("未匹配到相关流程")
        return result
