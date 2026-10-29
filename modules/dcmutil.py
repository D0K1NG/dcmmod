import pathlib
import sys
import os
import re

from pydicom.datadict import dictionary_VR, dictionary_description, dictionary_has_tag
from pydicom.uid import generate_uid, JPEG2000
from pydicom.tag import Tag, BaseTag
from pydicom import dcmread


TRANSFER_SYNTAX_TAG = Tag(0x0002, 0x0010)

class dcm:
    def __init__(self, dcm_path):
        self.path = dcm_path
        self.ds = self.Open()

    def Open(self):
        if not isinstance(self.path, pathlib.Path):
            try:
                self.path = pathlib.Path(self.path)
            except:
                sys.exit(f"**ERROR** Provided path is not legitimate: {self.path}")

        if "DICOMDIR" in str(self.path):
            sys.exit("**ERROR** This is a DICOMDIR, not a .dcm file!")

        try:
            ds = dcmread(self.path)
        except:
            sys.exit(f"**ERROR** Could not open dcm file: {self.path}")
        
        return ds

    def changeTransferSyntax(self, tag, value):
        from pydicom.encaps import encapsulate
        from pydicom.sequence import Sequence
        import imageio as iio
        import io
        import numpy as np

        if value == JPEG2000:
            # Compress to JPEG2000:
            arr = self.ds.pixel_array.astype(np.uint16)
            buffer = io.BytesIO()
            iio.imwrite(buffer, arr, format="j2k", compression="jpeg2000")
            encoded = buffer.getvalue()
            frames = [encoded]

            # Update transfer syntax:
            self.ds.file_meta.TransferSyntaxUID = JPEG2000
            self.ds.is_little_endian = True
            self.ds.is_implicit_VR = False

            # Encapsulate
            self.ds.PixelData = encapsulate(frames)
            self.ds["PixelData"].is_undefined_length = True
            self.ds["PixelData"].VR = "OB" if self.ds.BitsAllocated <= 8 else "OW"

        elif value == "1.2.840.10008.1.2.4.95":
            self.ds.RetrieveURL = "jpip://example.com/image.j2k"          # URI to JPIP stream
            # self.ds.ReferencedImageSequence = Sequence([self.ds])
            self.ds.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.4.95"
            if "PixelData" in self.ds:
                del self.ds.PixelData

        else:
            sys.exit("**ERROR** This compression format is not yet supported!")

    def modifyTag(self, mods, readme_path, regenerateSopInstanceUid=True):
        # mod -> list of pairs

        if not isinstance(mods, list):
            raise TypeError("mods must be a list of (tag, value) pairs")
        
        modified_lines = []
        
        for mod in mods:
            if not isinstance(mod, tuple) or len(mod) != 2:
                raise ValueError(f"Each modification must be a tuple of (tag, value), got: {mod}")

            tag, value = mod

            # Get tag name for README:
            tag_name = dictionary_description(tag.pydicom_tag) or "Unknown"

            if tag.pydicom_tag == Tag("TransferSyntaxUID"):
                self.changeTransferSyntax(tag, value)
                modified_lines.append(f"         {tag.pydicom_tag} ({tag_name}) = {value}\n")

            # Removing an element:
            elif tag.pydicom_tag in self.ds and value.lower() == "remove":
                del self.ds[tag.pydicom_tag]
                modified_lines.append(f"         {tag.pydicom_tag} ({tag_name}) = REMOVED\n")

            elif tag.pydicom_tag not in self.ds and value.lower() == "remove":
                continue

            # Adding a new element:
            elif tag.pydicom_tag not in self.ds:
                VR = dictionary_VR(tag.pydicom_tag)
                
                # TO DO:
                if "or" in VR:
                    VR = VR.split(" ")[0]
                    value = self.cast_value_for_vr(VR, value)
                # 
                
                self.ds.add_new(tag.pydicom_tag, VR, value)
                
                modified_lines.append(f"**NEW**  {tag.pydicom_tag} ({tag_name}) = {value}\n")
                continue
            
            # Change existing element value:
            elif tag.pydicom_tag in self.ds:
                VR = dictionary_VR(tag.pydicom_tag)
                value = self.cast_value_for_vr(VR, value)

                self.ds[tag.pydicom_tag].value = value

                modified_lines.append(f"         {tag.pydicom_tag} ({tag_name}) = {value}\n")

            # Nothing to do:
            else:
                print(f"**WARNING** Nothing to do with this tag: {tag_name}!")
                continue

        if readme_path and modified_lines:
            try:
                self.append_unique_lines(readme_path, modified_lines)
            except Exception as e:
                print(f"Could not write readme file: {e}")
        
        if regenerateSopInstanceUid:
            # Generate a unique instance UID for the modified copy.
            newUID = generate_uid()
            self.ds.SOPInstanceUID = newUID
            self.ds.file_meta.MediaStorageSOPInstanceUID = newUID

    @staticmethod
    def cast_value_for_vr(vr, value):
        if vr in ('US', 'SS'):
            return int(value)
        elif vr in ('FL', 'FD'):
            return float(value)
        elif vr in ('DA', 'TM', 'PN', 'LO', 'CS', 'SH'):
            return str(value)
        else:
            return value  # fallback, might be handled manually

    def append_unique_lines(self, file_path, new_lines):
        # Ensure file exists
        if not os.path.exists(file_path):
            open(file_path, "w", encoding="utf-8").close()

        # Read existing lines
        with open(file_path, "r", encoding="utf-8") as f:
            existing_lines = set(line.strip() for line in f if line.strip())

        # Filter out duplicates
        unique_new_lines = [line for line in new_lines if line.strip() not in existing_lines]

        # Append only if something is new
        if unique_new_lines:
            with open(file_path, "a", encoding="utf-8") as f:
                for line in unique_new_lines:
                    f.write(line if line.endswith("\n") else line + "\n")

    def findTag(self, tag_input):
        if hasattr(tag_input, "pydicom_tag"):
            tag_input = tag_input.pydicom_tag

        if tag_input in self.ds:
            elem = self.ds[tag_input]
            print(f"Search result: {elem}")
        else:
            print(f"Tag {tag_input} not found in dataset {self.path}")

    def getLinesFromDcm(self):

        lines = str(self.ds).split("\n")
        lines = [line + "\n" for line in lines]

        return lines

    def saveDcm(self, destDir, seriesName=None):
        filename = self.path.name

        if seriesName:
            seriesDir = seriesName
            # Generate a new file (ex: XXX8XXXX)
            filename = filename[:3] + seriesName + filename[4:]
        else:
            parent = os.path.dirname(self.path)
            seriesDir = os.path.basename(parent)
        
        studyDir = str(self.ds.StudyID)

        dest = os.path.join(destDir, "Scan", studyDir, seriesDir)
        
        os.makedirs(dest, exist_ok=True)

        outFile = os.path.join(dest, filename)

        self.ds.save_as(outFile, write_like_original=False)

        return outFile

    def saveInPlace(self):
        self.ds.save_as(self.path, write_like_original=False)

