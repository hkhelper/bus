import requests, os, time, httpx, asyncio, json, base64
import pandas as pd
from urllib.parse import quote
from datetime import datetime, timedelta

django_url = os.getenv('DJANGO_API', None)
django_token = os.getenv('DJANGO_KEY', None)

def getOrderList(statusStr):
    url = django_url + 'hkzh/api/user/list/'+statusStr+'/'
    headers = {'Authorization': 'Token ' + django_token}
    try:
        r = sendReq(url, headers=headers, skipErrorStatusCode=True)
        books = r.json()
    except Exception as e:
        print('Get booked list failed: ',e)
        return []
    return books

def loginOrder():
    orderList = getOrderList('processing,login')
    login_expire_minutes = int(getConfigValue('CHECK_LOGIN_EXPIRE_MINUTES'))
    now = datetime.now()
    count = success = 0
    for book in orderList:
        if (book['status'] == 'login') and (book['cookie'] is not None) and (book['cookie'] != ''):
            cookie = json.loads(book['cookie'])
            createdAt = cookie['createdAt']
            createdAt = datetime.strptime(createdAt, '%Y-%m-%d %H:%M:%S')
            if (createdAt + timedelta(minutes=login_expire_minutes)) > now:
                continue
        # login.
        count += 1
        login_user, login_pwd = book['loginInfo'].split(',')
        try:
            loginRet = login(login_user, login_pwd, book['id'])
        except Exception as e:
            print(e)
            continue
        if not loginRet:
            print('Login failed.')
            continue
        success += 1
    print('Success logged in %i/%i orders'%(success, count))
    return True

# 取账户里的指定的状态订单
def getAccountOrders(cookie, paid=False):
    for base, d in cookie.items():
        base_url = base
        token = d['token']
        break
    if paid:
        status = 1
    else:
        status = 0
    url = base_url + '/wx/query.wx.order.record'
    data = {
        'appId': "HZMBWEB_HK",
        'equipment': "PC",
        'joinType': "WEB",
        'nextOrderNo': "",
        'orderStatus': status,
        'rowCount': 20,
        'ticketCategory': "1,2",
        'version': version
    }
    headers = {'Authorization': token}
    r = sendReq(url, data=data, method='post', headers=headers)
    ret = r.json()
    if len(ret['responseData']) > 0:
        return ret['responseData']
    else:
        return []

# 比较账户中的订单是否和预订单一致
def compareExistOrders(orders, book):
    cookie = json.loads(book['cookie'])
    passengerInfo = book['passengerInfo'].split(',')
    passengers = []
    for k in range(int(len(passengerInfo) / 2)):
        passengers.append({'id': passengerInfo[k * 2], 'name': passengerInfo[1 + k * 2]})

    for order in orders:
        orderNo = order['orderNo']
        isThisOrder = True
        # check if linecode is consistent
        accountLineCode = order['qZddm']+order['zZddm']
        if book['line_code'] != accountLineCode:
            isThisOrder = False
            continue
        # compare date
        if book['sort_date'].find(order['bcrq']) < 0:
            isThisOrder = False
            continue
        # if HKGZHO compare the passengers.
        if book['line_code'] in ['HKGZHO', 'HKGMAC']:
            accountOrderInfo = getOrderInfo(orderNumber=orderNo, cookie=cookie)
            for passenger in passengers:
                if passenger['id'][0] == '#':
                    passengerId = passenger['id'][1:]
                else:
                    passengerId = passenger['id']
                if accountOrderInfo['usersInfo'].find(passengerId) < 0:
                    isThisOrder = False
                    break
        if isThisOrder:
            return order
    return False


