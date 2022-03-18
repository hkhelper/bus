import requests, os, time, socket, json, base64
import pandas as pd
from datetime import datetime, timedelta

django_url = os.getenv('DJANGO_API', None)
django_token = os.getenv('DJANGO_KEY', None)

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

def selectUser():
    node = socket.gethostname()
    url = django_url + 'hkzh/api/user/get_schedule/'+node+'/'
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
        bookData = books[0]
    except Exception as e:
        print('Select user return error: ', str(books))
        print(e)
        return False
    login_user, login_pwd = bookData['loginInfo'].split(',')
    bookData['login'] = {
        'username': login_user,
        'password': login_pwd,
    }

    passengerInfo = bookData['passengerInfo'].split(',')
    passengers = []
    for k in range(int(len(passengerInfo) / 2)):
        passengers.append({'id': passengerInfo[k * 2], 'name': passengerInfo[1 + k * 2]})
    bookData['passengers'] = passengers

    bookData['datelist'] = bookData['sort_date'].split(',')
    return bookData

def getBookInfo(id):
    url = django_url + 'hkzh/api/user/get/' + str(id) + '/'
    headers = {'Authorization': 'Token ' + django_token}
    try:
        r = sendReq(url, headers=headers, method='get', skipErrorStatusCode=True)
        bookData = r.json()
    except Exception as e:
        print('Get user %i failed: '%id, e)
        return False
    login_user, login_pwd = bookData['loginInfo'].split(',')
    bookData['login'] = {
        'username': login_user,
        'password': login_pwd,
    }

    passengerInfo = bookData['passengerInfo'].split(',')
    passengers = []
    for k in range(int(len(passengerInfo) / 2)):
        passengers.append({'id': passengerInfo[k * 2], 'name': passengerInfo[1 + k * 2]})
    bookData['passengers'] = passengers

    bookData['datelist'] = bookData['sort_date'].split(',')
    return bookData

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

def login(user, pwd):
    success = False
    retAry = {}
    for burl in base_url.split(';'):
        url = burl + '/login'
        data = {"webUserid": user, "passWord": pwd, "code": "", "appId": "HZMBWEB_HK", "joinType": "WEB",
                "version": version, "equipment": "PC"}
        try:
            r = sendReq(url, data=data, method='post')
        except Exception as e:
            continue
        cookie = r.cookies
        ret = r.json()
        if ('code' not in ret) or ('message' not in ret):
            print('Login returned json error: ' + str(ret))
            continue
        if ret['code'] == 'FAIL':
            if ret['message'] in ['賬戶或密碼錯誤', '用戶不存在']:
                raise AssertionError(ret['message'])
            print('Login failed: '+ret['message'])
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
    return retAry

def getOrderDetails(orderNumber, cookie):
    url = '/wx/query.wx.order.info'
    data = {
        "orderNo": orderNumber,
        "appId": "HZMBWEB_HK",
        "joinType": "WEB",
        "version": version,
        "equipment": "PC"
    }
    r = sendReq(url, data=data, method='post', cookie=cookie)
    ret = r.json()
    if ('code' in ret) and (ret['code'] == '408'):
        raise PermissionError(ret['message'])
    if len(ret['responseData']) > 0:
        return ret['responseData']['0']
    else:
        raise AssertionError('Order %s not exist.' % orderNumber)

def getOrderStatus(orderNumber, orderReqno, cookie):
    if orderReqno is not None:
        # update payment result
        url = '/pay/update.order.payresult'
        data = {
            'appId': "HZMBWEB_HK",
            'equipment': "PC",
            'joinType': "WEB",
            'orderReqno': orderReqno,
            'payType': "MasterCard",
            'version': version
        }
        r = sendReq(url, data=data, method='post', cookie=cookie)
        ret = r.json()
        if ('code' in ret) and (ret['code'] == '408'):
            raise PermissionError(ret['message'])
        print('Update payment result returns: ', ret)
        # skip get order details if update payment returns order info
        if ('code' in ret) and (ret['code'] == 'SUCCESS') and ('responseData' in ret) and ('status' in ret['responseData']) \
                and ('exchangeCode' in ret['responseData']) and (ret['responseData']['status'] == '1') and (len(ret['responseData']['exchangeCode']) > 10):
            return {
                'orderStatus': '1',
                'orderNo': ret['responseData']['orderNo'],
                'bcrq': ret['responseData']['ticketData'],
                'bookBeginTime': ret['responseData']['bookBeginTime']
            }
    return getOrderDetails(orderNumber, cookie)
    # return order['orderStatus']

