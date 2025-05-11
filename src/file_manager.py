import os
import time
import threading
import urllib.parse
from pathlib import Path

class FileManager:
    """文件管理器，处理文件操作和路径管理"""
    
    def __init__(self, root_dir):
        """
        初始化文件管理器
        
        Args:
            root_dir: 根目录路径
        """
        self.root_dir = os.path.abspath(root_dir)
        self.locks = {}  # 文件锁字典
        self.lock_mutex = threading.Lock()  # 锁互斥量
        
    def validate_path(self, path):
        """
        验证路径是否在根目录下
        
        Args:
            path: 要验证的路径
            
        Returns:
            bool: 路径是否有效
        """
        abs_path = os.path.abspath(path)
        return abs_path.startswith(self.root_dir)
    
    def get_absolute_path(self, rel_path):
        """
        获取相对路径对应的绝对路径
        
        Args:
            rel_path: 相对路径
            
        Returns:
            str: 绝对路径
        """
        # 解码URL编码的路径
        decoded_path = urllib.parse.unquote(rel_path)
        # 规范化路径（处理 .. 和 . 等）
        norm_path = os.path.normpath(decoded_path).lstrip('/')
        # 拼接绝对路径
        abs_path = os.path.join(self.root_dir, norm_path)
        
        # 验证路径是否在根目录下
        if not self.validate_path(abs_path):
            raise ValueError(f"路径 {abs_path} 不在根目录 {self.root_dir} 下")
            
        return abs_path
    
    def list_directory(self, path):
        """
        列出目录内容
        
        Args:
            path: 目录路径
            
        Returns:
            list: 目录内容列表，包含文件和目录信息
        """
        abs_path = self.get_absolute_path(path)
        if not os.path.isdir(abs_path):
            raise ValueError(f"{abs_path} 不是一个目录")
            
        items = []
        for item in os.listdir(abs_path):
            item_path = os.path.join(abs_path, item)
            is_dir = os.path.isdir(item_path)
            size = 0 if is_dir else os.path.getsize(item_path)
            mtime = os.path.getmtime(item_path)
            
            items.append({
                'name': item,
                'is_dir': is_dir,
                'size': size,
                'mtime': mtime,
                'mtime_str': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
            })
            
        return items
    
    def acquire_lock(self, filename):
        """
        获取文件锁
        
        Args:
            filename: 文件名
            
        Returns:
            bool: 是否成功获取锁
        """
        with self.lock_mutex:
            if filename in self.locks:
                return False
            self.locks[filename] = threading.Lock()
            self.locks[filename].acquire()
            return True
    
    def release_lock(self, filename):
        """
        释放文件锁
        
        Args:
            filename: 文件名
        """
        with self.lock_mutex:
            if filename in self.locks:
                self.locks[filename].release()
                del self.locks[filename]
    
    def check_file_exists(self, rel_path):
        """
        检查文件是否存在
        
        Args:
            rel_path: 相对路径
            
        Returns:
            bool: 文件是否存在
        """
        try:
            abs_path = self.get_absolute_path(rel_path)
            return os.path.exists(abs_path) and os.path.isfile(abs_path)
        except ValueError:
            return False
    
    def check_conflicts(self, filenames, target_dir):
        """
        检查文件名冲突
        
        Args:
            filenames: 文件名列表
            target_dir: 目标目录
            
        Returns:
            list: 冲突的文件名列表
        """
        conflicts = []
        for filename in filenames:
            rel_path = os.path.join(target_dir, filename)
            if self.check_file_exists(rel_path) or filename in self.locks:
                conflicts.append(filename)
                
        return conflicts
