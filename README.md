
<div align="center">
<img src="https://raw.githubusercontent.com/james4ever0/swm/main/logo/logo.png" alt="logo" width="200"/>

<h1>Scrcpy Window Manager</h1>
</div>

## Use cases

- Want to work but cannot put down your phone
- Share data between PC and Android device
- Bring your work wherever you go
- Want to experience something like Samsung Dex but do not have a compatible device
- A more ergonomic way of using your Android phone, especially for professional Android users
- Boost productivity by multi-tasking on Android

## Installation

Using `pip`:

```bash
pip install swm-android
```


## Commandline

```
SWM - Scrcpy Window Manager

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

```