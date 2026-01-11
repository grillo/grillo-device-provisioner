#!/usr/bin/env python3
"""
Grillo Device Reader - NiceGUI

Cross-platform web-based GUI for provisioning ESP32 devices.
"""

import asyncio
from nicegui import ui, run

# Import functions from the main script
from esp32_device_reader import (
    find_esp32_port,
    get_mac_address,
    register_device,
    print_label,
    append_to_csv,
    flash_firmware,
    DEFAULT_CSV_FILE,
    DEFAULT_FIRMWARE_DIR,
    DEVICE_CONFIGS,
    DEFAULT_DEVICE_TYPE,
)

# Optional pyserial for port listing and serial monitor
try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False


class DeviceReaderApp:
    def __init__(self):
        # State
        self.ports: list[str] = []
        self.selected_port: str = ""
        self.device_type: str = DEFAULT_DEVICE_TYPE
        self.device_id: str = "—"
        self.status: str = "Ready"
        self.status_color: str = "grey"
        self.processing: bool = False

        # Options
        self.opt_print: bool = False
        self.opt_register: bool = False
        self.opt_csv: bool = False
        self.csv_file: str = DEFAULT_CSV_FILE
        self.opt_flash: bool = False
        self.firmware_dir: str = DEFAULT_FIRMWARE_DIR

        # Serial monitor
        self.serial_running: bool = False
        self.serial_task: asyncio.Task | None = None

        # UI references
        self.port_select: ui.select = None
        self.log_area: ui.log = None
        self.start_button: ui.button = None
        self.monitor_button: ui.button = None
        self.device_id_label: ui.label = None
        self.status_label: ui.label = None

    def refresh_ports(self):
        """Refresh available COM ports."""
        self.ports = []
        if HAS_PYSERIAL:
            for port in serial.tools.list_ports.comports():
                self.ports.append(port.device)

        if self.port_select:
            self.port_select.options = self.ports
            self.port_select.update()

        self.set_status(f"Found {len(self.ports)} port(s)", "grey")

    def set_status(self, message: str, color: str = "grey"):
        """Update status message."""
        self.status = message
        self.status_color = color
        if self.status_label:
            self.status_label.text = message
            self.status_label.style(f"color: {color}")

    def log(self, message: str):
        """Add message to log."""
        if self.log_area:
            self.log_area.push(message)

    async def copy_device_id(self):
        """Copy device ID to clipboard."""
        if self.device_id and self.device_id != "—":
            await ui.run_javascript(f'navigator.clipboard.writeText("{self.device_id}")')
            self.set_status("Copied to clipboard!", "green")

    async def toggle_monitor(self):
        """Toggle serial monitor."""
        if self.serial_running:
            await self.stop_monitor()
        else:
            await self.start_monitor()

    async def start_monitor(self):
        """Start serial monitoring."""
        if not HAS_PYSERIAL:
            self.log("[ERROR] pyserial not installed")
            return

        if not self.selected_port:
            self.log("[ERROR] No port selected")
            return

        self.serial_running = True
        if self.monitor_button:
            self.monitor_button.text = "Stop Monitor"

        self.serial_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitor(self):
        """Stop serial monitoring."""
        self.serial_running = False
        if self.monitor_button:
            self.monitor_button.text = "Start Monitor"

        if self.serial_task:
            self.serial_task.cancel()
            try:
                await self.serial_task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        """Background serial monitoring."""
        try:
            ser = await run.io_bound(
                lambda: serial.Serial(self.selected_port, 115200, timeout=0.1)
            )
            self.log(f"[Monitor] Connected to {self.selected_port}")

            while self.serial_running:
                if ser.in_waiting:
                    try:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        if line:
                            self.log(f"[DEVICE] {line}")
                    except Exception:
                        pass
                await asyncio.sleep(0.01)

            ser.close()
            self.log("[Monitor] Disconnected")

        except serial.SerialException as e:
            self.log(f"[Monitor] Error: {e}")
            await self.stop_monitor()

    async def process_device(self):
        """Main device processing."""
        if self.processing:
            return

        self.processing = True
        if self.start_button:
            self.start_button.disable()

        self.device_id = "—"
        if self.device_id_label:
            self.device_id_label.text = "—"

        # Stop monitor if running
        if self.serial_running:
            await self.stop_monitor()
            await asyncio.sleep(0.5)

        try:
            port = self.selected_port

            # Auto-detect if no port selected
            if not port:
                self.set_status("Auto-detecting device...", "blue")
                port = await run.io_bound(find_esp32_port)
                if not port:
                    self.set_status("No device found!", "red")
                    return
                self.selected_port = port
                if self.port_select:
                    self.port_select.value = port

            # Read Device ID
            self.set_status(f"Reading Device ID from {port}...", "blue")
            self.log(f"[INFO] Reading Device ID from {port}...")

            device_id = await run.io_bound(lambda: get_mac_address(port))

            if not device_id:
                self.set_status("Failed to read Device ID!", "red")
                self.log("[ERROR] Failed to read Device ID")
                return

            self.device_id = device_id
            if self.device_id_label:
                self.device_id_label.text = device_id
            self.log(f"[INFO] Device ID: {device_id}")

            # Optional: Register with API
            if self.opt_register:
                self.set_status("Registering with API...", "blue")
                self.log("[INFO] Registering with API...")
                await run.io_bound(lambda: register_device(device_id))

            # Optional: Save to CSV
            if self.opt_csv:
                self.set_status("Saving to CSV...", "blue")
                self.log(f"[INFO] Saving to {self.csv_file}...")
                await run.io_bound(lambda: append_to_csv(device_id, self.csv_file))

            # Optional: Print label
            if self.opt_print:
                self.set_status("Printing label...", "blue")
                self.log("[INFO] Printing label...")
                await run.io_bound(lambda: print_label(device_id))

            # Optional: Flash firmware
            if self.opt_flash:
                device_name = DEVICE_CONFIGS[self.device_type]["name"]
                self.set_status(f"Flashing {device_name}...", "blue")
                self.log(f"[INFO] Flashing {device_name} firmware from {self.firmware_dir}...")

                success, msg = await run.io_bound(
                    lambda: flash_firmware(port, self.firmware_dir, self.device_type)
                )

                if success:
                    self.log("[INFO] Firmware flashed successfully!")
                    self.set_status("Flashed! Monitoring output...", "green")
                    await asyncio.sleep(2)
                    await self.start_monitor()
                else:
                    self.log(f"[ERROR] Flashing failed: {msg}")
                    self.set_status("Flash failed!", "red")
                    return

            if not self.opt_flash:
                self.set_status(f"Done! Device ID: {device_id}", "green")

        except Exception as e:
            self.set_status(f"Error: {e}", "red")
            self.log(f"[ERROR] {e}")

        finally:
            self.processing = False
            if self.start_button:
                self.start_button.enable()

    def build_ui(self):
        """Build the NiceGUI interface."""
        ui.dark_mode(False)

        with ui.card().classes("w-96 mx-auto mt-4"):
            ui.label("Grillo Device Reader").classes("text-2xl font-bold mb-4")

            # Port selection
            with ui.row().classes("w-full items-center"):
                self.port_select = ui.select(
                    options=self.ports,
                    label="Device Port",
                    on_change=lambda e: setattr(self, 'selected_port', e.value or "")
                ).classes("flex-grow")
                ui.button("Refresh", on_click=self.refresh_ports).props("flat")

            # Device type selection
            ui.select(
                options=list(DEVICE_CONFIGS.keys()),
                value=self.device_type,
                label="Device Type",
                on_change=lambda e: setattr(self, 'device_type', e.value)
            ).classes("w-full")

            # Options
            with ui.card().classes("w-full mt-2"):
                ui.label("Options").classes("font-bold")

                ui.checkbox("Print label", on_change=lambda e: setattr(self, 'opt_print', e.value))
                ui.checkbox("Register with API", on_change=lambda e: setattr(self, 'opt_register', e.value))

                with ui.row().classes("items-center"):
                    ui.checkbox("Save to CSV:", on_change=lambda e: setattr(self, 'opt_csv', e.value))
                    ui.input(value=self.csv_file, on_change=lambda e: setattr(self, 'csv_file', e.value)).classes("w-32")

                with ui.row().classes("items-center"):
                    ui.checkbox("Flash firmware:", on_change=lambda e: setattr(self, 'opt_flash', e.value))
                    ui.input(value=self.firmware_dir, on_change=lambda e: setattr(self, 'firmware_dir', e.value)).classes("w-32")

            # Start button
            self.start_button = ui.button("Start", on_click=self.process_device).classes("w-full mt-4").props("color=primary size=lg")

            # Result
            with ui.card().classes("w-full mt-4"):
                ui.label("Result").classes("font-bold")
                with ui.row().classes("items-center"):
                    ui.label("Device ID:")
                    self.device_id_label = ui.label("—").classes("font-mono text-lg font-bold")
                    ui.button("Copy", on_click=self.copy_device_id).props("flat size=sm")

            # Serial Log
            with ui.card().classes("w-full mt-4"):
                ui.label("Serial Log").classes("font-bold")
                self.log_area = ui.log(max_lines=100).classes("w-full h-48 font-mono text-xs")

                with ui.row():
                    self.monitor_button = ui.button("Start Monitor", on_click=self.toggle_monitor).props("flat")
                    ui.button("Clear", on_click=lambda: self.log_area.clear()).props("flat")

            # Status
            with ui.row().classes("mt-4 items-center"):
                ui.label("Status:")
                self.status_label = ui.label("Ready").style("color: grey")

        # Initial port refresh
        self.refresh_ports()


def main():
    import sys
    native = "--native" in sys.argv or "-n" in sys.argv

    app = DeviceReaderApp()
    app.build_ui()
    ui.run(
        title="Grillo Device Reader",
        port=8080,
        reload=False,
        native=native,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
