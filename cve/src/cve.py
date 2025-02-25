# coding: utf-8

import os
import yaml
import time
import urllib.request
import gzip
import shutil

from datetime import datetime
from pycti import OpenCTIConnectorHelper
from cvetostix2 import convert


class Cve:
    def __init__(self):
        # Instantiate the connector helper from config
        config_file_path = os.path.dirname(os.path.abspath(__file__)) + '/config.yml'
        config = yaml.load(open(config_file_path), Loader=yaml.FullLoader) if os.path.isfile(config_file_path) else {}
        self.helper = OpenCTIConnectorHelper(config)
        # Extra config
        self.cve_nvd_data_feed = os.getenv('CVE_NVD_DATA_FEED') or config['cve']['nvd_data_feed']
        self.cve_interval = os.getenv('CVE_INTERVAL') or config['cve']['interval']
        self.update_existing_data = os.getenv('CONNECTOR_UPDATE_EXISTING_DATA') or config['connector']['update_existing_data']
        if isinstance(self.update_existing_data, str):
            self.update_existing_data = (self.update_existing_data == 'True' or self.update_existing_data == 'true')

    def get_interval(self):
        return int(self.cve_interval) * 60 * 60 * 24

    def run(self):
        self.helper.log_info('Fetching CVE knowledge...')
        while True:
            try:
                # Get the current timestamp and check
                timestamp = int(time.time())
                current_state = self.helper.get_state()
                if current_state is not None and 'last_run' in current_state:
                    last_run = current_state['last_run']
                    self.helper.log_info(
                        'Connector last run: ' + datetime.utcfromtimestamp(last_run).strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    last_run = None
                    self.helper.log_info('Connector has never run')
                # If the last_run is more than interval-1 day
                if last_run is None or ((timestamp - last_run) > ((int(self.cve_interval) - 1) * 60 * 60 * 24)):
                    # Downloading json.gz file
                    self.helper.log_info('Requesting the file')
                    urllib.request.urlretrieve(self.cve_nvd_data_feed, os.path.dirname(os.path.abspath(__file__)) + '/data.json.gz')
                    # Unzipping the file
                    self.helper.log_info('Unzipping the file')
                    with gzip.open('data.json.gz', 'rb') as f_in:
                        with open('data.json', 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    # Converting the file to stix2
                    self.helper.log_info('Converting the file')
                    convert('data.json', 'data-stix2.json')
                    with open('data-stix2.json') as stix_json:
                        contents = stix_json.read()
                        self.helper.send_stix2_bundle(contents, self.helper.connect_scope, self.update_existing_data)

                    # Remove files
                    os.remove('data.json')
                    os.remove('data.json.gz')
                    os.remove('data-stix2.json')
                    # Store the current timestamp as a last run
                    self.helper.log_info('Connector successfully run, storing last_run as ' + str(timestamp))
                    self.helper.set_state({'last_run': timestamp})
                    self.helper.log_info(
                        'Last_run stored, next run in: ' + str(round(self.get_interval() / 60 / 60 / 24, 2)) + ' days')
                    time.sleep(60)
                else:
                    new_interval = self.get_interval() - (timestamp - last_run)
                    self.helper.log_info(
                        'Connector will not run, next run in: ' + str(round(new_interval / 60 / 60 / 24, 2)) + ' days')
                    time.sleep(60)
            except (KeyboardInterrupt, SystemExit):
                self.helper.log_info('Connector stop')
                exit(0)
            except Exception as e:
                self.helper.log_error(str(e))
                time.sleep(60)


if __name__ == '__main__':
    cveConnector = Cve()
    cveConnector.run()
