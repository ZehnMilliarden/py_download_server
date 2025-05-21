import os
import time
import threading
import urllib.parse
import shutil
from pathlib import Path
from datetime import datetime

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
        
        # 确保根目录存在
        os.makedirs(self.root_dir, exist_ok=True)
        
        print(f"工作目录: {self.root_dir}")
    
    def validate_path(self, path):
        """
        验证路径是否在根目录下
        
        Args:
            path: 要验证的路径
            
        Returns:
            bool: 路径是否有效
        """
        # 统一路径格式
        abs_path = os.path.abspath(path)
        # 在Windows上不区分大小写比较路径
        if os.name == 'nt':
            return abs_path.lower().startswith(self.root_dir.lower())
        return abs_path.startswith(self.root_dir)
    
    def get_absolute_path(self, rel_path):
        """
        获取相对路径对应的绝对路径
        
        Args:
            rel_path: 相对路径
            
        Returns:
            str: 绝对路径
        """
        # 处理空路径
        if not rel_path or rel_path == '/':
            return self.root_dir
            
        # 解码URL编码的路径
        decoded_path = urllib.parse.unquote(rel_path)
        # 移除开头的斜杠
        if decoded_path.startswith('/'):
            decoded_path = decoded_path[1:]
        # 规范化路径，处理 .. 和 . 等
        norm_path = os.path.normpath(decoded_path)
        # 拼接绝对路径
        abs_path = os.path.normpath(os.path.join(self.root_dir, norm_path))
        
        # 验证路径是否在根目录下
        if not self.validate_path(abs_path):
            raise ValueError(f"路径 {abs_path} 不在根目录 {self.root_dir} 下")
            
        return abs_path
    
    def get_relative_path(self, abs_path):
        """
        获取绝对路径对应的相对路径（相对于根目录）
        
        Args:
            abs_path: 绝对路径
            
        Returns:
            str: 相对路径
        """
        try:
            # 确保路径格式一致
            norm_path = os.path.normpath(abs_path)
            # 验证路径是否在根目录下
            if not self.validate_path(norm_path):
                raise ValueError(f"路径 {norm_path} 不在根目录 {self.root_dir} 下")
                
            # 计算相对路径
            rel_path = os.path.relpath(norm_path, self.root_dir)
            # 将Windows反斜杠转换为Web正斜杠
            web_path = rel_path.replace("\\", "/")
            # 处理根目录的情况
            if web_path == ".":
                return ""
            return web_path
        except Exception as e:
            print(f"获取相对路径错误: {str(e)}")
            return ""
    
    def list_directory(self, path):
        """
        列出目录内容
        
        Args:
            path: 目录路径
            
        Returns:
            list: 目录内容列表，包含文件和目录信息
        """
        abs_path = self.get_absolute_path(path)
        
        if not os.path.exists(abs_path):
            raise ValueError(f"路径 {abs_path} 不存在")
            
        if not os.path.isdir(abs_path):
            raise ValueError(f"{abs_path} 不是一个目录")
            
        items = []
        try:
            # 列出目录内容
            for item in os.listdir(abs_path):
                try:
                    item_path = os.path.join(abs_path, item)
                    stat_info = os.stat(item_path)
                    is_dir = os.path.isdir(item_path)
                    size = 0 if is_dir else stat_info.st_size
                    mtime = stat_info.st_mtime
                    mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 文件扩展名
                    ext = os.path.splitext(item)[1].lower()[1:] if not is_dir else ''
                    
                    items.append({
                        'name': item,
                        'is_dir': is_dir,
                        'size': size,
                        'ext': ext,
                        'mtime': mtime,
                        'mtime_str': mtime_str
                    })
                except (PermissionError, OSError) as e:
                    # 记录无法访问的项
                    print(f"无法访问 {item_path}: {str(e)}")
                    items.append({
                        'name': item,
                        'is_dir': False,
                        'size': 0,
                        'ext': '',
                        'mtime': 0,
                        'mtime_str': '无法访问',
                        'error': str(e)
                    })
        except PermissionError as e:
            print(f"无法列出目录 {abs_path}: {str(e)}")
            raise ValueError(f"无法访问目录 {path}: 权限不足")
            
        return items
    
    def create_directory(self, rel_path):
        """
        创建目录
        
        Args:
            rel_path: 相对路径
            
        Returns:
            bool: 是否成功创建目录
        """
        try:
            abs_path = self.get_absolute_path(rel_path)
            if os.path.exists(abs_path):
                if os.path.isdir(abs_path):
                    return True  # 目录已存在
                else:
                    return False  # 同名文件存在
            
            os.makedirs(abs_path, exist_ok=True)
            return True
        except Exception as e:
            print(f"创建目录错误: {str(e)}")
            return False
    
    def delete_item(self, rel_path):
        """
        删除文件或目录
        
        Args:
            rel_path: 相对路径
            
        Returns:
            bool: 是否成功删除
        """
        try:
            abs_path = self.get_absolute_path(rel_path)
            
            # 检查路径是否存在
            if not os.path.exists(abs_path):
                return True  # 视为删除成功
                
            # 检查是否是文件
            if os.path.isfile(abs_path):
                os.remove(abs_path)
                return True
                
            # 是目录，使用shutil.rmtree递归删除
            shutil.rmtree(abs_path)
            return True
        except Exception as e:
            print(f"删除项目错误: {str(e)}")
            return False
    
    def rename_item(self, old_rel_path, new_name):
        """
        重命名文件或目录
        
        Args:
            old_rel_path: 原相对路径
            new_name: 新名称（不包含路径）
            
        Returns:
            bool: 是否成功重命名
        """
        try:
            old_abs_path = self.get_absolute_path(old_rel_path)
            
            # 获取父目录
            parent_dir = os.path.dirname(old_abs_path)
            # 拼接新路径
            new_abs_path = os.path.join(parent_dir, new_name)
            
            # 检查新路径是否已存在
            if os.path.exists(new_abs_path):
                return False
                
            # 重命名
            os.rename(old_abs_path, new_abs_path)
            return True
        except Exception as e:
            print(f"重命名项目错误: {str(e)}")
            return False
    
    def move_item(self, src_rel_path, dst_rel_path):
        """
        移动文件或目录
        
        Args:
            src_rel_path: 源相对路径
            dst_rel_path: 目标相对路径
            
        Returns:
            bool: 是否成功移动
        """
        try:
            src_abs_path = self.get_absolute_path(src_rel_path)
            dst_abs_path = self.get_absolute_path(dst_rel_path)
            
            # 检查源路径是否存在
            if not os.path.exists(src_abs_path):
                return False
                
            # 检查目标路径是否已存在
            if os.path.exists(dst_abs_path):
                return False
                
            # 确保目标目录存在
            os.makedirs(os.path.dirname(dst_abs_path), exist_ok=True)
            
            # 移动
            shutil.move(src_abs_path, dst_abs_path)
            return True
        except Exception as e:
            print(f"移动项目错误: {str(e)}")
            return False
    
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
