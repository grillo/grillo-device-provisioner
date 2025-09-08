# ESP32-S3 Label Printer & Device Registration

This script automatically reads the MAC address from a connected ESP32-S3 device, registers it with the backend system, and prints a label with the MAC address (without colons) plus a Code128 barcode.

## Usage

### Automatic Detection (Recommended)
Simply run the script and it will find your ESP32 device:
```bash
./esp32_label_printer.sh
```

### Manual Port Specification
If you know the specific port:
```bash
./esp32_label_printer.sh /dev/ttyUSB0
```

## How it Works

1. **Device Detection**: Scans `/dev/ttyUSB*` and `/dev/ttyACM*` for ESP32 devices
2. **MAC Address Reading**: Uses `esptool read-mac` to get the device's MAC address  
3. **Device Registration**: Sends HTTP POST request to add device to inventory:
   ```json
   {"devices": [{"device_id": "AABBCCDDEEFF"}]}
   ```
4. **Label Generation**: Creates a label with:
   - MAC address as text (no colons, uppercase)  
   - QR code of the same MAC address
   - Centered alignment with 80% font scaling

## Requirements

- `esptool` - for reading MAC addresses from ESP32 devices
- `labelle` - for printing labels
- `curl` - for device registration (usually pre-installed)
- ESP32-S3 device connected via USB

## Configuration

The script uses these default settings (modify at top of script if needed):
- API Server: `http://localhost:8080`

## Example Output

For a device with MAC address `AA:BB:CC:DD:EE:FF`, the script will:
- Add device ID `AABBCCDDEEFF` to the inventory
- Print the text: `AABBCCDDEEFF`  
- Print a Code128 barcode encoding: `AABBCCDDEEFF`

## Troubleshooting

- **Device not found**: Make sure the ESP32 is connected and USB drivers are installed
- **Permission denied**: You may need to add your user to the `dialout` group:
  ```bash
  sudo usermod -a -G dialout $USER
  ```
  Then log out and back in.
- **Registration failed**: If `curl` is not available, the script will skip registration and continue with label printing
- **Label not printing**: Check that your label printer is connected and configured with `labelle`

## Notes

- Device registration is optional - if `curl` is not available, the script will skip registration and just print the label
- The MAC address (without colons) is used as the device ID for inventory registration
- Once added to inventory, devices can later be claimed and configured through the web interface