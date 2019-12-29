import argparse, textwrap, time, json, re, requests, random, datetime, copy
from datetime import datetime as dt
from copy import deepcopy

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from fake_useragent import UserAgent





parser = argparse.ArgumentParser(description=textwrap.dedent('''\
        scrape JSONs containing photos from flickr
         '''))

parser.add_argument("-a", "--after_date", help="Start date (in unix timestamp format). Defaults to yesterday", type=float, default=dt.now().timestamp() - (30 * 24 * 3600))
parser.add_argument("-b", "--before_date", help="End date (in unix timestamp format). Defaults to now", type=float, default=dt.now().timestamp())
parser.add_argument("-s", "--courtesy_sleep", help="Range (in string format) from which a random value will be chosen to sleep randomly. example: '1.3, 2.7'", type=str, default="1.3, 2.7")
parser.add_argument("-n", "--photos_per_page", help="Photos per file. Default is 500 which is the maximum", type=int, default=500)
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="count", default=0)
parser.add_argument("-p", "--dump_path", help="Path where to dump json files", type=str, default='./')
parser.add_argument("-t", "--test", help="test mode", action='store_true')
parser.add_argument("-w", "--webdriver", help="Turn off headless mode for on the chrome webdriver", action='store_false')
parser.add_argument("-x", "--add_extras", help="extra json fields to request. Defaults to 'url_o,original_format,date_taken,date_upload,geo'", type=str, default="url_o,original_format,date_taken,date_upload,geo")

args = parser.parse_args()

global driver, params, AFTER_DATE ,BEFORE_DATE ,COURTESY_SLEEP ,PHOTOS_PER_PAGE ,VERBOSE ,TEST ,DUMP_PATH ,ADD_EXTRAS, HEADLESS


args.__dict__['HEADLESS'] = args.webdriver

# ansigning global variables from cmdline args for easy typing
for each in args.__dict__: globals()[each.upper()] = args.__dict__[each]

# making sure the dates are in datetime format
for each in ["AFTER_DATE", "BEFORE_DATE"]:
    if type(each) != type(dt.now()):
        try:
            globals()[each] = dt.fromtimestamp(globals()[each])
        except Exception as e:
            print(f"please make sure the dates entered are in unix timestamps format: {e}")

# printing parameters for easy debugging
if VERBOSE >=3:
    print("".ljust(120, "_") + "\nscript parameters")
    for each in args.__dict__:
        print(f"{each.upper()}: {args.__dict__[each]}")
    print("".ljust(120, "_"))

COURTESY_SLEEP = [float(COURTESY_SLEEP.split(',')[0]) , float(COURTESY_SLEEP.split(',')[1])]
if TEST and VERBOSE > 3: COURTESY_SLEEP = [0, 0.000000001]



def parse_api_call(call_string):
    ''' parsing data from DOM element '''
    #creating variables for each parsed data
    for each in variables:

        if  re.search(each["regex"], string=call_string, flags=re.MULTILINE) != None:
            globals()[each["var_name"]] = re.search(each["regex"], string=call_string, flags=re.MULTILINE).group(each["group"])
        else:
            globals()[each["var_name"]] = None

    if VERBOSE >= 2:
        print("Extracted ajax params:--------\n")
        for each in var_names:
            print("%(var)s :     %(value)s" % {"var": each.ljust(10, ' '), "value" : globals()[each]})

def looping_over_date_range(path, params, session, start, stop, offset):
    ''' loops over given date range'''

    # copying request parameters to prepare to simultaneous execusion
    params_lcl = deepcopy(params)

    last_response_time = 0

    # initializing time index
    params_lcl['min_upload_date'] = stop

    while params_lcl['min_upload_date'].timestamp() >= start.timestamp():
        if VERBOSE >= 3: print("".ljust(20, '+'))

        params_lcl['max_upload_date'] = params_lcl['min_upload_date']
        params_lcl['min_upload_date'] -= datetime.timedelta(days=offset)

        total_photos = s.get(api_url, params=params_lcl).json()['photos']['total']
        if VERBOSE >=3: print(f"New date range: {params_lcl['min_upload_date']} to {params_lcl['max_upload_date']}______ total photos: {total_photos}")

        returned_values = find_best_date_range(session=s, params=params_lcl, start=params_lcl['min_upload_date'], stop=params_lcl['max_upload_date'], total_photos=total_photos, offset=offset)

        params_lcl['min_upload_date'] = returned_values['new_start']
        next_batch_size = returned_values['total_photos']
        offset = returned_values['offset']

        if VERBOSE >= 2: print(f"Next suitable range: {params_lcl['min_upload_date']} to {params_lcl['max_upload_date']}______ total photos : {next_batch_size}".ljust(120, ' '))

        if VERBOSE >= 1: print(f'starting JSON dump...')

        if TEST and VERBOSE > 3:
            print(" fake writing to file ")
        else:
            write_each_page_as_json_file(path=DATA_PATH, call_params=params_lcl, session=s)

        time.sleep(0.2)
        time.sleep(last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]) * 2)


