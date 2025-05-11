from src.server import Server
import os
import argparse

if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='文件上传下载服务器')
    parser.add_argument('--host', default='0.0.0.0', help='服务器主机地址')
    parser.add_argument('--port', type=int, default=8080, help='服务器端口')
    parser.add_argument('--dir', default='D:/Document', help='工作目录路径')
    args = parser.parse_args()
    
    # 确保工作目录存在
    if not os.path.exists(args.dir):
        os.makedirs(args.dir, exist_ok=True)
    
    print(f"启动服务器，主机: {args.host}, 端口: {args.port}, 工作目录: {args.dir}")
    
    # 创建并启动服务器
    server = Server(host=args.host, port=args.port, working_dir=args.dir)
    server.start()