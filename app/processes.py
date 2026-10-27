"""Portable cleanup limited to process trees owned by SlideVoice."""

import subprocess
import sys
import threading

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


# Windows child processes inherit the frozen app's DLL directory. External tools
# must resolve their own libraries; restore the app's search path right after spawn.
_external_spawn_lock = threading.RLock()


def external_popen(command, **options):
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return subprocess.Popen(command, **options)
    import ctypes
    import os

    with _external_spawn_lock:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        kernel.SetDllDirectoryW.restype = ctypes.c_int
        saved = ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(saved), saved)
        previous_error_mode = kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        environment = dict(options.pop("env", None) or os.environ)
        bundled = os.path.normcase(sys._MEIPASS).rstrip("\\/") + os.sep
        environment["PATH"] = os.pathsep.join(
            path
            for path in environment.get("PATH", "").split(os.pathsep)
            if not (os.path.normcase(path).rstrip("\\/") + os.sep).startswith(bundled)
        )
        try:
            if not kernel.SetDllDirectoryW(None):
                raise ctypes.WinError(ctypes.get_last_error())
            return subprocess.Popen(command, env=environment, **options)
        finally:
            kernel.SetDllDirectoryW(saved.value or None)
            kernel.SetErrorMode(previous_error_mode)


def run_external(command, *, capture_output=False, timeout=None, check=False, **options):
    if capture_output:
        options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with external_popen(command, **options) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            stop_process_tree(process)
            raise
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