# def update_date_range(index, params, offset=3):
    # ''' shifts the date range by offset days (default is 3 days) '''

    # new_index = index - datetime.timedelta(days=offset)
    # params['min_upload_date'] = new_index
    # params['max_upload_date'] = index

    # return index

def find_best_date_range(session, params, start, stop, total_photos, offset):

    call_params = deepcopy(params)
    # creating local variables to avoid multiprocessing issues down the line
    call_params['per_page'] = 1
    call_params['extras'] = ''

    if VERBOSE >=3: print(f"Finding a better range (in 20 attempts or less) ...")
    repeats = 0

    # This loop check whether the returned total photos are just a hair under
    # which is the maximum allowed by the api. If not it cleverly adjusts the
    # offset. The adjustment value used is difference ratio to the wanted
    # number of photos (the assumption for this heuristic is that for a small
    # range the uploaded photos density will not change much. And thus the
    # difference % when applied to the range will give us a ballpark of the wanted range)

    while (int(total_photos) > 4000 or int(total_photos) < 3990) and not (int(total_photos) < 4000 and repeats > 20):

        if int(total_photos) > 4000:
            if VERBOSE >=3: print(f"({str(repeats)}): too many    ({total_photos.ljust(5, '+')})", end = '\r')
            # here the % will be small because we overshot the value wanted
            offset = offset * 4000/ int(total_photos)

        if int(total_photos) <= 4000:

            if VERBOSE >=3: print(f"({str(repeats)}): not enough  ({total_photos.ljust(5, '-')})", end = '\r')
            # here the % will be big because we underestimated the range (plus a small nudge)
            offset = offset * 4000 / int(total_photos)

        start = stop - datetime.timedelta(offset)

        # shifting the date range
        call_params['min_upload_date'] = start
        total_photos = session.get(api_url, params=call_params).json()['photos']['total']

        repeats += 1
        # if VERBOSE >3 and TEST: time.sleep(1)
    return {'new_start': start, 'total_photos': total_photos, 'offset': offset}

def write_each_page_as_json_file(path, call_params, session):

    for each in added_params: call_params[each] = added_params[each]

    # making_sure the request pages are correct
    call_params['per_page'] = PHOTOS_PER_PAGE
    pages = s.get(api_url, params=call_params).json()['photos']['pages']

    for page in range(1, 1 + pages):
        print(f"Requesting page {page}...".ljust(120, ' '),  end='\r')

        call_params['page'] = page

        before = dt.now().timestamp()

        try:
            response = session.get(api_url, params=call_params)
        except Exception as e:
            print(f"Couldn't request JSON data:____ {e}")
        after = dt.now().timestamp()

        last_response_time = after - before

        # Trying to write JSON data to file
        file_to_be_written = f"{path}{term}_{str(call_params['min_upload_date'].timestamp())}-{str(call_params['max_upload_date'].timestamp())}_{page}.json"
        #if VERBOSE >=3: print(f" file path to be written: {file_to_be_written}\n\n")
        try:
            with open(file_to_be_written, 'w') as outfile:
                json.dump(response.json(), outfile)

            time_it_took = str(round(last_response_time, 2))
            print(f"{file_to_be_written} written succesfully! took {time_it_took} s")
            time.sleep(0.2)
        except Exception as e:
            print(f"problem dumping json data: {str(e)}")
        if VERBOSE >=2: print(f'sleeping for {last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1])} seconds... (for courtesy :P )'.ljust(120, ' '), end = '\r')
        time.sleep(last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]))
    print("")






