import os
import io
import time
import uuid
import json
import mimetypes
import threading
import zipfile
import tempfile
from datetime import datetime, timedelta

class DownloadManager:
    """下载管理器，处理文件下载、批量下载和进度跟踪"""
    
    # 下载状态常量
    STATUS_QUEUED = 'queued'      # 已加入队列
    STATUS_PREPARING = 'preparing'  # 准备中
    STATUS_DOWNLOADING = 'downloading'  # 下载中
    STATUS_COMPLETED = 'completed'  # 已完成
    STATUS_ERROR = 'error'       # 错误
    STATUS_CANCELLED = 'cancelled'  # 已取消
    
    # 临时文件过期时间（小时）
    TEMP_FILE_EXPIRY_HOURS = 2
    
    def __init__(self, file_manager):
        """
        初始化下载管理器
        
        Args:
            file_manager: 文件管理器实例
        """
        self.file_manager = file_manager
        # 下载队列字典 {session_id: {files: [], status: 'queued|processing|completed|error', ...}}
        self.download_queues = {}  
        self.queue_mutex = threading.Lock()  # 队列互斥量
        self.download_status = {}  # 下载状态信息 {download_id: status_info}
        self.status_mutex = threading.Lock()  # 状态互斥量
        self.zip_temp_files = {}  # 批量下载的临时zip文件 {download_id: temp_file_path}
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_task, daemon=True)
        self.cleanup_thread.start()
    
    def _cleanup_task(self):
        """清理任务，定期清理过期的下载和临时文件"""
        while self.running:
            try:
                now = datetime.now()
                expiry_time = now - timedelta(hours=self.TEMP_FILE_EXPIRY_HOURS)
                
                # 清理过期的下载状态
                with self.status_mutex:
                    for download_id in list(self.download_status.keys()):
                        status = self.download_status[download_id]
                        if 'creation_time' in status:
                            creation_time = datetime.fromtimestamp(status['creation_time'])
                            if creation_time < expiry_time:
                                # 过期了，清理
                                del self.download_status[download_id]
                
                # 清理过期的临时ZIP文件
                with self.status_mutex:
                    for download_id in list(self.zip_temp_files.keys()):
                        temp_file = self.zip_temp_files[download_id]
                        if os.path.exists(temp_file):
                            # 检查文件修改时间
                            mtime = os.path.getmtime(temp_file)
                            mtime_dt = datetime.fromtimestamp(mtime)
                            if mtime_dt < expiry_time:
                                try:
                                    os.unlink(temp_file)
                                    del self.zip_temp_files[download_id]
                                except Exception as e:
                                    print(f"清理临时文件错误: {str(e)}")
            except Exception as e:
                print(f"清理任务错误: {str(e)}")
            finally:
                # 每15分钟运行一次
                time.sleep(900)
    
    def cleanup(self):
        """清理资源，安全停止清理线程"""
        self.running = False
        if self.cleanup_thread.is_alive():
            self.cleanup_thread.join(2.0)  # 等待最多2秒
            
        # 清理临时文件
        with self.status_mutex:
            for download_id, temp_file in self.zip_temp_files.items():
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception as e:
                        print(f"清理临时文件错误: {str(e)}")
            self.zip_temp_files.clear()
        
    def start_download(self, rel_path, request_handler):
        """
        开始下载任务
        
        Args:
            rel_path: 相对路径
            request_handler: HTTP请求处理器
            
        Returns:
            bool: 是否成功
        """
        try:
            # 获取文件绝对路径
            abs_path = self.file_manager.get_absolute_path(rel_path)
            
            # 检查是否是文件
            if not os.path.isfile(abs_path):
                request_handler.send_error(404, "文件不存在或不是一个文件")
                return False
            
            # 获取文件信息
            file_size = os.path.getsize(abs_path)
            file_mtime = os.path.getmtime(abs_path)
            file_mtime_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_mtime))
            
            # 获取MIME类型
            content_type, encoding = mimetypes.guess_type(abs_path)
            if content_type is None:
                content_type = 'application/octet-stream'
            
            # 处理Range请求（断点续传）
            range_header = request_handler.headers.get('Range')
            start_range = 0
            end_range = file_size - 1
            
            if range_header and range_header.startswith('bytes='):
                ranges = range_header.replace('bytes=', '').split('-')
                if len(ranges) == 2:
                    if ranges[0]:  # 有起始位置
                        start_range = int(ranges[0])
                    if ranges[1]:  # 有结束位置
                        end_range = min(int(ranges[1]), file_size - 1)
            
            # 计算实际要发送的内容长度
            content_length = end_range - start_range + 1
            
            # 设置响应头
            if range_header:
                request_handler.send_response(206)  # Partial Content
                request_handler.send_header('Content-Range', f'bytes {start_range}-{end_range}/{file_size}')
            else:
                request_handler.send_response(200)
            
            request_handler.send_header('Content-Type', content_type)
            request_handler.send_header('Content-Length', str(content_length))
            request_handler.send_header('Accept-Ranges', 'bytes')  # 支持断点续传
            request_handler.send_header('Last-Modified', file_mtime_str)
            request_handler.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(abs_path)}"')
            request_handler.end_headers()
            
            # 如果是HEAD请求，不发送文件内容
            if request_handler.command == 'HEAD':
                return True
            
            # 发送文件内容
            with open(abs_path, 'rb') as f:
                f.seek(start_range)
                bytes_sent = 0
                chunk_size = 8192  # 8KB 块大小
                
                while bytes_sent < content_length:
                    remaining = content_length - bytes_sent
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    request_handler.wfile.write(chunk)
                    bytes_sent += len(chunk)
            
            return True
        
        except Exception as e:
            print(f"下载错误: {str(e)}")
            try:
                request_handler.send_error(500, f"下载错误: {str(e)}")
            except:
                pass
            return False
    
    def create_batch_download(self, rel_paths, folder_name=""):
        """
        创建批量下载任务，将多个文件打包为Zip
        
        Args:
            rel_paths: 相对路径列表
            folder_name: 文件夹名称（可选）
            
        Returns:
            dict: 下载任务信息
        """
        # 生成唯一下载 ID
        download_id = str(uuid.uuid4())
        now = time.time()
        
        # 保存当前时间作为创建时间
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 生成文件名
        if not folder_name:
            folder_name = f"download_{timestamp}"
        zip_filename = f"{folder_name}.zip"
        
        # 初始化下载状态
        status_info = {
            'id': download_id,
            'status': self.STATUS_QUEUED,
            'creation_time': now,
            'last_update': now,
            'rel_paths': rel_paths,
            'filename': zip_filename,
            'total_files': len(rel_paths),
            'processed_files': 0,
            'total_size': 0,
            'message': f"准备打包 {len(rel_paths)} 个文件"
        }
        
        # 存储状态信息
        with self.status_mutex:
            self.download_status[download_id] = status_info
        
        # 启动异步进程创建ZIP
        create_thread = threading.Thread(
            target=self._create_zip_file,
            args=(download_id, rel_paths, zip_filename),
            daemon=True
        )
        create_thread.start()
        
        return {
            'success': True,
            'download_id': download_id,
            'status': self.STATUS_QUEUED,
            'message': f"已将 {len(rel_paths)} 个文件加入下载队列"
        }
        
    def _create_zip_file(self, download_id, rel_paths, zip_filename):
        """
        创建 ZIP 文件的异步方法
        
        Args:
            download_id: 下载 ID
            rel_paths: 相对路径列表
            zip_filename: ZIP 文件名
        """
        try:
            # 更新状态为准备中
            self._update_download_status(download_id, self.STATUS_PREPARING, "正在准备文件...")
            
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_file.close()
            
            # 收集文件大小和检查文件存在
            total_size = 0
            valid_files = []
            for rel_path in rel_paths:
                try:
                    abs_path = self.file_manager.get_absolute_path(rel_path)
                    if os.path.isfile(abs_path):
                        size = os.path.getsize(abs_path)
                        total_size += size
                        valid_files.append((rel_path, abs_path))
                    else:
                        print(f"跳过非文件: {rel_path}")
                except Exception as e:
                    print(f"跳过无效文件 {rel_path}: {str(e)}")
            
            # 更新状态
            self._update_download_status(
                download_id, 
                self.STATUS_PREPARING, 
                f"准备压缩 {len(valid_files)} 个文件 ({self._format_size(total_size)})",
                total_size=total_size,
                total_files=len(valid_files)
            )
            
            # 创建 ZIP 文件
            with zipfile.ZipFile(temp_file.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                processed_files = 0
                
                for rel_path, abs_path in valid_files:
                    try:
                        # 更新状态
                        processed_files += 1
                        self._update_download_status(
                            download_id,
                            self.STATUS_DOWNLOADING,
                            f"正在压缩文件 ({processed_files}/{len(valid_files)}): {os.path.basename(rel_path)}",
                            processed_files=processed_files
                        )
                        
                        # 引用的zip中应该是文件的相对路径
                        archive_name = rel_path
                        if archive_name.startswith('/'):
                            archive_name = archive_name[1:]
                        
                        # 将文件添加到 ZIP
                        zip_file.write(abs_path, archive_name)
                        
                    except Exception as e:
                        print(f"添加文件到ZIP错误 {rel_path}: {str(e)}")
            
            # 存储临时文件信息
            with self.status_mutex:
                self.zip_temp_files[download_id] = temp_file.name
            
            # 更新完成状态
            self._update_download_status(
                download_id,
                self.STATUS_COMPLETED,
                f"打包完成: {len(valid_files)} 个文件 ({self._format_size(total_size)})",
                filename=zip_filename
            )
            
        except Exception as e:
            print(f"创建压缩文件错误: {str(e)}")
            self._update_download_status(download_id, self.STATUS_ERROR, f"创建压缩文件错误: {str(e)}")
    
    def _update_download_status(self, download_id, status, message, **kwargs):
        """更新下载状态"""
        with self.status_mutex:
            if download_id in self.download_status:
                # 更新状态和消息
                self.download_status[download_id]['status'] = status
                self.download_status[download_id]['message'] = message
                self.download_status[download_id]['last_update'] = time.time()
                
                # 更新其他字段
                for key, value in kwargs.items():
                    self.download_status[download_id][key] = value
    
    def get_download_status(self, download_id=None):
        """
        获取下载状态
        
        Args:
            download_id: 下载 ID，如果为空则返回所有下载的状态
            
        Returns:
            dict: 下载状态信息
        """
        with self.status_mutex:
            if download_id:
                # 返回指定下载的状态
                if download_id in self.download_status:
                    status = self.download_status[download_id].copy()  # 复制一份避免竞争
                    # 添加下载 URL，如果完成
                    if status['status'] == self.STATUS_COMPLETED and download_id in self.zip_temp_files:
                        status['download_url'] = f"/download-batch/{download_id}"
                    return status
                else:
                    return {'error': f"找不到下载任务: {download_id}"}
            else:
                # 返回所有下载的状态摘要
                result = []
                for id, status in self.download_status.items():
                    summary = {
                        'id': id,
                        'status': status['status'],
                        'message': status['message'],
                        'filename': status.get('filename', ''),
                        'creation_time': status.get('creation_time', 0),
                    }
                    # 添加下载 URL，如果完成
                    if status['status'] == self.STATUS_COMPLETED and id in self.zip_temp_files:
                        summary['download_url'] = f"/download-batch/{id}"
                    result.append(summary)
                return {'downloads': result}
    
    def serve_batch_download(self, download_id, request_handler):
        """
        提供批量下载文件
        
        Args:
            download_id: 下载 ID
            request_handler: HTTP 请求处理器
            
        Returns:
            bool: 是否成功
        """
        # 检查下载 ID 是否存在
        with self.status_mutex:
            if download_id not in self.download_status or download_id not in self.zip_temp_files:
                request_handler.send_error(404, "文件不存在或已过期")
                return False
            
            status = self.download_status[download_id]
            temp_file = self.zip_temp_files[download_id]
            filename = status.get('filename', f"download_{download_id}.zip")
        
        try:
            # 检查文件是否存在
            if not os.path.exists(temp_file):
                request_handler.send_error(404, "文件不存在或已过期")
                return False
            
            # 获取文件信息
            file_size = os.path.getsize(temp_file)
            
            # 处理 Range 请求（断点续传）
            range_header = request_handler.headers.get('Range')
            start_range = 0
            end_range = file_size - 1
            
            if range_header and range_header.startswith('bytes='):
                ranges = range_header.replace('bytes=', '').split('-')
                if len(ranges) == 2:
                    if ranges[0]:  # 有起始位置
                        start_range = int(ranges[0])
                    if ranges[1]:  # 有结束位置
                        end_range = min(int(ranges[1]), file_size - 1)
            
            # 计算实际要发送的内容长度
            content_length = end_range - start_range + 1
            
            # 设置响应头
            if range_header:
                request_handler.send_response(206)  # Partial Content
                request_handler.send_header('Content-Range', f'bytes {start_range}-{end_range}/{file_size}')
            else:
                request_handler.send_response(200)
            
            request_handler.send_header('Content-Type', 'application/zip')
            request_handler.send_header('Content-Length', str(content_length))
            request_handler.send_header('Accept-Ranges', 'bytes')  # 支持断点续传
            request_handler.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            request_handler.end_headers()
            
            # 如果是 HEAD 请求，不发送文件内容
            if request_handler.command == 'HEAD':
                return True
            
            # 发送文件内容
            with open(temp_file, 'rb') as f:
                f.seek(start_range)
                bytes_sent = 0
                chunk_size = 8192  # 8KB 块大小
                
                while bytes_sent < content_length:
                    remaining = content_length - bytes_sent
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    request_handler.wfile.write(chunk)
                    bytes_sent += len(chunk)
            
            return True
            
        except Exception as e:
            print(f"提供批量下载错误: {str(e)}")
            try:
                request_handler.send_error(500, f"下载错误: {str(e)}")
            except:
                pass
            return False
    
    def cancel_download(self, download_id):
        """
        取消下载任务
        
        Args:
            download_id: 下载 ID
            
        Returns:
            dict: 取消结果
        """
        with self.status_mutex:
            if download_id not in self.download_status:
                return {'success': False, 'message': f"找不到下载任务: {download_id}"}
            
            # 更新状态
            self.download_status[download_id]['status'] = self.STATUS_CANCELLED
            self.download_status[download_id]['message'] = "下载已取消"
            
            # 清理临时文件
            if download_id in self.zip_temp_files:
                temp_file = self.zip_temp_files[download_id]
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception as e:
                        print(f"删除临时文件错误: {str(e)}")
                del self.zip_temp_files[download_id]
            
            return {'success': True, 'message': "下载已成功取消"}
    
    def _format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"
    
    def get_queue_status(self, session_id):
        """
        获取队列状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            dict: 队列状态
        """
        with self.download_mutex:
            if session_id not in self.active_downloads:
                return {
                    'session_id': session_id,
                    'exists': False
                }
            
            session = self.active_downloads[session_id]
            return {
                'session_id': session_id,
                'exists': True,
                'queue_length': len(session['queue']),
                'current': session['current'],
                'completed': len(session['completed'])
            }
    
    def clear_queue(self, session_id):
        """
        清空下载队列
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否成功
        """
        with self.download_mutex:
            if session_id in self.active_downloads:
                del self.active_downloads[session_id]
                return True
            return False
