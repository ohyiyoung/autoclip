"""AutoClip Desktop - jendela desktop untuk AutoClip.

Menjalankan server AutoClip di latar belakang (di dalam proses yang sama), lalu
membuka UI-nya di jendela asli. UI yang sama sudah punya:
  - preview klip (9:16 + caption) di halaman Review
  - tombol Export -> Download untuk menyimpan MP4

Jadi launcher ini tidak menduplikasi UI; ia hanya membungkusnya jadi aplikasi .exe.
Kalau pywebview tidak ada / WebView2 tidak tersedia, otomatis membuka browser biasa.
"""
from __future__ import annotations

import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

APP_TITLE = "AutoClip"
PREFERRED_PORT = 8000
HOST = "127.0.0.1"


# ---------- util ----------
def notify(message: str, title: str = APP_TITLE) -> None:
    """Tampilkan pesan. App windowed tidak punya konsol, jadi pakai dialog di Windows."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
            return
        except Exception:
            pass
    print(f"[{title}] {message}", file=sys.stderr)


def pick_port(preferred: int = PREFERRED_PORT, host: str = HOST) -> int:
    """Pakai port favorit kalau kosong, kalau tidak minta port bebas dari OS."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("Tidak ada port yang tersedia.")


def wait_until_up(url: str, timeout: float = 90.0) -> bool:
    """Tunggu sampai server menjawab. Import berat (mediapipe dll) bisa makan waktu."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except urllib.error.HTTPError:
            return True  # server hidup, hanya status non-200
        except Exception:
            time.sleep(0.4)
    return False


def check_ffmpeg() -> str | None:
    """Kembalikan peringatan kalau ffmpeg/ffprobe tidak ada di PATH."""
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if not missing:
        return None
    return (
        f"{' dan '.join(missing)} tidak ditemukan di PATH.\n\n"
        "AutoClip butuh ffmpeg build LENGKAP (dengan libass) agar caption bisa dibakar.\n"
        "Windows: buka Terminal, jalankan\n    winget install Gyan.FFmpeg\n"
        "lalu buka ulang AutoClip."
    )


# ---------- server ----------
class ServerThread:
    """Menjalankan uvicorn di thread terpisah dan bisa dihentikan dengan rapi."""

    def __init__(self, host: str, port: int) -> None:
        import uvicorn

        # Objek app dioper langsung (bukan string "autoclip.app:app") supaya
        # PyInstaller menemukan modulnya lewat analisis import statis.
        from autoclip.app import app

        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True, name="autoclip-server")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=8)


# ---------- window ----------
def open_window(url: str) -> bool:
    """Buka jendela native. True kalau jendela dipakai (blok sampai ditutup)."""
    try:
        import webview
    except Exception:
        return False

    # Tanpa ini tombol Download di UI tidak melakukan apa-apa di jendela pywebview.
    webview.settings["ALLOW_DOWNLOADS"] = True
    try:
        webview.create_window(APP_TITLE, url, width=1280, height=860, min_size=(900, 600))
        webview.start()
        return True
    except Exception as exc:  # WebView2 belum terpasang, dsb.
        print(f"Jendela native gagal ({exc}); pindah ke browser.", file=sys.stderr)
        return False


def open_in_browser(url: str) -> None:
    import webbrowser

    webbrowser.open(url)
    notify(
        f"AutoClip berjalan di {url}\n\nTutup pesan ini untuk MENGHENTIKAN AutoClip.",
    )


# ---------- main ----------
def main() -> int:
    multiprocessing.freeze_support()  # wajib untuk PyInstaller di Windows

    warning = check_ffmpeg()
    if warning:
        notify(warning)

    port = pick_port()
    url = f"http://{HOST}:{port}"

    try:
        server = ServerThread(HOST, port)
    except Exception as exc:
        notify(f"Gagal memuat AutoClip:\n{exc}")
        return 1
    server.start()

    if not wait_until_up(url):
        notify("Server AutoClip tidak merespons. Coba jalankan ulang.")
        server.stop()
        return 1

    if not open_window(url):
        open_in_browser(url)  # blok lewat dialog; menutupnya = berhenti

    server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
