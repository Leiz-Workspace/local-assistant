"""Run the Local Assistant CLI through uv without requiring shell aliases."""

from apps.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