if __name__ == '__main__':


    DATA_PATH = ('./test/' if TEST else DUMP_PATH)

    params = {
        "sort" : "relevance",
        "parse_tags" : "1",
        "content_type" : "7",
        "lang": "en-US",
        "has_geo" :"1",
        "media" : "photos",
        "view_all" : "1",
        "text" : "clouds",
        "viewerNSID": "",
        "method" : "flickr.photos.search",
        "csrf" : "",
        "format" : "json",
        "hermes" : "1",
        "hermesClient" : "1",
        "nojsoncallback" : "1",
        "geo_context": '2', # 0: all , 1: indoors, 2 : outdoors
        "privacy_filter" : 1
    }

    privacy_filters = '''
    "public photos" : '1',
    "private photos visible to friends" : '2',
    "private photos visible to family" : '3',
    "private photos visible to friends & family": '4',
    "completely private photos" : '5'
    '''

    FLICKR = 'https://flickr.com/search/'
    TAGS = ['clouds', 'cloud', 'sky', 'storm', 'weather', 'rain cloud']

    var_names = ["api_key", "reqId", "api_url", "extras"]
    re_expressions = [r"(api_key)=([\dabcdef]*)(&)", r"(reqId)=([\dabcdef]*)(&)", r"(https:\/\/(\w+\.?)+(\/\w+)+)(\?)", r"extras=((\w+(%2)?)+?)?&"]
    groups = [2,2,1,1]

    variables = [dict(zip(["var_name", "regex", 'group'], each)) for each in [each for each in zip(var_names, re_expressions, groups)]]

    options = Options()

    if HEADLESS: options.add_argument('--headless')

    caps = DesiredCapabilities.CHROME
    caps['loggingPref'] = {'performance': 'ALL'}

    driver = webdriver.Chrome(options = options, desired_capabilities=caps)

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

        if VERBOSE >=1: print('title : "{}"'.format(driver.title))

    except Exception as e:
        print('Error! Cannot open search page: ' + str(e))

    wait = False
    while wait != True:
        if VERBOSE >= 1: print("Getting AJAX data...")
        # trying scroll to trigger and api call
        try:
            if VERBOSE >= 3: print('attempting Scroll!')
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            if VERBOSE >= 3: print('Scrolled...')

            # waiting for the api call to be included in the DOM
            wait = WebDriverWait(driver, 15).until(EC.text_to_be_present_in_element((By.ID, "interceptedResponse"), "api_key"))

        except Exception as e:
            print("intercept failed!:" + str(e))

        intercepts = driver.find_elements_by_id('interceptedResponse')

    if wait == True and VERBOSE >= 1: print('ajax call intercepted!\n')
    xhr_api_call = intercepts[0].text

    cookies = driver.get_cookies()
    driver.close()

    parse_api_call(xhr_api_call)

    extras = extras.replace('%2C', ',')

    added_params = {
        "extras" : extras + ','+ ADD_EXTRAS,
        "per_page" : 1,
        "api_key" : api_key,
        "reqId" : reqId,
    }

    for each in added_params: params[each] = added_params[each]

    spoof_webdriver = False

    if spoof_webdriver: ua = UserAgent()

    with requests.sessions.Session() as s:
        for cookie in cookies:
            s.cookies.set(cookie['name'], cookie['value'])
        if spoof_webdriver: s.headers['User-Agent'] = str(ua.chrome)

    offset = 3


    TEST_RANGE = TAGS[:-2] if TEST and VERBOSE > 3 else TAGS

    for term in TEST_RANGE:

        params['text'] = term

        first_range = True

        start = AFTER_DATE
        stop = BEFORE_DATE

        params['min_upload_date'] = start
        params['max_upload_date'] = stop

        looping_over_date_range(path=DATA_PATH, params=params, session=s, start=params['min_upload_date'], stop=params['max_upload_date'], offset = offset)
        if VERBOSE >=3:
            print("".ljust(120, "-"))
            print(f"Finished for term: {term}   in date range : from {start} to {stop}")
            print("".ljust(120, "-"))

        time.sleep(random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]) * 3)
