"""SWM - Scrcpy Window Manager

Usage:
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app run <app_name> [<scrcpy_args>...]
  swm [options] app (list|search)
  swm [options] app most-used [count]
  swm [options] app config <app_name> (show|edit)
  swm [options] session (list|search)
  swm [options] session restore [session_name]
  swm [options] session (save|delete) <session_name>
  swm [options] device (list|search)
  swm [options] device select <device_id>
  swm [options] device name <device_id> <device_alias>
  swm [options] baseconfig show [diagnostic]
  swm [options] baseconfig edit
  swm --version
  swm --help

Options:
  -h --help     Show this screen.
  --version     Show version.
  -c --config=<config_file>
                Use a config file.
  -v --verbose  Enable verbose logging.
  -d --device=<device_selected>
                Device name or ID for executing the command
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
from docopt import docopt
from typing import List, Dict, Optional
import tempfile
import zipfile
import yaml

__version__ = "0.1.0"

# TODO: set window title as "scrcpy - <device_name> - <app_name>"
# --window-title=<title>

# TODO: override icon with SCRCPY_ICON_PATH=<app_icon_path>

# TODO: use "scrcpy --list-apps" instead of using aapt to parse app labels

def select_editor():
    unix_editors = ["vim", "nano", "vi", "emacs"]
    windows_editors = ["notepad"]
    cross_platform_editors = ["code"]

    possible_editors = unix_editors + windows_editors + cross_platform_editors

    for editor in possible_editors:
        editor_binpath = shutil.which(editor)
        if editor_binpath:
            print("Using editor:", editor_binpath)
            return editor_binpath
    print(
        "No editor found. Please install one of the following editors:",
        ", ".join(possible_editors),
    )


def edit_file(filepath: str, editor_binpath: str):
    execute_subprogram(editor_binpath, [filepath])


def edit_or_open_file(filepath: str):
    editor_binpath = select_editor()
    if editor_binpath:
        edit_file(filepath, editor_binpath)
    else:
        open_file_with_default_application(filepath)


def open_file_with_default_application(filepath: str):
    system = platform.system()
    if system == "Darwin":  # macOS
        command = ["open", filepath]
    elif system == "Windows":  # Windows
        command = ["start", filepath]
    elif shutil.which("open"):  # those Linux OSes with "xdg-open"
        command = ["open", filepath]
    else:
        raise ValueError("Unsupported operating system.")
    subprocess.run(command, check=True)


def download_and_unzip(url, extract_dir):
    """
    Downloads a ZIP file from a URL and extracts it to the specified directory.

    Args:
        url (str): URL of the ZIP file to download.
        extract_dir (str): Directory path where contents will be extracted.
    """
    # Create extraction directory if it doesn't exist
    os.makedirs(extract_dir, exist_ok=True)

    # Stream download to a temporary file
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Raise error for bad status codes

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            # Write downloaded chunks to the temporary file
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
            tmp_path = tmp_file.name

    # Extract the ZIP file
    with zipfile.ZipFile(tmp_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    # Clean up temporary file
    os.unlink(tmp_path)


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


def download_binary_into_cache_dir_and_return_path(
    cache_dir: str, bin_name: str
) -> str:
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

    def infer_current_device(self, default_device: str):
        all_devices = self.adb_wrapper.list_devices()
        if len(all_devices) == 0:
            # no devices.
            print("No device is online")
            return
        elif len(all_devices) == 1:
            # only one device.
            device = all_devices[0]
            if device != default_device:
                print(
                    "Device selected by config (%s) is not online, using the only device online (%s)"
                    % (default_device, device)
                )
            return device
        else:
            print("Multiple device online")
            if default_device in all_devices:
                print("Using selected device:", default_device)
                return default_device
            else:
                print(
                    "Device selected by config (%s) is not online, please select one."
                    % default_device
                )
                prompt_for_device = f"Select a device from {all_devices}: "
                # TODO: input numbers or else
                # TODO: show detailed info per device, such as device type, last swm use time, alias, device model, android info, etc...
                while True:
                    selected_device = input(prompt_for_device)
                    if selected_device in all_devices:
                        print("Selecting device:", selected_device)
                        return selected_device
                    else:
                        print("Invalid device selected, please try again.")


class AppManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.config = swm.config

    def search(self):
        return self.list(search=True)

    def list(self, search: bool = False, most_used: Optional[int] = None):
        if most_used:
            apps = self.list_most_used_apps(most_used)
        else:
            apps = self.list_all_apps()

        if search:
            return self.swm.fzf_wrapper.select_item(apps)
        return apps

    def run(self, app_name: str, scrcpy_args: List[str] = None):
        # TODO: memorize the last scrcpy run args, by default in swm config

        # Get app config
        app_config = self.get_app_config(app_name)

        # Add window config if exists
        win = app_config.get("window", None)

        if scrcpy_args is None:
            scrcpy_args = app_config.get("scrcpy_args", None)

        # Execute scrcpy
        self.swm.scrcpy_wrapper.launch_app(
            app_name, window_params=win, scrcpy_args=scrcpy_args
        )

    def edit_app_config(self, app_name: str) -> bool:
        # return True if edited, else False
        print(f"Editing config for {app_name}")
        app_config_path = self.get_app_config_path(app_name)
        self.get_or_create_app_config(app_name)
        edit_or_open_file(app_config_path)

    def show_app_config(self, app_name: str):
        config = self.get_or_create_app_config(app_name)
        print(pretty_print_json(config))

    def get_app_config_path(self, app_name: str):

        app_config_dir = os.path.join(self.swm.cache_dir, "apps")
        os.makedirs(app_config_dir, exist_ok=True)

        app_config_path = os.path.join(app_config_dir, f"{app_name}.yaml")
        return app_config_path

    def get_or_create_app_config(self, app_name: str) -> Dict:
        app_config_path = self.get_app_config_path(app_name)
        
        if not os.path.exists(app_config_path):
            print("Creating default config for app:", app_name)
            # Write default YAML template with comments
            with open(app_config_path, "w") as f:
                f.write(self.default_app_config)

        with open(app_config_path, "r") as f:
            return yaml.safe_load(f)

    @property
    def default_app_config(self):
        return """# Application configuration template
