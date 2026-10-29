import os, re, sys
import argparse
import subprocess
import difflib
import random

from pydicom.uid import generate_uid
from pydicom import dcmread

from modules.dirutil import dcmdir
from modules import dcmutil

def main():
    cli_options = CLI()

    executeOptions(cli_options)

def executeOptions(cli_options):
    if "print" in cli_options:
        execPrint(cli_options["print"])

    if "find_tag" in cli_options:
        execFind(cli_options["find_tag"])

    if "modify" in  cli_options:
        modify = cli_options["modify"]
        target = cli_options["target"]
        studySeries = tuple(map(int, cli_options["study/series"]))

        if "copy_original" in cli_options:
            cpy_orig = cli_options["copy_original"]
        else:
            cpy_orig = False
        
        force_remove_required = cli_options.get("force_remove_required", False)

        execModify(modify, target, studySeries, cpy_orig, force_remove_required)

    if "compare_dcm" in cli_options:
        paths = cli_options["compare_dcm"]
        execCompare(paths)

def execCompare(paths):
    rep = []

    for dcm_path in paths:
        dcm = dcmutil.dcm(dcm_path)
        rep.append(dcm.getLinesFromDcm())

    diff = difflib.Differ()

    for line in diff.compare(rep[0], rep[1]):
        # Print only the difference
        if line.startswith("-"):
            print(f"DICOM 1: {line}")
        elif line.startswith("+"):
            print(f"DICOM 2: {line}")

def execModify(modify, target, studySeries, cpyOrig, forceRemoveRequired=False):
    src = target[0]
    dest = target[1]

    if len(modify) == 1 and os.path.isfile(modify[0]) and modify[0].endswith(".txt"):
        pairs, patientNameTag = modifyWithTxt(modify[0])
    else:
        sys.exit("NO SUPPORT FOR PROVIED INPUT!")

    deferred_removals = []
    if forceRemoveRequired:
        pairs, deferred_removals = deferRemovalPairs(pairs)

    # Reuse the anonymized patient/study if the destination already contains one.
    IDs = getExistingIDs(dest) or newIDs()
    # new Series ID:
    seriesID = newSeriesID()

    pairs.extend(IDs)
    pairs.append(seriesID)

    # Check if tags are modifiable and values are valid:
    mods = validMods(pairs)
    if not mods:
        sys.exit(f"Text file u provided does not have anything to modify: {modify[0]}")

    # Open DICOMDIR modify said tags:
    dir = dcmdir(src)
    modified_paths, readme_path = dir.modifySeries(studySeries, mods, dest)

    if cpyOrig:
        req_pairs = IDs.copy()
        req_pairs.append(newSeriesID())
        req_pairs.extend(newSeriesDesc())

        if patientNameTag and not isRemovalPair(patientNameTag):
            req_pairs.append(patientNameTag)

        mods = validMods(req_pairs)
        dir.modifySeries(studySeries, mods, dest, orig=True)

    createDcmdir(os.path.join(dest, "Scan"))

    if deferred_removals:
        removal_mods = validMods(deferred_removals, allowUnmodifiable=True)
        applyDeferredRemovals(modified_paths, removal_mods, readme_path)

def isRemovalPair(pair):
    return pair[1].strip().lower() == "remove"

def deferRemovalPairs(pairs):
    regular_pairs = []
    removal_pairs = []

    for pair in pairs:
        if isRemovalPair(pair):
            removal_pairs.append((pair[0], "remove"))
        else:
            regular_pairs.append(pair)

    return regular_pairs, removal_pairs

def applyDeferredRemovals(dicomPaths, mods, readmePath):
    for path in dicomPaths:
        dcm = dcmutil.dcm(path)
        dcm.modifyTag(mods, readmePath, regenerateSopInstanceUid=False)
        dcm.saveInPlace()

def newIDs():
    pairs = [
        ("PatientID", str(random.randint(1_000_000, 9_999_999))),
        ("StudyID", str(random.randint(1_000_000, 9_999_999))),
        ("StudyInstanceUID", generate_uid())
    ]
    return pairs

def newSeriesID():
    return ("SeriesInstanceUID", generate_uid()) 

def getExistingIDs(dest):
    scan_dir = os.path.join(dest, "Scan")

    if not os.path.isdir(scan_dir):
        return None

    for root, _, files in os.walk(scan_dir):
        for filename in sorted(files):
            if filename == "DICOMDIR":
                continue

            path = os.path.join(root, filename)

            try:
                ds = dcmread(path, stop_before_pixels=True)
            except Exception:
                continue

            required = ("PatientID", "StudyID", "StudyInstanceUID")
            if all(hasattr(ds, tag) for tag in required):
                return [
                    ("PatientID", str(ds.PatientID)),
                    ("StudyID", str(ds.StudyID)),
                    ("StudyInstanceUID", str(ds.StudyInstanceUID))
                ]

    return None

def newSeriesDesc():
    pairs = [
        ("SeriesDescription", "Original valid series"),
        ("SeriesNumber", "8")
    ]
    return pairs

def validMods(pairs, allowUnmodifiable=False):
    valid_mods = []

    for i, (tag_str, value) in enumerate(pairs, start=1):
        tag = dcmutil.dcmTag(tag_str)

        if not tag.exists():
            print(f"**WARNING**  Line {i}: Tag {tag_str} does not exist in DICOM standard, skipping.")
            continue

        if tag.pydicom_tag in tag.unmodifiable_tags and not allowUnmodifiable:
            print(f"**WARNING**  Line {i}: Tag {tag_str} is unmodifiable, skipping.")
            continue
        
        if not tag.goodTagValue(value):
            print(f"**WARNING** Line {i}: Invalid value '{value}' for tag {tag_str} — skipping.")
            continue

        valid_mods.append((tag, value))

    return valid_mods

