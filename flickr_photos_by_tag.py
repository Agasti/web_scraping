import argparse
import textwrap
import time
import json
import re
import requests
import random
import datetime
# import copy
import os.path
import csv
import shutil
from datetime import datetime as dt
from tempfile import NamedTemporaryFile
from copy import deepcopy

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from fake_useragent import UserAgent

global driver, params, AFTER_DATE, BEFORE_DATE, COURTESY_SLEEP, PHOTOS_PER_PAGE
global VERBOSE, TEST, DUMP_PATH, ADD_EXTRAS, HEADLESS, GEO_BOX

# AFTER_DATE = dt.fromtimestamp(1546800000) # 2020/01/06
# #AFTER_DATE = dt.fromtimestamp(1072915200) # 2014/01/01
# BEFORE_DATE = dt.now()
# PHOTOS_PER_PAGE =  250
# VERBOSE = 3
# DUMP_PATH = './'
# TEST = True
# ADD_EXTRAS = 'url_o,original_format,date_taken,date_upload,geo'
# HEADLESS = True
# COURTESY_SLEEP = "0, 0.000000001"
# GET_DATES_ONLY = False
# BBOX_PHOTOS_PER_PAGE = 250
# GEO_BOX = '-124.799423, 24.750821, -54.517891, 54.306268' # US and Canada

parser = argparse.ArgumentParser(description=textwrap.dedent('''\
        scrape JSONs containing photos from flickr
         '''))

parser.add_argument(
    "-a", "--after_date",
    help=r"Start date (in unix timestamp format).\Defaults to yesterday",
    type=float, default=dt.now().timestamp() - (30 * 24 * 3600))
parser.add_argument(
    "-b",
    "--before_date",
    help="End date (in unix timestamp format). Defaults to now",
    type=float,
    default=dt.now().timestamp())
parser.add_argument(
    "-s",
    "--courtesy_sleep",
    help="Range (in string format) from which a random value will be chosen to sleep randomly. example: '1.3, 2.7'",
    type=str,
    default="1.3, 2.7")
parser.add_argument(
    "-n",
    "--photos_per_page",
    help="Photos per file. Default is 500 which is the maximum",
    type=int,
    default=500)
parser.add_argument(
    "-v",
    "--verbose",
    help="increase output verbosity",
    action="count",
    default=0)
parser.add_argument(
    "-p",
    "--dump_path",
    help="Path where to dump json files",
    type=str,
    default='./')
parser.add_argument("-t", "--test", help="test mode", action='store_true')
parser.add_argument(
    "-d", "--get_dates_only",
    help="Only scan for suitable ranges and store them on csv file.\
                    \n suitable ranges are dates where the photos returned aproximates\
                    4000",
    action='store_true')
parser.add_argument(
    "-g", "--geo_box",
    help="Limit the search to the geographical locations in the bounding\
                    box defined by 4 values. The 4 values represent the bottom-left corner \
                    of the box and the top-right corner, minimum_longitude, minimum_latitude, \
                    maximum_longitude, maximum_latitude. Defaults to '-180, -90, 180, 90'",
    default='-180, -90, 180, 90')
parser.add_argument(
    "-w", "--webdriver",
    help="Turn off headless mode for on the chrome webdriver",
    action='store_false')
parser.add_argument(
    "-x", "--add_extras",
    help="extra json fields to request. Defaults to 'url_o,original_format\
                    ,date_taken,date_upload,geo'",
    type=str, default="url_o,original_format,date_taken,date_upload,geo")

args = parser.parse_args()


args.__dict__['HEADLESS'] = args.webdriver

# ansigning global variables from cmdline args for easy typing
for each in args.__dict__:
    globals()[each.upper()] = args.__dict__[each]

# making sure the dates are in datetime format
for each in ["AFTER_DATE", "BEFORE_DATE"]:
    if type(each) != type(dt.now()):
        try:
            globals()[each] = dt.fromtimestamp(globals()[each])
        except Exception as e:
            print(
                f"please make sure the dates entered are in unix timestamps format: {e}")

# printing parameters for easy debugging
if VERBOSE >= 3:
    print("".ljust(120, "_") + "\nscript parameters")
    for each in args.__dict__:
        print(f"{each.upper()}: {args.__dict__[each]}")
    print("".ljust(120, "_"))


