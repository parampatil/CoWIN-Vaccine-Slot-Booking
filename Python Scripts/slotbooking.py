#-----------IMPORTS-----------#

#imports for GUI
import PySimpleGUI as sg

#imports for main function
import argparse
import copy
import os
import sys
import time
from types import SimpleNamespace

import jwt

#imports for functions
import json
from hashlib import sha256
from collections import Counter
from PySimpleGUI.PySimpleGUI import Window
from inputimeout import inputimeout, TimeoutOccurred
import tabulate, copy, time, datetime, requests, sys, os, random
import uuid
from datetime import date

#imports for Captcha
import base64
import json
import os
import re
import sys

from bs4 import BeautifulSoup

#imports for rate-limit
import time

import boto3
import requests
from ec2_metadata import ec2_metadata

#--------IMPORTS CLOSE--------#

#--------URLs--------
BOOKING_URL = "https://cdn-api.co-vin.in/api/v2/appointment/schedule"
BENEFICIARIES_URL = "https://cdn-api.co-vin.in/api/v2/appointment/beneficiaries"
CALENDAR_URL_DISTRICT = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={0}&date={1}"
CALENDAR_URL_PINCODE = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByPin?pincode={0}&date={1}"
FIND_URL_DISTRICT = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/findByDistrict?district_id={0}&date={1}"
FIND_URL_PINCODE = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/findByPin?pincode={0}&date={1}"
CAPTCHA_URL = "https://cdn-api.co-vin.in/api/v2/auth/getRecaptcha"
OTP_PUBLIC_URL = "https://cdn-api.co-vin.in/api/v2/auth/public/generateOTP"
OTP_PRO_URL = "https://cdn-api.co-vin.in/api/v2/auth/generateMobileOTP"
APPOINTMENT_SLIP_URL = (
    "https://cdn-api.co-vin.in/api/v2/appointment/appointmentslip/download"
)

KVDB_BUCKET = os.getenv("KVDB_BUCKET")
#-----URLs ENDs--------

#-----GUI Declerations------

#GUI for displaying Info
#Changing the standar output for gui
def mprint(*args, **kwargs):
    dispwindow['-ML1-'+sg.WRITE_ONLY_KEY].print(*args, **kwargs)
print = mprint
layoutdisp=[
    [sg.Text('Click Start to Book')],
    [sg.MLine(key='-ML1-'+sg.WRITE_ONLY_KEY, size=(100,30), auto_refresh=True)],
    [sg.Ok('Start'),sg.Button('Next')]
]
dispwindow = sg.Window('Covid Vaccine booking',layoutdisp)

#-----GUI Declerations ENDS------
#----------FUNCTION DFINATIONS----------#

#Threading Defination
# def main():
#     threading.Thread(target=main_thread, args=(window,), daemon=True).start()

#------Rate limit functions------
network_interface_id = None
re_assignment_failed = False


def disable_re_assignment_feature():
    global re_assignment_failed
    re_assignment_failed = True
    print("INFO: Reassignment feature is disabled")


def wait_for_new_ip(ip):
    reflected = False
    while not reflected:
        try:
            resp = requests.get("https://ifconfig.me", timeout=(1, 1))
            if resp.status_code == 200 and resp.text == ip:
                print(f"{ip} ready to use.")
                reflected = True
            else:
                print(f"{ip} not reflected. ip still is {resp.text}.")
                time.sleep(1)
        except requests.exceptions.Timeout:
            print("Request to ifconfig.me timed out.")


def detect_network_interface_id():
    """
    This method will fail on non-ec2 instances. Meaning it is not on ec2.
    :return: returns primary interface's eni-id
    """
    return ec2_metadata.network_interfaces[ec2_metadata.mac].interface_id


def handle_rate_limited():
    global re_assignment_failed
    global network_interface_id

    if not re_assignment_failed:
        try:
            if network_interface_id is None:
                network_interface_id = detect_network_interface_id()
            print(
                "\n================================= AWS Re-assignment ===============================\n"
            )
            ip = re_assign_ip(network_interface_id)
            if type(ip) is bool and ip is False:
                re_assignment_failed = True
            else:
                wait_for_new_ip(ip)
            re_assignment_failed = not ip
        except Exception:
            re_assignment_failed = True
    else:
        print(
            "Rate-limited by CoWIN. Waiting for 5 seconds.\n"
            "(You can reduce your refresh frequency. Please note that other devices/browsers "
            "using CoWIN/Umang/Arogya Setu also contribute to same limit.)"
        )
        time.sleep(5)


def re_assign_ip(eni_id):
    try:
        client = boto3.client("ec2")
        response = client.describe_network_interfaces(
            NetworkInterfaceIds=[
                eni_id,
            ],
        )
        if "NetworkInterfaces" in response and len(response["NetworkInterfaces"]) == 1:
            association = response["NetworkInterfaces"][0]["Association"]
            print(f"Public Ip of {eni_id} is {association['PublicIp']}")
            print("Requesting new ip...")
            new_allocation = client.allocate_address(
                TagSpecifications=[
                    {
                        "ResourceType": "elastic-ip",
                        "Tags": [
                            {"Key": "Name", "Value": "Refreshed IP"},
                        ],
                    },
                ]
            )
            print(
                f"New allocated id {new_allocation['AllocationId']} and public ip is {new_allocation['PublicIp']}"
            )
            client.associate_address(
                AllocationId=new_allocation["AllocationId"],
                NetworkInterfaceId=eni_id,
                PrivateIpAddress=response["NetworkInterfaces"][0]["PrivateIpAddress"],
            )
            print(f"Associated IP.")
            print(f"Releasing IP.")
            client.release_address(AllocationId=association["AllocationId"])
            print(f"Released IP.")
            return new_allocation["PublicIp"]
    except Exception as e:
        print(f"Error in IP Reassignment : {str(e)}")
        return False

#------Rate limit functions ENDS------

#------CAPTCHA FUNCTIONS----------
#Captcha  MANUAL
def captcha_builder_manual(resp):
    from PIL import Image
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    with open("captcha.svg", "w") as f:
        f.write(re.sub('(<path d=)(.*?)(fill="none"/>)', "", resp["captcha"]))

    drawing = svg2rlg("captcha.svg")
    renderPM.drawToFile(drawing, "captcha.png", fmt="PNG")

    im = Image.open("captcha.png")
    im = im.convert("RGB").convert("P", palette=Image.ADAPTIVE)
    im.save("captcha.gif")

    layout = [
        [sg.Image("captcha.gif")],
        [sg.Text("Enter Captcha Below")],
        [sg.Input(key="input")],
        [sg.Button("Submit", bind_return_key=True)],
    ]

    window = sg.Window("Enter Captcha", layout, finalize=True)
    window.TKroot.focus_force()  # focus on window
    window.Element("input").SetFocus()  # focus on field
    event, values = window.read()
    window.close()
    return values["input"]

#Captcha AUTO
def captcha_builder_auto(resp):
    model = open(os.path.join(os.path.dirname(sys.argv[0]), "model.txt")).read()
    svg_data = resp["captcha"]
    soup = BeautifulSoup(svg_data, "html.parser")
    model = json.loads(base64.b64decode(model.encode("ascii")))
    CAPTCHA = {}

    for path in soup.find_all("path", {"fill": re.compile("#")}):
        ENCODED_STRING = path.get("d").upper()
        INDEX = re.findall("M(\d+)", ENCODED_STRING)[0]
        ENCODED_STRING = re.findall("([A-Z])", ENCODED_STRING)
        ENCODED_STRING = "".join(ENCODED_STRING)
        CAPTCHA[int(INDEX)] = model.get(ENCODED_STRING)

    CAPTCHA = sorted(CAPTCHA.items())
    CAPTCHA_STRING = ""

    for char in CAPTCHA:
        CAPTCHA_STRING += char[1]
    return CAPTCHA_STRING

#------CAPTCHA FUNCTIONS ENDS----------

#------Utils Functions----------

