"""
测试 protocol.py：命令字节构造、密度换算、通知解析
"""
import pytest
from phomemo.protocol import (
    cmd_density, cmd_heat, cmd_init, cmd_compression,
    cmd_raster_header, cmd_feed, density_to_params,
    parse_notification,
)


class TestCommands:
    def test_density_prefix(self):
        data = cmd_density(0x04)
        assert data[:3] == bytes([0x1F, 0x11, 0x02])
        assert data[3] == 0x04

    def test_density_clamps_to_nibble(self):
        # level 只能是 0x00~0x0F，超出应被 & 0x0F 截断
        assert cmd_density(0xFF)[3] == 0x0F

    def test_heat_prefix(self):
        data = cmd_heat(200)
        assert data[:3] == bytes([0x1F, 0x11, 0x37])
        assert data[3] == 200

    def test_init(self):
        assert cmd_init() == bytes([0x1F, 0x11, 0x0B])

    def test_compression_default(self):
        assert cmd_compression() == bytes([0x1F, 0x11, 0x35, 0x00])

    def test_compression_custom(self):
        assert cmd_compression(0x01)[3] == 0x01

    def test_feed(self):
        assert cmd_feed() == bytes([0x1B, 0x64, 0x02])

    def test_raster_header_format(self):
        hdr = cmd_raster_header(width_bytes=75, height_lines=100)
        assert hdr[0:4] == bytes([0x1D, 0x76, 0x30, 0x00])
        # width = 75 = 0x4B, little-endian → 0x4B, 0x00
        assert hdr[4] == 75
        assert hdr[5] == 0
        # height = 100 = 0x64, little-endian → 0x64, 0x00
        assert hdr[6] == 100
        assert hdr[7] == 0

    def test_raster_header_large_values(self):
        # 896 像素宽度 → width_bytes=112，测试 16-bit LE
        hdr = cmd_raster_header(width_bytes=112, height_lines=500)
        assert hdr[4] == 112
        assert hdr[5] == 0
        assert hdr[6] == (500 & 0xFF)
        assert hdr[7] == (500 >> 8)


class TestDensityConversion:
    def test_min_density(self):
        level, heat = density_to_params(1)
        assert level == 2         # round(1/8 * 15) = round(1.875) = 2
        assert heat == 100

    def test_max_density(self):
        level, heat = density_to_params(8)
        assert level == 15        # round(8/8 * 15) = 15
        assert heat > 100

    def test_density_clamp_low(self):
        l1, h1 = density_to_params(0)
        l2, h2 = density_to_params(1)
        assert l1 == l2 and h1 == h2

    def test_density_clamp_high(self):
        l1, h1 = density_to_params(8)
        l2, h2 = density_to_params(99)
        assert l1 == l2 and h1 == h2

    @pytest.mark.parametrize("d", [1, 2, 3, 4, 5, 6, 7, 8])
    def test_density_range_valid(self, d):
        level, heat = density_to_params(d)
        assert 0 <= level <= 15
        assert 100 <= heat <= 300


class TestParseNotification:
    def test_battery_table_value(self):
        # 0x64 = 100%
        result = parse_notification(bytes([0x1A, 0x04, 0x64]))
        assert result is not None
        assert result["field"] == "battery"
        assert result["value"] == "100%"

    def test_battery_raw_percent(self):
        # 直接用 50 表示 50%
        result = parse_notification(bytes([0x1A, 0x04, 50]))
        assert result["value"] == "50%"

    def test_paper_ok(self):
        result = parse_notification(bytes([0x1A, 0x06, 0x00]))
        assert result["field"] == "paper"
        assert result["value"] == "ok"

    def test_paper_out(self):
        result = parse_notification(bytes([0x1A, 0x06, 0x88]))
        assert result["value"] == "out"

    def test_cover_open(self):
        result = parse_notification(bytes([0x1A, 0x05, 0x98]))
        assert result["field"] == "cover"
        assert result["value"] == "open"

    def test_cover_closed(self):
        result = parse_notification(bytes([0x1A, 0x05, 0x00]))
        assert result["value"] == "closed"

    def test_unknown_type(self):
        result = parse_notification(bytes([0x1A, 0xFF, 0x00]))
        assert result is not None
        assert "unknown" in result["field"]

    def test_invalid_header(self):
        assert parse_notification(bytes([0x00, 0x04, 0x64])) is None

    def test_too_short(self):
        assert parse_notification(bytes([0x1A, 0x04])) is None
