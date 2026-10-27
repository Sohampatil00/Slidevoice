"""Portable cleanup limited to process trees owned by SlideVoice."""

import subprocess
import sys

import psutil


def background_options(platform=None):
    if (platform or sys.platform) == "win32":
        return {"creationflags": 0x00000200 | 0x08000000}  # NEW_PROCESS_GROUP | NO_WINDOW
    return {"start_new_session": True}


def stop_process_tree(process, timeout=8):
    if process is None or process.poll() is not None:
        return
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    # Snapshot descendants before ending the parent; this includes pip/uv, model,
    # resource trackers, and ffmpeg children even if they use separate sessions.
    targets = [parent, *reversed(children)]
    for target in targets:
        try:
            target.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(targets, timeout=timeout)
    for target in alive:
        try:
            target.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        process.wait(timeout=3)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        pass
