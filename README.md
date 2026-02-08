# Grillo Device Provisioner

Factory tool for provisioning Grillo sensors. Flashes firmware, reads device MAC addresses, registers devices in cloud inventory, and prints identification labels.

## 🚀 Quick Start

**Windows (recommended):** Download and run `Grillo Device Provisioner.exe` — no installation required.

**From source:**
```bash
pip install -r requirements.txt
python main.py            # Launch GUI
python main.py --cli      # CLI mode
```

> If your PC doesn't recognize the ESP32, install the USB driver: [CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) or [CH340](http://www.wch-ic.com/downloads/CH341SER_ZIP.html)

## 🏗️ Provisioning Flow

```
Firmware CDN ─→ Download firmware ─→ Flash ESP32 via USB ─→ Read MAC address
(S3+CloudFront)                                                    │
                                                                   ▼
                                              Print DYMO label ←─ Register device
                                              (ID, type, QR)      (cloud-backend API)
```

1. **Select device type** (Pulse or One) and firmware version
2. **Download firmware** from `firmware.cloud.grillo.io`
3. **Flash firmware** via esptool over USB serial
4. **Read MAC address** from flashed device (becomes device ID)
5. **Register device** via cloud-backend inventory API
6. **Print label** with device ID, type, firmware version, QR code

## 🖥️ GUI

<img src="device_provisioner.png" width="400">

Features:
- Device type selection and firmware version picker
- One-click flash, register, and label print
- Serial monitor with simplified device status view
- Status badges: Active, Connection, TimeSync, ADXL, ADS, Messaging, Data
- Hardware reset button (DTR/RTS)
- Auto-detects new devices on port refresh

## ⌨️ CLI Usage

```bash
python main.py --cli [OPTIONS] [port]
```

| Flag | Description |
|------|-------------|
| `-p` | Print label (requires labelle + DYMO printer) |
| `-r` | Register with cloud-backend API |
| `-c [FILE]` | Save to CSV (default: devices.csv) |
| `-f [DIR]` | Flash firmware from directory (default: firmware/) |
| `-d TYPE` | Device type: `pulse` or `one` (default: pulse) |

## ⚡ Firmware Flashing

| Device | Chip | Flash Size | Firmware File |
|--------|------|------------|---------------|
| Pulse | ESP32-S3 | 16MB | grillo-pulse-firmware.bin |
| One | ESP32 | 8MB | grillo-one-firmware.bin |

```bash
python main.py --cli -f                    # Flash Pulse (default)
python main.py --cli -f -d one             # Flash One
```

Supports both merged binaries (recommended) and individual partition files. See `--help` for details.

## 🛠️ Development

```bash
pip install -r requirements.txt
python main.py                # Run from source

# Build Windows executable
pyinstaller main.spec
```

### Platform Notes

| Platform | Serial Access | Label Printing |
|----------|--------------|----------------|
| Windows | Install CP210x/CH340 driver | DYMO + Zadig (WinUSB) |
| Linux | `sudo usermod -a -G dialout $USER` | `pip install labelle` |
| macOS | Built-in drivers | `pip install labelle` |

## 🔗 Related Repos

| Repo | Relationship |
|------|-------------|
| [grillo-firmware-pulse](../grillo-firmware-pulse) | Firmware binary flashed onto Pulse devices |
| [grillo-firmware-one](../grillo-firmware-one) | Firmware binary flashed onto One devices |
| [grillo-cloud-backend](../grillo-cloud-backend) | Inventory API for device registration |
