import time
import threading
from datetime import datetime
import os

class DateBasedLogger:
    def __init__(self, base_name="default", file_name="application.log"):
        # 定义文件夹路径
        folder_name = "logs"
        full_dir = os.path.join(folder_name, base_name)

        # 如果完整路径不存在，则创建
        if not os.path.exists(full_dir):
            os.makedirs(full_dir, exist_ok=True)

        # 使用固定文件名
        self.file_path = os.path.join(full_dir, file_name)
        self.lock = threading.Lock()
        
    def write_log(self, message, level="INFO"):
        """写入日志到文件，包含时间戳和日志级别"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        # 确保多线程环境下日志写入安全
        with self.lock:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
                f.flush()
        
    def info(self, message):
        self.write_log(message, "INFO")
        
    def error(self, message):
        self.write_log(message, "ERROR")
        
    def debug(self, message):
        self.write_log(message, "DEBUG")
    
    def warning(self, message):
        self.write_log(message, "WARNING")

# 创建2个独立的日志实例，供直接导入使用
logger = DateBasedLogger("default", "application.log")
logger2 = DateBasedLogger("default", "AImodel.log")