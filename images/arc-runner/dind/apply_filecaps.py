import ctypes
import ctypes.util
import os

lib = ctypes.CDLL(ctypes.util.find_library("cap"), use_errno=True)
lib.cap_from_text.argtypes = [ctypes.c_char_p]
lib.cap_from_text.restype = ctypes.c_void_p
lib.cap_set_file.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
lib.cap_set_file.restype = ctypes.c_int
lib.cap_free.argtypes = [ctypes.c_void_p]
lib.cap_free.restype = ctypes.c_int
for path, capability in [("/usr/bin/newuidmap", b"cap_setuid,cap_setfcap=ep"), ("/usr/bin/newgidmap", b"cap_setgid=ep")]:
    os.chmod(path, 0o755)
    value = lib.cap_from_text(capability)
    assert value
    try:
        rc = lib.cap_set_file(path.encode(), value)
        if rc != 0:
            raise OSError(ctypes.get_errno(), path)
        assert os.getxattr(path, "security.capability")
    finally:
        assert lib.cap_free(value) == 0
