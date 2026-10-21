"""Windows Hello user-presence checks for an *already unlocked* vault session.

Desktop UserConsentVerifier interop is called with the app HWND. A successful
result never supplies a vault key and cannot unlock a closed VaultSession.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import time
import uuid
from ctypes import wintypes
from threading import Event


class _Guid(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def _guid(value: str) -> _Guid:
    return _Guid.from_buffer_copy(uuid.UUID(value).bytes_le)


def _method(pointer, slot: int, *args):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *args)(vtable[slot])


def _check(hr: int) -> None:
    if hr < 0:
        raise OSError(f"Windows Hello API returned 0x{hr & 0xffffffff:08x}")


def _release(pointer) -> None:
    if pointer and pointer.value:
        _method(pointer, 2)(pointer)


_CLASS = "Windows.Security.Credentials.UI.UserConsentVerifier"
_ASYNC_INFO = "00000036-0000-0000-c000-000000000046"
_RESULT_OPERATION = "fd596ffd-2318-558f-9dbe-d21df43764a5"
_STATICS = "af4f3f91-564c-4ddc-b8b5-973447627c65"
_INTEROP = "39e050c3-4e74-441a-8dc0-b81104df949c"
_AVAILABILITY = {0: "available", 1: "device absent", 2: "not configured",
                 3: "disabled by policy", 4: "device busy"}
_RESULT = {0: "verified", 1: "device absent", 2: "not configured",
           3: "disabled by policy", 4: "device busy", 5: "retries exhausted",
           6: "canceled"}


def _combase():
    dll = ctypes.WinDLL("combase", use_last_error=True)
    dll.RoInitialize.argtypes = (ctypes.c_uint32,)
    dll.RoInitialize.restype = ctypes.c_long
    dll.RoUninitialize.argtypes = ()
    dll.WindowsCreateString.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32,
                                        ctypes.POINTER(ctypes.c_void_p))
    dll.WindowsCreateString.restype = ctypes.c_long
    dll.WindowsDeleteString.argtypes = (ctypes.c_void_p,)
    dll.RoGetActivationFactory.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Guid),
                                          ctypes.POINTER(ctypes.c_void_p))
    dll.RoGetActivationFactory.restype = ctypes.c_long
    return dll


class _Runtime:
    def __enter__(self):
        self.dll = _combase()
        _check(self.dll.RoInitialize(1))  # Worker thread, multi-threaded apartment.
        self.factory = ctypes.c_void_p()
        self.name = ctypes.c_void_p()
        try:
            _check(self.dll.WindowsCreateString(_CLASS, len(_CLASS), ctypes.byref(self.name)))
        except BaseException:
            self.dll.RoUninitialize()
            raise
        return self

    def __exit__(self, *_):
        _release(self.factory)
        if self.name.value:
            self.dll.WindowsDeleteString(self.name)
        self.dll.RoUninitialize()

    def activation_factory(self, iid: str):
        _check(self.dll.RoGetActivationFactory(self.name, ctypes.byref(_guid(iid)),
                                               ctypes.byref(self.factory)))
        return self.factory

    def hstring(self, value: str):
        result = ctypes.c_void_p()
        _check(self.dll.WindowsCreateString(value, len(value), ctypes.byref(result)))
        return result


def _await_operation(operation, timeout: float, cancel: Event | None) -> int | None:
    info = ctypes.c_void_p()
    try:
        _check(_method(operation, 0, ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p))(
            operation, ctypes.byref(_guid(_ASYNC_INFO)), ctypes.byref(info)))
        deadline = time.monotonic() + timeout
        while True:
            status = ctypes.c_int()
            _check(_method(info, 7, ctypes.POINTER(ctypes.c_int))(info, ctypes.byref(status)))
            if status.value == 1:
                value = ctypes.c_int()
                _check(_method(operation, 8, ctypes.POINTER(ctypes.c_int))(
                    operation, ctypes.byref(value)))
                return value.value
            if status.value in (2, 3):
                if status.value == 3:
                    error = ctypes.c_long()
                    if _method(info, 8, ctypes.POINTER(ctypes.c_long))(
                            info, ctypes.byref(error)) >= 0:
                        logging.getLogger("nasolt.hello").warning(
                            "Windows Hello async operation failed (0x%08x)",
                            error.value & 0xffffffff)
                return -2 if status.value == 2 else -3
            if cancel is not None and cancel.is_set():
                _method(info, 9)(info)
                return -2
            if time.monotonic() >= deadline:
                _method(info, 9)(info)  # Cancel the native request.
                return -1
            time.sleep(0.05)
    finally:
        if info.value:
            _method(info, 10)(info)
            _release(info)


def availability(timeout: float = 5.0) -> str:
    """Return native availability; call from a worker thread, never from Tk."""
    if sys.platform != "win32" or sys.getwindowsversion().build < 22000:
        return "unsupported Windows version"
    try:
        with _Runtime() as runtime:
            operation = ctypes.c_void_p()
            try:
                factory = runtime.activation_factory(_STATICS)
                _check(_method(factory, 6, ctypes.POINTER(ctypes.c_void_p))(
                    factory, ctypes.byref(operation)))
                result = _await_operation(operation, timeout, None)
                return _AVAILABILITY.get(result, "unavailable")
            finally:
                _release(operation)
    except (OSError, ValueError, AttributeError) as exc:
        logging.getLogger("nasolt.hello").warning("Windows Hello availability failed (%s)", type(exc).__name__)
        return "unavailable"


def verify(hwnd: int, *, timeout: float = 45.0, cancel: Event | None = None,
           purpose: str = "summon") -> str:
    """Ask Windows for fresh consent. `verified` is session reauth only."""
    if sys.platform != "win32" or sys.getwindowsversion().build < 22000 or not hwnd:
        return "unavailable"
    try:
        with _Runtime() as runtime:
            operation = ctypes.c_void_p()
            prompt = ctypes.c_void_p()
            try:
                factory = runtime.activation_factory(_INTEROP)
                message = ("Confirm it's you to enroll Windows Hello for Nasolt Vault" if
                           purpose == "enroll" else "Confirm it's you to open Nasolt Vault Summon")
                prompt = runtime.hstring(message)
                _check(_method(factory, 6, wintypes.HWND, ctypes.c_void_p,
                               ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p))(
                    factory, hwnd, prompt, ctypes.byref(_guid(_RESULT_OPERATION)),
                    ctypes.byref(operation)))
                result = _await_operation(operation, timeout, cancel)
                return {-1: "timeout", -2: "canceled"}.get(result,
                        _RESULT.get(result, "unavailable"))
            finally:
                _release(operation)
                if prompt.value:
                    runtime.dll.WindowsDeleteString(prompt)
    except (OSError, ValueError, AttributeError) as exc:
        logging.getLogger("nasolt.hello").warning("Windows Hello verification failed (%s)", type(exc).__name__)
        return "unavailable"
