"""Resolve the user's Downloads folder without creating it or saving settings."""
from pathlib import Path
import sys


def _windows_downloads():
    # FOLDERID_Downloads respects redirected/relocated Windows known folders.
    # https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid
    import ctypes
    from uuid import UUID
    shell = ctypes.WinDLL("shell32")
    ole = ctypes.WinDLL("ole32")
    query = shell.SHGetKnownFolderPath
    query.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    query.restype = ctypes.c_long
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    folder_id = (ctypes.c_byte * 16).from_buffer_copy(UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le)
    pointer = ctypes.c_wchar_p()
    initialized = ole.CoInitializeEx(None, 2) in (0, 1)
    try:
        if query(ctypes.byref(folder_id), 0, None, ctypes.byref(pointer)) == 0 and pointer.value:
            return Path(pointer.value)
    finally:
        ole.CoTaskMemFree(ctypes.cast(pointer, ctypes.c_void_p))
        if initialized:
            ole.CoUninitialize()
    return None


def default_download_directory():
    if sys.platform == "win32":
        try:
            location = _windows_downloads()
            if location:
                return location
        except (AttributeError, OSError, ValueError):
            pass
    # The standard macOS location; also a portable fallback on other platforms.
    return Path.home() / "Downloads"
