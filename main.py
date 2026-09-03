from typing import List
from selenium.common.exceptions import WebDriverException
from threading import Thread, Lock
import pandas as pd
import requests
import warnings
warnings.filterwarnings("ignore")
from DB import Database, DatabaseRow
from datetime import datetime
from VPNController import VPNController
import random
import Utils
import os
from Scraper import Scraper, Completer
import time
from tqdm import tqdm
import json
from Env import Env, logger
keywords = None
remaining_pages = None
override = None
deep_mode_path = None
shallow_mode_path = None
should_download_pdf = True
is_shallow_mode = None
is_deep_mode = None
should_resume = None
vpn = None
start_year = None
mode = None
citation_level_limit = None
number_of_threads = None
refresh_time = None

MIN_WAIT_TIME_BETWEEN_PAGE = 5
MAX_WAIT_TIME_BETWEEN_PAGE = 15

def run_scraper():
    global should_resume, start_year, remaining_pages, shallow_mode_path, citation_level_limit, number_of_threads
    for keyword in keywords:
        keyword = keyword.replace("'", '"').lower()
        logger.info(f"Started Scraping {keyword}")
        try:
            db = Database(shallow_mode_path, keyword,should_resume, start_year, citation_level_limit = citation_level_limit)
        except Exception as e:
            logger.exception(e)
            Env.is_running = False
            exit()
        pbar = tqdm(total = db.get_total_urls())
        pbar.update(db.get_total_scraped())
        def run_single(scraper : Scraper, row : DatabaseRow):
            global remaining_pages
            if remaining_pages <= 0 and mode == 'test':
                scraper.__del__()
                logger.info("No job to do. Stopping")
                return
            
            if not row:
                logger.info(f"Nothing found to scrape")
                return
            
            
            pbar.total = db.get_total_urls()
            try:
                success = scraper.scrape(row)
            except Exception as e:
                logger.error("Scraping stopped becuase of exception")
                logger.exception(e)
                exit()
                
            retries = 3
            while not success and retries > 0:
                try:
                    success = scraper.scrape(row)
                except WebDriverException:
                    logger.exception(e)
                    logger.warning(f"An error happened while scraping page {row['URL']}. Retrying again .. ")

                retries-= 1
            
            if not success:
                logger.error(f"Maximum retries exceeded while scraping page {row['URL']}. Exiting")
                exit()
            else:
                logger.debug(f"Finished scraping: {row['URL']}")
                WAIT_TIME_BETWEEN_PAGES = random.randint(MIN_WAIT_TIME_BETWEEN_PAGE, MAX_WAIT_TIME_BETWEEN_PAGE)
                logger.info(f"Waiting for {WAIT_TIME_BETWEEN_PAGES} seconds between the current page and the next one")
                db.update(row['URL'])
                pbar.update(1)
                time.sleep(WAIT_TIME_BETWEEN_PAGES)
                
        
        db_thread = Thread(target = db.add_rows, name = "Database")
        db_thread.start()
        scrapers = []
        for _ in range(number_of_threads):
            try:
                scraper = Scraper(shallow_mode_path, override, db)
                scraper.change_keyword(keyword)
            except Exception as e:
                logger.exception(e)
                Env.is_running = False
                exit()

            scrapers.append(scraper)

        
        while db.has_next() and (mode == 'full' or (mode == 'test' and remaining_pages > 0)):
            rows = db.get_next(number_of_threads)
            threads = [Thread(target = run_single, args = (scrapers[i], rows[i]), name=f"Thread-{i+1}") for i in range(number_of_threads)]
            for thread in threads:
                thread.start()
                remaining_pages-= 1
            logger.info("Waiting to join each thread ..")
            for thread in threads:
                thread.join()
            logger.debug("All threads are joined")
            time.sleep(5)
        
        db.stop_flag = True
        with Env.is_running_lock:
            Env.is_running = False
        db_thread.join()
        db.__del__()
        logger.debug(f"Finished Scraping {keyword}")
            