#is token valid function
def is_token_valid(token):
    payload = jwt.decode(token, options={"verify_signature": False})
    remaining_seconds = payload["exp"] - int(time.time())
    if remaining_seconds <= 1 * 30:  # 30 secs early before expiry for clock issues
        return False
    if remaining_seconds <= 60:
        print("Token is about to expire in next 1 min ...")
    return True

SMS_REGEX = r"(?<!\d)\d{6}(?!\d)"

WARNING_BEEP_DURATION = (1000, 5000)

if os.getenv("BEEP") == "no":

    def beep(freq, duration):
        pass

else:
    try:
        import winsound

    except ImportError:
        import os

        if sys.platform == "darwin":

            def beep(freq, duration):
                # brew install SoX --> install SOund eXchange universal sound sample translator on mac
                os.system(f"play -n synth {duration / 1000} sin {freq} >/dev/null 2>&1")

        else:

            def beep(freq, duration):
                # apt-get install beep  --> install beep package on linux distros before running
                os.system("beep -f %s -l %s" % (freq, duration))

    else:

        def beep(freq, duration):
            winsound.Beep(freq, duration)


def viable_options(resp, minimum_slots, min_age_booking, fee_type, dose_num):
    options = []
    if len(resp["centers"]) >= 0:
        for center in resp["centers"]:
            for session in center["sessions"]:
                # Cowin uses slot number for display post login, but checks available_capacity before booking appointment is allowed
                available_capacity = min(
                    session[f"available_capacity_dose{dose_num}"],
                    session["available_capacity"],
                )
                if (
                    (available_capacity >= minimum_slots)
                    and (session["min_age_limit"] <= min_age_booking)
                    and (center["fee_type"] in fee_type)
                ):
                    out = {
                        "name": center["name"],
                        "district": center["district_name"],
                        "pincode": center["pincode"],
                        "center_id": center["center_id"],
                        "vaccine": session["vaccine"],
                        "fee_type": center["fee_type"],
                        "available": available_capacity,
                        "date": session["date"],
                        "slots": session["slots"],
                        "session_id": session["session_id"],
                    }
                    options.append(out)

                else:
                    pass
    else:
        pass

    return options


def display_table(dict_list):
    """
    This function
        1. Takes a list of dictionary
        2. Add an Index column, and
        3. Displays the data in tabular format
    """
    header = ["idx"] + list(dict_list[0].keys())
    rows = [[idx + 1] + list(x.values()) for idx, x in enumerate(dict_list)]
    print(tabulate.tabulate(rows, header, tablefmt="grid"))


def display_info_dict(details):
    for key, value in details.items():
        if isinstance(value, list):
            if len(value) > 0 and all(isinstance(item, dict) for item in value):
                print(f"\t{key}:")
                display_table(value)
            else:
                print(f"\t{key}\t: {value}")
        else:
            print(f"\t{key}\t: {value}")


def confirm_and_proceed(collected_details, no_tty):
    print(
        "\n================================= Confirm Info =================================\n"
    )
    display_info_dict(collected_details)

    confirm = sg.popup_yes_no("Proceed with above info?") if no_tty else "Yes"
    confirm = confirm if confirm else "Yes"
    if confirm != "Yes":
        print("Details not confirmed. Exiting process.")
        sg.popup_error("Details not confirmed. Exiting process.")
        #os.system("pause")
        sys.exit()


def save_user_info(filename, details):
    print(
        "\n================================= Save Info =================================\n"
    )
    # save_info = input(
    #     "Would you like to save this as a JSON file for easy use next time?: (y/n Default y): "
    # )
    save_info = sg.popup_yes_no(
        "Would you like to save this as a JSON file for easy use next time?"
    )
    print(
        "Would you like to save this as a JSON file for easy use next time?: " + save_info
    )
    save_info = save_info if save_info else "Yes"
    if save_info == "Yes":
        with open(filename, "w") as f:
            # JSON pretty save to file
            json.dump(details, f, sort_keys=True, indent=4)
        print(f"Info saved to {filename} in {os.getcwd()}")


def get_saved_user_info(filename):
    with open(filename, "r") as f:
        data = json.load(f)

    # for backward compatible logic
    if data["search_option"] != 3 and "pin_code_location_dtls" not in data:
        data["pin_code_location_dtls"] = []

    if "find_option" not in data:
        data["find_option"] = 1
    return data


def get_dose_num(collected_details):
    # If any person has vaccine detail populated, we imply that they'll be taking second dose
    # Note: Based on the assumption that everyone have the *EXACT SAME* vaccine status
    if all(
        detail["status"] == "Partially Vaccinated"
        for detail in collected_details["beneficiary_dtls"]
    ):
        return 2

    return 1


def start_date_search(find_option):

    # Get search start date
    print("\nSearch from when?")
    # start_date = (
    #     input(
    #         "\nUse 1 for today, 2 for tomorrow, or provide a date in the format dd-mm-yyyy. Default 2: "
    #     )
    #     if find_option == 1
    #     else input(
    #         "\nUse 1 for today, 2 for tomorrow, 3 for today and tomorrow, or provide a date in the format dd-mm-yyyy. "
    #         "Default 2: "
    #     )
    # )

    date1 = date.today()
    #datetoday= str(date1.month) + "," + str(date1.day) + "," + str(date1.year)

    #GUI for Date
    layoutdate = [
        [sg.Text('Please Select Start date (Format:dd-mm-yyyy):'),sg.Input(key='-selecteddate-')],
        [sg.Button('Today'),sg.Button('Tomorrow'),sg.Button('Today & Tomorrow'),sg.CalendarButton('Select From Calender', target='-selecteddate-', format='%d-%m-%y', default_date_m_d_y=(date1.month,date1.day,date1.year))],
        [sg.Submit()]
    ]

    windowdate = sg.Window('Select Date', layoutdate)
    start_date="NULL"
    while True:
        event, values = windowdate.read()
        if event == sg.WIN_CLOSED:
            break
        elif event == 'Today':
            start_date = "1"
            break
        elif event == 'Tomorrow':
            start_date = "2"
            break
        elif event == 'Today & Tomorrow':
            start_date = "3"
            break
        elif event == 'Select From Calender':
            start_date = values['-selecteddate-']
        elif event == 'Submit':
            if start_date=="NULL":
                start_date="2"
            break

    windowdate.close()

    if not start_date:
        start_date = 2
    elif start_date in ["1", "2", "3"]:
        start_date = int(start_date)
    else:
        try:
            datetime.datetime.strptime(start_date, "%d-%m-%Y")
        except ValueError:
            start_date = 2
            print("Invalid Date! Proceeding with tomorrow.")
    return start_date


