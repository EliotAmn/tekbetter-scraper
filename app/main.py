import os
import threading
import time
import traceback
from datetime import datetime, timedelta
from app.intranet.intranet_manager import IntranetManager
from app.logger import log_info, log_error, log_warning
from app.myepitech.myepitech_manager import MyEpitechManager
from app.tools.config_loader import load_configuration
from app.tools.env_loader import check_env_variables
from app.model.Student import Student, TaskStatus, TaskType


class Main:
    def __init__(self):
        log_info("Welcome to the TekBetter scraper")
        self.students = []
        self.threads = []
        self.myepitech = MyEpitechManager()
        self.intranet = IntranetManager()
        self.intervals = {
            TaskType.MOULI: 30,
            TaskType.MODULES: 60,
            TaskType.PROFILE: 60,
            TaskType.PLANNING: 60,
            TaskType.PROJECTS: 60,
            TaskType.NETSOUL: 600,
        }

        if not check_env_variables() or not load_configuration(self):
            exit(1)

        for student in self.students:
            student.main = self

    def clean_threads(self):
        for thread in self.threads:
           if not thread.is_alive():
               self.threads.remove(thread)
    def sync_passage(self):
        self.clean_threads()
        students = [s for s in self.students if s is not None]
        # Remove student who is currently scraping
        scraping_count = len([s for s in students if s.is_scraping])
        students = [s for s in students if not s.is_scraping and s.one_need_scrape() and not s.is_last_failed()]
        # sort by student.get_last_scrape() to get olders first
        students.sort(key=lambda x: x.last_scrape_start)
        max_threads = int(os.getenv("MAX_THREADS", 10))
        to_scrape_count = max_threads - scraping_count
        if to_scrape_count <= 0:
            return
        # get the "to_scrape_count's users
        to_scrape = students[:to_scrape_count]
        for student in to_scrape:
            thr = threading.Thread(target=student.scrape_now)
            thr.start()
            self.threads.append(thr)

if __name__ == "__main__":
    main = Main()
    last_config_update = datetime.now()
    CONFIG_RELOAD_INTERVAL = 2

    try:
        while True:
            try:
                time.sleep(1)
                main.sync_passage()

                if last_config_update + timedelta(minutes=CONFIG_RELOAD_INTERVAL) < datetime.now():
                    last_config_update = datetime.now()
                    load_configuration(main)
            except Exception as e:
                log_error("An error occured in the main loop")
                log_error(str(e))
                traceback.print_exc()
                time.sleep(60)
                continue
    except KeyboardInterrupt:
        log_error("Received keyboard interrupt, exiting.")
        for t in main.threads:
            t.join()
        exit(0)