def run_completer():
    global number_of_threads
    subset_folders = Utils.to_subsets(deep_mode_path, number_of_threads)
    total_folders = sum(len(list(os.walk(folder))) for folder in subset_folders) - len(subset_folders)
    pbar = tqdm(total = total_folders)
    def run_single(folders_path : List[str]):
        nonlocal pbar
        global should_download_pdf, override
        completer = Completer(folders_path, should_download_pdf, override)
        for subdir,_,_ in os.walk(folders_path):
            if subdir == folders_path:
                continue
            folder_name = os.path.basename(subdir)
            logger.info(f"Started Deep mode for {folder_name} ..")
            json_dir = f"{subdir}/{folder_name}.json"
            info = Utils.read_json(json_dir) 
            pbar.update(1)
            if not info:
                continue
            try:
                completer.get_remaining(info)
            except Exception as e:
                logger.warning(f"Error with paper titled : {info['Title']}. Skipping ..")
                logger.exception(e)
                continue
            logger.debug(f"Finished Deep mode for {folder_name} ..")
            time.sleep(2.5)
    threads = [Thread(target = run_single, args = (subset_folders[i], ), name = f"Thread-{i+1}") for i in range(number_of_threads)]
    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()
    
    logger.debug("Deep mode is finished successfully")
    

def read_config():
    logger.info("Started reading config")
    with open('config.json', 'r') as f:
        obj = json.loads(f.read())
        global keywords, remaining_pages, override, should_download_pdf, is_deep_mode, is_shallow_mode, deep_mode_path, shallow_mode_path, should_resume, start_year, mode, citation_level_limit, number_of_threads, refresh_time
        keywords = obj['Keywords']
        override = obj['Override']
        remaining_pages = obj['num_testpage']
        is_shallow_mode = obj['is_shallow_mode']
        is_deep_mode = obj['is_deep_mode']
        deep_mode_path = obj['deep_mode_path']
        shallow_mode_path = obj['shallow_mode_path']
        should_resume = obj['resume']
        start_year = obj['Start Year']
        if obj['page_num_limit']:
            Env.REQUESTS_LIMIT = obj['page_num_limit']
        mode = obj['mode'].lower()
        citation_level_limit = obj['citation_level_limit']
        number_of_threads = obj['number_of_threads']
        refresh_time = obj['refresh_time']
    logger.debug("Finished reading config")



def make_assertions():
    global keywords,remaining_pages, override, should_download_pdf, is_deep_mode, is_shallow_mode, deep_mode_path, shallow_mode_path,should_resume, start_year, mode, number_of_threads, refresh_time
    if is_deep_mode and not deep_mode_path:
        logger.error("Deep Mode Path not provided. Please provide a vaild path")
        exit()
    
    if is_shallow_mode and not shallow_mode_path:
        logger.error("Shallow Mode Path not provided. Please provide a vaild path")
        exit()

    if is_deep_mode and is_shallow_mode:
        logger.error('Choose only one mode not both (shallow mode or deep mode)')
        exit()
    
    if not is_deep_mode and not is_shallow_mode:
        logger.error("You didn't choose the scraping mode (shallow mode or deep mode)")
        exit()
    
    if not keywords and is_shallow_mode:
        logger.error('No Keywords are provided, please provide at least one')
        exit()
    cur_year = datetime.now().year
    if not start_year or not (1800 <= start_year <= cur_year):
        logger.error('Year range is not valid')
        exit()

    if not mode or mode.lower() not in ['test', 'full']:
        logger.error('Mode not provided correctly')
        exit()
    
    if not number_of_threads:
        logger.error('Number of threads not provided correctly')
        exit()
    if number_of_threads < 1:
        logger.error('Number of threads must be at least 1')
        exit()
    
    if refresh_time < 30:
        logger.error('Refresh Time must be at least 30 seconds')
        exit()
    
    
def main():
    try:
        read_config()
        make_assertions()
        global vpn
        Env.total_requests = 0
        Env.is_running = True
        vpn = VPNController()
        vpn.connect_to_nordvpn()
        vpn_thread = Thread(target = vpn.run_vpn, args = (refresh_time, ))
        vpn_thread.start()
        if is_shallow_mode: # Scrape everything except DOI and PDFs
            run_scraper()
        else: 
            run_completer() # Extract DOI and download PDFs
        with Env.is_running_lock:
            Env.is_running = False
        vpn_thread.join()
        logger.debug("Script stopped running successfully")
    except Exception as e:
        logger.exception(e)
    

    


if __name__ == '__main__':
    main()