# All settings are optional - uncomment and modify as needed

# arguments passed to scrcpy
scrcpy_args: []

"""

    def save_app_config(self, app_name: str, config: Dict):
        app_config_path = self.get_app_config_path(app_name)
        with open(app_config_path, "w") as f:
            yaml.safe_dump(config, f)

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

    def search(self):
        return self.list(search=True)

    def list(self, search: bool = False) -> List[str]:
        sessions = [f for f in os.listdir(self.session_dir) if f.endswith(".json")]

        if search:
            return self.swm.fzf_wrapper.select_item(sessions)
        return sessions

    def save(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.json")

        # Get current window positions and app states
        session_data = {
            "timestamp": time.time(),
            "device": self.swm.current_device,
            "windows": self._get_window_states(),
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

    def delete(self, session_name: str) -> bool:
        session_path = os.path.join(self.session_dir, f"{session_name}.json")
        if os.path.exists(session_path):
            os.remove(session_path)
            return True
        return False

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

    def search(self):
        return self.list(search=True)

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
        result = subprocess.run(cmd, capture_output=capture, text=True, check=True)
        if capture:
            return result.stdout.strip()
        return None

    def get_android_version(self) -> str:
        return self.execute(
            ["shell", "getprop", "ro.build.version.release"], capture=True
        )

    def get_device_architecture(self) -> str:
        return self.execute(["shell", "getprop", "ro.product.cpu.abi"], capture=True)

    def list_devices(self) -> List[str]:
        # TODO: detect and filter unauthorized and abnormal devices
        output = self.execute(["devices"], capture=True)
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                elements = line.split()
                device_id = elements[0]
                device_status = elements[1]
                if device_status != "unauthorized":
                    devices.append(device_id)
                else:
                    print("Warning: device %s unauthorized thus skipped" % device_id)
        return devices

    def list_packages(self) -> List[str]:
        output = self.execute(["shell", "pm", "list", "packages"], capture=True)
        packages = []
        for line in output.splitlines():
            if line.startswith("package:"):
                packages.append(line[len("package:") :].strip())
        return packages

    def create_swm_dir(self):
        self.execute(["shell", "mkdir", "-p", self.config.android_session_storage_path])

    def push_aapt(self, device_path: str = None):
        if device_path is None:
            device_path = os.path.join(self.config.android_session_storage_path, "aapt")
        device_architecture = self.get_device_architecture()
        local_aapt_path = os.path.join(
            self.config.cache_dir, "bin", "aapt-%s" % device_architecture
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

    def launch_app(
        self,
        package_name: str,
        window_params: Dict = None,
        scrcpy_args: list[str] = None,
    ):
        args = []

        configured_window_options = []

        zoom_factor = self.config.zoom_factor # TODO: make use of it

        if window_params:
            for it in ["x", "y", "width", "height"]:
                if it in window_params:
                    args.extend(["--window-%s=%s" % (it, window_params[it])])
                    configured_window_options.append("--window-%s" % it)

        if scrcpy_args:
            for it in scrcpy_args:
                if it.split("=")[0] not in configured_window_options:
                    args.append(it)
                else:
                    print("Warning: one of scrcpy options '%s' is already configured via window options" % it)


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
                cmd, stdin=open(tmp.name, "r"), capture_output=True, text=True
            )

            if result.returncode == 0:
                return result.stdout.strip()
            return ""


def create_default_config(cache_dir: str) -> omegaconf.DictConfig:
    return omegaconf.OmegaConf.create(
        {
            "cache_dir": cache_dir,
            "device": None,
            "zoom_factor": 1.0,
            "session_autosave": True,
            "android_session_storage_path": "/sdcard/.swm",
            "github_mirrors": [
                "https://github.com",
                "https://bgithub.xyz",
                "https://kgithub.com",
            ],
            "binaries": {
                "adb": {"version": "1.0.41"},
                "scrcpy": {"version": "2.0"},
                "fzf": {"version": "0.42.0"},
            },
        }
    )


def get_config_path(cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    config_path = os.path.join(cache_dir, "config.yaml")
    return config_path


def load_or_create_config(cache_dir: str, config_path: str) -> omegaconf.DictConfig:
    if os.path.exists(config_path):
        print("Loading existing config from:", config_path)
        return omegaconf.OmegaConf.load(config_path)

    print("Creating default config at:", config_path)
    config = create_default_config(cache_dir)
    omegaconf.OmegaConf.save(config, config_path)
    return config


def override_system_excepthook(program_specific_params: Dict):
    def custom_excepthook(exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        print("\nAn unhandled exception occurred, showing diagnostic info:")
        print_diagnostic_info(program_specific_params)

    sys.excepthook = custom_excepthook


def parse_args():
    return docopt(__doc__, version=f"SWM {__version__}", options_first=True)


def main():
    # Setup cache directory
    default_cache_dir = os.path.expanduser("~/.swm")
    SWM_CACHE_DIR = os.environ.get("SWM_CACHE_DIR", default_cache_dir)
    os.makedirs(SWM_CACHE_DIR, exist_ok=True)

    config_path = get_config_path(SWM_CACHE_DIR)
    # Load or create config
    config = load_or_create_config(SWM_CACHE_DIR, config_path)

    # Parse CLI arguments
    args = parse_args()

    # Prepare diagnostic info
    program_specific_params = {
        "cache_dir": SWM_CACHE_DIR,
        "config": omegaconf.OmegaConf.to_container(config),
        "argv": sys.argv,
        "parsed_args": args,
        "executable": sys.executable,
        "config_overriden_parameters": {},
    }
    override_system_excepthook(program_specific_params)

    # Initialize SWM core
    swm = SWM(config)

    # # Command routing
    # try:
    if args["adb"]:
        execute_subprogram(swm.adb, args["<adb_args>"])

    elif args["scrcpy"]:
        execute_subprogram(swm.scrcpy, args["<scrcpy_args>"])

    elif args["baseconfig"]:
        if args["show"]:
            if args["diagnostic"]:
                print_diagnostic_info(program_specific_params)
            else:
                print(omegaconf.OmegaConf.to_yaml(config))

        elif args["edit"]:
            # Implementation would open editor
            print("Opening config editor")
            edit_or_open_file(config_path)

    elif args["device"]:
        if args["list"]:
            devices = swm.device_manager.list()
            print("\n".join(devices))
        elif args["search"]:
            device = swm.device_manager.search()
            ans = input("Choose an option(select|name):")
            if ans.lower() == "select":
                swm.device_manager.select(device)
            elif ans.lower() == "name":
                alias = input("Enter the alias for device %s:" % device)
                swm.device_manager.name(device, alias)
        elif args["select"]:
            swm.device_manager.select(args["<device_id>"])
        elif args["name"]:
            swm.device_manager.name(args["<device_id>"], args["<device_alias>"])

    elif args["--version"]:
        print(f"SWM version {__version__}")
    else:
        # Device specific branches

        # Handle device selection
        cli_device = args["<device_selected>"]
        config_device = config.device

        if cli_device is not None:
            default_device = cli_device
        else:
            default_device = config_device

        current_device = swm.infer_current_device(default_device)

        if current_device is not None:
            swm.set_current_device(current_device)
        else:
            raise ValueError("No available device")

        if args["app"]:
            if args["list"]:
                apps = swm.app_manager.list()
                print("\n".join(apps))
            elif args["search"]:
                app = swm.app_manager.search()
                ans = input("Please select an action (run|config):")
                if ans.lower() == "run":
                    scrcpy_args = input("Application arguments:")
                    swm.app_manager.run(app, scrcpy_args)
                elif ans.lower() == "config":
                    opt = input("Please choose an option (edit|show)")
                    if opt == "edit":
                        swm.app_manager.edit_app_config(app_name)
                    elif opt == "show":
                        swm.app_manager.show_app_config(app_name)
            elif args["most-used"]:
                apps = swm.app_manager.list(most_used=args.get("count", 10))
                print("\n".join(apps))
            elif args["run"]:
                swm.app_manager.run(args["<app_name>"], args["<scrcpy_args>"])

            elif args["config"]:
                app_name = args["<app_name>"]
                if args["show"]:
                    swm.app_manager.show_app_config(app_name)
                elif args["edit"]:
                    # Implementation would open editor
                    swm.app_manager.edit_app_config(app_name)

        elif args["session"]:
            if args["list"]:
                sessions = swm.session_manager.list()
                print("\n".join(sessions))
            elif args["search"]:
                session_name = swm.session_manager.search()
                opt = input("Please specify an action (restore|delete)")
                if opt == "restore":
                    swm.session_manager.restore(session_name)
                elif opt == "delete":
                    swm.session_manager.delete(session_name)

            elif args["save"]:
                swm.session_manager.save(args["<session_name>"])

            elif args["restore"]:
                session_name = args.get("<session_name>", "default")
                swm.session_manager.restore(session_name)

            elif args["delete"]:
                swm.session_manager.delete(args["<session_name>"])
            else:
                ...  # Implement other device specific commands

    # except Exception as e:
    #     print(f"Error: {e}")
    #     if args["--verbose"]:
    #         traceback.print_exc()


if __name__ == "__main__":
    main()
