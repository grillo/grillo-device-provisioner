#!/bin/bash

# ESP32-S3 Label Printer Script
# Manually triggered script to register device and print labels with MAC address and barcode

set -e  # Exit on any error

# Configuration
API_SERVER="http://localhost:8080"
CSV_FILE="devices.csv"
ESPTOOL="python3 -m esptool"

# Flags (disabled by default)
PRINT_LABEL=false
REGISTER_API=false
APPEND_CSV=false

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS] [device_port]"
    echo ""
    echo "Options:"
    echo "  -p, --print       Print label with MAC address and QR code"
    echo "  -r, --register    Register device with API server"
    echo "  -c, --csv [FILE]  Append device ID to CSV file (default: devices.csv)"
    echo "  -h, --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                          # Just read MAC address"
    echo "  $0 -p                       # Read MAC and print label"
    echo "  $0 -r -p                    # Read MAC, register, and print"
    echo "  $0 -c                       # Read MAC and append to devices.csv"
    echo "  $0 -c mydevices.csv         # Read MAC and append to mydevices.csv"
    echo "  $0 -p -r -c /dev/ttyUSB0    # All options with specific port"
    exit 0
}

# Function to log messages
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

# Function to find ESP32 device port
find_esp32_port() {
    log "Searching for ESP32 device..."
    
    # Look for common ESP32 USB devices (Linux and macOS)
    for port in /dev/ttyUSB* /dev/ttyACM* /dev/tty.usbserial*; do
        if [ -e "$port" ]; then
            log "Found potential device: $port"
            # Test if we can communicate with esptool
            if $ESPTOOL --port "$port" chip_id >/dev/null 2>&1; then
                log "Confirmed ESP32 device at: $port"
                echo "$port"
                return 0
            fi
        fi
    done
    
    log "No ESP32 device found. Make sure it's connected and drivers are installed."
    return 1
}

# Function to get MAC address from ESP32-S3
get_mac_address() {
    local device_port="$1"
    
    log "Reading MAC address from device at $device_port"
    
    # Use esptool to read MAC address
    local mac_output
    mac_output=$($ESPTOOL --port "$device_port" read_mac 2>&1)
    
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to read MAC address: $mac_output"
        return 1
    fi
    
    # Extract MAC address from esptool output
    # esptool typically outputs: "MAC: xx:xx:xx:xx:xx:xx"
    local mac_address
    mac_address=$(echo "$mac_output" | grep -i "MAC:" | head -1 | sed 's/.*MAC: *//i' | tr -d ' \t\r\n')
    
    if [ -z "$mac_address" ]; then
        log "ERROR: Could not extract MAC address from esptool output"
        log "esptool output was: $mac_output"
        return 1
    fi
    
    # Remove colons to get alphanumeric string
    local clean_mac
    clean_mac=$(echo "$mac_address" | tr -d ':' | tr '[:lower:]' '[:upper:]')
    
    log "Extracted MAC address: $mac_address -> $clean_mac"
    echo "$clean_mac"
}

# Function to register device in inventory
register_device() {
    local device_id="$1"
    
    log "Adding device to inventory: $device_id"
    
    # Check if curl is available
    if ! command -v curl &> /dev/null; then
        log "WARNING: curl not found. Skipping device registration."
        log "Install curl to enable device registration: sudo apt install curl"
        return 0
    fi
    
    # Send HTTP POST request to add device to inventory
    local json_payload="{\"devices\":[{\"device_id\":\"$device_id\"}]}"
    local response
    response=$(curl -s -X POST "$API_SERVER/internal/devices/inventory" \
        -H "Content-Type: application/json" \
        -d "$json_payload" 2>&1)
    
    if [ $? -eq 0 ]; then
        log "Device added to inventory: $response"
    else
        log "WARNING: Device inventory registration failed: $response"
        log "Continuing with label printing..."
    fi
}

# Function to print label
print_label() {
    local mac_address="$1"

    log "Printing label for MAC: $mac_address"

    # Print label with MAC address text and QR code using batch mode
    cat << EOF | labelle --batch --font-scale 40
LABELLE-LABEL-SPEC-VERSION:1
QR:$mac_address
TEXT:$mac_address
EOF

    if [ $? -eq 0 ]; then
        log "Label printed successfully!"
    else
        log "ERROR: Failed to print label"
        return 1
    fi
}

# Function to append device ID to CSV
append_to_csv() {
    local device_id="$1"
    local csv_file="$2"
    local full_path
    full_path=$(cd "$(dirname "$csv_file")" 2>/dev/null && pwd)/$(basename "$csv_file")

    # Create CSV with header if it doesn't exist
    if [ ! -f "$csv_file" ]; then
        echo "device_id,timestamp" > "$csv_file"
        log "Created new CSV file: $full_path"
    fi

    # Append device ID with timestamp
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$device_id,$timestamp" >> "$csv_file"

    log "Appended device $device_id to $full_path"
}

# Parse command line arguments (sets global DEVICE_PORT)
parse_args() {
    DEVICE_PORT=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--print)
                PRINT_LABEL=true
                shift
                ;;
            -r|--register)
                REGISTER_API=true
                shift
                ;;
            -c|--csv)
                APPEND_CSV=true
                shift
                # Check if next argument is a filename (not starting with -)
                if [[ $# -gt 0 && ! "$1" =~ ^- && ! "$1" =~ ^/dev/ ]]; then
                    CSV_FILE="$1"
                    shift
                fi
                ;;
            -h|--help)
                usage
                ;;
            -*)
                echo "Unknown option: $1"
                usage
                ;;
            *)
                # Assume it's the device port
                DEVICE_PORT="$1"
                shift
                ;;
        esac
    done
}

# Main function
main() {
    parse_args "$@"
    local device_port="$DEVICE_PORT"

    log "Starting ESP32 device processing..."

    # If no port specified, try to find one automatically
    if [ -z "$device_port" ]; then
        device_port=$(find_esp32_port)
        if [ $? -ne 0 ]; then
            usage
        fi
    fi

    log "Using device port: $device_port"

    # Wait a moment for device to be ready
    sleep 1

    # Get MAC address
    local mac_address
    mac_address=$(get_mac_address "$device_port")

    if [ $? -ne 0 ] || [ -z "$mac_address" ]; then
        log "ERROR: Failed to get MAC address"
        exit 1
    fi

    # Register device with API if requested
    if [ "$REGISTER_API" = true ]; then
        register_device "$mac_address"
    else
        log "Skipping API registration (use -r to enable)"
    fi

    # Append to CSV if requested
    if [ "$APPEND_CSV" = true ]; then
        append_to_csv "$mac_address" "$CSV_FILE"
    else
        log "Skipping CSV append (use -c to enable)"
    fi

    # Print label if requested
    if [ "$PRINT_LABEL" = true ]; then
        print_label "$mac_address"
    else
        log "Skipping label printing (use -p to enable)"
    fi

    log "ESP32 processing completed for MAC: $mac_address"
    echo "$mac_address"
}

# Run main function with all arguments
main "$@"