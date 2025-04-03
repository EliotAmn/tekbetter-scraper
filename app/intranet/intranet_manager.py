import re
from datetime import datetime

from app.intranet.intranet_api import IntranetApi
from app.model.Student import Student
from app.tools.date_spliter import split_dates


class IntranetManager:
    def __init__(self):
        self.api = IntranetApi()

    def fetch_student(self, student: Student):
        student.log_scrap(f"[INTRA] Fetching student profile")
        return self.api.api_request("user/?format=json", student)

    def fetch_planning(self, student: Student, start_date: datetime, end_date: datetime):
        student.log_scrap(f"[INTRA] Fetching student planning")
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        final = []
        dates = split_dates(start_str, end_str, 70)

        for s_start, s_end in dates:
            student.log_scrap(f"[INTRA] Fetching student planning from {s_start} to {s_end}")
            res = self.api.api_request(f"planning/load?start={s_start}&end={s_end}&format=json", student)

            for event in res:
                # Skip personal events
                if event.get("calendar_type") == "perso":
                    continue

                # If the student is self-registered, save it.
                if event.get("event_registered") in ["present", "registered", "absent"]:
                    final.append(event)
                    continue

                # If it's an appointment, and the student is registered, save it.
                if event.get("rdv_indiv_registered") is not None:
                    final.append(event)
                    continue

                # If it's a group appointment, and the student is registered, save it.
                if event.get("rdv_group_registered") is not None:
                    final.append(event)
                    continue

                # If none of the above applies, skip the event.
                # final.append(event)  # <- laissé commenté, conforme à ton code source

        return final  # Duplicates not expected here; otherwise, use set + hashable key if necessary.

    def fetch_projects(self, student: Student, start_date: datetime, end_date: datetime):
        student.log_scrap(f"[INTRA] Fetching student projects")
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        final = []
        dates = split_dates(start_str, end_str, 70)

        for s_start, s_end in dates:
            student.log_scrap(f"[INTRA] Fetching student projects from {s_start} to {s_end}")
            res = self.api.api_request(f"module/board/?start={s_start}&end={s_end}&format=json", student)

            for activity in res:
                if activity.get("registered") and activity.get("type_acti_code") in ["proj", "tp"]:
                    final.append(activity)

        return final

    def fetch_project_slug(self, ask_json: dict, student: Student):
        scolyear = ask_json["year"]
        codemodule = ask_json["module"]
        codeinstance = ask_json["instance"]
        codeacti = ask_json["code_acti"]

        url = f"module/{scolyear}/{codemodule}/{codeinstance}/{codeacti}/project/?format=json"

        student.log_scrap(f"[INTRA] Fetching project slug for {codeacti}")
        result = self.api.api_request(url, student)

        return result.get("slug")  # plus concis

    def fetch_student_picture(self, student_login: str, student: Student) -> bytes:
        """
        Fetch the student picture from the intranet
        :param student_login:
        :param student:
        :return: Image bytes
        """
        student.log_scrap(f"[INTRA] Fetching student picture")
        url = f"file/userprofil/profilview/{student_login}.jpg"
        return self.api.api_request(url, student)

    def fetch_modules_list(self, student: Student):
        url = "/course/filter?format=json"
        student.log_scrap(f"[INTRA] Fetching modules list")
        res = self.api.api_request(url, student)

        return [
            {
                "code": m["code"],
                "id": int(m["id"]) if "id" in m and m["id"] is not None else None,
                "scolaryear": m["scolaryear"],
                "codeinstance": m["codeinstance"],
            }
            for m in res
        ]

    def fetch_module(self, scolar_year: int, code_module: str, code_instance: str, student: Student):
        url = f"module/{scolar_year}/{code_module}/{code_instance}/?format=json"
        student.log_scrap(f"[INTRA] Fetching module {code_module}")

        module_data = self.api.api_request(url, student)

        # Init TekBetter custom fields
        module_data["tb_is_roadblock"] = False
        module_data["tb_roadblock_submodules"] = None
        module_data["tb_required_credits"] = None

        # Detect if the module is a roadblock
        if "-EPI-" in module_data.get("codemodule", "") and module_data.get("description"):
            road_submodules = []

            for row in module_data["description"].split("\n"):
                # extract the code of the submodule, who have the format like "L-LLL-NNN"
                match = re.search(r"[A-Z]-[A-Z]{3}-\d{3}", row)
                if match:
                    road_submodules.append(match.group())

                # detect required credits like "validate this unit you must acquire at least X credits"
                match = re.search(r"validate this unit you must acquire at least (\d+) credits", row)
                if match:
                    module_data["tb_required_credits"] = int(match.group(1))

            module_data["tb_roadblock_submodules"] = road_submodules
            module_data["tb_is_roadblock"] = bool(road_submodules and module_data["tb_required_credits"])

        return module_data
