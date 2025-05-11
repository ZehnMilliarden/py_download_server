import os
import time
import threading
import mimetypes

class DownloadManager:
    """下载管理器，处理文件下载和断点续传"""
    
    def __init__(self, file_manager):
        """
        初始化下载管理器
        
        Args:
            file_manager: 文件管理器实例
        """
        self.file_manager = file_manager
        self.active_downloads = {}  # 活跃下载任务字典
        self.download_mutex = threading.Lock()  # 下载互斥量
        
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
    
    def add_to_queue(self, rel_paths, session_id):
        """
        添加到下载队列
        
        Args:
            rel_paths: 相对路径列表
            session_id: 会话ID
            
        Returns:
            dict: 队列信息
        """
        with self.download_mutex:
            # 初始化会话队列
            if session_id not in self.active_downloads:
                self.active_downloads[session_id] = {
                    'queue': [],
                    'current': None,
                    'completed': []
                }
            
            # 检查每个文件是否存在且是文件
            valid_paths = []
            for path in rel_paths:
                try:
                    abs_path = self.file_manager.get_absolute_path(path)
                    if os.path.isfile(abs_path):
                        valid_paths.append(path)
                except:
                    continue
            
            # 添加到队列
            self.active_downloads[session_id]['queue'].extend(valid_paths)
            
            return {
                'session_id': session_id,
                'queue_length': len(self.active_downloads[session_id]['queue']),
                'added_files': len(valid_paths)
            }
    
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
