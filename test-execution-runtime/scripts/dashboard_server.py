import argparse
import functools
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_HOST='127.0.0.1'
DEFAULT_PORT=8765

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def create_server(directory, host=DEFAULT_HOST, port=DEFAULT_PORT):
    root=Path(directory).resolve()
    if not root.exists(): raise AssertionError(f'dashboard directory does not exist: {root}')
    if not (root/'index.html').exists(): raise AssertionError(f'dashboard index missing: {root/"index.html"}')
    if not (root/'dashboard-data.json').exists(): raise AssertionError(f'dashboard data missing: {root/"dashboard-data.json"}')
    handler=functools.partial(QuietHandler,directory=str(root))
    return ThreadingHTTPServer((host,port),handler)

def url_for(server):
    host,port=server.server_address[:2]
    if host in {'0.0.0.0','::'}: host='127.0.0.1'
    return f'http://{host}:{port}/'

def serve(directory,host=DEFAULT_HOST,port=DEFAULT_PORT,open_browser=False):
    server=create_server(directory,host,port); url=url_for(server)
    print(f'Dashboard: {url}',flush=True)
    if open_browser: threading.Timer(0.2,lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

def main():
    a=argparse.ArgumentParser(description='Serve a test-run Dashboard over local HTTP so fetch(dashboard-data.json) works reliably.')
    a.add_argument('--directory',help='Dashboard directory containing index.html and dashboard-data.json')
    a.add_argument('--run-dir',help='Run root; serves <run-dir>/dashboard')
    a.add_argument('--host',default=DEFAULT_HOST)
    a.add_argument('--port',type=int,default=DEFAULT_PORT)
    a.add_argument('--open',action='store_true',dest='open_browser')
    x=a.parse_args()
    if bool(x.directory)==bool(x.run_dir): raise SystemExit('provide exactly one of --directory or --run-dir')
    directory=x.directory or str(Path(x.run_dir)/'dashboard')
    serve(directory,x.host,x.port,x.open_browser)

if __name__=='__main__': main()
