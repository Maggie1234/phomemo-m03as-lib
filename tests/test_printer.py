"""
测试 M03ASPrinter：初始化校验、mode 路由、context manager
使用 mock transport，不需要真实打印机。
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from PIL import Image

from phomemo.printer.m03as import M03ASPrinter
from phomemo.constants import PAPER_CONFIGS


class TestPrinterInit:
    def test_valid_paper(self):
        p = M03ASPrinter(paper="80mm")
        assert p.width_px == 896
        assert p.width_bytes == 112

    def test_valid_paper_53mm(self):
        p = M03ASPrinter(paper="53mm")
        assert p.width_px == 600

    def test_invalid_paper_raises(self):
        with pytest.raises(ValueError, match="不支持的纸张规格"):
            M03ASPrinter(paper="100mm")

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            M03ASPrinter(mode="wifi")

    def test_default_mode_is_auto(self):
        p = M03ASPrinter()
        assert p.mode == "auto"

    def test_not_connected_initially(self):
        p = M03ASPrinter()
        assert not p.is_connected


class TestPrinterUsb:
    """USB 模式测试（mock serial）"""

    def _make_mock_usb(self):
        mock = MagicMock()
        mock.is_connected = True
        mock.connect = MagicMock()
        mock.disconnect = MagicMock()
        mock.write = MagicMock()
        mock.write_delay = MagicMock()
        mock.send_bitmap = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_connect_usb_mode(self):
        p = M03ASPrinter(target="COM12", paper="53mm", mode="usb")
        with patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = self._make_mock_usb()
            MockUsb.return_value = mock_transport
            await p.connect()
            assert p._active_mode == "usb"
            assert p.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_usb(self):
        p = M03ASPrinter(target="COM12", paper="53mm", mode="usb")
        with patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = self._make_mock_usb()
            MockUsb.return_value = mock_transport
            await p.connect()
            await p.disconnect()
            mock_transport.disconnect.assert_called_once()
            assert p._usb is None

    @pytest.mark.asyncio
    async def test_print_text_usb(self):
        p = M03ASPrinter(target="COM12", paper="53mm", mode="usb")
        with patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = self._make_mock_usb()
            MockUsb.return_value = mock_transport
            await p.connect()
            await p.print_text("测试文字", density=6, feed=0)
            # 至少调用了 write / write_delay
            assert mock_transport.write_delay.called or mock_transport.write.called

    @pytest.mark.asyncio
    async def test_print_pil_image_usb(self):
        p = M03ASPrinter(target="COM12", paper="53mm", mode="usb")
        with patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = self._make_mock_usb()
            MockUsb.return_value = mock_transport
            await p.connect()
            img = Image.new("RGB", (600, 50), (200, 200, 200))
            await p.print_pil_image(img, density=5, feed=0)
            assert mock_transport.send_bitmap.called

    @pytest.mark.asyncio
    async def test_print_without_connect_raises(self):
        p = M03ASPrinter(target="COM12", paper="53mm", mode="usb")
        with pytest.raises(RuntimeError, match="未连接"):
            await p.print_text("hello")


class TestPrinterAutoMode:
    """自动模式路由测试"""

    @pytest.mark.asyncio
    async def test_auto_picks_usb_when_available(self):
        p = M03ASPrinter(target="auto", paper="53mm", mode="auto",
                         ble_address="AA:BB:CC:DD:EE:FF")
        with patch("phomemo.printer.m03as.find_usb_port", return_value="COM12"), \
             patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = MagicMock()
            mock_transport.is_connected = True
            mock_transport.connect = MagicMock()
            MockUsb.return_value = mock_transport
            await p.connect()
            assert p._active_mode == "usb"

    @pytest.mark.asyncio
    async def test_auto_falls_back_to_ble(self):
        p = M03ASPrinter(target="auto", paper="53mm", mode="auto",
                         ble_address="AA:BB:CC:DD:EE:FF")
        mock_ble = MagicMock()
        mock_ble.is_connected = True
        mock_ble.connect = AsyncMock()
        mock_ble.enable_notify = AsyncMock()
        with patch("phomemo.printer.m03as.find_usb_port", return_value=None), \
             patch("phomemo.printer.m03as.BleTransport", return_value=mock_ble):
            await p.connect()
            assert p._active_mode == "ble"

    @pytest.mark.asyncio
    async def test_auto_no_usb_no_ble_raises(self):
        p = M03ASPrinter(target="auto", paper="53mm", mode="auto", ble_address="")
        with patch("phomemo.printer.m03as.find_usb_port", return_value=None):
            with pytest.raises(RuntimeError, match="蓝牙地址"):
                await p.connect()


class TestPrinterContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self):
        with patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = MagicMock()
            mock_transport.is_connected = True
            mock_transport.connect = MagicMock()
            mock_transport.disconnect = MagicMock()
            MockUsb.return_value = mock_transport

            async with M03ASPrinter(target="COM12", paper="53mm", mode="usb") as p:
                assert p.is_connected
            mock_transport.disconnect.assert_called_once()


class TestQueryStatus:
    @pytest.mark.asyncio
    async def test_query_status_usb_returns_empty(self):
        p = M03ASPrinter(target="COM12", paper="53mm", mode="usb")
        with patch("phomemo.printer.m03as.UsbTransport") as MockUsb:
            mock_transport = MagicMock()
            mock_transport.is_connected = True
            mock_transport.connect = MagicMock()
            MockUsb.return_value = mock_transport
            await p.connect()
            result = await p.query_status()
            assert result == {}
