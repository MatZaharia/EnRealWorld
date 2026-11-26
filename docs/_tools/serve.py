"""Serve the project page locally with byte ranges for media playback."""

import functools
import os
from pathlib import Path
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class PreviewHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.bytes_remaining = None
        header = self.headers.get("Range", "")
        match = re.fullmatch(r"bytes=(\d{0,18})-(\d{0,18})", header)
        if self.command != "GET" or not match or not any(match.groups()):
            return super().send_head()

        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return super().send_head()

        try:
            content = path.open("rb")
        except OSError:
            return super().send_head()

        info = os.fstat(content.fileno())
        modified = self.date_time_string(info.st_mtime)
        if_range = self.headers.get("If-Range")
        if if_range and if_range != modified:
            content.close()
            return super().send_head()

        first, last = match.groups()
        size = info.st_size
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            start, end = max(0, size - int(last)), size - 1

        if start > end:
            content.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        content.seek(start)
        self.bytes_remaining = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(self.bytes_remaining))
        self.send_header("Last-Modified", modified)
        self.end_headers()
        return content

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def copyfile(self, source, outputfile):
        if self.bytes_remaining is None:
            return super().copyfile(source, outputfile)
        remaining = self.bytes_remaining
        while remaining:
            chunk = source.read(min(remaining, 64 * 1024))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


if __name__ == "__main__":
    docs = Path(__file__).resolve().parents[1]
    handler = functools.partial(PreviewHandler, directory=str(docs))
    with ThreadingHTTPServer(("127.0.0.1", 4173), handler) as server:
        print("EnRealWorld preview at http://127.0.0.1:4173/", flush=True)
        server.serve_forever()