def collect_user_details(request_header):
    
    # Get Beneficiaries
    #print("Fetching registered beneficiaries.. ")
    #dispwindow.read()
    beneficiary_dtls = get_beneficiaries(request_header)
    
    if len(beneficiary_dtls) == 0:
        print("There should be at least one beneficiary. Exiting.")
        sg.popup_error('There should be at least one beneficiary.\nExiting!!!')
        #os.system("pause")
        sys.exit(1)

    # Make sure all beneficiaries have the same type of vaccine
    vaccine_types = [beneficiary["vaccine"] for beneficiary in beneficiary_dtls]
    vaccines = Counter(vaccine_types)

    if len(vaccines.keys()) != 1:
        print(
            f"All beneficiaries in one attempt should have the same vaccine type. Found {len(vaccines.keys())}"
        )
        sg.popup_error(f"All beneficiaries in one attempt should have the same vaccine type. Found {len(vaccines.keys())}")
        # os.system("pause")
        sys.exit(1)

    vaccine_type = vaccine_types[
        0
    ]  # if all([beneficiary['status'] == 'Partially Vaccinated' for beneficiary in beneficiary_dtls]) else None
    if not vaccine_type:
        print(
            "\n================================= Vaccine Info =================================\n"
        )
        vaccine_type = get_vaccine_preference()
        print('Vaccine Preference is SET')

    print(
        "\n================================= Location Info =================================\n"
    )

    # get search method to use
    #Location Info GUI
    radio_choices_loc = ['Pincode', 'State/District', 'Smart search State/District for selected Pincodes']
    layout_loc = [
            [sg.Text('Search By:')],
            [sg.Radio(text, 1) for text in radio_choices_loc],
            [sg.Button('Submit'), sg.Button('Exit')]
         ]

    window_loc = sg.Window('Location Search Preferance', layout_loc)
    e,v=window_loc.read()
    window_loc.close()
    for val in v:
        if window_loc.FindElement(val).get()==True:
            preference = val
    preference = int(preference) if preference and int(preference) in [0, 1, 2, 3] else 0
    
    if e == 'Submit':
        if preference == 0:
            search_option = "1"
        elif preference == 1:
            search_option = "2"
        elif preference == 2:
            search_option = "3"
        else:
            search_option = "2"
    elif e == 'Exit':
        sys.exit(1)

    if not search_option or int(search_option) not in [1, 2, 3]:
        search_option = 2
    else:
        search_option = int(search_option)

    pin_code_location_dtls = []
    if search_option == 3:
        location_dtls = get_districts(request_header)
        pin_code_location_dtls = get_pincodes()
    elif search_option == 2:
        # Collect vaccination center preference
        location_dtls = get_districts(request_header)
    else:
        # Collect vaccination center preference
        location_dtls = get_pincodes()
    print(location_dtls)
    print(
        "\n================================= Additional Info =================================\n"
    )

    # Set filter condition
    minimum_slots = sg.popup_get_text(
        f'Filter out centers with availability less than ? Minimum {len(beneficiary_dtls)} : ', 'Slots Amount Filter'
    )
    print('\nMinimum Slots : ' + minimum_slots)
    if minimum_slots:
        minimum_slots = (
            int(minimum_slots)
            if int(minimum_slots) >= len(beneficiary_dtls)
            else len(beneficiary_dtls)
        )
    else:
        minimum_slots = len(beneficiary_dtls)

    # Get refresh frequency
    refresh_freq = sg.popup_get_text(
        'How often do you want to refresh the calendar (in seconds)?\n Default 10. Minimum 5. \n(You might be blocked if the value is too low, in that case please try after a while with a Higher frequency) : ', 'Refresh Rate'
    )
    print('\nRefresh frequency : ' + refresh_freq)
    refresh_freq = int(refresh_freq) if refresh_freq and int(refresh_freq) >= 1 else 15
    

    find_option = sg.popup_yes_no(
        'Date Preference','Yes - search for seven days (rate limits are too high with this search)\nNO - Single date search'
    )

    if find_option=='Yes':
        find_option=1
    else:
        find_option=2

    if not find_option or int(find_option) not in [1, 2]:
        find_option = 2
    else:
        find_option = int(find_option)

    # Checking if partially vaccinated and thereby checking the the due date for dose2
    if all(
        [
            beneficiary["status"] == "Partially Vaccinated"
            for beneficiary in beneficiary_dtls
        ]
    ):
        today = datetime.datetime.today()
        today = today.strftime("%d-%m-%Y")
        due_date = [beneficiary["dose2_due_date"] for beneficiary in beneficiary_dtls]
        dates = Counter(due_date)
        if len(dates.keys()) != 1:
            print(
                f"All beneficiaries in one attempt should have the same due date. Found {len(dates.keys())}"
            )
            sg.popup_error(f"All beneficiaries in one attempt should have the same due date. Found {len(dates.keys())}")
            #os.system("pause")
            sys.exit(1)

        if (
            datetime.datetime.strptime(due_date[0], "%d-%m-%Y")
            - datetime.datetime.strptime(str(today), "%d-%m-%Y")
        ).days > 0:
            print("\nHaven't reached the due date for your second dose")
            search_due_date = sg.popup_yes_no('Do you want to search for the week starting from your due date\nYes : Proceed\nNO : Exit')
            if search_due_date == "Yes":
                start_date = due_date[0]
            else:
                #os.system("pause")
                sg.popup_ok('Exiting Script')
                sys.exit(1)
        else:
            start_date = start_date_search(find_option)
            print(start_date)

    else:
        # Non vaccinated
        start_date = start_date_search(find_option)
        print(start_date)

    fee_type = get_fee_type_preference()
    print("Fee Preferance : ")
    print(fee_type)

    # print(
    #     "\n=========== CAUTION! =========== CAUTION! CAUTION! =============== CAUTION! =======\n"
    # )
    # print(
    #     "===== BE CAREFUL WITH THIS OPTION! AUTO-BOOKING WILL BOOK THE FIRST AVAILABLE CENTRE, DATE, AND A RANDOM SLOT! ====="
    # )
    # auto_book = "yes-please"

    # print("\n================================= Captcha Automation =================================\n")
    #
    # captcha_automation = input("Do you want to automate captcha autofill? (y/n) Default y: ")
    # captcha_automation = "y" if not captcha_automation else captcha_automation

    collected_details = {
        "beneficiary_dtls": beneficiary_dtls,
        "location_dtls": location_dtls,
        "pin_code_location_dtls": pin_code_location_dtls,
        "find_option": find_option,
        "search_option": search_option,
        "minimum_slots": minimum_slots,
        "refresh_freq": refresh_freq,
        # "auto_book": auto_book,
        "start_date": start_date,
        "vaccine_type": vaccine_type,
        "fee_type": fee_type,
        # 'captcha_automation': captcha_automation,
    }
    #dispwindow.close()
    return collected_details


def correct_schema(sessions):
    centers = {}
    if "sessions" in sessions and len(sessions["sessions"]) > 0:
        for session in sessions["sessions"]:
            center_id = session["center_id"]
            if center_id not in centers:
                centers[center_id] = copy.deepcopy(session)
                del centers[center_id]["session_id"]
                del centers[center_id]["date"]
                del centers[center_id]["available_capacity"]
                del centers[center_id]["available_capacity_dose1"]
                del centers[center_id]["available_capacity_dose2"]
                del centers[center_id]["min_age_limit"]
                del centers[center_id]["vaccine"]
                del centers[center_id]["slots"]
                centers[center_id]["sessions"] = []
            centers[center_id]["sessions"].append(
                {
                    "session_id": session["session_id"],
                    "date": session["date"],
                    "available_capacity": session["available_capacity"],
                    "available_capacity_dose1": session["available_capacity_dose1"],
                    "available_capacity_dose2": session["available_capacity_dose2"],
                    "min_age_limit": session["min_age_limit"],
                    "vaccine": session["vaccine"],
                    "slots": session["slots"],
                }
            )
    return {"centers": list(centers.values())}


def filter_centers_by_age(resp, min_age_booking):
    if min_age_booking >= 45:
        center_age_filter = 45
    else:
        center_age_filter = 18

    if "centers" in resp:
        for center in list(resp["centers"]):
            for session in list(center["sessions"]):
                if session["min_age_limit"] != center_age_filter:
                    center["sessions"].remove(session)
                    if len(center["sessions"]) == 0:
                        resp["centers"].remove(center)

    return resp


