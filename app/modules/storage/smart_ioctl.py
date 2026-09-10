"""Read SMART / NVMe health from the drive itself (not only WMI).

Uses DeviceIoControl on \\\\.\\PhysicalDriveN — the same class of pass-through
vendor tools use. Usually needs Administrator. Never fabricates sensors.
"""

from __future__ import annotations

import ctypes
import logging
import struct
import sys
from ctypes import wintypes
from dataclasses import dataclass

logger = logging.getLogger("techbench.storage.smart")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
INVALID_HANDLE = ctypes.c_void_p(-1).value
ERROR_ACCESS_DENIED = 5

IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
IOCTL_ATA_PASS_THROUGH = 0x4D02C

StorageDeviceProtocolSpecificProperty = 50
StorageDeviceTemperatureProperty = 52
StorageDeviceEnduranceProperty = 62
PropertyStandardQuery = 0
ProtocolTypeNvme = 3
NVMeDataTypeLogPage = 2
NVME_LOG_HEALTH = 2

ATA_FLAGS_DRDY_REQUIRED = 0x01
ATA_FLAGS_DATA_IN = 0x02
SMART_CMD = 0xB0
SMART_READ_DATA = 0xD0
SMART_RETURN_STATUS = 0xDA
SMART_CYL_LOW = 0x4F
SMART_CYL_HIGH = 0xC2
SMART_FAIL_LOW = 0xF4
SMART_FAIL_HIGH = 0x2C

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
_kernel32 = None
_ioctl_access_denied = False


def _k32():
    global _kernel32
    if _kernel32 is None:
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _kernel32.CreateFileW.restype = wintypes.HANDLE
        _kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        _kernel32.DeviceIoControl.restype = wintypes.BOOL
        _kernel32.CloseHandle.restype = wintypes.BOOL
    return _kernel32


@dataclass
class SmartReading:
    available: bool = False
    predict_failure: bool | None = None
    realloc_or_pending: bool = False
    temperature_c: int | None = None
    note: str = "SMART information unavailable"
    source: str = ""
    needs_admin: bool = False
    wear: str = "Unavailable"
    spare: str = "Unavailable"
    power_on_hours: str = "Unavailable"


class ATA_PASS_THROUGH_EX(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_uint16),
        ("AtaFlags", ctypes.c_uint16),
        ("PathId", ctypes.c_uint8),
        ("TargetId", ctypes.c_uint8),
        ("Lun", ctypes.c_uint8),
        ("ReservedAsUchar", ctypes.c_uint8),
        ("DataTransferLength", ctypes.c_uint32),
        ("TimeOutValue", ctypes.c_uint32),
        ("ReservedAsUlong", ctypes.c_uint32),
        ("DataBufferOffset", ULONG_PTR),
        ("PreviousTaskFile", ctypes.c_uint8 * 8),
        ("CurrentTaskFile", ctypes.c_uint8 * 8),
    ]


def _u128(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 16], "little")


def parse_nvme_health(data: bytes) -> SmartReading:
    """NVMe SMART / Health Information log (LID 02h)."""
    if len(data) < 192:
        return SmartReading()
    warning = data[0]
    kelvin = int.from_bytes(data[1:3], "little")
    spare = data[3]
    spare_th = data[4]
    used = data[5]
    hours = _u128(data, 128)
    temp = kelvin - 273 if 200 <= kelvin <= 400 else None
    fail = bool(warning & 0b00011101) or (spare_th > 0 and spare < spare_th)
    parts = ["NVMe health log"]
    if warning:
        parts.append(f"critical warning 0x{warning:02x}")
    else:
        parts.append("no critical warning")
    wear = f"{used}% used (measured NVMe)" if used <= 255 else "Unavailable"
    spare_txt = f"{spare}% (threshold {spare_th}%)" if spare_th or spare else f"{spare}%"
    hours_txt = f"{hours}" if 0 < hours < 10_000_000 else "Unavailable"
    return SmartReading(
        available=True,
        predict_failure=fail,
        realloc_or_pending=fail and bool(warning & 0b00000100),
        temperature_c=temp,
        note="; ".join(parts),
        source="NVMe health log",
        wear=wear,
        spare=spare_txt,
        power_on_hours=hours_txt,
    )


