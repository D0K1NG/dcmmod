import sys
import os

from pydicom.fileset import FileSet
from pydicom import dcmread
import pathlib

from modules import dcmutil

# Use it to get all the paths included in a DICOMDIR so you can modify each dcm file it refrences
# You can only modify dicoms for specific series and study

class dcmdir:

    def __init__(self, dicomdir_path):
        self.path = self.convertPath(dicomdir_path)
        self.fs = self.open()
        self.studies_list = self.getStudiestList()

    def convertPath(self, path):
        if not isinstance(path, pathlib.Path):
            try:
                path = pathlib.Path(path)
            except:
                raise sys.exit(f"Provided path is not legitimate: {path}")
        return path
    
    @staticmethod
    def createReadme(destDir, name):
        os.makedirs(destDir, exist_ok=True)

        name = "SERIES_" + str(name) + "_MODIFICATIONS" + ".txt"
        readme_path = os.path.join(destDir, name)

        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("List of modifications applied to DICOMDIR:\n")
                f.write("="*50 + "\n\n")
        
        return readme_path

    def modifySeries(self, study_series, mods, dest, orig=False):
        studyNum = study_series[0]
        seriesNum = study_series[1]

        if orig:
            seriesName = str(8)
            readmePath = self.createReadme(dest, seriesName)
        else:
            readmePath = self.createReadme(dest, seriesNum)
        
        seriesPaths = self.getPaths(studyNum, seriesNum)
        outputPaths = []

        # Modify each DICOM:
        for dcmPath in seriesPaths:
            dcm = dcmutil.dcm(dcmPath)

            dcm.modifyTag(mods, readmePath)

            if orig:
                outputPaths.append(dcm.saveDcm(dest, seriesName=seriesName))
            else:
                outputPaths.append(dcm.saveDcm(dest))

        return outputPaths, readmePath

    # Problematic:
    # dont use this
    def __getAllPaths(self):
        paths = []

        for study in self.studies_list:
            for series in study["series_list"]:
                paths.extend(series["image_paths"])

        return paths
    # 

    def getPaths(self, studyNum, seriesNum):
        study = next(s for s in self.studies_list if s["study_number"] == studyNum)

        if not study:
            raise sys.exit(f"**ERROR** Study {studyNum} not found.")
        
        series = next((s for s in study["series_list"] if s["series_number"] == seriesNum), None)

        if not series:
            raise sys.exit(f"**ERROR** Series {seriesNum} not found in study {studyNum}.")

        return series["image_paths"]

    def printStudiesList(self):
        current_patient = None

        for study in self.studies_list:
            if study["patient_id"] != current_patient:
                current_patient = study["patient_id"]
                print("=" * 120)
                print(
                    f"Patient name: {study['patient_name']}\n"
                    f"Patient ID: {study['patient_id']}"
                )
                print("=" * 120)

            print(
                f"  Stuy [ {study['study_number']} ]\n"
                f"  Study Description: {study['study_description']}\n"
                f"  Study UID: {study['study_uid']}\n"
            )

            padding = " " * 4

            self._printSeriesList(study["series_list"], padding)

            print("=" * 120)

    def _printSeriesList(self, series_list, indent):
        for series in series_list:
            padding = " " * round(len(str(series["image_paths"][0])) / 2)
            img_cnt = len(series["image_paths"])

            print(
                f"{indent}Series [ {series['series_number']} ]: \n"
                f"{indent}  Series description:   {series['series_desc']}\n"
                f"{indent}  Series UID:           {series['series_uid']}\n"
                f"{indent}  Image count:          {img_cnt}\n"
                f"{indent}  Image paths:"
            )
            if img_cnt <= 5:
                for path in series["image_paths"]:
                    print(f"\t\t  {path}\n")
            else:
                print(
                    f"{indent}\t\t  {series['image_paths'][0]}\n"
                    f"{indent}\t\t  {series['image_paths'][1]}\n"
                    f"{indent}\t\t  {series['image_paths'][2]}\n"
                    f"{indent}{padding}\t\t  .\n"
                    f"{indent}{padding}\t\t  .\n"
                    f"{indent}{padding}\t\t  .\n"
                    f"{indent}\t\t  {series['image_paths'][img_cnt - 1]}\n"
                )
            print(indent + "-" * 100)

    def open(self):
        if not "DICOMDIR" in self.path.name:
            raise sys.exit(f"This is not a DICOMDIR file path: {self.path}")
        
        try:
            ds = dcmread(self.path)
        except:
            raise sys.exit(f"This is not a valid DICOMDIR file: {self.path}")

        fs = FileSet(ds)

        return fs

    def getImagePath(self, all_images):
        paths = []

        for file_id in all_images:

            if not file_id:
                raise print(f"WARNING: Could not get ReferencedFileID of an image, found {file_id}")
            
            base_dir = self.path.parent
            
            paths.append(base_dir.joinpath(*file_id))

        return paths

    def getSeriesDesc(self, image_path):
        try:
            ds = dcmread(image_path)
        except:
            raise sys.exit(f"Could not read image path {image_path}!")
        
        if "SeriesDescription" in ds:
            return ds.SeriesDescription
        else:
            return "N/A"

    def getStudiestList(self):
        # a list of dicts: [{"patient_name": str}, {"study_description": str}, {"series_list": [series_list]}]
        studies_list = []
        study_num = 1

        patient_ids = self.fs.find_values("PatientID")

        for patient_id in patient_ids:
            patient_instances = self.fs.find(PatientID=patient_id)
            patient_name = getattr(patient_instances[0], "PatientName", "N/A")
            study_uids = self.fs.find_values("StudyInstanceUID", instances=patient_instances)

            for study_uid in study_uids:
                study_instances = self.fs.find(PatientID=patient_id, StudyInstanceUID=study_uid)

                study_description = getattr(study_instances[0], "StudyDescription", "N/A")
                
                # a list of dicts: [{"series_number": int, "series_uid": str, "image_paths": [list_of_paths]}]
                series_list = []

                series_uids = self.fs.find_values("SeriesInstanceUID", instances=study_instances)

                for series_uid in series_uids:
                    series_instances = self.fs.find(PatientID=patient_id, StudyInstanceUID=study_uid, SeriesInstanceUID=series_uid)

                    series_num = getattr(series_instances[0], "SeriesNumber", "N/A")
                    series_desc = getattr(series_instances[0], "SeriesDescription", "N/A")

                    all_images = self.fs.find_values("ReferencedFileID", instances=series_instances)
                    image_paths = self.getImagePath(all_images)

                    if series_desc == "N/A":
                        series_desc = self.getSeriesDesc(image_paths[0])

                    series_list.append({
                        "series_number": series_num,
                        "series_desc": series_desc,
                        "series_uid": series_uid,
                        "image_paths": image_paths
                    })

                studies_list.append({
                    "patient_name": patient_name,
                    "patient_id": patient_id,
                    "study_number": study_num,
                    "study_description": study_description,
                    "study_uid": study_uid,
                    "series_list": series_list
                })

                study_num += 1

        return studies_list