def check_by_district(
    find_option,
    request_header,
    vaccine_type,
    location_dtls,
    start_date,
    minimum_slots,
    min_age_booking,
    fee_type,
    dose_num,
    beep_required=True,
    ):
    """
    This function
        1. Takes details required to check vaccination calendar
        2. Filters result by minimum number of slots available
        3. Returns False if token is invalid
        4. Returns list of vaccination centers & slots if available
    """
    try:
        print(
            "==================================================================================="
        )
        today = datetime.datetime.today()
        base_url = CALENDAR_URL_DISTRICT if find_option == 1 else FIND_URL_DISTRICT

        if vaccine_type:
            base_url += f"&vaccine={vaccine_type}"

        options = []
        for location in location_dtls:
            resp = requests.get(
                base_url.format(location["district_id"], start_date),
                headers=request_header,
            )

            if resp.status_code == 403 or resp.status_code == 429:
                handle_rate_limited()
                return False

            elif resp.status_code == 401:
                print("TOKEN INVALID")
                return False

            elif resp.status_code == 200:
                resp = resp.json()

                if find_option == 2:
                    resp = correct_schema(resp)

                resp = filter_centers_by_age(resp, min_age_booking)

                if "centers" in resp:
                    print(
                        f"Centers available in {location['district_name']} {'from' if find_option == 1 else 'for'} {start_date} as of {today.strftime('%Y-%m-%d %H:%M:%S')}: {len(resp['centers'])} "
                    )
                    options += viable_options(
                        resp, minimum_slots, min_age_booking, fee_type, dose_num
                    )

            else:
                print(resp.status_code)
                print(resp.headers)
                print(resp.text)

        # beep only when needed
        if beep_required:
            for location in location_dtls:
                if location["district_name"] in [
                    option["district"] for option in options
                ]:
                    for _ in range(2):
                        beep(location["alert_freq"], 150)
        return options

    except Exception as e:
        print(str(e))
        beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def check_by_pincode(
    find_option,
    request_header,
    vaccine_type,
    location_dtls,
    start_date,
    minimum_slots,
    min_age_booking,
    fee_type,
    dose_num,
    ):
    """
    This function
        1. Takes details required to check vaccination calendar
        2. Filters result by minimum number of slots available
        3. Returns False if token is invalid
        4. Returns list of vaccination centers & slots if available
    """
    try:
        print(
            "==================================================================================="
        )
        today = datetime.datetime.today()
        base_url = CALENDAR_URL_PINCODE if find_option == 1 else FIND_URL_PINCODE

        if vaccine_type:
            base_url += f"&vaccine={vaccine_type}"

        options = []
        for location in location_dtls:
            resp = requests.get(
                base_url.format(location["pincode"], start_date), headers=request_header
            )

            if resp.status_code == 403 or resp.status_code == 429:
                handle_rate_limited()
                return False

            elif resp.status_code == 401:
                print("TOKEN INVALID")
                return False

            elif resp.status_code == 200:
                resp = resp.json()

                if find_option == 2:
                    resp = correct_schema(resp)

                resp = filter_centers_by_age(resp, min_age_booking)

                if "centers" in resp:
                    print(
                        f"Centers available in {location['pincode']} {'from' if find_option == 1 else 'for'} {start_date} as of {today.strftime('%Y-%m-%d %H:%M:%S')}: {len(resp['centers'])}"
                    )
                    options += viable_options(
                        resp, minimum_slots, min_age_booking, fee_type, dose_num
                    )

            else:
                print(resp.status_code)
                print(resp.headers)
                print(resp.text)

        for location in location_dtls:
            if int(location["pincode"]) in [option["pincode"] for option in options]:
                for _ in range(2):
                    beep(location["alert_freq"], 150)

        return options

    except Exception as e:
        print(str(e))
        beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def generate_captcha(request_header, captcha_automation):
    print(
        "================================= GETTING CAPTCHA =================================================="
    )
    resp = requests.post(CAPTCHA_URL, headers=request_header)
    print(f"Captcha Response Code: {resp.status_code}")

    if resp.status_code == 200 and captcha_automation == "n":
        return captcha_builder_manual(resp.json())
    elif resp.status_code == 200 and captcha_automation == "y":
        return captcha_builder_auto(resp.json())