COURTESY_SLEEP = [
    float(
        COURTESY_SLEEP.split(',')[0]), float(
            COURTESY_SLEEP.split(',')[1])]
if TEST and VERBOSE > 3:
    COURTESY_SLEEP = [0, 0.000000001]


DATA_PATH = ('./test/' if TEST else DUMP_PATH)

params = {
    #
    "bbox": GEO_BOX,
    "sort": "relevance",
    "parse_tags": "1",
    "content_type": "7",
    "lang": "en-US",
    "has_geo": "1",
    "media": "photos",
    "view_all": "1",
    "text": "clouds",
    "viewerNSID": "",
    "method": "flickr.photos.search",
    "csrf": "",
    "format": "json",
    "hermes": "1",
    "hermesClient": "1",
    "nojsoncallback": "1",
    "geo_context": '2',  # 0: all , 1: indoors, 2 : outdoors
    "privacy_filter": 1
}

privacy_filters = '''
"public photos" : '1',
"private photos visible to friends" : '2',
"private photos visible to family" : '3',
"private photos visible to friends & family": '4',
"completely private photos" : '5'
'''

FLICKR = 'https://flickr.com/search/'
TAGS = [
    'rain cloud',
    'sun clouds',
    'sunny clouds',
    'clouds',
    'cloud',
    'sky',
    'storm',
    'weather',
    'cloudy']

var_names = ["api_key", "reqId", "api_url", "extras"]
re_expressions = [
    r"(api_key)=([\dabcdef]*)(&)",
    r"(reqId)=([\dabcdef]*)(&)",
    r"(https:\/\/(\w+\.?)+(\/\w+)+)(\?)",
    r"extras=((\w+(%2)?)+?)?&"]
groups = [2, 2, 1, 1]

variables = [dict(zip(["var_name", "regex", 'group'], each)) for each in [
                  each for each in zip(var_names, re_expressions, groups)]]


def get_api_call_string():
    ''' use selenium to get the api_call string'''

    options = Options()

    if HEADLESS:
        options.add_argument('--headless')

    caps = DesiredCapabilities.CHROME
    caps['loggingPref'] = {'performance': 'ALL'}

    driver = webdriver.Chrome(options=options, desired_capabilities=caps)

    xhrCallIntercept_js = """
    (function(XHR) {
      "use strict";

      var element = document.createElement('div');
      element.id = "interceptedResponse";
      element.appendChild(document.createTextNode(""));
      document.body.appendChild(element);

      var open = XHR.prototype.open;
      var send = XHR.prototype.send;

      XHR.prototype.open = function(method, url, async, user, pass) {
        this._url = url; // want to track the url requested
        open.call(this, method, url, async, user, pass);
      };

      XHR.prototype.send = function(data) {
        var self = this;
        var oldOnReadyStateChange;
        var url = this._url;

        function onReadyStateChange() {
          if(self.status === 200 && self.readyState == 4 /* complete */) {
            document.getElementById("interceptedResponse").innerHTML +=
              '{"data":' + self._url + ', "headers" :' + self.headers + ' }*****';
          }
          if(oldOnReadyStateChange) {
            oldOnReadyStateChange();
          }
        }

        if(this.addEventListener) {
          this.addEventListener("readystatechange", onReadyStateChange,
            false);
        } else {
          oldOnReadyStateChange = this.onreadystatechange;
          this.onreadystatechange = onReadyStateChange;
        }
        send.call(this, data);
      }
    })(XMLHttpRequest);
    """

    try:
        url = FLICKR + "?has_geo=1&media=photos&view_all=1&text=" + TAGS[0]

        driver.get(url)

        driver.execute_script(xhrCallIntercept_js)

        if VERBOSE >= 1:
            print('title : "{}"'.format(driver.title))

    except Exception as e:
        print('Error! Cannot open search page: ' + str(e))

    wait = False
    while not wait:
        if VERBOSE >= 1:
            print("Getting AJAX data...")
        # trying scroll to trigger and api call
        try:
            if VERBOSE >= 3:
                print('attempting Scroll!')
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            if VERBOSE >= 3:
                print('Scrolled...')

            # waiting for the api call to be included in the DOM
            wait = WebDriverWait(
                driver, 15).until(
                EC.text_to_be_present_in_element(
                    (By.ID, "interceptedResponse"),
                    "api_key"))

        except Exception as e:
            print("intercept failed!:" + str(e))

        intercepts = driver.find_elements_by_id('interceptedResponse')

    if wait == True and VERBOSE >= 1:
        print('ajax call intercepted!\n')
    xhr_api_call = intercepts[0].text

    cookies = driver.get_cookies()
    driver.close()

    return xhr_api_call, cookies