# 检查已预定的订单状态
def checkBookedStatus():
    booklist = getOrderList('booked,payment,checking')
    print('%i booked order need to check'%len(booklist))
    for book in booklist:
        if book['bookNumber'] is None:
            orderNumber = ''
        else:
            orderNumber = book['bookNumber'].split(',')[0]
        cookie = json.loads(book['cookie'])
        if orderNumber == '':
            # 账户里有未付款订单，未取到订单号的情况
            accountOrders = getAccountOrders(cookie, False)
            if len(accountOrders) == 0:
                accountOrders = getAccountOrders(cookie, True)
                if len(accountOrders) == 0:
                    print('Have not found any order in the account.')
                    if (book['cookie'] is not None) and (len(book['cookie']) > 1):
                        bookStatus = 'login'
                    else:
                        bookStatus = 'processing'
                    updateBookInfo(book['id'], {
                        'status': bookStatus
                    })
                else:
                    orderId = compareExistOrders(accountOrders, book)
                    if orderId:
                        updateBookInfo(book['id'], {
                            'bookNumber': orderId['orderNo'],
                            'status': 'paid',
                            'bookDate': orderId['fcsjBcrq'],
                            'paidAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                    else:
                        print('Have not found related orders in the account.')
                        if (book['cookie'] is not None) and (len(book['cookie']) > 1):
                            bookStatus = 'login'
                        else:
                            bookStatus = 'processing'
                        updateBookInfo(book['id'], {
                            'status': bookStatus
                        })
            else:
                orderId = compareExistOrders(accountOrders, book)
                if orderId:
                    updateBookInfo(book['id'], {
                        'bookNumber': orderId['orderNo'],
                        'bookDate': orderId['fcsjBcrq'],
                        'status': 'booked'
                    })
                else:
                    accountOrders = getAccountOrders(cookie, True)
                    if len(accountOrders) == 0:
                        print('Have not found any order in the account.')
                        if (book['cookie'] is not None) and (len(book['cookie']) > 1):
                            bookStatus = 'login'
                        else:
                            bookStatus = 'processing'
                        updateBookInfo(book['id'], {
                            'status': bookStatus
                        })
                    else:
                        orderId = compareExistOrders(accountOrders, book)
                        if orderId:
                            updateBookInfo(book['id'], {
                                'bookNumber': orderId['orderNo'],
                                'status': 'paid',
                                'bookDate': orderId['fcsjBcrq'],
                                'paidAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                        else:
                            print('Have not found related orders in the account.')
                            if (book['cookie'] is not None) and (len(book['cookie']) > 1):
                                bookStatus = 'login'
                            else:
                                bookStatus = 'processing'
                            updateBookInfo(book['id'], {
                                'status': bookStatus
                            })
        else:
            if book['status'] == 'checking':
                orderReqno = book['bookNumber'].split(',')[1]
            else:
                orderReqno = None
            try:
                status = getOrderStatus(orderNumber=orderNumber, orderReqno=orderReqno, cookie=cookie)
            except PermissionError as e:
                print(e)
                print('Relogin...')
                login_user, login_pwd = book['loginInfo'].split(',')
                try:
                    loginRet = login(login_user, login_pwd, book['id'], False)
                except Exception as e:
                    print(e)
                if not loginRet:
                    print('Login failed.')
                continue
            except Exception as e:
                print(e)
                continue
            print('User #%i Order %s status is %s'%(book['id'], orderNumber, status['orderStatus']))

            # pending payment
            if (status['orderStatus'] == '0') and (book['status'] not in ['booked', 'payment', 'checking']):
                if len(book['bookNumber'].split(',')) == 3:
                    bookStatus = 'payment'
                else:
                    bookStatus = 'booked'
                updateBookInfo(book['id'], {
                    'status': bookStatus
                })
            # pending payment - recreate payment link
            elif (status['orderStatus'] == '0') and (book['status'] == 'booked'):
                if len(book['bookNumber'].split(',')) < 3:
                    paylink = getPaymentLink(book['bookNumber'].split(',')[0], cookie)
                    if paylink is not False:
                        updateBookInfo(book['id'], {
                            'bookNumber': book['bookNumber'].split(',')[0] + ',' + paylink['orderReqno'] + ',' + paylink['session'],
                            'status': 'payment',
                            'paymentExpireAt': paylink['endTime']
                        })
            # canceled, refund or expired
            elif (status['orderStatus'] in ['C', 'E', 'U']) and (book['status'] not in ['processing', 'login']):
                if (book['cookie'] is not None) and (len(book['cookie']) > 1):
                    bookStatus = 'login'
                else:
                    bookStatus = 'processing'
                updateBookInfo(book['id'], {
                    'status': bookStatus
                })
            # paid
            elif (status['orderStatus'] == '1') and (book['status'] not in ['paid', 'done']):
                updateBookInfo(book['id'], {
                    'status': 'paid',
                    'bookNumber': status['orderNo'],
                    'bookDate': status['bcrq']+' '+status['bookBeginTime'],
                    'paidAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

def getConfigValue(key):
    url = django_url + 'hkzh/api/config/' + key + '/'
    headers = {'Authorization': 'Token ' + django_token}
    try:
        r = sendReq(url, headers=headers, skipErrorStatusCode=True)
        ret = r.json()
    except Exception as e:
        raise ValueError('Get config value %s error: '%key + str(e))
    if 'value' in ret:
        return ret['value']
    else:
        print('config %s not found.'%key)
        return None

def getBookInfo(line_code, date, count):
    url = django_url + 'hkzh/api/user/get_by_date/'+line_code+'/'+date+'/'+str(count)+'/'
    headers = {'Authorization': 'Token '+django_token}
    try:
        r = sendReq(url, headers=headers, skipErrorStatusCode=True)
        books = r.json()
    except Exception as e:
        print('Select user failed: ', e)
        return False
    if len(books) == 0:
        return False
    try:
        return books[0]
    except Exception as e:
        print('Select user return error: ', str(books))
        print(e)
        return False

def updateConfig(key, value):
    url = django_url + 'hkzh/api/config/update/' + key + '/'
    headers = {'Authorization': 'Token ' + django_token}
    data = {'value': value}
    try:
        r = sendReq(url, data=data, headers=headers, method='patch', skipErrorStatusCode=True)
        ret = r.json()
    except Exception as e:
        print('Update config %s failed: '%key, e)
        return False
    if ('key' in ret) and (ret['key'] == key):
        return True
    else:
        print('Update config %s failed: '%key, str(ret))
        return False

def updateBookInfo(id, data):
    url = django_url + 'hkzh/api/user/update/'+str(id)+'/'
    headers = {'Authorization': 'Token ' + django_token}
    try:
        r = sendReq(url, data=data, headers=headers, method='patch', skipErrorStatusCode=True)
        ret = r.json()
    except Exception as e:
        print('Update user %i failed: '%id, e)
        return False
    if ('id' in ret) and (ret['id'] == id):
        return True
    else:
        print('Update user %i failed: '%id, str(ret))
        return False

def login(user, pwd, id=None, updateLoginStatus=True):
    success = False
    retAry = {}
    for burl in base_url.split(';'):
        url = burl + '/login'
        data = {"webUserid": user, "passWord": pwd, "code": "", "appId": "HZMBWEB_HK", "joinType": "WEB",
                "version": version, "equipment": "PC"}
        r = sendReq(url, data=data, method='post')
        cookie = r.cookies
        ret = r.json()
        if ('code' not in ret) or ('message' not in ret):
            print('Login returned json error: ' + str(ret))
            continue
        if ret['code'] == 'FAIL':
            print('Login failed: '+ret['message'])
            if ret['message'] in ['賬戶或密碼錯誤', '用戶不存在']:
                if id:
                    updateBookInfo(id, {
                        'status': 'pending',
                        'comment': 'Login failed: ' + ret['message']
                    })
                raise AssertionError(ret['message'])
            continue
        if 'jwt' not in ret:
            print('Login token not found in return: ' + str(ret))
            continue
        token = ret['jwt']
        success = True
        retAry[burl] = {'cookie': cookie.get_dict()['PHPSESSID'], 'token': token}
        if debug:
            print('cookie:', cookie)
            print('Authorization:', token)
    if success is False:
        return False
    retAry['createdAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if id:
        data = {
            'cookie': json.dumps(retAry)
        }
        if updateLoginStatus:
            data['status'] = 'login'
        updateBookInfo(id, data)
    return retAry

def getOrderInfo(orderNumber, cookie):
    for base, d in cookie.items():
        base_url = base
        token = d['token']
        break
    url = base_url + '/wx/query.wx.order.info'
    data = {
        "orderNo": orderNumber,
        "appId": "HZMBWEB_HK",
        "joinType": "WEB",
        "version": version,
        "equipment": "PC"
    }
    headers = {'Authorization': token}
    r = sendReq(url, data=data, method='post', headers=headers)
    ret = r.json()
    if ('code' in ret) and (ret['code'] == '408'):
        raise PermissionError(ret['message'])
    if len(ret['responseData']) > 0:
        return ret['responseData']['0']
    else:
        raise AssertionError('Order %s not exist.' % orderNumber)

def getOrderStatus(orderNumber, orderReqno, cookie):
    if orderReqno is not None:
        for base, d in cookie.items():
            base_url = base
            token = d['token']
            break
        # update payment result
        url = base_url + '/pay/update.order.payresult'
        data = {
            'appId': "HZMBWEB_HK",
            'equipment': "PC",
            'joinType': "WEB",
            'orderReqno': orderReqno,
            'payType': "MasterCard",
            'version': version
        }
        headers = {'Authorization': token}
        r = sendReq(url, data=data, method='post', headers=headers)
        ret = r.json()
        print('Update payment result returns: ', ret)
        # skip get order details if update payment returns order info
        if ('code' in ret) and (ret['code'] == 'SUCCESS') and ('responseData' in ret) and (
                'status' in ret['responseData']) \
                and ('exchangeCode' in ret['responseData']) and (ret['responseData']['status'] == '1') and (
                len(ret['responseData']['exchangeCode']) > 10):
            return {
                'orderStatus': '1',
                'orderNo': ret['responseData']['orderNo'],
                'bcrq': ret['responseData']['ticketData'],
                'bookBeginTime': ret['responseData']['bookBeginTime']
            }
    return getOrderInfo(orderNumber, cookie)
    # return order['orderStatus']

def book(date, beginTime, endTime, peoples, cookie, line, captcha):
    for base, d in cookie.items():
        base_url = base
        token = d['token']
        mycookie = d['cookie']
        break
    tickets = []
    price = 0
    for people in peoples:
        if people['id'][0] == '#':
            #child
            tickets.append({
                "ticketType": "01",
                "idCard": people['id'][1:] if (line in ['HKGZHO', 'HKGMAC']) else '',
                "idType": 1,
                "userName": people['name'] if (line in ['HKGZHO', 'HKGMAC']) else '',
                "telNum": ""
            })
            price += 3300
        else:
            #adult
            tickets.append({
                "ticketType": "00",
                "idCard": people['id'] if (line in ['HKGZHO', 'HKGMAC']) else '',
                "idType": 1,
                "userName": people['name'] if (line in ['HKGZHO', 'HKGMAC']) else '',
                "telNum": ""
            })
            price += 6500
    url = base_url + '/ticket/buy.ticket'
    data = {
        "ticketData": date,
        "lineCode": line,
        "startStationCode": line[:3],
        "endStationCode": line[3:],
        "boardingPointCode": line[:3]+"01",
        "breakoutPointCode": line[3:]+"01",
        "currency": "2",  ###HKD
        "captcha": captcha,
        "ticketCategory": "1",
        "tickets": tickets,
        "amount": price,
        "feeType": 9,  ###
        "totalVoucherpay": 0, "voucherNum": 0, "voucherStr": "", "totalBalpay": 0,
        "totalNeedpay": price,
        "bookBeginTime": beginTime,
        "bookEndTime": endTime,
        "appId": "HZMBWEB_HK",
        "joinType": "WEB",
        "version": version,
        "equipment": "PC"
    }
    headers = {'Authorization': token}
    r = sendReq(url, data=data, method='post', cookie={'PHPSESSID': mycookie}, headers=headers, timeout=book_timeout)
    ret = r.json()
    if ('responseData' in ret) and ('orderNumber' in ret['responseData']):
        return ret['responseData']['orderNumber']
    elif ('code' in ret) and ('message' in ret) and (ret['code'] == 'FAIL') and (ret['message'] == '您還有未支付的訂單,請先支付后再進行購票,謝謝!'):
        print('User has unpaid orders.')
        return ''
    else:
        print('Book failed. ', ret)
        if ('code' in ret) and (ret['code'] == '400'):
            # wrong captcha Retry
            raise ValueError('Captcha error.')
        if ('message' in ret) and (ret['message'] == '預約人數超出當前可預約的總人數'):
            # Continue
            raise AssertionError(ret['message'])
        # Retry
        raise TimeoutError('Failed')

def getPaymentLink(orderId, cookie):
    for base, d in cookie.items():
        base_url = base
        token = d['token']
        break
    url = base_url + '/wx/query.wx.order.payreq'
    data = {
        'appId': "HZMBWEB_HK",
        'currency': "2",
        'equipment': "PC",
        'feeType': 9,
        'joinType': "WEB",
        'language': "lang-zh",
        'orderNo': orderId,
        'payType': "MasterCard",
        'version': version,
    }
    headers = {'Authorization': token}
    try:
        r = sendReq(url, data=data, method='post', headers=headers)
        ret = r.json()
    except Exception as e:
        print('Get payment link failed: ',e)
        return False
    if ret['code'] != 'SUCCESS':
        print('Get payment link failed: ' + str(ret))
        return False
    if ('responseData' not in ret) or ('json' not in ret) or ('orderReqno' not in ret['responseData']) or ('tradeEtime' not in ret['responseData']):
        print('Get payment link failed: ' + str(ret))
        return False
    try:
        retJson = json.loads(ret['json'])
    except Exception as e:
        print('Get payment link json decode failed: ' + ret['json'])
        return False
    if ('session' not in retJson) or ('id' not in retJson['session']):
        print('Get payment link json decode failed: ' + ret['json'])
        return False
    sessionId = retJson['session']['id']
    orderReqno = ret['responseData']['orderReqno']
    endTime = ret['responseData']['tradeEtime']
    return {'session': sessionId, 'orderReqno': orderReqno, 'endTime': endTime}

def sendReq(url, data=None, method='get', timeout=None, retry=None, resp_json=True, cookie=None, headers=None, skipErrorStatusCode=False):
    if timeout is None:
        timeout = req_timeout
    if retry is None:
        retry = req_retry

    while retry > 0:
        try:
            if debug:
                print('Req. ...', url)
            if method == 'get':
                r = requests.get(url, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookie)
            elif method == 'patch':
                r = requests.patch(url, json=data, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookie)
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
            print('Got error status code:', r.status_code)
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

async def checkAvailableSlot(date, line_code, method, i=0):
    if debug:
        print(' Looking for available slot on ', date)
    async with httpx.AsyncClient() as client:
        url = base_url.split(';')[i] + '/manage/query.book.info.data'
        data = {"bookDate": date, "lineCode": line_code, "appId": "HZMBWEB_HK", "joinType": "WEB",
                "version": version, "equipment": "PC"}
        headers = {'Authorization':  slot_token.split(';')[i]}
        try:
            resp = await client.post(url=url, json=data, timeout=req_timeout, headers=headers)
        except:
            print(time.strftime("%H:%M:%S") + f'  #Req. failed or times out({req_timeout}s). ')
            return slotRespProc(data=False)
        try:
            assert resp.status_code == 200
        except AssertionError:
            print(time.strftime("%H:%M:%S") + f'  #Got error status code {resp.status_code}. ')
            return slotRespProc(data=False)
        try:
            data = resp.json()
        except ValueError:
            print(time.strftime("%H:%M:%S") + f'  #Got json decode error: {resp.text}')
            return slotRespProc(data=False)
        return slotRespProc(data=data, date=date, method=method)

def slotRespProc(data, date=None, method=None):
    if debug:
        print('Got return '+str(data))
    if not data:
        return
    slotlist = data
    if 'responseData' not in slotlist:
        print('Can not found responseData in slotlist', slotlist)
        return
    df = pd.DataFrame(slotlist['responseData'])
    if 'bookDate' not in df.columns:
        print(date, 'ResponseData in slotlist is empty.', df)
        return
    if len(df) > 0:
        df['availablePeople'] = df['maxPeople'] - df['totalPeople']
        df.sort_values('availablePeople', ascending=False, inplace=True)
        fullslotlist = df
        slotlist = fullslotlist[(fullslotlist['saleStatus'] == 1) & (fullslotlist['availablePeople'] > 0)]
    else:
        fullslotlist = slotlist = pd.DataFrame()
    if 'maxPeople' in fullslotlist:
        totals_people = fullslotlist['maxPeople'].sum()
    else:
        totals_people = 0
    if 'availablePeople' in slotlist:
        available_people = slotlist['availablePeople'].sum()
    else:
        available_people = 0
    print('Found %i/%i available on' % (available_people, totals_people), date)
    if (method == 'check') and (available_people > 0):
        runBook(slotlist)
    elif (method == 'checkopen') and (totals_people > 0):
        # notify and reset the RUN MODE to 2
        updateConfig('CHECK_SLOT_RUN', '2')
        slotstring = date + '名额已开放'
        if wxpusher:
            url = 'http://wxpusher.zjiecode.com/api/send/message'
            wx_token, wx_uid = wxpusher.split(',')
            data = {
                "appToken": wx_token,
                "content": slotstring,
                # "summary": slotstring,
                "contentType": 1,
                "uids": [
                    wx_uid
                ]
            }
            sendReq(url, data=data, method='post', resp_json=False)
        if telegram_id:
            url = 'http://api.callmebot.com/start.php?user=%s&text=%s&lang=cmn-CN-Standard-A' % (
            telegram_id, quote(slotstring))
            try:
                # don't wait resp.
                sendReq(url, timeout=3, retry=1, resp_json=False)
            except Exception as e:
                print('Telegram notified.')
        try:
            updateSlotList(fullslotlist)
        except Exception as e:
            print('Save slot list to DB error: ', e)
            return False

    elif (method == 'slot') and (len(fullslotlist) > 0):
        try:
            updateSlotList(fullslotlist)
        except Exception as e:
            print('Save slot list to DB error: ', e)
            return False
    return True

def updateSlotList(slotlist):
    url = django_url + 'hkzh/api/slot/'
    headers = {'Authorization': 'Token ' + django_token}
    slotlist = slotlist.rename(columns={'lineCode': 'linecode', 'bookDate': 'date', 'beginTime': 'time'})
    data = slotlist.to_dict('records')
    try:
        r = sendReq(url, headers=headers, data=data, method='post', skipErrorStatusCode=True)
        ret = r.json()
    except Exception as e:
        raise ValueError('Update slot list error: ' + str(e))
    if 'SUCCESS' in ret:
        return True
    raise ValueError('Update slot list returns error: ' + str(ret))

def calHoursFromNow(dtStr):
    td = datetime.strptime(dtStr, '%Y-%m-%d %H:%M:%S') - datetime.now()
    return (td.days * 24 * 3600 + td.seconds) / 3600

def captchaFromCjy(imageBase64):
    url = 'http://upload.chaojiying.net/Upload/Processing.php'
    # 1004 1~4位英文数字
    data = {"user": cjy_user, "pass": cjy_pass, "softid": cjy_soft, "codetype": cjy_type, "file_base64": imageBase64}
    r = sendReq(url, data, method='post')
    ret = r.json()
    if ret['err_no'] == 0:
        return ret['pic_str']
    else:
        raise AssertionError('CJY returns error: ' + ret['err_str'])

def getCaptcha(cookie):
    for base, d in cookie.items():
        base_url = base
        mycookie = d['cookie']
        break
    url = base_url + '/captcha'
    r = sendReq(url, cookie={'PHPSESSID': mycookie}, resp_json=False)
    return base64.b64encode(r.content).decode('utf-8')

def runBook(slotlist):
    for index, slot in slotlist.iterrows():
        # skip if < today_delta_hours
        if calHoursFromNow(slot['bookDate']+' '+slot['beginTime']) < today_delta_hours:
            print('Time is to close: %s. Skip.'%(slot['bookDate']+' '+slot['beginTime']))
            continue
        bookData = getBookInfo(slot['lineCode'], slot['bookDate'], slot['availablePeople'])
        if not bookData:
            print('No user need.')
            continue
        if bool(getConfigValue('CHECK_BOOK_RUN')):
            print('Working on User #%i' % bookData['id'])
            cookie = json.loads(bookData['cookie'])
            login_user, login_pwd = bookData['loginInfo'].split(',')
            passengerInfo = bookData['passengerInfo'].split(',')
            passengers = []
            for k in range(int(len(passengerInfo) / 2)):
                passengers.append({'id': passengerInfo[k * 2], 'name': passengerInfo[1 + k * 2]})

            print('Try to book ', slot['bookDate'], slot['beginTime'])
            order = None
            for bi in range(book_retry):
                try:
                    captchaBase64 = getCaptcha(cookie)
                    captcha = captchaFromCjy(captchaBase64)
                    order = book(slot['bookDate'], slot['beginTime'], slot['endTime'], passengers, cookie,
                                 slot['lineCode'], captcha)
                except ValueError as e:
                    print(str(e))
                    continue
                except Exception as e:
                    print('Book failed:', e)
                    break
                break
            if order is None:
                continue
            print('SUCCESS!!! Order #', order)
            update_obj = {
                'bookNumber': order,
                'status': 'booked'
            }
            if order != '':
                update_obj['bookDate'] = slot['bookDate'] + ' ' + slot['beginTime']
            updateBookInfo(bookData['id'], update_obj)

            if order != '':
                paylink = getPaymentLink(order, cookie)
                if paylink is not False:
                    updateBookInfo(bookData['id'], {
                        'bookNumber': order + ',' + paylink['orderReqno'] + ',' + paylink[
                            'session'],
                        'status': 'payment',
                        'paymentExpireAt': paylink['endTime']
                    })
            if trig_url:
                slotstring = '#' + str(bookData['id']) + ',' + login_user + ',' + login_pwd + ';' + slot['bookDate'] + ' ' + slot['beginTime']
                data = {'value1': slotstring, 'value2': datetime.now().strftime('%m-%d %H:%M')}
                sendReq(trig_url, data=data, method='post', resp_json=False)
            if wxpusher:
                slotstring = '#' + str(bookData['id']) + ',' + login_user + ',' + login_pwd + ';' + slot['bookDate'] + ' ' + slot['beginTime']\
                             + ';价格:' + str(bookData['price']) + ';付款:' + str(bookData['ticket_price'])
                url = 'http://wxpusher.zjiecode.com/api/send/message'
                wx_token, wx_uid = wxpusher.split(',')
                data = {
                    "appToken": wx_token,
                    "content": slotstring,
                    # "summary": slotstring,
                    "contentType": 1,
                    "uids": [
                        wx_uid
                    ]
                }
                sendReq(url, data=data, method='post', resp_json=False)

            if telegram_id:
                string = '抢票成功，请及时支付。UserID: ' + str(bookData['id'])
                url = 'http://api.callmebot.com/start.php?user=%s&text=%s&lang=cmn-CN-Standard-A' % (telegram_id, quote(string))
                try:
                    # don't wait resp.
                    sendReq(url, timeout=3, retry=1, resp_json=False)
                except Exception as e:
                    print('Telegram notified.')

    return

async def checkRun():
    while True:
        now = datetime.now()
        print(now.strftime('%m-%d %H:%M:%S'))
        if bool(getConfigValue('CHECK_LOGIN_RUN')):
            # 登入账号
            loginOrder()

        if bool(getConfigValue('CHECK_STATUS_RUN')):
            # 更新待付款订单状态
            try:
                checkBookedStatus()
            except Exception as e:
                print('Check booked order failed: ', e)

        baseurl_count = len(base_url.split(';'))
        date_delta = datetime.strptime(check_end_date, '%Y-%m-%d') - now
        if int(getConfigValue('CHECK_SLOT_RUN')) == 1:
            for line_code in check_line_code.split(','):
                for n in range(0, date_delta.days+2):
                    for i in range(0, concurrency_level):
                        date = (now + timedelta(days=n)).strftime('%Y-%m-%d')
                        asyncio.create_task(checkAvailableSlot(date, line_code, 'check', i % baseurl_count))
                        await asyncio.sleep(checkdate_step)
                for i in range(0, concurrency_level):
                    date = getConfigValue('SCHEDULE_CHECK_DATE').split(',')[0]
                    asyncio.create_task(checkAvailableSlot(date, line_code, 'checkopen', i % baseurl_count))
                    await asyncio.sleep(checkdate_step)
        elif int(getConfigValue('CHECK_SLOT_RUN')) == 2:
            for line_code in check_line_code.split(','):
                for date in getConfigValue('SCHEDULE_CHECK_DATE').split(','):
                    for i in range(0, concurrency_level):
                        asyncio.create_task(checkAvailableSlot(date, line_code, 'slot', i % baseurl_count))
                        await asyncio.sleep(checkdate_step)
        elif int(getConfigValue('CHECK_SLOT_RUN')) == 3:
            for line_code in check_line_code.split(','):
                for date in getConfigValue('SCHEDULE_CHECK_DATE').split(','):
                    for i in range(0, concurrency_level):
                        asyncio.create_task(checkAvailableSlot(date, line_code, 'checkopen', i % baseurl_count))
                        await asyncio.sleep(checkdate_step)


        await asyncio.sleep(step)


if __name__ == '__main__':
    if (django_url is None) or (django_token is None):
        raise ValueError('django_url & django_token must be set.')

    debug = False
    req_timeout = req_retry = 10
    base_url = getConfigValue('BASE_URL')
    slot_token = getConfigValue('slot_token')
    trig_url = getConfigValue('TRIG_URL')
    wxpusher = getConfigValue('WX_PUSHER')
    telegram_id = getConfigValue('TG_ID')
    version = getConfigValue('API_VERSION')
    today_delta_hours = float(getConfigValue('TODAY_DELTA_HOURS'))
    check_line_code = getConfigValue('CHECK_LINE_CODE')
    step = float(getConfigValue('CHECK_STEP'))
    concurrency_level = int(getConfigValue('CHECK_CLEVEL'))
    checkdate_step = float(getConfigValue('CHECK_DATE_STEP'))
    debug = bool(getConfigValue('CHECK_DEBUG'))
    req_timeout = float(getConfigValue('REQ_TIMEOUT'))
    req_retry = int(getConfigValue('REQ_RETRY'))
    book_retry = int(getConfigValue('BOOK_RETRY'))
    book_timeout = int(getConfigValue('BOOK_TIMEOUT'))
    check_end_date = getConfigValue('CHECK_END_DATE')
    cjy_auth = getConfigValue('CJY_AUTH')
    cjy_user, cjy_pass, cjy_soft, cjy_type = cjy_auth.split(',')

    asyncio.run(checkRun())
