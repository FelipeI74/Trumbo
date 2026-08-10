# Sophocles 2007 — binary facts

## Directly established from the supplied installer

The supplied `soph2007.exe` is a PE32 x86 Windows GUI installer. Its resources contain the actual Sophocles application, compiled as a separate PE32 executable.

The extracted application has four major PE sections:

- `.text` — executable code, about 2.8 MB
- `.rdata` — read-only data/RTTI/string data, about 0.75 MB
- `.data` — mutable data
- `.rsrc` — Windows resources, about 1.7 MB

The executable imports classic Win32/MFC-era APIs including USER32, GDI32, COMCTL32, OLE32/OLEAUT32, SHELL32, WINSPOOL, WINMM and WS2_32.

Compiler/toolchain strings directly reference Visual Studio 8 ATL/MFC headers and MFC source locations. RTTI names show hundreds of MFC/C++ classes.

## Installer resources recovered

The installer contains, among other resources:

- embedded Sophocles HTML Help (`Sophocles.chm`), about 2.1 MB
- compressed Sophocles application executable, original size 5,519,048 bytes
- uninstaller executable
- update agent executable
- screenplay/setup templates
- several bundled typefaces

The bundled typefaces were identified during analysis but are not included in this handoff package.

## What was not recovered

The original `.cpp`, `.h`, Visual Studio solution/project files, comments, original variable names, and complete function symbols are not present. Any implementation for Trumbo should therefore be a clean reimplementation of observed behavior, not a claim of recovered original source.