def parse_api_call(call_string):
    ''' parsing data from DOM element '''
    # creating variables for each parsed data
    for each in variables:

        if re.search(each["regex"], string=call_string,
                     flags=re.MULTILINE) is not None:
            globals()[
                each["var_name"]] = re.search(
                each["regex"],
                string=call_string,
                flags=re.MULTILINE).group(
                each["group"])
        else:
            globals()[each["var_name"]] = None

    if VERBOSE >= 2:
        print("Extracted ajax params:--------\n")
        for each in var_names:
            print("%(var)s :     %(value)s" %
                  {"var": each.ljust(10, ' '), "value": globals()[each]})


def construct_date_ranges(path, params, session):
    '''From one big range construct a bunch of contiguous ones joined
    end to end containing aproximately 4000 photos each'''

    # copying request parameters to prepare to simultaneous execusion
    params_lcl = deepcopy(params)

    TERMS = TAGS[-2:] if TEST and VERBOSE > 3 else TAGS

    for term in TERMS:

        params_lcl['text'] = term
        offset = 3
        #first_range = True

        # initializing time index
        params_lcl['min_upload_date'] = BEFORE_DATE

        ranges = ''
        time_to_break = False

        while True:
            if VERBOSE >= 3:
                print("".ljust(20, '+'))

            params_lcl['max_upload_date'] = params_lcl['min_upload_date']
            params_lcl['min_upload_date'] -= datetime.timedelta(days=offset)

            next_batch_size = s.get(api_url, params=params_lcl).json()[
                                    'photos']['total']
            if VERBOSE >= 3:
                print(f"New date range: {params_lcl['min_upload_date']}"
                      f" to {params_lcl['max_upload_date']}______ "
                      f"total photos: {next_batch_size}")

            params_lcl['min_upload_date'], next_batch_size, offset = find_best_date_range(
                session=s, params=params_lcl,
                start=params_lcl['min_upload_date'],
                stop=params_lcl['max_upload_date'],
                total_photos=next_batch_size,
                offset=offset)

            if (
                params_lcl['min_upload_date'].timestamp(
                ) <= AFTER_DATE.timestamp()
                # and int(next_batch_size) <= 4000
            ):
                time_to_break = True
                params_lcl['min_upload_date'] = AFTER_DATE
                next_batch_size = s.get(
                    api_url, params=params_lcl).json()['photos']['total']

            if VERBOSE >= 2:
                print(f"Next suitable range!: {params_lcl['min_upload_date']} "
                      f"to {params_lcl['max_upload_date']}______ total "
                      f"photos : {next_batch_size}".ljust(120, ' '))

            ranges += f"\n{term.replace(' ','_')},{params_lcl['min_upload_date']}" \
                f",{params_lcl['max_upload_date']},{next_batch_size},Nay"

            if time_to_break:
                break
        temp_file.write(ranges)

        if VERBOSE >= 3:
            print("".ljust(120, "-"))
            print(
                f"Finished for term: {term}   in date range : from {AFTER_DATE} to {BEFORE_DATE}")
            print("".ljust(120, "-"))


