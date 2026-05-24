"""
BLE 传输层（依赖可选包 bleak）
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

_CHUNK_MAX            = 128
_MAX_ROWS_PER_SEGMENT = 320
_SEGMENT_PAUSE        = 1.0


class BleTransport:
    """BLE GATT 传输，负责扫描、连接和发送数据。"""

    def __init__(self, address: str, write_uuid: str, notify_uuid: str) -> None:
        self.address     = address
        self.write_uuid  = write_uuid
        self.notify_uuid = notify_uuid
        self._client     = None
        self.chunk_size  = _CHUNK_MAX
        self.segment_rows = _MAX_ROWS_PER_SEGMENT
        self.segment_pause = _SEGMENT_PAUSE

    async def connect(self, timeout: float = 15.0) -> None:
        try:
            from bleak import BleakClient, BleakError, BleakScanner
        except ImportError:
            raise ImportError(
                "BLE 模式需要 bleak 库。请运行：pip install 'phomemo-m03as[ble]'")

        scan_secs = min(8.0, timeout)
        device = None
        for attempt in range(3):
            if attempt > 0:
                log.info(f"未发现设备，{scan_secs:.0f}s 后重试（{attempt+1}/3）...")
                await asyncio.sleep(scan_secs)
            device = await BleakScanner.find_device_by_address(
                self.address, timeout=scan_secs)
            if device:
                break

        if device is None:
            raise BleakError(
                f"未找到蓝牙设备 {self.address}。\n"
                "M03AS 固件限制：插过 USB 后需重启打印机才能恢复蓝牙广播。")

        self._client = BleakClient(device, timeout=timeout)
        await self._client.connect()

        if not self._client.is_connected:
            raise BleakError("连接后状态异常，请重试")

        for retry in range(2):
            mtu = self._client.mtu_size
            if mtu > 23:
                break
            log.info(f"MTU={mtu}，第 {retry+1} 次重连以协商更大 MTU...")
            await self._client.disconnect()
            await asyncio.sleep(2.0)
            await self._client.connect()

        mtu = self._client.mtu_size
        self.chunk_size = min(_CHUNK_MAX, max(20, mtu - 3))
        log.info(f"BLE 已连接，MTU={mtu}，chunk_size={self.chunk_size}")

    async def enable_notify(self, callback) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.start_notify(self.notify_uuid, callback)
            except Exception as e:
                log.warning(f"BLE 通知启用失败（不影响打印）：{e}")

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(self.notify_uuid)
            except Exception:
                pass
            await self._client.disconnect()
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def write(self, data: bytes, response: bool = True) -> None:
        if not self.is_connected:
            raise RuntimeError("BLE 连接已断开")
        await self._client.write_gatt_char(self.write_uuid, data, response=response)

    async def write_delay(self, data: bytes, delay_s: float) -> None:
        await self.write(data)
        if delay_s > 0:
            await asyncio.sleep(delay_s)

    async def send_bitmap_segmented(
        self,
        bitmap: bytes,
        width_bytes: int,
        height_lines: int,
        raster_header_fn,
        on_progress=None,
    ) -> None:
        """
        分段发送位图（BLE 特有，防止缓冲区溢出）。
        raster_header_fn(width_bytes, rows) → bytes
        on_progress(sent_bytes, total_bytes) 可选进度回调
        """
        total_segs = (height_lines + self.segment_rows - 1) // self.segment_rows
        total = len(bitmap)
        total_sent = 0

        for seg_idx in range(total_segs):
            r0  = seg_idx * self.segment_rows
            r1  = min(r0 + self.segment_rows, height_lines)
            seg_data = bitmap[r0 * width_bytes : r1 * width_bytes]

            await self.write(
                raster_header_fn(width_bytes, r1 - r0), response=True)

            for i in range(0, len(seg_data), self.chunk_size):
                chunk = seg_data[i : i + self.chunk_size]
                await self.write(chunk, response=True)
                total_sent += len(chunk)
                if on_progress:
                    on_progress(total_sent, total)

            if seg_idx < total_segs - 1:
                await asyncio.sleep(self.segment_pause)
