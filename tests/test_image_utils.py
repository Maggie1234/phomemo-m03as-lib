"""
测试 image_utils.py：位图转换、文字渲染
"""
import pytest
from PIL import Image
from phomemo.image_utils import image_to_bitmap, text_to_image, bitmap_preview


class TestImageToBitmap:
    def _make_white(self, w=100, h=50):
        return Image.new("RGB", (w, h), (255, 255, 255))

    def _make_black(self, w=100, h=50):
        return Image.new("RGB", (w, h), (0, 0, 0))

    def test_output_types(self):
        bmp, wb, h = image_to_bitmap(self._make_white(), width_px=96)
        assert isinstance(bmp, bytes)
        assert isinstance(wb, int)
        assert isinstance(h, int)

    def test_width_bytes_correct(self):
        _, wb, _ = image_to_bitmap(self._make_white(), width_px=96)
        assert wb == 96 // 8  # = 12

    def test_bitmap_length_matches_dimensions(self):
        bmp, wb, h = image_to_bitmap(self._make_white(), width_px=96)
        assert len(bmp) == wb * h

    def test_width_aligned_down_to_8(self):
        # width_px=100 应被对齐到 96（最近的 8 倍数）
        _, wb, _ = image_to_bitmap(self._make_white(), width_px=100)
        assert wb == 96 // 8

    def test_white_image_mostly_zero(self):
        # 白图打印位图应几乎全 0（不打印）
        bmp, wb, h = image_to_bitmap(self._make_white(200, 50), width_px=200)
        ones = sum(bin(b).count("1") for b in bmp)
        total_bits = len(bmp) * 8
        assert ones / total_bits < 0.05  # 黑点占比 <5%

    def test_black_image_mostly_one(self):
        # 黑图打印位图应几乎全 1（全部打印）
        bmp, wb, h = image_to_bitmap(self._make_black(200, 50), width_px=200)
        ones = sum(bin(b).count("1") for b in bmp)
        total_bits = len(bmp) * 8
        assert ones / total_bits > 0.95  # 黑点占比 >95%

    def test_rgba_input(self):
        # RGBA 图也能处理（贴白底）
        img = Image.new("RGBA", (100, 50), (0, 0, 0, 128))
        bmp, wb, h = image_to_bitmap(img, width_px=96)
        assert len(bmp) == wb * h

    def test_grayscale_input(self):
        img = Image.new("L", (100, 50), 128)
        bmp, wb, h = image_to_bitmap(img, width_px=96)
        assert len(bmp) == wb * h

    def test_no_dither(self):
        bmp, wb, h = image_to_bitmap(
            self._make_white(), width_px=96, dither=False)
        assert len(bmp) == wb * h

    def test_aspect_ratio_preserved(self):
        # 原图 200×100，缩到宽 96px，高应约为 48px
        img = Image.new("RGB", (200, 100), (128, 128, 128))
        _, wb, h = image_to_bitmap(img, width_px=96)
        assert 40 <= h <= 56  # 允许整数取整误差


class TestTextToImage:
    def test_returns_pil_image(self):
        img = text_to_image("Hello", width_px=600)
        assert isinstance(img, Image.Image)

    def test_image_width_matches(self):
        img = text_to_image("Hello", width_px=600)
        assert img.width == 600

    def test_image_mode_is_grayscale(self):
        img = text_to_image("Hello", width_px=600)
        assert img.mode == "L"

    def test_multiline_taller_than_single(self):
        img1 = text_to_image("一行文字", width_px=600)
        img2 = text_to_image("一行文字\n第二行\n第三行", width_px=600)
        assert img2.height > img1.height

    def test_empty_line_handled(self):
        # 含空行不应报错
        img = text_to_image("第一行\n\n第三行", width_px=600)
        assert img.height > 0

    def test_long_line_wraps(self):
        # 超长单行应被自动折行，图高 > 单行
        long_text = "这是一段很长的文字" * 10
        img1 = text_to_image("短", width_px=600)
        img2 = text_to_image(long_text, width_px=600)
        assert img2.height > img1.height

    def test_chinese_text(self):
        img = text_to_image("印先森打印机测试", width_px=600)
        assert img.width == 600

    def test_custom_font_size(self):
        img_small = text_to_image("A", width_px=600, font_size=20)
        img_large = text_to_image("A", width_px=600, font_size=60)
        assert img_large.height > img_small.height


class TestBitmapPreview:
    def test_runs_without_error(self, capsys):
        # 生成一个简单位图并调用 preview，不应抛出异常
        bmp, wb, h = image_to_bitmap(
            Image.new("L", (96, 20), 128), width_px=96)
        bitmap_preview(bmp, wb, h, scale=2)
        captured = capsys.readouterr()
        assert "px" in captured.out