def parse_ata_smart(data: bytes, *, predict_failure: bool | None = None) -> SmartReading:
    """ATA SMART READ DATA (512 bytes)."""
    if len(data) < 362:
        return SmartReading()
    realloc = False
    temp: int | None = None
    hours: int | None = None
    life: int | None = None
    for i in range(30):
        base = 2 + i * 12
        attr_id = data[base]
        if attr_id == 0:
            continue
        raw = data[base + 5 : base + 11]
        raw_val = int.from_bytes(raw, "little")
        current = data[base + 3]
        if attr_id in {5, 196, 197, 198} and raw_val > 0:
            realloc = True
        if attr_id in {190, 194} and temp is None:
            candidate = raw[0]
            if 1 <= candidate <= 125:
                temp = candidate
        if attr_id == 9 and hours is None and 0 < raw_val < 10_000_000:
            hours = raw_val
        if attr_id in {169, 173, 177, 231, 233} and 1 <= current <= 100 and life is None:
            life = current
    predict = predict_failure
    if predict is None:
        predict = False
    note = (
        "SMART predictive failure is set"
        if predict
        else "SMART predictive failure is not set"
    )
    return SmartReading(
        available=True,
        predict_failure=predict,
        realloc_or_pending=realloc,
        temperature_c=temp,
        note=note,
        source="ATA SMART",
        wear=f"{life}% remaining (SMART)" if life is not None else "Unavailable",
        power_on_hours=str(hours) if hours is not None else "Unavailable",
    )


def parse_windows_temperature(blob: bytes) -> int | None:
    """STORAGE_TEMPERATURE_DATA_DESCRIPTOR — first sensor, Celsius."""
    if len(blob) < 28:
        return None
    info_count = struct.unpack_from("<H", blob, 12)[0]
    if info_count < 1 or len(blob) < 28:
        return None
    temp = struct.unpack_from("<h", blob, 26)[0]
    if -40 <= temp <= 125:
        return int(temp)
    return None


def parse_windows_endurance(blob: bytes) -> int | None:
    """STORAGE_ENDURANCE_DATA_DESCRIPTOR.EnduranceInfo.LifePercentage (used %)."""
    if len(blob) < 36:
        return None
    used = struct.unpack_from("<I", blob, 32)[0]
    if 0 <= used <= 100:
        return int(used)
    return None


def read_physical_drive(index: int) -> SmartReading:
    """Best-effort SMART from PhysicalDriveN. Empty reading if not Windows."""
    if sys.platform != "win32" or index < 0:
        return SmartReading()
    global _ioctl_access_denied
    _ioctl_access_denied = False
    handle, denied = _open_drive(index)
    if handle is None:
        note = (
            "SMART/temperature need administrator rights"
            if denied
            else "SMART information unavailable"
        )
        return SmartReading(needs_admin=denied, note=note)
    try:
        reading = _read_handle(handle)
        if not reading.available and (denied or _ioctl_access_denied):
            reading.needs_admin = True
            reading.note = "SMART/temperature need administrator rights"
        return reading
    except Exception:
        logger.debug("SMART ioctl failed for PhysicalDrive%s", index, exc_info=True)
        return SmartReading(
            needs_admin=denied or _ioctl_access_denied,
            note=(
                "SMART/temperature need administrator rights"
                if denied or _ioctl_access_denied
                else "SMART information unavailable"
            ),
        )
    finally:
        _k32().CloseHandle(handle)


