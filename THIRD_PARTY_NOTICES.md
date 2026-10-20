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
package metadata used for source testing. Direct runtime versions are pinned
in `requirements.txt`; transitive versions below record that test environment.
A future binary release must
regenerate this list for its exact build and include runtime notices in the
distributed package.

| Package | Local version | License evidence in this tree |
|---|---:|---|
| CustomTkinter | 6.0.0 | `third_party_licenses/customtkinter-6.0.0/LICENSE` (CC0) |
| darkdetect | 0.8.0 | `third_party_licenses/darkdetect-0.8.0/LICENSE` (BSD-3-Clause) |
| Pillow | 12.3.0 | `third_party_licenses/Pillow-12.3.0/LICENSE` (Pillow license) |
| cryptography | 50.0.2 | `third_party_licenses/cryptography-50.0.2/` (Apache-2.0 OR BSD-3-Clause) |
| argon2-cffi | 25.1.0 | `third_party_licenses/argon2-cffi-25.1.0/LICENSE` (MIT) |
| argon2-cffi-bindings | 26.1.0 | `third_party_licenses/argon2-cffi-bindings-26.1.0/LICENSE` (MIT) |
| cffi | 2.1.1 | `third_party_licenses/cffi-2.1.1/LICENSE` (MIT) |
| pycparser | 3.0 | `third_party_licenses/pycparser-3.0/LICENSE` (BSD-3-Clause) |
| packaging | 26.3 | `third_party_licenses/packaging-26.3/` (Apache-2.0 OR BSD-2-Clause) |
| pyperclip | 1.11.0 | `third_party_licenses/pyperclip-1.11.0/` (BSD) |
| PyInstaller build tool | 6.22.3 | `third_party_licenses/PyInstaller-6.22.3/COPYING.txt` (GPL with bundling exception) |

The source install may resolve different transitive versions on another system;
their license texts must be checked against those actual versions. Python, Tcl/Tk, native extension
binaries, fonts, and any NSIS installer runtime need a full binary notice
inventory before distributing a Windows installer or executable. The original
project source and app icon are licensed under the root MIT `LICENSE`; the
Lucide/Feather artwork and dependencies retain the licenses above.
