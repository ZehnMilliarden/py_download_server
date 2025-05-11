import os
import json
import threading
import tempfile
import shutil

class UploadManager:
    """上传管理器，处理文件上传和冲突检测"""
    
    def __init__(self, file_manager):
        """
        初始化上传管理器
        
        Args:
            file_manager: 文件管理器实例
        """
        self.file_manager = file_manager
        self.active_uploads = {}  # 活跃上传任务字典
        self.upload_mutex = threading.Lock()  # 上传互斥量
        
    def check_upload_conflicts(self, filenames, target_dir):
        """
        检查上传文件名冲突
        
        Args:
            filenames: 文件名列表
            target_dir: 目标目录
            
        Returns:
            dict: 检查结果，包含是否有冲突和冲突文件列表
        """
        conflicts = self.file_manager.check_conflicts(filenames, target_dir)
        
        # 检查是否有活跃上传任务使用相同文件名
        with self.upload_mutex:
            for filename in filenames:
                upload_path = os.path.join(target_dir, filename)
                if upload_path in self.active_uploads and filename not in conflicts:
                    conflicts.append(filename)
        
        return {
            'has_conflicts': len(conflicts) > 0,
            'conflicts': conflicts
        }
    
    def start_upload(self, filename, target_dir):
        """
        开始上传任务
        
        Args:
            filename: 文件名
            target_dir: 目标目录
            
        Returns:
            dict: 上传任务信息，包含临时文件路径和上传ID
        """
        upload_path = os.path.join(target_dir, filename)
        
        # 获取文件锁
        if not self.file_manager.acquire_lock(upload_path):
            raise ValueError(f"无法获取文件锁: {filename}")
        
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        upload_id = os.path.basename(temp_file.name)
        
        # 记录活跃上传任务
        with self.upload_mutex:
            self.active_uploads[upload_path] = {
                'id': upload_id,
                'temp_file': temp_file.name,
                'target_path': self.file_manager.get_absolute_path(upload_path),
                'filename': filename,
                'target_dir': target_dir
            }
        
        return {
            'upload_id': upload_id,
            'temp_file': temp_file.name
        }
    
    def append_chunk(self, upload_id, chunk_data):
        """
        追加上传数据块
        
        Args:
            upload_id: 上传ID
            chunk_data: 数据块
            
        Returns:
            bool: 是否成功
        """
        # 查找上传任务
        upload_info = None
        for info in self.active_uploads.values():
            if info['id'] == upload_id:
                upload_info = info
                break
        
        if not upload_info:
            raise ValueError(f"找不到上传任务: {upload_id}")
        
        # 写入数据块
        with open(upload_info['temp_file'], 'ab') as f:
            f.write(chunk_data)
        
        return True
    
    def complete_upload(self, upload_id):
        """
        完成上传任务
        
        Args:
            upload_id: 上传ID
            
        Returns:
            dict: 完成结果
        """
        # 查找上传任务
        upload_info = None
        upload_path = None
        
        with self.upload_mutex:
            for path, info in self.active_uploads.items():
                if info['id'] == upload_id:
                    upload_info = info
                    upload_path = path
                    break
        
        if not upload_info:
            raise ValueError(f"找不到上传任务: {upload_id}")
        
        # 移动临时文件到目标位置
        try:
            shutil.move(upload_info['temp_file'], upload_info['target_path'])
            
            # 清理上传任务
            with self.upload_mutex:
                del self.active_uploads[upload_path]
            
            # 释放文件锁
            self.file_manager.release_lock(upload_path)
            
            return {
                'success': True,
                'filename': upload_info['filename'],
                'path': upload_path
            }
        except Exception as e:
            # 出错时释放锁并清理
            self.file_manager.release_lock(upload_path)
            with self.upload_mutex:
                del self.active_uploads[upload_path]
            
            if os.path.exists(upload_info['temp_file']):
                os.unlink(upload_info['temp_file'])
                
            raise e
    
    def cancel_upload(self, upload_id):
        """
        取消上传任务
        
        Args:
            upload_id: 上传ID
            
        Returns:
            bool: 是否成功
        """
        # 查找上传任务
        upload_info = None
        upload_path = None
        
        with self.upload_mutex:
            for path, info in self.active_uploads.items():
                if info['id'] == upload_id:
                    upload_info = info
                    upload_path = path
                    break
        
        if not upload_info:
            raise ValueError(f"找不到上传任务: {upload_id}")
        
        # 清理临时文件
        if os.path.exists(upload_info['temp_file']):
            os.unlink(upload_info['temp_file'])
        
        # 清理上传任务
        with self.upload_mutex:
            del self.active_uploads[upload_path]
        
        # 释放文件锁
        self.file_manager.release_lock(upload_path)
        
        return True
