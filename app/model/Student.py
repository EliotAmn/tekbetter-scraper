import base64
import os
import time
import traceback
from datetime import datetime, timedelta
from inspect import trace

from app.intranet.intranet_antiddos_bypass import IntranetAntiDDoSBypasser
import requests

from app.logger import log_error, log_info


class TaskStatus:
    ERROR = "error"
    LOADING = "loading"
    SUCCESS = "success"


class TaskType:
    MOULI = "mouli"
    PLANNING = "planning"
    PROJECTS = "projects"
    SLUGS = "slugs"
    MODULES = "modules"
    PICTURE = "picture"
    NETSOUL = "netsoul"
    PROFILE = "profile"
    AUTH = "auth"
    SCRAPING = "scraping"


class Student:
    microsoft_session: str
    tekbetter_token: str = None
    myepitech_token: str = None
    intra_token: str = None
    last_sync: int = 0
    student_label: str = None
    antiddos: IntranetAntiDDoSBypasser = None
    main: None
    last_scrapes = {}
    last_scrape_start = 0
    is_scraping = False
    last_failed_auth = 0

    def send_task_status(self, status: {TaskType: TaskStatus}):
        """
        Send to the server the current scraping status for a task
        """
        try:
            body = {}
            for key, value in status.items():
                body[key] = value
            requests.post(f"{os.getenv('TEKBETTER_API_URL')}/api/scraper/status", json=body, headers={
                "Authorization": f"Bearer {self.tekbetter_token}"
            })
        except Exception as e:
            log_error(f"Failed to send task status to the server for student: {self.student_label}")
            log_error(str(e))

    def log_scrap(self, message):
        log_info(f"[{self.student_label}] {message}")

    def err_scrap(self, message):
        log_error(f"[{self.student_label}] {message}")

    def is_last_failed(self):
        return time.time() - self.last_failed_auth < 60 * 5 # Disable scraping if last auth failed less than 5 minutes ago

    def scrape_now(self):
        try:
            self.last_scrape_start = time.time() # Important: used for the thread-count limiter in main.py
            if not self.one_need_scrape() or self.is_last_failed():
                return
            self.is_scraping = True
            self.log_scrap(f"Scraping started.")
            try:
                res = requests.get(f"{os.getenv('TEKBETTER_API_URL')}/api/scraper/infos", headers={
                    "Authorization": f"Bearer {self.tekbetter_token}"
                })
                if res.status_code != 200:
                    raise
            except:
                self.err_scrap(f"Failed to fetch basic informations from the tekbetter api.")
                self.is_scraping = False
                return

            self.send_task_status({TaskType.SCRAPING: TaskStatus.LOADING})

            out_data = {
                TaskType.MOULI: None,
                TaskType.MODULES: None,
                TaskType.PROFILE: None,
                TaskType.PLANNING: None,
                TaskType.PROJECTS: None,
                TaskType.PICTURE: None,
                TaskType.NETSOUL: None,
                TaskType.SLUGS: {},
            }

            known_tests = res.json()["known_tests"]
            known_modules = res.json()["known_modules"] if "known_modules" in res.json() else []
            asked_slugs = res.json()["asked_slugs"]
            need_picture = res.json()["need_picture_login"] if "need_picture_login" in res.json() else []
            student_login = res.json()["student_login"]

            start_date = datetime.now() - timedelta(days=365 * 5)
            end_date = datetime.now() + timedelta(days=365)
            if "fetch_start" in res.json():
                start_date = datetime.strptime(res.json()["fetch_start"], "%Y-%m-%d")
            if "fetch_end" in res.json():
                end_date = datetime.strptime(res.json()["fetch_end"], "%Y-%m-%d")

            if self.can_scrape(TaskType.MOULI):
                out_data[TaskType.MOULI] = self.scrape_moulinettes(known_tests)
            if time.time() - self.last_failed_auth > 60: # Scrape only if the microsoft auth is not failed for moulis
                if self.can_scrape(TaskType.MODULES):
                    out_data[TaskType.MODULES] = self.scrape_modules(known_modules)
                if self.can_scrape(TaskType.PROFILE):
                    out_data[TaskType.PROFILE] = self.scrape_intra_profile()
                if self.can_scrape(TaskType.PLANNING):
                    out_data[TaskType.PLANNING] = self.scrape_intra_planning(start_date, end_date)
                if self.can_scrape(TaskType.PROJECTS):
                    out_data[TaskType.PROJECTS] = self.scrape_intra_projects(start_date, end_date)
                if self.can_scrape(TaskType.NETSOUL):
                    out_data [TaskType.NETSOUL] = self.scrape_netsoul(student_login)
                if need_picture is not None:
                    out_data[TaskType.PICTURE] = self.scrape_intra_picture(need_picture)
                if asked_slugs is not None and len(asked_slugs) > 0:
                    out_data[TaskType.SLUGS] = self.scrape_slugs(asked_slugs)

            self.log_scrap(f"Pushing data for student: {self.student_label}")
            res = requests.post(f"{os.getenv('TEKBETTER_API_URL')}/api/scraper/push", json=out_data, headers={
                "Authorization": f"Bearer {self.tekbetter_token}"
            })
            if res.status_code != 200:
                self.err_scrap(f"Failed to push data for student: {self.student_label}")
                self.send_task_status({TaskType.SCRAPING: TaskStatus.ERROR})
                self.is_scraping = False
                return
            self.log_scrap(f"Data pushed for student: {self.student_label}")
            self.send_task_status({TaskType.SCRAPING: TaskStatus.SUCCESS})
            self.is_scraping = False
        except Exception as e:
            traceback.print_exc()
            self.is_scraping = False

    def save_scrape(self, key):
        self.last_scrapes[key] = time.time()

    def can_scrape(self, type: str):
        if type not in self.last_scrapes:
            return True
        if type not in self.main.intervals:
            return
        if type in self.last_scrapes:
            return time.time() - self.last_scrapes[type] > self.main.intervals[type]
        return True

    def one_need_scrape(self):
        return True in [
            self.can_scrape(TaskType.MOULI),
            self.can_scrape(TaskType.MODULES),
            self.can_scrape(TaskType.PROFILE),
            self.can_scrape(TaskType.PLANNING),
            self.can_scrape(TaskType.PROJECTS),
            self.can_scrape(TaskType.PICTURE),
            self.can_scrape(TaskType.NETSOUL),
        ]

    def scrape_moulinettes(self, known_tests):
        result = None
        try:
            self.log_scrap(f"Fetching MyEpitech data.")
            self.send_task_status({TaskType.MOULI: TaskStatus.LOADING})
            result = self.main.myepitech.fetch_student(self, known_tests=known_tests)
            self.send_task_status({TaskType.MOULI: TaskStatus.SUCCESS})
        except Exception as e:
            traceback.print_exc()
            self.err_scrap(f"Failed to fetch MyEpitech data.")
            self.send_task_status({TaskType.MOULI: TaskStatus.ERROR})

        self.save_scrape(TaskType.MOULI)
        return result

    def scrape_slugs(self, asked_slugs):
        results = {}
        try:
            self.log_scrap(f"Fetching Intranet project slugs.")
            self.send_task_status({TaskType.SLUGS: TaskStatus.LOADING})
            for proj in asked_slugs:
                results[proj["code_acti"]] = self.main.intranet.fetch_project_slug(proj, self)
            self.send_task_status({TaskType.SLUGS: TaskStatus.SUCCESS})
        except Exception as e:
            self.err_scrap(f"Failed to fetch Intranet project slugs.")
            self.send_task_status({TaskType.SLUGS: TaskStatus.ERROR})
        return results

    def scrape_netsoul(self, student_login):
        results = None
        try:
            self.log_scrap(f"Fetching Intranet netsoul.")
            self.send_task_status({TaskType.NETSOUL: TaskStatus.LOADING})
            r = self.main.intranet.fetch_netsoul(student_login, self)
            if r is None:
                self.err_scrap(f"Failed to fetch Intranet netsoul.")
                self.send_task_status({TaskType.NETSOUL: TaskStatus.ERROR})
                return
            results = []
            for day in r:
                timestamp = day[0]
                student_time = day[1]
                average_time = day[5]
                results.append({
                    "timestamp": timestamp,
                    "student_time": student_time,
                    "average_time": average_time,
                })
        except Exception as e:
            self.err_scrap(f"Failed to fetch Intranet netsoul: {str(e)}")
            self.send_task_status({TaskType.NETSOUL: TaskStatus.ERROR})
        self.send_task_status({TaskType.NETSOUL: TaskStatus.SUCCESS})
        self.save_scrape(TaskType.NETSOUL)
        return results

    def scrape_modules(self, known_modules):
        results = []
        try:
            self.log_scrap(f"Fetching Intranet modules for student.")
            self.send_task_status({TaskType.MODULES: TaskStatus.LOADING})
            all_modules = self.main.intranet.fetch_modules_list(self)
            for module in all_modules:
                if len([m for m in known_modules if m == module["id"]]) == 0:
                    m = self.main.intranet.fetch_module(module["scolaryear"], module["code"], module["codeinstance"],
                                                        self)
                    m["id"] = module["id"] if "id" in module else None
                    results.append(m)
            self.send_task_status({TaskType.MODULES: TaskStatus.SUCCESS})
        except Exception as e:
            self.send_task_status({TaskType.MODULES: TaskStatus.ERROR})
            self.err_scrap(f"Failed to fetch Intranet modules for student")
        self.save_scrape(TaskType.MODULES)
        return results

    def scrape_intra_profile(self):
        profile = None
        try:
            self.log_scrap(f"Fetching Intranet profile.")
            self.send_task_status({TaskType.PROFILE: TaskStatus.LOADING})
            profile = self.main.intranet.fetch_student(self)
            self.send_task_status({TaskType.PROFILE: TaskStatus.SUCCESS})
        except Exception as e:
            self.send_task_status({TaskType.PROFILE: TaskStatus.ERROR})
            self.err_scrap(f"Failed to fetch Intranet profile.")
        self.save_scrape(TaskType.PROFILE)
        return profile

    def scrape_intra_planning(self, start, end):
        planning = None
        try:
            self.log_scrap(f"Fetching Intranet planning from {start} to {end}.")
            self.send_task_status({TaskType.PLANNING: TaskStatus.LOADING})
            planning = self.main.intranet.fetch_planning(self, start, end)
            self.send_task_status({TaskType.PLANNING: TaskStatus.SUCCESS})
        except Exception as e:
            self.send_task_status({TaskType.PLANNING: TaskStatus.ERROR})
            self.err_scrap(f"Failed to fetch Intranet planning.")
        self.save_scrape(TaskType.PLANNING)
        return planning

    def scrape_intra_projects(self, start_date, end_date):
        projects = None
        try:
            self.log_scrap(f"Fetching Intranet projects from {start_date} to {end_date}.")
            self.send_task_status({TaskType.PROJECTS: TaskStatus.LOADING})
            projects = self.main.intranet.fetch_projects(self, start_date, end_date)
            self.send_task_status({TaskType.PROJECTS: TaskStatus.SUCCESS})
        except Exception as e:
            self.send_task_status({TaskType.PROJECTS: TaskStatus.ERROR})
            self.err_scrap(f"Failed to fetch intranet projects")
        self.save_scrape(TaskType.PROJECTS)
        return projects

    def scrape_intra_picture(self, student_login):
        picture = None
        try:
            self.log_scrap(f"Fetching Intranet student picture.")
            picture = self.main.intranet.fetch_student_picture(student_login, self)
            picture = base64.b64encode(picture).decode("utf-8")
        except Exception as e:
            self.err_scrap(f"Failed to fetch Intranet student picture.")
        self.save_scrape(TaskType.PICTURE)
        return picture
