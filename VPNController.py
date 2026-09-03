import subprocess
import random
import os
import time
from Env import Env,logger, SingletonMeta
class VPNController(metaclass = SingletonMeta):

    def __init__(self):
        return
        if Env.is_debug:
            logger.info("Initalized NordVPN")
            return
        logger.info("Initalizing NordVPN")
        self._cur_server_index = 0
        self.VPN_SERVERS = []
        with open('complete_servers_list.txt', 'r') as f:
            self.VPN_SERVERS = [server.replace('\n', '') for server in f.readlines()]
        random.shuffle(self.VPN_SERVERS)
        if self.__is_connected_to_nordvpn():
            self.__disconnect_from_nordvpn()


    def __disconnect_from_nordvpn(self):
        logger.info("Disconnected from NordVPN")
        os.system("nordvpn disconnect")


    def __is_connected_to_nordvpn(self):
        output = str(subprocess.check_output(['nordvpn', 'status']))
        return "disconnected" not in output.lower()

    def connect_to_nordvpn(self, timeout = 35)->bool:
            return True
            if Env.is_debug:
                logger.info("Connecting to NordVPN")
                logger.debug("Connected to NordVPN")
                return
            for _ in range(10): # Try to connect for 10 times
                logger.info("Trying to connect to NordVPN ..")
                self._cur_server_index+= 1
                if self._cur_server_index >= len(self.VPN_SERVERS):
                    self._cur_server_index = 0
                output = "N/A"
                try:
                    output = str(subprocess.check_output(['nordvpn', 'connect', self.VPN_SERVERS[self._cur_server_index]], timeout = timeout))
                except KeyboardInterrupt:
                    return False
                except:
                    if self.__is_connected_to_nordvpn():
                        self.__disconnect_from_nordvpn()
                    output = ""
                    time.sleep(2.5)
                time.sleep(4)
                if 'you are connected' in output.lower():
                    logger.debug(f"Connected to NordVPN successfully. Server Name : {self.VPN_SERVERS[self._cur_server_index]}")
                    return True
                else:
                    logger.warning("Failed to connect to NordVPN. Retrying again .. ")
            
            
            logger.error("Max retries reached. Couldn't connect to NordVPN")
            return False

    def run_vpn(self, refresh_time):
        return
        elapsed_seconds = 0
        while True:
            with Env.is_running_lock:
                if not Env.is_running:
                    break
            while elapsed_seconds < refresh_time:
                with Env.is_running_lock:
                    if not Env.is_running:
                        break
                
                time.sleep(1)
                elapsed_seconds+= 1
            with Env.is_running_lock:
                if not Env.is_running:
                    break
            elapsed_seconds = 0
            logger.info("VPN Refresh Time is reached")
            self.connect_to_nordvpn()
        logger.debug("VPN Thread is joined successfully")



