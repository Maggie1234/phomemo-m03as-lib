"""
M04 协议命令构造（纯函数，无 I/O）
逆向自 phomymo 开源项目 src/web/printer.js
"""
from __future__ import annotations


def cmd_density(level: int) -> bytes:
    """[1F 11 02 <level>] 打印密度 0x00~0x0F"""
    return bytes([0x1F, 0x11, 0x02, level & 0x0F])


def cmd_heat(param: int) -> bytes:
    """[1F 11 37 <param>] 加热参数，实测有效范围约 100~250"""
    return bytes([0x1F, 0x11, 0x37, param & 0xFF])


def cmd_init() -> bytes:
    """[1F 11 0B] 初始化，设为连续纸模式"""
    return bytes([0x1F, 0x11, 0x0B])


def cmd_compression(mode: int = 0x00) -> bytes:
    """[1F 11 35 <mode>] 压缩模式，0x00=原始位图（推荐）"""
    return bytes([0x1F, 0x11, 0x35, mode & 0xFF])


def cmd_raster_header(width_bytes: int, height_lines: int) -> bytes:
    """[1D 76 30 00 <wL> <wH> <hL> <hH>] ESC/POS 栅格图像头"""
    return bytes([
        0x1D, 0x76, 0x30, 0x00,
        width_bytes & 0xFF, (width_bytes >> 8) & 0xFF,
        height_lines & 0xFF, (height_lines >> 8) & 0xFF,
    ])


def cmd_feed() -> bytes:
    """[1B 64 02] 进纸"""
    return bytes([0x1B, 0x64, 0x02])


def density_to_params(density: int) -> tuple[int, int]:
    """1~8档密度 → (m04_level, m04_heat)"""
    density = max(1, min(8, density))
    level = round((density / 8) * 15)
    heat  = round(100 + (density - 1) * 50 / 3)
    return level, heat


# 状态查询命令
QUERY_COMMANDS = {
    "battery":  bytes([0x1F, 0x11, 0x08]),
    "paper":    bytes([0x1F, 0x11, 0x11]),
    "firmware": bytes([0x1F, 0x11, 0x07]),
    "serial":   bytes([0x1F, 0x11, 0x09]),
}


def parse_notification(data: bytes) -> dict | None:
    """解析 BLE 通知回包 → {"field", "value", "raw"}"""
    if len(data) < 3 or data[0] != 0x1A:
        return None
    type_byte  = data[1]
    value_byte = data[2]
    mapping = {
        0x04: ("battery",      _parse_battery),
        0x05: ("cover",        lambda b: "open" if b == 0x98 else "closed"),
        0x06: ("paper",        lambda b: "out" if b == 0x88 else "ok"),
        0x07: ("firmware",     lambda b: ".".join(str(x) for x in data[2:])),
        0x08: ("serial",       lambda b: data[2:].decode("ascii", errors="replace")),
        0x0B: ("print_status", lambda b: "error" if b == 0xB8 else str(b)),
    }
    if type_byte in mapping:
        field, parser = mapping[type_byte]
        return {"field": field, "value": parser(value_byte), "raw": data.hex(" ")}
    return {"field": f"unknown_0x{type_byte:02x}", "value": None, "raw": data.hex(" ")}


def _parse_battery(b: int) -> str:
    table = {
        0xA4: "0%",  0xA3: "3%",  0xA2: "5%",  0xA1: "10%",
        0x64: "100%",0x5A: "90%", 0x50: "80%", 0x46: "70%",
        0x3C: "60%", 0x32: "50%", 0x28: "40%", 0x1E: "30%",
        0x14: "20%", 0x0A: "10%",
    }
    if b in table:
        return table[b]
    if 0 <= b <= 100:
        return f"{b}%"
    return f"raw=0x{b:02X}"
