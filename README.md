![Creative Commons BY SA](https://i.creativecommons.org/l/by-sa/4.0/80x15.png)

# Modpack Helper

Since Curse doesn't release any modpack installers for servers, this script aim to ease the deployement of modded Minecraft servers.

It is not intended as a replacement for CurseClient or CurseVoice installer, nor any future product released by them.

Inspired by [curseDownloader](https://github.com/portablejim/curseDownloader)

## Features

- Automatically download required mods
- Deploy the custom configuration for the modpack
- Handle Forge installation for MC 1.6, 1.7 and 1.8
- Preserve the previous mod configuration (optional)
- Blacklist some mods from being installed, _ie._ clientside only mods (optional)

## Dependencies

Python 3.4 or newer

## Usage

You first require the path to a Curse modpack or a download link to it.  

For a basic usage, in the server directory execute:
```bash
path/to/modpack-helper.py PATH_OR_URL
```

There are more options, you can see them by running `modpack-helper.py -h`. The `-j` option should speed things up.

### Example

```bash
mkdir ftb-unstable-1.8
cd ftb-unstable-1.8

# Those are clienside only mods
echo 'LLOverlayReloaded*
CustomMainMenu*
ResourceLoader*
' > mod_blacklist.txt

path/to/modpack-helper.py -j 25 -e mod_blacklist.txt http://addons-origin.cursecdn.com/files/2279/786/FTBUnstable18-3.0.18-1.8.9.zip

# Launch the server unsing the symlink
java -jar minecraft_server.jar
```

## Issues

Mods are downloaded from the public facing website of CurseForge. That means that any mods no longer available there (*humekanismhum hum*) will fail to download.
Some modpack are therefore impossible to install for now.

## Disclaimer

I made this script primarly for my own usage: if you encounter a problem you can create an issue but I may not respond.
It might (read: *will*) be completely broken in the future, if Curse or Forge change their websites.
Feel free to fork it of course.

This script downloads and executes code from potentially __UNTRUSTED__ sources, over HTTP, without verification of any kind.
You should probably read it before you use it, and not trust the author.

## License

This project is released under the Creative Commons BY SA
