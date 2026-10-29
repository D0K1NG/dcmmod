import pydicom

class PrintDicomDirTree:
    def __init__(self, ds, show_attributes=False):
        self.ds = ds
        self.show_attributes = show_attributes
        self.PrintTree()
    
    # Counters:
    patient_cnt = 1
    studies_cnt = 1
    series_cnt = 1
    image_cnt = 1

    # Padding:
    rec_indent = 4
    attr_indent = 0
        

    def PrintAllAttributes(self, Record, padding):
        for attribute in Record:
            tag = attribute.tag
            name = attribute.name
            value = attribute.value

            # If attribute is a sequence:
            if isinstance(value, pydicom.sequence.Sequence):
                print(f"{padding}{tag} {name}:")

                for i, item in enumerate(value):
                    print(padding + f"\t\tItem #{i + 1}: ")
                    for sub_attr in item:
                        # get rid of new lines
                        sub_val = str(sub_attr.value).replace("\n", " ")
                        print(padding + f"\t\t {sub_attr.tag} {sub_attr.name}: {sub_val}")
            else:
                # get rid of new lines
                value = str(value).replace("\n", " ").replace("\r", " ")

                print(f"{padding}{tag}  {name}: {value}")

    
    def SearchImage(self, image, lvl):
        padding = " " * (self.rec_indent * lvl)
        attr_pad = " " * (self.rec_indent * lvl + self.attr_indent)

        if image:
            print(padding + f"Image [{getattr(image, 'ImageDescription', str(self.image_cnt))}]")

            if(self.show_attributes):
                self.PrintAllAttributes(image, attr_pad)

            print(attr_pad + ".  .  .\n")

    def SearchSeries(self, all_series, lvl):
        for series in all_series:
            padding = " " * (self.rec_indent * lvl)
            attr_pad = " " * (self.rec_indent * lvl + self.attr_indent)

            print(padding + f"Series [{getattr(series, 'SeriesDescription', 'N/A')}], [{getattr(series, 'SeriesNumber', 'N/A')}]")

            if (self.show_attributes):
                self.PrintAllAttributes(series, attr_pad)

            print()

            images = [image for image in series.children if image.DirectoryRecordType == "IMAGE"]

            self.SearchImage(images[0], lvl + 1)

            self.series_cnt += 1

    def SearchStudies(self, studies, lvl):
        for study in studies:
            padding = " " * (self.rec_indent * lvl)
            attr_pad = " " * (self.rec_indent * lvl + self.attr_indent)

            print(padding + f"Study [{getattr(study, 'StudyDescription', str(self.studies_cnt))}]")

            if (self.show_attributes):
                self.PrintAllAttributes(study, attr_pad)
            
            print()

            # Collect all series for a given study
            all_series = [series for series in study.children if series.DirectoryRecordType == "SERIES"]

            self.SearchSeries(all_series, lvl + 1)

            self.studies_cnt += 1

    def SearchPatients(self, lvl=0):
        for patient in self.ds.DirectoryRecordSequence:
            padding = " " * (self.rec_indent * lvl)
            attr_pad = " " * (self.rec_indent * lvl + self.attr_indent)

            print(
                f"Patient [ {self.patient_cnt} ]\n"
                f"Name: {patient.PatientName}\n"
                f"PatientID: {patient.PatientID}"
                )

            if (self.show_attributes):
                self.PrintAllAttributes(patient, attr_pad)

            print()

            # Collect all studies for a specific patient
            studies = [study for study in patient.children if study.DirectoryRecordType == "STUDY"]

            self.SearchStudies(studies, lvl + 1)

            self.patient_cnt += 1

    def PrintTree(self):
        self.SearchPatients()
