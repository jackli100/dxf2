#!/usr/bin/env python
"""List all TEXT entities in a DXF and report how many there are."""

from pathlib import Path
import ezdxf

DXF_FILE = "room_and_number.dxf"  # change if needed


def main():
    path = Path(DXF_FILE)
    if not path.exists():
        print(f"DXF not found: {path}")
        return
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    texts = list(msp.query("TEXT"))
    print(f"Found {len(texts)} TEXT entities in {path.name}")


if __name__ == "__main__":
    main()
