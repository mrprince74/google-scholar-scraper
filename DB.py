from queue import Queue
from typing import Tuple, List, Dict
from Env import *
from Env import Env
from Utils import get_total_pages, get_driver, increase_total_requests, get_formatted_pages_urls
from selenium import webdriver
import numpy as np
import os
import pandas as pd
from datetime import datetime
from VPNController import VPNController
from collections.abc import Iterator, Iterable
class DatabaseRow:
    def __init__(self,url : str, citation_level : int, year : int = None, parent : str = None, scraped : bool = False, citations_count = 0)->None:
        self.row : Dict[str] = {}
        self.row['Year'] = year
        self.row['URL'] = url
        self.row['Scraped'] = scraped
        self.row['Citation Level'] = citation_level
        self.row['Citations Count'] = citations_count
        self.row['Parent'] = parent
        
    
    def __getitem__(self, key_name : str):
        assert key_name in self.row.keys(), "Key not exist. Bad Database Usage"
        return self.row[key_name]

class Database(metaclass = SingletonMeta):
    def __init__(self, output_directory, keyword, should_update, start_year = 1996, citation_level_limit : int = 2):
        self.citation_level_limit = citation_level_limit
        logger.info("Initalizing Database ..")
        self.start_year = start_year
        self.end_year = datetime.now().year
        self.should_update = should_update
        self.keyword = keyword
        self.db_file_name = f"{output_directory}/{self.keyword}_db.csv"
        self.next_db_index = 0
        self.driver = None
        self.columns = ['Year', 'URL', 'Scraped', 'Citation Level', 'Parent']
        self.vpn = VPNController()
        self.__create_db()
        self.db: pd.DataFrame = self.__read_db()
        self.__update_db()
        self.citations_queue = Queue()
        logger.debug("Database Initalized")
        
        
        
        
    def __create_db(self)->None:
        logger.info("Creating the database file..")
        if os.path.exists(self.db_file_name):
            logger.info("Found an existing database file.")
            return
        table = []
        for year in range(self.start_year, self.end_year + 1):
            scholar_url = f"https://scholar.google.com/scholar?q={self.keyword}&hl=en&as_sdt=0,5&as_ylo={year}&as_yhi={year}"
            if not self.driver:
                self.driver = get_driver()
            logger.info(f"Extracting total number of pages for year {year}")
            urls = get_total_pages(self.driver, scholar_url)
            increase_total_requests()
            for url in urls:
                row = [year, url, False, 0, None]
                table.append(row)
            logger.debug(f"Extraced total number of pages for year {year}")
            
        df = pd.DataFrame(table, columns = self.columns)
        df.to_csv(self.db_file_name)
        logger.debug("Database file created successfully")
    

    def __read_db(self)->pd.DataFrame:
        df = pd.read_csv(self.db_file_name)
        if 'Unnamed: 0' in df.columns:
            df.drop(columns = ['Unnamed: 0'], inplace = True)
        
        return df
    
    def __update_db(self)->None:
        if 'Citation Level' not in self.db.columns:
            self.db['Citation Level'] = 0
            self.db.loc[self.db['Year'].isnull(), 'Citation Level'] = 1
        
        if 'Parent' not in self.db.columns:
            self.db['Parent'] = None
        
        db_start_year = int(self.db.iloc[0]['Year'])
        remaining_years = []
        logger.info("Updating the database .. ")
        for year in range(self.start_year, db_start_year):
                scholar_url = f"https://scholar.google.com/scholar?q={self.keyword}&hl=en&as_sdt=0,5&as_ylo={year}&as_yhi={year}"
                if not self.driver:
                    self.driver = get_driver()
                logger.info(f"Updating database for year {year}")
                urls = get_total_pages(self.driver, scholar_url)
                increase_total_requests()
                for url in urls:
                    row = [year, url, False, 0, None]
                    remaining_years.append(row)
        else:
            logger.info("No needed updates are found")
        

        remaining_years = pd.DataFrame(remaining_years, columns = self.columns)
        combined_df = pd.concat([remaining_years, self.db], ignore_index = True)
        self.db = combined_df.copy()
        self.db[self.db['Year'] == self.end_year]['Scraped'] = False
        
        if self.should_update:
            self.db.to_csv(self.db_file_name)
        
    def _move_iter_pointer(self):
        while self.next_db_index < len(self.db) and (self.db.at[self.next_db_index, 'Scraped'] == True or self.db.at[self.next_db_index, 'Year'] < self.start_year):
            self.next_db_index+= 1

    
    def has_next(self)->bool:
        self._move_iter_pointer()
        return self.next_db_index < len(self.db)
    
    def get_next(self)->DatabaseRow:        
        assert self.has_next(), "Nothing to scrape, bad database usage"
        row = self.db.loc[self.next_db_index].copy()
        return DatabaseRow(row['URL'], row['Citation Level'], year = row['Year'], parent = row['Parent'], scraped = row['Scraped'])

    def get_next(self, total_rows)->List[DatabaseRow]:
        rows = [None] * total_rows
        cur_index = self.next_db_index
        for row_index in range(total_rows):
            while cur_index < len(self.db) and self.db.at[cur_index, 'Scraped'] == True:
                cur_index+= 1
            
            if cur_index < len(self.db):
                row = self.db.loc[cur_index].copy()
                row = DatabaseRow(row['URL'], row['Citation Level'], year = row['Year'], parent = row['Parent'], scraped = row['Scraped'])
                rows[row_index] = row

            cur_index+= 1
        return rows
        
        
        

    def update(self):
        assert self.has_next(), "Nothing to scrape, bad database usage"
        logger.info("Marked last scraped page in the database as DONE")
        self.db.loc[self.next_db_index, 'Scraped'] = True
        self.next_db_index+= 1
        if self.should_update:
            self.db.to_csv(self.db_file_name)

    def update(self, url : DatabaseRow):
        row = self.db[self.db['URL'] == url]
        assert len(row) > 0, "Row Not Found. Bad database usage"
        row_index = row.index
        self.db.loc[row_index, 'Scraped'] = True
        logger.debug(f"Marked {url} as Scraped")
        self._move_iter_pointer()
        if self.should_update:
            self.db.to_csv(self.db_file_name)
    

    def add_rows(self):
        while Env.is_running or not self.citations_queue.empty():
            if self.citations_queue.empty():
                continue
            row = self.citations_queue.get()
            url = row['URL']
            citations_count = row['Citations Count']
            logger.info(f"Extracting number of pages for the citation : {url} ..")
            urls = get_formatted_pages_urls(url, citations_count)
            
            for url in urls:
                new_row = [row['Year'], url, False, row['Citation Level'] + 1, row['Parent']]
                self.db.loc[len(self.db)] = new_row
            
            logger.debug(f"Finished extracting number of pages for the citation : {url} successfully")
            
            if self.should_update:
                self.db.to_csv(self.db_file_name)

    def add_row(self, row : DatabaseRow)->None: # Add children
        url = row['URL']
        if url + "&start=0" in self.db['URL'].values or row['Citation Level'] >= self.citation_level_limit:
            return
        self.citations_queue.put(row)
    
    
    def get_total_urls(self):
        return len(self.db)

    def get_total_scraped(self):
        rows = self.db[self.db['Scraped'] == True]
        return len(rows)
        
    def __del__(self):
        if self.driver:
            self.driver.quit()
        
        