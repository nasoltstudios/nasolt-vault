# Third-party notices and source inventory

This source tree retains 39 UI PNGs generated from Lucide icons via Iconify.
The [Lucide license](https://lucide.dev/license) is ISC; some Lucide icons
derive from Feather under MIT. Both copyright and permission notices are in
`third_party_licenses/LUCIDE-AND-FEATHER.txt`. The exact source package version
used by the earlier generator was not recorded. No third-party brand logos are
bundled. The Nasolt Studios README logo was supplied by the project owner; the
application draws original account monograms locally for recognized names and
initial avatars for other entries. The app icon pack was generated for this
project and can be rebuilt from its master image with `tools/make_icon.py`.

The following license texts were copied from the locally installed Python
package metadata used for source testing. Reviewed runtime and build Python
versions are pinned in `requirements.txt` and `requirements-build.txt`.
A future binary release must
regenerate this list for its exact build and include runtime notices in the
distributed package.

| Package | Local version | License evidence in this tree |
|---|---:|---|
| CustomTkinter | 6.0.0 | `third_party_licenses/customtkinter-6.0.0/LICENSE` (MIT, copyright 2023 Tom Schimansky) |
| darkdetect | 0.8.0 | `third_party_licenses/darkdetect-0.8.0/LICENSE` (BSD-3-Clause) |
| Pillow | 13.0.0 | `third_party_licenses/Pillow-13.0.0/LICENSE` (MIT-CMU) |
| cryptography | 50.0.2 | `third_party_licenses/cryptography-50.0.2/` (Apache-2.0 OR BSD-3-Clause) |
| argon2-cffi | 25.1.0 | `third_party_licenses/argon2-cffi-25.1.0/LICENSE` (MIT) |
| argon2-cffi-bindings | 26.1.0 | `third_party_licenses/argon2-cffi-bindings-26.1.0/LICENSE` (MIT) |
| cffi | 2.1.1 | `third_party_licenses/cffi-2.1.1/LICENSE` (MIT-0) |
| pycparser | 3.11 | `third_party_licenses/pycparser-3.11/LICENSE` (BSD-3-Clause) |
| packaging | 26.3 | `third_party_licenses/packaging-26.3/` (Apache-2.0 OR BSD-2-Clause) |
| pyperclip | 1.11.0 | `third_party_licenses/pyperclip-1.11.0/` (BSD) |
| PyInstaller build tool | 6.22.3 | `third_party_licenses/PyInstaller-6.22.3/COPYING.txt` (GPL with bundling exception) |
| altgraph build dependency | 0.17.5 | `third_party_licenses/altgraph-0.17.5/LICENSE` (MIT) |
| pefile build dependency | 2024.8.26 | `third_party_licenses/pefile-2024.8.26/LICENSE` (MIT) |
| PyInstaller Community Hooks build dependency | 2026.9 | `third_party_licenses/pyinstaller-hooks-contrib-2026.9/LICENSE` (GPL-2.0-or-later hooks; Apache-2.0 runtime hooks) |
| pywin32-ctypes build dependency | 0.2.3 | `third_party_licenses/pywin32-ctypes-0.2.3/LICENSE.txt` (BSD-3-Clause) |
| setuptools build dependency | 84.2.1 | `third_party_licenses/setuptools-84.2.1/LICENSE` (MIT; bundled vendor notices need binary review) |

Platform-specific dependencies can still differ on another system; their
license texts must be checked against the actual build. Python, Tcl/Tk, native extension
binaries, fonts, and any NSIS installer runtime need a full binary notice
inventory before distributing a Windows installer or executable. The original
project source and app icon are licensed under the root MIT `LICENSE`; the
Lucide/Feather artwork and dependencies retain the licenses above.

`requirements.txt` and `requirements-build.txt` pin the current direct and
resolved Python dependencies, but not wheel hashes, Python/Tcl/Tk, or NSIS.
A reproducible binary release needs an exact wheel inventory and desktop test.
