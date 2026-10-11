"""
Build script to package JobHunter into a standalone Windows Desktop Executable (.exe).
Anyone can download and run JobHunter.exe without installing Python or dependencies.
"""
import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def build():
    print("=" * 60)
    print("Building JobHunter Desktop Executable (.exe)...")
    print("=" * 60)

    # Verify requirements
    icon_path = os.path.join(BASE_DIR, "app_icon.ico")
    public_path = os.path.join(BASE_DIR, "public")
    data_path = os.path.join(BASE_DIR, "data")

    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--name=JobHunter",
        "--noconsole",
        "--onedir",
        f"--icon={icon_path}",
        f"--add-data={public_path}{sep}public",
        f"--add-data={icon_path}{sep}.",
        "--hidden-import=webview",
        "--hidden-import=webview.platforms.winforms",
        "--hidden-import=sqlite3",
        "--hidden-import=urllib.request",
        "--clean",
        "-y",
        os.path.join(BASE_DIR, "desktop.py")
    ]

    # Include seed data folder if present
    if os.path.isdir(data_path):
        cmd.append(f"--add-data={data_path}{sep}data")

    print(f"Running PyInstaller:\n{' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=BASE_DIR)
    
    if res.returncode == 0:
        dist_dir = os.path.join(BASE_DIR, "dist", "JobHunter")
        exe_file = os.path.join(dist_dir, "JobHunter.exe")
        zip_base = os.path.join(BASE_DIR, "dist", "JobHunter-Windows-x64")
        
        print("\nCreating release ZIP archive...")
        shutil.make_archive(zip_base, "zip", root_dir=os.path.join(BASE_DIR, "dist"), base_dir="JobHunter")
        zip_file = zip_base + ".zip"
        size_mb = os.path.getsize(zip_file) // (1024 * 1024) if os.path.isfile(zip_file) else 0

        # Check for Inno Setup compiler to create setup installer
        iscc_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
            r"C:\Program Files\Inno Setup 7\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            shutil.which("iscc") or "",
        ]
        iscc_exe = next((p for p in iscc_paths if p and os.path.isfile(p)), None)
        setup_exe = os.path.join(BASE_DIR, "dist", "JobHunter-Setup.exe")
        if iscc_exe and os.path.isfile(os.path.join(BASE_DIR, "installer.iss")):
            print("\nCompiling Windows Setup Installer...")
            subprocess.run([iscc_exe, os.path.join(BASE_DIR, "installer.iss")], cwd=BASE_DIR)

        setup_size = f"{os.path.getsize(setup_exe) / (1024 * 1024):.1f} MB" if os.path.isfile(setup_exe) else "N/A"

        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print(f"1. Setup Installer:    {setup_exe} ({setup_size})")
        print(f"2. Standalone Folder:  {exe_file}")
        print(f"3. Distribution ZIP:   {zip_file} ({size_mb} MB)")
        print("=" * 60)
    else:
        print("\nPyInstaller build failed with returncode:", res.returncode)

if __name__ == "__main__":
    build()

