import base64
import os
import time
import traceback
from datetime import datetime, timedelta

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
    PROFILE = "profile"
    AUTH = "auth"
    SCRAPING = "scraping"


class Student:
    def __init__(self):
        self.microsoft_session = ""
        self.tekbetter_token = None
        self.myepitech_token = None
        self.intra_token = None
        self.last_sync = 0
        self.student_label = None
        self.antiddos = None
        self.main = None
        self.last_scrapes = {}
        self.last_scrape_start = 0
        self.is_scraping = False
        self.last_failed_auth = 0

    def send_task_status(self, status: dict[str, str]):
        try:
            api_url = os.getenv("TEKBETTER_API_URL")
            body = {key: value for key, value in status.items()}
            requests.post(
                f"{api_url}/api/scraper/status",
                json=body,
                headers={"Authorization": f"Bearer {self.tekbetter_token}"},
                timeout=10
            )
        except Exception as e:
            log_error(f"Failed to send task status for student: {self.student_label}")
            log_error(str(e))

    def log_scrap(self, message):
        log_info(f"[{self.student_label}] {message}")

    def err_scrap(self, message):
        log_error(f"[{self.student_label}] {message}")

    def is_last_failed(self):
        return time.time() - self.last_failed_auth < 60 * 5

    def scrape_now(self):
        try:
            self.last_scrape_start = time.time()
            if not self.one_need_scrape() or self.is_last_failed():
                return

            self.is_scraping = True
            self.log_scrap("Scraping started.")
            api_url = os.getenv("TEKBETTER_API_URL")

            try:
                res = requests.get(
                    f"{api_url}/api/scraper/infos",
                    headers={"Authorization": f"Bearer {self.tekbetter_token}"},
                    timeout=10
                )
                if res.status_code != 200:
                    raise Exception("Failed to fetch /infos")
                res_json = res.json()
            except Exception as e:
                self.err_scrap("Failed to fetch scraping infos from API. Error :" + str(e))
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
                TaskType.SLUGS: {},
            }

            known_tests = res_json.get("known_tests", [])
            known_modules = res_json.get("known_modules", [])
            asked_slugs = res_json.get("asked_slugs", [])
            need_picture = res_json.get("need_picture_login", [])

            start_date = datetime.strptime(res_json.get("fetch_start"), "%Y-%m-%d") if res_json.get("fetch_start") else (datetime.now() - timedelta(days=5 * 365))
            end_date = datetime.strptime(res_json.get("fetch_end"), "%Y-%m-%d") if res_json.get("fetch_end") else (datetime.now() + timedelta(days=365))

            if self.can_scrape(TaskType.MOULI):
                start = time.time()
                out_data[TaskType.MOULI] = self.scrape_moulinettes(known_tests)
                self.log_scrap(f"Mouli scraped in {time.time() - start:.2f}s")

            if time.time() - self.last_failed_auth > 60:
                if self.can_scrape(TaskType.MODULES):
                    start = time.time()
                    out_data[TaskType.MODULES] = self.scrape_modules(known_modules)
                    self.log_scrap(f"Modules scraped in {time.time() - start:.2f}s")

                if self.can_scrape(TaskType.PROFILE):
                    out_data[TaskType.PROFILE] = self.scrape_intra_profile()

                if self.can_scrape(TaskType.PLANNING):
                    out_data[TaskType.PLANNING] = self.scrape_intra_planning(start_date, end_date)

                if self.can_scrape(TaskType.PROJECTS):
                    out_data[TaskType.PROJECTS] = self.scrape_intra_projects(start_date, end_date)

                if need_picture:
                    out_data[TaskType.PICTURE] = self.scrape_intra_picture(need_picture)

                if asked_slugs:
                    out_data[TaskType.SLUGS] = self.scrape_slugs(asked_slugs)

            self.log_scrap("Pushing scraped data...")
            try:
                res = requests.post(
                    f"{api_url}/api/scraper/push",
                    json=out_data,
                    headers={"Authorization": f"Bearer {self.tekbetter_token}"},
                    timeout=10
                )
                if res.status_code != 200:
                    raise Exception("Push failed")

                self.send_task_status({TaskType.SCRAPING: TaskStatus.SUCCESS})
                self.log_scrap("Data pushed successfully.")
            except Exception as e:
                self.err_scrap("Failed to push scraped data.")
                self.send_task_status({TaskType.SCRAPING: TaskStatus.ERROR})
        except Exception as e:
            traceback.print_exc()
            self.err_scrap("Scraping process failed.")
        finally:
            self.is_scraping = False

    def save_scrape(self, key):
        self.last_scrapes[key] = time.time()

    def can_scrape(self, task_type: str):
        if task_type not in self.main.intervals:
            return False
        last = self.last_scrapes.get(task_type, 0)
        return (time.time() - last) > self.main.intervals[task_type]

    def one_need_scrape(self):
        return any(self.can_scrape(t) for t in [
            TaskType.MOULI, TaskType.MODULES, TaskType.PROFILE,
            TaskType.PLANNING, TaskType.PROJECTS, TaskType.PICTURE
        ])

    def scrape_moulinettes(self, known_tests):
        result = None
        try:
            self.log_scrap("Fetching MyEpitech data.")
            self.send_task_status({TaskType.MOULI: TaskStatus.LOADING})
            result = self.main.myepitech.fetch_student(self, known_tests=known_tests)
            self.send_task_status({TaskType.MOULI: TaskStatus.SUCCESS})
        except Exception as e:
            self.err_scrap("Failed to fetch MyEpitech data : " + str(e))
            self.send_task_status({TaskType.MOULI: TaskStatus.ERROR})
        self.save_scrape(TaskType.MOULI)
        return result

    def scrape_slugs(self, asked_slugs):
        results = {}
        try:
            self.log_scrap("Fetching Intranet project slugs.")
            self.send_task_status({TaskType.SLUGS: TaskStatus.LOADING})
            for proj in asked_slugs:
                results[proj["code_acti"]] = self.main.intranet.fetch_project_slug(proj, self)
            self.send_task_status({TaskType.SLUGS: TaskStatus.SUCCESS})
        except Exception:
            self.err_scrap("Failed to fetch project slugs.")
            self.send_task_status({TaskType.SLUGS: TaskStatus.ERROR})
        return results

    def scrape_modules(self, known_modules):
        results = []
        try:
            self.log_scrap("Fetching Intranet modules.")
            self.send_task_status({TaskType.MODULES: TaskStatus.LOADING})
            all_modules = self.main.intranet.fetch_modules_list(self)
            for module in all_modules:
                if module["id"] not in known_modules:
                    m = self.main.intranet.fetch_module(module["scolaryear"], module["code"], module["codeinstance"], self)
                    m["id"] = module.get("id")
                    results.append(m)
            self.send_task_status({TaskType.MODULES: TaskStatus.SUCCESS})
        except Exception:
            self.send_task_status({TaskType.MODULES: TaskStatus.ERROR})
            self.err_scrap("Failed to fetch modules.")
        self.save_scrape(TaskType.MODULES)
        return results

    def scrape_intra_profile(self):
        profile = None
        try:
            self.log_scrap("Fetching Intranet profile.")
            self.send_task_status({TaskType.PROFILE: TaskStatus.LOADING})
            profile = self.main.intranet.fetch_student(self)
            self.send_task_status({TaskType.PROFILE: TaskStatus.SUCCESS})
        except Exception:
            self.send_task_status({TaskType.PROFILE: TaskStatus.ERROR})
            self.err_scrap("Failed to fetch profile.")
        self.save_scrape(TaskType.PROFILE)
        return profile

    def scrape_intra_planning(self, start, end):
        planning = None
        try:
            self.log_scrap(f"Fetching planning from {start} to {end}.")
            self.send_task_status({TaskType.PLANNING: TaskStatus.LOADING})
            planning = self.main.intranet.fetch_planning(self, start, end)
            self.send_task_status({TaskType.PLANNING: TaskStatus.SUCCESS})
        except Exception:
            self.send_task_status({TaskType.PLANNING: TaskStatus.ERROR})
            self.err_scrap("Failed to fetch planning.")
        self.save_scrape(TaskType.PLANNING)
        return planning

    def scrape_intra_projects(self, start_date, end_date):
        projects = None
        try:
            self.log_scrap(f"Fetching projects from {start_date} to {end_date}.")
            self.send_task_status({TaskType.PROJECTS: TaskStatus.LOADING})
            projects = self.main.intranet.fetch_projects(self, start_date, end_date)
            self.send_task_status({TaskType.PROJECTS: TaskStatus.SUCCESS})
        except Exception:
            self.send_task_status({TaskType.PROJECTS: TaskStatus.ERROR})
            self.err_scrap("Failed to fetch projects.")
        self.save_scrape(TaskType.PROJECTS)
        return projects

    def scrape_intra_picture(self, student_login):
        picture = None
        try:
            self.log_scrap("Fetching student picture.")
            picture = self.main.intranet.fetch_student_picture(student_login, self)
            picture = base64.b64encode(picture).decode("utf-8")
        except Exception:
            self.err_scrap("Failed to fetch picture.")
        self.save_scrape(TaskType.PICTURE)
        return picture