def looping_over_date_ranges(path, params, session):
    ''' loops over given date range'''

    # copying request parameters to prepare to simultaneous execusion
    params_lcl = deepcopy(params)

    last_response_time = 0

    TERMS = TAGS[-2:] if TEST and VERBOSE > 3 else TAGS

    for term in TERMS:

        csv_file.seek(0)

        for date_range in ranges_reader:
            if (
                date_range['Search_Term'] == term.replace(' ', '_')
                and date_range['Downloaded'] == 'Nay'
            ):
                if VERBOSE >= 3:
                    print(date_range)

                date_format = '%Y-%m-%d %H:%M:%S.%f'
                start = date_range['Uploaded_After']
                stop = date_range['Uploaded_Before']
                start = start + ".0" if '.' not in start else start
                stop = stop + ".0" if '.' not in stop else stop
                params_lcl['min_upload_date'] = dt.strptime(
                    start, date_format)
                params_lcl['max_upload_date'] = dt.strptime(
                    stop, date_format)
                # try:
                    # date_format = '%Y-%m-%d %H:%M:%S.%f'
                    # start = date_range['Uploaded_After']
                    # stop = date_range['Uploaded_Before']
                    # params_lcl['min_upload_date'] = dt.strptime(
                        # start, date_format)
                    # params_lcl['max_upload_date'] = dt.strptime(
                        # stop, date_format)
                # except ValueError:
                    # date_format = '%Y-%m-%d %H:%M:%S'
                    # start = date_range['Uploaded_After']
                    # stop = date_range['Uploaded_Before']
                    # params_lcl['min_upload_date'] = dt.strptime(
                        # start, date_format)
                    # params_lcl['max_upload_date'] = dt.strptime(
                        # stop, date_format)

                next_batch_size = date_range['Batch_Size']
                if VERBOSE >= 3:
                    print("".ljust(20, '+'))
                if VERBOSE >= 2:
                    print(
                        f"Next range to download: {params_lcl['min_upload_date']}\
                to {params_lcl['max_upload_date']}______ total photos : {next_batch_size}".ljust(
                            120, ' '))

                if VERBOSE >= 1:
                    print(f'starting JSON dump...')
                if TEST and VERBOSE > 3:
                    print(" fake writing to file ")
                else:
                    write_each_page_as_json_file(
                        path=DATA_PATH, call_params=params_lcl,
                        session=s, term=term)

                date_range['Downloaded'] = 'Aye'
                ranges_writer.writerow(date_range)
                time.sleep(0.2)
                time.sleep(
                    last_response_time *
                    random.uniform(
                        COURTESY_SLEEP[0],
                        COURTESY_SLEEP[1]) *
                    2)

        if VERBOSE >= 3:
            print("".ljust(120, "-"))
            print(
                f"Finished for term: {term} in date range : from {AFTER_DATE} to {BEFORE_DATE}")
            print("".ljust(120, "-"))

        #time.sleep(random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]) * 3)


def find_best_date_range(session, params, start, stop, total_photos, offset):

    call_params = deepcopy(params)
    # creating local variables to avoid multiprocessing issues down the line
    call_params['per_page'] = 1
    call_params['extras'] = ''

    if VERBOSE >= 3:
        print(f"Finding a better range (in 20 attempts or less) ...")
    repeats = 0
    nudge = 0

    # This loop check whether the returned total photos are just a hair under
    # which is the maximum allowed by the api. If not it cleverly adjusts the
    # offset. The adjustment value used is difference ratio to the wanted
    # number of photos (the assumption for this heuristic is that for a small
    # range the uploaded photos density will not change much. And thus the
    # difference % when applied to the range will give us a ballpark of the
    # wanted range)

    while (
        int(total_photos) != 4000
        and (
            int(total_photos) > 4000
            or int(total_photos) < (4000 * 0.99)
        )
        and not (
            int(total_photos) < 4000
            and repeats > 20
        )
    ):

        nudge = random.uniform(0, repeats / 100)

        if int(total_photos) > 4000:
            if VERBOSE >= 3:
                print(
                    f"({str(repeats)}): too many    ({total_photos.ljust(5, '+')})\
            {start} --- {stop}", end='\r')
            # here the % will be small because we overshot the value wanted
            try:
                offset *= 4000 / int(total_photos)
            except ZeroDivisionError:
                offset *= 4000

        if int(total_photos) < 4000:
            if VERBOSE >= 3:
                print(
                    f"({str(repeats)}): not enough  ({total_photos.ljust(5, '-')})\
            {start} --- {stop}", end='\r')
            # here the % will be big because we underestimated the range
            try:
                offset *= (1 - nudge) * 4000 / int(total_photos)
            except ZeroDivisionError:
                offset *= 4000

        #if TEST and VERBOSE > 3: print("\n", offset, nudge)
        start = stop - datetime.timedelta(offset)

        # shifting the date range
        call_params['min_upload_date'] = start
        total_photos = session.get(api_url, params=call_params).json()[
                                   'photos']['total']

        repeats += 1

        #if VERBOSE >3 and TEST: time.sleep(0.3)
    return start, total_photos, offset


