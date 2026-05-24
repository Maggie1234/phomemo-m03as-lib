"""
M03AS 打印机常量
"""
from __future__ import annotations

# BLE GATT UUIDs
SERVICE_UUID    = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID= "0000ff03-0000-1000-8000-00805f9b34fb"

# 纸张规格（300 DPI）
PAPER_CONFIGS: dict[str, dict] = {
    "53mm": {"width_bytes": 75,  "width_px": 600, "dpi": 300},
    "80mm": {"width_bytes": 112, "width_px": 896, "dpi": 300},
    "15mm": {"width_bytes": 23,  "width_px": 184, "dpi": 300},
}

DEFAULT_PAPER   = "53mm"
DEFAULT_DENSITY = 6
DEFAULT_FEED    = 16   # 0=不额外进纸，16=1条命令，32=2条命令

# USB 串口匹配规则（自动发现用）
USB_VID_PID = {
    (0x0416, 0x5011),
    (0x1a86, 0x7523),  # CH340
}
USB_DESC_KEYWORDS = ["phomemo", "yinxianSen", "yin xian", "printer"]
USB_BAUD_RATE = 115200