class dcmTag:
    def __init__(self, input_value):

        if isinstance(input_value, BaseTag):
            self.pydicom_tag = input_value
        else:
            self.pydicom_tag = self.parseTag(input_value)

    def exists(self):
        if dictionary_has_tag(self.pydicom_tag):
            return True
        return False

    def isFileMeta(self):
        return self.pydicom_tag.group == 0x0002

    @staticmethod
    def parseTag(tag):
        tag = tag.strip()

        if "," in tag:
            try:
                parts = tag.split(",")
                group = int(parts[0].strip(), 16)
                element = int(parts[1].strip(), 16)

                return Tag(group, element)
            except Exception:
                sys.exit(f"Could not parse provided tag: {tag}")

        key = tag.replace(" ", "")
        try:
            return Tag(key)
        except KeyError:
            sys.exit(f"Could not parse provided tag: {tag}")

    def goodTagValue(self, value):
        vr = dictionary_VR(self.pydicom_tag)

        # Skip sequence types (complex)
        if vr == "SQ":
            return False

        # Handle normal types only
        if value == "remove":
            return True
        elif vr in ("PN", "LO", "SH", "ST", "LT", "UT"):
            return len(value) <= 1024
        elif vr == "DA":
            return value.isdigit() and len(value) == 8
        elif vr == "TM":
            return value.replace('.', '').isdigit()
        elif vr in ("IS", "DS"):
            # IS and DS may be multi-valued. DICOM separates values with
            # backslashes (for example, Pixel Spacing: "0.7\\0.7").
            components = value.split('\\')
            if any(not component.strip() for component in components):
                return False

            try:
                for component in components:
                    float(component)
                return True
            except ValueError:
                return False
        elif vr == "CS":
            return value.isupper()
        elif vr == "AS":
            return bool(re.match(r"^\d{1,3}[DWMY]$", value))

        return True

    unmodifiable_tags = [
        Tag(0x0008, 0x0032),    # Acquisition Time
        Tag(0x0008, 0x0033),    # Content Time
        Tag(0x0018, 0x1151),    # X-Ray Tube Current
        Tag(0x0018, 0x1152),    # Exposure
        Tag(0x0018, 0x9318),    # Reconstruction Target Center
        Tag(0x0018, 0x9345),    # CTDIvol
        Tag(0x0020, 0x0013),    # Instance Number
        Tag(0x0020, 0x1041),    # Slice Location
        Tag(0x0028, 0x0107),    # Largest Image Pixel Value
    ]
