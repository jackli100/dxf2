# dxf-mileage-tool

This repository contains two small utilities built with **Python 3** for working with
drawing exchange files (DXF). The scripts use `ezdxf` and `pandas` and are
targeted at railway drawings where mileage and power line data are stored in
specific layers.

## Tools

### `rail_power.py`
Calculates the mileage and right-side angle of each intersection between railway
center lines and power line polylines. The script automatically searches all
layers beginning with "电力" (electric power) and outputs a spreadsheet with the
following columns:

- `Mileage_m` – the mileage in metres along the railway.
- `Angle` – the right-side angle formatted as degrees and minutes.
- `Remark` – free text extracted from the layer name.

Edit the constants at the top of the file to set the input DXF path and the
mileage offset for each railway layer. Run the script with `python rail_power.py`
and an Excel file named `<input>.rail_power_dynamic.xlsx` will be generated.

### `rail_power_draw.py`
Reads a mileage‑angle table (Excel or CSV) and draws annotation polylines on the
designated railway layers in the DXF file. Important configuration options at the
start of the file include:

- `RAIL_LAYERS` – mapping of railway layer names to mileage offsets.
- `DXF_FILE` – path to the DXF file to modify.
- `TABLE_FILE` – mileage/angle table to read.
- `ANNOT_LENGTH` – length of the annotation line in metres.
- `ANNOT_LAYER` – layer name used for the generated annotations.

Execute `python rail_power_draw.py` after configuring the paths and the script
will save a new DXF with annotations added.


### `extract_closed_polyline_text.py`

Extracts single line text entities located inside closed polylines on the
demolition layer of `room_and_number.dxf`. Each label is projected
perpendicularly onto the railway alignment from `break.dxf` to obtain its
mileage. The text content, polyline vertices and mileage are written to
`room_and_number_extracted.csv`.

Run `python extract_closed_polyline_text.py` and the CSV will be produced if
matching features are found.

## Installation
1. Install Python 3.8 or higher.
2. Install dependencies:
   ```bash
   pip install ezdxf pandas
   ```

## Sample Data
A small sample DXF file `break.dxf` is included for testing purposes. Replace it
with your own drawing when running the scripts on real data.

## License
This project is released into the public domain without warranty of any kind.


## Usage
Edit the variables at the top of each script to point to your DXF file and, for
`rail_power_draw.py`, the mileage-angle table. Then run one of the scripts from
command line:
```bash
python rail_power.py
python rail_power_draw.py
python extract_closed_polyline_text.py