def _open_drive(index: int) -> tuple[object | None, bool]:
    path = f"\\\\.\\PhysicalDrive{index}"
    k32 = _k32()
    denied = False
    for access in (GENERIC_READ | GENERIC_WRITE, GENERIC_READ):
        handle = k32.CreateFileW(
            path,
            access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        hval = ctypes.cast(handle, ctypes.c_void_p).value
        if hval not in (None, INVALID_HANDLE):
            return handle, denied
        if ctypes.get_last_error() == ERROR_ACCESS_DENIED:
            denied = True
    return None, denied


def _device_io(handle: object, code: int, indata: bytes, out_size: int) -> bytes | None:
    global _ioctl_access_denied
    k32 = _k32()
    in_buf = ctypes.create_string_buffer(indata, len(indata)) if indata else None
    out_buf = ctypes.create_string_buffer(out_size)
    returned = wintypes.DWORD(0)
    ok = k32.DeviceIoControl(
        handle,
        code,
        in_buf,
        len(indata) if indata else 0,
        out_buf,
        out_size,
        ctypes.byref(returned),
        None,
    )
    if not ok:
        if ctypes.get_last_error() == ERROR_ACCESS_DENIED:
            _ioctl_access_denied = True
        return None
    size = returned.value or out_size
    return out_buf.raw[:size]


def _read_handle(handle: wintypes.HANDLE) -> SmartReading:
    reading = SmartReading()
    nvme = _try_nvme(handle)
    if nvme.available:
        reading = nvme
    else:
        ata = _try_ata(handle)
        if ata.available:
            reading = ata

    temp = _try_windows_temperature(handle)
    if reading.temperature_c is None and temp is not None:
        reading.temperature_c = temp
        if not reading.source:
            reading.source = "Windows storage sensor"

    used = _try_windows_endurance(handle)
    if reading.wear == "Unavailable" and used is not None:
        reading.wear = f"{used}% used (Windows endurance)"

    if not reading.available and reading.temperature_c is not None:
        reading.note = "Temperature from Windows; SMART attributes unavailable"
    return reading


def _try_nvme(handle: wintypes.HANDLE) -> SmartReading:
    data_len = 512
    proto_size = 40  # STORAGE_PROTOCOL_SPECIFIC_DATA
    header = struct.pack("<II", StorageDeviceProtocolSpecificProperty, PropertyStandardQuery)
    for nsid in (0xFFFFFFFF, 1, 0):
        proto = struct.pack(
            "<10I",
            ProtocolTypeNvme,
            NVMeDataTypeLogPage,
            NVME_LOG_HEALTH,
            nsid,
            proto_size,
            data_len,
            0,
            0,
            0,
            0,
        )
        payload = header + proto + bytes(data_len)
        out = _device_io(handle, IOCTL_STORAGE_QUERY_PROPERTY, payload, len(payload))
        if not out or len(out) < 8 + proto_size + 16:
            continue
        offset = struct.unpack_from("<I", out, 8 + 16)[0]
        length = struct.unpack_from("<I", out, 8 + 20)[0]
        start = 8 + (offset or proto_size)
        blob = out[start : start + (length or data_len)]
        parsed = parse_nvme_health(blob)
        if parsed.available:
            return parsed
    return SmartReading()


def _try_ata(handle: wintypes.HANDLE) -> SmartReading:
    predict = _ata_return_status(handle)
    blob = _ata_command(handle, SMART_READ_DATA, data_in=True)
    if not blob:
        return SmartReading()
    return parse_ata_smart(blob, predict_failure=predict)


def _ata_return_status(handle: wintypes.HANDLE) -> bool | None:
    raw = _ata_command(handle, SMART_RETURN_STATUS, data_in=False)
    if raw is None:
        return None
    if len(raw) < 2:
        return None
    low, high = raw[0], raw[1]
    if low == SMART_FAIL_LOW and high == SMART_FAIL_HIGH:
        return True
    if low == SMART_CYL_LOW and high == SMART_CYL_HIGH:
        return False
    return None


def _ata_command(handle: wintypes.HANDLE, feature: int, *, data_in: bool) -> bytes | None:
    size = ctypes.sizeof(ATA_PASS_THROUGH_EX)
    pkt = ATA_PASS_THROUGH_EX()
    pkt.Length = size
    pkt.AtaFlags = ATA_FLAGS_DRDY_REQUIRED
    pkt.TimeOutValue = 10
    pkt.DataBufferOffset = size
    if data_in:
        pkt.AtaFlags |= ATA_FLAGS_DATA_IN
        pkt.DataTransferLength = 512
    task = pkt.CurrentTaskFile
    task[0] = feature
    task[1] = 1
    task[2] = 1
    task[3] = SMART_CYL_LOW
    task[4] = SMART_CYL_HIGH
    task[5] = 0xA0
    task[6] = SMART_CMD
    buf = bytes(pkt) + (bytes(512) if data_in else b"")
    out = _device_io(handle, IOCTL_ATA_PASS_THROUGH, buf, len(buf))
    if not out or len(out) < size:
        return None
    if data_in:
        return out[size : size + 512]
    out_pkt = ATA_PASS_THROUGH_EX.from_buffer_copy(out[:size])
    return bytes(out_pkt.CurrentTaskFile[3:5])


def _try_windows_temperature(handle: wintypes.HANDLE) -> int | None:
    query = struct.pack("<II", StorageDeviceTemperatureProperty, PropertyStandardQuery)
    out = _device_io(handle, IOCTL_STORAGE_QUERY_PROPERTY, query, 256)
    if not out:
        return None
    return parse_windows_temperature(out)


def _try_windows_endurance(handle: wintypes.HANDLE) -> int | None:
    query = struct.pack("<II", StorageDeviceEnduranceProperty, PropertyStandardQuery)
    out = _device_io(handle, IOCTL_STORAGE_QUERY_PROPERTY, query, 128)
    if not out:
        return None
    return parse_windows_endurance(out)
