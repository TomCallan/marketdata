import os
from pathlib import Path

startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
vbs_path = startup_dir / "MarketDataTray.vbs"
target_exe = Path(r"C:\Users\TomCa\Documents\velotrade\.venv\Scripts\pythonw.exe")
cwd = Path(r"C:\Users\TomCa\Documents\velotrade")

vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{cwd}"
WshShell.Run """{target_exe}"" -m marketdata.tray", 0, False
'''

with open(vbs_path, "w", encoding="utf-8") as f:
    f.write(vbs_content)

print(f"Created startup file at: {vbs_path}")
