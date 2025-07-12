__doc__ = (
    DOCSTRING
) = """SWM - Scrcpy Window Manager

Usage:
  swm init [force]
  swm [options] repl
  swm [options] healthcheck
  swm [options] adb [<adb_args>...]
  swm [options] scrcpy [<scrcpy_args>...]
  swm [options] app recent
  swm [options] app run <query> [no-new-display] [<init_config>]
  swm [options] app list [with-last-used-time] [with-type] [update]
  swm [options] app search [with-type] [index]
  swm [options] app most-used [<count>]
  swm [options] app config show-default
  swm [options] app config list
  swm [options] app config (show|edit) <config_name>
  swm [options] app config copy <source_name> <target_name>
  swm [options] mount <device_path> <host_path>
  swm [options] mount reverse <host_path> <device_path>
  swm [options] ime list
  swm [options] ime (switch|activate|deactivate) <query>
  swm [options] ime search
  swm [options] ime switch-to-previous
  swm [options] java run <script_path>
  swm [options] java shell [<shell_args>...]
  swm [options] termux run <script_path>
  swm [options] termux exec <executable>
  swm [options] termux shell [<shell_args>...]
  swm [options] session list [last-used]
  swm [options] session search [index]
  swm [options] session restore [session_name]
  swm [options] session delete <query>
  swm [options] session edit <query>
  swm [options] session save <session_name>
  swm [options] session copy <source> <target>
  swm [options] device list [last-used]
  swm [options] device search [index]
  swm [options] device select <query>
  swm [options] device name <device_id> <device_alias>
  swm [options] baseconfig show [diagnostic]
  swm [options] baseconfig show-default
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
                Device name or ID for executing the command.
  --debug       Debug mode, capturing all exceptions.

Environment variables:
  SWM_CACHE_DIR
                SWM managed cache directory on PC, which stores the main config file
  SWM_CLI_SUGGESION_LIMIT
                Maximum possible command suggestions when failed to parse user input
  ADB           Path to ADB binary (overrides SWM managed ADB)
  SCRCPY        Path to SCRCPY binary (overrides SWM managed SCRCPY)
  FZF           Path to FZF binary (overrides SWM managed FZF)
"""

# TODO: use filelock to handle app recovery clashing at device reconnection, release the lock when app is launched for sure

# TODO: check gboard version, include gboard apk in our binary release, install gboard as our official companion input method app in uhid mode

# TODO: blacklist commands, change execution preferences, configs, commandline help based on healthcheck result per device

# TODO: Implement swm mount command, mount host volume to device and vice versa

# TODO: use java to collect usagestats, infer app last used time, instead of directory access time enumeration (incorrect), or increase enumeration depth? (slow)

# TODO: terminate scrcpy with the same app_id running when running new app, or refuse to launch, by configuration "launch_policy"

# TODO: infer the reason of scrcpy closing, like device_disconnect, app_gone, user_requested, new_instance, unknown

# TODO: restart application if the device is physically disconnected at the time it connects back

# TODO: paste from pc to device using adb keyboard by listening for paste events when clipboard fails

# TODO: fix IME issues using custom scrcpy GUI such as https://github.com/me2sy/MYScrcpy

# TODO: display placeholder window with text "Device offline", the same icon and window size while waiting device online

# TODO: display different commandline help for rooted and non-rooted devices

# TODO: generate, store and use android device uuid instead of device_id from adb devices for storing icons
# TODO: create desktop shortcuts for running specific swm commands

# TODO: manage all stdout and stderr into a separate textualize window, then setup a prompt or repl for doing various things like switching ime, starting and managing multiple sessions, managing wifi, bluetooth, files, etc.

# TODO: save session to all devices with the same name, and restore with the same name

# TODO: hold the main display lock if it is unlocked, till swm is not connected

# TODO: setup network connection between PC client and on device daemon via:
# adb forward tcp:<PC_PORT> tcp:<DEVICE_PORT>
# adb reverse tcp:<DEVICE_PORT> tcp:<PC_PORT>
# deepseek says "adb forward" is suitable for this scenario

# TODO: figure out the protocol used in scrcpy-server, change resolution on the fly using the protocol, track down the port forwarded per scrcpy session
# Note: seems adb is not showing scrcpy forwarded ports
# maybe it is communicated via unix socket, via adb shell?
# or using a separate adb server?
# android.net.LocalServerSocket
# adb shell cat /proc/net/unix
# adb forward tcp:<PC_PORT> localabstract:<ABSTRACT_SOCKET>
# adb reverse localabstract:<ABSTRACT_SOCKET> tcp:<PC_PORT>
# scrcpy/app/src/server.c:sc_adb_tunnel_open
# scrcpy/app/src/adb/adb_tunnel.c:sc_adb_tunnel_open
# SC_SOCKET_NONE

# adb forward --list
# adb reverse --list
# adb forward --remove
# adb forward --remove-all

# TODO: list running background apps viewable in taskbar

# TODO: Mark session with PC signature so we can prompt the user if mismatch, like "This is a remote session from xyz, do you trust this machine?"
# TODO: Sign session and other files on android device with public key to ensure integrity (using gnupg or something)

# TODO: provide a loadable, editable app alias file in yaml for faster launch

# BUG: cannot paste when screen is locked
# TODO: unlock the screen automatically using user provided scripts, note down the success rate, last success time, and last failure time

# TODO: suggest possible command completions when the user types a wrong command, using levenshtein

# TODO: when the main screen is locked, clipboard may fail to traverse. warn the user and ask to unlock the screen. (or automatically unlock the screen, if possible)

# TODO: consider a command to mirror the main display

# only import package when needed
# TODO: create a filelock or pid file to prevent multiple instances of the same app running
# TODO: ask the user to "run anyway" when multiple instances of the same app are running

# TODO: dynamically change the fps of scrcpy, only let the foreground one be full and others be 1 fps
# TODO: use platform specific window session manager
# TODO: run swm daemon at first invocation, monitoring window changes, fetch app list in the background, etc

# TODO: globally install this package into the first folder with permission in PATH, or use other tools (actually, adding current binary folder to PATH is better than this, so warn user if not added to PATH)

# TODO: show partial help instead of full help based on the command args given

import os
import platform
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

import omegaconf
from tinydb import Query, Storage, TinyDB
from tinydb.table import Document

__version__ = "0.1.0"

# TODO: refactor all code in scrcpywrapper and adbwrapper that does not require device_id with NO_DEVICE_ID
NO_DEVICE_ID = "NO_DEVICE_ID"


def sha256sum(text: str):
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


def get_file_content(filepath: str):
    if not os.path.exists(filepath):
        raise ValueError("File '%s' does not exist" % filepath)
    if os.path.isfile(filepath):
        with open(filepath, "r") as f:
            content = f.read()
            return content
    else:
        raise ValueError("File '%s' is not a file" % filepath)


def local_webp_to_png(webp_path: str, png_path: str):
    from PIL import Image

    img = Image.open(webp_path)
    img.save(png_path)


def get_android_bin_arch(device_arch: str):
    if "64" in device_arch:
        return "aarch64"
    elif "hf" in device_arch or "v7" in device_arch:
        return "armhf"
    else:
        raise ValueError("Unable to translate device arch %s to bin arch" % device_arch)


def start_daemon_thread(target, args=(), kwargs={}):
    import threading

    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread


def wait_for_all_threads(threads: list):
    for t in threads:
        t.join()


def format_keyvalue(data: dict):
    ret = []
    for k, v in data.items():
        it = "%s=%s" % (k, v)
        ret.append(it)
    ret = ", ".join(ret)
    return ret


def get_first_laddr_port_with_pid(pid: int):
    # used for finding scrcpy local control port
    import psutil

    conns = psutil.net_connections()
    conns = [it for it in conns if it.pid == pid]
    if len(conns) > 0:
        laddr = conns[0].laddr
        ret = getattr(laddr, "port", None)
        return ret


def parse_dumpsys_active_apps(text: str):
    ret = {"foreground": [], "focused": []}
    lines = grep_lines(text, ["ResumedActivity"])
    # print("Lines:", lines)
    for it in lines:
        if it.startswith("ResumedActivity:"):
            ret["focused"].append(extract_app_id_from_activity_record(it))
        elif it.startswith("topResumedActivity="):
            ret["foreground"].append(extract_app_id_from_activity_record(it))
    # print("Ret:", ret)
    return ret


def extract_app_id_from_activity_record(text: str, return_original_on_failure=True):
    items = text.replace("/", "/ /").split()
    for it in items:
        it = it.strip()
        if it.endswith("/"):
            return it[:-1]
    if return_original_on_failure:
        return text


def parse_display_focus(lines: list[str]):
    ret = {}
    display_id = None
    for it in lines:
        if it.startswith("Display:"):
            display_id = it.split()[1]
            if "mDisplayId" in display_id:  # hope this format won't change?
                display_id = display_id.split("=")[1]
                display_id = int(display_id)
            else:
                display_id = None
        elif it.startswith("mFocusedApp="):
            if "ActivityRecord" in it:
                if display_id is not None:
                    focused_app = extract_app_id_from_activity_record(it)
                    ret[display_id] = focused_app
    return ret


def split_lines(text: str) -> list[str]:
    ret = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            ret.append(line)
    return ret


def grep_lines(
    text: str, whitelist: list[str] = [], blacklist: list[str] = []
) -> list[str]:
    ret = []
    for line in split_lines(text):
        if whitelist and not any(wh in line for wh in whitelist):
            continue
        if blacklist and any(bl in line for bl in blacklist):
            continue
        ret.append(line)
    return ret


def parse_dumpsys_keyvalue_output(output: str):
    lines = output.splitlines()
    ret = {}
    for line in lines:
        line = line.strip()
        if line:
            key, value = line.split("=", 1)
            ret[key.strip()] = value.strip()
    return ret


def suggest_closest_commands(
    possible_commands: list[dict], user_input: str, limit: int
):
    import warnings

    warnings.filterwarnings(
        "ignore"
    )  # so that we don't have to install fuzzywuzzy[speedup] or python-Levenshtein
    from fuzzywuzzy import fuzz

    assert limit >= 1, "Limit must be greater than zero, given %s" % limit
    ret = possible_commands.copy()
    ret.sort(
        key=lambda x: -fuzz.token_sort_ratio(
            user_input,
            x["matcher"],
        )
    )
    # print("Sorted:", ret)
    ret = [it["display"] for it in ret[:limit]]
    return ret


def remove_option_variable(option: str):
    words = option.split(" ")
    ret = []
    for it in words:
        it = it.strip()
        if it:
            if it[0] not in "([<":
                ret.append(it)
    ret = " ".join(ret)
    return ret


def extract_possible_commands_from_doc():
    assert DOCSTRING, "No docstring found"
    lines = DOCSTRING.split("\n")
    lines = [it.strip() for it in lines]
    ret = [
        dict(matcher=remove_option_variable(it), display=it)
        for it in lines
        if it.startswith("swm ")
    ]
    return ret


def show_suggestion_on_wrong_command(user_input: str, limit: int = 1):
    # print("User input:", user_input)
    possible_commands = extract_possible_commands_from_doc()
    # print("Possible commands:", possible_commands)
    closest_commands = suggest_closest_commands(
        possible_commands=possible_commands, user_input=user_input, limit=limit
    )
    print("Did you mean:", *closest_commands, sep="\n  ")


def get_init_complete_path(basedir: str):
    init_flag = os.path.join(basedir, ".INITIAL_BINARIES_DOWNLOADED")
    return init_flag


def check_init_complete(basedir: str):
    init_flag = get_init_complete_path(basedir)
    return os.path.exists(init_flag)


def test_best_github_mirror(mirror_list: list[str], timeout: float):
    results = []
    for it in mirror_list:
        success, duration = test_internet_connectivity(it, timeout)
        results.append((success, duration, it))
    results = list(filter(lambda x: x[0], results))
    results.sort(key=lambda x: x[1])

    if len(results) > 0:
        return results[0][2]
    else:
        return None


def test_internet_connectivity(url: str, timeout: float):
    import requests

    try:
        response = requests.get(url, verify=False, timeout=timeout)
        return response.status_code == 200, response.elapsed.total_seconds()
    except:
        return False, -1


def download_initial_binaries(basedir: str, mirror_list: list[str], force=False):
    import pathlib

    init_flag = get_init_complete_path(basedir)
    if not force:
        if check_init_complete(basedir):
            print("Initialization complete")
            return
    else:
        print("Performing force init")
    github_mirror = test_best_github_mirror(mirror_list, timeout=5)
    print("Using mirror: %s" % github_mirror)
    baseurl = "%s/James4Ever0/swm/releases/download/bin/" % github_mirror
    pc_os_arch = (
        "%s-%s" % get_system_and_architecture()
    )  # currently, linux only. let's be honest.
    print("Your PC OS and architecture: %s" % pc_os_arch)
    download_files = [
        "android-binaries.zip",
        "java-jar.zip",
        "apk.zip",
        "pc-binaries-%s.zip" % pc_os_arch,
    ]
    # now download and unzip all zip files to target directory
    for it in download_files:
        url = baseurl + it
        print("Downloading %s" % url)
        download_and_unzip(url, basedir)
    if os.name == "posix":
        print("Making PC binaries executable")
        subprocess.run(["chmod", "-R", "+x", os.path.join(basedir, "pc-binaries")])
    print("All binaries downloaded")
    pathlib.Path(init_flag).touch()


def convert_unicode_escape(input_str):
    # Extract the hex part after 'u+'
    hex_str = input_str[2:]
    # Convert hex string to integer and then to Unicode character
    return chr(int(hex_str, 16))


def split_args(args_str: str):
    splited_args = args_str.split()
    ret = []
    for it in splited_args:
        it = it.strip()
        if it:
            ret.append(it)
    return ret


def encode_base64_str(data: str):
    import base64

    encoded_bytes = base64.b64encode(data.encode("utf-8"))
    encoded_str = encoded_bytes.decode("utf-8")
    return encoded_str


# TODO: use logger
# import structlog
# import loguru

# TODO: init app with named config

# TODO: put manual configuration into first priority, and we should only take care of those would not be manually done (like unicode input)
# TODO: create github pages for swm

# TODO: Create an app config template repo, along with all other devices, pcs, for easy initialization

# TODO: override icon with SCRCPY_ICON_PATH=<app_icon_path>

# TODO: not allowing exiting the app in the new display, or close the display if the app is exited, or reopen the app if exited

# TODO: configure app with the same id to use the same app config or separate by device

# TODO: write wiki about enabling com.android.shell for root access in kernelsu/magisk
# TODO: use a special apk for running SWM specific root commands instead of direct invocation of adb root shell

# TODO: monitor the output of scrcpy and capture unicode char input accordingly, for sending unicode char to the adbkeyboard


class OldInstanceRunning(AssertionError): ...


class NoDeviceError(ValueError): ...


class NoSelectionError(ValueError): ...


class NoConfigError(ValueError): ...


class NoAppError(ValueError): ...


class NoBaseConfigError(ValueError): ...


class NoDeviceConfigError(ValueError): ...


class NoDeviceAliasError(ValueError): ...


class NoDeviceNameError(ValueError): ...


class NoDeviceIdError(ValueError): ...


class DeviceOfflineError(ValueError): ...


def prompt_for_option_selection(
    options: List[str], prompt: str = "Select an option: "
) -> str:
    while True:
        print(prompt)
        for i, option in enumerate(options):
            print(f"{i + 1}. {option}")
        try:
            user_input = input("Enter your choice: ")
            if user_input in options:
                return user_input
            selection = int(user_input)
            if 1 <= selection <= len(options):
                return options[selection - 1]
        except ValueError:
            pass


def reverse_text(text):
    return "".join(reversed(text))


def spawn_and_detach_process(cmd: List[str]):
    return subprocess.Popen(cmd, start_new_session=True)


def parse_scrcpy_app_list_output_single_line(text: str):
    ret = {}
    text = text.strip()

    package_type_symbol, rest = text.split(" ", maxsplit=1)

    reversed_text = reverse_text(rest)

    ret["type_symbol"] = package_type_symbol

    package_id_reverse, rest = reversed_text.split(" ", maxsplit=1)

    package_id = reverse_text(package_id_reverse)
    ret["id"] = package_id

    package_alias = reverse_text(rest).strip()

    ret["alias"] = package_alias
    return ret


def select_editor():
    import shutil

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


# TODO: download nano editor binary, use it to edit files despite the operate system
# TODO: find a pure python text editor in textualize, or a package for this purpose, or write one
def edit_file(filepath: str, editor_binpath: str):
    execute_subprogram(editor_binpath, [filepath])


def edit_content(content: str):
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
        tmpfile.write(content)
        tmpfile.flush()
        tmpfile_path = tmpfile.name
        edited_content = edit_or_open_file(tmpfile_path, return_value="content")
        assert type(edited_content) == str
        return edited_content