def book_appointment(request_header, details, mobile, generate_captcha_pref="n"):
    """
    This function
        1. Takes details in json format
        2. Attempts to book an appointment using the details
        3. Returns True or False depending on Token Validity
           a) 0 - when token is expired
           b) 1 - when token is OK but unable to book due to selected center is completely booked
           c) 2 - when token is OK but unable to book due to any other reason

    """
    try:
        valid_captcha = True
        while valid_captcha:
            # captcha = generate_captcha(request_header, generate_captcha_pref)
            # details["captcha"] = captcha

            print(
                "================================= ATTEMPTING BOOKING =================================================="
            )
            resp = requests.post(BOOKING_URL, headers=request_header, json=details)
            print(f"Booking Response Code: {resp.status_code}")
            print(f"Booking Response : {resp.text}")

            if resp.status_code == 403 or resp.status_code == 429:
                handle_rate_limited()
                pass

            elif resp.status_code == 401:
                print("TOKEN INVALID")
                return 0

            elif resp.status_code == 200:
                beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
                print(
                    "##############    BOOKED!  ############################    BOOKED!  ##############"
                )
                print(
                    "                        Hey, Hey, Hey! It's your lucky day!                       "
                )

                try:
                    appSlipBase = (
                        APPOINTMENT_SLIP_URL
                        + f"?appointment_id={resp.json()['appointment_confirmation_no']}"
                    )
                    appslip = requests.get(appSlipBase, headers=request_header)
                    with open(
                        f"{mobile}_{resp.json()['appointment_confirmation_no']}.pdf",
                        "wb",
                    ) as appSlipPdf:
                        appSlipPdf.write(appslip.content)
                    if os.path.exists(
                        f"{mobile}_{resp.json()['appointment_confirmation_no']}.pdf"
                    ):
                        print(
                            "\nDownload Successful. Check the Current Working Directory for the Appointment Slip."
                        )
                        sg.popup_ok('Download Successful. Check the Current Working Directory for the Appointment Slip.')
                    else:
                        print("\nAppointment Slip Download Failed...")
                        sg.popup_ok('Appointment Slip Download Failed...')

                except Exception as e:
                    print(str(e))

                print("\nPress any key thrice to exit program.")
                sg.popup_ok('Press Ok to Exit')
                # os.system("pause")
                # os.system("pause")
                # os.system("pause")
                dispwindow.close()
                sys.exit()

            elif resp.status_code == 409:
                print(f"Response: {resp.status_code} : {resp.text}")
                try:
                    data = resp.json()
                    # Response: 409 : {"errorCode":"APPOIN0040","error":"This vaccination center is completely booked for the selected date. Please try another date or vaccination center."}
                    if data.get("errorCode", "") == "APPOIN0040":
                        return 1
                except Exception as e:
                    print(str(e))
                return 2
            elif resp.status_code == 400:
                print(f"Response: {resp.status_code} : {resp.text}")
                # Response: 400 : {"errorCode":"APPOIN0044", "error":"Please enter valid security code"}
                pass
            elif resp.status_code >= 500:
                print(f"Response: {resp.status_code} : {resp.text}")
                # Server error at the time of high booking
                # Response: 500 : {"message":"Throughput exceeds the current capacity of your table or index.....","code":"ThrottlingException","statusCode":400,"retryable":true}
                pass
            else:
                print(f"Response: {resp.status_code} : {resp.text}")
                return 2

    except Exception as e:
        print(str(e))
        beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def check_and_book(
    request_header,
    beneficiary_dtls,
    location_dtls,
    pin_code_location_dtls,
    find_option,
    search_option,
    **kwargs,
    ):
    """
    This function
        1. Checks the vaccination calendar for available slots,
        2. Lists all viable options,
        3. Takes user's choice of vaccination center and slot,
        4. Calls function to book appointment, and
        5. Returns True or False depending on Token Validity
    """
    slots_available = False
    try:
        min_age_booking = get_min_age(beneficiary_dtls)

        minimum_slots = kwargs["min_slots"]
        refresh_freq = kwargs["ref_freq"]
        # auto_book = kwargs["auto_book"]
        start_dates = []
        input_start_date = kwargs["start_date"]
        vaccine_type = kwargs["vaccine_type"]
        fee_type = kwargs["fee_type"]
        mobile = kwargs["mobile"]
        # captcha_automation = kwargs['captcha_automation']
        dose_num = kwargs["dose_num"]

        if isinstance(input_start_date, int) and input_start_date in [1, 3]:
            start_dates.append(datetime.datetime.today().strftime("%d-%m-%Y"))
        if isinstance(input_start_date, int) and input_start_date in [2, 3]:
            start_dates.append(
                (datetime.datetime.today() + datetime.timedelta(days=1)).strftime(
                    "%d-%m-%Y"
                )
            )
        if not isinstance(input_start_date, int):
            start_dates.append(input_start_date)

        options = []
        for start_date in start_dates:
            options_for_date = get_options_for_date(
                dose_num,
                fee_type,
                find_option,
                location_dtls,
                min_age_booking,
                minimum_slots,
                pin_code_location_dtls,
                request_header,
                search_option,
                start_date,
                vaccine_type,
            )
            if isinstance(options_for_date, bool):
                return False
            options.extend(options_for_date)

        options = sorted(
            options,
            key=lambda k: (
                k["district"].lower(),
                k["pincode"],
                k["name"].lower(),
                datetime.datetime.strptime(k["date"], "%d-%m-%Y"),
            ),
        )

        tmp_options = copy.deepcopy(options)
        if len(tmp_options) > 0:
            cleaned_options_for_display = []
            for item in tmp_options:
                item.pop("session_id", None)
                item.pop("center_id", None)
                cleaned_options_for_display.append(item)

            display_table(cleaned_options_for_display)
            slots_available = True
        else:
            try:
                for i in range(refresh_freq, 0, -1):
                    msg = f"\nNo viable options. Next update in {i} seconds..."
                    print(msg, end="\r")
                    # sys.stdout.flush()
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Keyboard Interrupt - OK. Refreshing...")
            slots_available = False

    except TimeoutOccurred:
        time.sleep(1)
        return True

    else:
        if not slots_available:
            return True
        else:
            # If we reached here then it means there is at-least one center having required doses.

            # sort options based on max available capacity of vaccine doses
            # highest available capacity of vaccine doses first for better chance of booking

            # ==> Caveat: if multiple folks are trying for same region like tier-I or tier-II cities then
            # choosing always first maximum available capacity may be a problem.
            # To solve this problem, we can use bucketization logic on top of available capacity
            #
            # Example:
            # meaning of pair is {center id, available capacity of vaccine doses at the center}
            # options = [{c1, 203}, {c2, 159}, {c3, 180}, {c4, 25}, {c5, 120}]
            #
            # Solution-1) Max available capacity wise ordering of options = [{c1, 203}, {c3, 180}, {c2, 159}, {c5, 120}, {c4, 25}]
            # Solution-2) Max available capacity with simple bucketization wise ordering of options = [{c1, 200}, {c3, 150}, {c2, 150}, {c5, 100}, {c4, 0}] when bucket size = 50
            # Solution-3) Max available capacity with simple bucketization & random seed wise ordering of options = [{c1, 211}, {c2, 180}, {c3, 160}, {c5, 123}, {c4, 15}] when bucket size = 50 + random seed
            #
            # Solution-3) is best as it also maximizing the chance of booking while considering max
            # at the same time it also adds flavour of randomization to handle concurrency.

            BUCKET_SIZE = 50
            options = sorted(
                options,
                key=lambda k: (BUCKET_SIZE * int(k.get("available", 0) / BUCKET_SIZE))
                + random.randint(0, BUCKET_SIZE - 1),
                reverse=True,
            )

            start_epoch = int(time.time())

            # if captcha automation is enabled then have less duration for stale information of centers & slots.
            MAX_ALLOWED_DURATION_OF_STALE_INFORMATION_IN_SECS = (
                1 * 60
            )  # if captcha_automation == 'n' else 2*60

            # Now try to look into all options unless it is not authentication related issue
            for i in range(0, len(options)):
                option = options[i]
                all_slots_of_a_center = option.get("slots", [])
                if not all_slots_of_a_center:
                    continue
                # For better chances of booking, use random slots of a particular center
                # This will help if too many folks are trying for same region at the same time.
                # Everyone will have better chances of booking otherwise everyone will look for same slot of same center at a time.
                # Randomized slots selection is maximizing chances of booking
                random.shuffle(all_slots_of_a_center)  # in-place modification

                for selected_slot in all_slots_of_a_center:
                    # if have spent too much time in loop iteration then means we are looking at stale information about centers & slots.
                    # so we should re-calculate this information while ending this loop more aggressively.
                    current_epoch = int(time.time())
                    if (
                        current_epoch - start_epoch
                        >= MAX_ALLOWED_DURATION_OF_STALE_INFORMATION_IN_SECS
                    ):
                        print(
                            "tried too many centers but still not able to book then look for current status of centers ..."
                        )
                        return True

                    try:
                        center_id = option["center_id"]
                        print(
                            f"============> Trying Choice # {i} Center # {center_id}, Slot #{selected_slot}"
                        )

                        dose_num = (
                            2
                            if [
                                beneficiary["status"]
                                for beneficiary in beneficiary_dtls
                            ][0]
                            == "Partially Vaccinated"
                            else 1
                        )
                        new_req = {
                            "beneficiaries": [
                                beneficiary["bref_id"]
                                for beneficiary in beneficiary_dtls
                            ],
                            "dose": dose_num,
                            "center_id": option["center_id"],
                            "session_id": option["session_id"],
                            "slot": selected_slot,
                        }
                        print(f"Booking with info: {new_req}")
                        booking_status = book_appointment(
                            request_header, new_req, mobile
                        )
                        # booking_status = book_appointment(request_header, new_req, mobile, captcha_automation)
                        # is token error ? If yes then break the loop by returning immediately
                        if booking_status == 0:
                            return False
                        else:
                            # try irrespective of booking status as it will be beneficial choice.
                            # try different center as slots are full for this center
                            # break the slots loop
                            print("Center is fully booked..Trying another...")
                            break
                    except IndexError:
                        print("============> Invalid Option!")
                        os.system("pause")
                        pass

            # tried all slots of all centers but still not able to book then look for current status of centers
            return True


def get_options_for_date(
    dose_num,
    fee_type,
    find_option,
    location_dtls,
    min_age_booking,
    minimum_slots,
    pin_code_location_dtls,
    request_header,
    search_option,
    start_date,
    vaccine_type,
    ):
    if search_option == 3:
        options = check_by_district(
            find_option,
            request_header,
            vaccine_type,
            location_dtls,
            start_date,
            minimum_slots,
            min_age_booking,
            fee_type,
            dose_num,
            beep_required=False,
        )

        if not isinstance(options, bool):
            pincode_filtered_options = []
            for option in options:
                for location in pin_code_location_dtls:
                    if int(location["pincode"]) == int(option["pincode"]):
                        # ADD this filtered PIN code option
                        pincode_filtered_options.append(option)
                        for _ in range(2):
                            beep(location["alert_freq"], 150)
            options = pincode_filtered_options

    elif search_option == 2:
        options = check_by_district(
            find_option,
            request_header,
            vaccine_type,
            location_dtls,
            start_date,
            minimum_slots,
            min_age_booking,
            fee_type,
            dose_num,
            beep_required=True,
        )
    else:
        options = check_by_pincode(
            find_option,
            request_header,
            vaccine_type,
            location_dtls,
            start_date,
            minimum_slots,
            min_age_booking,
            fee_type,
            dose_num,
        )
    return options


def get_vaccine_preference():
    print(
        "\n\nIt seems you're trying to find a slot for your first dose. Do you have a vaccine preference?"
    )

    #GUI Vaccine Preferance
    radio_choices = ['COVISHIELD', 'COVAXIN', 'SPUTNIK V', 'ANY']
    layoutvac = [
            [sg.Text("It seems you're trying to find a slot for your first dose. Do you have a vaccine preference?")],
            [sg.Radio(text, 1) for text in radio_choices],
            [sg.Button('Submit'), sg.Button('Exit')]
         ]
    
    windowvac = sg.Window('Vaccine Preference', layoutvac)
    e,v=windowvac.read()
    windowvac.close()
    preference=""
    for val in v:
        if windowvac.FindElement(val).get()==True:
            preference = val
    
    preference = int(preference) if preference and int(preference) in [0, 1, 2, 3] else 0

    if e == 'Submit':
        if preference == 0:
            return "COVISHIELD"
        elif preference == 1:
            return "COVAXIN"
        elif preference == 2:
            return "SPUTNIK V"
        
        else:
            return None
    elif e == 'Exit':
        sys.exit(1)

