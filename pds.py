from src.server import Server
import os
import argparse

if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='文件上传下载服务器')
    parser.add_argument('--host', default='0.0.0.0', help='服务器主机地址')
    parser.add_argument('--port', type=int, default=8080, help='服务器端口')
    # 使用当前目录作为默认工作目录
    default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    parser.add_argument('--dir', default=default_dir, help='工作目录路径')
    args = parser.parse_args()
    
    # 规范化工作目录路径（将正斜杠转换为系统适用的路径分隔符）
    work_dir = os.path.normpath(args.dir)
    
    # 确保工作目录存在
    if not os.path.exists(work_dir):
        os.makedirs(work_dir, exist_ok=True)
    
    print(f"启动服务器，主机: {args.host}, 端口: {args.port}, 工作目录: {work_dir}")
    
    # 创建并启动服务器
    server = Server(host=args.host, port=args.port, working_dir=work_dir)
    server.start()