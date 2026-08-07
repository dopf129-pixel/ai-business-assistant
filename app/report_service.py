import os
from datetime import datetime



class ReportService:


    def __init__(self):

        self.folder = "reports"


        if not os.path.exists(self.folder):

            os.makedirs(self.folder)




    def save_report(
        self,
        report,
        name="report"
    ):


        filename = (

            f"{name}_"
            f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            ".txt"

        )



        path = os.path.join(
            self.folder,
            filename
        )



        with open(
            path,
            "w",
            encoding="utf-8"
        ) as file:


            file.write(report)



        return path