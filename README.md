# Smart File Organizer

A powerful, lightweight command-line tool that automatically organizes your messy folders by file type, date, or custom rules. Built for developers and anyone tired of a cluttered Downloads folder.

[![PyPI version](https://img.shields.io/pypi/v/smart-file-organizer)](https://pypi.org/project/smart-file-organizer/)
[![Python versions](https://img.shields.io/pypi/pyversions/smart-file-organizer)](https://pypi.org/project/smart-file-organizer/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 🗂️ **Smart categorization** - Automatically sorts files into Documents, Images, Videos, Audio, Code, Archives, etc.
- 📅 **Date-based organization** - Group files by year, month, or week
- ⚙️ **Custom rules** - Define your own folder structure based on extensions, size, or date
- 🛡️ **Dry-run mode** - Preview changes before moving anything
- ⚡ **Fast and lightweight** - No heavy dependencies, works on any folder
- 🌍 **Cross-platform** - Works on Windows, macOS, and Linux

## Installation

```bash
pip install smart-file-organizer
```

## Quick Start

Organize your Downloads folder by file type:

```bash
organize ~/Downloads --by type
```

Organize by date (year/month):

```bash
organize ~/Downloads --by date
```

Preview what would happen without moving files:

```bash
organize ~/Downloads --by type --dry-run
```

## Usage

```
organize <path> [OPTIONS]

Options:
  --by [type|date|size]   Organize by file type, date, or file size
  --dry-run               Preview changes without moving files
  --recursive             Also process subdirectories
  --config PATH           Use a custom configuration file
  --undo                  Undo the last organization run
  -v, --verbose           Show detailed output
  -h, --help              Show this help message
```

## How It Works

Smart File Organizer scans your target directory and moves files into categorized subfolders based on their extension or metadata. It keeps a log of every move so you can undo changes if needed.

### Default Categories

| Category | Extensions |
|----------|-----------|
| Documents | .pdf, .doc, .docx, .txt, .md, .ppt, .pptx, .xls, .xlsx, .csv |
| Images | .jpg, .jpeg, .png, .gif, .bmp, .svg, .webp, .tiff |
| Videos | .mp4, .mov, .avi, .mkv, .flv, .wmv, .webm |
| Audio | .mp3, .wav, .flac, .aac, .ogg, .m4a |
| Code | .py, .js, .ts, .html, .css, .java, .cpp, .go, .rs |
| Archives | .zip, .tar, .gz, .rar, .7z |
| Executables | .exe, .msi, .dmg, .deb, .rpm |

## Configuration

Create a `.organizer.yml` file in your project directory to customize categories:

```yaml
categories:
  Documents:
    - .pdf
    - .doc
    - .docx
  Images:
    - .jpg
    - .png
    - .gif
  MyCustomCategory:
    - .xyz
    - .abc
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) file for details.
