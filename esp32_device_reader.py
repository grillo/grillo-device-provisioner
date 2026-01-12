#!/usr/bin/env python3
"""
ESP32 Device ID Reader - Cross-platform tool for reading ESP32 MAC addresses.

Reads the MAC address from a connected ESP32 device. Optionally registers it
with a backend API, appends to a CSV file, and/or prints a label.

Works on Windows, Linux, and macOS.
"""

import argparse
import csv
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Optional dependencies
try:
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# Configuration
API_SERVER = "http://localhost:8080"
DEFAULT_CSV_FILE = "devices.csv"
DEFAULT_FIRMWARE_DIR = "firmware"

# Merged firmware binary (preferred for production)
MERGED_FIRMWARE = "merged_firmware.bin"

# Device type configurations
DEVICE_CONFIGS = {
    "pulse": {
        "name": "Grillo Pulse",
        "chip": "esp32s3",
        "flash_size": "16MB",
        "bootloader_offset": 0x0,      # ESP32-S3 bootloader at 0x0
        "app_offset": 0x20000,
        "firmware_file": "grillo-pulse-firmware.bin",
    },
    "one": {
        "name": "Grillo One",
        "chip": "esp32",
        "flash_size": "8MB",
        "bootloader_offset": 0x1000,   # ESP32 bootloader at 0x1000
        "app_offset": 0x20000,
        "firmware_file": "grillo-one-firmware.bin",
    },
}

DEFAULT_DEVICE_TYPE = "pulse"
DEFAULT_BAUD_RATE = 460800
BAUD_RATES = [115200, 230400, 460800, 921600]


