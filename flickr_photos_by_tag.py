import argparse, textwrap, time, json, re, requests, random, datetime
from datetime import datetime as dt

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

#from fake_useragent import UserAgent
parser = argparse.ArgumentParser(description=textwrap.dedent('''\
        scrape JSONs containing photos from flickr
         '''))

parser.add_argument("-a", "--after_date", help="Start date (in unix timestamp format). Defaults to yesterday", type=float, default=dt.now().timestamp() - (24 * 3600))
parser.add_argument("-b", "--before_date", help="End date (in unix timestamp format). Defaults to now", type=float, default=dt.now().timestamp())
parser.add_argument("-s", "--courtesy_sleep", help="Range (in string format) from which a random value will be chosen to sleep randomly. example: '1.3, 2.7'", type=str, default="1.3, 2.7")
parser.add_argument("-n", "--photos_per_page", help="Photos per file. Default is 500 which is the maximum", type=int, default=500)
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="count", default=0)
parser.add_argument("-t", "--test", help="test mode", action='store_true')
parser.add_argument("-p", "--dump_path", help="Path where to dump json files", type=str, default='./json_data/')
parser.add_argument("-x", "--add_extras", help="extra json fields to request. Defaults to 'url_o,original_format,date_taken,date_upload,geo'", type=str, default="url_o,original_format,date_taken,date_upload,geo")

args = parser.parse_args()

# verbose = args.verbose
# test = args.test
# AFTER_DATE = args.after_date
# BEFORE_DATE = args.before_date
# PHOTOS_PER_PAGE = args.photos_per_page
# additional_extras = args.add_extras
# DATA_PATH = args.dump_path

# print(args)


for each in args.__dict__: globals()[each.upper()] = args.__dict__[each]


# making sure the dates are in datetime format
for each in ["AFTER_DATE", "BEFORE_DATE"]:
    if type(each) != type(dt.now()):
        globals()[each] = dt.fromtimestamp(globals()[each])

# printing parameters for easy debugging
if VERBOSE >=3:
    print("".ljust(80, "_") + "\nscript parameters")
    for each in args.__dict__:
        print(f"{each.upper()}: {args.__dict__[each]}")
    print("".ljust(80, "_"))

# VERBOSE = 3

# TEST = 1

# AFTER_DATE = 1576471428

# BEFORE_DATE = dt.now()

# PHOTOS_PER_PAGE = 500

# ADD_EXTRAS = "url_o,original_format,date_taken,date_upload,geo"

COURTESY_SLEEP = [float(COURTESY_SLEEP.split(',')[0]) , float(COURTESY_SLEEP.split(',')[1])]

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
TAGS = ['clouds', 'cloud', 'sky', 'storm', 'weather']

options = Options()

headless = True
if headless: options.add_argument('--headless')

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

    print('title : "{}"'.format(driver.title))

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
xhr_call = intercepts[0].text

cookies = driver.get_cookies()
driver.close()


# pasrsing data from DOM element
var_names = ["api_key", "reqId", "api_url", "extras"]
re_expressions = [r"(api_key)=([\dabcdef]*)(&)", r"(reqId)=([\dabcdef]*)(&)", r"(https:\/\/(\w+\.?)+(\/\w+)+)(\?)", r"extras=((\w+(%2)?)+?)?&"]

groups = [2,2,1,1]

variables = [dict(zip(["var_name", "regex", 'group'], each)) for each in [each for each in zip(var_names, re_expressions, groups)]]

#creating variables for each parsed data
for each in variables:

    if  re.search(each["regex"], string=xhr_call, flags=re.MULTILINE) != None:
        globals()[each["var_name"]] = re.search(each["regex"], string=xhr_call, flags=re.MULTILINE).group(each["group"])
    else:
        globals()[each["var_name"]] = None

extras = extras.replace('%2C', ',')

if VERBOSE >= 2:
    print("Extracted ajax params:--------\n")
    for each in var_names:
        print("%(var)s :     %(value)s" % {"var": each.ljust(10, ' '), "value" : globals()[each]})

added_params = {
    "extras" : extras + ADD_EXTRAS,
    "per_page" : PHOTOS_PER_PAGE,
    "api_key" : api_key,
    "reqId" : reqId
}

for each in added_params: params[each] = added_params[each]

spoof_webdriver = False

if spoof_webdriver: ua = UserAgent()

