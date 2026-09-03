import threading
import math
import random
from VPNController import VPNController
from Env import Env, logger
from bs4 import BeautifulSoup as BS
import shutil
import json
from typing import List
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from hashlib import *
import os
lock = threading.Lock()
def increase_total_requests():
    pass
    # with lock:
    #     Env.total_requests+= 1
        # if Env.total_requests >= Env.REQUESTS_LIMIT:
        #     logger.warning("Maximum requests per IP is reached. Changing the IP .. ")
        #     VPNController().connect_to_nordvpn()
        #     time.sleep(3)
        #     Env.total_requests = 0
    


def get_driver(options = Options()):
    # options.add_argument('--headless')
    driver = webdriver.Chrome(options = options)
    return driver
    


def read_text_file(file_path):
    res = []
    with open(file_path, 'r') as f:
        res = set([line.replace('\n', '') for line in f.readlines()])
        res = list(res)
    return res



def get_hash(word : str):
    return sha224(word.encode('utf-8')).hexdigest()

def write_to_csv_file(file_path, content):
    mode = 'a' if os.path.exists(file_path) else 'w'
    with open(file_path, mode) as f:
        f.write(content)
        f.write("\n")

def has_pdf(directory: str)->bool:
    for file in os.listdir(directory):
        if file.lower().endswith('.pdf'):
            return True
    return False
    


def download_pdf(url, output_path, timeout = 45)->None:
    options = Options()
    options.add_experimental_option('prefs', {
                "download.default_directory": f"{output_path}", #Change default directory for downloads
                "download.prompt_for_download": False, # To auto download the file
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True #It will not show PDF directly in chrome
            })

    driver = get_driver(options = options)
    driver.get(url)
    time.sleep(timeout)

def add_to_tsv_file(output_path, key, value):
    mode = 'a' if os.path.exists(output_path) else 'w'
    key = key.replace('\t', ' ')
    value = value.replace('\t', ' ')
    with open(output_path, mode) as f:
        f.write(f"{key}\t{value}\n")


def rename_pdfs(output_folder):
    for subdir, dirs, files in os.walk(output_folder):
    
        if subdir == output_folder:
            continue

        folder_name = os.path.basename(subdir)

        for file in files:
            if file.lower().endswith('.pdf'):
                old_file_path = os.path.join(subdir, file)

                new_file_name = f"{folder_name}.pdf"
                new_file_path = os.path.join(subdir, new_file_name)

                os.rename(old_file_path, new_file_path)


def read_json(path):
    obj = None
    try:
        with open(path, 'r') as f:
            obj = json.loads(f.read())
    except:
        pass
    return obj


        
def has_pdf(path):
    for file in os.listdir(path):
        _, extension = os.path.splitext(file)
        if extension == '.pdf':
            return True
    return False
    
    
    
def change_last_downloaded(directory, new_name):
    old_name = max([directory + "/" + f for f in os.listdir(directory) if f.endswith('.pdf')], key = os.path.getctime)
    extension = "." + old_name.split(".")[-1]

    new_name = os.path.join(directory, new_name + extension)
    shutil.move(old_name,new_name)
    return new_name


def get_total_pages(driver : webdriver.Remote, url):
    driver.get(url + '&start=100000')
    time.sleep(2)
    doc = BS(driver.page_source, 'html.parser')
    all_numbers = [str(i) for i in range(1, 101)]
    has_any = 'did not match any articles' not in doc.text
    if not has_any: # If no papers exist in the page --> it will give this the message
        return []

    container = doc.find("div", attrs = {'id' : 'gs_n'})
    total_pages = 0
    if not container: # if no pages are provided for the current year --> only one page there
        total_pages = 1
    
    try:
        for td in container.find_all("td"):
            if td.text in all_numbers:
                total_pages = max(total_pages, int(td.text))
    except:
        pass
    
    urls = [url + f'&start={page * 10}' for page in range(0, total_pages)]
    return urls

def get_formatted_pages_urls(url, citations_count):
    urls = []
    total_pages =  math.ceil(citations_count / 10)
    total_pages = min(total_pages, 100)
    for page_number in range(total_pages):
        page_url = url + f'&start={10 * page_number}'
        urls.append(page_url)
    return urls

def to_subsets(folder_path : str, subset_size : int)->List[str]:
    def distribute_folders(folders: List[str], sub_folders_count: int) -> List[List[str]]:
        distributed = [[] for _ in range(sub_folders_count)]
        for i, folder in enumerate(folders):
            distributed[i % sub_folders_count].append(folder)
        return distributed

    all_folders = [path[0] for path in os.walk(folder_path) if path[0] != folder_path]
    subset_size = min(subset_size, len(all_folders))
    distributed_folders = distribute_folders(all_folders, subset_size)
    subsets = []
    for folder_number in range(subset_size):
        subset_folder_path = f"{folder_path}/Subset-{folder_number + 1}"
        subsets.append(subset_folder_path)
        if  os.path.exists(subset_folder_path):
            continue
        os.mkdir(subset_folder_path)
        for folder in distributed_folders[folder_number]:
            shutil.move(folder , subset_folder_path)
    
    
    return subsets
    