def edit_or_open_file(filepath: str, return_value="edited"):
    print("Editing file:", filepath)
    content_before_edit = get_file_content(filepath)
    editor_binpath = select_editor()
    if editor_binpath:
        edit_file(filepath, editor_binpath)
    else:
        open_file_with_default_application(filepath)
    content_after_edit = get_file_content(filepath)
    edited = content_before_edit != content_after_edit
    if edited:
        print("File has been edited.")
    else:
        print("File has not been edited.")
    if return_value == "edited":
        return edited
    elif return_value == "content":
        return content_after_edit
    else:
        raise ValueError("Unknown return value:", return_value)


def open_file_with_default_application(filepath: str):
    import shutil

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
    import tempfile
    import requests
    import zipfile

    # Create extraction directory if it doesn't exist
    os.makedirs(extract_dir, exist_ok=True)

    # Stream download to a temporary file
    with requests.get(url, stream=True, allow_redirects=True, verify=False) as response:
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
    if arch == "x64":
        arch = "x86_64"
    elif arch == "arm64":
        arch = "aarch64"
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
    import json

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
    cache_dir: str, bin_name: str, bin_type: str
) -> str:
    import shutil

    # Adjust binary name for platform
    bin_env_name = bin_name.upper()
    platform_specific_name = bin_name.lower()

    if platform.system() == "Windows":
        platform_specific_name += ".exe"

    # 1. Check environment variable
    env_path = os.environ.get(bin_env_name)
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Check in cache directory
    cache_path = os.path.join(cache_dir, "pc-binaries", platform_specific_name)
    if os.path.exists(cache_path):
        return cache_path

    # 3. Check in PATH
    path_path = shutil.which(platform_specific_name)
    if path_path:
        return path_path

    # 4. Not found anywhere - attempt to download
    return download_binary_into_cache_dir_and_return_path(
        cache_dir, bin_name=bin_name, bin_type=bin_type
    )


def download_binary_into_cache_dir_and_return_path(
    cache_dir: str, bin_type: str, bin_name: str
) -> str:

    raise NotImplementedError(
        "Downloading is not implemented yet for %s-%s-%s"
        % (*get_system_and_architecture(), bin_name)
    )

    bin_dir = os.path.join(cache_dir, bin_type)
    os.makedirs(bin_dir, exist_ok=True)

    # For demonstration purposes, we'll just create an empty file
    bin_path = os.path.join(bin_dir, bin_name)
    if platform.system() == "Windows":
        bin_path += ".exe"

    if platform.system() != "Windows":
        os.chmod(bin_path, 0o755)

    return bin_path


class ADBStorage(Storage):
    def __init__(self, filename, adb_wrapper: "AdbWrapper", enable_read_cache=True):
        self.filename = filename
        self.adb_wrapper = adb_wrapper
        adb_wrapper.create_file_if_not_exists(self.filename)
        self.enable_read_cache = enable_read_cache
        self.read_cache = None
        self.write_cache = None

    def read(self):
        import json

        try:
            if self.enable_read_cache:
                if self.read_cache is None:
                    content = self.adb_wrapper.read_file(self.filename)
                    self.read_cache = content
                else:
                    content = self.read_cache
            else:
                content = self.adb_wrapper.read_file(self.filename)
            data = json.loads(content)
            return data
        except json.JSONDecodeError:
            return None

    def write(self, data):
        import json

        content = json.dumps(data)
        self.write_cache = content
        if self.enable_read_cache:
            self.read_cache = content
    
    def flush(self):
        if self.write_cache:
            self.adb_wrapper.write_file(self.filename, self.write_cache)

    def close(self):
        self.flush()
        pass


class SWMOnDeviceDatabase:
    def __init__(self, db_path: str, adb_wrapper: "AdbWrapper"):
        import functools

        self.db_path = db_path
        self.storage = functools.partial(ADBStorage, adb_wrapper=adb_wrapper)
        assert type(adb_wrapper.device) == str
        self.device_id = adb_wrapper.device
        self._db = TinyDB(db_path, storage=self.storage)
    
    def flush(self):
        self._db.storage.flush() # type: ignore

    def write_previous_ime(self, previous_ime: str):
        PreviousIme = Query()
        device_id = self.device_id
        self._db.table("previous_ime").upsert(
            dict(device_id=device_id, previous_ime=previous_ime),
            (PreviousIme.device_id == device_id),
        )
        self.flush()

    def read_previous_ime(self):
        PreviousIme = Query()
        device_id = self.device_id

        # Search for matching document
        result = self._db.table("previous_ime").get(
            (PreviousIme.device_id == device_id)
        )
        # Return datetime object if found, None otherwise

        if result:
            assert type(result) == Document
            ret = result["previous_ime"]
            assert type(ret) == str
            return ret

    def write_app_last_used_time(
        self, device_id, app_id: str, last_used_time: datetime
    ):
        AppUsage = Query()

        # Upsert document: update if exists, insert otherwise
        self._db.table("app_usage").upsert(
            {
                "device_id": device_id,
                "app_id": app_id,
                "last_used_time": last_used_time.isoformat(),
            },
            (AppUsage.device_id == device_id) & (AppUsage.app_id == app_id),
        )

    def update_app_last_used_time(self, device_id: str, app_id: str):
        last_used_time = datetime.now()
        self.write_app_last_used_time(device_id, app_id, last_used_time)
        self.flush()

    def get_app_last_used_time(self, device_id, app_id: str) -> Optional[datetime]:
        AppUsage = Query()

        # Search for matching document
        result = self._db.table("app_usage").get(
            (AppUsage.device_id == device_id) & (AppUsage.app_id == app_id)
        )
        # Return datetime object if found, None otherwise

        if result:
            assert type(result) == Document
            return datetime.fromisoformat(result["last_used_time"])


class SWM:
    def __init__(self, config: omegaconf.DictConfig):
        self.config = config
        self.cache_dir = config.cache_dir
        self.bin_dir = os.path.join(self.cache_dir, "bin")
        os.makedirs(self.bin_dir, exist_ok=True)

        # Initialize binaries
        self.adb = self._get_binary("adb", "pc-binaries")
        self.scrcpy = self._get_binary("scrcpy", "pc-binaries")
        self.fzf = self._get_binary("fzf", "pc-binaries")

        # Initialize components
        self.adb_wrapper = AdbWrapper(self.adb, self.config)
        self.scrcpy_wrapper = ScrcpyWrapper(self.scrcpy, self)
        self.fzf_wrapper = FzfWrapper(self.fzf)

        # Initialize attributes
        self.current_device = None
        self.on_device_db = None

        # Initialize managers
        self.app_manager = AppManager(self)
        self.session_manager = SessionManager(self)
        self.device_manager = DeviceManager(self)
        self.ime_manager = ImeManager(self)
        self.java_manager = JavaManager(self)
        self.termux_manager = TermuxManager(self)

    def healthcheck(self):
        print("Warning: Healthcheck is not implemented yet.")
        ...

    def repl(self):
        print("Warning: REPL mode is not implemented yet.")
        ...

    @property
    def local_icon_dir(self):
        assert self.current_device
        ret = os.path.join(self.cache_dir, "icons", self.current_device)
        os.makedirs(ret, exist_ok=True)
        return ret

    @property
    def fingerprint(self):
        import uuid

        if os.path.exists(self._fingerprint_path):
            with open(self._fingerprint_path, "r") as f:
                return f.read()
        else:
            ret = str(uuid.uuid4())
            with open(self._fingerprint_path, "w+") as f:
                f.write(ret)
            return ret

    @property
    def _fingerprint_path(self):
        return os.path.join(self.cache_dir, ".fingerprint")

    @property
    def _trusted_fingerprints_path(self):
        return os.path.join(self.cache_dir, ".trusted_fingerprints")

    def trust_fingerprint(self, fingerprint: str):
        with open(self._trusted_fingerprints_path, "a+") as f:
            f.write(fingerprint + "\n")

    def check_fingerprint_trusted(self, fingerprint: str):
        trusted_fingerprints = self.list_trusted_fingerprints()
        ret = fingerprint in trusted_fingerprints
        return ret

    def list_trusted_fingerprints(self):
        ret = []
        if os.path.exists(self._trusted_fingerprints_path):
            with open(self._trusted_fingerprints_path, "r") as f:
                contents = f.read()
                ret = split_lines(contents)
        return ret

    def load_swm_on_device_db(self):
        db_path = os.path.join(self.config.android_session_storage_path, "db.json")
        self.on_device_db = SWMOnDeviceDatabase(db_path, self.adb_wrapper)

    def _get_binary(self, name: str, bin_type: str) -> str:
        return search_or_obtain_binary_path_from_environmental_variable_or_download(
            self.cache_dir, name, bin_type
        )

    def set_current_device(self, device_id: str):
        self.current_device = device_id
        self.adb_wrapper.set_device(device_id)
        self.scrcpy_wrapper.set_device(device_id)

        self.scrcpy_wrapper.cleanup_scrcpy_proc_pid_files()
        self.adb_wrapper.stay_awake_while_plugged_in()

        # now check for android version
        self.check_android_version()

    def check_android_version(self):
        # multi display: 8
        # ref: https://stackoverflow.com/questions/63333696/which-is-the-first-version-of-android-that-support-multi-display
        # multi display with different resolution: 9
        # ref: https://source.android.com/docs/core/display/multi_display/displays
        minimum_android_version_for_multi_displays = 10  # from source code of scrcpy
        android_version = self.adb_wrapper.get_android_version()
        print("Android version:", android_version)
        device_arch = self.adb_wrapper.get_device_architecture()
        print("Device architecture:", device_arch)
        if android_version < minimum_android_version_for_multi_displays:
            raise RuntimeError(
                "Android version must be %s or higher"
                % minimum_android_version_for_multi_displays
            )

    def get_device_architecture(self) -> str:
        return self.adb_wrapper.get_device_architecture()

    def infer_current_device(self, default_device: str):
        all_devices = self.adb_wrapper.list_device_ids()
        if len(all_devices) == 0:
            # no devices.
            print("No online device")
            return
        elif len(all_devices) == 1:
            # only one device.
            device = all_devices[0]
            if default_device is None:
                print(
                    "No device specified in config, using the only device online (%s)"
                    % device
                )
            elif device != default_device:
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
                if default_device is None:
                    print("No device specified in config, please select one.")
                else:
                    print(
                        "Device selected by config (%s) is not online, please select one."
                        % default_device
                    )
                prompt_for_device = f"Select a device from: "
                # TODO: input numbers or else
                # TODO: show detailed info per device, such as device type, last swm use time, alias, device model, android info, etc...
                selected_device = prompt_for_option_selection(
                    all_devices, prompt_for_device
                )
                return selected_device


def load_and_print_as_dataframe(
    list_of_dict, drop_fields={}, show=True, sort_columns=True
):
    import pandas

    df = pandas.DataFrame(list_of_dict)
    if sort_columns:
        sorted_columns = sorted(df.columns)

        # Reindex the DataFrame with the sorted column order
        df = df[sorted_columns]
    for key, value in drop_fields.items():
        if value is False:
            df.drop(key, axis=1, inplace=True)
    if "last_used_time" in df.columns:
        df["last_used_time"] = df["last_used_time"].transform(
            lambda x: x.strftime("%Y-%m-%d %H:%M")
        )
    formatted_output = df.to_string(index=False)
    if show:
        print(formatted_output)
    return formatted_output


class AppManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.config = swm.config
    
    def list_recent_apps(self, print_formatted=False):

        ret = self.swm.adb_wrapper.list_recent_apps()
        
        if print_formatted:
            load_and_print_as_dataframe(ret)
        return ret

    def resolve_app_main_activity(self, app_id: str):
        # adb shell cmd package resolve-activity --brief <PACKAGE_NAME> | tail -n 1
        cmd = [
            "bash",
            "-c",
            "cmd package resolve-activity --brief %s | tail -n 1" % app_id,
        ]
        output = self.swm.adb_wrapper.check_output_shell(cmd).strip()
        return output

    def start_app_in_given_display(self, app_id: str, display_id: int):
        # adb shell am start --display <DISPLAY_ID> -n <PACKAGE/ACTIVITY>
        app_main_activity = self.resolve_app_main_activity(app_id)
        self.swm.adb_wrapper.execute_shell(
            ["am", "start", "--display", str(display_id), "-n", app_main_activity]
        )

    def resolve_app_query(self, query: str):
        ret = query
        if not self.check_app_existance(query):
            # this is definitely a query
            ret = self.search(index=False, query=query)
        return ret

    # let's mark it rooted device only.
    # we get the package path, data path and get last modification date of these files
    # or use java to access UsageStats
    def get_app_last_used_time_from_device(self, app_id: str):
        data_path = "/data/data/%s" % app_id
        if self.swm.adb_wrapper.test_path_existance_su(data_path):
            cmd = "ls -Artls '%s' | tail -n 1 | awk '{print $7,$8}'" % data_path
            last_used_time = self.swm.adb_wrapper.check_output_su(cmd).strip()
            # format: 2022-12-31 12:00
            last_used_time = datetime.strptime(last_used_time, "%Y-%m-%d %H:%M")
            return last_used_time

    def get_app_last_used_time_from_db(self, package_id: str):
        assert self.swm.on_device_db
        device_id = self.swm.current_device
        last_used_time = self.swm.on_device_db.get_app_last_used_time(
            device_id, package_id
        )
        return last_used_time

    def write_app_last_used_time_to_db(self, package_id: str, last_used_time: datetime):
        assert self.swm.on_device_db
        device_id = self.swm.current_device
        self.swm.on_device_db.write_app_last_used_time(
            device_id, package_id, last_used_time
        )

    def search(self, index: bool, query: Optional[str] = None):
        apps = self.list()
        items = []
        for i, it in enumerate(apps):
            line = f"{it['alias']}\t{it['id']}"
            if index:
                line = f"[{i+1}]\t{line}"
            items.append(line)
        selected = self.swm.fzf_wrapper.select_item(items, query=query)
        if selected:
            package_id = selected.split("\t")[-1]
            return package_id
        else:
            return None

    def list(
        self,
        most_used: Optional[int] = None,
        print_formatted: bool = False,
        update_cache=False,
        drop_fields: dict[str, bool] = {},
        update_last_used=False,
    ):
        if update_last_used:
            self.update_all_app_last_used_time()
        if most_used:
            apps = self.list_most_used_apps(most_used, update_cache=update_cache)
        else:
            apps = self.list_all_apps(update_cache=update_cache)

        if print_formatted:
            load_and_print_as_dataframe(apps, drop_fields=drop_fields)

        return apps

    def retrieve_app_icon(self, package_id: str, icon_path: str):
        self.swm.adb_wrapper.retrieve_app_icon(package_id, icon_path)

    def build_window_title(self, package_id: str):
        # TODO: set window title as "<device_name> - <app_name>"
        # --window-title=<title>
        device_id = self.swm.adb_wrapper.device
        device_name = self.swm.adb_wrapper.get_device_name(device_id)
        # TODO: make the window title format configurable
        # app_name = package_id
        app_name = self.swm.adb_wrapper.get_app_name(package_id)
        return "%s - %s" % (app_name, device_name)

    def check_app_existance(self, app_id):
        return self.swm.adb_wrapper.check_app_existance(app_id)

    def check_clipboard_malfunction(self):
        display_and_lock_state = self.swm.adb_wrapper.get_display_and_lock_state()
        print("Display and lock state: %s" % display_and_lock_state)
        clipboard_may_malfunction = False
        if "_locked" in display_and_lock_state:
            clipboard_may_malfunction = True
            print("Device is locked")
        if "off_" in display_and_lock_state:
            clipboard_may_malfunction = True
            print("Main display is off")  # TODO: fix false nagative
            # mHoldingWakeLockSuspendBlocker=false
            # mHoldingDisplaySuspendBlocker=true
        if display_and_lock_state == "unknown":
            clipboard_may_malfunction = True
            print("Warning: Device display and lock state unknown")
        if clipboard_may_malfunction:
            print("Warning: Clipboard may malfunction")
        return clipboard_may_malfunction

    def get_app_config(self, config_name: str):
        assert self.check_app_config_existance(config_name)
        app_config = self.get_or_create_app_config(config_name)
        return app_config

    def run(
        self,
        app_id: str,
        init_config: Optional[str] = None,
        new_display: bool = True,
    ):
        # TODO: recreate the scrcpy instance if it is exited abnormally, such as app closed on device
        import traceback

        self.check_clipboard_malfunction()
        if not self.check_app_existance(app_id):
            raise NoAppError(
                "Applicaion %s does not exist on device %s"
                % (app_id, self.swm.current_device)
            )
        # TODO: memorize the last scrcpy run args, by default in swm config
        # Get app config
        env = {}
        if init_config:
            app_config = self.get_app_config(init_config)
        else:
            app_config = self.get_or_create_app_config(app_id)
        ime_preference = app_config.get("ime_preference", "adbkeyboard")
        # use_adb_keyboard =app_config.get("use_adb_keyboard", False)
        self.ime_preference = ime_preference

        if app_config.get("retrieve_app_icon", False):
            icon_path = os.path.join(self.swm.local_icon_dir, "%s.png" % app_id)
            # try:
            if not os.path.exists(icon_path):
                self.retrieve_app_icon(app_id, icon_path)
            env["SCRCPY_ICON_PATH"] = icon_path
            # except:
            #     traceback.print_exc() # TODO: print traceback only if verbose mode is on
            #     print("Failed to retrieve app icon for:", app_id)
        # Add window config if exists
        # print("Env:", env)
        win = app_config.get("window", None)

        scrcpy_args = []

        # if scrcpy_args is None:
        #     scrcpy_args = app_config.get("scrcpy_args", None)

        title = self.build_window_title(app_id)

        # Write last used time to db
        self.update_app_last_used_time_to_db(app_id)
        # Execute scrcpy
        self.swm.scrcpy_wrapper.launch_app(
            app_id,
            init_config=init_config,
            window_params=win,
            scrcpy_args=scrcpy_args,
            title=title,
            new_display=new_display,
            # use_adb_keyboard=use_adb_keyboard,
            ime_preference=ime_preference,
            env=env,
        )

    def update_app_last_used_time_to_db(self, app_id: str):
        # we cannot update the last used time at device, since it is managed by android
        assert self.swm.current_device, "No current device being set"
        assert self.swm.on_device_db, (
            "Device '%s' missing on device db" % self.swm.current_device
        )
        device_id = self.swm.current_device
        self.swm.on_device_db.update_app_last_used_time(device_id, app_id)

    def edit_app_config(self, app_name: str) -> bool:
        # return True if edited, else False
        print(f"Editing config for {app_name}")
        app_config_path = self.get_app_config_path(app_name)
        self.get_or_create_app_config(app_name)
        content = self.swm.adb_wrapper.read_file(app_config_path)
        edited_content = edit_content(content)
        ret = edited_content != content
        if ret:
            self.swm.adb_wrapper.write_file(app_config_path, edited_content)
        assert type(ret) == bool
        return ret

    def copy_app_config(self, source_name: str, target_name: str):
        if target_name == "default":
            raise ValueError("Target name cannot be 'default'")
        if self.check_app_config_existance(target_name):
            raise ValueError("Target '%s' still exists. Consider using reference?")

        if source_name == "default":
            config_yaml_content = self.default_app_config
        elif source_name in self.list_app_config(print_result=False):
            source_config_path = self.get_app_config_path(source_name)

            config_yaml_content = self.swm.adb_wrapper.read_file(source_config_path)
        else:
            raise ValueError("Source '%s' does not exist" % source_name)

        target_config_path = self.get_app_config_path(target_name)
        self.swm.adb_wrapper.write_file(target_config_path, config_yaml_content)

    def list_app_config(self, print_result: bool):
        # display config name, categorize them into two groups: default and custom
        # you may configure the default config of an app to use a custom config
        # both default and custom one could be referred in default config, but custom config cannot refer others
        # if one default config is being renamed as custom config, then all reference shall be flattened
        app_config_yamls = self.swm.adb_wrapper.listdir(self.app_config_dir)
        app_config_names = [
            os.path.splitext(it)[0] for it in app_config_yamls if it.endswith(".yaml")
        ]
        if print_result:
            self.display_app_config(app_config_names)
        return app_config_names

    def display_app_config(self, app_config_names: List[str]):
        import pandas

        records = []
        for it in app_config_names:
            app_exists = self.check_app_existance(it)
            if app_exists:
                _type = "app"
            else:
                _type = "custom"
            rec = dict(name=it, type=_type)
            records.append(rec)
        df = pandas.DataFrame(records)
        # now display this dataframe
        print(df.to_string(index=False))

    def show_app_config(self, app_name: str):
        config = self.get_or_create_app_config(app_name)
        print(pretty_print_json(config))

    @property
    def app_config_dir(self):
        device_id = self.swm.current_device
        assert device_id
        ret = os.path.join(
            self.swm.config.android_session_storage_path, "app_config"
        )  # TODO: had better to separate devices, though. could add suffix to config name, in order to share config
        return ret

    def get_app_config_path(self, app_name: str):
        app_config_dir = self.app_config_dir
        self.swm.adb_wrapper.ensure_dir_existance(app_config_dir)

        app_config_path = os.path.join(app_config_dir, f"{app_name}.yaml")
        return app_config_path

    def check_app_config_existance(self, config_name: str):
        config_path = self.get_app_config_path(config_name)
        ret = self.swm.adb_wrapper.test_path_existance(config_path)
        return ret

    def resolve_app_config_reference(
        self, ref: str, sources: List[str] = []
    ):  # BUG: if you mark List as "list" it will be resolved into class method "list"
        if ref == "default":
            raise ValueError("Reference cannot be 'default'")
        if ref in sources:
            raise ValueError("Loop reference found for %s in %s" % (ref, sources))
        # this ref must exists
        assert ref in self.list_app_config(print_result=False), (
            "Reference %s does not exist" % ref
        )
        ret = self.get_or_create_app_config(ref, resolve_reference=False)
        ref_in_ref = ret.get("reference", None)
        if ref_in_ref:
            ret = self.resolve_app_config_reference(
                ref=ref_in_ref, sources=sources + [ref]
            )
        return ret

    def get_or_create_app_config(self, app_name: str, resolve_reference=True) -> Dict:
        import yaml

        default_config_obj = yaml.safe_load(self.default_app_config)

        if app_name == "default":  # not creating it
            return default_config_obj

        app_config_path = self.get_app_config_path(app_name)

        if not self.swm.adb_wrapper.test_path_existance(app_config_path):
            print("Creating default config for app:", app_name)
            # Write default YAML template with comments
            self.swm.adb_wrapper.write_file(app_config_path, self.default_app_config)
            return default_config_obj

        yaml_content = self.swm.adb_wrapper.read_file(app_config_path)
        ret = yaml.safe_load(yaml_content)
        if resolve_reference:
            ref = ret.get("reference", None)
            if ref:
                ret = self.resolve_app_config_reference(ref, sources=[app_name])
        return ret

    # TODO: re-ensure ime preference (activate gboard or adbkeyboard) when the app is focused, to deal with different ime settings per app

    @property
    def default_app_config(self):
        return """# Application configuration template
# All settings are optional - uncomment and modify as needed

# uncomment the below line for using custom config
# reference: <custom_config_name>

# notice, if you reference any config here, the below settings will be ignored

# arguments passed to scrcpy
scrcpy_args: []

# install and enable adb keyboard, useful for using PC input method when multi-tasking (deprecated)
# use_adb_keyboard: true

# ime preference, can be "adbkeyboard", "gboard", "uhid", "plain", "hide", default is "adbkeyboard"
ime_preference: "adbkeyboard"

# retrieve and display app icon instead of the default scrcpy icon
retrieve_app_icon: true
"""

    def save_app_config(self, app_name: str, config: Dict):
        import yaml

        app_config_path = self.get_app_config_path(app_name)
        with open(app_config_path, "w") as f:
            yaml.safe_dump(config, f)
    
    def flush_device_db(self):
        self.swm.on_device_db.flush()
            
    def update_all_app_last_used_time(self):
        if not hasattr(self, "all_app_last_used_time_updated"):
            all_app_usage_stats = self.swm.adb_wrapper.list_app_last_visible_time()
            for it in all_app_usage_stats:
                # TODO: bulk update, improve tinydb i/o speed, separate read from commit
                app_id = it["app_id"]
                last_visible_time = it['lastTimeVisible']
                self.write_app_last_used_time_to_db(app_id, last_visible_time)
            self.flush_device_db()
            setattr(self, "all_app_last_used_time_updated", True)

    def list_all_apps(self, update_cache=False) -> List[dict[str, str]]:
        # package_ids = self.swm.adb_wrapper.list_packages()
        (
            package_list,
            cache_expired,
        ) = self.swm.scrcpy_wrapper.load_package_id_and_alias_cache()
        if update_cache or cache_expired:
            package_list = self.swm.scrcpy_wrapper.list_package_id_and_alias()
            self.swm.scrcpy_wrapper.save_package_id_and_alias_cache(package_list)
        assert type(package_list) == list

        if update_cache:
            self.update_all_app_last_used_time()


        for it in package_list:
            package_id = it["id"]
            if update_cache:
                last_used_time = self.get_app_last_used_time_from_device(package_id)
                if last_used_time is None:
                    last_used_time = self.get_app_last_used_time_from_db(package_id)
                else:
                    # update db
                    self.write_app_last_used_time_to_db(package_id, last_used_time)
            else:
                last_used_time = self.get_app_last_used_time_from_db(package_id)
                if last_used_time is None:
                    last_used_time = self.get_app_last_used_time_from_device(package_id)
                    if last_used_time is not None:
                        # update db
                        self.write_app_last_used_time_to_db(package_id, last_used_time)
            if last_used_time is None:
                last_used_time = datetime.fromtimestamp(0)
            it["last_used_time"] = last_used_time
        self.flush_device_db()
        return package_list

    def list_most_used_apps(
        self, limit: int, update_cache=False
    ) -> List[dict[str, Any]]:
        # Placeholder implementation
        all_apps = self.list_all_apps(update_cache=update_cache)
        all_apps.sort(key=lambda x: -x["last_used_time"].timestamp())  # type: ignore
        selected_apps = all_apps[:limit]
        return selected_apps


