# ESP32 Device ID Reader

Reads the MAC address from a connected ESP32 device. Optionally registers it with a backend API, appends to a CSV file, and/or prints a label.

## Usage

```bash
./esp32_deviceID_print_register.sh [OPTIONS] [device_port]
```

### Options

| Flag | Description |
|------|-------------|
| `-p, --print` | Print label with MAC address and QR code |
| `-r, --register` | Register device with API server |
| `-c, --csv [FILE]` | Append device ID to CSV file (default: `devices.csv`) |
| `-h, --help` | Show help message |

### Examples

```bash
# Just read and display MAC address
./esp32_deviceID_print_register.sh

# Read MAC and print label
./esp32_deviceID_print_register.sh -p

# Read MAC and register with API
./esp32_deviceID_print_register.sh -r

# Read MAC and append to default CSV (devices.csv)
./esp32_deviceID_print_register.sh -c

# Read MAC and append to custom CSV
./esp32_deviceID_print_register.sh -c mydevices.csv

# All options with specific port
./esp32_deviceID_print_register.sh -p -r -c /dev/ttyUSB0
```

## How it Works

1. **Device Detection**: Scans `/dev/ttyUSB*`, `/dev/ttyACM*`, and `/dev/tty.usbserial*` for ESP32 devices (or uses specified port)
2. **MAC Address Reading**: Uses `esptool read-mac` to get the device's MAC address
3. **Optional Actions** (based on flags):
   - `-r`: Sends HTTP POST to register device in inventory
   - `-c`: Appends device ID and timestamp to CSV file
   - `-p`: Prints label with MAC address text and QR code

## Requirements

- `esptool` - for reading MAC addresses from ESP32 devices
- `labelle` - for printing labels (only if using `-p`)
- `curl` - for device registration (only if using `-r`)
- ESP32-S3 device connected via USB

### Installing esptool

```bash
pip install esptool
```

## Configuration

Modify at top of script if needed:
- API Server: `http://localhost:8080`
- Default CSV file: `devices.csv`

## Troubleshooting

- **Device not found**: Make sure the ESP32 is connected and USB drivers are installed
- **Permission denied**: Add your user to the `dialout` group:
  ```bash
  sudo usermod -a -G dialout $USER
  ```
  Then log out and back in.
