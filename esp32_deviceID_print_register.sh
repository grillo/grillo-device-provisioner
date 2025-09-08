#!/bin/bash

# ESP32-S3 Label Printer Script
# Manually triggered script to register device and print labels with MAC address and barcode

set -e  # Exit on any error

# Configuration
API_SERVER="http://localhost:8080"

# Function to log messages
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

# Function to find ESP32 device port
find_esp32_port() {
    log "Searching for ESP32 device..."
    
    # Look for common ESP32 USB devices
    for port in /dev/ttyUSB* /dev/ttyACM*; do
        if [ -e "$port" ]; then
            log "Found potential device: $port"
            # Test if we can communicate with esptool
            if esptool --port "$port" chip_id >/dev/null 2>&1; then
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
    mac_output=$(esptool --port "$device_port" read-mac 2>&1)
    
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

# Main function
main() {
    local device_port="$1"
    
    log "Starting ESP32 label printing..."
    
    # If no port specified, try to find one automatically
    if [ -z "$device_port" ]; then
        device_port=$(find_esp32_port)
        if [ $? -ne 0 ]; then
            echo "Usage: $0 [device_port]"
            echo "Example: $0 /dev/ttyUSB0"
            echo "Or just run: $0 (will auto-detect)"
            exit 1
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
    
    # Add device to inventory (use MAC as device_id)
    register_device "$mac_address"
    
    # Print label
    print_label "$mac_address"
    
    log "ESP32 processing completed for MAC: $mac_address"
}

# Run main function with all arguments
main "$@"