def get_fee_type_preference():
    #GUI Fee Preferance
    radio_choices = ['Free', 'Paid', 'Any']
    layoutfee = [
            [sg.Text("Do you have a fee type preference?")],
            [sg.Radio(text, 1) for text in radio_choices],
            [sg.Button('Submit'), sg.Button('Exit')]
         ]
    
    windowfee = sg.Window('Fee Preference', layoutfee)
    e,v=windowfee.read()
    windowfee.close()
    preference=""
    for val in v:
        if windowfee.FindElement(val).get()==True:
            preference = val
    
    preference = int(preference) if preference and int(preference) in [0, 1, 2] else 0

    if e == 'Submit':
        if preference == 0:
            return ["Free"]
        elif preference == 1:
            return ["Paid"]
        elif preference == 2:
            return ["Free", "Paid"]
        else:
            return ["Free", "Paid"]
    elif e == 'Exit':
        sys.exit(1)


def get_pincodes():
    locations = []
    pincodes = sg.popup_get_text('Enter comma separated 6 digit pincodes to monitor: ', 'Enter Pincodes')
    for idx, pincode in enumerate(pincodes.split(",")):
        if not pincode or len(pincode) < 6:
            print(f"Ignoring invalid pincode: {pincode}")
            continue
        pincode = {"pincode": pincode, "alert_freq": 440 + ((2 * idx) * 110)}
        locations.append(pincode)
    return locations


def get_districts(request_header):
    """
    This function
        1. Lists all states, prompts to select one,
        2. Lists all districts in that state, prompts to select required ones, and
        3. Returns the list of districts as list(dict)
    """
    states = requests.get(
        "https://cdn-api.co-vin.in/api/v2/admin/location/states", headers=request_header
    )

    if states.status_code == 200:
        states = states.json()["states"]

        refined_states = []
        for state in states:
            tmp = {"state": state["state_name"]}
            refined_states.append(tmp)

        display_table(refined_states)
    
        state = int(sg.popup_get_text('Enter State Index No\nStates Displayed in Main Window','State Select'))

        state_id = states[state - 1]["state_id"]

        districts = requests.get(
            f"https://cdn-api.co-vin.in/api/v2/admin/location/districts/{state_id}",
            headers=request_header,
        )

        if districts.status_code == 200:
            districts = districts.json()["districts"]

            refined_districts = []
            for district in districts:
                tmp = {"district": district["district_name"]}
                refined_districts.append(tmp)

            display_table(refined_districts)
            reqd_districts = sg.popup_get_text('Enter comma separated index numbers of districts to monitor : ')
            districts_idx = [int(idx) - 1 for idx in reqd_districts.split(",")]
            reqd_districts = [
                {
                    "district_id": item["district_id"],
                    "district_name": item["district_name"],
                    "alert_freq": 440 + ((2 * idx) * 110),
                }
                for idx, item in enumerate(districts)
                if idx in districts_idx
            ]

            print(f"Selected districts: ")
            display_table(reqd_districts)
            return reqd_districts

        else:
            print("Unable to fetch districts")
            print(districts.status_code)
            print(districts.text)
            sg.popup_error("Unable to fetch districts")
            #os.system("pause")
            sys.exit(1)

    else:
        print("Unable to fetch states")
        print(states.status_code)
        print(states.text)
        sg.popup_error("Unable to fetch states")
        #os.system("pause")
        sys.exit(1)


def fetch_beneficiaries(request_header):
    return requests.get(BENEFICIARIES_URL, headers=request_header)


def vaccine_dose2_duedate(vaccine_type):
    """
    This function
        1.Checks the vaccine type
        2.Returns the appropriate due date for the vaccine type
    """
    covishield_due_date = 84
    covaxin_due_date = 28
    sputnikV_due_date = 21

    if vaccine_type == "COVISHIELD":
        return covishield_due_date
    elif vaccine_type == "COVAXIN":
        return covaxin_due_date
    elif vaccine_type == "SPUTNIK V":
        return sputnikV_due_date


def get_beneficiaries(request_header):
    """
    This function
        1. Fetches all beneficiaries registered under the mobile number,
        2. Prompts user to select the applicable beneficiaries, and
        3. Returns the list of beneficiaries as list(dict)
    """
    beneficiaries = fetch_beneficiaries(request_header)

    vaccinated = False

    if beneficiaries.status_code == 200:
        beneficiaries = beneficiaries.json()["beneficiaries"]

        refined_beneficiaries = []
        for beneficiary in beneficiaries:
            beneficiary["age"] = datetime.datetime.today().year - int(
                beneficiary["birth_year"]
            )
            if beneficiary["vaccination_status"] == "Partially Vaccinated":
                vaccinated = True
                days_remaining = vaccine_dose2_duedate(beneficiary["vaccine"])

                dose1_date = datetime.datetime.strptime(
                    beneficiary["dose1_date"], "%d-%m-%Y"
                )
                beneficiary["dose2_due_date"] = dose1_date + datetime.timedelta(
                    days=days_remaining
                )
            else:
                vaccinated = False
                # print(beneficiary_2)

            tmp = {
                "bref_id": beneficiary["beneficiary_reference_id"],
                "name": beneficiary["name"],
                "vaccine": beneficiary["vaccine"],
                "age": beneficiary["age"],
                "status": beneficiary["vaccination_status"],
                "dose1_date": beneficiary["dose1_date"],
            }
            if vaccinated:
                tmp["due_date"] = beneficiary["dose2_due_date"]
            refined_beneficiaries.append(tmp)

        print(
            "\n================================= Benificiaries Registered =================================\n"
        )
        display_table(refined_beneficiaries)
        # print(refined_beneficiaries)
        print(
            """
                        ################# IMPORTANT NOTES #################
        # 1. While selecting beneficiaries, make sure that selected beneficiaries are all taking the same dose: either first OR second.
        #    Please do no try to club together booking for first dose for one beneficiary and second dose for another beneficiary.
        #
        # 2. While selecting beneficiaries, also make sure that beneficiaries selected for second dose are all taking the same vaccine: COVISHIELD OR COVAXIN.
        #    Please do no try to club together booking for beneficiary taking COVISHIELD with beneficiary taking COVAXIN.
        #
        # 3. If you're selecting multiple beneficiaries, make sure all are of the same age group (45+ or 18+) as defined by the govt.
        #    Please do not try to club together booking for younger and older beneficiaries.
                        ###################################################
        """
        )

        #GUI for Selecting Benificiaries
        reqd_beneficiaries=""
        layoutusers = [
            [sg.Text('Benificiary Indexes are listed in the Main Window followed by the names.\nPlease read Importannt Notes(Main Window) Before selecting')],
            [sg.Checkbox('Benificiary 1', key='Benificiary 1'), sg.Checkbox('Benificiary 2', key='Benificiary 2'), sg.Checkbox('Benificiary 3', key='Benificiary 3'), sg.Checkbox('Benificiary 4', key='Benificiary 4')],
            [sg.Submit()]
        ]
        windowusers = sg.Window('Select Benificiary',layoutusers)
        event, values = windowusers.read()
        windowusers.close()
        if event == sg.WIN_CLOSED:
            sys.exit(1)
        elif event == 'Submit':
            if values['Benificiary 1']== True:
                reqd_beneficiaries = reqd_beneficiaries + ",1"
            if values['Benificiary 2']== True:
                reqd_beneficiaries = reqd_beneficiaries + ",2"
            if values['Benificiary 3']== True:
                reqd_beneficiaries = reqd_beneficiaries + ",3"
            if values['Benificiary 4']== True:
                reqd_beneficiaries = reqd_beneficiaries + ",4"
        


        # reqd_beneficiaries = input(
        #     "Enter comma separated index numbers of beneficiaries to book for : "
        # )
        reqd_beneficiaries = reqd_beneficiaries[1:]
        beneficiary_idx = [int(idx) - 1 for idx in reqd_beneficiaries.split(",")]
        reqd_beneficiaries = [
            {
                "bref_id": item["beneficiary_reference_id"],
                "name": item["name"],
                "vaccine": item["vaccine"],
                "age": item["age"],
                "status": item["vaccination_status"],
                "dose1_date": item["dose1_date"],
            }
            for idx, item in enumerate(beneficiaries)
            if idx in beneficiary_idx
        ]

        for beneficiary in reqd_beneficiaries:
            if beneficiary["status"] == "Partially Vaccinated":
                days_remaining = vaccine_dose2_duedate(beneficiary["vaccine"])

                dose1_date = datetime.datetime.strptime(
                    beneficiary["dose1_date"], "%d-%m-%Y"
                )
                dose2DueDate = dose1_date + datetime.timedelta(days=days_remaining)
                beneficiary["dose2_due_date"] = dose2DueDate.strftime("%d-%m-%Y")

        print(
            "\n================================= Selected beneficiaries =================================\n"
        )
        display_table(reqd_beneficiaries)
        selected_user_verify = sg.popup_yes_no('Are the selected Users correct? (Selecting No will exit the program)')
        if selected_user_verify == "No":
            sg.PopupError('Exiting Program')
            sys.exit(1)
        else:
            return reqd_beneficiaries

    else:
        print("Unable to fetch beneficiaries")
        print(beneficiaries.status_code)
        print(beneficiaries.text)
        os.system("pause")
        return []


