# phomemo-m03as-lib

Python library for controlling **Phomemo M03AS** / **YinXianSen** 300 DPI thermal printers via USB or Bluetooth.

## Features

- USB serial connection (recommended, stable)
- Bluetooth BLE connection (optional)
- Auto-detect: tries USB first, falls back to BLE
- Print text (Chinese/English, auto word-wrap)
- Print images (Floyd-Steinberg dithering + gamma correction)
- Supports 15mm / 53mm / 80mm paper widths

## Install

```bash
# USB only (recommended for Home Assistant)
pip install phomemo-m03as-lib

# With Bluetooth support
pip install "phomemo-m03as-lib[ble]"
```

## Quick Start

```python
import asyncio
from phomemo import M03ASPrinter

async def main():
    # Auto-detect: USB first, fallback to BLE
    printer = M03ASPrinter(
        target="auto",
        paper="80mm",
        ble_address="9D:86:57:63:34:DD",  # fallback BLE address
    )
    async with printer:
        await printer.print_text("Hello, 印先森！")
        await printer.print_image("photo.jpg")

asyncio.run(main())
```

## Protocol

Uses M04 ESC/POS extended protocol (300 DPI), reverse-engineered from the [phomymo](https://github.com/transcriptionstream/phomymo) open-source project.
