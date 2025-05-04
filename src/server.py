import os
import socket
import http.server
import socketserver

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.list_files()
        else:
            http.server.SimpleHTTPRequestHandler.do_GET(self)

    def list_files(self):
        files = [f for f in os.listdir(self.server.server.working_dir) if os.path.isfile(os.path.join(self.server.server.working_dir, f))]
        files_html = '<html><body><h1>Available Files</h1><ul>' + ''.join([f'<li><a href="{f}">{f}</a></li>' for f in files]) + '</ul></body></html>'
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(bytes(files_html, 'utf-8'))

class Server(socketserver.TCPServer):
    def __init__(self, host='localhost', port=8080, working_dir='.'):
        self.working_dir = working_dir
        super().__init__((host, port), RequestHandler)
        self.RequestHandler.server = self

    def upload(self, filename, target_dir):
        file_path = os.path.join(self.working_dir, target_dir, filename)
        with open(file_path, 'wb') as file:
            data = self.connection.recv(1024)
            while data:
                file.write(data)
                data = self.connection.recv(1024)

    def download(self, filename, target_dir):
        file_path = os.path.join(self.working_dir, target_dir, filename)
        with open(file_path, 'rb') as file:
            data = file.read(1024)
            while data:
                self.connection.sendall(data)
                data = file.read(1024)

    def start(self):
        while True:
            print('Waiting for connection...')
            self.handle_request()