import os
import json
import socket
import http.server
import socketserver
import threading
import urllib.parse
import uuid
import time
import mimetypes
import cgi
from http import HTTPStatus

# 导入自定义模块
from src.file_manager import FileManager
from src.upload_manager import UploadManager
from src.download_manager import DownloadManager

# 设置最大上传文件大小 (100MB)
MAX_UPLOAD_SIZE = 100 * 1024 * 1024

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """支持多线程的HTTP服务器"""
    daemon_threads = True
    allow_reuse_address = True

class RequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP请求处理器"""
    
    protocol_version = 'HTTP/1.1'  # 使用HTTP/1.1支持断点续传
    
    def __init__(self, *args, **kwargs):
        self.file_manager = None
        self.upload_manager = None
        self.download_manager = None
        super().__init__(*args, **kwargs)
    
    def setup(self):
        """设置请求处理器"""
        super().setup()
        self.file_manager = self.server.file_manager
        self.upload_manager = self.server.upload_manager
        self.download_manager = self.server.download_manager
    
    def do_GET(self):
        """处理GET请求"""
        try:
            # 解析URL路径
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            query = urllib.parse.parse_qs(parsed_path.query)
            
            # 处理API请求
            if path.startswith('/api/'):
                self.handle_api_request(path[5:], query)
                return
            
            # 处理静态文件请求
            if path.startswith('/static/'):
                self.serve_static_file(path[8:])
                return
            
            # 处理单文件下载请求
            if path.startswith('/download/'):
                rel_path = path[10:]
                self.download_manager.start_download(rel_path, self)
                return
            
            # 处理批量下载请求
            if path.startswith('/download-batch/'):
                download_id = path[15:]
                self.download_manager.serve_batch_download(download_id, self)
                return
            
            # 处理目录浏览请求 - 直接打开文件管理器
            if path == '/' or path.startswith('/browse/'):
                rel_path = path[8:] if path.startswith('/browse/') else ''
                self.serve_directory_listing(rel_path)
                return
            
            # 如果以上所有都不匹配，重定向到根目录
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
            
        except Exception as e:
            print(f"处理GET请求错误: {str(e)}")
            self.send_error(500, f"服务器错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def do_HEAD(self):
        """处理HEAD请求（用于断点续传）"""
        try:
            # 解析URL路径
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            # 处理文件下载HEAD请求
            if path.startswith('/download/'):
                rel_path = path[10:]
                self.download_manager.start_download(rel_path, self)
                return
            
            # 其他HEAD请求
            self.send_response(HTTPStatus.OK)
            self.end_headers()
            
        except Exception as e:
            print(f"处理HEAD请求错误: {str(e)}")
            self.send_error(500, f"服务器错误: {str(e)}")
    
    def do_POST(self):
        """处理POST请求"""
        try:
            # 解析URL路径
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            # 处理API请求
            if path.startswith('/api/'):
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    try:
                        json_data = json.loads(post_data.decode('utf-8'))
                    except:
                        json_data = {}
                    self.handle_api_request(path[5:], {}, json_data)
                else:
                    self.handle_api_request(path[5:], {})
                return
            
            # 处理文件上传请求
            if path.startswith('/upload/'):
                self.handle_file_upload(path[8:])
                return
            
            # 默认返回405方法不允许
            self.send_error(405, "方法不允许")
            
        except Exception as e:
            print(f"处理POST请求错误: {str(e)}")
            self.send_error(500, f"服务器错误: {str(e)}")
    
    def handle_api_request(self, endpoint, query_params=None, json_data=None):
        """处理API请求"""
        if query_params is None:
            query_params = {}
        if json_data is None:
            json_data = {}
        
        try:
            # 列出目录内容
            if endpoint == 'list':
                path = query_params.get('path', [''])[0]
                try:
                    items = self.file_manager.list_directory(path)
                    self.send_json_response(items)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # ===== 上传相关API =====
            # 检查上传冲突
            if endpoint == 'check_conflicts':
                target_dir = json_data.get('target_dir', '')
                filenames = json_data.get('filenames', [])
                
                if not filenames:
                    self.send_json_response({'error': '没有提供文件名'}, status=400)
                    return
                
                try:
                    result = self.upload_manager.check_upload_conflicts(filenames, target_dir)
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 开始上传
            if endpoint == 'start_upload':
                target_dir = json_data.get('target_dir', '')
                filename = json_data.get('filename', '')
                file_size = json_data.get('file_size', 0)
                overwrite = json_data.get('overwrite', False)
                
                if not filename:
                    self.send_json_response({'error': '没有提供文件名'}, status=400)
                    return
                
                try:
                    result = self.upload_manager.start_upload(filename, target_dir, file_size, overwrite)
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 获取上传进度
            if endpoint == 'upload_progress':
                upload_id = query_params.get('upload_id', [''])[0]
                
                try:
                    if upload_id:
                        result = self.upload_manager.get_upload_progress(upload_id)
                    else:
                        result = self.upload_manager.get_upload_progress()
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 完成上传
            if endpoint == 'complete_upload':
                upload_id = json_data.get('upload_id', '')
                
                if not upload_id:
                    self.send_json_response({'error': '没有提供上传ID'}, status=400)
                    return
                
                try:
                    result = self.upload_manager.complete_upload(upload_id)
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 取消上传
            if endpoint == 'cancel_upload':
                upload_id = json_data.get('upload_id', '')
                
                if not upload_id:
                    self.send_json_response({'error': '没有提供上传ID'}, status=400)
                    return
                
                try:
                    result = self.upload_manager.cancel_upload(upload_id)
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # ===== 目录相关API =====
            # 创建目录
            if endpoint == 'create_directory':
                path = json_data.get('path', '')
                
                if not path:
                    self.send_json_response({'error': '没有提供目录路径'}, status=400)
                    return
                
                try:
                    success = self.file_manager.create_directory(path)
                    if success:
                        self.send_json_response({'success': True, 'message': f'目录创建成功: {path}'})
                    else:
                        self.send_json_response({'error': f'目录创建失败: {path}'}, status=400)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 删除文件或目录
            if endpoint == 'delete_item':
                path = json_data.get('path', '')
                
                if not path:
                    self.send_json_response({'error': '没有提供要删除的路径'}, status=400)
                    return
                
                try:
                    success = self.file_manager.delete_item(path)
                    if success:
                        self.send_json_response({'success': True, 'message': f'删除成功: {path}'})
                    else:
                        self.send_json_response({'error': f'删除失败: {path}'}, status=400)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # ===== 下载相关API =====
            # 创建批量下载
            if endpoint == 'batch_download':
                paths = json_data.get('paths', [])
                folder_name = json_data.get('folder_name', '')
                
                if not paths:
                    self.send_json_response({'error': '没有提供文件路径'}, status=400)
                    return
                
                try:
                    result = self.download_manager.create_batch_download(paths, folder_name)
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 获取下载状态
            if endpoint == 'download_status':
                download_id = query_params.get('download_id', [''])[0]
                
                try:
                    if download_id:
                        result = self.download_manager.get_download_status(download_id)
                    else:
                        result = self.download_manager.get_download_status()
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 取消下载
            if endpoint == 'cancel_download':
                download_id = json_data.get('download_id', '')
                
                if not download_id:
                    self.send_json_response({'error': '没有提供下载ID'}, status=400)
                    return
                
                try:
                    result = self.download_manager.cancel_download(download_id)
                    self.send_json_response(result)
                except Exception as e:
                    self.send_json_response({'error': str(e)}, status=400)
                return
            
            # 未知API端点
            self.send_json_response({'error': f'未知API端点: {endpoint}'}, status=404)
            
        except Exception as e:
            print(f"API错误 ({endpoint}): {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_json_response({'error': f'处理API请求错误: {str(e)}'}, status=500)
    
    def handle_file_upload(self, target_dir):
        """处理文件上传"""
        # 检查Content-Type
        content_type = self.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            self.send_json_response({'error': '无效的Content-Type，必须是multipart/form-data'}, status=400)
            return
        
        # 解析表单数据
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={'REQUEST_METHOD': 'POST'}
        )
        
        # 获取上传ID
        upload_id = form.getvalue('upload_id')
        if not upload_id:
            self.send_json_response({'error': '没有提供上传ID'}, status=400)
            return
        
        # 获取文件项
        file_item = form['file'] if 'file' in form else None
        if not file_item:
            self.send_json_response({'error': '没有提供文件'}, status=400)
            return
        
        # 处理文件数据
        try:
            # 如果是文件开始，获取文件名
            if 'filename' in form:
                filename = form.getvalue('filename')
                # 开始上传
                result = self.upload_manager.start_upload(filename, target_dir)
                self.send_json_response(result)
                return
            
            # 如果是文件块，追加数据
            file_data = file_item.file.read()
            self.upload_manager.append_chunk(upload_id, file_data)
            
            # 检查是否是最后一块
            is_last_chunk = form.getvalue('is_last_chunk') == 'true'
            if is_last_chunk:
                # 完成上传
                result = self.upload_manager.complete_upload(upload_id)
                self.send_json_response(result)
            else:
                # 继续上传
                self.send_json_response({'success': True, 'upload_id': upload_id})
                
        except Exception as e:
            print(f"文件上传错误: {str(e)}")
            self.send_json_response({'error': str(e)}, status=500)
    
    def serve_static_file(self, rel_path):
        """提供静态文件"""
        try:
            # 获取静态文件路径
            static_dir = os.path.join(os.path.dirname(__file__), 'static')
            file_path = os.path.join(static_dir, rel_path)
            
            # 检查文件是否存在
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                self.send_error(404, "文件不存在")
                return
            
            # 获取MIME类型
            content_type, _ = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'application/octet-stream'
            
            # 发送文件
            with open(file_path, 'rb') as f:
                file_content = f.read()
                
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(file_content)))
            self.end_headers()
            self.wfile.write(file_content)
            
        except Exception as e:
            print(f"提供静态文件错误: {str(e)}")
            self.send_error(500, f"服务器错误: {str(e)}")
    
    def serve_directory_listing(self, rel_path):
        """提供目录列表页面"""
        try:
            # 获取目录内容
            items = self.file_manager.list_directory(rel_path)
            print(f"目录列表 ({rel_path}): {items}")
            
            # 构建当前路径导航
            path_parts = []
            current_path = ''
            for part in rel_path.split('/'):
                if part:
                    current_path = os.path.join(current_path, part)
                    path_parts.append({
                        'name': part,
                        'path': current_path
                    })
            
            # 读取模板文件
            template_path = os.path.join(os.path.dirname(__file__), 'static', 'templates', 'directory.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # 生成直接在HTML中显示的文件列表
            file_list_html = self._generate_file_list_html(rel_path, items)
            
            # 替换模板变量
            html = template.replace('{{current_path}}', rel_path)
            
            # 将JSON数据编码后嵌入到HTML中
            items_json = json.dumps(items)
            path_parts_json = json.dumps(path_parts)
            
            # 打印所有返回的JSON数据以及长度进行调试
            print(f"目录数据 (长度{len(items_json)}): {items_json}")
            print(f"路径数据 (长度{len(path_parts_json)}): {path_parts_json}")
            
            # 将生成的文件列表HTML直接插入到页面中
            html = html.replace('<!-- FILE_LIST_PLACEHOLDER -->', file_list_html)
            
            # 添加JSON数据作为备用
            html = html.replace('{{items_json}}', items_json.replace('\\', '\\\\').replace('"', '\\"'))
            html = html.replace('{{path_parts_json}}', path_parts_json.replace('\\', '\\\\').replace('"', '\\"'))
            
            # 发送响应
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(html.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            print(f"提供目录列表错误: {str(e)}")
            self.send_error(500, f"服务器错误: {str(e)}")
    
    def _generate_file_list_html(self, current_path, items):
        """生成文件列表HTML"""
        html = []
        
        # 分离文件夹和文件
        folders = sorted([item for item in items if item['is_dir']], key=lambda x: x['name'])
        files = sorted([item for item in items if not item['is_dir']], key=lambda x: x['name'])
        
        # 添加父目录链接
        if current_path:
            parent_path = '/'.join(current_path.split('/')[:-1])
            html.append(f'''
            <tr class="parent-dir">
                <td></td>
                <td colspan="4">
                    <a href="/browse/{parent_path}">
                        <span class="folder-icon"></span> ../ (返回上级目录)
                    </a>
                </td>
            </tr>''')
        
        # 添加文件夹
        for folder in folders:
            folder_path = f"{current_path}/{folder['name']}" if current_path else folder['name']
            folder_path = folder_path.replace('//', '/')
            html.append(f'''
            <tr data-path="{folder_path}" data-type="folder">
                <td></td>
                <td>
                    <a href="/browse/{folder_path}" class="item-name">
                        <span class="folder-icon"></span> {folder['name']}
                    </a>
                </td>
                <td>文件夹</td>
                <td>{folder['mtime_str']}</td>
                <td>
                    <button class="action-btn upload-to-folder" data-path="{folder_path}" title="上传到此文件夹">
                        <i class="icon-upload"></i>
                    </button>
                </td>
            </tr>''')
        
        # 添加文件
        for file in files:
            file_path = f"{current_path}/{file['name']}" if current_path else file['name']
            file_path = file_path.replace('//', '/')
            icon_class = self._get_file_icon_class(file['name'])
            size_str = self._format_size(file['size'])
            
            html.append(f'''
            <tr data-path="{file_path}" data-type="file">
                <td><input type="checkbox" class="file-checkbox" data-path="{file_path}"></td>
                <td>
                    <span class="item-name">
                        <span class="file-icon {icon_class}"></span> {file['name']}
                    </span>
                </td>
                <td>{size_str}</td>
                <td>{file['mtime_str']}</td>
                <td>
                    <a href="/download/{file_path}" class="action-btn download-file" download title="下载">
                        <i class="icon-download"></i>
                    </a>
                </td>
            </tr>''')
        
        # 没有文件时显示提示
        if not folders and not files:
            html.append('''
            <tr>
                <td colspan="5" class="empty-message">没有文件或目录</td>
            </tr>''')
            
        return ''.join(html)
    
    def _get_file_icon_class(self, filename):
        """根据文件名返回图标类"""
        ext = os.path.splitext(filename)[1].lower()[1:]
        
        # 图片文件
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp']:
            return 'image'
        
        # 视频文件
        if ext in ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm']:
            return 'video'
        
        # 压缩文件
        if ext in ['zip', 'rar', '7z', 'tar', 'gz', 'bz2']:
            return 'archive'
        
        return ''
        
    def _format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024
            i += 1
            
        return f"{size_bytes:.2f} {units[i]}"

    def serve_index_page(self):
        """提供主页"""
        try:
            # 读取模板文件
            template_path = os.path.join(os.path.dirname(__file__), 'static', 'templates', 'index.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            # 发送响应
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(html.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            print(f"提供主页错误: {str(e)}")
            self.send_error(500, f"服务器错误: {str(e)}")
    
    def send_json_response(self, data, status=200):
        """发送JSON响应"""
        response = json.dumps(data).encode('utf-8')
        
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

class Server:
    """文件服务器主类"""
    
    def __init__(self, host='0.0.0.0', port=8080, working_dir='./'):
        """
        初始化服务器
        
        Args:
            host: 主机地址
            port: 端口号
            working_dir: 工作目录
        """
        self.host = host
        self.port = port
        self.working_dir = os.path.abspath(working_dir)
        
        # 创建必要的目录
        self._create_required_directories()
        
        # 初始化管理器
        self.file_manager = FileManager(self.working_dir)
        self.upload_manager = UploadManager(self.file_manager)
        self.download_manager = DownloadManager(self.file_manager)
        
        # 创建HTTP服务器
        self.server = ThreadedHTTPServer((host, port), RequestHandler)
        self.server.file_manager = self.file_manager
        self.server.upload_manager = self.upload_manager
        self.server.download_manager = self.download_manager
    
    def _create_required_directories(self):
        """创建必要的目录"""
        # 确保工作目录存在
        os.makedirs(self.working_dir, exist_ok=True)
        
        # 创建静态文件目录
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        os.makedirs(static_dir, exist_ok=True)
        
        # 创建模板目录
        templates_dir = os.path.join(static_dir, 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        
        # 创建CSS目录
        css_dir = os.path.join(static_dir, 'css')
        os.makedirs(css_dir, exist_ok=True)
        
        # 创建JS目录
        js_dir = os.path.join(static_dir, 'js')
        os.makedirs(js_dir, exist_ok=True)
    
    def start(self):
        """启动服务器"""
        server_thread = threading.Thread(target=self._run_server)
        server_thread.daemon = True
        server_thread.start()
        
        print(f"服务器已启动，访问 http://{self.host}:{self.port}/")
        print(f"工作目录: {self.working_dir}")
        print("按 Ctrl+C 停止服务器")
        
        try:
            # 保持主线程运行
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("正在停止服务器...")
            self.stop()
    
    def _run_server(self):
        """运行服务器"""
        self.server.serve_forever()
    
    def stop(self):
        """停止服务器"""
        self.server.shutdown()
        self.server.server_close()
        print("服务器已停止")