"""Run: python processing/app.py --port 8765 (no external dependencies)."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

if __package__:
    from .core.plots import svg_chart
    from .core.workspace import Workspace
else:
    from core.plots import svg_chart
    from core.workspace import Workspace

ROOT = Path(__file__).resolve().parent
_dialog_lock = threading.Lock()


def choose_directory(kind):
    """Native chooser opens only when the user explicitly clicks its HTML button."""
    with _dialog_lock:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            try:
                return filedialog.askdirectory(title='Chọn thư mục nguồn (chỉ đọc)' if kind == 'source' else 'Chọn thư mục đích để sao chép', parent=root)
            finally:
                root.destroy()
        except Exception as exc:
            raise ValueError('Không mở được hộp chọn thư mục. Hãy nhập đường dẫn vào ô trên giao diện.') from exc


def create_server(port=8765, storage_root=None, public_url=None, share_user='reviewer', share_password=None):
    public_host = public_origin = None
    if public_url:
        parsed = urlsplit(public_url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError('Public URL phải là origin HTTPS, ví dụ https://ten-mien.ngrok-free.dev')
        if share_password is not None and (not share_user or ':' in share_user or len(share_password) < 12):
            raise ValueError('Khi bật mật khẩu, cần username hợp lệ và mật khẩu ít nhất 12 ký tự.')
        public_host = parsed.netloc.lower()
        public_origin = f'https://{public_host}'
    expected_auth = hashlib.sha256(f'{share_user}:{share_password}'.encode('utf-8')).digest() if public_host and share_password is not None else None
    workspace = Workspace(storage_root or ROOT / 'reviews')
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Do not print sensor data, local source paths or authentication tokens.
            if args and isinstance(args[0], str) and args[0].startswith(('GET /api/', 'POST /api/')):
                return
            super().log_message(fmt, *args)

        def send(self, body, status=200, content_type='application/json; charset=utf-8', filename=None, challenge=False):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            if challenge:
                self.send_header('WWW-Authenticate', 'Basic realm="RoboNose", charset="UTF-8"')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def trusted_host(self):
            return self.headers.get('Host', '').lower() in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}', public_host}

        def authenticated(self):
            if expected_auth is None:
                return True
            try:
                scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
                supplied = base64.b64decode(encoded, validate=True) if scheme.lower() == 'basic' else b''
            except (ValueError, TypeError):
                supplied = b''
            if secrets.compare_digest(hashlib.sha256(supplied).digest(), expected_auth):
                return True
            self.send({'error': 'Cần đăng nhập để truy cập phiên chia sẻ.'}, 401, challenge=True)
            return False

        def api_allowed(self):
            if not self.trusted_host():
                self.send({'error': 'Host không hợp lệ.'}, 403)
                return False
            if not self.authenticated():
                return False
            if not secrets.compare_digest(self.headers.get('X-Review-Token', ''), token):
                self.send({'error': 'Phiên không hợp lệ. Mở lại trang ứng dụng localhost.'}, 403)
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}', public_origin}:
                self.send({'error': 'Origin không hợp lệ.'}, 403)
                return False
            return True

        def do_GET(self):
            url = urlsplit(self.path)
            if not self.trusted_host():
                self.send({'error': 'Localhost only.'}, 403)
                return
            if not self.authenticated():
                return
            if url.path == '/':
                html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8').replace('__REVIEW_TOKEN__', token)
                self.send(html.encode('utf-8'), content_type='text/html; charset=utf-8')
                return
            static = {'/static/style.css': ('style.css', 'text/css; charset=utf-8'), '/static/app.js': ('app.js', 'text/javascript; charset=utf-8')}
            if url.path in static:
                name, mime = static[url.path]
                self.send((ROOT / 'web' / name).read_bytes(), content_type=mime)
                return
            if not self.api_allowed():
                return
            try:
                query = parse_qs(url.query)
                if url.path == '/api/state':
                    self.send(workspace.state())
                elif url.path == '/api/sample':
                    self.send(workspace.detail(query.get('id', [''])[0]))
                elif url.path == '/api/plot':
                    key, channel = query.get('id', [''])[0], query.get('channel', [''])[0]
                    data = workspace.detail(key)
                    self.send(svg_chart(data, channel, data['name']), content_type='image/svg+xml; charset=utf-8', filename=f'raw-{key[:8]}.svg')
                elif url.path == '/api/manifest':
                    self.send(workspace.export_manifest(), content_type='text/csv; charset=utf-8', filename='review-labels.csv')
                else:
                    self.send({'error': 'Không có endpoint này.'}, 404)
            except (ValueError, OSError) as exc:
                self.send({'error': str(exc)}, 400)
            except Exception:
                self.send({'error': 'Không xử lý được yêu cầu. Xem lại nguồn và thử tải lại.'}, 500)

        def do_POST(self):
            if not self.api_allowed():
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 1024 * 1024:
                    raise ValueError('Kích thước yêu cầu không hợp lệ.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Yêu cầu phải là JSON object.')
                path = urlsplit(self.path).path
                if path == '/api/source':
                    self.send(workspace.load_source(body.get('path', '')))
                elif path == '/api/target':
                    self.send(workspace.set_target(body.get('path', '')))
                elif path == '/api/pick':
                    kind = body.get('kind')
                    if kind not in {'source', 'target'}:
                        raise ValueError('Loại thư mục không hợp lệ.')
                    self.send({'path': choose_directory(kind)})
                elif path == '/api/refresh':
                    self.send(workspace.refresh())
                elif path == '/api/groups':
                    self.send(workspace.add_group(body.get('name', '')))
                elif path == '/api/review':
                    self.send(workspace.review(body.get('id'), body.get('decision'), body.get('note', ''), body.get('raw_hash'), body.get('metadata_hash')))
                elif path == '/api/copy':
                    self.send(workspace.copy(body.get('id'), body.get('group'), body.get('raw_hash'), body.get('metadata_hash')))
                else:
                    self.send({'error': 'Không có endpoint này.'}, 404)
            except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
                self.send({'error': str(exc)}, 400)
            except Exception:
                self.send({'error': 'Lỗi nội bộ. Không tự sửa/xóa dữ liệu nguồn.'}, 500)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.workspace = workspace
    return server


def main():
    parser = argparse.ArgumentParser(description='RoboNose: duyệt raw, gán nhãn và COPY nguyên mẫu bằng tay.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--public-url', help='Origin HTTPS chính xác của tunnel ngrok; mở trực tiếp, mặc định không mật khẩu.')
    parser.add_argument('--require-password', action='store_true', help='Tùy chọn bật mật khẩu cho phiên chia sẻ.')
    parser.add_argument('--share-user', default='reviewer', help='Tên đăng nhập chia sẻ (mặc định reviewer).')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Port phải nằm trong 0..65535.')
    if args.require_password and not args.public_url:
        parser.error('--require-password cần đi cùng --public-url.')
    password = getpass.getpass('Mật khẩu chia sẻ (ít nhất 12 ký tự, không hiện khi gõ): ') if args.require_password else None
    try:
        server = create_server(args.port, public_url=args.public_url, share_user=args.share_user, share_password=password)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'RoboNose Raw Review: http://127.0.0.1:{server.server_port}/', flush=True)
    print('Chỉ đọc nguồn; không smoothing. Ctrl+C để dừng.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