def log(message: str) -> None:
    """Log a message with timestamp to stderr."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}", file=sys.stderr)


def get_esptool_command() -> list:
    """Get the esptool command as a list for subprocess."""
    return [sys.executable, "-m", "esptool"]


def find_esp32_port() -> str | None:
    """
    Find an ESP32 device port automatically.

    Returns the port name (e.g., 'COM3' on Windows, '/dev/ttyUSB0' on Linux)
    or None if no device is found.
    """
    log("Searching for ESP32 device...")

    candidate_ports = []

    if HAS_PYSERIAL:
        # Use pyserial for cross-platform port detection
        ports = serial.tools.list_ports.comports()
        for port in ports:
            # ESP32 common USB VID/PID combinations
            # CP210x: VID=10C4, PID=EA60
            # CH340: VID=1A86, PID=7523
            # FTDI: VID=0403, PID=6001
            # ESP32-S3 native USB: VID=303A, PID=1001
            esp32_vids = [0x10C4, 0x1A86, 0x0403, 0x303A]

            if port.vid in esp32_vids:
                log(f"Found potential ESP32 device: {port.device} ({port.description})")
                candidate_ports.insert(0, port.device)  # Prioritize known ESP32 devices
            elif port.vid is not None:
                # Other USB serial devices as fallback
                candidate_ports.append(port.device)
    else:
        # Fallback: platform-specific port patterns
        system = platform.system()
        if system == "Windows":
            # Try COM1 through COM20
            candidate_ports = [f"COM{i}" for i in range(1, 21)]
        elif system == "Darwin":  # macOS
            import glob
            candidate_ports = glob.glob("/dev/tty.usbserial*") + glob.glob("/dev/tty.usbmodem*")
        else:  # Linux
            import glob
            candidate_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")

    # Test each candidate port with esptool
    esptool_cmd = get_esptool_command()

    for port in candidate_ports:
        try:
            log(f"Testing port: {port}")
            result = subprocess.run(
                esptool_cmd + ["--port", port, "chip_id"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                log(f"Confirmed ESP32 device at: {port}")
                return port
        except subprocess.TimeoutExpired:
            log(f"Timeout testing port: {port}")
        except Exception as e:
            log(f"Error testing port {port}: {e}")

    log("No ESP32 device found. Make sure it's connected and drivers are installed.")
    return None


def get_mac_address(device_port: str) -> str | None:
    """
    Read the MAC address from an ESP32 device.

    Args:
        device_port: The serial port (e.g., 'COM3' or '/dev/ttyUSB0')

    Returns:
        The MAC address as an uppercase hex string without colons (e.g., 'AABBCCDDEEFF')
        or None if reading fails.
    """
    log(f"Reading MAC address from device at {device_port}")

    esptool_cmd = get_esptool_command()

    try:
        result = subprocess.run(
            esptool_cmd + ["--port", device_port, "read_mac"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            log(f"ERROR: Failed to read MAC address: {result.stderr}")
            return None

        output = result.stdout + result.stderr

        # Extract MAC address from esptool output
        # esptool outputs: "MAC: xx:xx:xx:xx:xx:xx"
        mac_match = re.search(r"MAC:\s*([0-9A-Fa-f:]+)", output)

        if not mac_match:
            log(f"ERROR: Could not extract MAC address from esptool output")
            log(f"esptool output was: {output}")
            return None

        mac_address = mac_match.group(1)

        # Remove colons and convert to uppercase
        clean_mac = mac_address.replace(":", "").upper()

        log(f"Extracted MAC address: {mac_address} -> {clean_mac}")
        return clean_mac

    except subprocess.TimeoutExpired:
        log("ERROR: Timeout reading MAC address")
        return None
    except Exception as e:
        log(f"ERROR: {e}")
        return None


def register_device(device_id: str, api_server: str = API_SERVER) -> bool:
    """
    Register a device with the backend API.

    Args:
        device_id: The device MAC address
        api_server: The API server URL

    Returns:
        True if registration succeeded, False otherwise.
    """
    log(f"Adding device to inventory: {device_id}")

    url = f"{api_server}/internal/devices/inventory"
    payload = {"devices": [{"device_id": device_id}]}

    if HAS_REQUESTS:
        try:
            response = requests.post(url, json=payload, timeout=10)
            log(f"Device added to inventory: {response.text}")
            return True
        except requests.RequestException as e:
            log(f"WARNING: Device inventory registration failed: {e}")
            return False
    else:
        # Fallback to curl if requests is not available
        try:
            import json
            json_payload = json.dumps(payload)

            result = subprocess.run(
                ["curl", "-s", "-X", "POST", url,
                 "-H", "Content-Type: application/json",
                 "-d", json_payload],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                log(f"Device added to inventory: {result.stdout}")
                return True
            else:
                log(f"WARNING: Device inventory registration failed: {result.stderr}")
                return False
        except FileNotFoundError:
            log("WARNING: Neither 'requests' library nor 'curl' found. Skipping device registration.")
            log("Install requests: pip install requests")
            return False
        except Exception as e:
            log(f"WARNING: Device inventory registration failed: {e}")
            return False


def print_label(mac_address: str, copies: int = 1, with_qr: bool = True) -> bool:
    """
    Print a label with the MAC address and optionally a QR code.

    Args:
        mac_address: The MAC address to print
        copies: Number of copies to print (default 1)
        with_qr: Include QR code on label (default True)

    Returns:
        True if printing succeeded, False otherwise.
    """
    qr_str = "with QR" if with_qr else "text only"
    log(f"Printing {copies}x label(s) ({qr_str}) for MAC: {mac_address}")

    if with_qr:
        label_spec = f"""LABELLE-LABEL-SPEC-VERSION:1
QR:{mac_address}
TEXT:{mac_address}
"""
    else:
        label_spec = f"""LABELLE-LABEL-SPEC-VERSION:1
