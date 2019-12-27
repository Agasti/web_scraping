import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import json, itertools, re, requests, random, datetime
from datetime import datetime as dt
from fake_useragent import UserAgent

options = Options()

options.add_argument('--headless')

FLICKR = 'https://flickr.com/search/'
TAGS = ['clouds', 'cloud', 'sky', 'storm', 'weather']

caps = DesiredCapabilities.CHROME
caps['loggingPref'] = {'performance': 'ALL'}

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

driver = webdriver.Chrome(options = options, desired_capabilities=caps)

try:
    url = FLICKR + "?has_geo=1&media=photos&view_all=1&text=" + TAGS[0]

    driver.get(url)
    driver.execute_script(xhrCallIntercept_js)

    print('title : "{}"'.format(driver.title))

    time.sleep(5)

except Exception as e:
    print('Error: ' + str(e))

wait = "Getting AJAX data..."
while wait != True:
    print(wait)
    # trying scroll to trigger and api call
    try:
        print('attempting Scroll!')
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        print('Scrolled...')

        # waiting for the api call to be included in the DOM
        wait = WebDriverWait(driver, 15).until(EC.text_to_be_present_in_element((By.ID, "interceptedResponse"), "api_key"))

    except Exception as e:
        print("intercept failed!:" + str(e))

    intercepts = driver.find_elements_by_id('interceptedResponse')

if wait == True:
    print('ajax call intercepted!\n')

xhr_call = intercepts[0].text

var_names = ["api_key", "reqId", "api_url", "extras"]
re_expressions = [r"(api_key)=([\dabcdef]*)(&)", r"(reqId)=([\dabcdef]*)(&)", r"(https:\/\/(\w+\.?)+(\/\w+)+)(\?)", r"extras=((\w+(%2)?)+?)?&"]

groups = [2,2,1,1]

variables = [dict(zip(["var_name", "regex", 'group'], each)) for each in [each for each in zip(var_names, re_expressions, groups)]]

for each in variables:

    if  re.search(each["regex"], string=xhr_call, flags=re.MULTILINE) != None:
        globals()[each["var_name"]] = re.search(each["regex"], string=xhr_call, flags=re.MULTILINE).group(each["group"])
    else:
        globals()[each["var_name"]] = None

extras = extras.replace('%2C', ',')

print("Extracted ajax params:--------\n")
for each in var_names:
    print("%(var)s :     %(value)s" % {"var": each.ljust(10, ' '), "value" : globals()[each]})


photos_per_page = "500"
additional_extras = "url_o,original_format,date_taken,date_upload,geo"

privacy_filter ={
    "public photos" : '1',
    "private photos visible to friends" : '2',
    "private photos visible to family" : '3',
    "private photos visible to friends & family": '4',
    "completely private photos" : '5'
}



global params
params = {
    "sort" : "relevance",
    "tags" : 'clouds',
    "parse_tags" : "1",
    "content_type" : "7",
    "extras" : extras + additional_extras,
    "per_page" : photos_per_page,
    "page" : 1,
    "lang": "en-US",
    "has_geo" :"1",
    "media" : "photos",
    "view_all" : "1",
    "text" : "clouds",
    "viewerNSID": "",
    "method" : "flickr.photos.search",
    "csrf" : "",
    "api_key" : api_key,
    "format" : "json",
    "hermes" : "1",
    "hermesClient" : "1",
    "reqId" : reqId,
    "nojsoncallback" : "1",
    "privacy_filter" : privacy_filter['public photos'],
    "geo_context": '2'
}

cookies = driver.get_cookies()

#ua = UserAgent()
driver.close()

with requests.sessions.Session() as s:
    for cookie in cookies:
        s.cookies.set(cookie['name'], cookie['value'])
    #s.headers['User-Agent'] = str(ua.chrome)
    response = s.get(api_url, params=params)

json_data_path = './json_data/'
photo_json = 'photos.json'
scraped_ids = 'scraped_photos.txt'
now = dt.now()
days_offset = 3

def change_date_range(index, offset=3):
    params['min_upload_date'] = index - datetime.timedelta(days=offset)
    params['max_upload_date'] = index

change_date_range(now)

params['tags'] = ''

total_photos = s.get(api_url, params=params).json()['photos']['total']

def find_best_date_range():

    global days_offset, total_photos

    print(f"Finding a better range (in 20 attempts or less) ...")
    repeats = 0
    #int(total_photos) <= 3990 or int(total_photos) > 4000
    while (int(total_photos) != 4000) and not (int(total_photos) < 4000 and repeats > 20):
        if int(total_photos) > 4000:
            days_offset = days_offset * 4000/ int(total_photos)
            print(f"({str(repeats)}): too many photos   ({total_photos.ljust(10, '+')}): new range from {params['min_upload_date']} to {params['max_upload_date']}", end = '\r')
        if int(total_photos) <= 3990:
            days_offset = days_offset * 3990 / int(total_photos)
            print(f"({str(repeats)}): not enough photos ({total_photos.ljust(10, '-')}): new range from {params['min_upload_date']} to {params['max_upload_date']}", end = '\r')
        params['min_upload_date'] = params['max_upload_date'] - datetime.timedelta(days_offset)

        params['per_page'] = 1
        total_photos = s.get(api_url, params=params).json()['photos']['total']
        repeats += 1

for term in TAGS:

    params['text'] = term

    first_range = True
    while params['min_upload_date'].timestamp() >= 1483228800 :
        if not first_range:
            change_date_range(params['max_upload_date'] - datetime.timedelta(days=days_offset), days_offset)
        else:
            first_range = False
        total_photos = s.get(api_url, params=params).json()['photos']['total']
        print("__________________________")
        print(f"New date range: {params['min_upload_date']} to {params['max_upload_date']}______ total photos : {total_photos}")

        total_photos = s.get(api_url, params=params).json()['photos']['total']
        print(f"Photos in current range: {total_photos}")

        find_best_date_range()
        total_photos = s.get(api_url, params=params).json()['photos']['total']
        print(f"Better range: {params['min_upload_date']} to {params['max_upload_date']}______ total photos : {total_photos}".ljust(200, ' '))

        print(f'starting JSON dump...')

        for page in range(1, 9):
            print(f"getting page {page}...", end = ' ')

            params['page'] = page
            params['per_page'] = photos_per_page

            before = dt.now().timestamp()

            response = s.get(api_url, params=params)

            after = dt.now().timestamp()

            response_time = after - before
            print(f'sleeping {response_time * random.randint(2, 6)} seconds... (for courtesy :))', end = '\r')
            time.sleep(response_time * random.randint(0, 3))

            path = f"{json_data_path}{term}_{str(params['min_upload_date'].timestamp())}-{str(params['max_upload_date'].timestamp())}_{page}.json"
            try:
                with open(path, 'w') as outfile:
                    json.dump(response.json(), outfile)
                print(f"{path} written succesfully!")
            except Exception as e:
                print(f"problem dumping json data: {str(e)}")
        time.sleep(random.randrange(1000, 2500)/ 1000)

    time.sleep(random.randrange(4000, 7000)/ 1000)
