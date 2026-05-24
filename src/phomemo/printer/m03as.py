"""
M03ASPrinter - 印先森 M03AS 打印机驱动
对外提供统一的 print_text / print_image / print_pil_image 接口。
"""
from __future__ import annotations

import asyncio
import logging
import time
from PIL import Image

from ..constants import (
    PAPER_CONFIGS, DEFAULT_PAPER, DEFAULT_DENSITY, DEFAULT_FEED,
    WRITE_CHAR_UUID, NOTIFY_CHAR_UUID,
)
from ..protocol import (
    cmd_density, cmd_heat, cmd_init, cmd_compression,
    cmd_raster_header, cmd_feed, density_to_params,
    QUERY_COMMANDS, parse_notification,
)
from ..image_utils import image_to_bitmap, text_to_image, bitmap_preview
from ..transport.usb import UsbTransport, find_usb_port
from ..transport.ble import BleTransport

log = logging.getLogger(__name__)


class M03ASPrinter:
    """
    印先森 M03AS 打印机控制类（支持 USB / BLE / 自动切换）。

    Args:
        target:      "auto" | COM 端口（如 "COM12"）| BLE MAC 地址
        paper:       纸张宽度："53mm" / "80mm" / "15mm"
        mode:        "auto"（自动，USB 优先）| "usb" | "ble"
        ble_address: mode="auto" 回退时使用的蓝牙地址
    """

    def __init__(
        self,
        target: str = "auto",
        paper: str = DEFAULT_PAPER,
        mode: str = "auto",
        ble_address: str = "",
    ) -> None:
        if paper not in PAPER_CONFIGS:
            raise ValueError(
                f"不支持的纸张规格 '{paper}'，可选：{list(PAPER_CONFIGS.keys())}")
        if mode not in ("auto", "usb", "ble"):
            raise ValueError(f"mode 须为 'auto'/'usb'/'ble'，收到：'{mode}'")

        self.target       = target
        self.paper        = paper
        self.mode         = mode
        self.ble_address  = ble_address
        self._cfg         = PAPER_CONFIGS[paper]

        self._active_mode: str = ""
        self._usb: UsbTransport | None = None
        self._ble: BleTransport | None = None
        self._ble_info: dict = {}

    # ── 属性 ─────────────────────────────────────────────────────

    @property
    def width_bytes(self) -> int:
        return self._cfg["width_bytes"]

    @property
    def width_px(self) -> int:
        return self._cfg["width_px"]

    @property
    def is_connected(self) -> bool:
        if self._active_mode == "usb":
            return self._usb is not None and self._usb.is_connected
        return self._ble is not None and self._ble.is_connected

    # ── 连接管理 ─────────────────────────────────────────────────

    async def connect(self, timeout: float = 15.0) -> None:
        if self.mode == "auto":
            await self._connect_auto(timeout)
        elif self.mode == "usb":
            await self._do_connect_usb(self.target)
        else:
            await self._do_connect_ble(self.ble_address or self.target, timeout)

    async def disconnect(self) -> None:
        if self._active_mode == "usb" and self._usb:
            self._usb.disconnect()
            self._usb = None
            print("🔌 已关闭串口")
        elif self._active_mode == "ble" and self._ble:
            await self._ble.disconnect()
            self._ble = None
            print("🔴 已断开 BLE 连接")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()

    async def _connect_auto(self, timeout: float) -> None:
        usb_port = find_usb_port() if self.target == "auto" else (
            self.target if not self._is_mac(self.target) else None
        )
        if usb_port:
            print(f"🔍 发现 USB 串口 {usb_port}，优先使用 USB...")
            try:
                await self._do_connect_usb(usb_port)
                return
            except Exception as e:
                log.warning(f"USB 连接失败（{e}），回退蓝牙...")
                print("   USB 失败，切换蓝牙...")

        ble_addr = self.ble_address or (
            self.target if self._is_mac(self.target) else "")
        if not ble_addr:
            raise RuntimeError(
                "未找到 USB 串口，且未配置蓝牙地址。\n"
                "请设置 ble_address 参数或通过 USB 连接打印机。")
        print(f"📡 切换蓝牙（{ble_addr}）...")
        await self._do_connect_ble(ble_addr, timeout)

    async def _do_connect_usb(self, port: str) -> None:
        self._usb = UsbTransport(port)
        self._usb.connect()
        self._active_mode = "usb"
        print(f"✅ 已连接！[USB:{port}] 纸张：{self.paper}，{self.width_px}px")

    async def _do_connect_ble(self, addr: str, timeout: float) -> None:
        print(f"🔵 扫描蓝牙 {addr}...")
        self._ble = BleTransport(addr, WRITE_CHAR_UUID, NOTIFY_CHAR_UUID)
        await self._ble.connect(timeout)
        self._active_mode = "ble"
        await self._ble.enable_notify(self._on_notify)
        print(f"✅ 已连接！[BLE:{addr}] 纸张：{self.paper}，{self.width_px}px")

    @staticmethod
    def _is_mac(s: str) -> bool:
        parts = s.split(":")
        return len(parts) == 6 and all(len(p) == 2 for p in parts)

    # ── 状态查询（仅 BLE） ────────────────────────────────────────

    async def query_status(self) -> dict:
        if self._active_mode == "usb":
            log.info("USB 模式不支持状态查询")
            return {}
        if not self.is_connected:
            raise RuntimeError("未连接")
        self._ble_info.clear()
        for name, cmd in QUERY_COMMANDS.items():
            try:
                await self._ble.write(cmd)
                await asyncio.sleep(0.120)
            except Exception as e:
                log.warning(f"查询 {name} 失败：{e}")
        return dict(self._ble_info)

    # ── 高级打印接口 ──────────────────────────────────────────────

    async def print_text(
        self,
        text: str,
        font_size: int = 40,
        font_path: str | None = None,
        density: int = DEFAULT_DENSITY,
        feed: int = DEFAULT_FEED,
        preview: bool = False,
    ) -> None:
        """打印文字（支持中英文、自动换行）"""
        print(f"📝 渲染文字（{len(text)} 字符，字号 {font_size}px）...")
        img = text_to_image(text, self.width_px, font_size=font_size,
                            font_path=font_path)
        bitmap, wb, h = image_to_bitmap(img, self.width_px)
        print(f"   → 位图：{wb * 8}×{h}px")
        if preview:
            bitmap_preview(bitmap, wb, h)
        await self._print_bitmap(bitmap, wb, h, density, feed)

    async def print_image(
        self,
        image_path: str,
        density: int = DEFAULT_DENSITY,
        feed: int = DEFAULT_FEED,
        dither: bool = True,
        preview: bool = False,
    ) -> None:
        """打印图片文件（JPEG/PNG/BMP）"""
        print(f"🖼  加载图片：{image_path}")
        img = Image.open(image_path)
        bitmap, wb, h = image_to_bitmap(img, self.width_px, dither=dither)
        print(f"   → 位图：{wb * 8}×{h}px")
        if preview:
            bitmap_preview(bitmap, wb, h)
        await self._print_bitmap(bitmap, wb, h, density, feed)

    async def print_pil_image(
        self,
        img: Image.Image,
        density: int = DEFAULT_DENSITY,
        feed: int = DEFAULT_FEED,
        dither: bool = True,
    ) -> None:
        """直接打印 PIL Image（供 Home Assistant 集成使用）"""
        bitmap, wb, h = image_to_bitmap(img, self.width_px, dither=dither)
        await self._print_bitmap(bitmap, wb, h, density, feed)

    # ── 底层打印分发 ──────────────────────────────────────────────

    async def _print_bitmap(
        self,
        bitmap: bytes,
        width_bytes: int,
        height_lines: int,
        density: int = DEFAULT_DENSITY,
        feed: int = DEFAULT_FEED,
    ) -> None:
        if not self.is_connected:
            raise RuntimeError("未连接打印机，请先调用 connect()")
        if self._active_mode == "usb":
            await self._print_usb(bitmap, width_bytes, height_lines, density, feed)
        else:
            await self._print_ble(bitmap, width_bytes, height_lines, density, feed)

    # ── USB 打印 ──────────────────────────────────────────────────

    async def _print_usb(self, bitmap, wb, h, density, feed) -> None:
        level, heat = density_to_params(density)
        feed_count = max(0, round(feed / 16))
        log.info(f"[USB] {wb}B×{h}行，密度={density} level={level} heat={heat}")
        print(f"🖨  开始打印（{wb * 8}×{h}px）[USB]...")

        usb = self._usb
        usb.write_delay(cmd_density(level), 0.030)
        usb.write_delay(cmd_heat(heat),     0.030)
        usb.write_delay(cmd_init(),         0.030)
        usb.write_delay(cmd_compression(),  0.030)
        usb.write(cmd_raster_header(wb, h))

        def _progress(sent, total):
            pct = sent * 100 // total
            print(f"\r   [{'█' * (pct // 5):<20}] {pct:3d}%",
                  end="", flush=True)

        usb.send_bitmap(bitmap, on_progress=_progress)
        print()
        time.sleep(0.5)
        for _ in range(feed_count):
            usb.write_delay(cmd_feed(), 0.030)
        time.sleep(0.5)
        print("✅ 打印完成！")

    # ── BLE 打印 ──────────────────────────────────────────────────

    async def _print_ble(self, bitmap, wb, h, density, feed) -> None:
        level, heat = density_to_params(density)
        feed_count = max(0, round(feed / 16))
        log.info(f"[BLE] {wb}B×{h}行，密度={density} level={level} heat={heat}")
        print(f"🖨  开始打印（{wb * 8}×{h}px）[BLE]...")

        ble = self._ble
        await ble.write_delay(cmd_density(level), 0.030)
        await ble.write_delay(cmd_heat(heat),     0.030)
        await ble.write_delay(cmd_init(),         0.030)
        await ble.write_delay(cmd_compression(),  0.030)

        def _progress(sent, total):
            pct = sent * 100 // total
            print(f"\r   [{'█' * (pct // 5):<20}] {pct:3d}%",
                  end="", flush=True)

        await ble.send_bitmap_segmented(
            bitmap, wb, h, cmd_raster_header, on_progress=_progress)
        print()
        await asyncio.sleep(0.5)
        for _ in range(feed_count):
            await ble.write_delay(cmd_feed(), 0.030)
        await asyncio.sleep(0.6)
        print("✅ 打印完成！")

    # ── BLE 通知回调 ──────────────────────────────────────────────

    def _on_notify(self, _sender, data: bytearray) -> None:
        result = parse_notification(bytes(data))
        if result:
            log.info(f"[打印机] {result['field']} = {result['value']}")
            self._ble_info[result["field"]] = result["value"]
            if result["field"] == "battery":
                print(f"   🔋 电量：{result['value']}")
            elif result["field"] == "paper" and result["value"] == "out":
                print("   ⚠  纸张用尽！")