def modifyWithTxt(file):
    pairs = []
    patientNamePair = None
    try:
        with open(file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if "=" not in line:
                    sys.exit(f"txt file lines need to be of format: [TAG] = [VALUE]")
                
                tag, value = map(str.strip, line.split("=", 1))

                if not re.match(r"^[0-9A-Fa-f]{4},?[0-9A-Fa-f]{4}$", tag) and not re.match(r"^[A-Za-z_]+$", tag):
                    sys.exit(f"Invalid tag format at line {i}: '{tag}'")

                pairs.append((tag, value))

                # If name changed, store separately:
                if tag in ("0010,0010", "PatientName"):
                    patientNamePair = (tag, value)
            
    except FileNotFoundError:
        sys.exit(f"File not found: {file}")
    except Exception as e:
        sys.exit(f"Failed to read file '{file}': {e}")

    if not pairs:
        sys.exit(f"No valid tag/value pairs found in {file}")

    return pairs, patientNamePair

def CLI():
    parser = argparse.ArgumentParser(description="dcmmod = python script for modifying DICOMDIR and DICOM files")
    cli_options = {}

    # Optional arguments:
    parser.add_argument("-p", help="Print DICOMDIR or DICOM contents (-p [DICOMDIR])")
    parser.add_argument("-m", nargs="+", help="Modify a DICOM tag (-m [TAG] [VALUE]), requires options:\n\t-\"-t\", target\n\t-\"-s\", study and series number ")
    parser.add_argument("-s", nargs=2, help="Specify study number and series number (-s [STUDY_NUM] [SERIES_NUM])")
    parser.add_argument("-v", action="store_true", help="If option \"-s\" has been selected, it will incorporate original (valid) series")
    parser.add_argument("-t", nargs=2, help="path to old DICOMDIR and path to new DICOMDIR (-t [SRC_DICOMDIR] [DEST_DICOMDIR])")
    parser.add_argument("-f", nargs="+", help="Find one or more tags in a DICOM (-f [TAG1] [TAG2]... [DCM_PATH]) or [-f [.txt_PATH] [DCM_PATH]]")
    parser.add_argument("-d", nargs=2, help="Compare 2 DICOM files (-d [DICOM1] [DICOM2])")
    parser.add_argument(
        "--force-remove-required",
        action="store_true",
        help=(
            "Allow removal of required or normally protected tags. Remove operations are "
            "applied after DICOMDIR creation so the generated study remains importable."
        )
    )

    args = parser.parse_args()

    # Convert Namespace to a dictionary
    args_dict = vars(args)
    # Check if any argument has been provided (non-None)
    if not any(value is not None for value in args_dict.values()):
        sys.exit("No options have been provided")

    mod_args = [args.m, args.t, args.s]
    provided = [arg is not None for arg in mod_args]

    if any(provided) and not all(provided):
        missing = []

        if args.m is None: missing.append("-m")
        if args.t is None: missing.append("-t")
        if args.s is None: missing.append("-s")

        sys.exit(f"The following arguments are required to modify a file: {', '.join(missing)}")

    elif all(provided):
        cli_options["modify"] = args.m
        cli_options["target"] = [args.t[0], args.t[1]]
        cli_options["study/series"] = [args.s[0], args.s[1]]
        cli_options["readme"] = True
        cli_options["force_remove_required"] = args.force_remove_required
    
    if args.v and all(provided):
        cli_options["copy_original"] = True
    elif args.v and any(provided):
        sys.exit(f"Option \"-v\" can only be provided with \"-m\" option!")

    if args.force_remove_required and not all(provided):
        sys.exit("Option \"--force-remove-required\" can only be provided with \"-m\" option!")

    if args.p:
        cli_options["print"] = args.p

    if args.d is not None:
        if len(args.d) != 2:
            sys.exit("For option '-d' both DICOM file paths need to be specified!")
        cli_options["compare_dcm"] = args.d
    
    if args.f is not None:
        if len(args.f) < 2:
            sys.exit("For option '-f' both Tag and DICOM path need to be specified!")
        cli_options["find_tag"] = args.f

    return cli_options

def execPrint(path):
    if "DICOMDIR" in  path:
        dir = dcmdir(path)
        dir.printStudiesList()
    elif path.lower().endswith((".dcm", ".dicom")) or not os.path.splitext(path)[1]:
        dcm = dcmutil.dcm(path)
        print(dcm.ds)
    else:
        sys.exit(f"**ERROR** Provided path is not a DICOMDIR nor a DICOM: {path}")

def execFind(find):
    # Detect if argument is a txt file:
    if len(find) == 2 and os.path.isfile(find[0]) and find[0].endswith(".txt"):
        input_tags = findFromTxt(find[0])
        tags = [dcmutil.dcmTag(tag) for tag in input_tags]
    else:
        tags = [dcmutil.dcmTag(tag) for tag in find[:-1]]

    dcm = dcmutil.dcm(find[-1])

    for tag in tags:
        dcm.findTag(tag.pydicom_tag)

def findFromTxt(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            tags = [line.strip() for line in f if line.strip()]
        return tags
    except:
        sys.exit(f"Could not open provided txt file: {file}")

def createDcmdir(DICOM_src):
    src = str(DICOM_src)

    if src.endswith("/"):
        dest = src + "DICOMDIR"
    else:
        dest = src + "/DICOMDIR"

    # Rebuilding into the same folder must start from a clean DICOMDIR,
    # otherwise dcmmkdir will recurse into the previous file and try to add it.
    if os.path.exists(dest):
        os.remove(dest)

    subprocess.run([
        "dcmmkdir",
        "--recurse",
        "--input-directory", src,
        "--output-file", dest
    ], check=True)

main()