def get_min_age(beneficiary_dtls):
    """
    This function returns a min age argument, based on age of all beneficiaries
    :param beneficiary_dtls:
    :return: min_age:int
    """
    age_list = [item["age"] for item in beneficiary_dtls]
    min_age = min(age_list)
    return min_age


def clear_bucket_and_send_OTP(storage_url, mobile, request_header):
    print("clearing OTP bucket: " + storage_url)
    response = requests.put(storage_url, data={})
    data = {
        "mobile": mobile,
        "secret": "U2FsdGVkX1+z/4Nr9nta+2DrVJSv7KS6VoQUSQ1ZXYDx/CJUkWxFYG6P3iM/VW+6jLQ9RDQVzp/RcZ8kbT41xw==",
    }
    print(f"Requesting OTP with mobile number {mobile}..")
    txnId = requests.post(
        url="https://cdn-api.co-vin.in/api/v2/auth/generateMobileOTP",
        json=data,
        headers=request_header,
    )

    if txnId.status_code == 200:
        txnId = txnId.json()["txnId"]
    else:
        print("Unable to Create OTP")
        print(txnId.text)
        if txnId.status_code == 403 or txnId.status_code == 429:
            handle_rate_limited()
        time.sleep(5)  # Saftey net againt rate limit
        txnId = None

    return txnId


def generate_token_OTP(mobile, request_header, kvdb_bucket):
    """
    This function generate OTP and returns a new token or None when not able to get token
    """
    storage_url = "https://kvdb.io/" + kvdb_bucket + "/" + mobile

    txnId = clear_bucket_and_send_OTP(storage_url, mobile, request_header)

    if txnId is None:
        return txnId

    time.sleep(10)
    t_end = time.time() + 60 * 3  # try to read OTP for atmost 3 minutes
    while time.time() < t_end:
        response = requests.get(storage_url)
        if response.status_code == 200:
            print("OTP SMS is:" + response.text)
            print("OTP SMS len is:" + str(len(response.text)))
            OTP = extract_from_regex(response.text, SMS_REGEX)
            if not OTP:
                time.sleep(5)
                continue
            break
        else:
            # Hope it won't 500 a little later
            print("error fetching OTP API:" + response.text)
            time.sleep(5)

    if not OTP:
        return None

    print("Parsed OTP:" + OTP)

    data = {"otp": sha256(str(OTP.strip()).encode("utf-8")).hexdigest(), "txnId": txnId}
    print(f"Validating OTP..")

    token = requests.post(
        url="https://cdn-api.co-vin.in/api/v2/auth/validateMobileOtp",
        json=data,
        headers=request_header,
    )
    if token.status_code == 200:
        token = token.json()["token"]
    else:
        print("Unable to Validate OTP")
        print(token.text)
        return None

    print(f"Token Generated: {token}")
    return token


def extract_from_regex(text, pattern):
    """
    This function extracts all particular string with help of regex pattern from given text
    """
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) > 0:
        return matches[0]
    else:
        return None


def generate_token_OTP_manual(mobile, request_header):
    """
    This function generate OTP and returns a new token
    """

    if not mobile:
        print("Mobile number cannot be empty")
        sg.popup_error('Mobile number cannot be empty')
        sys.exit()

    valid_token = False
    while not valid_token:
        try:
            data = {
                "mobile": mobile,
                "secret": "U2FsdGVkX1+z/4Nr9nta+2DrVJSv7KS6VoQUSQ1ZXYDx/CJUkWxFYG6P3iM/VW+6jLQ9RDQVzp/RcZ8kbT41xw==",
            }
            txnId = requests.post(url=OTP_PRO_URL, json=data, headers=request_header)

            if txnId.status_code == 200:
                # print(
                #     f"Successfully requested OTP for mobile number {mobile} at {datetime.datetime.today()}.."
                # )
                txnId = txnId.json()["txnId"]

                OTP = sg.popup_get_text(f'Successfully requested OTP for mobile number {mobile} at {datetime.datetime.today()}..', 'OTP Manual Entry Box')
                if OTP:
                    data = {
                        "otp": sha256(str(OTP).encode("utf-8")).hexdigest(),
                        "txnId": txnId,
                    }
                    #print(f"Validating OTP..")

                    token = requests.post(
                        url="https://cdn-api.co-vin.in/api/v2/auth/validateMobileOtp",
                        json=data,
                        headers=request_header,
                    )
                    if token.status_code == 200:
                        token = token.json()["token"]
                        #print(f"Token Generated: {token}")
                        valid_token = True
                        return token

                    else:
                        print("Unable to Validate OTP")
                        print(f"Response: {token.text}")

                        retry = sg.popup_yes_no(f'Unable to Validate OTP \nRetry with {mobile} ?')
                        retry = retry if retry else "Yes"
                        if retry == "Yes":
                            pass
                        else:
                            sys.exit()

            else:
                print("Unable to Generate OTP")
                sg.PopupError("Unable to Generate OTP")
                print(txnId.status_code, txnId.text)
                if txnId.status_code == 403 or txnId.status_code == 429:
                    handle_rate_limited()

                retry = sg.popup_yes_no(f'Unable to Validate OTP \nRetry with {mobile} ?')
                retry = retry if retry else "Yes"
                if retry == "Yes":
                    pass
                else:
                    sys.exit()

        except Exception as e:
            print(str(e))
#------Utils Functions ENDS-----


#--------Function Definations END--------#

#--------MAIN FUNCTION--------#

