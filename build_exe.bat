@echo off
echo Building Grillo Device Provisioner executable...
echo.

pip install pyinstaller --quiet

pyinstaller --onefile --windowed ^
    --name "Grillo Device Provisioner" ^
    --add-data "esp32_device_reader.py;." ^
    --hidden-import=esptool ^
    --hidden-import=serial ^
    --hidden-import=serial.tools.list_ports ^
    --hidden-import=customtkinter ^
    esp32_device_reader_gui.py

echo.
echo Done! Executable is in: dist\Grillo Device Provisioner.exe
pause
