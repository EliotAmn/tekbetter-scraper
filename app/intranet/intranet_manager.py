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

        for (s_start, s_end )in dates:
            student.log_scrap(f"[INTRA] Fetching student planning from {s_start} to {s_end}")
            res =  self.api.api_request(f"planning/load?start={s_start}&end={s_end}&format=json", student)

            for event in res:
                # Skip personal events
                if "calendar_type" in event and event["calendar_type"] == "perso":
                    continue

                # If the student is self-registered, save it.
                if "event_registered" in event and event["event_registered"] is not None and event["event_registered"] in ["present", "registered"]:
                    final.append(event)
                    continue

                # If it's an appointment, and the student is registered, save it.
                if "rdv_indiv_registered" in event and event["rdv_indiv_registered"] is not None:
                    final.append(event)
                    continue

                # If it's a group appointment, and the student is registered, save it.
                if "rdv_group_registered" in event and event["rdv_group_registered"] is not None:
                    final.append(event)
                    continue

                # if not event['event_registered'] in ['present', 'registered'] and (event['rdv_indiv_registered'] is None and event['rdv_group_registered'] is None):
                #     continue # Skip events without registered students
#                final.append(event)
        # Remove duplicates
        return final

    def fetch_netsoul(self, student: Student, student_login: str):
        res = self.api.api_request(f"user/{student_login}/netsoul/?format=json", student)
        if not res:
            return None
        return res

    def fetch_projects(self, student: Student, start_date: datetime, end_date: datetime):
        student.log_scrap(f"[INTRA] Fetching student projects")
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        final = []

        dates = split_dates(start_str, end_str, 70)

        for (s_start, s_end )in dates:
            student.log_scrap(f"[INTRA] Fetching student projects from {s_start} to {s_end}")
            res = self.api.api_request(f"module/board/?start={s_start}&end={s_end}&format=json", student)

            for activity in res:
                if not activity['registered']:
                    continue
                if activity['type_acti_code'] not in ["proj", "tp"]:
                    continue
                final.append(activity)
        return final

    def fetch_project_slug(self, ask_json: dict, student: Student):
        scolyear = ask_json['year']
        codemodule = ask_json['module']
        codeinstance = ask_json['instance']
        codeacti = ask_json['code_acti']

        url = f"module/{scolyear}/{codemodule}/{codeinstance}/{codeacti}/project/?format=json"

        student.log_scrap(f"[INTRA] Fetching project slug for {codeacti}")
        result =  self.api.api_request(url, student)

        if not "slug" in result:
            return None
        return result["slug"]

    def fetch_student_picture(self, student_login: str, student: Student) -> bytes:
        """
        Fetch the student picture from the intranet
        :param student_login:
        :param student:
        :return: Image bytes
        """
        student.log_scrap(f"[INTRA] Fetching student picture")
        url = f"file/userprofil/profilview/{student_login}.jpg"
        img_bytes = self.api.api_request(url, student)
        return img_bytes


    def fetch_modules_list(self, student: Student):
        url = f"/course/filter?format=json"
        student.log_scrap(f"[INTRA] Fetching modules list")
        res = self.api.api_request(url, student)
        ret = []
        for m in res:
            ret.append({
                "code": m["code"],
                "id": int(m["id"]) if "id" in m else None,
                "scolaryear": m["scolaryear"],
                "codeinstance": m["codeinstance"],
            })
        return ret

    def fetch_module(self, scolar_year: int, code_module: str, code_instance: str, student: Student):
        url = f"module/{scolar_year}/{code_module}/{code_instance}/?format=json"
        student.log_scrap(f"[INTRA] Fetching module {code_module}")

        module_data = self.api.api_request(url, student)

        module_data["tb_is_roadblock"] = False
        module_data["tb_roadblock_submodules"] = None
        module_data["tb_required_credits"] = None

        if "-EPI-" in module_data["codemodule"] and "description" in module_data and module_data["description"]:
            # This module is a roadblock
            road_submodules = []

            for row in module_data["description"].split("\n"):
                # extract the code of the submodule, who have the format like "L-LLL-NNN" where L is a letter and N is a number
                mod_patten = re.compile(r"[A-Z]-[A-Z]{3}-\d{3}")
                match = mod_patten.search(row)
                if match:
                    road_submodules.append(match.group())

                # As a reminder, to validate this unit you must acquire at least 3 credits with the units listed below:
                cred_pattern = re.compile(r"validate this unit you must acquire at least (\d+) credits")
                match = cred_pattern.search(row)
                if match:
                    module_data["tb_required_credits"] = int(match.group(1))

            module_data["tb_roadblock_submodules"] = road_submodules
            module_data["tb_is_roadblock"] = len(road_submodules) > 0 and module_data["tb_required_credits"] is not None
        return module_data
