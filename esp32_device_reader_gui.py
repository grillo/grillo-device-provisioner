#!/usr/bin/env python3
"""
Grillo Device Provisioner - GUI

Cross-platform GUI for provisioning ESP32 devices.
Uses CustomTkinter for modern appearance.
"""

import threading
import sys
import time
import re
import os
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Try CustomTkinter first, fall back to standard tkinter
try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    HAS_CUSTOMTKINTER = True
except ImportError:
    HAS_CUSTOMTKINTER = False
    import tkinter as tk
    from tkinter import ttk

from tkinter import filedialog

# Import functions from the main script
from esp32_device_reader import (
    find_esp32_port,
    get_mac_address,
    register_device,
    print_label,
    append_to_csv,
    flash_firmware,
    DEFAULT_CSV_FILE,
    DEVICE_CONFIGS,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_BAUD_RATE,
    BAUD_RATES,
)

# Optional pyserial for port listing and serial monitor
try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False

# S3 firmware bucket (public HTTPS access)
S3_FIRMWARE_URL = "https://s3.amazonaws.com/grillo.firmware"


class ESP32ReaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Grillo Device Provisioner")
        self.root.minsize(580, 650)

        # Variables
        self.port_var = ctk.StringVar() if HAS_CUSTOMTKINTER else tk.StringVar()
        self.device_type_var = ctk.StringVar(value=DEFAULT_DEVICE_TYPE) if HAS_CUSTOMTKINTER else tk.StringVar(value=DEFAULT_DEVICE_TYPE)
        self.baud_rate_var = ctk.StringVar(value=str(DEFAULT_BAUD_RATE)) if HAS_CUSTOMTKINTER else tk.StringVar(value=str(DEFAULT_BAUD_RATE))
        self.print_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.register_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.csv_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.csv_file_var = ctk.StringVar(value=DEFAULT_CSV_FILE) if HAS_CUSTOMTKINTER else tk.StringVar(value=DEFAULT_CSV_FILE)
        self.flash_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        default_firmware_dir = str(Path.home() / "Desktop")
        self.firmware_dir_var = ctk.StringVar(value=default_firmware_dir) if HAS_CUSTOMTKINTER else tk.StringVar(value=default_firmware_dir)
        self.device_id_var = ctk.StringVar(value="—") if HAS_CUSTOMTKINTER else tk.StringVar(value="—")
        self.status_var = ctk.StringVar(value="Ready") if HAS_CUSTOMTKINTER else tk.StringVar(value="Ready")
        self.firmware_version_var = ctk.StringVar(value="") if HAS_CUSTOMTKINTER else tk.StringVar(value="")
        self.firmware_versions = []  # Available S3 versions

        # Serial monitoring
        self.serial_thread = None
        self.serial_running = False

        # Track known ports for auto-selection
        self.known_ports = set()

        self.create_widgets()
        self.on_device_type_change()  # Set initial firmware folder and refresh

    def create_widgets(self):
        if HAS_CUSTOMTKINTER:
            self._create_ctk_widgets()
        else:
            self._create_ttk_widgets()

    def _create_ctk_widgets(self):
        """Create modern CustomTkinter widgets."""
        # Store window dimensions
        self.main_width = 550
        self.panel_width = 800
        self.log_panel_visible = False

        # Container for horizontal layout
        container = ctk.CTkFrame(self.root)
        container.pack(fill="both", expand=True)

        # Left panel (main controls)
        left_panel = ctk.CTkFrame(container)
        left_panel.pack(side="left", fill="both", expand=True, padx=15, pady=15)

        # Title
        ctk.CTkLabel(left_panel, text="Grillo Device Provisioner", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(0, 15))

        # Port selection frame
        port_frame = ctk.CTkFrame(left_panel)
        port_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(port_frame, text="Device Port:", width=100, anchor="w").pack(side="left", padx=5)
        self.port_combo = ctk.CTkComboBox(port_frame, variable=self.port_var, width=200)
        self.port_combo.pack(side="left", padx=5)
        ctk.CTkButton(port_frame, text="Refresh", command=self.refresh_ports, width=80).pack(side="left", padx=5)

        # Driver hint (shown when no ports found)
        self.driver_hint = ctk.CTkLabel(left_panel, text="Connect a Grillo device. If not detected, install USB driver: CP210x or CH340",
                                        font=ctk.CTkFont(size=11), text_color="gray")
        self.driver_hint.pack(anchor="w", padx=15)
        self.driver_hint.pack_forget()  # Hidden by default

        # Options frame
        options = ctk.CTkFrame(left_panel)
        options.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(options, text="Options", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        ctk.CTkCheckBox(options, text="Print label", variable=self.print_var).pack(anchor="w", padx=20, pady=2)
        ctk.CTkCheckBox(options, text="Register with API", variable=self.register_var).pack(anchor="w", padx=20, pady=2)

        # CSV option
        csv_frame = ctk.CTkFrame(options, fg_color="transparent")
        csv_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkCheckBox(csv_frame, text="Append to CSV:", variable=self.csv_var, width=120).pack(side="left")
        ctk.CTkEntry(csv_frame, textvariable=self.csv_file_var, width=150).pack(side="left", padx=5)
        ctk.CTkButton(csv_frame, text="...", command=self.browse_csv, width=30).pack(side="left")

        # Flash option
        flash_frame = ctk.CTkFrame(options, fg_color="transparent")
        flash_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkCheckBox(flash_frame, text="Flash firmware:", variable=self.flash_var, width=120).pack(side="left")
        ctk.CTkEntry(flash_frame, textvariable=self.firmware_dir_var, width=150).pack(side="left", padx=5)
        ctk.CTkButton(flash_frame, text="...", command=self.browse_firmware, width=30).pack(side="left")

        # Firmware selector: device type + version dropdown + refresh
        firmware_frame = ctk.CTkFrame(options, fg_color="transparent")
        firmware_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(firmware_frame, text="Firmware:", width=120, anchor="w").pack(side="left")
        self.pulse_btn = ctk.CTkButton(firmware_frame, text="Pulse", width=80, command=lambda: self.select_device_type("pulse"))
        self.pulse_btn.pack(side="left", padx=2)
        self.one_btn = ctk.CTkButton(firmware_frame, text="One", width=80, command=lambda: self.select_device_type("one"))
        self.one_btn.pack(side="left", padx=2)
        self.version_combo = ctk.CTkComboBox(firmware_frame, variable=self.firmware_version_var, width=100, state="readonly")
        self.version_combo.pack(side="left", padx=(10, 2))
        ctk.CTkButton(firmware_frame, text="Refresh", command=self.refresh_firmware_versions, width=60).pack(side="left", padx=2)

        # Download button
        download_frame = ctk.CTkFrame(options, fg_color="transparent")
        download_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkLabel(download_frame, text="", width=120).pack(side="left")  # Spacer to align with above
        ctk.CTkButton(download_frame, text="Download from S3", command=self.download_firmware, width=150).pack(side="left", padx=2)

        # Baud rate
        baud_frame = ctk.CTkFrame(options, fg_color="transparent")
        baud_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkLabel(baud_frame, text="Flash baud rate:", width=120, anchor="w").pack(side="left")
        ctk.CTkComboBox(baud_frame, variable=self.baud_rate_var,
                        values=[str(b) for b in BAUD_RATES], width=100, state="readonly").pack(side="left", padx=5)

        # Start button
        self.start_btn = ctk.CTkButton(left_panel, text="Start", command=self.process_device,
                                        height=40, font=ctk.CTkFont(size=14, weight="bold"))
        self.start_btn.pack(fill="x", padx=10, pady=15)

        # Device ID frame
        id_container = ctk.CTkFrame(left_panel)
        id_container.pack(fill="x", padx=10, pady=5)

        id_frame = ctk.CTkFrame(id_container, fg_color="transparent")
        id_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(id_frame, text="Device ID:", width=80, anchor="w").pack(side="left")
        self.id_label = ctk.CTkLabel(id_frame, textvariable=self.device_id_var,
                                      font=ctk.CTkFont(family="Consolas", size=14, weight="bold"))
        self.id_label.pack(side="left", padx=10)
        ctk.CTkButton(id_frame, text="Copy", command=self.copy_device_id, width=60).pack(side="right")

        # Device status frame (simplified log)
        status_log_frame = ctk.CTkFrame(left_panel)
        status_log_frame.pack(fill="x", padx=10, pady=5)

        # Status badges row
        badge_frame = ctk.CTkFrame(status_log_frame, fg_color="transparent")
        badge_frame.pack(fill="x", padx=10, pady=5)

        self.badges = {}
        badge_names = ["FW", "Conn", "TimeSync", "ADXL", "ADS", "Messaging", "Data", "OTA"]
        for name in badge_names:
            badge = ctk.CTkLabel(badge_frame, text=name, fg_color="gray40", corner_radius=5,
                                 padx=8, pady=2, font=ctk.CTkFont(size=11))
            badge.pack(side="left", padx=2)
            self.badges[name] = badge

        self.status_text = ctk.CTkTextbox(status_log_frame, font=ctk.CTkFont(family="Consolas", size=11), height=80)
        self.status_text.pack(fill="x", padx=10, pady=5)

        # Monitor buttons row
        monitor_btn_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        monitor_btn_frame.pack(fill="x", padx=10, pady=5)
        self.monitor_btn = ctk.CTkButton(monitor_btn_frame, text="Start Monitor", command=self.toggle_monitor, width=100)
        self.monitor_btn.pack(side="left", padx=5)
        ctk.CTkButton(monitor_btn_frame, text="Reset", command=self.reset_device, width=60).pack(side="left", padx=5)

        # Serial Log button (separate row for visibility)
        log_btn_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        log_btn_frame.pack(fill="x", padx=10, pady=5)
        self.log_panel_btn = ctk.CTkButton(log_btn_frame, text="Serial Log >>", command=self.toggle_log_panel, width=150)
        self.log_panel_btn.pack(side="left", padx=5)

        # Status bar
        status_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        status_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(status_frame, text="Status:").pack(side="left", padx=5)
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var, text_color="gray")
        self.status_label.pack(side="left", padx=5)

        # Right panel (Serial Log) - hidden by default
        self.right_panel = ctk.CTkFrame(container, width=self.panel_width)
        self.right_panel.pack_propagate(False)  # Enforce fixed width
        # Don't pack yet - hidden by default

        # Serial log header
        log_header = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(log_header, text="Serial Log", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(log_header, text="X", command=self.toggle_log_panel, width=30, height=30).pack(side="right")
        ctk.CTkButton(log_header, text="Copy", command=self.copy_serial_log, width=50).pack(side="right", padx=5)
        ctk.CTkButton(log_header, text="Clear", command=self.clear_log, width=50).pack(side="right", padx=5)

        # Serial log textbox
        self.log_text = ctk.CTkTextbox(self.right_panel, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Legacy compatibility
        self.log_visible = False
        self.log_frame = self.right_panel
        self.log_content = self.right_panel

    def toggle_log_panel(self):
        """Toggle the serial log side panel (CustomTkinter only)."""
        if not hasattr(self, 'log_panel_visible'):
            return  # Not applicable for ttk
        if self.log_panel_visible:
            # Hide panel
            self.right_panel.pack_forget()
            self.log_panel_btn.configure(text="Serial Log >>")
            self.log_panel_visible = False
        else:
            # Show panel to the right
            self.right_panel.pack(side="right", fill="both", padx=(0, 15), pady=15)
            self.log_panel_btn.configure(text="<< Close")
            self.log_panel_visible = True

    def _create_ttk_widgets(self):
        """Fallback to standard ttk widgets."""
        from tkinter import scrolledtext

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        # Port selection
        ttk.Label(main, text="Device Port:").grid(row=0, column=0, sticky="w")
        port_frame = ttk.Frame(main)
        port_frame.grid(row=0, column=1, sticky="ew", pady=5)
        self.port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, width=20)
        self.port_combo.pack(side="left", padx=(0, 5))
        ttk.Button(port_frame, text="Refresh", command=self.refresh_ports).pack(side="left")

        # Driver hint (shown when no ports found)
        self.driver_hint = ttk.Label(main, text="Connect a Grillo device. If not detected, install USB driver: CP210x or CH340",
                                     foreground="gray")
        self.driver_hint.grid(row=0, column=1, sticky="w", pady=(25, 0))
        self.driver_hint.grid_remove()  # Hidden by default

        # Options
        options = ttk.LabelFrame(main, text="Options", padding=10)
        options.grid(row=1, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Checkbutton(options, text="Print label", variable=self.print_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="Register with API", variable=self.register_var).grid(row=1, column=0, sticky="w")

        csv_frame = ttk.Frame(options)
        csv_frame.grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(csv_frame, text="Append to CSV:", variable=self.csv_var).pack(side="left")
        ttk.Entry(csv_frame, textvariable=self.csv_file_var, width=15).pack(side="left", padx=5)
        ttk.Button(csv_frame, text="...", command=self.browse_csv, width=3).pack(side="left")

        flash_frame = ttk.Frame(options)
        flash_frame.grid(row=3, column=0, sticky="w", pady=5)
        ttk.Checkbutton(flash_frame, text="Flash firmware:", variable=self.flash_var).pack(side="left")
        ttk.Entry(flash_frame, textvariable=self.firmware_dir_var, width=15).pack(side="left", padx=5)
        ttk.Button(flash_frame, text="...", command=self.browse_firmware, width=3).pack(side="left")

        # Firmware selector: device type + version dropdown + refresh
        firmware_frame = ttk.Frame(options)
        firmware_frame.grid(row=4, column=0, sticky="w", pady=5)
        ttk.Label(firmware_frame, text="Firmware:").pack(side="left")
        self.pulse_btn = ttk.Button(firmware_frame, text="Pulse", width=8, command=lambda: self.select_device_type("pulse"))
        self.pulse_btn.pack(side="left", padx=2)
        self.one_btn = ttk.Button(firmware_frame, text="One", width=8, command=lambda: self.select_device_type("one"))
        self.one_btn.pack(side="left", padx=2)
        self.version_combo = ttk.Combobox(firmware_frame, textvariable=self.firmware_version_var, width=10, state="readonly")
        self.version_combo.pack(side="left", padx=(10, 2))
        ttk.Button(firmware_frame, text="Refresh", command=self.refresh_firmware_versions, width=7).pack(side="left", padx=2)

        # Download button
        download_frame = ttk.Frame(options)
        download_frame.grid(row=5, column=0, sticky="w", pady=2)
        ttk.Label(download_frame, text="", width=10).pack(side="left")  # Spacer
        ttk.Button(download_frame, text="Download from S3", command=self.download_firmware, width=18).pack(side="left", padx=2)

        baud_frame = ttk.Frame(options)
        baud_frame.grid(row=6, column=0, sticky="w")
        ttk.Label(baud_frame, text="Flash baud rate:").pack(side="left")
        ttk.Combobox(baud_frame, textvariable=self.baud_rate_var,
                     values=[str(b) for b in BAUD_RATES], width=10, state="readonly").pack(side="left", padx=5)

        # Start button
        self.start_btn = ttk.Button(main, text="Start", command=self.process_device)
        self.start_btn.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")

        # Device ID
        id_container = ttk.LabelFrame(main, text="Device ID", padding=10)
        id_container.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)

        id_frame = ttk.Frame(id_container)
        id_frame.pack(fill="x")
        self.id_label = ttk.Label(id_frame, textvariable=self.device_id_var, font=("Consolas", 12, "bold"))
        self.id_label.pack(side="left", padx=5)
        ttk.Button(id_frame, text="Copy", command=self.copy_device_id).pack(side="right")

        # Device status (simplified log)
        status_log_frame = ttk.LabelFrame(main, text="Device Status", padding=10)
        status_log_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)

        # Monitor buttons at top
        monitor_btn_frame = ttk.Frame(status_log_frame)
        monitor_btn_frame.pack(fill="x", pady=5)
        self.monitor_btn = ttk.Button(monitor_btn_frame, text="Start Monitor", command=self.toggle_monitor)
        self.monitor_btn.pack(side="left")
        ttk.Button(monitor_btn_frame, text="Clear", command=self.clear_log).pack(side="left", padx=5)
        ttk.Button(monitor_btn_frame, text="Reset", command=self.reset_device).pack(side="left", padx=5)

        # Status badges row
        badge_frame = ttk.Frame(status_log_frame)
        badge_frame.pack(fill="x", pady=5)

        self.badges = {}
        badge_names = ["FW", "Conn", "TimeSync", "ADXL", "ADS", "Messaging", "Data", "OTA"]
        for name in badge_names:
            badge = ttk.Label(badge_frame, text=name, background="gray", foreground="white",
                              padding=(5, 2))
            badge.pack(side="left", padx=2)
            self.badges[name] = badge

        self.status_text = scrolledtext.ScrolledText(status_log_frame, height=4, font=("Consolas", 9))
        self.status_text.pack(fill="x", expand=False)

        # Log (collapsible, hidden by default)
        self.log_frame = ttk.LabelFrame(main, text="Serial Log", padding=10)
        self.log_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=5)
        main.rowconfigure(5, weight=1)
        main.columnconfigure(1, weight=1)
        self.log_visible = False

        log_header = ttk.Frame(self.log_frame)
        log_header.pack(fill="x")
        self.collapse_btn = ttk.Button(log_header, text="Show", command=self.toggle_log_visibility, width=6)
        self.collapse_btn.pack(side="right")
        ttk.Button(log_header, text="Copy", command=self.copy_serial_log, width=6).pack(side="right", padx=5)

        self.log_content = ttk.Frame(self.log_frame)
        # Don't pack log_content - hidden by default

        self.log_text = scrolledtext.ScrolledText(self.log_content, height=8, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

        # Status
        status_frame = ttk.Frame(main)
        status_frame.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Label(status_frame, text="Status:").pack(side="left")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side="left", padx=5)

    def refresh_ports(self):
        """Refresh the list of available COM ports. Auto-selects new ports."""
        ports = []
        if HAS_PYSERIAL:
            for port in serial.tools.list_ports.comports():
                ports.append(port.device)
        else:
            if sys.platform == "win32":
                ports = [f"COM{i}" for i in range(1, 21)]

        if HAS_CUSTOMTKINTER:
            self.port_combo.configure(values=ports)
        else:
            self.port_combo["values"] = ports

        # Detect new ports and auto-select
        current_ports = set(ports)
        new_ports = current_ports - self.known_ports
        self.known_ports = current_ports

        # Show/hide driver hint based on ports found
        if hasattr(self, 'driver_hint'):
            if not ports:
                if HAS_CUSTOMTKINTER:
                    self.driver_hint.pack(anchor="w", padx=5, after=self.port_combo.master)
                else:
                    self.driver_hint.grid()
            else:
                if HAS_CUSTOMTKINTER:
                    self.driver_hint.pack_forget()
                else:
                    self.driver_hint.grid_remove()

        if new_ports:
            # Auto-select the new port
            new_port = sorted(new_ports)[0]
            self.port_var.set(new_port)
            self.set_status(f"New device: {new_port}", "green")
        elif ports and not self.port_var.get():
            self.port_var.set(ports[0])
            self.set_status(f"Found {len(ports)} port(s)")
        elif not ports:
            self.set_status("No ports found")
        else:
            self.set_status(f"Found {len(ports)} port(s)")

    def browse_csv(self):
        """Open file dialog to select CSV file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=self.csv_file_var.get()
        )
        if filename:
            self.csv_file_var.set(filename)

    def browse_firmware(self):
        """Open directory dialog to select firmware folder."""
        dirname = filedialog.askdirectory(
            initialdir=self.firmware_dir_var.get(),
            title="Select Firmware Directory"
        )
        if dirname:
            self.firmware_dir_var.set(dirname)

    def select_device_type(self, device_type):
        """Select device type and update button appearance."""
        self.device_type_var.set(device_type)
        self.update_device_type_buttons()
        self.on_device_type_change()

    def update_device_type_buttons(self):
        """Update device type button appearance based on selection."""
        if not hasattr(self, 'pulse_btn'):
            return  # Buttons not created yet
        device_type = self.device_type_var.get()
        if HAS_CUSTOMTKINTER:
            # Selected button is highlighted, other is dimmed
            if device_type == "pulse":
                self.pulse_btn.configure(fg_color=("green", "green"))
                self.one_btn.configure(fg_color=("gray50", "gray30"))
            else:
                self.pulse_btn.configure(fg_color=("gray50", "gray30"))
                self.one_btn.configure(fg_color=("green", "green"))
        # ttk doesn't support easy color changes, button text indicates selection

    def on_device_type_change(self):
        """Handle device type change - refresh ports and versions."""
        self.update_device_type_buttons()
        self.refresh_ports()
        self.refresh_firmware_versions()

    def refresh_firmware_versions(self):
        """Fetch available firmware versions from S3 via HTTPS."""
        device_type = self.device_type_var.get()
        prefix = f"grillo-{device_type}/"
        list_url = f"{S3_FIRMWARE_URL}/?prefix={prefix}&delimiter=/"

        def fetch_versions():
            try:
                with urllib.request.urlopen(list_url, timeout=10) as response:
                    xml_data = response.read().decode('utf-8')

                # Parse S3 XML response
                root = ET.fromstring(xml_data)
                ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}

                versions = []
                for content in root.findall('.//s3:Contents', ns):
                    key = content.find('s3:Key', ns).text
                    # Look for version folders like "grillo-pulse/1.0.0/"
                    if key.startswith(prefix) and key.endswith('/'):
                        parts = key[len(prefix):].rstrip('/').split('/')
                        if len(parts) == 1 and parts[0] and re.match(r'^\d+\.\d+\.\d+$', parts[0]):
                            versions.append(parts[0])

                versions = list(set(versions))  # Remove duplicates
                versions.sort(key=lambda v: [int(x) if x.isdigit() else x for x in v.split(".")], reverse=True)
                self.firmware_versions = versions

                def update_ui():
                    if HAS_CUSTOMTKINTER:
                        self.version_combo.configure(values=versions)
                    else:
                        self.version_combo["values"] = versions
                    if versions:
                        # Default to 1.0.0 if available, otherwise first in list
                        default_version = "1.0.0" if "1.0.0" in versions else versions[0]
                        self.firmware_version_var.set(default_version)
                        self.set_status(f"Found {len(versions)} firmware versions", "green")
                    else:
                        self.set_status("No firmware versions found", "gray")

                self.root.after(0, update_ui)

            except urllib.error.URLError as e:
                self.root.after(0, lambda: self.set_status(f"Network error: {e.reason}", "red"))
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Error: {e}", "red"))

        self.set_status("Fetching firmware versions...", "blue")
        threading.Thread(target=fetch_versions, daemon=True).start()

    def download_firmware(self):
        """Download selected firmware version from S3 via HTTPS."""
        version = self.firmware_version_var.get()
        if not version:
            self.set_status("Select a firmware version first", "red")
            return

        device_type = self.device_type_var.get()
        base_dir = self.firmware_dir_var.get()

        # Create device-type and version subfolder (e.g., firmware/pulse/1.0.0/)
        local_dir = Path(base_dir) / device_type / version
        local_dir.mkdir(parents=True, exist_ok=True)

        # Files to download: firmware (versioned) + bootloader & partition (device-level)
        firmware_name = f"grillo-{device_type}-firmware.bin"
        downloads = [
            (f"{S3_FIRMWARE_URL}/grillo-{device_type}/{version}/{firmware_name}", firmware_name),
            (f"{S3_FIRMWARE_URL}/grillo-{device_type}/bootloader.bin", "bootloader.bin"),
            (f"{S3_FIRMWARE_URL}/grillo-{device_type}/partition-table.bin", "partition-table.bin"),
        ]

        def do_download():
            try:
                success_count = 0
                for url, filename in downloads:
                    local_path = Path(local_dir) / filename
                    try:
                        urllib.request.urlretrieve(url, str(local_path))
                        success_count += 1
                        self.root.after(0, lambda f=filename: self.log_message(f"[INFO] Downloaded {f}"))
                    except urllib.error.HTTPError as e:
                        self.root.after(0, lambda f=filename, e=e: self.log_message(f"[WARN] Failed to download {f}: HTTP {e.code}"))
                    except urllib.error.URLError as e:
                        self.root.after(0, lambda f=filename, e=e: self.log_message(f"[WARN] Failed to download {f}: {e.reason}"))

                if success_count == len(downloads):
                    # Don't update firmware_dir_var - keep base path so user can download different versions
                    self.root.after(0, lambda: self.set_status(f"Downloaded {device_type} v{version} to {local_dir}", "green"))
                else:
                    self.root.after(0, lambda: self.set_status(f"Downloaded {success_count}/{len(downloads)} files", "orange"))

            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Error: {e}", "red"))

        self.set_status(f"Downloading {device_type} v{version}...", "blue")
        threading.Thread(target=do_download, daemon=True).start()

    def set_status(self, message, color="gray"):
        """Update status message."""
        self.status_var.set(message)
        if HAS_CUSTOMTKINTER:
            self.status_label.configure(text_color=color)
        else:
            self.status_label.configure(foreground=color)
        self.root.update_idletasks()

    def log_message(self, message):
        """Add message to log output."""
        if HAS_CUSTOMTKINTER:
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        else:
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")

    def clear_log(self):
        """Clear the log output and device status."""
        if HAS_CUSTOMTKINTER:
            self.log_text.delete("1.0", "end")
            self.status_text.delete("1.0", "end")
        else:
            self.log_text.delete("1.0", "end")
            self.status_text.delete("1.0", "end")
        self.reset_badges()

    def add_device_status(self, message):
        """Add a simplified status message to the device status display."""
        if HAS_CUSTOMTKINTER:
            self.status_text.insert("end", message + "\n")
            self.status_text.see("end")
        else:
            self.status_text.insert("end", message + "\n")
            self.status_text.see("end")

    def set_badge(self, name, active=True, text=None):
        """Set badge color (green if active, gray if inactive) and optionally text."""
        if not hasattr(self, 'badges') or name not in self.badges:
            return
        if HAS_CUSTOMTKINTER:
            color = "green" if active else "gray40"
            self.badges[name].configure(fg_color=color)
            if text:
                self.badges[name].configure(text=text)
        else:
            color = "green" if active else "gray"
            self.badges[name].configure(background=color)
            if text:
                self.badges[name].configure(text=text)

    def reset_badges(self):
        """Reset all badges to inactive."""
        if hasattr(self, 'badges'):
            for name in self.badges:
                self.set_badge(name, False)
            self.set_badge("FW", False, "FW")
            self.set_badge("Conn", False, "Conn")

    def parse_serial_line(self, line):
        """Parse serial line and return simplified status message if applicable."""
        # Firmware version detection (from boot message or SoH)
        # Patterns: "Grillo Pulse v1.0.0", "Grillo One v1.0.0", "fw=1.0.0", "version: 1.0.0"
        fw_match = re.search(r'(?:Grillo (?:Pulse|One) v|fw=|[Vv]ersion[:\s]+)(\d+\.\d+\.\d+)', line)
        if fw_match:
            version = fw_match.group(1)
            self.root.after(0, lambda v=version: self.set_badge("FW", True, v))
            return f"Firmware: v{version}"
        # Boot/reset
        if "rst:0x" in line or "boot:" in line and "ESP-IDF" in line:
            self.root.after(0, self.reset_badges)
            return "Device starting..."
        # WiFi connected
        if "wifi:connected with" in line:
            self.root.after(0, lambda: self.set_badge("Conn", True, "WiFi"))
            ssid = line.split("connected with ")[1].split(",")[0] if "connected with " in line else "?"
            return f"WiFi connected: {ssid}"
        # Ethernet connected
        if "Ethernet link up" in line or "ethernet attached" in line:
            self.root.after(0, lambda: self.set_badge("Conn", True, "Ethernet"))
            return "Ethernet connected"
        # Cellular connected
        if "cellular" in line.lower() and ("connected" in line.lower() or "attached" in line.lower()):
            self.root.after(0, lambda: self.set_badge("Conn", True, "Cellular"))
            return "Cellular connected"
        # Connection type from SoH (conn=wifi, conn=ethernet, conn=cellular)
        if "conn=" in line:
            match = re.search(r'conn=(\w+)', line)
            if match:
                conn_type = match.group(1).capitalize()
                self.root.after(0, lambda t=conn_type: self.set_badge("Conn", True, t))
        # Got IP
        if "sta ip:" in line or "WiFi got IP:" in line:
            ip = line.split("ip: ")[1].split(",")[0] if "ip: " in line else "?"
            return f"Got IP: {ip}"
        # Time sync
        if "Time synchronized:" in line or "[INITIAL SYNC]" in line:
            self.root.after(0, lambda: self.set_badge("TimeSync", True))
            return "Time synchronized"
        # ADXL355 init
        if "ADXL355 initialized" in line or "ADXL355 detected" in line:
            self.root.after(0, lambda: self.set_badge("ADXL", True))
            return "ADXL355 accelerometer detected"
        # ADS1262 init (Pulse)
        if "ADS1262 driver initialized" in line or "ADS1262 configuration completed" in line:
            self.root.after(0, lambda: self.set_badge("ADS", True))
            return "ADS1262 ADC initialized"
        # Calibration
        if "Calibration complete" in line or "calibration completed" in line or "DC bias calibration complete" in line:
            return "Sensor calibration complete"
        # Messaging init
        if "Messaging initialized" in line:
            self.root.after(0, lambda: self.set_badge("Messaging", True))
            return "Messaging initialized"
        # Device ID
        if "Device ID:" in line and "main:" in line:
            did = line.split("Device ID: ")[1].strip() if "Device ID: " in line else "?"
            return f"Device ID: {did}"
        # System ready
        if "initialized successfully" in line and ("Grillo One" in line or "Grillo Pulse" in line or "System ready" in line):
            return "System ready"
        # SOH sent
        if "SOH message sent" in line or ("SoH:" in line and "id=" in line):
            return "SoH message sent"
        # SOH received
        if "SOH response" in line:
            return "SoH response received"
        # Data messages
        if "[JSON]:" in line and ("geo=" in line or "ax=" in line):
            self.root.after(0, lambda: self.set_badge("Data", True))
            return "Sending data..."
        # OTA update
        if "OTA" in line and ("start" in line.lower() or "begin" in line.lower()):
            self.root.after(0, lambda: self.set_badge("OTA", True))
            return "OTA update starting..."
        if "OTA" in line and ("success" in line.lower() or "complete" in line.lower() or "done" in line.lower()):
            self.root.after(0, lambda: self.set_badge("OTA", True))
            return "OTA update complete"
        if "OTA" in line and ("fail" in line.lower() or "error" in line.lower()):
            return "OTA update failed"
        return None

    def copy_device_id(self):
        """Copy device ID to clipboard."""
        device_id = self.device_id_var.get()
        if device_id and device_id != "—":
            self.root.clipboard_clear()
            self.root.clipboard_append(device_id)
            self.set_status("Copied to clipboard!", "green")

    def copy_serial_log(self):
        """Copy serial log contents to clipboard."""
        if HAS_CUSTOMTKINTER:
            log_content = self.log_text.get("1.0", "end-1c")
        else:
            log_content = self.log_text.get("1.0", "end-1c")
        if log_content.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(log_content)
            self.set_status("Log copied to clipboard!", "green")
        else:
            self.set_status("Log is empty", "gray")

    def reset_device(self):
        """Reset the ESP32 device via DTR/RTS pins."""
        if not HAS_PYSERIAL:
            self.set_status("pyserial not installed", "red")
            return

        port = self.port_var.get()
        if not port:
            self.set_status("No port selected", "red")
            return

        # Stop monitor temporarily if running
        was_monitoring = self.serial_running
        if was_monitoring:
            self.stop_monitor()
            time.sleep(0.2)

        try:
            ser = serial.Serial(port, 115200)
            # Toggle DTR/RTS to reset ESP32
            ser.dtr = False
            ser.rts = True
            time.sleep(0.1)
            ser.rts = False
            ser.close()
            self.clear_log()
            self.set_status("Device reset", "green")
            self.add_device_status("Device reset triggered")
        except serial.SerialException as e:
            self.set_status(f"Reset failed: {e}", "red")

        # Restart monitor if it was running
        if was_monitoring:
            time.sleep(0.5)
            self.start_monitor()

    def toggle_log_visibility(self):
        """Toggle serial log visibility (ttk fallback only)."""
        if not hasattr(self, 'collapse_btn'):
            return  # Not applicable for CustomTkinter
        if self.log_visible:
            self.log_content.pack_forget()
            self.collapse_btn.configure(text="Show")
            self.log_visible = False
            self.root.update_idletasks()
            self.root.geometry(f"{self.root.winfo_width()}x{self.root.winfo_reqheight()}")
        else:
            self.log_content.pack(fill="both", expand=True)
            self.collapse_btn.configure(text="Hide")
            self.log_visible = True
            self.root.update_idletasks()
            self.root.geometry("")

    def toggle_monitor(self):
        """Toggle serial monitor on/off."""
        if self.serial_running:
            self.stop_monitor()
        else:
            self.start_monitor()

    def start_monitor(self):
        """Start serial monitor."""
        if not HAS_PYSERIAL:
            self.log_message("[ERROR] pyserial not installed")
            return

        port = self.port_var.get()
        if not port:
            self.log_message("[ERROR] No port selected")
            return

        self.serial_running = True
        if HAS_CUSTOMTKINTER:
            self.monitor_btn.configure(text="Stop Monitor")
        else:
            self.monitor_btn.configure(text="Stop Monitor")
        self.serial_thread = threading.Thread(target=self._monitor_thread, args=(port,), daemon=True)
        self.serial_thread.start()

    def stop_monitor(self):
        """Stop serial monitor."""
        self.serial_running = False
        if HAS_CUSTOMTKINTER:
            self.monitor_btn.configure(text="Start Monitor")
        else:
            self.monitor_btn.configure(text="Start Monitor")

    def _monitor_thread(self, port):
        """Background thread for serial monitoring."""
        try:
            ser = serial.Serial(port, 115200, timeout=0.1)
            self.root.after(0, lambda: self.log_message(f"[Monitor] Connected to {port}"))
            self.root.after(0, lambda: self.add_device_status("Monitor connected"))
            last_status = None

            while self.serial_running:
                if ser.in_waiting:
                    try:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        if line:
                            self.root.after(0, lambda l=line: self.log_message(f"[DEVICE] {l}"))
                            # Parse and show simplified status
                            status = self.parse_serial_line(line)
                            if status and status != last_status:
                                # Avoid repeating "Sending data..." endlessly
                                if status == "Sending data..." and last_status == "Sending data...":
                                    pass
                                else:
                                    self.root.after(0, lambda s=status: self.add_device_status(s))
                                    last_status = status
                    except Exception:
                        pass
                time.sleep(0.01)

            ser.close()
            self.root.after(0, lambda: self.log_message("[Monitor] Disconnected"))

        except serial.SerialException as e:
            self.root.after(0, lambda: self.log_message(f"[Monitor] Error: {e}"))
            self.root.after(0, self.stop_monitor)

    def process_device(self):
        """Process device (runs in background thread)."""
        if HAS_CUSTOMTKINTER:
            self.start_btn.configure(state="disabled")
        else:
            self.start_btn.configure(state="disabled")
        self.set_status("Processing...", "blue")
        self.device_id_var.set("—")

        # Stop monitor if running
        if self.serial_running:
            self.stop_monitor()
            time.sleep(0.5)

        thread = threading.Thread(target=self._process_device_thread, daemon=True)
        thread.start()

    def _process_device_thread(self):
        """Background thread for processing device."""
        try:
            port = self.port_var.get()

            if not port:
                self.root.after(0, lambda: self.set_status("Auto-detecting device...", "blue"))
                port = find_esp32_port()
                if not port:
                    self.root.after(0, lambda: self.set_status("No device found!", "red"))
                    return
                self.root.after(0, lambda: self.port_var.set(port))

            # Read Device ID
            self.root.after(0, lambda: self.set_status(f"Reading Device ID from {port}...", "blue"))
            self.root.after(0, lambda: self.log_message(f"[INFO] Reading Device ID from {port}..."))
            device_id = get_mac_address(port)

            if not device_id:
                self.root.after(0, lambda: self.set_status("Failed to read Device ID!", "red"))
                self.root.after(0, lambda: self.log_message("[ERROR] Failed to read Device ID"))
                return

            self.root.after(0, lambda: self.device_id_var.set(device_id))
            self.root.after(0, lambda: self.log_message(f"[INFO] Device ID: {device_id}"))

            # Optional actions
            if self.register_var.get():
                self.root.after(0, lambda: self.set_status("Registering with API...", "blue"))
                self.root.after(0, lambda: self.log_message("[INFO] Registering with API..."))
                register_device(device_id)

            if self.csv_var.get():
                self.root.after(0, lambda: self.set_status("Saving to CSV...", "blue"))
                self.root.after(0, lambda: self.log_message(f"[INFO] Saving to {self.csv_file_var.get()}..."))
                append_to_csv(device_id, self.csv_file_var.get())

            if self.print_var.get():
                self.root.after(0, lambda: self.set_status("Printing label...", "blue"))
                self.root.after(0, lambda: self.log_message("[INFO] Printing label..."))
                print_label(device_id)

            # Flash firmware if requested
            if self.flash_var.get():
                device_type = self.device_type_var.get()
                device_name = DEVICE_CONFIGS[device_type]["name"]
                baud_rate = int(self.baud_rate_var.get())
                version = self.firmware_version_var.get()

                # Construct firmware path: base_dir/device_type/version
                base_dir = self.firmware_dir_var.get()
                if version:
                    firmware_path = str(Path(base_dir) / device_type / version)
                else:
                    firmware_path = base_dir  # Fallback if no version selected

                self.root.after(0, lambda: self.set_status(f"Flashing {device_name}...", "blue"))
                self.root.after(0, lambda fp=firmware_path: self.log_message(f"[INFO] Flashing {device_name} @ {baud_rate} baud from {fp}..."))

                success, msg = flash_firmware(port, firmware_path, device_type, baud_rate)
                if success:
                    self.root.after(0, lambda: self.log_message("[INFO] Firmware flashed successfully!"))
                    self.root.after(0, lambda: self.set_status("Flashed! Monitoring output...", "green"))
                    time.sleep(2)
                    self.root.after(0, self.start_monitor)
                else:
                    self.root.after(0, lambda m=msg: self.log_message(f"[ERROR] Flashing failed: {m}"))
                    self.root.after(0, lambda: self.set_status("Flash failed!", "red"))
                    return

            if not self.flash_var.get():
                self.root.after(0, lambda: self.set_status(f"Done! Device ID: {device_id}", "green"))

        except Exception as e:
            self.root.after(0, lambda: self.set_status(f"Error: {e}", "red"))
            self.root.after(0, lambda: self.log_message(f"[ERROR] {e}"))
        finally:
            if HAS_CUSTOMTKINTER:
                self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            else:
                self.root.after(0, lambda: self.start_btn.configure(state="normal"))


def main():
    if HAS_CUSTOMTKINTER:
        root = ctk.CTk()
    else:
        root = tk.Tk()
        # Set DPI awareness on Windows
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

    app = ESP32ReaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