with requests.sessions.Session() as s:
    for cookie in cookies:
        s.cookies.set(cookie['name'], cookie['value'])
    if spoof_webdriver: s.headers['User-Agent'] = str(ua.chrome)
response = s.get(api_url, params=params)



now = BEFORE_DATE
days_offset = 3

def change_date_range(index, offset=3):
    params['min_upload_date'] = index - datetime.timedelta(days=offset)
    params['max_upload_date'] = index

change_date_range(now)



total_photos = s.get(api_url, params=params).json()['photos']['total']

def find_best_date_range():

    global days_offset, total_photos

    params['per_page'] = 1

    if VERBOSE >=3: print(f"Finding a better range (in 20 attempts or less) ...")
    repeats = 0
    while (int(total_photos) != 4000) and not (int(total_photos) < 4000 and repeats > 20):
        if int(total_photos) > 4000:
            days_offset = days_offset * 4000/ int(total_photos)
            if VERBOSE >=3: print(f"({str(repeats)}): too many photos ({total_photos.ljust(5, '+')}): new range from {params['min_upload_date']} to {params['max_upload_date']}", end = '\r')
        if int(total_photos) <= 3990:
            days_offset = days_offset * 3990 / int(total_photos)
            if VERBOSE >=3: print(f"({str(repeats)}): not enough photos ({total_photos.ljust(5, '-')}): new range from {params['min_upload_date']} to {params['max_upload_date']}", end = '\r')
        params['min_upload_date'] = params['max_upload_date'] - datetime.timedelta(days_offset)
        total_photos = s.get(api_url, params=params).json()['photos']['total']
        repeats += 1
    params['per_page'] = PHOTOS_PER_PAGE

def write_each_page_as_json_file(path, params, session, max_pages):
    params['per_page'] = PHOTOS_PER_PAGE

    for page in range(1, 1 + max_pages):
        print(f"Requesting page {page}...".ljust(120, ' '),  end='\r')

        params['page'] = page


        before = dt.now().timestamp()
        try:
            response = session.get(api_url, params=params)
        except Exception as e:
            print(f"Couldn't request JSON data:____ {e}")
        after = dt.now().timestamp()

        last_response_time = after - before


        # Trying to write JSON data to file
        file_to_be_written = f"{path}{term}_{str(params['min_upload_date'].timestamp())}-{str(params['max_upload_date'].timestamp())}_{page}.json"
        #if VERBOSE >=3: print(f" file path to be written: {file_to_be_written}\n\n")
        try:
            with open(file_to_be_written, 'w') as outfile:
                json.dump(response.json(), outfile)
                #print('\r', end = '')
            print(f"{file_to_be_written} written succesfully!")
            time.sleep(0.2)
        except Exception as e:
            print(f"problem dumping json data: {str(e)}")
        if VERBOSE >=2: print(f'sleeping for {last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1])} seconds... (for courtesy :P )'.ljust(120, ' '), end = '\r')
        time.sleep(last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]))


last_response_time = 0
for term in TAGS:

    params['text'] = term

    first_range = True
    response = s.get(api_url, params=params)

    while params['min_upload_date'].timestamp() >= 1483228800 :
        if not first_range:
            change_date_range(params['max_upload_date'] - datetime.timedelta(days=days_offset), days_offset)
            total_photos = response.json()['photos']['total']
        else:
            first_range = False
            total_photos = s.get(api_url, params=params).json()['photos']['total']
        print("".ljust(120, '_'))
        if VERBOSE >=3: print(f"New date range: {params['min_upload_date']} to {params['max_upload_date']}")

        total_photos = s.get(api_url, params=params).json()['photos']['total']
        if VERBOSE >=3: print(f"Photos in current range: {total_photos}")

        find_best_date_range()

        response = s.get(api_url, params=params)
        total_photos = response.json()['photos']['total']
        if VERBOSE >= 2: print(f"Next suitable range: {params['min_upload_date']} to {params['max_upload_date']}______ total photos : {total_photos}".ljust(120, ' '))

        print(f'starting JSON dump...')
        max_pages = response.json()['photos']['max_allowed_pages']

        write_each_page_as_json_file(path=DATA_PATH, params=params, session=s, max_pages=max_pages)

        time.sleep(last_response_time * random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]) * 2)

    time.sleep(random.uniform(COURTESY_SLEEP[0], COURTESY_SLEEP[1]) * 3)
