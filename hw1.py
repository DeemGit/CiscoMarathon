#!/usr/bin/env python
# """Module docstring."""

# Imports
from netmiko import ConnectHandler
import csv
import logging
import datetime
import sys
import os
import time

DEVICE_FILE_PATH = 'devices.csv'  # file should contain a list of devices in format: ip,username,password,device_type
BACKUP_DIR_PATH = 'backups'  # complete path to backup directory
NTP_SERVER = '10.10.0.1'  # ntp server ip address

TEXT_FSM_TEMPLATES_PATH = 'ntc-templates\\templates'  # templates path. Comment this line if you want to use default values

try:
    os.environ.setdefault("NET_TEXTFSM", TEXT_FSM_TEMPLATES_PATH)
except NameError:
    pass


def enable_logging():
    # This function enables netmiko logging for reference

    logging.basicConfig(filename='netmiko.log', level=logging.DEBUG)
    logger = logging.getLogger("netmiko")


def get_devices_from_file(device_file):
    # This function takes a CSV file with inventory and creates a python list of dictionaries out of it
    # Each disctionary contains information about a single device

    # creating empty structures
    device_list = list()
    device = dict()

    # reading a CSV file with ',' as a delimeter
    with open(device_file, 'r') as f:
        reader = csv.DictReader(f, delimiter=',')

        # every device represented by single row which is a dictionary object with keys equal to column names.
        for row in reader:
            device_list.append(row)

    # returning a list of dictionaries
    return device_list


def get_current_date_and_time():
    # This function returns the current date and time
    now = datetime.datetime.now()

    # Returning a formatted date string
    # Format: yyyy_mm_dd-hh_mm_ss
    return now.strftime("%Y_%m_%d-%H_%M_%S")


def connect_to_device(device):
    # This function opens a connection to the device using Netmiko
    # Requires a device dictionary as an input

    # Since there is a 'hostname' key, this dictionary can't be used as is
    connection = ConnectHandler(
        host=device['ip'],
        username=device['username'],
        password=device['password'],
        device_type=device['device_type'],
        secret=device['secret']
    )

    print('Opened connection to ' + device['ip'])


    # returns a "connection" object
    return connection


def disconnect_from_device(connection, hostname):
    # This function terminates the connection to the device

    connection.disconnect()
    print('Connection to device {} terminated'.format(hostname))


def get_backup_file_path(hostname, timestamp):
    # This function creates a backup file name (a string)
    # backup file path structure is hostname/hostname-yyyy_mm_dd-hh_mm

    # checking if backup directory exists for the device, creating it if not present
    if not os.path.exists(os.path.join(BACKUP_DIR_PATH, hostname)):
        os.makedirs(os.path.join(BACKUP_DIR_PATH, hostname))

    # Merging a string to form a full backup file name
    backup_file_path = os.path.join(BACKUP_DIR_PATH, hostname, '{}-{}.txt'.format(hostname, timestamp))
    print('Backup file path will be ' + backup_file_path)



    # returning backup file path
    return backup_file_path


def create_backup(connection, backup_file_path, hostname):
    # This function pulls running configuration from a device and writes it to the backup file
    # Requires connection object, backup file path and a device hostname as an input

    try:
        # sending a CLI command using Netmiko and printing an output
        connection.enable()
        output = connection.send_command('sh run')

        # creating a backup file and writing command output to it
        with open(backup_file_path, 'w') as file:
            file.write(output)
        print("Backup of " + hostname + " is complete!")



        # if successfully done
        return True

    except Error:
        # if there was an error
        print('Error! Unable to backup device ' + hostname)
        return False


def check_cdp_neighbours_count(connection):
    # This function executes sh cdp neighbors details function and returns formatted result

    output = connection.send_command('sh cdp neighbors detail', use_textfsm=True)

    if type(output) == list:
        return f"CDP is ON, {len(output)} peers"
    else:
        return f"CDP is OFF, 0 peers"


def check_version(connection):
    # This function parses sh ver command

    output = connection.send_command('sh ver', use_textfsm=True)

    if not output:
        return "", "", "", ""

    return output[0].get("hostname", ""), \
           output[0].get("hardware", [""])[0], \
           output[0].get("version", "").upper(), \
           "NPE" if "NPE" in output[0].get("running_image", "").upper() else "PE"


def set_timezone(connection):
    # set timezone to +0

    print("Setting timezone to +0")
    connection.send_config_set(["clock timezone GMT+0 0"])


def ping_ntp(connection, ntp_server):
    # checking ntp server availability

    print(f"Ping NTP server {ntp_server}")
    output = connection.send_command(f'ping {ntp_server}\n')
    if "....." in output:
        print(f"NTP server is not available")
        return False
    else:
        print("Ok!")
        return True


def check_ntp(connection, ntp_server):
    # check if clock is in sync
    print(f"Promoting ntp server {ntp_server}")
    connection.send_config_set([f"ntp server {ntp_server}"])
#    connection.send_command(["clock read-calendar"])
    time.sleep(4)
    output = connection.send_command("sh ntp asso")
    return "Clock in Sync" if f"*~{ntp_server}" in output else "Not Sync"


def process_target(device, timestamp):
    # This function will be run by each of the processes in parallel
    # This function implements a logic for a single device using other functions defined above:
    #  - connects to the device,
    #  - gets a backup file name and a hostname for this device,
    #  - creates a backup for this device
    #  - terminates connection
    #  - compares a backup to the golden configuration and logs the delta
    # Requires connection object and a timestamp string as an input

    connection = connect_to_device(device)

    backup_file_path = get_backup_file_path(device['hostname'], timestamp)

    create_backup(connection, backup_file_path, device['hostname'])

    _cdp_result = check_cdp_neighbours_count(connection)

    _hostname, _device_type, _image, _is_NPE = check_version(connection)

    set_timezone(connection)

    ping_ntp(connection, NTP_SERVER)

    _ntp_result = check_ntp(connection, NTP_SERVER)


    disconnect_from_device(connection, device['hostname'])

    return f"{_hostname}|{_device_type}|{_image}|{_is_NPE}|{_cdp_result}|{_ntp_result}"

def main(*args):
    # This is a main function

    # Enable logs
    # enable_logging()

    # getting the timestamp string
    timestamp = get_current_date_and_time()

    # getting a device list from the file in a python format
    device_list = get_devices_from_file(DEVICE_FILE_PATH)

    # creating a empty list
    processes = list()


    result = []
    for device in device_list:
        result.append(process_target(device, timestamp))

    print(*result, sep="\n")


if __name__ == '__main__':
    # checking if we run independently
    _, *script_args = sys.argv

    # the execution starts here
    main(*script_args)
