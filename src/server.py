import os
import socket
import http.server
import socketserver
import urllib.parse

class RequestHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.startswith('/'):
            sub_path = os.path.normpath(self.path[1:])
            new_dir = os.path.join(self.work_dir, sub_path)
            if os.path.exists(new_dir) and os.path.isdir(new_dir):
                self.list_files(new_dir)
            else:
                http.server.SimpleHTTPRequestHandler.do_GET(self)
        else:
            http.server.SimpleHTTPRequestHandler.do_GET(self)

    def list_files(self, folder = './'):
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) or os.path.isdir(os.path.join(folder, f))]
        files_html = '<html><body><h1>Available Files</h1><ul>' + ''.join([f'<li><a href="{os.path.join(self.path, f)}">{f}</a></li>' if os.path.isdir(os.path.join(folder, f)) else f'<li><a href="{os.path.join(self.path, f)}" download>{f}</a></li>' for f in files]) + '</ul></body></html>'
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8') # Add charset=utf-8 to the Content-type header
        self.end_headers()
        self.wfile.write(bytes(files_html, 'utf-8'))

class Server(socketserver.TCPServer):
    def __init__(self, host='localhost', port=8080, working_dir='./'):
        self.working_dir = working_dir
        super().__init__((host, port), RequestHandler, bind_and_activate=False)
        self.server_name = self.server_address[0]
        self.allow_reuse_address = True
        self.RequestHandlerClass.server_address = self.server_address
        self.RequestHandlerClass.protocol_version = "HTTP/1.0"
        self.RequestHandlerClass.work_dir = working_dir
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_bind()
        self.server_activate()

    def upload(self, filename, target_dir):
        file_path = os.path.join(self.working_dir, target_dir, filename)
        with open(file_path, 'wb') as file:
            data = self.connection.recv(1024)
            while data:
                file.write(data)
                data = self.connection.recv(1024)

    def download(self, filename, target_dir):
        decoded_filename = urllib.parse.unquote(filename)
        file_path = os.path.join(self.working_dir, target_dir, decoded_filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as file:
                data = file.read(1024)
                while data:
                    self.connection.sendall(data)
                    data = file.read(1024)
        else:
            self.send_error(404, 'File not found')

    def start(self):
        while True:
            print('Waiting for connection...')
            self.handle_request()