def main():
    # start_booking=sg.popup_yes_no('Do you wnat to start the slot booking process', 'Start Script?')
    # if start_booking=='No':
    #     sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Pass token directly")
    parser.add_argument("--mobile", help="Pass mobile directly")
    parser.add_argument("--kvdb-bucket", help="Pass kvdb.io bucket directly")
    parser.add_argument("--config", help="Config file name")
    parser.add_argument(
        "--no-tty",
        help="Do not ask any terminal inputs. Proceed with smart choices",
        action="store_false",
    )

    args = parser.parse_args()

    if args.config:
        filename = args.config
    else:
        filename = "vaccine-booking-details-"

    if args.mobile:
        mobile = args.mobile
    else:
        mobile = None
        
    if args.kvdb_bucket:
        kvdb_bucket = args.kvdb_bucket
    else:
        kvdb_bucket = KVDB_BUCKET

    print("Running Script")
    beep(500, 150)

    try:
        base_request_header = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36",
            "origin": "https://selfregistration.cowin.gov.in/",
            "referer": "https://selfregistration.cowin.gov.in/",
        }

        token = None
        otp_pref = "n"
        if args.token:
            token = args.token
        else:
            if mobile is None:
                mobile = sg.popup_get_text('Enter the registered mobile number: ', 'Mobile Number')
                print('Enter the registered mobile number: ' + mobile)
            if not args.config:
                filename = filename + mobile + ".json"
            if not kvdb_bucket:
                otp_pref = (
                    sg.popup_yes_no('OTP - Manual/Automatic', 'Do you want to enter OTP manually?\nYES- Enter Manually       NO- Automatic \n\nNote: selecting NO would require some setup described in README')
                    if args.no_tty
                    else "n"
                )
                print('OTP - Manual/Automatic', 'Do you want to enter OTP manually?\nYES- Enter Manually       NO- Automatic \n\nNote: selecting NO would require some setup described in README\nInput :' + otp_pref)
                if otp_pref == 'Yes':
                    otp_pref='y'
                else:
                    otp_pref='n'
                otp_pref = otp_pref if otp_pref else "n"
                if otp_pref == "n":
                    kvdb_bucket = (
                        # input(
                        #     "Please refer KVDB setup in ReadMe to setup your own KVDB bucket. Please enter your KVDB bucket value here: "
                        # )
                        sg.popup_get_text("Please refer KVDB setup in ReadMe to setup your own KVDB bucket. Please enter your KVDB bucket value here: ")
                        if args.no_tty and kvdb_bucket is None
                        else kvdb_bucket
                    )
                    if not kvdb_bucket:
                        print(
                            "Sorry, having your private KVDB bucket is mandatory. Please refer ReadMe and create your own private KVBD bucket."
                        )
                        sys.exit()
            if kvdb_bucket:
                print(
                    "\n### Note ### Please make sure the URL configured in the IFTTT/Shortcuts app on your phone is: "
                    + "https://kvdb.io/"
                    + kvdb_bucket
                    + "/"
                    + mobile
                    + "\n"
                )


            while token is None:
                if otp_pref == "n":
                    try:
                        token = generate_token_OTP(
                            mobile, base_request_header, kvdb_bucket
                        )
                    except Exception as e:
                        print(str(e))
                        print("OTP Retrying in 5 seconds")
                        time.sleep(5)
                elif otp_pref == "y":
                    token = generate_token_OTP_manual(mobile, base_request_header)

        request_header = copy.deepcopy(base_request_header)
        request_header["Authorization"] = f"Bearer {token}"
        #dispwindow.close()

        if os.path.exists(filename):
            print(
                "\n=================================== Note ===================================\n"
            )
            print(
                f"Info from perhaps a previous run already exists in {filename} in this directory."
            )
            print(
                f"IMPORTANT: If this is your first time running this version of the application, DO NOT USE THE FILE!"
            )
            try_file = (
                sg.popup_yes_no(f'Info from perhaps a previous run already exists in {filename} in this directory.\nWould you like to see the details and confirm to proceed?\n\nIMPORTANT: If this is your first time running this version of the application, DO NOT USE THE FILE!(Select NO)')
                if args.no_tty
                else "y"
            )
            if try_file=='Yes':
                try_file='y'
            else:
                try_file='n'
            try_file = try_file if try_file else "y"

            if try_file == "y":
                collected_details = get_saved_user_info(filename)
                print(
                    "\n================================= Info =================================\n"
                )
                display_info_dict(collected_details)

                file_acceptable = (
                    sg.popup_yes_no('Proceed with above info?')
                    if args.no_tty
                    else "y"
                )
                if file_acceptable=='Yes':
                    file_acceptable='y'
                else:
                    file_acceptable='n'
                
                file_acceptable = file_acceptable if file_acceptable else "y"

                if file_acceptable != "y":
                    #dispwindow.close()
                    collected_details = collect_user_details(request_header)
                    save_user_info(filename, collected_details)
                
            else:
                #dispwindow.close()
                collected_details = collect_user_details(request_header)
                save_user_info(filename, collected_details)
                

        else:
            collected_details = collect_user_details(request_header)
            save_user_info(filename, collected_details)
            confirm_and_proceed(collected_details, args.no_tty)
            
        
        # HACK: Temporary workaround for not supporting reschedule appointments
        beneficiary_ref_ids = [
            beneficiary["bref_id"]
            for beneficiary in collected_details["beneficiary_dtls"]
        ]
        beneficiary_dtls = fetch_beneficiaries(request_header)
        if beneficiary_dtls.status_code == 200:
            beneficiary_dtls = [
                beneficiary
                for beneficiary in beneficiary_dtls.json()["beneficiaries"]
                if beneficiary["beneficiary_reference_id"] in beneficiary_ref_ids
            ]
            active_appointments = []
            for beneficiary in beneficiary_dtls:
                expected_appointments = (
                    1
                    if beneficiary["vaccination_status"] == "Partially Vaccinated"
                    else 0
                )
                if len(beneficiary["appointments"]) > expected_appointments:
                    data = beneficiary["appointments"][expected_appointments]
                    beneficiary_data = {
                        "name": data["name"],
                        "state_name": data["state_name"],
                        "dose": data["dose"],
                        "date": data["date"],
                        "slot": data["slot"],
                    }
                    active_appointments.append(
                        {"beneficiary": beneficiary["name"], **beneficiary_data}
                    )

            if active_appointments:
                print(
                    "\n\nThe following appointments are active! Please cancel them manually first to continue"
                )
                display_table(active_appointments)
                beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
                sg.popup_ok("The following appointments are active! Please cancel them manually first to continue")
                return
        else:
            print(
                "WARNING: Failed to check if any beneficiary has active appointments. Please cancel before using this script"
            )
            if args.no_tty:
                sg.popup_ok('Press OK to continue execution...') #input("Press any key to continue execution...")

        info = SimpleNamespace(**collected_details)

        if info.find_option == 1:
            disable_re_assignment_feature()

        print('Slot Booking Process Starting')

        while True:  # infinite-loop
            # create new request_header
            request_header = copy.deepcopy(base_request_header)
            request_header["Authorization"] = f"Bearer {token}"

            # call function to check and book slots
            try:
                token_valid = is_token_valid(token)

                # token is invalid ?
                # If yes, generate new one
                if not token_valid:
                    print("Token is INVALID.")
                    token = None
                    while token is None:
                        if otp_pref == "n":
                            try:
                                token = generate_token_OTP(
                                    mobile, base_request_header, kvdb_bucket
                                )
                            except Exception as e:
                                print(str(e))
                                print("OTP Retrying in 5 seconds")
                                time.sleep(5)
                        elif otp_pref == "y":
                            token = generate_token_OTP_manual(
                                mobile, base_request_header
                            )

                check_and_book(
                    request_header,
                    info.beneficiary_dtls,
                    info.location_dtls,
                    info.pin_code_location_dtls,
                    info.find_option,
                    info.search_option,
                    min_slots=info.minimum_slots,
                    ref_freq=info.refresh_freq,
                    # auto_book=info.auto_book,
                    start_date=info.start_date,
                    vaccine_type=info.vaccine_type,
                    fee_type=info.fee_type,
                    mobile=mobile,
                    # captcha_automation=info.captcha_automation,
                    dose_num=get_dose_num(collected_details),
                )
            except Exception as e:
                print(str(e))
                print("Retryin in 5 seconds")
                time.sleep(5)
        #window.close()
    except Exception as e:
        print(str(e))
        print("Exiting Script")
        sg.popup_error('Exiting Script')
        # os.system("pause")
        dispwindow.close()
        sys.exit(1)

#--------MAIN FUNCTION END--------#


#---FIRST LINES OF CODE---
if __name__ == '__main__':
    #---Main GUI window Declerations---
    #sg.theme('Dark Teal 10')
    dispwindow.read()
    print('Click Start to Book')
    main()
    dispwindow.close()