def book(date, beginTime, endTime, peoples, cookie, line, captcha, baseurl):
    newcookie = {}
    for bUrl, obj in cookie.items():
        if bUrl == baseurl:
            newcookie[bUrl] = obj
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
    url = '/ticket/buy.ticket'
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
    r = sendReq(url, data=data, method='post', cookie=newcookie, timeout=book_timeout)
    ret = r.json()
    if ('responseData' in ret) and ('orderNumber' in ret['responseData']):
        return ret['responseData']['orderNumber']
    elif ('code' in ret) and ('message' in ret) and (ret['code'] == 'FAIL') and (ret['message'] == '您還有未支付的訂單,請先支付后再進行購票,謝謝!'):
        print('User has unpaid orders.')
        return ''
    elif ('code' in ret) and (ret['code'] == '408'):
        raise PermissionError(ret['message'])
    elif ('code' in ret) and ('message' in ret) and (ret['code'] == 'FAIL') and (ret['message'] == '預約人數超出當前可預約的總人數'):
        raise LookupError(ret['message'])
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
    url = '/wx/query.wx.order.payreq'
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
    try:
        r = sendReq(url, data=data, method='post', cookie=cookie)
        ret = r.json()
    except Exception as e:
        print('Get payment link failed: ',e)
        return False
    if ('code' in ret) and (ret['code'] == '408'):
        raise PermissionError(ret['message'])
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

def sendReq(reqUrl, data=None, method='get', timeout=None, retry=None, resp_json=True, cookie=None, headers=None, skipErrorStatusCode=False, returnBaseUrl=False):
    if timeout is None:
        timeout = req_timeout
    if retry is None:
        retry = req_retry

    if cookie is not None:
        urlAry = []
        cookieStrAry = []
        tokenAry = []
        if headers is None:
            headers = {}
        for bUrl, obj in cookie.items():
            if 'token' in obj:
                tokenAry.append(obj['token'])
                cookieStrAry.append(obj['cookie'])
                urlAry.append(bUrl)

    while retry > 0:
        if cookie is not None:
            baseurl = urlAry[retry % len(urlAry)]
            url = baseurl + reqUrl
            cookieStr = {'PHPSESSID': cookieStrAry[retry % len(urlAry)]}
            headers['Authorization'] = tokenAry[retry % len(urlAry)]
        else:
            cookieStr = None
            url = reqUrl
        try:
            if debug:
                print('Req. ...', url)
            if method == 'get':
                r = requests.get(url, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookieStr)
            elif method == 'patch':
                r = requests.patch(url, json=data, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookieStr)
            else:
                r = requests.post(url, json=data, timeout=timeout, allow_redirects=False, headers=headers, cookies=cookieStr)
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
        if returnBaseUrl:
            return r, baseurl
        else:
            return r
    print('Retry too many times. Failed.')
    raise Exception('Retry too many times. Failed.')


def selectSlot(linecode, datelist, count):
    url = django_url + 'hkzh/api/slot/list/'
    headers = {'Authorization': 'Token ' + django_token}
    try:
        r = sendReq(url, headers=headers, skipErrorStatusCode=True)
        ret = r.json()
    except Exception as e:
        raise ValueError('Get slot list error: ' + str(e))
    if len(ret) == 0:
        return []
    else:
        df = pd.DataFrame(ret)
        df = df[(df['availablePeople'] >= count) & (df['saleStatus'] == 1) & (df['date'].isin(datelist)) & (df['linecode'] == linecode)]
        # Sort by availablePeople desc
        # df = df.sort_values(by='availablePeople', ascending=False)
        # random sorting
        if len(df) > 1:
            df = df.sample(frac=1, weights='availablePeople')
        # print(df)
        return df.to_dict('records')

# 取账户里的指定的状态订单
def getAccountOrders(cookie, paid=False):
    if paid:
        status = 1
    else:
        status = 0
    url = '/wx/query.wx.order.record'
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
    r = sendReq(url, data=data, method='post', cookie=cookie)
    ret = r.json()
    if ('code' in ret) and (ret['code'] == '408'):
        raise PermissionError(ret['message'])
    if len(ret['responseData']) > 0:
        return ret['responseData']
    else:
        return []

