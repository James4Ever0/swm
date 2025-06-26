"""SWM - Scrcpy Window Manager

Usage:
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app run <app_name> [<app_args>...]
  swm [options] app list [--search] [--most-used <limit>]
  swm [options] app config <app_name> (show|edit)
  swm [options] session list [--search]
  swm [options] session restore [session_name]
  swm [options] session save <session_name>
  swm [options] session delete <session_name>
  swm [options] device list [--search]
  swm [options] device select <device_id>
  swm [options] device name <device_id> <device_alias>
  swm [options] baseconfig show [--diagnostic]
  swm [options] baseconfig edit
  swm --version
  swm --help

Options:
  -h --help     Show this screen.
  --version     Show version.
  -c --config=<config_file>
                Use a config file.
  -v --verbose  Enable verbose logging.
  -d --device   Device name or ID for executing the command
"""

import os
import platform
import shutil
import omegaconf
import sys
import traceback
import json
import subprocess
import requests
import time
import tempfile
import stat
from docopt import docopt
from pathlib import Path
from typing import List, Dict, Optional, Tuple

__version__ = "0.1.0"

def download_and_unzip_file_to_target_directory(url, directory):
    # Implementation would go here
    pass

def get_system_and_architecture():
    system = platform.system().lower()
    arch = platform.machine().lower()
    if arch == "x86_64":
        arch = "x64"
    elif arch == "aarch64":
        arch = "arm64"
    return system, arch

def collect_system_info_for_diagnostic():
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "architecture": platform.architecture(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }

def pretty_print_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=4)

def print_diagnostic_info(program_specific_params):
    system_info = collect_system_info_for_diagnostic()
    print("System info:")
    print(pretty_print_json(system_info))
    print("\nProgram parameters:")
    print(pretty_print_json(program_specific_params))

