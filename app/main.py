import json
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

from app.intranet.intranet_api import IntranetApi
from app.intranet.intranet_manager import IntranetManager
from app.logger import log_info, log_error, log_warning
from app.model.Student import Student
from app.myepitech.myepitech_manager import MyEpitechManager

class Main:
    def __init__(self):
        log_info("Welcome to the TekBetter scraper")
        self.students = []
        self.student_interval = 0

        self.myepitech = MyEpitechManager()
        self.intranet = IntranetManager()

        if not self.check_env():
            exit(1)
        if not self.load_config():
            exit(1)

    def check_env(self):
        log_info("Loading environment variables")
        load_dotenv()
        valid = True
        if not os.getenv("TEKBETTER_API_URL"):
            log_error("Missing TEKBETTER_API_URL environment variable")
            valid = False
        if not os.getenv("SCRAPER_MODE"):
            log_warning("Missing SCRAPER_MODE environment variable. Using default value 'private'")
        if  os.getenv("SCRAPER_MODE") == "public" and not os.getenv("TEKBETTER_API_KEY"):
            log_error("Missing TEKBETTER_API_KEY environment variable")
            valid = False
        if not os.getenv("SCRAPER_CONFIG_FILE"):
            log_error("Missing SCRAPER_CONFIG_FILE environment variable")
            valid = False
        else:
            if not os.path.exists(os.getenv("SCRAPER_CONFIG_FILE")):
                log_error("Invalid SCRAPER_CONFIG_FILE path")
                valid = False
            if not os.access(os.getenv("SCRAPER_CONFIG_FILE"), os.R_OK):
                log_error(f"{os.getenv('SCRAPER_CONFIG_FILE')} is not readable")
                valid = False
            if not os.access(os.getenv("SCRAPER_CONFIG_FILE"), os.W_OK):
                log_error(f"{os.getenv('SCRAPER_CONFIG_FILE')} is not writable")
                valid = False
        return valid

    def load_config(self):
        path = os.getenv("SCRAPER_CONFIG_FILE")
        file_content = open(path, "r").read()
        json_data = {}
        if file_content:
            try:
                json_data = json.loads(file_content)
            except:
                log_error("Config file is not a valid JSON file")
                return False
        else:
            json_data = {}
        # Create config keys if they don't exist
        if not "student_interval" in json_data:
            json_data["student_interval"] = 60
        if not "students" in json_data:
            json_data["students"] = []
        for student in json_data["students"]:
            if not "microsoft_session" in student:
                student["microsoft_session"] = ""
            if not "tekbetter_token" in student:
                student["tekbetter_token"] = ""
        # Save the config
        with open(path, "w") as f:
            f.write(json.dumps(json_data, indent=4))

        self.student_interval = json_data["student_interval"]
        for student in json_data["students"]:
            student_obj = Student()
            student_obj.microsoft_session = student["microsoft_session"]
            student_obj.tekbetter_token = student["tekbetter_token"]
            self.students.append(student_obj)
        return True

    def sync_student(self, student):
        res = requests.get(f"{os.getenv('TEKBETTER_API_URL')}/api/scraper/infos", headers={
            "Authorization": f"Bearer {student.tekbetter_token}"
        })

        if res.status_code != 200:
            log_error(f"Failed to fetch known tests for student: {student.student_label}")
            return
        known_tests = res.json()["known_tests"]
        asked_slugs = res.json()["asked_slugs"]

        body = {
            "new_moulis": None,
            "intra_profile": None,
            "intra_planning": None,
            "intra_projects": None,
            "projects_slugs": {},
        }

        try:
            body["new_moulis"] = self.myepitech.fetch_student(student, known_tests=known_tests)
        except Exception as e:
            log_error(f"Failed to fetch MyEpitech data for student: {student.student_label}")
            log_error(str(e))
        start_date = datetime.now() - timedelta(days=365)
        end_date = datetime.now() + timedelta(days=365)

        try:
            body["intra_profile"] = self.intranet.fetch_student(student)
        except Exception as e:
            log_error(f"Failed to fetch Intranet data for student: {student.student_label}")
            log_error(str(e))
        try:
            body["intra_planning"] = self.intranet.fetch_planning(student, start_date, end_date)
        except Exception as e:
            log_error(f"Failed to fetch Intranet planning for student: {student.student_label}")
            log_error(str(e))
        try:
            body["intra_projects"] = self.intranet.fetch_projects(student, start_date, end_date)
        except Exception as e:
            log_error(f"Failed to fetch Intranet projects for student: {student.student_label}")
            log_error(str(e))

        try:
            for proj in body["intra_projects"]:
                if proj["codeacti"] in asked_slugs:
                    slug = self.intranet.fetch_project_slug(proj, student)
                    body["projects_slugs"][proj["codeacti"]] = slug
        except Exception as e:
            log_error(f"Failed to fetch Intranet project slugs for student: {student.student_label}")
            log_error(str(e))
        log_info(f"Pushing data for student: {student.student_label}")

        res = requests.post(f"{os.getenv('TEKBETTER_API_URL')}/api/scraper/push", json=body, headers={
            "Authorization": f"Bearer {student.tekbetter_token}"
        })

        if res.status_code != 200:
            log_error(f"Failed to push data for student: {student.student_label}")
            return
        log_info(f"Data pushed for student: {student.student_label}")

if __name__ == "__main__":
    main = Main()
    main.sync_student(student=main.students[0])