"""
USB 串口传输层
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

_BAUD_RATE  = 115200
_CHUNK_SIZE = 256
_VID_PID = {(0x0416, 0x5011), (0x1a86, 0x7523)}
_DESC_KW = ["phomemo", "yinxianSen", "yin xian", "printer"]


try:
    import serial.tools.list_ports as lp
    import serial
except ImportError:
    lp = None      # type: ignore[assignment]
    serial = None  # type: ignore[assignment]


def find_usb_port() -> str | None:
    """扫描串口，返回最可能是打印机的端口名，找不到返回 None"""
    if lp is None:
        return None

    candidates: list[tuple[int, str]] = []
    for p in lp.comports():
        vid_pid = (p.vid, p.pid) if p.vid and p.pid else None
        desc = (p.description or "").lower()
        mfr  = (p.manufacturer or "").lower()
        if vid_pid in _VID_PID:
            candidates.append((0, p.device))
        elif any(kw in desc or kw in mfr for kw in _DESC_KW):
            candidates.append((1, p.device))
        elif "usb serial" in desc or "usb-serial" in desc:
            candidates.append((2, p.device))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    best = candidates[0][1]
    log.info(f"自动发现 USB 串口：{best}（共 {len(candidates)} 个候选）")
    return best


class UsbTransport:
    """USB 串口传输，负责打开/关闭串口和发送数据。"""

    def __init__(self, port: str) -> None:
        self.port = port
        self._serial = None

    def connect(self) -> None:
        if serial is None:
            raise ImportError("USB 模式需要 pyserial。请运行：pip install pyserial")
        log.info(f"USB 连接 {self.port}（{_BAUD_RATE} baud）")
        try:
            self._serial = serial.Serial(self.port, _BAUD_RATE, timeout=2)
        except Exception as e:
            self._serial = None
            raise RuntimeError(f"USB 连接失败：{e}") from e

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def write(self, data: bytes) -> None:
        if not self.is_connected:
            raise RuntimeError("USB 串口已关闭")
        self._serial.write(data)

    def write_delay(self, data: bytes, delay_s: float) -> None:
        self.write(data)
        if delay_s > 0:
            time.sleep(delay_s)

    def send_bitmap(
        self,
        data: bytes,
        on_progress: "Callable[[int, int], None] | None" = None,
    ) -> None:
        """分块发送位图数据，可选进度回调 on_progress(sent_bytes, total_bytes)"""
        total = len(data)
        sent = 0
        for i in range(0, total, _CHUNK_SIZE):
            chunk = data[i : i + _CHUNK_SIZE]
            self.write(chunk)
            sent += len(chunk)
            if on_progress:
                on_progress(sent, total)