def execute_subprogram(program_path, args):
    try:
        subprocess.run([program_path] + args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing {program_path}: {e}")
    except FileNotFoundError:
        print(f"Executable not found: {program_path}")

def search_or_obtain_binary_path_from_environmental_variable_or_download(
    cache_dir: str, bin_name: str
) -> str:
    # Adjust binary name for platform
    bin_env_name = bin_name.upper()
    platform_specific_name = bin_name.lower()
    
    if platform.system() == "Windows":
        platform_specific_name += ".exe"
    
    # 1. Check environment variable
    env_path = os.environ.get(bin_env_name)
    if env_path and os.path.exists(env_path):
        return env_path
    
    # 2. Check in PATH
    path_path = shutil.which(platform_specific_name)
    if path_path:
        return path_path
    
    # 3. Check in cache directory
    cache_path = os.path.join(cache_dir, "bin", platform_specific_name)
    if os.path.exists(cache_path):
        return cache_path
    
    # 4. Not found anywhere - attempt to download
    return download_binary_into_cache_dir_and_return_path(cache_dir, bin_name)

def download_binary_into_cache_dir_and_return_path(cache_dir: str, bin_name: str) -> str:
    # Placeholder implementation - would download the binary
    bin_dir = os.path.join(cache_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    
    # For demonstration purposes, we'll just create an empty file
    bin_path = os.path.join(bin_dir, bin_name)
    if platform.system() == "Windows":
        bin_path += ".exe"
    
    print(f"WARNING: Creating placeholder binary at {bin_path}")
    with open(bin_path, "w") as f:
        f.write("#!/bin/sh\necho 'Placeholder binary for SWM'")
    
    if platform.system() != "Windows":
        os.chmod(bin_path, 0o755)
    
    return bin_path

class SWM:
    def __init__(self, config: omegaconf.DictConfig):
        self.config = config
        self.cache_dir = config.cache_dir
        self.bin_dir = os.path.join(self.cache_dir, "bin")
        os.makedirs(self.bin_dir, exist_ok=True)
        
        # Initialize binaries
        self.adb = self._get_binary("adb")
        self.scrcpy = self._get_binary("scrcpy")
        self.fzf = self._get_binary("fzf")
        
        # Initialize components
        self.adb_wrapper = AdbWrapper(self.adb, self.config)
        self.scrcpy_wrapper = ScrcpyWrapper(self.scrcpy, self.config)
        self.fzf_wrapper = FzfWrapper(self.fzf)
        
        # Device management
        self.current_device = self.config.get("device")
        
        # Initialize managers
        self.app_manager = AppManager(self)
        self.session_manager = SessionManager(self)
        self.device_manager = DeviceManager(self)
    
    def _get_binary(self, name: str) -> str:
        return search_or_obtain_binary_path_from_environmental_variable_or_download(
            self.cache_dir, name
        )
    
    def set_current_device(self, device_id: str):
        self.current_device = device_id
        self.adb_wrapper.set_device(device_id)
        self.scrcpy_wrapper.set_device(device_id)
    
    def get_device_architecture(self) -> str:
        return self.adb_wrapper.get_device_architecture()

class AppManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.config = swm.config
    
    def list(self, search: bool = False, most_used: Optional[int] = None):
        if most_used:
            apps = self.list_most_used_apps(most_used)
        else:
            apps = self.list_all_apps()
        
        if search:
            return self.swm.fzf_wrapper.select_item(apps)
        return apps
    
    def run(self, app_name: str, app_args: List[str] = None):
        if app_args is None:
            app_args = []
        
        # Get app config
        app_config = self.get_app_config(app_name)
        
        # Build scrcpy command
        scrcpy_args = []
        
        # Add window config if exists
        win = app_config.get("window", None)
        device_win = app_config.get("device_window", None)
        
        
        # Add app launch parameters
        scrcpy_args.extend(["--start-app", app_name])
        
        # Execute scrcpy
        self.swm.scrcpy_wrapper.launch_app(app_name, window_params = win, device_window_params= device_win)
    
    def get_app_config(self, app_name: str) -> Dict:
        # Load app config from cache
        app_config_path = os.path.join(
            self.swm.cache_dir, "apps", f"{app_name}.json"
        )
        
        if os.path.exists(app_config_path):
            with open(app_config_path, "r") as f:
                return json.load(f)
        
        # Return default config if none exists
        return {
            "dpi": 160,
            "window": {
                "x": 100,
                "y": 100,
                "width": 800,
                "height": 600
            }
        }
    
    def save_app_config(self, app_name: str, config: Dict):
        app_dir = os.path.join(self.swm.cache_dir, "apps")
        os.makedirs(app_dir, exist_ok=True)
        
        app_config_path = os.path.join(app_dir, f"{app_name}.json")
        with open(app_config_path, "w") as f:
            json.dump(config, f, indent=2)
    
    def list_all_apps(self) -> List[str]:
        return self.swm.adb_wrapper.list_packages()
    
    def list_most_used_apps(self, limit: int) -> List[str]:
        # Placeholder implementation
        return self.list_all_apps()[:limit]

class SessionManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.config = swm.config
        self.session_dir = os.path.join(swm.cache_dir, "sessions")
        os.makedirs(self.session_dir, exist_ok=True)
    
    def list(self, search: bool = False) -> List[str]:
        sessions = [f for f in os.listdir(self.session_dir) 
                   if f.endswith(".json")]
        
        if search:
            return self.swm.fzf_wrapper.select_item(sessions)
        return sessions
    
    def save(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")
        
        # Get current window positions and app states
        session_data = {
            "timestamp": time.time(),
            "device": self.swm.current_device,
            "windows": self._get_window_states()
        }
        
        with open(session_path, "w") as f:
            json.dump(session_data, f, indent=2)
    
    def restore(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")
        
        if not os.path.exists(session_path):
            raise FileNotFoundError(f"Session not found: {session_name}")
        
        with open(session_path, "r") as f:
            session_data = json.load(f)
        
        # Restore each window
        for app_name, window_config in session_data["windows"].items():
            self.swm.app_manager.run(app_name)
            # Additional window positioning would go here
    
    def delete(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")
        if os.path.exists(session_path):
            os.remove(session_path)
    
    def _get_window_states(self) -> Dict:
        # Placeholder implementation
        return {}

class DeviceManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.devices_file = os.path.join(swm.cache_dir, "devices.json")
        self.devices = self._load_devices()
    
    def list(self, search: bool = False) -> List[str]:
        if search:
            return self.swm.fzf_wrapper.select_item(list(self.devices.keys()))
        return list(self.devices.keys())
    
    def select(self, device_id: str):
        self.swm.set_current_device(device_id)
    
    def name(self, device_id: str, alias: str):
        self.devices[alias] = device_id
        self._save_devices()
    
    def _load_devices(self) -> Dict:
        if os.path.exists(self.devices_file):
            with open(self.devices_file, "r") as f:
                return json.load(f)
        return {}
    
    def _save_devices(self):
        with open(self.devices_file, "w") as f:
            json.dump(self.devices, f, indent=2)

class AdbWrapper:
    def __init__(self, adb_path: str, config: omegaconf.DictConfig):
        self.adb_path = adb_path
        self.config = config
        self.device = config.get("device")
    
    def set_device(self, device_id: str):
        self.device = device_id
    
    def _build_cmd(self, args: List[str]) -> List[str]:
        cmd = [self.adb_path]
        if self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(args)
        return cmd
    
    def execute(self, args: List[str], capture: bool = False) -> Optional[str]:
        cmd = self._build_cmd(args)
        result = subprocess.run(
            cmd, 
            capture_output=capture, 
            text=True,
            check=True
        )
        if capture:
            return result.stdout.strip()
        return None
    
    def get_device_architecture(self) -> str:
        return self.execute(["shell", "getprop", "ro.product.cpu.abi"], capture=True)
    
    def list_devices(self) -> List[str]:
        output = self.execute(["devices"], capture=True)
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                devices.append(line.split()[0])
        return devices
    
    def list_packages(self) -> List[str]:
        output = self.execute(["shell", "pm", "list", "packages"], capture=True)
        packages = []
        for line in output.splitlines():
            if line.startswith("package:"):
                packages.append(line[len("package:"):].strip())
        return packages
    
    def create_swm_dir(self):
        self.execute(["shell", "mkdir", "-p", self.config.android_session_storage_path])
    
    def push_aapt(self, local_aapt_path: str, device_path: str = None):
        if device_path is None:
            device_path = os.path.join(
                self.config.android_session_storage_path, "aapt"
            )
        self.execute(["push", local_aapt_path, device_path])
        self.execute(["shell", "chmod", "755", device_path])
    
    def pull_session(self, session_name: str, local_path: str):
        remote_path = os.path.join(
            self.config.android_session_storage_path, session_name
        )
        self.execute(["pull", remote_path, local_path])

class ScrcpyWrapper:
    def __init__(self, scrcpy_path: str, config: omegaconf.DictConfig):
        self.scrcpy_path = scrcpy_path
        self.config = config
        self.device = config.get("device")
    
    def set_device(self, device_id: str):
        self.device = device_id
    
    def _build_cmd(self, args: List[str]) -> List[str]:
        cmd = [self.scrcpy_path]
        if self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(args)
        return cmd
    
    def execute(self, args: List[str]):
        cmd = self._build_cmd(args)
        subprocess.run(cmd, check=True)
    
    def launch_app(self, package_name: str, window_params: Dict = None, device_window_params:str= None):
        args = []
        
        if window_params:
            args.extend([
                f"--window-x={window_params['x']}",
                f"--window-y={window_params['y']}",
                f"--window-width={window_params['width']}",
                f"--window-height={window_params['height']}"
            ])
        
        if device_window_params:
            args.extend([f"--new-display={device_window_params}"])
        else:
            args.extend(["--new-display"])
        
        
        args.extend(["--start-app", package_name])
        self.execute(args)

class FzfWrapper:
    def __init__(self, fzf_path: str):
        self.fzf_path = fzf_path
    
    def select_item(self, items: List[str]) -> str:
        with tempfile.NamedTemporaryFile(mode="w+") as tmp:
            tmp.write("\n".join(items))
            tmp.flush()
            
            cmd = [self.fzf_path, "--height", "40%", "--layout=reverse"]
            result = subprocess.run(
                cmd,
                stdin=open(tmp.name, "r"),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return ""

def create_default_config(cache_dir: str) -> omegaconf.DictConfig:
    return omegaconf.OmegaConf.create({
        "cache_dir": cache_dir,
        "device": None,
        "zoom_factor": 1.0,
        "session_autosave": True,
        "android_session_storage_path": "/sdcard/.swm",
        "github_mirrors": [
            "https://github.com",
            "https://kgithub.com"
        ],
        "binaries": {
            "adb": {"version": "1.0.41"},
            "scrcpy": {"version": "2.0"},
            "fzf": {"version": "0.42.0"}
        }
    })

def load_or_create_config(cache_dir: str) -> omegaconf.DictConfig:
    config_path = os.path.join(cache_dir, "config.yaml")
    
    if os.path.exists(config_path):
        print("Loading existing config from:", config_path)
        return omegaconf.OmegaConf.load(config_path)
    
    os.makedirs(cache_dir, exist_ok=True)
    print("Creating default config at:", config_path)
    config = create_default_config(cache_dir)
    omegaconf.OmegaConf.save(config, config_path)
    return config

def override_system_excepthook(program_specific_params: Dict):
    def custom_excepthook(exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        print("\nAn unhandled exception occurred:")
        print_diagnostic_info(program_specific_params)
    
    sys.excepthook = custom_excepthook

def parse_args():
    return docopt(__doc__, version=f"SWM {__version__}",  options_first=True)

def main():
    # Setup cache directory
    default_cache_dir = os.path.expanduser("~/.swm")
    SWM_CACHE_DIR = os.environ.get("SWM_CACHE_DIR", default_cache_dir)
    os.makedirs(SWM_CACHE_DIR, exist_ok=True)
    
    # Load or create config
    config = load_or_create_config(SWM_CACHE_DIR)
    
    # Prepare diagnostic info
    program_specific_params = {
        "cache_dir": SWM_CACHE_DIR,
        "config": omegaconf.OmegaConf.to_container(config),
        "argv": sys.argv,
        "executable": sys.executable
    }
    override_system_excepthook(program_specific_params)
    
    # Parse CLI arguments
    args = parse_args()
    
    # Initialize SWM core
    swm = SWM(config)
    
    # Handle device selection
    if args["--device"]:
        swm.set_current_device(args["--device"])
    
    # # Command routing
    # try:
    if args["adb"]:
        execute_subprogram(swm.adb, args["<adb_args>"])
    
    elif args["scrcpy"]:
        execute_subprogram(swm.scrcpy, args["<scrcpy_args>"])
    
    elif args["app"]:
        if args["list"]:
            apps = swm.app_manager.list(
                search=args["--search"],
                most_used=int(args["--most-used"]) if args["--most-used"] else None
            )
            print("\n".join(apps))
        
        elif args["run"]:
            swm.app_manager.run(args["<app_name>"], args["<app_args>"])
        
        elif args["config"]:
            app_name = args["<app_name>"]
            if args["show"]:
                config = swm.app_manager.get_app_config(app_name)
                print(pretty_print_json(config))
            elif args["edit"]:
                # Implementation would open editor
                print(f"Editing config for {app_name}")
    
    elif args["session"]:
        if args["list"]:
            sessions = swm.session_manager.list(search=args["--search"])
            print("\n".join(sessions))
        
        elif args["save"]:
            swm.session_manager.save(args["<session_name>"])
        
        elif args["restore"]:
            session_name = args.get("<session_name>", "default")
            swm.session_manager.restore(session_name)
        
        elif args["delete"]:
            swm.session_manager.delete(args["<session_name>"])
    
    elif args["device"]:
        if args["list"]:
            devices = swm.device_manager.list(search=args["--search"])
            print("\n".join(devices))
        
        elif args["select"]:
            swm.device_manager.select(args["<device_id>"])
        
        elif args["name"]:
            swm.device_manager.name(
                args["<device_id>"], 
                args["<device_alias>"]
            )
    
    elif args["baseconfig"]:
        if args["show"]:
            if args["--diagnostic"]:
                print_diagnostic_info(program_specific_params)
            else:
                print(omegaconf.OmegaConf.to_yaml(config))
        
        elif args["edit"]:
            # Implementation would open editor
            print("Opening config editor")
    
    elif args["--version"]:
        print(f"SWM version {__version__}")

    # except Exception as e:
    #     print(f"Error: {e}")
    #     if args["--verbose"]:
    #         traceback.print_exc()

if __name__ == "__main__":
    main()