def write_each_page_as_json_file(path, call_params, session, term):

    for each in added_params:
        call_params[each] = added_params[each]

    # making_sure the request pages are correct
    call_params['per_page'] = PHOTOS_PER_PAGE
    pages = s.get(api_url, params=call_params).json()[
                  'photos']['max_allowed_pages']

    start = str(call_params['min_upload_date'].timestamp())
    stop = str(call_params['max_upload_date'].timestamp())

    for page in range(1, 1 + pages):
        print(f"Requesting page {page}...".ljust(120, ' '),  end='\r')

        call_params['page'] = page

        try:
            before = dt.now().timestamp()
            response = session.get(api_url, params=call_params)
            after = dt.now().timestamp()
            data = response.json()
            data['api_call_params'] = call_params
            data['api_call_params']['min_upload_date'] = start
            data['api_call_params']['max_upload_date'] = stop
        except Exception as e:
            print(f"Couldn't request JSON data:____ {e}")

        last_response_time = after - before

        # Trying to write JSON data to file
        file_to_be_written = f"{path}/{term.replace(' ','_')}_{start}-{stop}_{page}.json"
        #if VERBOSE >=3: print(f" file path to be written: {file_to_be_written}\n\n")
        try:
            with open(file_to_be_written, 'w') as outfile:
                json.dump(data, outfile)

            time_it_took = str(round(last_response_time, 2))
            print(f"{file_to_be_written} written succesfully! took {time_it_took} s")
            time.sleep(0.2)
        except Exception as e:
            print(f"problem dumping json data: {str(e)}")
        if VERBOSE >= 2:
            print(
                f'sleeping for {last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1])} seconds... (for courtesy :P )'.ljust(
                    120,
                    ' '),
                end='\r')
        time.sleep(
            last_response_time *
            random.uniform(
                COURTESY_SLEEP[0],
                COURTESY_SLEEP[1]))
    print("")


if __name__ == '__main__':

    xhr_api_call, cookies = get_api_call_string()

    parse_api_call(xhr_api_call)

    extras = extras.replace('%2C', ',')

    added_params = {
        # "extras" : '',
        "extras": extras + ',' + ADD_EXTRAS,
        "per_page": 1,
        "api_key": api_key,
        "reqId": reqId,
    }

    for each in added_params:
        params[each] = added_params[each]

    SPOOF_WEBDRIVER = False

    if SPOOF_WEBDRIVER:
        ua = UserAgent()

    with requests.sessions.Session() as s:
        for cookie in cookies:
            s.cookies.set(cookie['name'], cookie['value'])
        if SPOOF_WEBDRIVER:
            s.headers['User-Agent'] = str(ua.chrome)

    date_format = '%Y_%m_%d'

    ranges_file = f'./date_ranges-{AFTER_DATE.strftime(date_format)}-{BEFORE_DATE.strftime(date_format)}.csv'

    temp_file = NamedTemporaryFile(mode='w', delete=False)

    csv_fields = [
        'Search_Term',
        'Uploaded_After',
        'Uploaded_Before',
        'Batch_Size',
        'Downloaded']

    file_exists = True if os.path.isfile(ranges_file) else False

    #mode ='a' if file_exists else 'w'

    with open(ranges_file, 'r') as csv_file, temp_file:
        ranges_reader = csv.DictReader(csv_file, fieldnames=csv_fields)
        ranges_writer = csv.DictWriter(temp_file, fieldnames=csv_fields)
        temp_file.write(
            'Search_Term,Uploaded_After,Uploaded_Before,Batch_Size,Downloaded\n')

        if GET_DATES_ONLY:
            construct_date_ranges(path=DATA_PATH, params=params, session=s)
        else:
            if file_exists:
                looping_over_date_ranges(
                    path=DATA_PATH, params=params, session=s)
            else:
                print(
                    f"The dates ranges file for the period {AFTER_DATE} to {BEFORE_DATE} could not be found!")

        # Writing changes to the original file
    shutil.move(temp_file.name, ranges_file)
