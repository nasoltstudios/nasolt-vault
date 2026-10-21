"""Compatibility entry point for the Windows build script."""

from scripts.build_windows import main


if __name__ == "__main__":
    raise SystemExit(main())
