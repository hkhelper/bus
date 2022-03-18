import requests, os

VERSION = ''
BASE_URL = ''

def setBase(baseurl, version):
    global VERSION, BASE_URL
    VERSION = version
    BASE_URL = baseurl

def calPrice(passengerStr):
    passengerInfo = passengerStr.split(',')
    passengers = []
    for k in range(int(len(passengerInfo) / 2)):
        passengers.append({'id': passengerInfo[k * 2], 'name': passengerInfo[1 + k * 2]})
    price = 0.0
    for people in passengers:
        if people['id'][0] == '#':
            #kid
            price += 33
        else:
            #adult
            price += 65
    return price

def redirectPayment(session):
    url = 'https://mpgsproxy.hzmbus.com/api/page/version/53/pay'
    data={
        'merchant': '010826386',
        'interaction.operation': 'PURCHASE',
        'interaction.merchant.name': 'HZMB',
        'interaction.locale': 'en',
        'interaction.cancelUrl': 'urn:hostedCheckout:defaultCancelUrl',
        'interaction.timeoutUrl': 'urn:hostedCheckout:defaultTimeoutUrl',
        'session.id': session,
    }
    headers={
        'Accept': 'application/json',
    }
    r = sendReq(url, data=data, method='postdata', headers=headers, skipErrorStatusCode=True)
    ret = r.json()
    if ('redirectURL' not in ret) or ('session' not in ret) or ('id' not in ret['session']) or (ret['session']['id'] != session):
        raise ValueError('Payment returned json error: ' + str(ret))
    return 'https://mpgsproxy.hzmbus.com/checkout/lightboxEntry/'+session


def login(username, password, debug=False):
    url = BASE_URL.split(';')[0] + '/login'
    data = {"webUserid": username, "passWord": password, "code": "", "appId": "HZMBWEB_HK", "joinType": "WEB",
            "version": VERSION, "equipment": "PC"}
    r = sendReq(url, data=data, method='post')
    cookie = r.cookies
    ret = r.json()
    if ('code' not in ret) or ('message' not in ret):
        raise ValueError('Login returned json error: ' + str(ret))
    if ret['code'] == 'FAIL':
        raise ValueError('Login failed: '+ret['message'])
    if 'jwt' not in ret:
        raise ValueError('Login token not found in return: ' + str(ret))
    token = ret['jwt']
    if debug:
        print('cookie:', cookie)
        print('Authorization:', token)
    return {'cookie': cookie, 'token': token}

# def book(date, time, peoples, token, line):
#     tickets = []
#     price = 0
#     for people in peoples:
#         if people['id'][0] == '#':
#             #child
#             tickets.append({
#                 "ticketType": "01",
#                 "idCard": people['id'][1:] if (line in ['HKGZHO', 'HKGMAC']) else '',
#                 "idType": 1,
#                 "userName": people['name'] if (line in ['HKGZHO', 'HKGMAC']) else '',
#                 "telNum": ""
#             })
#             price += 3300
#         else:
#             #adult
#             tickets.append({
#                 "ticketType": "00",
#                 "idCard": people['id'] if (line in ['HKGZHO', 'HKGMAC']) else '',
#                 "idType": 1,
#                 "userName": people['name'] if (line in ['HKGZHO', 'HKGMAC']) else '',
#                 "telNum": ""
#             })
#             price += 6500
#     url = BASE_URL + '/ticket/buy.ticket'
#     data = {
#         "ticketData": date,
#         "lineCode": line,
#         "startStationCode": line[:3],
#         "endStationCode": line[3:],
#         "boardingPointCode": line[:3]+"01",
#         "breakoutPointCode": line[3:]+"01",
#         "currency": "2",  ###HKD
#         "ticketCategory": "1",
#         "tickets": tickets,
#         "amount": price,
#         "feeType": 9,  ###
#         "totalVoucherpay": 0, "voucherNum": 0, "voucherStr": "", "totalBalpay": 0,
#         "totalNeedpay": price,
#         "bookBeginTime": time,
#         "bookEndTime": time,
#         "appId": "HZMBWEB_HK",
#         "joinType": "WEB",
#         "version": VERSION,
#         "equipment": "PC"
#     }
#     headers = {'Authorization': token}
#     r = sendReq(url, data=data, method='post', cookie=None, headers=headers)
#     ret = r.json()
#     if ('responseData' in ret) and ('orderNumber' in ret['responseData']):
#         return ret['responseData']['orderNumber']
#     elif ('code' in ret) and ('message' in ret) and (ret['code'] == 'FAIL') and (ret['message'] == '您還有未支付的訂單,請先支付后再進行購票,謝謝!'):
#         print('User has unpaid orders.')
#         return ''
#     else:
#         print('Book failed. ', ret)
#         raise AssertionError('Failed:'+str(ret))

def sendReq(url, data=None, method='get', timeout=None, retry=None, resp_json=True, cookie=None, headers=None, debug=False, skipErrorStatusCode=False):
    if timeout is None:
        timeout = int(os.getenv('TIMEOUT', '10'))
    if retry is None:
        retry = int(os.getenv('RETRY', '10'))

    while retry > 0:
        try:
            if debug:
                print('Req. ...', url)
            if method == 'get':
                r = requests.get(url, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookie)
            elif method == 'postdata':
                r = requests.post(url, data=data, timeout=timeout, allow_redirects=False, headers=headers,
                                  cookies=cookie)
            else:
                r = requests.post(url, json=data, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookie)
            if not skipErrorStatusCode:
                r.raise_for_status()
            if r.status_code == 302:
                print('Got 302 status code.')
                retry -= 1
                continue
            if resp_json:
                ret = r.json()
            else:
                ret = r.text
        except requests.exceptions.HTTPError as err:
            print(err)
            print('Got error status code:', r.status_code, r.text)
            retry -= 1
            continue
        except requests.exceptions.RequestException as err:
            print(err)
            print('Request failed.')
            retry -= 1
            continue
        except ValueError:
            print('Got none json return:', r.text)
            retry -= 1
            continue
        if debug:
            print('Got return: ', ret)
        return r
    print('Retry too many times. Failed.')
    raise Exception('Retry too many times. Failed.')

def getOrders(orderStatus, cookie):
    for base, d in cookie.items():
        base_url = base
        token = d['token']
        break
    url = base_url + '/wx/query.wx.order.record'
    data = {
        'appId': "HZMBWEB_HK",
        'equipment': "PC",
        'joinType': "WEB",
        'nextOrderNo': "",
        'orderStatus': orderStatus,
        'rowCount': 20,
        'ticketCategory': "1,2",
        'version': VERSION
    }
    headers = {'Authorization': token}
    r = sendReq(url, data=data, method='post', cookie=None, headers=headers)
    ret = r.json()
    if len(ret['responseData']) > 0:
        return ret['responseData']
    else:
        return []