# TODO: manual specification instead of automatic
# TODO: specify pc display size in session config
class SessionManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.adb_wrapper = swm.adb_wrapper
        self.config = swm.config
        self.session_dir = os.path.join(
            swm.config.android_session_storage_path, "sessions"
        )  # remote path
        self.swm.adb_wrapper.execute(
            ["shell", "mkdir", "-p", self.session_dir], check=False
        )

    @property
    def template_session_config(self):
        print(
            "Warning: 'template_session_config' has not been implemented, returning placeholder instead."
        )
        return """
# Session template config
# Uncomment any options below and begin customization
"""

    def resolve_session_query(self, query: str):
        if query in self.list():
            return query
        else:
            return self.search(query)

    def get_swm_window_params(self) -> List[Dict[str, Any]]:
        windows = self.get_all_window_params()
        windows = [it for it in windows if it["title"].startswith("[SWM]")]
        return windows

    def get_all_window_params(self) -> List[Dict[str, Any]]:
        os_type = platform.system()
        if os_type == "Linux":
            if not self._is_wmctrl_installed():
                print("Please install wmctrl to manage windows on Linux.")
                return []
            return self._get_windows_linux()
        elif os_type == "Windows":
            return self._get_windows_windows()
        elif os_type == "Darwin":
            return self._get_windows_macos()
        else:
            print(f"Unsupported OS: {os_type}")
            return []

    def _is_wmctrl_installed(self) -> bool:
        try:
            subprocess.run(
                ["wmctrl", "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _get_windows_linux(self) -> List[Dict[str, Any]]:
        try:
            output = subprocess.check_output(["wmctrl", "-lGx"]).decode("utf-8")
            windows = []
            for line in output.splitlines():
                parts = line.split(maxsplit=6)
                if len(parts) < 7:
                    continue
                desktop_id = parts[1]
                pid = parts[2]
                x, y, width, height = map(int, parts[3:7])
                title = parts[6]
                windows.append(
                    {
                        "title": title,
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "desktop_id": desktop_id,
                        "pid": pid,
                    }
                )
            return windows
        except Exception as e:
            print(f"Error getting windows on Linux: {e}")
            return []

    def _get_windows_windows(self) -> List[Dict[str, Any]]:
        try:
            import pygetwindow as gw

            windows = []
            for win in gw.getAllWindows():
                title = win.title
                windows.append(
                    {
                        "title": title,
                        "x": win.left,
                        "y": win.top,
                        "width": win.width,
                        "height": win.height,
                        "is_maximized": win.isMaximized,
                        "hwnd": win._hWnd,
                    }
                )
            return windows
        except ImportError:
            print("Please install pygetwindow: pip install pygetwindow")
            return []
        except Exception as e:
            print(f"Error getting windows on Windows: {e}")
            return []

    def _get_windows_macos(self) -> List[Dict[str, Any]]:
        try:
            from AppKit import NSWorkspace

            windows = []
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.isActive():
                    app_name = app.localizedName()
                    windows.append({"title": app_name, "pid": app.processIdentifier()})
            return windows
        except ImportError:
            print("macOS support requires PyObjC. Install with: pip install pyobjc")
            return []
        except Exception as e:
            print(f"Error getting windows on macOS: {e}")
            return []

    def move_window_to_position(self, window_title: str, window_params: Dict[str, Any]):
        os_type = platform.system()
        if os_type == "Linux":
            self._move_window_linux(window_title, window_params)
        elif os_type == "Windows":
            self._move_window_windows(window_title, window_params)
        elif os_type == "Darwin":
            self._move_window_macos(window_title, window_params)
        else:
            print(f"Unsupported OS: {os_type}")

    def _move_window_linux(self, window_title: str, window_params: Dict[str, Any]):
        if not self._is_wmctrl_installed():
            print("wmctrl not installed. Cannot move window.")
            return
        try:
            x = window_params.get("x", 0)
            y = window_params.get("y", 0)
            width = window_params.get("width", 800)
            height = window_params.get("height", 600)
            desktop_id = window_params.get("desktop_id", "0")
            cmd = f"wmctrl -r '{window_title}' -e '0,{x},{y},{width},{height}'"
            if desktop_id:
                cmd += f" -t {desktop_id}"
            subprocess.run(cmd, shell=True, check=True)
        except Exception as e:
            print(f"Error moving window on Linux: {e}")

    def _move_window_windows(self, window_title: str, window_params: Dict[str, Any]):
        try:
            import pygetwindow as gw

            wins = gw.getWindowsWithTitle(window_title)
            if wins:
                win = wins[0]
                if win.isMaximized:
                    win.restore()
                win.resizeTo(
                    window_params.get("width", 800), window_params.get("height", 600)
                )
                win.moveTo(window_params.get("x", 0), window_params.get("y", 0))
        except ImportError:
            print("Please install pygetwindow: pip install pygetwindow")
        except Exception as e:
            print(f"Error moving window on Windows: {e}")

    def _move_window_macos(self, window_title: str, window_params: Dict[str, Any]):
        try:
            from AppKit import NSWorkspace

            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.localizedName() == window_title:
                    app.activateWithOptions_(NSWorkspaceLaunchDefault)
                    break
            print(
                "Note: Detailed window moving on macOS is complex and not fully implemented here."
            )
        except ImportError:
            print("macOS support requires PyObjC. Install with: pip install pyobjc")
        except Exception as e:
            print(f"Error moving window on macOS: {e}")

    def get_pc_screen_size(self) -> Optional[Dict[str, int]]:
        os_type = platform.system()
        if os_type == "Linux":
            try:
                output = subprocess.check_output(["xrandr", "--query"]).decode("utf-8")
                for line in output.splitlines():
                    if "*+" in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if "+" in part and "x" in part:
                                width, height = part.split("x")
                                return {"width": int(width), "height": int(height)}
            except Exception as e:
                print(f"Error getting screen size on Linux: {e}")
        elif os_type == "Windows":
            try:
                import win32api

                width = win32api.GetSystemMetrics(0)
                height = win32api.GetSystemMetrics(1)
                return {"width": width, "height": height}
            except ImportError:
                print("win32api not available. Install pywin32.")
            except Exception as e:
                print(f"Error getting screen size on Windows: {e}")
        elif os_type == "Darwin":
            try:
                from AppKit import NSScreen

                screen = NSScreen.mainScreen().frame().size
                return {"width": int(screen.width), "height": int(screen.height)}
            except ImportError:
                print("macOS support requires PyObjC. Install with: pip install pyobjc")
            except Exception as e:
                print(f"Error getting screen size on macOS: {e}")
        else:
            print(f"Unsupported OS: {os_type}")
        return None

    def search(self, query: Optional[str] = None):
        sessions = self.list()
        return self.swm.fzf_wrapper.select_item(sessions, query=query)

    def list(self, show_last_used=False, print_formatted=False) -> List[str]:
        session_json_paths = [
            f for f in self.adb_wrapper.listdir(self.session_dir) if f.endswith(".json")
        ]
        session_names = [os.path.splitext(it)[0] for it in session_json_paths]
        # session_names.append("default")
        # TODO: no one can save a session named "default", or one may customize this behavior through swm pc/android config, somehow allow this to happen
        if print_formatted:
            print("Session saved on device %s:" % self.adb_wrapper.device)
            print("\t" + ("\n\t".join(session_names)))
        return session_names

    def get_pc_info(self):
        import socket
        import getpass

        # Get the current username
        username = getpass.getuser()
        hostname = socket.gethostname()
        fingerprint = self.swm.fingerprint
        ret = dict(hostname=hostname, user=username, fingerprint=fingerprint)
        return ret

    def save(self, session_name: str):
        # TODO: store all running app launch parameters at "swm_scrcpy_proc_pid_path", then we read and merge them here
        # TODO: must verify the process is alive by its pid, or exclude it
        import time

        assert session_name != "default", "Cannot save a session named 'default'"

        device = self.swm.current_device
        assert device
        print("Saving session for device:", device)
        # Get current window positions and app states
        pc = self.get_pc_info()
        session_data = {
            "timestamp": time.time(),
            "device": device,
            "pc": pc,
            # "windows": self._get_window_states(),
            "windows": self.get_window_states_for_device_by_scrcpy_pid_files(),
        }

        self._save_session_data(session_name, session_data)

    def get_window_states_for_device_by_scrcpy_pid_files(self):
        swm_info_list = (
            self.swm.scrcpy_wrapper.get_running_swm_managed_scrcpy_info_list()
        )
        return swm_info_list

    def exists(self, session_name: str) -> bool:
        session_path = self.get_session_path(session_name)
        return self.adb_wrapper.test_path_existance(session_path)

    def copy(self, source, target):
        sourcepath = self.get_session_path(source)
        targetpath = self.get_session_path(target)
        assert self.adb_wrapper.test_path_existance(sourcepath)
        assert not self.adb_wrapper.test_path_existance(targetpath)
        self.adb_wrapper.execute(["shell", "cp", sourcepath, targetpath])

    def edit(self, session_name: str):
        import tempfile

        session_path = self.get_session_path(session_name)
        if self.adb_wrapper.test_path_existance(session_name):
            tmpfile_content = self.adb_wrapper.read_file(session_path)
        else:
            tmpfile_content = self.template_session_config

        with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
            tmpfile.write(tmpfile_content)
            tmpfile.flush()
            edited_content = edit_or_open_file(tmpfile.name, return_value="content")
            assert type(edited_content) == str
            self.swm.adb_wrapper.write_file(session_path, edited_content)

    def get_session_path(self, session_name: str):
        session_path = os.path.join(self.session_dir, f"{session_name}.yaml")
        return session_path

    def _save_session_data(self, session_name: str, session_data: dict):
        import yaml

        session_path = self.get_session_path(session_name)
        content = yaml.safe_dump(session_data)
        self.swm.adb_wrapper.write_file(session_path, content)

    def check_pc_info(self, session_pc_info: dict):
        current_pc_info = self.get_pc_info()
        session_fingerprint = session_pc_info["fingerprint"]
        current_fingerprint = current_pc_info["fingerprint"]
        if current_fingerprint == session_fingerprint:
            return True
        else:
            fingerprint_trusted = self.swm.check_fingerprint_trusted(
                session_fingerprint
            )

            if fingerprint_trusted:
                return True
            else:
                # warn the user
                print("Current PC:", format_keyvalue(current_pc_info))
                print("Session PC:", format_keyvalue(session_pc_info))
                print("Warning: PC not trusted")
                ans = prompt_for_option_selection(
                    ["y", "n"],
                    "Do you trust this PC (fingerprint: %s) ?" % session_fingerprint,
                )
                if ans == "y":
                    self.swm.trust_fingerprint(session_fingerprint)
                    return True
                # ask the user to trust the pc and enlist its fingerprint
        print("User declined the trust request")
        return False

    def restore(self, session_name: str):
        import yaml

        session_path = self.get_session_path(session_name)

        if not self.swm.adb_wrapper.test_path_existance(session_path):
            raise FileNotFoundError(f"Session not found: {session_name}")

        content = self.swm.adb_wrapper.read_file(session_path)
        session_data = yaml.safe_load(content)

        session_pc_info = session_data["pc"]

        if not self.check_pc_info(session_pc_info):
            print("Not loading session '%s'" % session_name)
            return

        threads = []

        # Restore each window
        for scrcpy_info in session_data["windows"]:
            launch_params = scrcpy_info["launch_params"]
            app_name = launch_params["package_name"]
            is_app_running = self.swm.scrcpy_wrapper.check_app_running(app_name)
            # TODO: preserve icons in session restoration
            if not is_app_running:
                # TODO: run this in detached mode, or print log with different pid
                # TODO: save and restore window positioning
                t = start_daemon_thread(
                    self.swm.scrcpy_wrapper.launch_app, kwargs=launch_params
                )
                threads.append(t)
        wait_for_all_threads(threads)

    def delete(self, session_name: str) -> bool:
        session_path = self.get_session_path(session_name)
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

    def list(self, print_formatted: bool = False, show_last_used=False):
        ret = self.swm.adb_wrapper.list_device_detailed()
        if print_formatted:
            load_and_print_as_dataframe(ret)
        return ret
        # TODO: use adb to get device name:
        # adb shell settings get global device_name
        # adb shell getprop net.hostname
        # set device name:
        # adb shell settings put global device_name "NEW_NAME"
        # adb shell settings setprop net.hostname "NEW_NAME"

    def search(self, query: Optional[str] = None):
        return self.swm.fzf_wrapper.select_item(
            self.list(print_formatted=False), query=query
        )

    def resolve_device_query(self, query: str):
        if query in self.list(print_formatted=False):
            device_id = query
        else:
            device_id = self.search(query)
        return device_id

    def select(self, query: str):
        device_id = self.resolve_device_query(query)
        self.swm.set_current_device(device_id)

    def name(self, device_id: str, alias: str):
        self.swm.adb_wrapper.set_device_name(device_id, alias)


class AdbWrapper:
    def __init__(self, adb_path: str, config: omegaconf.DictConfig):
        self.adb_path = adb_path
        self.config = config
        self.device = config.get("device")
        self.remote_swm_dir = self.config.android_session_storage_path
        self.initialize()
        self.remote = self
    
    def list_app_last_visible_time(self):
        import datetime
        java_code = """
import android.content.Context;
import java.util.Calendar;
import android.os.Build;

import android.app.usage.UsageStatsManager;
import android.app.usage.UsageStats;

UsageStatsManager usageStatsManager = (UsageStatsManager) 
    systemContext.getSystemService(Context.USAGE_STATS_SERVICE);

Calendar calendar = Calendar.getInstance();
long endTime = calendar.getTimeInMillis();
calendar.add(Calendar.YEAR, -100);
long startTime = calendar.getTimeInMillis();

// Query usage stats
stats = usageStatsManager.queryAndAggregateUsageStats(startTime, endTime);

// Process results
for (UsageStats usageStats : stats.values()) {
    String packageName = usageStats.getPackageName();
    long lastTimeVisible;
    // Use getLastTimeVisible() if available (API 29+), else fallback to getLastTimeUsed()
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        lastTimeVisible = usageStats.getLastTimeVisible();
    } else {
        lastTimeVisible = usageStats.getLastTimeUsed();
    }
    System.out.println("package="+packageName+" lastTimeVisible="+lastTimeVisible.toString());
}
"""
        output = self.execute_java_code(java_code, capture_output=True)
        assert output
        # now process lines
        lines = split_lines(output)
        ret = []
        for it in lines:
            if it.startswith("package="):
                app_id, lastTimeVisible = it.split(" ")
                app_id, lastTimeVisible = app_id.split("=")[-1], lastTimeVisible.split("=")[-1]
                lastTimeVisible = int(lastTimeVisible)
                lastTimeVisible = datetime.datetime.fromtimestamp(lastTimeVisible/1000)
                ret.append(dict(app_id=app_id, lastTimeVisible = lastTimeVisible))
        return ret

    def disable_selinux(self):
        self.execute_su_cmd("setenforce 0")

    def enable_selinux(self):
        self.execute_su_cmd("setenforce 1")

    def list_recent_apps(self):
        # dumpsys activity recents  |grep 'Recent #' | grep type=standard
        output = self.check_output_shell(["dumpsys", "activity", "recents"])
        lines = grep_lines(output, ["Recent #"])
        lines = grep_lines("\n".join(lines), ["type=standard"])
        # parse app id from lines
        #   * Recent #0: Task{611ba52 #4446 type=standard A=10244:com.tencent.mobileqq U=0 visible=true visibleRequested=true mode=fullscreen translucent=false sz=1}
        ret = []
        for it in lines:
            kv_list = it.split(" ")
            ret_it = dict()
            for kv in kv_list:
                if kv.startswith("A="):
                    app_id = kv.split(":")[-1].split("/")[0]
                    ret_it["app_id"] = app_id
                    # we need the app name
                    app_name = self.get_app_name(app_id)
                    ret_it['name'] = app_name
                elif kv.startswith("visible="):
                    visible = None
                    if kv.endswith("=true"):
                        visible = True
                    elif kv.endswith("=false"):
                        visible = False
                    if visible is not None:
                        ret_it["visible"] = visible
            ret.append(ret_it)
        
        return ret

    def enable_selinux_delayed(self, delay):
        import time

        def enable_selinux_runner():
            time.sleep(delay)
            self.enable_selinux()

        start_daemon_thread(target=enable_selinux_runner)

    def check_device_online(self, device_id: str):
        active_device_ids = self.list_device_ids()
        ret = device_id in active_device_ids
        return ret

    def check_file_permission(self, remote_path: str):
        if self.test_path_existance_su(remote_path):
            user = self.check_output_su(f"stat -c '%U' '{remote_path}'").strip()
            return user
        else:
            print("Warning: File '%s' not found" % remote_path)

    def sha256sum(self, path: str):
        if self.test_path_existance_su(path):
            return self.check_output_su(
                f"sha256sum '{path}' | awk '{{print $1}}'"
            ).strip()
        else:
            print("Warning: file %s does not exist" % path)
            return None

    def stay_awake_while_plugged_in(self):
        cmd = "settings put global stay_on_while_plugged_in 7"
        self.execute_su_cmd(cmd)

    def listdir(self, path: str):
        assert self.test_path_existance(path)
        output = self.check_output_shell(["ls", "-1", path])
        ret = split_lines(output)
        return ret

    def check_has_root(self):
        return self.execute_su_cmd("whoami", check=False).returncode == 0

    def get_current_ime(self):
        # does not require su, but anyway we just use su
        output = self.check_output_su(
            "settings get secure default_input_method", check=False
        )
        return output

    def list_active_imes(self):
        ret = self.check_output_su("ime list -s")
        ret = split_lines(ret)
        return ret

    def list_installed_imes(self):
        ret = self.check_output_su("ime list -s -a")
        ret = split_lines(ret)
        return ret

    def set_current_ime(self, ime_name):
        self.execute_su_cmd(f"settings put secure default_input_method {ime_name}")

    def check_output_su(self, cmd: str, **kwargs):
        return self.check_output_shell(["su", "-c", cmd], **kwargs)

    def check_output_shell(self, cmd_args: list[str], **kwargs):
        return self.check_output(["shell"] + cmd_args, **kwargs)

    # TODO: if app is not foreground, or is ime input target but has different display id, then we close the corresponding scrcpy window

    def get_display_density(self, display_id: int):
        # adb shell wm density -d <display_id>
        # first, it must exist
        output = self.check_output(
            ["shell", "wm", "density", "-d", str(display_id)]
        ).strip()
        ret = output.split(":")[-1].strip()
        ret = int(ret)
        if ret <= 0:
            print("Warning: display %s does not exist" % display_id)
        else:
            return ret

    def check_app_in_display(self, app_id: str, display_id: int):
        display_focus = self.get_display_current_focus().get(display_id, "")
        ret = (app_id + "/") in (display_focus + "/")
        return ret

    def get_display_current_focus(self):
        # adb shell dumpsys window | grep "ime" | grep display
        # adb shell dumpsys window displays | grep "mCurrentFocus"
        # adb shell dumpsys window displays | grep -E "mDisplayId|mFocusedApp"

        # we can get display id and current focused app per display here
        # just need to parse section "WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)"

        output = self.check_output(["shell", "dumpsys", "window", "displays"])
        lines = grep_lines(output, ["mDisplayId", "mFocusedApp"])
        ret = parse_display_focus(lines)
        # print("Ret:", ret)
        return ret

    def check_app_is_foreground(self, app_id: str):
        # convert the binary output from "wm dump-visible-window-views" into ascii byte by byte, those not viewable into "."
        # adb shell wm dump-visible-window-views | xxd | grep <app_id>

        # or use the readable output from dumpsys
        # adb shell "dumpsys activity activities | grep ResumedActivity" | grep <app_id>
        # topResumedActivity: on top of specific display
        # ResumedActivity: the current focused app
        data = self.get_active_apps()
        foreground_apps = data["foreground"]
        # print("Foreground apps:", foreground_apps)
        for it in foreground_apps:
            if (app_id + "/") in (it + "/"):
                return True
        return False

    def get_active_apps(self):
        output = self.check_output(["shell", "dumpsys", "activity", "activities"])
        data = parse_dumpsys_active_apps(output)
        return data

    def check_app_existance(self, app_id):
        apk_path = self.get_app_apk_path(app_id)
        if apk_path:
            return True
        return False

    def get_display_and_lock_state(self):
        # reference: https://stackoverflow.com/questions/35275828/is-there-a-way-to-check-if-android-device-screen-is-locked-via-adb
        # adb shell dumpsys power | grep 'mHolding'
        # If both are false, the display is off.
        # If mHoldingWakeLockSuspendBlocker is false, and mHoldingDisplaySuspendBlocker is true, the display is on, but locked.
        # If both are true, the display is on.
        output = self.check_output(["shell", "dumpsys", "power"])
        lines = grep_lines(output, ["mHolding"])
        data = parse_dumpsys_keyvalue_output("\n".join(lines))
        if (
            data.get("mHoldingWakeLockSuspendBlocker") == "false"
            and data.get("mHoldingDisplaySuspendBlocker") == "false"
        ):
            ret = "off_locked"
        elif (
            data.get("mHoldingWakeLockSuspendBlocker") == "true"
            and data.get("mHoldingDisplaySuspendBlocker") == "true"
        ):
            ret = "on_unlocked"
        elif (
            data.get("mHoldingWakeLockSuspendBlocker") == "true"
            and data.get("mHoldingDisplaySuspendBlocker") == "false"
        ):
            ret = "on_locked"
        elif (
            data.get("mHoldingWakeLockSuspendBlocker") == "false"
            and data.get("mHoldingDisplaySuspendBlocker") == "true"
        ):
            ret = "off_unlocked"
        else:
            ret = "unknown"
        return ret

    def adb_keyboard_input_text(self, text: str):
        # adb shell am broadcast -a ADB_INPUT_B64 --es msg `echo -n '你好' | base64`
        base64_text = encode_base64_str(text)
        self.execute_shell(
            ["am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", base64_text]
        )
        # TODO: restore the previously using keyboard after swm being detached, either manually or using script/apk

    def execute_shell(self, cmd_args: list[str], **kwargs):
        self.execute(["shell", *cmd_args], **kwargs)

    def get_device_name(self, device_id):
        # self.set_device(device_id)
        output = self.check_output(
            ["shell", "settings", "get", "global", "device_name"], device_id=device_id
        ).strip()
        return output

    def set_device_name(self, device_id, name):
        # self.set_device(device_id)
        self.execute_shell(
            ["settings", "put", "global", "device_name", name],
            device_id=device_id,
        )

    def online(self):
        return self.device in self.list_device_ids()

    def create_file_if_not_exists(self, remote_path: str):
        if not self.test_path_existance(remote_path):
            basedir = os.path.dirname(remote_path)
            self.create_dirs(basedir)
            self.touch(remote_path)

    def touch(self, remote_path: str):
        self.execute(["shell", "touch", remote_path])

    def initialize(self):
        if self.online():
            self.create_swm_dir()

    def test_path_existance(self, remote_path: str):
        cmd = ["shell", "test", "-e", remote_path]
        result = self.execute(cmd, check=False)
        if result.returncode == 0:
            return True
        return False

    def test_path_existance_su(self, remote_path: str):
        cmd = "test -e '%s'" % remote_path
        result = self.execute_su_cmd(cmd, check=False)
        if result.returncode == 0:
            return True
        return False

    def set_device(self, device_id: str):
        self.device = device_id
        self.initialize()

    def _build_cmd(self, args: List[str], device_id=None) -> List[str]:
        cmd = [self.adb_path]
        if device_id == NO_DEVICE_ID:
            ...
        elif device_id:
            cmd.extend(["-s", device_id])
        elif self.device:  # this is problematic
            cmd.extend(["-s", self.device])
        cmd.extend(args)
        return cmd

    def execute(
        self,
        args: List[str],
        capture: bool = False,
        text=True,
        check=True,
        device_id=None,
    ) -> subprocess.CompletedProcess:
        cmd = self._build_cmd(args, device_id)
        result = subprocess.run(cmd, capture_output=capture, text=text, check=check)
        return result

    def check_output(self, args: List[str], device_id=None, **kwargs) -> str:
        return self.execute(
            args, capture=True, device_id=device_id, **kwargs
        ).stdout.strip()

    def read_file(self, remote_path: str) -> str:
        """Read a remote file's content as a string."""
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name
        try:
            self.pull_file(remote_path, tmp_path)
            with open(tmp_path, "r") as f:
                return f.read()
        finally:
            os.unlink(tmp_path)

    def write_file(self, remote_path: str, content: str):
        import tempfile

        """Write a string to a remote file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(content)
        try:
            self.push_file(tmp_path, remote_path)
        finally:
            os.unlink(tmp_path)

    def pull_file(self, remote_path: str, local_path: str):
        """Pull a file from the device to a local path."""
        self.execute(["pull", remote_path, local_path])

    def push_file(self, local_path: str, remote_path: str):
        """Push a local file to the device."""
        self.execute(["push", local_path, remote_path])

    def get_swm_apk_path(self, apk_name: str) -> str:
        path = os.path.join(self.config.cache_dir, f"apk/{apk_name}.apk")
        if os.path.exists(path):
            return path
        raise FileNotFoundError(f"APK file {apk_name} not found in cache")

    def install_adb_keyboard(self):
        adb_keyboard_app_id = "com.android.adbkeyboard"
        installed_app_id_list = self.list_packages()
        if adb_keyboard_app_id not in installed_app_id_list:
            apk_path = self.get_swm_apk_path("ADBKeyboard")
            self.install_apk(apk_path)

    def execute_su_cmd(self, cmd: str, **kwargs):
        return self.execute(["shell", "su", "-c", cmd], **kwargs)

    def execute_su_script(self, script: str, **kwargs):
        tmpfile = "/sdcard/.swm/tmp.sh"
        self.write_file(tmpfile, script)
        cmd = "sh %s" % tmpfile
        return self.execute_su_cmd(cmd, **kwargs)

    def enable_and_set_specific_keyboard(self, keyboard_activity_name: str):
        if self.get_current_ime() != keyboard_activity_name:
            self.enable_keyboard_su(keyboard_activity_name)
            self.set_keyboard_su(keyboard_activity_name)

    def enable_keyboard_su(self, keyboard_activity_name: str):
        self.execute_su_cmd("ime enable %s" % keyboard_activity_name)

    def disable_keyboard_su(self, keyboard_activity_name: str):
        self.execute_su_cmd("ime disable %s" % keyboard_activity_name)

    def set_keyboard_su(self, keyboard_activity_name: str):
        self.execute_su_cmd("ime set %s" % keyboard_activity_name)

    # TODO: update apk.zip with gboard apks

    def download_gboard_apk(self, gboard_bin_id: str):
        import requests

        download_dir = os.path.join(self.config.cache_dir, "apk")
        os.makedirs(download_dir, exist_ok=True)
        github_mirror = test_best_github_mirror(self.config.github_mirrors, 5)
        apk_name = "%s.apk" % gboard_bin_id
        download_url = "%s" % (github_mirror, apk_name)
        download_path = os.path.join(download_dir, apk_name)
        try:
            with requests.get(download_url, stream=True) as r:
                r.raise_for_status()
                with open(download_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        finally:
            if os.path.exists(download_path):
                os.remove(download_path)

    def install_gboard(self):
        device_arch = self.get_device_architecture()

        gboard_app_id = "com.google.android.inputmethod.latin"
        gboard_installed = self.check_app_existance(gboard_app_id)
        if not gboard_installed:
            gboard_bin_id = "gboard-%s" % device_arch
            try:
                apk_path = self.get_swm_apk_path(gboard_bin_id)
            except FileNotFoundError:
                self.download_gboard_apk(gboard_bin_id)
                apk_path = self.get_swm_apk_path(gboard_bin_id)
            self.install_apk(apk_path)

    def enable_and_set_gboard(self):
        gboard_activity_name = "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"
        self.enable_and_set_specific_keyboard(gboard_activity_name)

    def enable_and_set_adb_keyboard(self):
        keyboard_activity_name = "com.android.adbkeyboard/.AdbIME"
        self.enable_and_set_specific_keyboard(keyboard_activity_name)

    def disable_adb_keyboard(self):
        self.execute(["shell", "am", "force-stop", "com.android.adbkeyboard"])

    def install_apk(self, apk_path: str, instant=False):
        """Install an APK file on the device."""
        if os.path.exists(apk_path):
            cmd = ["install"]
            if instant:
                cmd.extend(["--instant"])
            cmd.append(apk_path)
            self.execute(cmd)
        else:
            raise FileNotFoundError(f"APK file not found: {apk_path}")

    def install_beeshell(self):
        apk_path = self.get_swm_apk_path("beeshell")
        app_id = "me.zhanghai.android.beeshell"
        try:
            self.install_apk(apk_path)
        except:
            print("Failed to install apk.")
            print("Uninstalling existing app %s" % app_id)
            self.uninstall_app(app_id)
            print("Trying second installation")
            self.install_apk(apk_path)

    def uninstall_app(self, app_id: str):
        self.execute(["uninstall", app_id])

    def execute_java_code(self, java_code, sudo=False, capture_output=False):
        # TODO: Capture execution output, inplant success challenge such as simple arithmatics
        # TODO: Write a java repl accessibke via swm cli
        # TODO: Run termux shell via swm cli, check if termux is installed first
        # TODO: Force airplane mode when using swm
        # print("Executing Java code:")
        # print(java_code)
        # https://github.com/zhanghai/BeeShell
        # adb install --instant app.apk
        # adb shell pm_path=`pm path me.zhanghai.android.beeshell` && apk_path=${pm_path#package:} && `dirname $apk_path`/lib/*/libbsh.so {tmp_path}

        """Execute Java code on the device."""
        self.install_beeshell()
        bsh_tmp_path = "/data/local/tmp/swm_java_code.bsh"
        sh_tmp_path = "/data/local/tmp/swm_java_code_runner.sh"
        java_code_runner = (
            "pm_path=`pm path me.zhanghai.android.beeshell` && apk_path=${pm_path#package:} && `dirname $apk_path`/lib/*/libbsh.so "
            + bsh_tmp_path
        )
        # copy files
        self.write_file(bsh_tmp_path, java_code)
        self.write_file(sh_tmp_path, java_code_runner)
        # execute
        if sudo:
            cmd = ["su", "-c", "sh '%s'" % sh_tmp_path]
        else:
            cmd = ["sh", sh_tmp_path]
        if capture_output:
            ret = self.check_output_shell(cmd)
            return ret
        else:
            self.execute_shell(cmd)

    def get_app_apk_path(self, app_id: str):
        ret = None
        output = self.check_output(["shell", "pm", "path", app_id], check=False).strip()
        if output:
            lines = split_lines(output)
            prefix = "package:"
            apk_path_list = []
            for it in lines:
                if it.startswith(prefix):
                    apk_path = it[len(prefix) :].strip()
                    apk_path_list.append(apk_path)
            apk_count = len(apk_path_list)

            if apk_count > 0:
                ret = apk_path_list[0]
            if apk_count > 1:
                print(
                    "Warning: App %s has multiple apk files (%s apks), using the first one: %s"
                    % (app_id, apk_count, ret)
                )
        if ret is None:
            print("Warning: App %s not found" % app_id)
        return ret

    def aapt_dump_badging(self, app_apk_remote_path: str):
        aapt_bin_path = self.install_aapt_binary()
        cmd = [aapt_bin_path, "dump", "badging", app_apk_remote_path]
        output = self.check_output_su(" ".join(cmd))
        return output

    def _get_app_name(self, app_apk_remote_path: str):
        output = self.aapt_dump_badging(app_apk_remote_path)
        lines = grep_lines(output, whitelist=["application-label"])
        app_name = lines[0].split(":")[1].strip().strip("'")
        return app_name

    def get_app_name(self, app_id: str):
        app_apk_remote_path = self.get_app_apk_path(app_id)
        # print("Apk remote path:", app_apk_remote_path)
        assert app_apk_remote_path
        app_name = self._get_app_name(app_apk_remote_path)
        return app_name

    def get_app_icon_path(self, app_apk_remote_path: str):
        output = self.aapt_dump_badging(app_apk_remote_path)
        lines = grep_lines(output, whitelist=["application-icon"])
        icon_path = lines[0].split(":")[1].strip().strip("'")
        return icon_path

    def extract_app_icon(self, app_apk_remote_path: str, icon_remote_dir: str):
        zip_icon_path = self.get_app_icon_path(app_apk_remote_path)
        extracted_icon_remote_path = os.path.join(icon_remote_dir, zip_icon_path)
        if self.test_path_existance(extracted_icon_remote_path):
            # remove it, no one can be sure it is the icon we want
            self.execute_shell(["rm", extracted_icon_remote_path])
        self.execute_shell(
            ["unzip", app_apk_remote_path, "-d", icon_remote_dir, zip_icon_path]
        )
        return extracted_icon_remote_path

    @property
    def remote_icon_dir(self):
        remote_cache_dir = self.remote_swm_dir
        ret = os.path.join(remote_cache_dir, "icons")
        self.create_dirs_if_not_exist(ret)
        return ret

    def create_dirs_if_not_exist(self, dir_path: str):
        if not self.test_path_existance(dir_path):
            self.create_dirs(dir_path)

    @property
    def remote_tmpdir(self):

        tmpdir = os.path.join(self.remote_swm_dir, "tmp")
        self.create_dirs_if_not_exist(tmpdir)
        return tmpdir

    def retrieve_app_icon(self, app_id: str, local_icon_path: str):
        remote_icon_png_path = os.path.join(self.remote_icon_dir, f"{app_id}_icon.png")
        tmpdir = self.remote_tmpdir
        if not self.test_path_existance(remote_icon_png_path):
            apk_remote_path = self.get_app_apk_path(app_id)
            assert apk_remote_path, f"Cannot find apk path for {app_id}"
            icon_remote_dir = tmpdir
            icon_remote_raw_path = self.extract_app_icon(
                apk_remote_path, icon_remote_dir
            )
            icon_format = icon_remote_raw_path.lower().split(".")[-1]
            # TODO:
            # use self.remote.* for all remote operations
            print("Icon format:", icon_format)
            if icon_format == "xml":
                # for debugging
                # self.copy_file(icon_remote_raw_path, "/sdcard/.swm/debug_icon.xml")
                self.convert_app_icon_drawable_to_png(app_id, remote_icon_png_path)
            elif icon_format == "png":
                self.copy_file(icon_remote_raw_path, remote_icon_png_path)
            elif icon_format == "webp":
                self.convert_webp_to_png(icon_remote_raw_path, remote_icon_png_path)
            else:
                raise ValueError("Unknown icon format %s" % icon_format)
            self.remove_dir(tmpdir, confirm=False)
        if self.test_path_existance(remote_icon_png_path):
            self.pull_file(remote_icon_png_path, local_icon_path)
        else:
            raise ValueError("Failed to extract app icon on device for:", app_id)

    def convert_app_icon_drawable_to_png(self, app_id: str, icon_png_path: str):
        import traceback

        # check kernel su manager source code for clues?
        # TODO: only use canvas when BitmapDrawable not working
        # ref:  https://stackoverflow.com/questions/44447056/convert-adaptiveicondrawable-to-bitmap-in-android-o-preview

        beeshell_app_id = "me.zhanghai.android.beeshell"
        java_code = f"""
import android.graphics.drawable.Drawable;
//import android.graphics.drawable.BitmapDrawable;
import android.graphics.Bitmap;
import android.graphics.Canvas;
        
String app_id = "{app_id}";
String output_icon_path = "{icon_png_path}";

Drawable d = systemContext.getPackageManager().getApplicationIcon(app_id); 

Bitmap bitmap = Bitmap.createBitmap(d.getIntrinsicWidth(), d.getIntrinsicHeight(), Bitmap.Config.ARGB_8888);

Canvas canvas = new Canvas(bitmap);

d.setBounds(0, 0, canvas.getWidth(), canvas.getHeight());
d.draw(canvas);

FileOutputStream out = new FileOutputStream(output_icon_path);

bitmap.compress(Bitmap.CompressFormat.PNG, 100, out);
out.close();

"""
        # TODO: store xml files under /data/data/me.zhanghai.android.beeshell/ and change permission into 777, remove afterwards
        try:
            self.execute_java_code(java_code)
        except:
            traceback.print_exc()
            print("Failed to extract icon.")
            if self.test_path_existance(icon_png_path):
                print("Removing output:", icon_png_path)
                cmd = "rm %s" % icon_png_path
                self.execute_su_cmd(cmd)

    def convert_webp_to_png(self, remote_webp_path: str, remote_png_path: str):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            local_png_path = os.path.join(tmpdir, "icon.png")
            local_webp_path = os.path.join(tmpdir, "icon.webp")

            self.pull_file(remote_webp_path, local_webp_path)
            local_webp_to_png(local_webp_path, local_png_path)
            self.push_file(local_png_path, remote_png_path)

    def copy_file(self, src_path: str, dst_path: str):
        self.execute_shell(["cp", src_path, dst_path])

    def remove_dir(self, dir_path: str, confirm=True):
        if not self.test_path_existance(dir_path):
            print("Path does not exist:", dir_path)
            return
        if confirm:
            ans = input("Are you sure you want to remove %s? (y/n)" % dir_path)
            if ans.lower() != "y":
                print("Aborting...")
                return
        self.execute_shell(["rm", "-rf", dir_path])

    def remove_file(self, file_path: str, confirm=True):
        if not self.test_path_existance(file_path):
            print("Path does not exist:", file_path)
            return
        if confirm:
            ans = input("Are you sure you want to remove %s? (y/n)" % file_path)
            if ans.lower() != "y":
                print("Aborting...")
                return
        self.execute_shell(["rm", file_path])

    @property
    def executable_remote_swm_dir(self):
        ret = "/data/data/.swm"
        if not self.test_path_existance_su(ret):
            self.execute_su_cmd("mkdir -p %s" % ret)
        return ret

    def install_aapt_binary(self):
        aapt_bin_path = os.path.join(self.executable_remote_swm_dir, "aapt")
        if not self.test_path_existance_su(aapt_bin_path):
            self.push_aapt_su(aapt_bin_path)
        return aapt_bin_path

    def get_android_version(self) -> int:
        ret = self.check_output(["shell", "getprop", "ro.build.version.release"])
        ret = int(ret)
        return ret

    def get_device_architecture(self) -> str:
        ret = self.check_output(["shell", "getprop", "ro.product.cpu.abi"])
        if "arm64" in ret:
            ret = "aarch64"
        elif "v7" in ret or "armeabi" in ret:
            ret = "armhf"
        return ret

    def list_device_ids(  # use adbutils instead.
        self,
        status_blacklist: list[str] = ["unauthorized", "fastboot"],
        with_status: bool = False,
    ) -> List:
        # TODO: detect and filter unauthorized and abnormal devices
        output = self.check_output(["devices"], device_id=NO_DEVICE_ID)
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                elements = line.split()
                device_id = elements[0]
                device_status = elements[1]
                if device_status not in status_blacklist:
                    if with_status:
                        devices.append({"id": device_id, "status": device_status})
                    else:
                        devices.append(device_id)
                else:
                    print(
                        "Warning: device %s status '%s' is in blacklist %s thus skipped"
                        % (device_id, device_status, status_blacklist)
                    )
        return devices

    def list_device_detailed(self) -> List[str]:
        device_infos = self.list_device_ids(with_status=True)
        for it in device_infos:
            device_id = it["id"]
            device_name = self.get_device_name(device_id)
            it["name"] = device_name
        return device_infos

    def list_packages(self) -> List[str]:
        output = self.check_output(["shell", "pm", "list", "packages"])
        packages = []
        for line in output.splitlines():
            if line.startswith("package:"):
                packages.append(line[len("package:") :].strip())
        return packages

    def ensure_dir_existance(self, dir_path: str):
        if self.test_path_existance(dir_path):
            return
        print("Directory %s not found, creating it now..." % dir_path)
        self.create_dirs(dir_path)

    def create_swm_dir(self):
        swm_dir = self.remote_swm_dir
        self.ensure_dir_existance(swm_dir)

    def create_dirs(self, dirpath: str):
        self.execute(["shell", "mkdir", "-p", dirpath])

    def push_aapt_su(self, target_path_su: str):
        device_path = os.path.join(self.config.android_session_storage_path, "aapt")
        device_architecture = self.get_device_architecture()
        bin_arch = get_android_bin_arch(device_architecture)
        local_aapt_path = os.path.join(
            self.config.cache_dir, "android-binaries", "aapt", "aapt-%s" % bin_arch
        )
        self.execute(["push", local_aapt_path, device_path])
        self.execute_su_cmd("cp %s %s" % (device_path, target_path_su))
        self.execute_su_cmd("chmod 700 %s" % target_path_su)

    def pull_session(self, session_name: str, local_path: str):
        remote_path = os.path.join(
            self.config.android_session_storage_path, session_name
        )
        self.execute(["pull", remote_path, local_path])


class ScrcpyWrapper:
    def __init__(
        self,
        scrcpy_path: str,
        swm: "SWM",
    ):
        self.scrcpy_path = scrcpy_path
        self.config = swm.config
        self.device = swm.config.get("device")
        self.adb_wrapper = swm.adb_wrapper
        self.swm = swm
        self.ime_preference = None

    @property
    def app_list_cache_path(self):
        return os.path.join(
            self.config.android_session_storage_path, "package_list_cache.json"
        )

    def load_package_id_and_alias_cache(self):
        import json
        import time

        package_list = None
        cache_expired = True
        if self.adb_wrapper.test_path_existance(self.app_list_cache_path):
            content = self.adb_wrapper.read_file(self.app_list_cache_path)
            data = json.loads(content)
            cache_save_time = data["cache_save_time"]
            now = time.time()
            cache_age = now - cache_save_time
            if cache_age < self.config.app_list_cache_update_interval:
                cache_expired = False
                package_list = data["package_list"]
        return package_list, cache_expired

    def save_package_id_and_alias_cache(self, package_list):
        import json
        import time

        data = {"package_list": package_list, "cache_save_time": time.time()}
        content = json.dumps(data)
        self.adb_wrapper.write_file(self.app_list_cache_path, content)

    def get_active_display_ids(self):
        # scrcpy --list-displays
        output = self.check_output(["--list-displays"])
        output_lines = output.splitlines()
        ret = {}
        for it in output_lines:
            it = it.strip()
            # we can only have size here, not dpi
            if it.startswith("--display-id"):
                display_id_part, size_part = it.split()
                display_id = display_id_part.split("=")[-1]
                display_id = int(display_id)
                size_part = size_part.replace("(", "").replace(")", "")
                x_size, y_size = size_part.split("x")
                x_size, y_size = int(x_size), int(y_size)
                ret[display_id] = dict(x=x_size, y=y_size)
        return ret

    # TODO: use "scrcpy --list-apps" instead of using aapt to parse app labels

    def list_package_id_and_alias(self):
        # will not list apps without activity or UI
        # scrcpy --list-apps
        output = self.check_output(["--list-apps"])
        # now, parse these apps
        parseable_lines = []
        for line in output.splitlines():
            # line: "package_id alias"
            line = line.strip()
            if line.startswith("* "):
                # system app
                parseable_lines.append(line)
            elif line.startswith("- "):
                # user app
                parseable_lines.append(line)
            else:
                # skip this line
                ...
        ret = []
        for it in parseable_lines:
            result = parse_scrcpy_app_list_output_single_line(it)
            ret.append(result)
        return ret

    def set_device(self, device_id: str):
        self.device = device_id

    def _build_cmd(self, args: List[str], device_id=None) -> List[str]:
        # TODO: make these configs into a config file, such as "scrcpy_base_args"
        cmd = [self.scrcpy_path]
        # TODO: display fps when loglevel is verbose
        # cmd.extend(['--print-fps'])
        # <scrcpy stdout> INFO: 61 fps
        ime_preference = self.ime_preference
        # may fail and require su
        # cmd.extend(["--mouse-bind=++++"])  # prevent accident exit, --forward-all-clicks
        cmd.extend(["--stay-awake"])
        cmd.extend(["--disable-screensaver"])
        cmd.extend(
            ["--display-ime-policy=local"]
        )  # preferred for Gboard, if only the gray bar of adbkeyboard can be hidden (a custom build, or any alternative maybe?)
        print("IME preference:", ime_preference)
        if ime_preference == "adbkeyboard":
            cmd.extend(
                ["--prefer-text"]
            )  # this flag shall be enabled when using the adbkeyboard to input text from PC IME, to make sure ASCII chars injected (cannot use with --keyboard=uhid)
            # https://github.com/npes87184/SocketIME
        elif ime_preference in ["gboard", "uhid"]:
            # Note: Shift + Space for switching IME (sometimes not working)
            # so that you can use gboard, the "hardware" keyboard, the floating keyboard
            cmd.extend(["--keyboard=uhid"])
        elif ime_preference == "plain":
            ...
        elif ime_preference == "hide":
            cmd.extend(["--display-ime-policy=hide"])
        else:
            raise ValueError("Unknown IME preference: %s" % ime_preference)
        # TODO: change scrcpy PC IME input prompt starting location based on android device cursor location, first get the cursor location (how did gboard know that?)
        # cmd.extend(["--display-ime-policy=hide"]) # not working with any keyboard
        # for capturing paste events
        # cmd.extend(["--verbosity=verbose"])
        # <scrcpy stdout> VERBOSE: input: key up   code=67 repeat=0 meta=000000
        # <scrcpy stdout> VERBOSE: input: clipboard 0 nopaste "<content>"
        if device_id == NO_DEVICE_ID:
            ...
        elif device_id:
            cmd.extend(["-s", device_id])
        elif self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(args)
        return cmd

    def execute(self, args: List[str]):
        cmd = self._build_cmd(args)
        subprocess.run(cmd, check=True)

    def execute_detached(self, args: List[str]):
        cmd = self._build_cmd(args)
        spawn_and_detach_process(cmd)

    def check_output(self, args: List[str]) -> str:
        cmd = self._build_cmd(args)
        output = subprocess.check_output(cmd).decode("utf-8")
        return output

    def start_sidecar_app_launch_filelock_releaser(
        self, proc: subprocess.Popen, lock, interval=0.5
    ):
        import time

        print("Starting sidecar app launch filelock releaser")

        def filelock_releaser():
            while True:
                time.sleep(interval)
                # print("Looping")
                if hasattr(proc, "terminate_reason"):
                    break
                if getattr(proc, "app_in_display", False):
                    break
            try:
                lock.release()
            except:
                pass
            try:
                os.remove(lock.lock_file)
            except:
                pass

        start_daemon_thread(target=filelock_releaser)

    def start_sidecar_ime_activator(self, proc: subprocess.Popen, interval=0.5):
        import time

        app_id = getattr(proc, "app_id")

        # proc_pid = proc.pid
        def ime_activator():
            if self.ime_preference not in ["gboard", "adbkeyboard"]:
                return
            while True:
                time.sleep(interval)
                if hasattr(proc, "terminate_reason"):
                    break
                if hasattr(proc, "device_disconnected"):
                    break
                active_apps = self.adb_wrapper.get_active_apps()
                # print("Active apps:", active_apps)
                focused_app_ids = active_apps["focused"]  # currently only one
                app_focused = app_id in focused_app_ids
                setattr(proc, "app_focused", app_focused)
                # print("App focused:", app_focused)
                # print("IME preference:", self.ime_preference)
                if app_focused:
                    # check app in display
                    app_in_display = getattr(proc, "app_in_display", False)
                    if not app_in_display:
                        continue
                    if hasattr(proc, "device_disconnected"):
                        break
                    if self.ime_preference == "gboard":
                        self.adb_wrapper.enable_and_set_gboard()
                    elif self.ime_preference == "adbkeyboard":
                        self.adb_wrapper.enable_and_set_adb_keyboard()

        start_daemon_thread(target=ime_activator)

    def start_sidecar_scrcpy_monitor_control_port(self, proc: subprocess.Popen):
        import time

        proc_pid = proc.pid

        def monitor_control_port():
            while True:
                time.sleep(1)
                port = get_first_laddr_port_with_pid(proc_pid)
                if port:
                    print("Control port:", port)
                    setattr(proc, "control_port", port)
                    break

        start_daemon_thread(monitor_control_port)

    def is_device_connected(self):
        assert self.device
        ret = self.swm.adb_wrapper.check_device_online(self.device)
        return ret

    def wait_for_device_reconnect(self):
        import time
        import random

        print("Waiting for device %s to reconnect" % self.device)

        while True:
            time.sleep(0.5 + 0.5 * random.random())
            if self.is_device_connected():
                print("Device %s is online" % self.device)
                break

    def install_and_use_adb_keyboard(self):  # require root
        # TODO: check root avalibility, decorate this method, if no root is found then raise exception
        self.swm.adb_wrapper.install_adb_keyboard()
        self.swm.adb_wrapper.enable_and_set_adb_keyboard()

    def install_and_use_gboard(self):
        self.swm.adb_wrapper.install_gboard()
        self.swm.adb_wrapper.enable_and_set_gboard()

    def acquire_app_launch_lock(self):
        import filelock

        lock_path = os.path.join(self.swm.config.cache_dir, "app_launch.lock")

        lock = filelock.FileLock(lock_path)
        lock.acquire()
        return lock

    def launch_app(
        self,
        package_name: str,
        init_config: Optional[str] = None,
        window_params: Optional[Dict] = None,
        scrcpy_args: Optional[list[str]] = None,
        new_display=True,
        title: Optional[str] = None,
        no_audio=True,
        ime_preference: Optional[str] = None,
        # use_adb_keyboard=False,
        env={},
    ):
        import signal
        import psutil
        import json
        import sys

        # import time
        try:
            self.cleanup_scrcpy_proc_pid_files(app_id=package_name)
        except OldInstanceRunning as e:
            print(e.args[0])
            return

        args = []

        self.ime_preference = ime_preference

        print("IME preference before launching app:", ime_preference)

        if ime_preference == "adbkeyboard":
            # if use_adb_keyboard:
            self.install_and_use_adb_keyboard()
        elif ime_preference == "gboard":
            self.install_and_use_gboard()

        configured_window_options = []

        zoom_factor = self.config.zoom_factor  # TODO: make use of it

        if window_params:
            for it in ["x", "y", "width", "height"]:
                if it in window_params:
                    args.extend(["--window-%s=%s" % (it, window_params[it])])
                    configured_window_options.append("--window-%s" % it)

        if new_display:
            args.extend(["--new-display"])

        if no_audio:
            args.extend(["--no-audio"])

        if title:
            args.extend(["--window-title", title])

        if scrcpy_args:
            for it in scrcpy_args:
                if it.split("=")[0] not in configured_window_options:
                    args.append(it)
                else:
                    print(
                        "Warning: one of scrcpy options '%s' is already configured" % it
                    )

        args.extend(["--start-app", package_name])
        # reference: https://stackoverflow.com/questions/2804543/read-subprocess-stdout-line-by-line

        # self.execute_detached(args)
        # self.execute(args)
        unicode_char_warning = "[server] WARN: Could not inject char"
        cmd = self._build_cmd(args)
        _env = os.environ.copy()
        _env.update(env)


        print("Acquiring lock")
        lock = self.acquire_app_launch_lock()
        print("Lock acquired")

        # merge stderr with stdout
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            env=_env,
        )
        setattr(proc, "app_id", package_name)
        proc_pid = proc.pid

        print("Scrcpy PID:", proc_pid)


        self.swm.ime_manager.run_previous_ime_restoration_script()  # BUG: no multicursor across multiple tab of the same file in vscode

        self.start_sidecar_scrcpy_app_monitor_thread(package_name, proc)

        self.start_sidecar_scrcpy_monitor_control_port(proc)

        if new_display:
            self.start_sidecar_scrcpy_stdout_monitor_thread(proc)
        else:
            setattr(proc, "display_id", 0)
        assert proc.stderr
        previous_ime = self.get_previous_ime()
        if not previous_ime:
            print("Warning: Previous IME unrecognized")

        # TODO: capture stdout for getting new display id
        # TODO: collect missing char into batches and execute once every 0.5 seconds
        # TODO: restart the app in given display if exited, or just close the window (configure this behavior as an option "on_app_exit")
        # not to use the compat "launch_params" since we may have trouble when the config file is edited.
        # TODO: configure this behavior further, by prefer "init_config" or "freezed_parameters"
        # TODO: build "env" when prefer "freezed_parameters"
        launch_params = dict(
            package_name=package_name,
            init_config=init_config,
            window_params=window_params,
            scrcpy_args=scrcpy_args,
            new_display=new_display,
            title=title,
            no_audio=no_audio,
            # use_adb_keyboard=use_adb_keyboard,
            ime_preference=ime_preference,
        )

        self.start_sidecar_ime_activator(proc=proc)

        swm_scrcpy_proc_pid_path = self.generate_swm_scrcpy_proc_pid_path()
        # lock = None
        try:
            self.start_sidecar_app_launch_filelock_releaser(proc=proc, lock=lock)
            # write the pid to the path
            with open(swm_scrcpy_proc_pid_path, "w") as f:
                data = dict(
                    pid=proc_pid, device_id=self.device, launch_params=launch_params
                )
                content_data = json.dumps(data, indent=4, ensure_ascii=False)
                f.write(content_data)
                # TODO: write additional launch parameters here so we can create a session based on these files
            if ime_preference == "adbkeyboard":
                self.start_sidecar_unicode_input(
                    proc=proc,
                )
            for line in proc.stderr:
                captured_line = line.strip()
                if self.config.verbose:
                    ...
                print(
                    "<scrcpy stderr> %s" % captured_line
                )  # now we check if this indicates some character we need to type in
                if "WARN: Device disconnected" in captured_line:
                    setattr(proc, "device_disconnected", True)
                    break
                if captured_line.startswith(unicode_char_warning):
                    char_repr = captured_line[len(unicode_char_warning) :].strip()
                    char_str = convert_unicode_escape(char_repr)
                    if char_str:
                        pending_unicode_input = getattr(
                            proc, "pending_unicode_input", ""
                        )
                        pending_unicode_input += char_str
                        setattr(proc, "pending_unicode_input", pending_unicode_input)
                    # TODO: use clipboard set and paste instead
                    # TODO: make unicode_input_method a text based config, opening the main display to show the default input method interface when no clipboard input or adb keyboard is enabled
                    # TODO: hover the main display on the focused new window to show input candidates
                    # Note: gboard is useful for single display, but not good for multi display.
                # [server] WARN: Could not inject char u+4f60
                # TODO: use adb keyboard for pasting text from clipboard
        finally:
            if lock:
                try:
                    lock.release()
                except:
                    pass
                try:
                    os.remove(lock.lock_file)
                except:
                    pass

            ex_type, ex_value, ex_traceback = sys.exc_info()

            # TODO: close the app when the main process is closed

            # check if the device is online.
            if getattr(proc, "device_disconnected", False):
                device_online = False
            else:
                device_online = self.is_device_connected()
            if not device_online:
                setattr(proc, "terminate_reason", "device_offline")
            # stderr will emit:
            # WARN: Device disconnected

            terminate_reason = "unknown"

            if hasattr(proc, "terminate_reason"):
                terminate_reason = getattr(proc, "terminate_reason")
            else:
                # read the reason from pid file
                if os.path.exists(swm_scrcpy_proc_pid_path):
                    with open(swm_scrcpy_proc_pid_path, "r") as f:
                        data = json.load(f)
                        assert type(data) == dict
                        terminate_reason = data.get("terminate_reason", "unknown")

            # kill by pid, if alive
            if psutil.pid_exists(proc_pid):
                # probably user_requested, or error
                if terminate_reason == "unknown":
                    if ex_type == KeyboardInterrupt:
                        terminate_reason = "user_requested"
                    elif ex_type is not None:
                        terminate_reason = "swm_error"
                try:
                    os.kill(proc_pid, signal.SIGTERM)
                    proc.kill()
                except:
                    print("Error while trying to kill the scrcpy process %s" % proc_pid)

            terminate_success = False
            # time.sleep(0.5) # reduce false nagative of terminate_success
            if os.path.exists(swm_scrcpy_proc_pid_path):
                if not psutil.pid_exists(proc_pid):
                    terminate_success = True
                    os.remove(swm_scrcpy_proc_pid_path)
                else:
                    print(
                        "Not removing PID file %s since the scrcpy process %s is still running (termination might be pending)"
                        % (swm_scrcpy_proc_pid_path, proc_pid)
                    )

            has_exception = ex_type is not None

            print("Has exception:", has_exception)
            print("Scrcpy terminate reason:", terminate_reason)
            print("Terminate success:", terminate_success)

            setattr(proc, "has_exception", has_exception)
            setattr(
                proc, "terminate_reason", terminate_reason
            )  # if at this point terminate_reason is 'unknown', probably it is killed using GUI or operating system
            setattr(proc, "terminate_success", terminate_success)

            restart_reasons = self.config.restart_reasons  # TODO: make this configurable in swm baseconfig

            need_restart = not has_exception and (terminate_reason in restart_reasons)

            setattr(proc, "need_restart", need_restart)

            if need_restart:
                if terminate_reason == "app_gone":
                    print("App gone, restarting app")

                if terminate_reason == "device_offline":
                    print("Device is offline, waiting for device to reconnect")
                    device_online = False  # assume to be False here
                else:
                    device_online = (
                        self.is_device_connected()
                    )  # only god know if the device is still online here
                if not device_online:
                    self.wait_for_device_reconnect()
                restart_params = launch_params.copy()
                restart_params["env"] = env
                self.launch_app(**restart_params)

            no_swm_process_running = not self.has_swm_process_running

            if no_swm_process_running:
                if previous_ime:
                    if self.is_device_connected():
                        print("Reverting to previous IME")
                        self.adb_wrapper.enable_and_set_specific_keyboard(previous_ime)
                    else:
                        print("Device offline, cannot revert to previous IME")

    def start_sidecar_unicode_input(
        self,
        proc: subprocess.Popen,
        # use_adb_keyboard: bool,
        poll_interval=0.1,
        pid_check_interval=1,
    ):
        import time
        import psutil

        def unicode_input():
            proc_pid = proc.pid
            last_pid_check_reltime = 0
            while True:
                time.sleep(poll_interval)
                last_pid_check_reltime += poll_interval
                if last_pid_check_reltime >= pid_check_interval:
                    last_pid_check_reltime = 0
                    if not psutil.pid_exists(proc_pid):
                        break
                if getattr(proc, "terminate_reason", ""):
                    break
                pending_unicode_input = getattr(proc, "pending_unicode_input", "")
                if not pending_unicode_input:
                    continue
                else:
                    setattr(proc, "pending_unicode_input", "")
                # if use_adb_keyboard:
                # TODO: check if the adb keyboard is "really" activated (with the grey bar underneath the screen) programatically before broadcasting the intent
                self.adb_wrapper.adb_keyboard_input_text(pending_unicode_input)
                # else:
                #     self.clipboard_paste_input_text(pending_unicode_input)

        start_daemon_thread(unicode_input)

    def check_app_in_display(self, app_id: str, display_id: int):
        assert self.device
        device_online = self.is_device_connected()
        if device_online:
            app_is_foreground = self.adb_wrapper.check_app_is_foreground(app_id)
            app_is_in_display = self.adb_wrapper.check_app_in_display(
                app_id, display_id
            )
        else:
            raise DeviceOfflineError(
                "Device %s is offline, cannot obtain app %s status in display %s"
                % (self.device, app_id, display_id)
            )

        if not app_is_foreground:
            print("App %s is not in foreground" % app_id)
        if not app_is_in_display:
            print("App %s is not in display %s" % (app_id, display_id))
        return app_is_foreground and app_is_in_display

    def start_sidecar_scrcpy_stdout_monitor_thread(self, proc: subprocess.Popen):
        assert proc.stdout
        proc_stdout = proc.stdout

        def monitor_stdout_and_set_attribute():
            for line in proc_stdout:
                line = line.strip()
                print("<scrcpy stdout> %s" % line)
                if line.startswith("[server] INFO: New display:"):
                    display_id = line.split("=")[-1].strip("()")
                    display_id = int(display_id)
                    setattr(proc, "display_id", display_id)

        start_daemon_thread(monitor_stdout_and_set_attribute)

    def scrcpy_app_monitor(self, app_id: str, proc: subprocess.Popen):
        # import signal
        import time
        import psutil

        proc_pid = proc.pid
        reconfirming_times = 3
        reconfirming_interval = 0.2

        while True:
            time.sleep(0.2)
            if hasattr(proc, "display_id"):
                display_id = getattr(proc, "display_id")
                break

        last_app_in_display = app_in_display = (
            True  # self.check_app_in_display(app_id, display_id)
        )
        while True:
            last_app_in_display = app_in_display
            time.sleep(1)
            try:
                app_in_display = self.check_app_in_display(app_id, display_id)
                setattr(proc, "app_in_display", app_in_display)
            except DeviceOfflineError as e:
                print(e.args[0])
                break
            process_alive = psutil.pid_exists(proc_pid)
            if not process_alive:
                break
            if (
                last_app_in_display == True and app_in_display == False
            ):  # app terminated
                # before terminate, analyze the current dump
                # TODO: restart app in given display, using adb shell
                for trial in range(reconfirming_times):
                    time.sleep(reconfirming_interval)
                    print(
                        "App %s seems not in display %s. Reconfirming %s/%s"
                        % (app_id, display_id, trial + 1, reconfirming_times)
                    )
                    if self.check_app_in_display(app_id, display_id):
                        app_in_display = True
                        break
                if app_in_display:
                    continue
                active_apps = self.adb_wrapper.get_active_apps()
                display_current_focus = self.adb_wrapper.get_display_current_focus()
                print("Dump info before killing scrcpy:")
                print("Active apps:", active_apps)
                print("Display current focus:", display_current_focus)
                proc.terminate()
                if not hasattr(proc, "terminate_reason"):
                    setattr(proc, "terminate_reason", "app_gone")
                # os.kill(proc_pid, signal.SIGKILL)
                break

    def get_previous_ime(self):
        adbkeyboard_ime = "com.android.adbkeyboard/.AdbIME"
        previous_ime = self.adb_wrapper.get_current_ime()
        if previous_ime == adbkeyboard_ime:
            previous_ime = self.read_previous_ime_from_device()
        else:
            self.store_previous_ime_to_device(previous_ime)
        return previous_ime

    def read_previous_ime_from_device(self):
        assert self.swm.on_device_db
        return self.swm.on_device_db.read_previous_ime()

    def store_previous_ime_to_device(self, previous_ime: str):
        assert self.swm.on_device_db
        self.swm.on_device_db.write_previous_ime(previous_ime)

    def start_sidecar_scrcpy_app_monitor_thread(
        self, app_id: str, proc: subprocess.Popen
    ):
        # configure this thread with daemon=True
        start_daemon_thread(
            target=self.scrcpy_app_monitor, kwargs=dict(app_id=app_id, proc=proc)
        )

    def generate_swm_scrcpy_proc_pid_path(self):
        import uuid

        unique_id = str(uuid.uuid4())
        filename = "%s.json" % unique_id
        ret = os.path.join(self.swm_scrcpy_proc_pid_basedir, filename)
        return ret

    @property
    def swm_scrcpy_proc_pid_basedir(self):
        ret = os.path.join(self.config.cache_dir, "swm_scrcpy_proc_pid")
        if not os.path.exists(ret):
            os.makedirs(ret, exist_ok=True)
        return ret

    @property
    def has_swm_process_running(self):
        return len(self.get_running_swm_managed_scrcpy_pids()) > 0

    def list_swm_managed_scrcpy_pid_files(self):
        ret = []
        for it in os.listdir(self.swm_scrcpy_proc_pid_basedir):
            path = os.path.join(self.swm_scrcpy_proc_pid_basedir, it)
            if os.path.isfile(path):
                if not path.endswith(".json"):
                    continue
                ret.append(path)
        return ret

    def get_running_swm_managed_scrcpy_pids(self):
        ret = self.get_running_swm_managed_scrcpy_info_list()
        ret = [it["pid"] for it in ret]
        return ret

    def check_app_running(self, app_id: str):
        running_app_ids = self.get_running_app_ids()
        ret = app_id in running_app_ids
        return ret

    def get_running_app_ids(self):
        scrcpy_info_list = self.get_running_swm_managed_scrcpy_info_list()
        ret = [it["launch_params"]["package_name"] for it in scrcpy_info_list]
        return ret

    def cleanup_scrcpy_proc_pid_files(self, app_id: Optional[str] = None):
        # TODO: consider record and revive these inactive ones instead of deleting them, or configure to be "restart=always"
        self.get_running_swm_managed_scrcpy_info_list(
            remove_inactive=True, remove_app_id=app_id
        )

    def get_running_swm_managed_scrcpy_info_list(
        self, remove_inactive=False, remove_app_id: Optional[str] = None
    ):
        import psutil
        import json
        import signal

        ret = []
        assert self.device
        for path in self.list_swm_managed_scrcpy_pid_files():
            if not os.path.exists(path):
                print("PID file %s is gone. Skipping" % path)
                continue
            with open(path, "r") as f:
                data = json.load(f)
            assert type(data) == dict
            terminate_reason = data.get("terminate_reason", None)
            if terminate_reason:
                os.remove(path)
            pid = data["pid"]
            pid = int(pid)
            if psutil.pid_exists(pid):
                app_id = data["launch_params"]["package_name"]
                device_id = data["device_id"]
                if device_id != self.device:
                    continue
                else:
                    if remove_app_id and app_id == remove_app_id:
                        launch_policy = self.swm.config.launch_policy
                        if launch_policy == "keep_new":
                            print(
                                "Terminating old scrcpy process (PID: %s) for app_id:"
                                % pid,
                                app_id,
                            )
                            os.kill(pid, signal.SIGTERM)
                            # now write the file
                            data["terminate_reason"] = "new_instance"
                            with open(path, "w") as f:
                                json.dump(data, f)
                            continue
                        elif launch_policy == "keep_old":
                            # kill current process right now
                            raise OldInstanceRunning(
                                "An app instance %s for device %s is running, and your launch_policy is %s"
                                % (app_id, self.device, launch_policy)
                            )
                        else:
                            # TODO: use pydantic to load config
                            print(
                                "Ineffective launch policy %s, ignoring" % launch_policy
                            )
                ret.append(data)
            else:
                if remove_inactive:
                    print("Removing inactive scrcpy pid file:", path)
                    os.remove(path)
        return ret

    def clipboard_paste_input_text(self, text: str):
        import pyperclip
        import pyautogui

        pyperclip.copy(text)
        if platform.system() == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")


class FzfWrapper:
    def __init__(self, fzf_path: str):
        self.fzf_path = fzf_path

    def select_item(self, items: List[str], query: Optional[str] = None) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w+") as tmp:
            tmp.write("\n".join(items))
            tmp.flush()

            cmd = [self.fzf_path, "--layout=reverse"]
            if query:
                # TODO: make this configurable with config file
                cmd.extend(["--bind", "one:accept"])
                cmd.extend(["--query", query])
            result = subprocess.run(
                cmd, stdin=open(tmp.name, "r"), stdout=subprocess.PIPE, text=True
            )
            if result.returncode == 0:
                ret = result.stdout.strip()
            else:
                print("Error: fzf exited with code %d" % result.returncode)
                ret = ""
            print("FZF selection:", ret)
            return ret


class ReplManager: ...


class ImeManager:
    def __init__(self, swm: SWM):
        self.swm = swm

    def run_previous_ime_restoration_script(self):
        print("Warning: run_previous_ime_restoration_script is not implemented yet")
        self.install_previous_ime_restoration_script()
        ...

    def install_previous_ime_restoration_script(self):
        print("Warning: install_previous_ime_restoration_script is not implemented yet")
        # execute this method everytime run a new app
        # run it on android as root
        # steps:
        # check if pid file exist
        #  if pid file not exist, continue execution
        #  if pid file exist, check if the pid is running
        #   if pid exist and the pid is running, exit program
        #   if pid does not exist, remove the pid file
        # create the pid file with the child pid (about to be detached)
        # look for "@scrcpy_" unix domain sockets on device
        #  if "@scrcpy_" unix domain sockets exist, continue execution
        #  if no "@scrcpy_" unix domain sockets exist, exit loop
        # look for previous ime record file
        #   if previous ime file exist, enable and set to previous ime
        #   if not exist, just exit
        ...

    def get_current_ime(self):
        ret = self.swm.adb_wrapper.get_current_ime()
        return ret

    def list(self, display=False):
        sort_order = {"active": 1, "installed": 2, "selected": 0}
        ret = self.swm.adb_wrapper.list_installed_imes()
        # print("Installed IMEs:", ret)
        if display:
            active_imes = self.swm.adb_wrapper.list_active_imes()
            # print("Active IMEs:", active_imes)
            records = []
            current_ime = self.get_current_ime()
            # print("Current IME:", current_ime)
            for it in ret:
                app_name = self.get_ime_app_name(it)
                # print("App Name:", app_name)
                state = "installed"
                if it in active_imes:
                    state = "active"
                if it == current_ime:
                    state = "selected"
                rec = dict(app_name=app_name, ime_id=it, state=state)
                records.append(rec)
            # load and display records
            records.sort(key=lambda x: sort_order[x["state"]])
            load_and_print_as_dataframe(records)
        return ret

    def get_ime_app_name(self, ime_id: str):
        app_id = ime_id.split("/")[0]
        # print("App ID:", app_id)
        app_name = self.swm.adb_wrapper.get_app_name(app_id)
        return app_name

    def search(self, query: Optional[str] = None):
        # TODO: show input app name in search
        ime_list = self.list()
        ret = self.swm.fzf_wrapper.select_item(ime_list, query=query)
        return ret

    def resolve_ime_query(self, query: str):
        ime_list = self.list()
        if query in ime_list:
            selected_ime = query
        else:
            selected_ime = self.search(query=query)
        return selected_ime

    def switch(self, query: str):
        ime = self.resolve_ime_query(query)
        self._switch(ime)

    def activate(self, query: str):
        ime = self.resolve_ime_query(query)
        self._activate(ime)

    def deactivate(self, query: str):
        ime = self.resolve_ime_query(query)
        self._deactivate(ime)

    def _activate(self, ime_id: str):
        self.swm.adb_wrapper.enable_keyboard_su(ime_id)

    def _deactivate(self, ime_id: str):
        self.swm.adb_wrapper.disable_keyboard_su(ime_id)

    def _switch(self, ime_id: str):
        self.swm.adb_wrapper.enable_and_set_specific_keyboard(ime_id)

    def switch_to_previous(self):
        previous_ime = self.swm.scrcpy_wrapper.get_previous_ime()
        if previous_ime:
            self._switch(previous_ime)
        else:
            print("No previous IME")


class WirelessManager: ...


class FileManager: ...


class JavaManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.beeshell_app_id = "me.zhanghai.android.beeshell"
        self.beeshell_invoke_command = "pm_path=`pm path me.zhanghai.android.beeshell` && apk_path=${pm_path#package:} && `dirname $apk_path`/lib/*/libbsh.so"

    def run(self, script_path: str, sudo=False):
        content = get_file_content(script_path)
        self.run_script(content, sudo=sudo)

    def run_script(self, content: str, sudo=False):
        self.swm.adb_wrapper.execute_java_code(content, sudo=sudo)

    def shell(self, shell_args: list[str] = [], sudo=False):
        if shell_args:
            script_content = " ".join(shell_args)
            self.run_script(script_content, sudo=sudo)
        else:
            print("No script provided, start REPL")
            self.swm.adb_wrapper.install_beeshell()
            if sudo:
                cmd = ["-t", "su", "-c", self.beeshell_invoke_command]
            else:
                cmd = ["-t", self.beeshell_invoke_command]
            self.swm.adb_wrapper.execute_shell(cmd)


# TODO: further restrict user privilege and emulate run_as behavior via chroot, proot or other methods, if Termux is not debug build

# == not working start ==

# getprop ro.debuggable # 0
# resetprop ro.debuggable 1 # ksu/magisk
# stop
# start
# (phone will soft-restart so we would not use this method, also ineffective for run-as com.termux, still "not debuggable")

# == not working end ==

# xposed module making app debuggable
# https://github.com/ttimasdf/XDebuggable

# optionally, run termux sshd service with "am startservice"

# get selinux context
# su -c 'am startservice -n com.termux/.app.TermuxService -e com.termux.RUN_COMMAND "id > /data/data/com.termux/files/home/id_output.txt"'
# cat /data/data/com.termux/files/home/id_output.txt
# or:
# ls -Z /data/data/com.termux/files/usr/bin/bash

# setenforce 0
# runcon u:r:untrusted_app_27:s0 id
# setenforce 1 # run this in a separate thread, 1 sec after above line started

# also you can use root privilege to make all apps debuggable, or just a selected few
# install termux from github release which is debuggable by default, unlike f-droid ones

# id difference:
# context=u:r:su:s0
# context=u:r:untrusted_app_27:s0:c24,c257,c512,c768

# ls -Z /data/data/com.termux/files/usr/var/run/tmux-10280/default difference:
# u:object_r:app_data_file:s0
# u:object_r:app_data_file:s0:c24,c257,c512,c768

# you can just run setenforce 0 to bypass selinux restrictions and may help with tmux permission issues, but dangerous


# TODO: warn the user that tmux may not work properly (permission denied from android termux app if the server is created using swm termux shell)
class TermuxManager:
    def __init__(self, swm: SWM):
        self.swm = swm
        self.content_init_script = """#!/system/bin/sh
export PREFIX='/data/data/com.termux/files/usr'
export HOME='/data/data/com.termux/files/home'
export LD_LIBRARY_PATH='/data/data/com.termux/files/usr/lib'
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
# export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets:$PATH"
export LD_PRELOAD='/data/data/com.termux/files/usr/lib/libtermux-exec-ld-preload.so'
export TERM='xterm-256color'
export TMPDIR='/data/data/com.termux/files/usr/tmp'
export LANG='en_US.UTF-8'
export SHELL='/data/data/com.termux/files/usr/bin/bash'
#SELINUX_CONTEXT=$(stat -c '%C' $SHELL)
cd "$HOME"
exec "$SHELL" -li $@
#runcon "$SELINUX_CONTEXT" "$SHELL" -li $@
"""
        self.sha256_init_script = sha256sum(self.content_init_script)
        self.termux_bash_path = "/data/data/com.termux/files/usr/bin/bash"
        self.path_init_script = self.swm.adb_wrapper.remote_swm_dir + "/termux_init.sh"

    def get_selinux_context(self):
        cmd = "stat -c '%C' '/data/data/com.termux/files/usr/bin/bash'"
        output = self.swm.adb_wrapper.check_output_su(cmd).strip()
        return output

    def check_termux_installed(self):
        ret = self.swm.adb_wrapper.test_path_existance_su(self.termux_bash_path)
        return ret

    def check_termux_init_script_installed(self):
        script_exists = self.swm.adb_wrapper.test_path_existance_su(
            self.path_init_script
        )
        if script_exists:
            script_sha256 = self.swm.adb_wrapper.sha256sum(self.path_init_script)
            if script_sha256 == self.sha256_init_script:
                return True
            else:
                print(
                    "Warning: Termux init script exists (sha256: %s) but is not the same (sha256: %s). Reinstalling"
                    % (script_sha256, self.sha256_init_script)
                )
        else:
            print(
                "Warning: Termux init script '%s' does not exist. Installing"
                % self.path_init_script
            )
        return False

    def install_termux_init_script(self):
        installed = self.check_termux_init_script_installed()
        if not installed:
            print("Installing Termux init script")
            self.swm.adb_wrapper.write_file(
                self.path_init_script, self.content_init_script
            )
            ret = self.check_termux_init_script_installed()
            if ret:
                print("Termux init script installed successfully")
                return ret
            else:
                raise ValueError("Termux init script installation failed")
        else:
            print("Termux init script already installed")
            return True

    def install_termux(self):
        raise NotImplementedError("Termux app installation not implemented")

    def run(self, script_path: str):
        content = get_file_content(script_path)
        self.run_script(content)

    def run_script(self, content: str):
        remote_tmpdir = "/data/local/tmp"
        remote_tmp_script_path = f"{remote_tmpdir}/swm.sh"
        self.swm.adb_wrapper.write_file(remote_tmp_script_path, content)
        self.shell([remote_tmp_script_path], no_prefix=True)
        self.swm.adb_wrapper.remove_file(remote_tmp_script_path, confirm=False)

    def exec(self, executable: str):
        self.shell([executable])

    def get_termux_app_user(self):
        termux_app_data_path = "/data/data/com.termux"
        # check file permission
        user = self.swm.adb_wrapper.check_file_permission(termux_app_data_path)
        assert user
        return user

    def shell(
        self, shell_args: list[str] = [], no_prefix: bool = False, disable_selinux=False
    ):
        termux_installed = self.check_termux_installed()
        if not termux_installed:
            print("Termux not installed. Installing now...")
            self.install_termux()
        else:
            print("Termux already installed")
        assert self.install_termux_init_script()
        user = self.get_termux_app_user()
        termux_data_init_script = "/data/data/com.termux/termux_init.sh"
        self.swm.adb_wrapper.execute_su_cmd(
            "cp %s %s" % (self.path_init_script, termux_data_init_script)
        )
        if shell_args:
            if no_prefix:
                additional_args = " ".join(shell_args)
            else:
                additional_args = "-c '%s'" % " ".join(shell_args)
        else:
            additional_args = ""
        if disable_selinux:
            selinux_context = self.get_selinux_context()
            cmd = [
                "-t",  # by DeepSeek
                "su",
                "-c",
                "runcon %s su - %s -c 'sh %s %s'"
                % (
                    selinux_context,
                    user,
                    termux_data_init_script,
                    additional_args,
                ),  # ineffective after setenforce 1, since tmux socket is still not accessable afterwards despite all attributes are the same for the socket file
                # but works for normal file
            ]
            # disable selinux
            self.swm.adb_wrapper.disable_selinux()
        else:
            self.swm.adb_wrapper.enable_selinux()  # ok if just install app using apt, but we cannot remove it
            cmd = [
                "-t",  # by DeepSeek
                "su",
                "-",
                user,
                "-c",
                "sh %s %s" % (termux_data_init_script, additional_args),
            ]
        # cannot live with setenforce 1, or this process would die
        # could we just enable selinux back on once detached?
        # self.swm.adb_wrapper.enable_selinux_delayed(2)
        self.swm.adb_wrapper.execute_shell(cmd)


def create_default_config(cache_dir: str):
    return omegaconf.OmegaConf.create(
        {
            "cache_dir": cache_dir,
            "device": None,  # TODO: not storing this value here, but upsert it to local tinydb
            "zoom_factor": 1.0,
            "db_path": os.path.join(cache_dir, "apps.db"),
            "session_autosave": True,
            "android_session_storage_path": "/sdcard/.swm",
            "app_list_cache_update_interval": 60 * 60 * 24,  # 1 day
            "session_autosave_interval": 60 * 60,  # 1 hour
            "app_list_cache_path": os.path.join(cache_dir, "app_list_cache.json"),
            "github_mirrors": [
                "https://github.com",
                "https://bgithub.xyz",
                "https://kgithub.com",
            ],
            "launch_policy": "keep_new",  # keep_new, keep_old
            "restart_reasons": [
                "device_offline",
                "app_gone",
            ],
            "use_shared_app_config": True,
            "binaries": {
                "adb": {"version": "1.0.41"},
                "scrcpy": {"version": "3.3.1"},
                "fzf": {"version": "0.62.0"},
                "adbkeyboard": {"version": "2.0"},
                "beeshell": {"version": "1.0.3"},  # TODO: figure out version of apks
                "beanshell": {
                    "version": "2.1.1"
                },  # TODO: replace bsh gui with bsh cli (core) on github release, "java-jar.zip"
                "aapt": {"version": "v0.2"},
                "gboard": {"version": "15.5.8.766552071"},
            },
        }
    )


def get_config_path(cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    config_path = os.path.join(cache_dir, "config.yaml")
    return config_path


def load_or_create_config(cache_dir: str, config_path: str):
    if os.path.exists(config_path):
        print("Loading existing config from:", config_path)
        config = omegaconf.OmegaConf.load(config_path)
    else:
        print("Creating default config at:", config_path)
        config = create_default_config(cache_dir)
        omegaconf.OmegaConf.save(config, config_path)
    assert type(config) == omegaconf.DictConfig
    return config


def override_system_excepthook(
    program_specific_params: Dict, ignorable_exceptions: list
):
    import sys
    import traceback

    def custom_excepthook(exc_type, exc_value, exc_traceback):
        if exc_type not in ignorable_exceptions:
            traceback.print_exception(
                exc_type, exc_value, exc_traceback, file=sys.stderr
            )
            print("\nAn unhandled exception occurred, showing diagnostic info:")
            print_diagnostic_info(program_specific_params)

    sys.excepthook = custom_excepthook


def parse_args(cli_suggestion_limit: int):
    from docopt import docopt, DocoptExit
    import sys

    try:
        return docopt(__doc__, version=f"SWM {__version__}", options_first=True)
    except DocoptExit:
        # print the docstring
        print(DOCSTRING)
        # must be something wrong with the arguments
        argv = sys.argv
        user_input = "swm " + (" ".join(argv[1:]))
        show_suggestion_on_wrong_command(user_input, limit=cli_suggestion_limit)
        # TODO: configure "limit" in swm config yaml
    exit(1)


def main():
    import sys

    # Setup cache directory
    default_cache_dir = os.path.expanduser("~/.swm")

    SWM_CACHE_DIR = os.environ.get("SWM_CACHE_DIR", default_cache_dir)
    # TODO: Include environment variable documentation into help and error message
    os.makedirs(SWM_CACHE_DIR, exist_ok=True)
    CLI_SUGGESION_LIMIT = os.environ.get("SWM_CLI_SUGGESION_LIMIT", 1)
    CLI_SUGGESION_LIMIT = int(CLI_SUGGESION_LIMIT)
    # Parse CLI arguments
    args = parse_args(CLI_SUGGESION_LIMIT)

    config_path = args["--config"]
    if config_path:
        print("Using CLI given config path:", config_path)
    else:
        config_path = get_config_path(SWM_CACHE_DIR)
    # Load or create config
    config = load_or_create_config(SWM_CACHE_DIR, config_path)

    verbose = args["--verbose"]
    debug = args["--debug"]

    # Prepare diagnostic info
    program_specific_params = {
        "cache_dir": SWM_CACHE_DIR,
        "config": omegaconf.OmegaConf.to_container(config),
        "config_path": config_path,
        "argv": sys.argv,
        "parsed_args": args,
        "executable": sys.executable,
        "config_overriden_parameters": {},
        "verbose": verbose,
    }

    if verbose:
        print("Verbose mode on. Showing diagnostic info:")
        print_diagnostic_info(program_specific_params)

    if debug:
        print(
            "Debug mode on. Overriding system excepthook to capture unhandled exceptions."
        )
        override_system_excepthook(
            program_specific_params=program_specific_params,
            ignorable_exceptions=(
                [] if verbose else [NoDeviceError, NoSelectionError, NoBaseConfigError]
            ),
        )

    config.verbose = verbose
    config.debug = debug

    if args["init"]:
        # setup initial environment, download binaries
        force = args["force"]
        download_initial_binaries(SWM_CACHE_DIR, config.github_mirrors, force=force)
        return
    init_complete = check_init_complete(SWM_CACHE_DIR)
    if not init_complete:
        print(
            "Warning: Initialization incomplete. Consider running 'swm init' to download missing binaries."
        )
    # Initialize SWM core
    swm = SWM(config)

    # # Command routing
    # try:

    if args["repl"]:
        swm.repl()
        return
    elif args["healthcheck"]:
        swm.healthcheck()
        return
    elif args["adb"]:
        execute_subprogram(swm.adb, args["<adb_args>"])

    elif args["scrcpy"]:
        execute_subprogram(swm.scrcpy, args["<scrcpy_args>"])

    elif args["baseconfig"]:
        if args["show"]:
            if args["diagnostic"]:
                print_diagnostic_info(program_specific_params)
            else:
                print(omegaconf.OmegaConf.to_yaml(config))
        elif args["show-default"]:
            default_config = create_default_config(SWM_CACHE_DIR)
            print(omegaconf.OmegaConf.to_yaml(default_config))
        elif args["edit"]:
            # Implementation would open editor
            print("Opening config editor")
            edit_or_open_file(config_path)

    elif args["device"]:
        if args["list"]:
            last_used = args["last-used"]
            swm.device_manager.list(print_formatted=True, show_last_used=last_used)
        elif args["search"]:
            device = swm.device_manager.search()
            ans = prompt_for_option_selection(["select", "name"], "Choose an option:")
            if ans.lower() == "select":
                swm.device_manager.select(device)
            elif ans.lower() == "name":
                alias = input("Enter the alias for device %s:" % device)
                swm.device_manager.name(device, alias)
        elif args["select"]:
            swm.device_manager.select(args["<query>"])
        elif args["name"]:
            swm.device_manager.name(args["<device_id>"], args["<device_alias>"])

    elif args["--version"]:
        print(f"SWM version {__version__}")
    else:
        # Device specific branches

        # Handle device selection
        cli_device = args["--device"]
        config_device = config.device

        if cli_device is not None:
            default_device = cli_device
        else:
            default_device = config_device

        current_device = swm.infer_current_device(default_device)

        if current_device is not None:
            device_name = swm.adb_wrapper.get_device_name(
                current_device
            )  # could fail if status is not "device", such as "fastboot"
            print("Current device name:", device_name)
            swm.set_current_device(current_device)
            swm.load_swm_on_device_db()
        else:
            raise NoDeviceError("No available device")

        if args["app"]:
            if args['recent']:
                swm.app_manager.list_recent_apps(print_formatted=True)
            elif args["search"]:
                app_id = swm.app_manager.search(index=args["index"])
                with_type = args["with-type"]
                if app_id is None:
                    raise NoSelectionError("No app has been selected")
                print("Selected app: {}".format(app_id))
                ans = prompt_for_option_selection(
                    ["run", "config"], "Please select an action:"
                )
                if ans.lower() == "run":
                    init_config = input("Initial config name:")
                    run_in_new_display = input("Run in new display? (y/n, default: y):")
                    if run_in_new_display.lower() == "n":
                        no_new_display = True
                    else:
                        no_new_display = False
                    swm.app_manager.run(app_id, init_config=init_config)
                elif ans.lower() == "config":
                    opt = prompt_for_option_selection(
                        ["edit", "show"], "Please choose an option:"
                    )
                    if opt == "edit":
                        swm.app_manager.edit_app_config(app_id)
                    elif opt == "show":
                        swm.app_manager.show_app_config(app_id)
            elif args["most-used"]:
                limit = args.get("<count>", 10)
                if limit is None:
                    limit = 10
                limit = int(limit)
                swm.app_manager.list(most_used=limit, print_formatted=True, update_last_used=True)
            elif args["run"]:
                no_new_display = args["no-new-display"]
                query = args["<query>"]
                init_config = args["<init_config>"]
                # TODO: search with query instead
                app_id = swm.app_manager.resolve_app_query(query)
                swm.app_manager.run(
                    app_id,  # type: ignore
                    init_config=init_config,
                    new_display=not no_new_display,
                )

            elif args["config"]:
                config_name = args["<config_name>"]
                if args["list"]:
                    swm.app_manager.list_app_config(print_result=True)
                elif args["show"]:
                    swm.app_manager.show_app_config(config_name)
                elif args["show-default"]:
                    swm.app_manager.show_app_config("default")
                elif args["edit"]:
                    if config_name == "default":
                        raise ValueError("Cannot edit default config")
                    swm.app_manager.edit_app_config(config_name)
                elif args["copy"]:
                    swm.app_manager.copy_app_config(
                        args["<source_name>"], args["<target_name>"]
                    )
            elif args["list"]:
                update_cache = args[
                    "update"
                ]  # cache previous list result (alias, id), but last_used_time is always up-to-date
                with_type = args["with-type"]
                swm.app_manager.list(
                    print_formatted=True,
                    update_cache=update_cache,
                    drop_fields=dict(
                        last_used_time=args["with-last-used-time"],
                        type_symbol=with_type,
                    ),
                )
            else:
                ...
        elif args["ime"]:
            if args["list"]:
                swm.ime_manager.list(display=True)
            elif args["switch"]:
                query = args["<query>"]
                swm.ime_manager.switch(query)
            elif args["activate"]:
                query = args["<query>"]
                swm.ime_manager.activate(query)
            elif args["deactivate"]:
                query = args["<query>"]
                swm.ime_manager.deactivate(query)
            elif args["search"]:
                ime_id = swm.ime_manager.search()
                options = ["activate", "deactivate", "switch"]
                opt = prompt_for_option_selection(options, "Select an option:")
                if opt == "activate":
                    swm.ime_manager.activate(ime_id)
                elif opt == "deactivate":
                    swm.ime_manager.deactivate(ime_id)
                elif opt == "switch":
                    swm.ime_manager.switch(ime_id)
            elif args["switch-to-previous"]:
                swm.ime_manager.switch_to_previous()
            else:
                ...
        elif args["java"]:
            # TODO: use beanshell instead of beeshell
            # adb shell "CLASSPATH=/data/local/tmp/bsh-2.0b6.jar app_process /system/bin bsh.Interpreter -c 'import android.graphics.*; print(Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888));'"
            if args["run"]:
                script_path = args["<script_path>"]
                # run the script
                swm.java_manager.run(script_path)
            elif args["shell"]:
                shell_args = args["<shell_args>"]
                swm.java_manager.shell(shell_args)
            else:
                ...
        elif args["termux"]:
            if args["run"]:
                script_path = args["<script_path>"]
                swm.termux_manager.run(script_path)
            elif args["exec"]:
                executable = args["<executable>"]
                swm.termux_manager.exec(executable)
            elif args["shell"]:
                shell_args = args["<shell_args>"]
                if shell_args:
                    script_content = " ".join(shell_args)
                    swm.termux_manager.run_script(script_content)
                else:
                    swm.termux_manager.shell()
            else:
                ...
        elif args["mount"]:
            print("Warning: 'mount' is not implemented yet")
        elif args["session"]:
            if args["list"]:
                last_used = args["last-used"]
                swm.session_manager.list(show_last_used=last_used, print_formatted=True)
            elif args["search"]:
                session_name = swm.session_manager.search()
                opt = prompt_for_option_selection(
                    ["restore", "delete"], "Please specify an action:"
                )
                if opt == "restore":
                    swm.session_manager.restore(session_name)
                elif opt == "delete":
                    swm.session_manager.delete(session_name)

            elif args["save"]:
                swm.session_manager.save(args["<session_name>"])

            elif args["restore"]:
                query = args["<query>"]
                if query is None:
                    query = "default"
                session_name = swm.session_manager.resolve_session_query(query)
                swm.session_manager.restore(session_name)

            elif args["delete"]:
                session_name = swm.session_manager.resolve_session_query(
                    args["<query>"]
                )
                swm.session_manager.delete(session_name)
            else:
                ...  # Implement other device specific commands

    # except Exception as e:
    #     print(f"Error: {e}")
    #     if args["--verbose"]:
    #         traceback.print_exc()


if __name__ == "__main__":
    main()
