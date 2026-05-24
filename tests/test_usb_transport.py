"""
测试 UsbTransport：连接、断开、数据发送（mock serial）
"""
import pytest
from unittest.mock import MagicMock, patch, call
from phomemo.transport.usb import UsbTransport, find_usb_port


class TestUsbTransport:
    def _mock_serial(self):
        s = MagicMock()
        s.is_open = True
        return s

    def test_connect_opens_serial(self):
        t = UsbTransport("COM12")
        with patch("phomemo.transport.usb.serial") as mock_serial_mod:
            mock_serial_mod.Serial.return_value = self._mock_serial()
            t.connect()
            mock_serial_mod.Serial.assert_called_once()
            assert t.is_connected

    def test_connect_failure_raises_runtime(self):
        t = UsbTransport("COM99")
        with patch("phomemo.transport.usb.serial") as mock_serial_mod:
            mock_serial_mod.Serial.side_effect = Exception("port not found")
            with pytest.raises(RuntimeError, match="USB 连接失败"):
                t.connect()
            # serial 抛异常后 _serial 应仍为 None
            assert not t.is_connected

    def test_disconnect_closes_serial(self):
        t = UsbTransport("COM12")
        mock_ser = self._mock_serial()
        t._serial = mock_ser
        t.disconnect()
        mock_ser.close.assert_called_once()
        assert t._serial is None

    def test_disconnect_when_not_open(self):
        t = UsbTransport("COM12")
        mock_ser = self._mock_serial()
        mock_ser.is_open = False
        t._serial = mock_ser
        t.disconnect()  # 不应报错
        mock_ser.close.assert_not_called()

    def test_write_sends_data(self):
        t = UsbTransport("COM12")
        mock_ser = self._mock_serial()
        t._serial = mock_ser
        t.write(b"\x1F\x11\x0B")
        mock_ser.write.assert_called_once_with(b"\x1F\x11\x0B")

    def test_write_when_disconnected_raises(self):
        t = UsbTransport("COM12")
        with pytest.raises(RuntimeError):
            t.write(b"\x00")

    def test_send_bitmap_chunks(self):
        t = UsbTransport("COM12")
        mock_ser = self._mock_serial()
        t._serial = mock_ser
        data = bytes(range(256)) * 3   # 768 字节，应被分成多块
        t.send_bitmap(data)
        assert mock_ser.write.call_count >= 3

    def test_send_bitmap_progress_callback(self):
        t = UsbTransport("COM12")
        mock_ser = self._mock_serial()
        t._serial = mock_ser
        calls = []
        data = bytes(512)
        t.send_bitmap(data, on_progress=lambda s, tot: calls.append((s, tot)))
        assert len(calls) > 0
        assert calls[-1][0] == 512  # 最后一次 sent == total

    def test_write_delay_calls_sleep(self):
        import time
        t = UsbTransport("COM12")
        mock_ser = self._mock_serial()
        t._serial = mock_ser
        with patch("phomemo.transport.usb.time") as mock_time:
            t.write_delay(b"\x00", 0.05)
            mock_time.sleep.assert_called_once_with(0.05)


class TestFindUsbPort:
    def test_returns_none_when_no_ports(self):
        with patch("phomemo.transport.usb.lp") as mock_lp:
            mock_lp.comports.return_value = []
            result = find_usb_port()
            assert result is None

    def test_finds_by_vid_pid(self):
        mock_port = MagicMock()
        mock_port.vid = 0x0416
        mock_port.pid = 0x5011
        mock_port.device = "COM5"
        mock_port.description = "USB Device"
        mock_port.manufacturer = ""
        with patch("phomemo.transport.usb.lp") as mock_lp:
            mock_lp.comports.return_value = [mock_port]
            result = find_usb_port()
            assert result == "COM5"

    def test_finds_by_description_keyword(self):
        mock_port = MagicMock()
        mock_port.vid = None
        mock_port.pid = None
        mock_port.device = "COM8"
        mock_port.description = "Phomemo USB Serial"
        mock_port.manufacturer = ""
        with patch("phomemo.transport.usb.lp") as mock_lp:
            mock_lp.comports.return_value = [mock_port]
            result = find_usb_port()
            assert result == "COM8"

    def test_falls_back_to_generic_usb_serial(self):
        mock_port = MagicMock()
        mock_port.vid = None
        mock_port.pid = None
        mock_port.device = "COM10"
        mock_port.description = "USB Serial Device"
        mock_port.manufacturer = ""
        with patch("phomemo.transport.usb.lp") as mock_lp:
            mock_lp.comports.return_value = [mock_port]
            result = find_usb_port()
            assert result == "COM10"
