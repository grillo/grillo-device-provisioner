#!/usr/bin/env python3
"""
Grillo Device Reader - GUI

Cross-platform GUI for provisioning ESP32 devices.
Uses CustomTkinter for modern appearance.
"""

import threading
import sys
import time

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
        self.root.title("Grillo Device Reader")
        self.root.minsize(520, 680)

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
        ctk.CTkLabel(main, text="Grillo Device Reader", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(0, 15))

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
                                          values=list(DEVICE_CONFIGS.keys()), width=200, state="readonly")
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

        # Result frame
        result = ctk.CTkFrame(main)
        result.pack(fill="x", pady=5)

        ctk.CTkLabel(result, text="Result", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        id_frame = ctk.CTkFrame(result, fg_color="transparent")
        id_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(id_frame, text="Device ID:", width=80, anchor="w").pack(side="left")
        self.id_label = ctk.CTkLabel(id_frame, textvariable=self.device_id_var,
                                      font=ctk.CTkFont(family="Consolas", size=14, weight="bold"))
        self.id_label.pack(side="left", padx=10)
        ctk.CTkButton(id_frame, text="Copy", command=self.copy_device_id, width=60).pack(side="left")

        # Log frame
        log_frame = ctk.CTkFrame(main)
        log_frame.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(log_frame, text="Serial Log", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        self.log_text = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        # Log buttons
        log_btn_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_btn_frame.pack(fill="x", padx=10, pady=5)
        self.monitor_btn = ctk.CTkButton(log_btn_frame, text="Start Monitor", command=self.toggle_monitor, width=100)
        self.monitor_btn.pack(side="left", padx=5)
        ctk.CTkButton(log_btn_frame, text="Clear", command=self.clear_log, width=60).pack(side="left", padx=5)

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

        # Result
        result = ttk.LabelFrame(main, text="Result", padding=10)
        result.grid(row=4, column=0, columnspan=2, sticky="ew")

        ttk.Label(result, text="Device ID:").grid(row=0, column=0, sticky="w")
        self.id_label = ttk.Label(result, textvariable=self.device_id_var, font=("Consolas", 12, "bold"))
        self.id_label.grid(row=0, column=1, sticky="w")
        ttk.Button(result, text="Copy", command=self.copy_device_id).grid(row=0, column=2)

        # Log
        log_frame = ttk.LabelFrame(main, text="Serial Log", padding=10)
        log_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=10)
        main.rowconfigure(5, weight=1)
        main.columnconfigure(1, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill="x", pady=5)
        self.monitor_btn = ttk.Button(log_btn_frame, text="Start Monitor", command=self.toggle_monitor)
        self.monitor_btn.pack(side="left")
        ttk.Button(log_btn_frame, text="Clear", command=self.clear_log).pack(side="left", padx=5)

        # Status
        status_frame = ttk.Frame(main)
        status_frame.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Label(status_frame, text="Status:").pack(side="left")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side="left", padx=5)

    def refresh_ports(self):
        """Refresh the list of available COM ports."""
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

        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

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
        """Clear the log output."""
        if HAS_CUSTOMTKINTER:
            self.log_text.delete("1.0", "end")
        else:
            self.log_text.delete("1.0", "end")

    def copy_device_id(self):
        """Copy device ID to clipboard."""
        device_id = self.device_id_var.get()
        if device_id and device_id != "—":
            self.root.clipboard_clear()
            self.root.clipboard_append(device_id)
            self.set_status("Copied to clipboard!", "green")

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

            while self.serial_running:
                if ser.in_waiting:
                    try:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        if line:
                            self.root.after(0, lambda l=line: self.log_message(f"[DEVICE] {l}"))
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
