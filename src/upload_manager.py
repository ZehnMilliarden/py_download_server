import os
import time
import uuid
import json
import tempfile
import threading
import shutil
from datetime import datetime

class UploadManager:
    """上传管理器，处理文件上传、进度跟踪和冲突检测"""
    
    def __init__(self, file_manager):
        """
        初始化上传管理器
        
        Args:
            file_manager: 文件管理器实例
        """
        self.file_manager = file_manager
        self.active_uploads = {}  # 活跃上传任务字典 {upload_id: upload_info}
        self.upload_mutex = threading.Lock()  # 上传互斥量
        self.upload_progress = {}  # 上传进度信息 {upload_id: progress_info}
        self.status_updater = threading.Thread(target=self._update_status, daemon=True)
        self.status_updater.start()
        self.running = True
        
    def _update_status(self):
        """后台线程，更新上传状态和进度"""
        while self.running:
            try:
                with self.upload_mutex:
                    # 更新每个上传的状态
                    for upload_id, info in self.active_uploads.items():
                        # 如果存在临时文件，计算当前大小
                        if 'temp_file' in info and os.path.exists(info['temp_file']):
                            current_size = os.path.getsize(info['temp_file'])
                            # 更新进度信息
                            if upload_id in self.upload_progress:
                                progress = self.upload_progress[upload_id]
                                # 计算速度
                                if 'last_update' in progress and 'last_size' in progress:
                                    elapsed = time.time() - progress['last_update']
                                    if elapsed > 0:
                                        size_diff = current_size - progress['last_size']
                                        speed = size_diff / elapsed
                                        progress['speed'] = speed
                                # 更新大小和时间
                                progress['last_size'] = current_size
                                progress['last_update'] = time.time()
                                # 计算进度百分比
                                if 'total_size' in progress and progress['total_size'] > 0:
                                    progress['percent'] = min(100, (current_size / progress['total_size']) * 100)
            except Exception as e:
                print(f"更新上传状态错误: {str(e)}")
            finally:
                time.sleep(0.5)  # 每500毫秒更新一次
    
    def cleanup(self):
        """清理资源，停止状态更新线程"""
        self.running = False
        if self.status_updater.is_alive():
            self.status_updater.join(2.0)  # 等待最多2秒
            
        # 清理所有活跃的上传
        with self.upload_mutex:
            for upload_id, info in list(self.active_uploads.items()):
                try:
                    if 'temp_file' in info and os.path.exists(info['temp_file']):
                        os.unlink(info['temp_file'])
                    if 'path' in info and info['path'] in self.file_manager.locks:
                        self.file_manager.release_lock(info['path'])
                except Exception as e:
                    print(f"清理上传任务错误: {str(e)}")
    
    def check_upload_conflicts(self, filenames, target_dir):
        """
        检查上传文件名冲突
        
        Args:
            filenames: 文件名列表
            target_dir: 目标目录
            
        Returns:
            dict: 检查结果，包含是否有冲突和冲突文件列表
        """
        # 转换目录分隔符为系统适用的格式
        target_dir = target_dir.replace('/', os.path.sep)
        
        conflicts = self.file_manager.check_conflicts(filenames, target_dir)
        
        # 检查是否有活跃上传任务使用相同文件名
        with self.upload_mutex:
            for upload_id, info in self.active_uploads.items():
                if 'filename' in info and 'target_dir' in info:
                    if info['filename'] in filenames and info['target_dir'] == target_dir:
                        if info['filename'] not in conflicts:
                            conflicts.append(info['filename'])
        
        return {
            'has_conflicts': len(conflicts) > 0,
            'conflicts': conflicts
        }
    
    def start_upload(self, filename, target_dir, file_size=0, overwrite=False):
        """
        开始上传任务
        
        Args:
            filename: 文件名
            target_dir: 目标目录
            file_size: 文件大小（字节）
            overwrite: 如果存在是否覆盖
            
        Returns:
            dict: 上传任务信息，包含上传ID和状态
        """
        # 规范化目录路径
        target_dir = target_dir.replace('/', os.path.sep).strip()
        # 生成相对路径
        rel_path = os.path.join(target_dir, filename)
        
        # 检查文件是否存在
        if not overwrite and self.file_manager.check_file_exists(rel_path):
            raise ValueError(f"文件已存在: {rel_path}")
        
        # 确保目录存在
        abs_dir = self.file_manager.get_absolute_path(target_dir)
        if not os.path.exists(abs_dir):
            os.makedirs(abs_dir, exist_ok=True)
        
        # 获取文件锁
        if not self.file_manager.acquire_lock(rel_path):
            raise ValueError(f"无法获取文件锁: {filename}")
        
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        upload_id = str(uuid.uuid4())  # 使用UUID生成唯一ID
        temp_path = temp_file.name
        temp_file.close()
        
        # 算出目标路径
        target_path = self.file_manager.get_absolute_path(rel_path)
        
        # 记录上传信息
        now = time.time()
        upload_info = {
            'id': upload_id,
            'temp_file': temp_path,
            'target_path': target_path,
            'filename': filename,
            'target_dir': target_dir,
            'rel_path': rel_path,
            'size': file_size,
            'start_time': now,
            'last_activity': now,
            'status': 'started'
        }
        
        # 初始化进度信息
        progress_info = {
            'total_size': file_size,
            'uploaded_size': 0,
            'last_size': 0,
            'last_update': now,
            'speed': 0,
            'percent': 0,
            'status': 'started',
            'filename': filename,
            'target_dir': target_dir,
            'rel_path': rel_path
        }
        
        # 更新数据结构
        with self.upload_mutex:
            self.active_uploads[upload_id] = upload_info
            self.upload_progress[upload_id] = progress_info
        
        return {
            'upload_id': upload_id,
            'status': 'started',
            'filename': filename,
            'target_dir': target_dir,
            'rel_path': rel_path
        }
    
    def append_chunk(self, upload_id, chunk_data):
        """
        追加上传数据块
        
        Args:
            upload_id: 上传ID
            chunk_data: 数据块
            
        Returns:
            dict: 进度信息
        """
        # 获取上传信息
        with self.upload_mutex:
            if upload_id not in self.active_uploads:
                raise ValueError(f"找不到上传任务: {upload_id}")
            
            upload_info = self.active_uploads[upload_id]
            
            # 检查上传状态
            if upload_info['status'] == 'completed' or upload_info['status'] == 'cancelled':
                raise ValueError(f"上传任务已{upload_info['status']}，不能继续上传")
            
            # 更新上传状态
            upload_info['status'] = 'uploading'
            upload_info['last_activity'] = time.time()
        
        # 获取待写入的临时文件
        temp_file = upload_info['temp_file']
        
        # 计算当前进度
        chunk_size = len(chunk_data)
        new_size = 0
        
        try:
            # 写入数据块
            with open(temp_file, 'ab') as f:
                f.write(chunk_data)
            
            # 获取新的文件大小
            new_size = os.path.getsize(temp_file)
            
            # 更新进度信息
            with self.upload_mutex:
                if upload_id in self.upload_progress:
                    progress = self.upload_progress[upload_id]
                    now = time.time()
                    
                    # 更新上传大小
                    progress['uploaded_size'] = new_size
                    
                    # 计算速度
                    if 'last_update' in progress:
                        elapsed = now - progress['last_update']
                        if elapsed > 0:
                            speed = chunk_size / elapsed
                            # 平滑速度显示
                            if 'speed' in progress and progress['speed'] > 0:
                                progress['speed'] = (progress['speed'] * 0.7) + (speed * 0.3)
                            else:
                                progress['speed'] = speed
                    
                    # 更新其他字段
                    progress['last_size'] = new_size
                    progress['last_update'] = now
                    progress['status'] = 'uploading'
                    
                    # 计算上传进度
                    if progress['total_size'] > 0:
                        progress['percent'] = min(99, (new_size / progress['total_size']) * 100)
                    else:
                        progress['percent'] = 0
                    
                    return {
                        'upload_id': upload_id,
                        'status': 'uploading',
                        'uploaded': new_size,
                        'total': progress['total_size'],
                        'percent': progress['percent'],
                        'speed': progress['speed']
                    }
        except Exception as e:
            print(f"追加数据块错误: {str(e)}")
            raise e
        
        # 如果无法获取进度信息，返回基本信息
        return {
            'upload_id': upload_id,
            'status': 'uploading',
            'uploaded': new_size
        }
    
    def complete_upload(self, upload_id):
        """
        完成上传任务
        
        Args:
            upload_id: 上传ID
            
        Returns:
            dict: 完成结果
        """
        # 查找上传任务
        with self.upload_mutex:
            if upload_id not in self.active_uploads:
                raise ValueError(f"找不到上传任务: {upload_id}")
                
            upload_info = self.active_uploads[upload_id]
            rel_path = upload_info['rel_path']
            
            # 检查上传状态
            if upload_info['status'] == 'completed':
                return {
                    'success': True,
                    'status': 'completed',
                    'filename': upload_info['filename'],
                    'rel_path': rel_path,
                    'message': '文件已完成上传'
                }
                
            if upload_info['status'] == 'cancelled':
                raise ValueError(f"上传任务已取消: {upload_id}")
                
            # 更新上传状态
            upload_info['status'] = 'completing'
            
            # 更新进度状态
            if upload_id in self.upload_progress:
                self.upload_progress[upload_id]['status'] = 'completing'
        
        # 获取临时文件和目标路径
        temp_file = upload_info['temp_file']
        target_path = upload_info['target_path']
        filename = upload_info['filename']
        
        # 检查临时文件是否存在
        if not os.path.exists(temp_file):
            # 清理资源
            self._clean_upload(upload_id)
            raise ValueError(f"上传文件丢失: {filename}")
        
        try:
            # 确保目标目录存在
            target_dir = os.path.dirname(target_path)
            os.makedirs(target_dir, exist_ok=True)
            
            # 移动临时文件到目标位置
            shutil.move(temp_file, target_path)
            
            # 获取完成时的文件尺寸
            final_size = os.path.getsize(target_path) if os.path.exists(target_path) else 0
            
            # 更新进度和状态
            with self.upload_mutex:
                if upload_id in self.upload_progress:
                    progress = self.upload_progress[upload_id]
                    progress['status'] = 'completed'
                    progress['uploaded_size'] = final_size
                    progress['percent'] = 100
                    
                # 更新上传状态
                if upload_id in self.active_uploads:
                    self.active_uploads[upload_id]['status'] = 'completed'
            
            # 释放文件锁
            self.file_manager.release_lock(rel_path)
            
            return {
                'success': True,
                'status': 'completed',
                'filename': filename,
                'rel_path': rel_path,
                'size': final_size
            }
        except Exception as e:
            print(f"完成上传错误: {str(e)}")
            # 清理资源
            self._clean_upload(upload_id)
            raise ValueError(f"完成上传错误: {str(e)}")
    
    def _clean_upload(self, upload_id):
        """清理上传相关资源"""
        with self.upload_mutex:
            if upload_id in self.active_uploads:
                upload_info = self.active_uploads[upload_id]
                
                # 清理临时文件
                if 'temp_file' in upload_info and os.path.exists(upload_info['temp_file']):
                    try:
                        os.unlink(upload_info['temp_file'])
                    except Exception as e:
                        print(f"清理临时文件错误: {str(e)}")
                
                # 释放文件锁
                if 'rel_path' in upload_info:
                    self.file_manager.release_lock(upload_info['rel_path'])
                
                # 移除上传任务
                del self.active_uploads[upload_id]
                
            # 清理进度信息
            if upload_id in self.upload_progress:
                del self.upload_progress[upload_id]
    
    def cancel_upload(self, upload_id):
        """
        取消上传任务
        
        Args:
            upload_id: 上传ID
            
        Returns:
            dict: 取消结果
        """
        # 查找上传任务
        with self.upload_mutex:
            if upload_id not in self.active_uploads:
                return {'success': False, 'message': f"找不到上传任务: {upload_id}"}
                
            upload_info = self.active_uploads[upload_id]
            filename = upload_info['filename']
            
            # 检查上传状态
            if upload_info['status'] == 'completed':
                return {'success': False, 'message': f"上传任务已完成，无法取消: {filename}"}
                
            if upload_info['status'] == 'cancelled':
                return {'success': True, 'message': f"上传任务已取消: {filename}"}
                
            # 更新状态
            upload_info['status'] = 'cancelling'
            
            # 更新进度状态
            if upload_id in self.upload_progress:
                self.upload_progress[upload_id]['status'] = 'cancelling'
        
        try:
            # 调用清理函数清理上传相关资源
            self._clean_upload(upload_id)
            
            return {
                'success': True,
                'status': 'cancelled',
                'message': f"上传任务已成功取消: {filename}"
            }
        except Exception as e:
            print(f"取消上传错误: {str(e)}")
            return {
                'success': False,
                'status': 'error',
                'message': f"取消上传时出错: {str(e)}"
            }
    
    def get_upload_progress(self, upload_id=None):
        """
        获取上传进度
        
        Args:
            upload_id: 上传ID，如果为空则返回所有上传的进度
            
        Returns:
            dict: 上传进度信息
        """
        with self.upload_mutex:
            if upload_id:
                # 返回指定上传的进度
                if upload_id in self.upload_progress:
                    progress = self.upload_progress[upload_id]
                    return {
                        'upload_id': upload_id,
                        'filename': progress.get('filename', ''),
                        'status': progress.get('status', 'unknown'),
                        'total_size': progress.get('total_size', 0),
                        'uploaded_size': progress.get('uploaded_size', 0),
                        'percent': progress.get('percent', 0),
                        'speed': progress.get('speed', 0)
                    }
                else:
                    return {'error': f"找不到上传任务: {upload_id}"}
            else:
                # 返回所有上传的进度
                result = []
                for id, progress in self.upload_progress.items():
                    result.append({
                        'upload_id': id,
                        'filename': progress.get('filename', ''),
                        'status': progress.get('status', 'unknown'),
                        'total_size': progress.get('total_size', 0),
                        'uploaded_size': progress.get('uploaded_size', 0),
                        'percent': progress.get('percent', 0),
                        'speed': progress.get('speed', 0)
                    })
                return {'uploads': result}
