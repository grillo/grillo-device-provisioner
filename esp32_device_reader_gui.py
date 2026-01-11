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
    DEFAULT_FIRMWARE_DIR,
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


class ESP32ReaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Grillo Device Provisioner")
        self.root.minsize(520, 780)

        # Variables
        self.port_var = ctk.StringVar() if HAS_CUSTOMTKINTER else tk.StringVar()
        self.device_type_var = ctk.StringVar(value=DEFAULT_DEVICE_TYPE) if HAS_CUSTOMTKINTER else tk.StringVar(value=DEFAULT_DEVICE_TYPE)
        self.baud_rate_var = ctk.StringVar(value=str(DEFAULT_BAUD_RATE)) if HAS_CUSTOMTKINTER else tk.StringVar(value=str(DEFAULT_BAUD_RATE))
        self.print_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.register_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.csv_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.csv_file_var = ctk.StringVar(value=DEFAULT_CSV_FILE) if HAS_CUSTOMTKINTER else tk.StringVar(value=DEFAULT_CSV_FILE)
        self.flash_var = ctk.BooleanVar() if HAS_CUSTOMTKINTER else tk.BooleanVar()
        self.firmware_dir_var = ctk.StringVar(value=DEFAULT_FIRMWARE_DIR) if HAS_CUSTOMTKINTER else tk.StringVar(value=DEFAULT_FIRMWARE_DIR)
        self.device_id_var = ctk.StringVar(value="—") if HAS_CUSTOMTKINTER else tk.StringVar(value="—")
        self.status_var = ctk.StringVar(value="Ready") if HAS_CUSTOMTKINTER else tk.StringVar(value="Ready")

        # Serial monitoring
        self.serial_thread = None
        self.serial_running = False

        # Track known ports for auto-selection
        self.known_ports = set()

        self.create_widgets()
        self.refresh_ports()

    def create_widgets(self):
        if HAS_CUSTOMTKINTER:
            self._create_ctk_widgets()
        else:
            self._create_ttk_widgets()

    def _create_ctk_widgets(self):
        """Create modern CustomTkinter widgets."""
        # Main frame
        main = ctk.CTkFrame(self.root)
        main.pack(fill="both", expand=True, padx=15, pady=15)

        # Title
        ctk.CTkLabel(main, text="Grillo Device Provisioner", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(0, 15))

        # Port selection frame
        port_frame = ctk.CTkFrame(main)
        port_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(port_frame, text="Device Port:", width=100, anchor="w").pack(side="left", padx=5)
        self.port_combo = ctk.CTkComboBox(port_frame, variable=self.port_var, width=200)
        self.port_combo.pack(side="left", padx=5)
        ctk.CTkButton(port_frame, text="Refresh", command=self.refresh_ports, width=80).pack(side="left", padx=5)

        # Device type frame
        type_frame = ctk.CTkFrame(main)
        type_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(type_frame, text="Device Type:", width=100, anchor="w").pack(side="left", padx=5)
        self.type_combo = ctk.CTkComboBox(type_frame, variable=self.device_type_var,
                                          values=list(DEVICE_CONFIGS.keys()), width=200, state="readonly",
                                          command=lambda _: self.refresh_ports())
        self.type_combo.pack(side="left", padx=5)

        # Options frame
        options = ctk.CTkFrame(main)
        options.pack(fill="x", pady=10)

        ctk.CTkLabel(options, text="Options", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        ctk.CTkCheckBox(options, text="Print label", variable=self.print_var).pack(anchor="w", padx=20, pady=2)
        ctk.CTkCheckBox(options, text="Register with API", variable=self.register_var).pack(anchor="w", padx=20, pady=2)

        # CSV option
        csv_frame = ctk.CTkFrame(options, fg_color="transparent")
        csv_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkCheckBox(csv_frame, text="Save to CSV:", variable=self.csv_var, width=120).pack(side="left")
        ctk.CTkEntry(csv_frame, textvariable=self.csv_file_var, width=150).pack(side="left", padx=5)
        ctk.CTkButton(csv_frame, text="...", command=self.browse_csv, width=30).pack(side="left")

        # Flash option
        flash_frame = ctk.CTkFrame(options, fg_color="transparent")
        flash_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkCheckBox(flash_frame, text="Flash firmware:", variable=self.flash_var, width=120).pack(side="left")
        ctk.CTkEntry(flash_frame, textvariable=self.firmware_dir_var, width=150).pack(side="left", padx=5)
        ctk.CTkButton(flash_frame, text="...", command=self.browse_firmware, width=30).pack(side="left")

        # Baud rate
        baud_frame = ctk.CTkFrame(options, fg_color="transparent")
        baud_frame.pack(fill="x", padx=20, pady=2)
        ctk.CTkLabel(baud_frame, text="Flash baud rate:", width=120, anchor="w").pack(side="left")
        ctk.CTkComboBox(baud_frame, variable=self.baud_rate_var,
                        values=[str(b) for b in BAUD_RATES], width=100, state="readonly").pack(side="left", padx=5)

        # Start button
        self.start_btn = ctk.CTkButton(main, text="Start", command=self.process_device,
                                        height=40, font=ctk.CTkFont(size=14, weight="bold"))
        self.start_btn.pack(fill="x", pady=15)

        # Device ID frame
        id_container = ctk.CTkFrame(main)
        id_container.pack(fill="x", pady=5)

        id_frame = ctk.CTkFrame(id_container, fg_color="transparent")
        id_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(id_frame, text="Device ID:", width=80, anchor="w").pack(side="left")
        self.id_label = ctk.CTkLabel(id_frame, textvariable=self.device_id_var,
                                      font=ctk.CTkFont(family="Consolas", size=14, weight="bold"))
        self.id_label.pack(side="left", padx=10)
        ctk.CTkButton(id_frame, text="Copy", command=self.copy_device_id, width=60).pack(side="right")

        # Device status frame (simplified log)
        status_log_frame = ctk.CTkFrame(main)
        status_log_frame.pack(fill="x", pady=5)

        # Monitor buttons at top
        monitor_btn_frame = ctk.CTkFrame(status_log_frame, fg_color="transparent")
        monitor_btn_frame.pack(fill="x", padx=10, pady=5)
        self.monitor_btn = ctk.CTkButton(monitor_btn_frame, text="Start Monitor", command=self.toggle_monitor, width=100)
        self.monitor_btn.pack(side="left", padx=5)
        ctk.CTkButton(monitor_btn_frame, text="Clear", command=self.clear_log, width=60).pack(side="left", padx=5)
        ctk.CTkButton(monitor_btn_frame, text="Reset", command=self.reset_device, width=60).pack(side="left", padx=5)

        ctk.CTkLabel(status_log_frame, text="Device Status", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        # Status badges row
        badge_frame = ctk.CTkFrame(status_log_frame, fg_color="transparent")
        badge_frame.pack(fill="x", padx=10, pady=5)

        self.badges = {}
        badge_names = ["Active", "Conn", "TimeSync", "ADXL", "ADS", "Messaging", "Data"]
        for name in badge_names:
            badge = ctk.CTkLabel(badge_frame, text=name, fg_color="gray40", corner_radius=5,
                                 padx=8, pady=2, font=ctk.CTkFont(size=11))
            badge.pack(side="left", padx=2)
            self.badges[name] = badge

        self.status_text = ctk.CTkTextbox(status_log_frame, font=ctk.CTkFont(family="Consolas", size=11), height=80)
        self.status_text.pack(fill="x", padx=10, pady=5)

        # Log frame (collapsible)
        self.log_frame = ctk.CTkFrame(main)
        self.log_frame.pack(fill="both", expand=True, pady=5)
        self.log_visible = True

        log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(log_header, text="Serial Log", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.collapse_btn = ctk.CTkButton(log_header, text="Hide", command=self.toggle_log_visibility, width=50)
        self.collapse_btn.pack(side="right")

        self.log_content = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.log_content.pack(fill="both", expand=True)

        self.log_text = ctk.CTkTextbox(self.log_content, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        # Status bar
        status_frame = ctk.CTkFrame(main, fg_color="transparent")
        status_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(status_frame, text="Status:").pack(side="left")
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var, text_color="gray")
        self.status_label.pack(side="left", padx=5)

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

        # Device type
        ttk.Label(main, text="Device Type:").grid(row=1, column=0, sticky="w")
        self.type_combo = ttk.Combobox(main, textvariable=self.device_type_var,
                                        values=list(DEVICE_CONFIGS.keys()), state="readonly")
        self.type_combo.grid(row=1, column=1, sticky="w", pady=5)
        self.type_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh_ports())

        # Options
        options = ttk.LabelFrame(main, text="Options", padding=10)
        options.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Checkbutton(options, text="Print label", variable=self.print_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="Register with API", variable=self.register_var).grid(row=1, column=0, sticky="w")

        csv_frame = ttk.Frame(options)
        csv_frame.grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(csv_frame, text="Save to CSV:", variable=self.csv_var).pack(side="left")
        ttk.Entry(csv_frame, textvariable=self.csv_file_var, width=15).pack(side="left", padx=5)
        ttk.Button(csv_frame, text="...", command=self.browse_csv, width=3).pack(side="left")

        flash_frame = ttk.Frame(options)
        flash_frame.grid(row=3, column=0, sticky="w", pady=5)
        ttk.Checkbutton(flash_frame, text="Flash firmware:", variable=self.flash_var).pack(side="left")
        ttk.Entry(flash_frame, textvariable=self.firmware_dir_var, width=15).pack(side="left", padx=5)
        ttk.Button(flash_frame, text="...", command=self.browse_firmware, width=3).pack(side="left")

        baud_frame = ttk.Frame(options)
        baud_frame.grid(row=4, column=0, sticky="w")
        ttk.Label(baud_frame, text="Flash baud rate:").pack(side="left")
        ttk.Combobox(baud_frame, textvariable=self.baud_rate_var,
                     values=[str(b) for b in BAUD_RATES], width=10, state="readonly").pack(side="left", padx=5)

        # Start button
        self.start_btn = ttk.Button(main, text="Start", command=self.process_device)
        self.start_btn.grid(row=3, column=0, columnspan=2, pady=10, sticky="ew")

        # Device ID
        id_container = ttk.LabelFrame(main, text="Device ID", padding=10)
        id_container.grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)

        id_frame = ttk.Frame(id_container)
        id_frame.pack(fill="x")
        self.id_label = ttk.Label(id_frame, textvariable=self.device_id_var, font=("Consolas", 12, "bold"))
        self.id_label.pack(side="left", padx=5)
        ttk.Button(id_frame, text="Copy", command=self.copy_device_id).pack(side="right")

        # Device status (simplified log)
        status_log_frame = ttk.LabelFrame(main, text="Device Status", padding=10)
        status_log_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=5)

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
        badge_names = ["Active", "Conn", "TimeSync", "ADXL", "ADS", "Messaging", "Data"]
        for name in badge_names:
            badge = ttk.Label(badge_frame, text=name, background="gray", foreground="white",
                              padding=(5, 2))
            badge.pack(side="left", padx=2)
            self.badges[name] = badge

        self.status_text = scrolledtext.ScrolledText(status_log_frame, height=4, font=("Consolas", 9))
        self.status_text.pack(fill="x", expand=False)

        # Log (collapsible)
        self.log_frame = ttk.LabelFrame(main, text="Serial Log", padding=10)
        self.log_frame.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=5)
        main.rowconfigure(6, weight=1)
        main.columnconfigure(1, weight=1)
        self.log_visible = True

        log_header = ttk.Frame(self.log_frame)
        log_header.pack(fill="x")
        self.collapse_btn = ttk.Button(log_header, text="Hide", command=self.toggle_log_visibility, width=6)
        self.collapse_btn.pack(side="right")

        self.log_content = ttk.Frame(self.log_frame)
        self.log_content.pack(fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(self.log_content, height=8, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

        # Status
        status_frame = ttk.Frame(main)
        status_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
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

        if new_ports:
            # Auto-select the new port
            new_port = sorted(new_ports)[0]
            self.port_var.set(new_port)
            self.set_status(f"New device: {new_port}", "green")
        elif ports and not self.port_var.get():
            self.port_var.set(ports[0])
            self.set_status(f"Found {len(ports)} port(s)")
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
            self.set_badge("Conn", False, "Conn")

    def parse_serial_line(self, line):
        """Parse serial line and return simplified status message if applicable."""
        # Boot/reset
        if "rst:0x" in line or "boot:" in line and "ESP-IDF" in line:
            self.root.after(0, self.reset_badges)
            self.root.after(0, lambda: self.set_badge("Active", True))
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
        return None

    def copy_device_id(self):
        """Copy device ID to clipboard."""
        device_id = self.device_id_var.get()
        if device_id and device_id != "—":
            self.root.clipboard_clear()
            self.root.clipboard_append(device_id)
            self.set_status("Copied to clipboard!", "green")

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
        """Toggle serial log visibility."""
        if self.log_visible:
            self.log_content.pack_forget()
            self.collapse_btn.configure(text="Show")
            self.log_visible = False
        else:
            self.log_content.pack(fill="both", expand=True)
            self.collapse_btn.configure(text="Hide")
            self.log_visible = True

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
            self.root.after(0, lambda: self.set_badge("Active", True))
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
                self.root.after(0, lambda: self.set_status(f"Flashing {device_name}...", "blue"))
                self.root.after(0, lambda: self.log_message(f"[INFO] Flashing {device_name} @ {baud_rate} baud from {self.firmware_dir_var.get()}..."))

                success, msg = flash_firmware(port, self.firmware_dir_var.get(), device_type, baud_rate)
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