# 比较账户中的订单是否和预订单一致
def compareExistOrders(orders, book):
    cookie = json.loads(book['cookie'])
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
            accountOrderInfo = getOrderDetails(orderNumber=orderNo, cookie=cookie)
            for passenger in book['passengers']:
                if passenger['id'][0] == '#':
                    passengerId = passenger['id'][1:]
                else:
                    passengerId = passenger['id']
                if accountOrderInfo['usersInfo'].find(passengerId) < 0:
                    isThisOrder = False
                    break
        if isThisOrder:
            return orderNo
    return False

def findOrderFromAccount(user, cookie):
    accountOrders = getAccountOrders(cookie, False)
    if len(accountOrders) == 0:
        accountOrders = getAccountOrders(cookie, True)
        if len(accountOrders) == 0:
            print('Have not found any order in the account.')
            return None
        else:
            orderId = compareExistOrders(accountOrders, user)
            if orderId:
                print('Found paid order %s'%orderId)
                return orderId
            else:
                print('Have not found related orders in the account.')
                return None
    else:
        orderId = compareExistOrders(accountOrders, user)
        if orderId:
            print('Found unpaid order %s' % orderId)
            return orderId
        else:
            accountOrders = getAccountOrders(cookie, True)
            if len(accountOrders) == 0:
                print('Have not found any order in the account.')
                return None
            else:
                orderId = compareExistOrders(accountOrders, user)
                if orderId:
                    print('Found paid order %s' % orderId)
                    return orderId
                else:
                    print('Have not found related orders in the account.')
                    return None

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
    url = '/captcha'
    r, baseurl = sendReq(url, cookie=cookie, resp_json=False, returnBaseUrl=True)
    return baseurl, base64.b64encode(r.content).decode('utf-8')


