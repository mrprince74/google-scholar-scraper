import shutil
from DB import Database, DatabaseRow
import os
import re
from bs4 import BeautifulSoup as BS
import requests
from typing import List, Dict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from Env import Env, logger
import random
from Utils import *
import time
from fake_useragent import UserAgent
import json


class Scraper:
    def __init__(self, output_path : str, override : bool, database: Database):
        self.user_agents = ['Mozilla/5.0 (iPhone; CPU iPhone OS 12_5_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/456.1.0.43.109;FBBV/594430238;FBDV/iPhone7,2;FBMD/iPhone;FBSN/iOS;FBSV/12.5.7;FBSS/2;FBCR/;FBID/phone;FBLC/pl_PL;FBOP/80]']
        self.all_authors = []
        self.all_sites = []

        self.override = override
        self.home_path = output_path
        self.base_url = "https://scholar.google.com/scholar?start={}&q={}&hl=en&as_sdt=0,5&as_ylo={}&as_yhi={}"
        self.keyword = None
        self.__config()
        self.out_driver = None
        self.db = database
        logger.info("Scraper Initalized")

        
    def __config(self):
        self.cur_user_agent = random.choice(self.user_agents)
        self.driver = get_driver()
        self.external_driver = None

    
    def __load_all_authors(self):
        logger.info("Preloading all authors ..")
        def get_author(url)->Dict[str,str]:
            headers = {
                "User-Agent": UserAgent().random,
                "Accept-Language": "en-US,en;q=0.9",
            }
            req = requests.get(url, headers = headers)
            
            doc = BS(req.text, 'html.parser')
            ret = {
                "Author Name": "N/A",
                "Author Profile": url,
                "Author Affiliation" : "N/A"
            }
            try:
                ret['Author Name'] = doc.find("div", attrs = {
                    "id" : "gsc_prf_in"
                }).text
            except:
                pass
            try:
                ret['Author Affiliation'] = doc.find('div', attrs = {
                    'class' : "gsc_prf_il" 
                }).text
            except:
                pass
            return ret

        self.all_authors = []
        authors_divs = self.driver.find_elements(By.CLASS_NAME, 'gs_a')
        for div in authors_divs:
            urls = div.find_elements(By.TAG_NAME, 'a')
            authors = {}
            for url in urls:
                url = url.get_attribute('href')
                author = get_author(url)
                author_name = author['Author Name'].lower()
                authors[author_name] = author
            self.all_authors.append(authors)
        logger.debug("Preloaded all authors successfully")
    
    def __load_all_sites(self):
        self.all_sites = []
        doc = BS(self.driver.page_source, 'html.parser')
        all_urls = doc.find_all("h3", attrs = {'class' : 'gs_rt'})
        for url in all_urls:
            url = url.find('a', href = True)
            if url:
                url = url['href']
            self.all_sites.append(url)

    def __load_all_titles(self):
        logger.info("Preloading all titles ..")
        self.all_titles = []
        divs = self.driver.find_elements(By.CLASS_NAME, 'gs_ri')
        for div in divs:
            h3 = div.find_element(By.TAG_NAME, "h3")
            text = h3.text
            self.all_titles.append(text.lower())
        logger.debug("Preloaded all titles successfully")


    def __get_external_info(self, url, result : Dict[str, str]):
        logger.info(f"Trying to scrape full abstract, DOI, and Pubmed ID for paper with title {result['Title']} ")
        info = {
             'DOI' : None,
             "Abstract" : result['Abstract'],
        }
        if self.external_driver is None:
            self.external_driver = get_driver()
        driver = self.external_driver
        increase_total_requests()
        driver.get(url)
        time.sleep(1)
        doc = BS(driver.page_source, 'html.parser')
        
        matches = re.findall(Env.DOI_PATTERN, driver.current_url + ' ' + driver.page_source)
        if len(matches):
             info['DOI'] = matches[0]
             logger.debug("Found DOI")
        else:
             logger.info("Unable to find DOI")

        
        pubmed_id = doc.find('div', attrs = {'class' : 'fm-citation-pmid'})
        if pubmed_id:
            pubmed_id = pubmed_id.text.split(':')[-1].strip()
            logger.debug("Found Pubmed ID")
        else:
            logger.info("Unable to find Pubmed ID")
        
        info['PMID'] = pubmed_id
        
        full_abstract = result['Abstract']
        if not len(full_abstract):
            return info
    

        tags = doc.find_all('div')
        tags.extend(doc.find_all('p'))
        for div in tags:
             text = div.text.lower()
             if text[ : len(full_abstract) // 2] == full_abstract.lower()[ : len(full_abstract) // 2] and len(text) >= len(full_abstract):
                  info['Abstract'] = div.text
                  logger.debug("Found full abstract")
        
        logger.debug(f"Finished scraping full abstract, DOI, and Pubmed ID for paper with title {result['Title']}")
        return info

    def __get_info_BS_method(self, index, body):
        logger.info(f"Started scraping paper's info with title {self.all_titles[index]}")
        doc = BS(body, 'html.parser')
        citations_count = 0
        citations_url = None
        li_items = doc.find_all('li')
        for item in li_items:
            text = item.text.lower()
            if 'cited by' in text:
                citations_count = int(text.replace('cited by', '').replace(' ', ''))
                citations_url = item.find('a')['href']
                citations_url = 'https://scholar.google.com/' + citations_url
                break
        pdf_link = None
        for a_tag in doc.find_all('a'):
            if 'pdf' in a_tag.text.lower() and a_tag['href']:
                pdf_link = a_tag['href']
                break
            if 'full view' in a_tag.text.lower() and a_tag['href']:
                pdf_link = a_tag['href'].replace('amd;', '')
                pdf_link = 'https://scholar.google.com' + pdf_link
                break
        if pdf_link:
            logger.debug("Found PDF link")
        else:
            logger.info("PDF link not found")

        
        info = {
            'Title' : doc.find("h3", attrs = {"class" : "gs_qabs_title"}).text,
            'Abstract' : doc.find('div', attrs = {'class' : 'gs_qabs_snippet'}).text,
            'Number of Citations' : citations_count,
            "Citation URL" : citations_url,
            'Publication Year': doc.find("div", attrs = {'class' : 'gs_qabs_pub'}).text.split(',')[-1].replace(' ', ''),
            'Journal Name' : ",".join(doc.find("div", attrs = {'class' : 'gs_qabs_pub'}).text.split(',')[:-1]),
            'Keyword' : self.keyword,
            'PDF URL' : pdf_link,
            'Paper Link' : None,
            "Authors" : []
        }
        author_names = doc.find('div', 'gs_qabs_au2').text.split(', ')
        cur_authors = self.all_authors[index]
        
        for _,author_info in cur_authors.items():
            info['Authors'].append(author_info.copy())
        
        for name in author_names:
            to_add = {
                "Author Name": name,
                "Author Profile": None,
                "Author Affiliation" : None
            }
            if name.lower() in cur_authors.keys():
                continue
            info['Authors'].append(to_add.copy())

        
        if info['Publication Year']:
                try:
                    info['Publication Year'] = int(info['Publication Year'])
                except:
                    info['Publication Year'] = None


        elems = self.driver.find_elements(By.CLASS_NAME, 'gs_qabs_src')
        for elem in elems:
            if 'view at' in elem.text.lower():
                a_tag = elem.find_element(By.TAG_NAME, 'a')
                url = a_tag.get_attribute('href')
                info['Paper Link'] = url
                break
        logger.debug(f"Finished Scraping : Title, Abstract, Number of Citations, Publication Year, Journal Name, PDF link, Authors for paper with title: {info['Title']}")
        return info


    def scrape(self, row : DatabaseRow):
        increase_total_requests()
        url = row['URL']
        self.driver.get(url)
        time.sleep(3)
        self.__load_all_authors()
        self.__load_all_sites()
        self.__load_all_titles()
        while len(self.all_titles) > 10:
            self.all_titles.pop(0)
        
        try:
            url = self.driver.find_element(By.CLASS_NAME, 'gs_ri')
        except:
            logger.error("No papers are found in the current page. Scraping for the current page stopped. Probably the captcha?")
            return False
        
        url = url.find_element(By.TAG_NAME, 'a')
        url.click()
        time.sleep(2)
        results = [None] * 10
        for _ in range(len(self.all_titles)):
            for index in range(6):
                try:
                    body = self.driver.execute_script("""
                        var obj = document.getElementsByClassName("gs_qabs_panel")[%s]
                        return obj.innerHTML
                        """ % index)
                    title = self.driver.execute_script("""
                        var obj = document.getElementsByClassName("gs_qabs_title")[%s]
                        return obj.innerText
                        """ % index)

                except:
                    continue

                title = title.lower()
                if title in self.all_titles:
                    # try:
                        pos = self.all_titles.index(title)
                        result = self.__get_info_BS_method(pos, body)
                        result['Citation Level'] = row['Citation Level']
                        self.all_titles[pos] = '$$$?$?$?@$?@$?'

                        url = self.all_sites[pos]
                        result['Paper Link'] = url
                        results[pos] = result
                        result['ID'] = get_hash(result['Title'])
                        if "..." in result['Abstract'][-3:] or "…" in result['Abstract'][-3:]:
                            result = result | self.__get_external_info(url, result)
                        
                        if result['Citation URL']:
                            citation_row = DatabaseRow(result['Citation URL'], row['Citation Level'], parent = result['Title'], citations_count = result['Number of Citations'])
                            self.db.add_row(citation_row)
                            logger.debug(f"Added citations for Paper with title: {result['Title']}")
                        else:
                            logger.info(f"No citations found for Paper with title: {result['Title']}")


                        result['parents'] = [row['Parent']]
                        self.save_result(result, result['ID'])
                    # except:
                        # continue

                time.sleep(1)
            
            
            try:
                self.driver.execute_script("""
                    var next_button = document.getElementsByClassName("gs_psd_prt");
                    next_button = next_button[0];
                    next_button.click();
                """)
            except:
                pass
            time.sleep(3)
        return True
        


    def change_keyword(self, new_keyword):
        self.keyword = new_keyword
    
    
    def save_result(self, result, file_name):
        logger.info(f"Saving file : {file_name}")
        file_name = file_name.replace('/', '-')
        output_path = f"{self.home_path}/{file_name}"
        

        if not os.path.exists(output_path):
            os.mkdir(output_path)
        
        has_file = os.path.exists(output_path + f"/{file_name}.json")

        
        if has_file:
            logger.warning(f"Found file {file_name}. Adding parents to the file")
            with open(output_path + f"/{file_name}.json", 'r') as f:
                old_result = json.loads(f.read())
                my_parent = result.get('parents', [None])[0]
                if my_parent not in old_result.get('parents', []):
                    result['parents'] = old_result.get('parents', [])
                    result['parents'].append(my_parent)
            logger.debug(f"Added parents to file {file_name} Successfully")
        
        result['parents'] = list(set(result['parents']))
        obj = json.dumps(result, indent = 4, ensure_ascii = False)
        with open(output_path + f'/{file_name}.json', 'w') as f:
            f.write(obj)
        logger.debug(f"Saved file : {file_name} Successfully")
    
    def restart(self):
        self.driver.quit()
        self.__config()
        pass
    
    
    def __del__(self):
        self.driver.quit()
        if self.external_driver:
            self.external_driver.quit()
        



class Completer:
    def __init__(self, output_path : str, should_download_pdf : bool, override : bool):
        logger.info("Completer Initalized")
        self.override = override
        self.driver = get_driver()
        self.output_path = output_path
        if self.output_path[-1] == '/':
            self.output_path = self.output_path[:-1]
        self.should_download_pdf = should_download_pdf
        self.__config()
    
    def __config(self):
        options = Options()
        options.add_experimental_option('prefs', {
                "download.default_directory": f"{self.output_path}", #Change default directory for downloads
                "download.prompt_for_download": False, # To auto download the file
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True #It will not show PDF directly in chrome
            })
        self.driver = get_driver()
        self.external_driver = None
        self.__login()

    def __login(self):  
        logger.info(f"Trying to login to {Env.ACADEMIA_LOGIN_URL}")
        increase_total_requests()
        self.driver.get(Env.ACADEMIA_LOGIN_URL)
        time.sleep(1.5)
        email_elem = self.driver.find_element(By.ID, 'login-modal-email-input')
        pass_elem =  self.driver.find_element(By.ID, 'login-modal-password-input')
        submit_button_elem = None
        all_inputs = self.driver.find_elements(By.TAG_NAME, 'input')
        for tag in all_inputs:
            try:
                if tag.get_attribute('type') == 'submit':
                    submit_button_elem = tag
                    break
            except:
                continue
        email_elem.send_keys(Env.ACADEMIA_EMAIL)
        time.sleep(1)
        pass_elem.send_keys(Env.ACADEMIA_PASSWORD)
        time.sleep(1)
        submit_button_elem.click()
        time.sleep(5)
        logger.debug(f"Logged in Successfully")

    def __get_external_info(self, url, result : Dict[str, str]):
        logger.info(f"Trying to scrape full abstract, DOI, and Pubmed ID for paper with title {result['Title']} ")
        info = {
             'DOI' : None,
             "Abstract" : result['Abstract'],
        }
        if self.external_driver is None:
            self.external_driver = get_driver()
        driver = self.external_driver
        increase_total_requests()
        driver.get(url)
        time.sleep(1)
        doc = BS(driver.page_source, 'html.parser')
        
        matches = re.findall(Env.DOI_PATTERN, driver.current_url + ' ' + driver.page_source)
        if len(matches):
             info['DOI'] = matches[0]
             logger.debug("Found DOI")
        else:
             logger.info("Unable to find DOI")

        
        pubmed_id = doc.find('div', attrs = {'class' : 'fm-citation-pmid'})
        if pubmed_id:
            pubmed_id = pubmed_id.text.split(':')[-1].strip()
            logger.debug("Found Pubmed ID")
        else:
            logger.info("Unable to find Pubmed ID")
        
        info['PMID'] = pubmed_id
        
        full_abstract = result['Abstract']
        if not len(full_abstract):
            return info
    

        tags = doc.find_all('div')
        tags.extend(doc.find_all('p'))
        for div in tags:
             text = div.text.lower()
             if text[ : len(full_abstract) // 2] == full_abstract.lower()[ : len(full_abstract) // 2] and len(text) >= len(full_abstract):
                  info['Abstract'] = div.text
                  logger.debug("Found full abstract")
        
        logger.debug(f"Finished scraping full abstract, DOI, and Pubmed ID for paper with title {result['Title']}")
        return info


    def get_remaining(self, info:dict):
        if info.get('done', False):
            logger.info(f"Paper : {info['Paper Link']} with title : {info['Paper Link']} is already scraped. Quitting")
            return
        logger.info(f"Attempting paper : {info['Paper Link']} with title : {info['Paper Link']} ..")
        paper_url = info["Paper Link"]
        info = info | self.__get_external_info(paper_url, info)
        if not info["PDF URL"]:
            info["PDF URL"] = self.__get_pdf_url(info["Title"])
        
        
        the_output_folder = f"{self.output_path}/{info['ID']}"
        try:
            if has_pdf(the_output_folder) and not self.override:
                logger.warning("Found PDF in the folder. Not Overriding")
                self.save_result(info, info['ID'])
                return
        except:
            pass
        
        
        if self.should_download_pdf and info["PDF URL"]:
            time.sleep(2)
            old_output_folder = self.output_path
            new_output_folder = f"{old_output_folder}/{info['ID']}/{info['ID']}"
            download_code = self.__download_pdf(info['PDF URL'])
            if download_code == 0:
                change_last_downloaded(old_output_folder, new_output_folder)
                logger.debug("Succesfully downloaded PDF")
            else:
                logger.warning("Unable to download PDF")
        
        logger.debug(f"Finished attempting paper : {info['Paper Link']} with title : {info['Title']}")
        self.save_result(info, info['ID'])

    def __download_pdf(self, file_url: str, timeout = 45):
        """
        Timeout: Maximum number of seconds to wait until the file is downloaded, otherwise the file is considered a fail

        Returns: -1 if file exceeded the timeout, otherwise 0
        """
        try:
            increase_total_requests()
            self.driver.get(file_url)
        except:
            return -1
        downloaded = False
        while timeout > 0 and not downloaded:
            if has_pdf(self.output_path):
                downloaded = True
                break
            time.sleep(1)
            timeout-= 1
        
        return -1 if not downloaded else 0


    def __get_pdf_url(self,title)->str:
        logger.info("Searching for PDF url ..")
        BASE_URL = "https://scholar.google.com/scholar?hl=en&as_sdt=0%2C5&q={}&btnG="
        url = BASE_URL.format(title)
        options = Options()
        # options.add_argument('--headless')
        driver = get_driver(options = options)
        increase_total_requests()
        driver.get(url)
        time.sleep(1.5)
        pdf_url = driver.execute_script("""
            var obj = document.getElementsByClassName('gs_r gs_or gs_scl');
            if (obj.length == 0){
                return null;
            }
            var first_link = null;
            var a_tag = obj[0].getElementsByTagName('a')[0];
            if (a_tag.innerText.toLowerCase().includes('[pdf]')){
                first_link = a_tag.getAttribute('href');
            }
            else if (a_tag.innerText.toLowerCase().includes('full view')){
                first_link = a_tag.getAttribute('href');
            }
            return first_link;
        """)
        driver.close()
        logger.debug("Finished searching for PDF url")
        return pdf_url


    def save_result(self, result, file_name):
        logger.info("Saving the json file after modifications .. ")
        result['done'] = True
        obj = json.dumps(result, indent = 4, ensure_ascii = False)
        file_name = file_name.replace('/', '-')
        output_path = f"{self.output_path}/{file_name}"
        

        if not os.path.exists(output_path):
            os.mkdir(output_path)
        
        with open(output_path + f'/{file_name}.json', 'w') as f:
            f.write(obj)
        logger.debug("Json file saved modifications")

    def restart(self):
        try:
            self.driver.quit()
        except:
            pass
        try:
            if self.external_driver:
                self.external_driver.quit()
        except:
            pass
        self.__config()
    

    def __del__(self):
        try:
            self.driver.quit()
        except:
            pass
        try:
            if self.external_driver:
                self.external_driver.quit()
        except:
            pass
        
