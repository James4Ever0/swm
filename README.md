
<div align="center">
<img src="https://raw.githubusercontent.com/james4ever0/swm/main/logo/logo.png" alt="logo" width="200"/>

<h1>Scrcpy Window Manager</h1>
<p align="center">
<a href="https://github.com/james4ever0/swm/blob/master/LICENSE"><img alt="License: WTFPL" src="https://img.shields.io/badge/license-UNLICENSE-green.svg?style=flat"></a>
<a href="https://pypi.org/project/swm-android/"><img alt="PyPI" src="https://img.shields.io/pypi/v/swm-android"></a>
<a href="https://deepwiki.com/James4Ever0/swm"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
<a href="https://pepy.tech/projects/swm-android"><img src="https://static.pepy.tech/badge/swm-android" alt="PyPI Downloads"></a>
<a href="https://github.com/james4ever0/swm"><img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
</p>
</div>

## Use cases

- Improve ergonimics
- Use your phone at work
- Share data between PC and Android device
- Bring your work wherever you go
- Experience something like Samsung Dex
- Boost productivity by multi-tasking on Android

## Requirements

Your Android version must be 10.0 or higher.

USB debugging (ADB) must be enabled.

Your phone needs to be rooted, and `com.android.shell` must have root permission.

## Features

- Multi-window, multi-application support
- Fuzzy search interface for managing apps, sessions, input methods, etc.
- Session persistance
- Reopen applications at device reconnection
- Config file customization
- PC-side UTF-8 input method support
- "Did you mean" suggestions when encountered a wrong command

## Installation

This application is running on your PC, with your Android device connected to it via ADB.

Using `pip`:

```bash
pip install swm-android
```

## Command line

```
SWM - Scrcpy Window Manager

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
```

## Demo

### App fuzzy run
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-app-run-fuzzy.gif "App fuzzy search")

### App search and run
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-app-search-and-run.gif "App search and run")

### Chrome demo
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-chrome-demo.gif "Chrome demo")

### Device status
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-device-status.gif "Device status")

### Java shell
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-java-shell.gif "Java shell")

### List IME
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-list-ime.gif "List IME")

### Search
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-search.gif "Search")

### Termux demo
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-termux-demo.gif "Termux demo")

### Termux shell
![Gif image](https://raw.githubusercontent.com/james4ever0/swm/main/gif/swm-termux-shell.gif "Termux shell")

## Related projects

[scrcpy-wrapper](https://github.com/Bluemangoo/scrcpy-wrapper)

[pyscrcpy](https://github.com/yixinNB/pyscrcpy)

[MYScrcpy](https://github.com/me2sy/MYScrcpy)

[Vysor](https://github.com/koush/vysor.io)
