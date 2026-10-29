# dcmmod

A Python command-line program for inspecting and modifying DICOM files and DICOMDIRs.

## Requirements

- Python 3.12 or newer
- DCMTK installed, with the `dcmmkdir` command available on your `PATH`. The program uses it to create a DICOMDIR; it is a system program and is not installed by `pip`.

## Setup

Open a terminal in the project directory, then create and activate a virtual environment:

```bash
python -m venv .venv
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the Python dependencies into that environment:

```bash
python -m pip install -r requirements.txt
```

## Run

Show the command-line options:

```bash
python dcmmod.py --help
```

For example, print a DICOMDIR or DICOM file:

```bash
python dcmmod.py -p /path/to/DICOMDIR
```

Keep the virtual environment activated while using the program. To leave it, run `deactivate`.

## Usage examples

Run these commands from the project directory with the virtual environment activated.

Print the studies and series listed in a DICOMDIR:

```bash
python dcmmod.py -p /path/to/input/DICOMDIR
```

Find tags in a DICOM file:

```bash
python dcmmod.py -f PatientName StudyDescription /path/to/input/image.dcm
```

Compare two DICOM files and show their differences:

```bash
python dcmmod.py -d /path/to/first.dcm /path/to/second.dcm
```

### Modify several tags from a text file

Create a text file such as `tag_changes.txt`, with one `tag = value` pair per line. Use a tag keyword or an eight digit hexadecimal tag (for example, `0010,0010`). Lines beginning with `#` and blank lines are ignored.

```text
# Change existing values
PatientName = Example^Patient
StudyDescription = Demonstration study

# Add this tag if it is missing, or change it if it exists
AccessionNumber = DEMO-001

# Remove this tag if it exists
PatientComments = remove
```

First print the source DICOMDIR to find the study and series numbers. Then pass the text file, source DICOMDIR, output directory, and those numbers:

```bash
python dcmmod.py -m tag_changes.txt -t /path/to/input/DICOMDIR /path/to/output -s 1 1
```

Replace `1 1` with the study and series numbers shown by the DICOMDIR listing. The modified files and rebuilt DICOMDIR are written beneath `/path/to/output/Scan/`. The literal value `remove` deletes a tag when present. The program also assigns new identifiers to the modified series.
