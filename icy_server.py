#!/usr/bin/env python3
"""
ICY Streaming Server
- Fixed ring buffer with global write counter
- ICY metadata with StreamTitle and StreamUrl (album art)
- ThreadingHTTPServer
"""

import collections
import http.server
import subprocess
import threading
import json
import time
import urllib.request

# Config
FIFO_PATH = "/tmp/snapstream"
SAMPLE_RATE = 48000
CHANNELS = 2
AAC_BITRATE = "128k"
HTTP_PORT = 8000
ICY_METAINT = 16000
SNAPSERVER_URL = "http://localhost:1780/jsonrpc"
BUFFER_SIZE = 2000

# Silent AAC ADTS frame (48kHz, stereo, LC) - ~21.3ms of silence
SILENT_ADTS_FRAME = b'\xff\xf1L\x80\x01\xbf\xfc!\x10\x04`\x8c\x1c'
SILENCE_FRAME_DURATION = 1024 / 48000  # ~0.02133s per AAC frame
SILENCE_TIMEOUT = 2.0  # seconds without ffmpeg data before generating silence

# Global state
current_icy_text = ""
current_art_url = ""
metadata_lock = threading.Lock()

# MP3 buffer
mp3_chunks = collections.deque(maxlen=BUFFER_SIZE)
mp3_write_idx = 0
mp3_lock = threading.Lock()
mp3_event = threading.Event()

# Silence generator coordination
last_ffmpeg_data_time = 0.0
last_ffmpeg_lock = threading.Lock()


def fetch_metadata():
    """Fetch now-playing info from snapserver."""
    global current_icy_text, current_art_url
    while True:
        try:
            req = urllib.request.Request(
                SNAPSERVER_URL,
                data=json.dumps({
                    "id": 1,
                    "jsonrpc": "2.0",
                    "method": "Server.GetStatus"
                }).encode(),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())

            for s in data["result"]["server"]["streams"]:
                if s["status"] == "playing":
                    m = s["properties"].get("metadata", {})
                    artist = ", ".join(m.get("artist", []))
                    title = m.get("title", "")
                    album = m.get("album", "")
                    art_url = m.get("artUrl", "")

                    if artist and title:
                        text = f"{artist} - {title}"
                    elif title:
                        text = title
                    else:
                        text = ""

                    with metadata_lock:
                        if text != current_icy_text:
                            current_icy_text = text
                            current_art_url = art_url
                            art_info = f" art={art_url[:50]}..." if art_url else ""
                            print(f"Metadata: {text} [{album}]{art_info}", flush=True)
                    break
        except Exception:
            pass

        time.sleep(3)


def run_ffmpeg():
    """Run ffmpeg continuously, buffer MP3 output."""
    global mp3_write_idx, last_ffmpeg_data_time

    while True:
        try:
            print("Starting ffmpeg...", flush=True)
            ffmpeg = subprocess.Popen(
                [
                    "ffmpeg",
                    "-f", "s16le",
                    "-ar", str(SAMPLE_RATE),
                    "-ac", str(CHANNELS),
                    "-i", FIFO_PATH,
                    "-c:a", "aac",
                    "-b:a", AAC_BITRATE,
                    "-f", "adts",
                    "-"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )

            while True:
                data = ffmpeg.stdout.read(4096)
                if not data:
                    break
                with mp3_lock:
                    mp3_chunks.append(data)
                    mp3_write_idx += 1
                with last_ffmpeg_lock:
                    last_ffmpeg_data_time = time.monotonic()
                mp3_event.set()

            ffmpeg.wait()
            print("ffmpeg ended, restarting...", flush=True)
        except Exception as e:
            print(f"ffmpeg error: {e}", flush=True)

        time.sleep(1)


def generate_silence():
    """Inject silent ADTS frames when ffmpeg is not producing data."""
    global mp3_write_idx, current_icy_text, current_art_url

    while True:
        time.sleep(SILENCE_TIMEOUT)

        with last_ffmpeg_lock:
            elapsed = time.monotonic() - last_ffmpeg_data_time

        if elapsed < SILENCE_TIMEOUT:
            continue

        # No data from ffmpeg -- start injecting silence
        with metadata_lock:
            current_icy_text = "Waiting for playback..."
            current_art_url = ""
        print("No audio data, generating silence...", flush=True)

        while True:
            with last_ffmpeg_lock:
                elapsed = time.monotonic() - last_ffmpeg_data_time
            if elapsed < 0.5:
                break

            with mp3_lock:
                mp3_chunks.append(SILENT_ADTS_FRAME)
                mp3_write_idx += 1
            mp3_event.set()
            time.sleep(SILENCE_FRAME_DURATION)

        # ffmpeg resumed -- clear waiting metadata
        with metadata_lock:
            current_icy_text = ""
            current_art_url = ""
        print("Audio data resumed, stopping silence.", flush=True)


def build_icy_metadata():
    """Build ICY metadata block with StreamTitle and StreamUrl."""
    with metadata_lock:
        text = current_icy_text
        art_url = current_art_url

    if not text:
        return b"\x00"

    meta_str = f"StreamTitle='{text}';"
    if art_url:
        meta_str += f"StreamUrl='{art_url}';"

    meta_bytes = meta_str.encode("utf-8")

    pad_length = (16 - (len(meta_bytes) % 16)) % 16
    meta_bytes += b"\x00" * pad_length

    length_byte = len(meta_bytes) // 16
    return bytes([length_byte]) + meta_bytes


class ICYHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        icy_requested = self.headers.get("Icy-MetaData") == "1"

        self.send_response(200)
        self.send_header("Content-Type", "audio/aac")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("icy-name", "Music Assistant")
        self.send_header("icy-pub", "0")
        if icy_requested:
            self.send_header("icy-metaint", str(ICY_METAINT))
            self.send_header("icy-metadata", "1")
        self.end_headers()

        with mp3_lock:
            client_idx = mp3_write_idx

        bytes_since_meta = 0

        try:
            while True:
                mp3_event.wait(timeout=5)

                with mp3_lock:
                    current_write = mp3_write_idx
                    buf_len = len(mp3_chunks)

                while client_idx < current_write:
                    offset = client_idx - (current_write - buf_len)
                    if offset < 0:
                        client_idx = current_write - buf_len
                        offset = 0

                    with mp3_lock:
                        if offset < len(mp3_chunks):
                            chunk = mp3_chunks[offset]
                        else:
                            break
                    client_idx += 1

                    if icy_requested:
                        pos = 0
                        while pos < len(chunk):
                            to_meta = ICY_METAINT - bytes_since_meta
                            end = min(pos + to_meta, len(chunk))
                            self.wfile.write(chunk[pos:end])
                            bytes_since_meta += (end - pos)
                            pos = end

                            if bytes_since_meta >= ICY_METAINT:
                                self.wfile.write(build_icy_metadata())
                                bytes_since_meta = 0
                    else:
                        self.wfile.write(chunk)

                    self.wfile.flush()

                    with mp3_lock:
                        current_write = mp3_write_idx

                mp3_event.clear()

        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {args[0]}", flush=True)


def main():
    threading.Thread(target=fetch_metadata, daemon=True).start()
    threading.Thread(target=run_ffmpeg, daemon=True).start()
    threading.Thread(target=generate_silence, daemon=True).start()

    server = http.server.ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), ICYHandler)
    print(f"ICY server running on port {HTTP_PORT}", flush=True)
    print(f"Stream URL: http://0.0.0.0:{HTTP_PORT}/", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()