TEXT:{mac_address}
"""

    try:
        success_count = 0
        for i in range(copies):
            result = subprocess.run(
                ["labelle", "--batch", "--font-scale", "40"],
                input=label_spec,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                success_count += 1
            else:
                log(f"ERROR: Failed to print label {i+1}: {result.stderr}")

        if success_count == copies:
            log(f"All {copies} label(s) printed successfully!")
            return True
        elif success_count > 0:
            log(f"WARNING: Only {success_count}/{copies} labels printed")
            return True
        else:
            log("ERROR: Failed to print any labels")
            return False
    except FileNotFoundError:
        log("ERROR: 'labelle' command not found. Install it to enable label printing.")
        return False
    except Exception as e:
        log(f"ERROR: Failed to print label: {e}")
        return False


def append_to_csv(device_id: str, csv_file: str = DEFAULT_CSV_FILE) -> bool:
    """
    Append a device ID to a CSV file if it doesn't already exist.

    Args:
        device_id: The device MAC address
        csv_file: Path to the CSV file

    Returns:
        True if append succeeded or device already exists, False on error.
    """
    csv_path = Path(csv_file).resolve()

    try:
        # Check if device already exists in CSV
        if csv_path.exists():
            with open(csv_path, "r", newline="") as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0] == device_id:
                        log(f"Device {device_id} already exists in {csv_path}")
                        return True

        # Create CSV with header if it doesn't exist
        file_exists = csv_path.exists()

        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)

            if not file_exists:
                writer.writerow(["device_id", "timestamp"])
                log(f"Created new CSV file: {csv_path}")

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([device_id, timestamp])

        log(f"Appended device {device_id} to {csv_path}")
        return True

    except Exception as e:
        log(f"ERROR: Failed to append to CSV: {e}")
        return False


def flash_firmware(device_port: str, firmware_dir: str = DEFAULT_FIRMWARE_DIR, device_type: str = DEFAULT_DEVICE_TYPE, baud_rate: int = DEFAULT_BAUD_RATE) -> tuple[bool, str]:
    """
    Flash firmware to an ESP32 device.

    Prefers merged_firmware.bin if available, otherwise uses individual files.

    Args:
        device_port: The serial port (e.g., 'COM3' or '/dev/ttyUSB0')
        firmware_dir: Directory containing the firmware files
        device_type: Device type ('pulse' or 'one')
        baud_rate: Flash baud rate (default: 921600)

    Returns:
        Tuple of (success: bool, message: str)
    """
    if device_type not in DEVICE_CONFIGS:
        return False, f"Unknown device type: {device_type}"

    config = DEVICE_CONFIGS[device_type]
    log(f"Flashing {config['name']} firmware from {firmware_dir} to device at {device_port} @ {baud_rate} baud")

    firmware_path = Path(firmware_dir).resolve()
    merged_path = firmware_path / MERGED_FIRMWARE

    # Build esptool command
    esptool_cmd = get_esptool_command()
    flash_cmd = esptool_cmd + [
        "--port", device_port,
        "--baud", str(baud_rate),
        "--chip", config["chip"],
        "write_flash",
    ]

    # Prefer merged binary (simpler, more reliable)
    if merged_path.exists():
        log(f"Using merged firmware: {merged_path}")
        flash_cmd.extend(["0x0", str(merged_path)])
    else:
        # Fall back to individual files
        log("Using individual firmware files...")
        individual_files = [
            ("bootloader.bin", config["bootloader_offset"]),
            ("partition-table.bin", 0x8000),
            (config["firmware_file"], config["app_offset"]),
        ]
        for filename, address in individual_files:
            file_path = firmware_path / filename
            if not file_path.exists():
                msg = f"Firmware file not found: {file_path}"
                log(f"ERROR: {msg}")
                return False, msg
            flash_cmd.extend([f"0x{address:x}", str(file_path)])

    log(f"Running: {' '.join(flash_cmd)}")

    try:
        result = subprocess.run(
            flash_cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout for flashing
        )

        if result.returncode != 0:
            # Extract useful error from output
            error_msg = result.stderr.strip() or result.stdout.strip()
            log(f"ERROR: Flashing failed: {error_msg}")
            return False, error_msg

        log("Firmware flashed successfully!")
        return True, "Firmware flashed successfully"

    except subprocess.TimeoutExpired:
        msg = "Timeout while flashing firmware"
        log(f"ERROR: {msg}")
        return False, msg
    except Exception as e:
        msg = str(e)
        log(f"ERROR: Failed to flash firmware: {msg}")
        return False, msg


def monitor_serial(device_port: str, baud_rate: int = 115200, duration: int = 10) -> None:
    """
    Monitor serial output from the device.

    Args:
        device_port: The serial port
        baud_rate: Serial baud rate (default: 115200)
        duration: How long to monitor in seconds (default: 10)
    """
    if not HAS_PYSERIAL:
        log("WARNING: pyserial not installed, cannot monitor serial output")
        log("Install with: pip install pyserial")
        return

    import serial

    try:
        # Wait for device to reboot after flashing
        time.sleep(2)

        ser = serial.Serial(device_port, baud_rate, timeout=1)
        log(f"Monitoring {device_port} at {baud_rate} baud for {duration}s...")

        start_time = time.time()
        while (time.time() - start_time) < duration:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        print(f"[DEVICE] {line}")
                except Exception:
                    pass

        ser.close()
        log("Serial monitoring ended")

    except serial.SerialException as e:
        log(f"WARNING: Could not open serial port: {e}")
    except KeyboardInterrupt:
        log("Serial monitoring stopped by user")
    except Exception as e:
        log(f"WARNING: Serial monitoring error: {e}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ESP32 Device ID Reader - Read MAC address and optionally register/print/log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Just read MAC address
  %(prog)s -p                       # Read MAC and print label
  %(prog)s -r -p                    # Read MAC, register, and print
  %(prog)s -c                       # Read MAC and append to devices.csv
  %(prog)s -c mydevices.csv         # Read MAC and append to mydevices.csv
  %(prog)s -p -r -c COM3            # All options with specific port (Windows)
  %(prog)s -p -r -c /dev/ttyUSB0    # All options with specific port (Linux)
"""
    )

    parser.add_argument(
        "-p", "--print",
        action="store_true",
        dest="print_label",
        help="Print label with MAC address and QR code"
    )
    parser.add_argument(
        "-r", "--register",
        action="store_true",
        help="Register device with API server"
    )
    parser.add_argument(
        "-c", "--csv",
        nargs="?",
        const=DEFAULT_CSV_FILE,
        metavar="FILE",
        help=f"Append device ID to CSV file (default: {DEFAULT_CSV_FILE})"
    )
    parser.add_argument(
        "-f", "--flash",
        nargs="?",
        const=DEFAULT_FIRMWARE_DIR,
        metavar="DIR",
        help=f"Flash firmware from directory (default: {DEFAULT_FIRMWARE_DIR})"
    )
    parser.add_argument(
        "-d", "--device-type",
        choices=list(DEVICE_CONFIGS.keys()),
        default=DEFAULT_DEVICE_TYPE,
        help=f"Device type: {', '.join(DEVICE_CONFIGS.keys())} (default: {DEFAULT_DEVICE_TYPE})"
    )
    parser.add_argument(
        "--api-server",
        default=API_SERVER,
        help=f"API server URL (default: {API_SERVER})"
    )
    parser.add_argument(
        "port",
        nargs="?",
        help="Device port (e.g., COM3 on Windows, /dev/ttyUSB0 on Linux). Auto-detected if not specified."
    )

    args = parser.parse_args()

    log("Starting ESP32 device processing...")

    # Find or use specified port
    device_port = args.port
    if not device_port:
        device_port = find_esp32_port()
        if not device_port:
            parser.print_help()
            return 1

    log(f"Using device port: {device_port}")

    # Wait a moment for device to be ready
    time.sleep(1)

    # Get MAC address
    mac_address = get_mac_address(device_port)

    if not mac_address:
        log("ERROR: Failed to get MAC address")
        return 1

    # Register device with API if requested
    if args.register:
        register_device(mac_address, args.api_server)
    else:
        log("Skipping API registration (use -r to enable)")

    # Append to CSV if requested
    if args.csv:
        append_to_csv(mac_address, args.csv)
    else:
        log("Skipping CSV append (use -c to enable)")

    # Print label if requested
    if args.print_label:
        print_label(mac_address)
    else:
        log("Skipping label printing (use -p to enable)")

    # Flash firmware if requested
    if args.flash:
        log(f"Device type: {DEVICE_CONFIGS[args.device_type]['name']}")
        success, msg = flash_firmware(device_port, args.flash, args.device_type)
        if not success:
            log(f"ERROR: Flashing failed - {msg}")
            return 1
        # Show serial output after flashing
        log("Monitoring serial output (Ctrl+C to stop)...")
        monitor_serial(device_port)
    else:
        log("Skipping firmware flash (use -f to enable)")

    log(f"ESP32 processing completed for MAC: {mac_address}")
    print(mac_address)

    return 0


if __name__ == "__main__":
    sys.exit(main())