def bookRun(user):
    while True:
        now = datetime.now()
        print(now.strftime('%m-%d %H:%M:%S'))
        # update status.
        user = getBookInfo(user['id'])
        if user['status'] in ['paid', 'done']:
            print('Status is %s'%user['status'])
            return True
        elif user['status'] in ['canceled', 'pending']:
            print('Status is %s'%user['status'])
            return False

        needLogin = False
        if (user['status'] == 'processing') or (user['cookie'] is None) or (user['cookie'] == ''):
            needLogin = True
        else:
            cookie = json.loads(user['cookie'])
            createdAt = cookie['createdAt']
            createdAt = datetime.strptime(createdAt, '%Y-%m-%d %H:%M:%S')
            if (createdAt + timedelta(minutes=login_expire_minutes)) < now:
                needLogin = True
        if needLogin:
            # login.
            print('Login... ', user['login']['username'])
            try:
                LoginRet = login(user['login']['username'],  user['login']['password'])
            except AssertionError as e:
                print('Login failed: '+str(e))
                user['comment'] += 'Change to pending: '+str(e)+'; '
                user['status'] = 'pending'
                updateBookInfo(user['id'], {
                    'comment': user['comment'],
                    'status': user['status']
                })
                return False
            except Exception as e:
                print(e)
                continue
            if not LoginRet:
                print('Login failed.')
                continue
            LoginRet['createdAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            user['cookie'] = json.dumps(LoginRet)
            if user['status'] == 'processing':
                user['status'] = 'login'
            updateBookInfo(user['id'], {
                'cookie': user['cookie'],
                'status': user['status']
            })
            print('Login success.')
            cookie = LoginRet

        if user['status'] in ['payment', 'checking', 'booked']:
            if (user['bookNumber'] == '') or (user['bookNumber'] is None):
                try:
                    # find orderNumber
                    user['bookNumber'] = findOrderFromAccount(user, cookie)
                except Exception as e:
                    print(e)
                    continue
                if user['bookNumber'] == None:
                    user['bookNumber'] = ''
                    user['status'] = 'login'
                    updateBookInfo(user['id'], {
                        'bookNumber': user['bookNumber'],
                        'status': user['status']
                    })
                    continue
                updateBookInfo(user['id'], {
                    'bookNumber': user['bookNumber']
                })

            # Pending payment and payment link not generated
            if len(user['bookNumber'].split(',')) < 3:
                order = user['bookNumber'].split(',')[0]
                try:
                    paylink = getPaymentLink(order, cookie)
                except PermissionError as e:
                    print(e)
                    print('Relogin...')
                    user['cookie'] = None
                    updateBookInfo(user['id'], {
                        'cookie': user['cookie']
                    })
                    continue
                except Exception as e:
                    print('getPaymentLink failed:', e)
                    continue
                if paylink is not False:
                    user['bookNumber'] = order + ',' + paylink['orderReqno'] + ',' + paylink[
                        'session']
                    user['status'] = 'payment'
                    user['paymentExpireAt'] = paylink['endTime']
                    updateBookInfo(user['id'], {
                        'bookNumber': user['bookNumber'],
                        'status': user['status'],
                        'paymentExpireAt': user['paymentExpireAt']
                    })

            if user['status'] == 'checking':
                orderReqno = user['bookNumber'].split(',')[1]
            else:
                orderReqno = None
            try:
                status = getOrderStatus(orderNumber=user['bookNumber'].split(',')[0], orderReqno=orderReqno, cookie=cookie)
            except PermissionError as e:
                print(e)
                print('Relogin...')
                user['cookie'] = None
                updateBookInfo(user['id'], {
                    'cookie': user['cookie']
                })
                continue
            except Exception as e:
                print(e)
                continue
            print('User #%i Order %s status is %s'%(user['id'], user['bookNumber'].split(',')[0], status['orderStatus']))

            # canceled or expired
            if status['orderStatus'] in ['C', 'E']:
                user['status'] = 'login'
                user['bookNumber'] = None
                updateBookInfo(user['id'], {
                    'bookNumber': user['bookNumber'],
                    'status': user['status']
                })
                continue
            # paid
            elif status['orderStatus'] == '1':
                updateBookInfo(user['id'], {
                    'status': 'paid',
                    'bookNumber': status['orderNo'],
                    'bookDate': status['bcrq'] + ' ' + status['bookBeginTime'],
                    'paidAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                return True


        if user['status'] == 'login':
            slotlist = selectSlot(user['line_code'], user['datelist'], user['passengerCount'])
            if len(slotlist) == 0:
                print('No slot available.')
            else:
                print('Try %i slots...'%len(slotlist))
                for slot in slotlist:
                    print('Try to book ', slot['date'], slot['time'])
                    order = None
                    for bi in range(book_retry):
                        try:
                            baseurl, captchaBase64 = getCaptcha(cookie)
                            captcha = captchaFromCjy(captchaBase64)
                            order = book(slot['date'], slot['time'], slot['time'], user['passengers'], cookie, slot['linecode'], captcha, baseurl=baseurl)
                        except PermissionError as e:
                            print(e)
                            print('Relogin...')
                            user['cookie'] = None
                            updateBookInfo(user['id'], {
                                'cookie': user['cookie']
                            })
                            break
                        except ValueError as e:
                            print(str(e))
                            continue
                        except LookupError as e:
                            # slot out of stock, try next slot
                            print(e)
                            break
                        except TimeoutError as e:
                            print('Book failed:', e)
                            break
                        except Exception as e:
                            print('Book failed:', e)
                            break
                        break
                    if order is None:
                        if user['cookie'] is None:
                            break
                        continue
                    print('SUCCESS!!! Order #', order)
                    user['status'] = 'booked'
                    user['bookNumber'] = order
                    update_obj = {
                        'bookNumber': user['bookNumber'],
                        'status': user['status']
                    }
                    if order != '':
                        update_obj['bookDate'] = slot['date'] + ' ' + slot['time']
                    updateBookInfo(user['id'], update_obj)
                    break

        time.sleep(step)


if __name__ == '__main__':
    if (django_url is None) or (django_token is None):
        raise ValueError('django_url & django_token must be set.')

    debug = False
    req_timeout = req_retry = 10
    base_url = getConfigValue('BASE_URL')
    version = getConfigValue('API_VERSION')
    step = int(getConfigValue('SCHEDULE_STEP'))
    debug = bool(getConfigValue('SCHEDULE_DEBUG'))
    req_timeout = int(getConfigValue('SCHEDULE_TIMEOUT'))
    req_retry = int(getConfigValue('SCHEDULE_RETRY'))
    book_retry = int(getConfigValue('BOOK_RETRY'))
    book_timeout = int(getConfigValue('BOOK_TIMEOUT'))
    login_expire_minutes = int(getConfigValue('CHECK_LOGIN_EXPIRE_MINUTES'))
    cjy_auth = getConfigValue('CJY_AUTH')
    cjy_user, cjy_pass, cjy_soft, cjy_type = cjy_auth.split(',')

    while True:
        if bool(getConfigValue('SCHEDULE_RUN')):
            user = selectUser()
            if not user:
                print('No available user.')
                time.sleep(step)
                continue
            print('Working on User #%i...' % user['id'])
            bookRun(user)
        else:
            print('SCHEDULE_RUN is set to disabled.')
        time.sleep(step)
