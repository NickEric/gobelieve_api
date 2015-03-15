# -*- coding: utf-8 -*-
import time
import logging
import sys
import redis
from apns import APNs, Payload
import json
import config
import traceback
import npush
import binascii

rds = redis.StrictRedis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)
apns = APNs(use_sandbox=False, cert_file=config.BAUHINIA_CERT_FILE)
npush_conn = npush.Connection(config.BAUHINIA_NPUSH_CERT_FILE, config.BAUHINIA_NPUSH_KEY_FILE)


class User:
    def __init__(self):
        self.apns_device_token = None
        self.ng_device_token = None
        self.uid = None
        self.appid = None

def get_user(rds, appid, uid):
    u = User()
    key = "users_%s_%s"%(appid, uid)
    u.apns_device_token, u.ng_device_token = rds.hmget(key, "apns_device_token", "ng_device_token")
    u.appid = appid
    u.uid = uid
    return u

def ios_push(u, body):
    global apns
    token = u.apns_device_token
    content = json.loads(body)

    if content.has_key("text"):
        payload = Payload(alert=content["text"], sound="default", badge=1)
    elif content.has_key("audio"):
        payload = Payload(alert=u"收到一条语音", sound="default", badge=1)
    elif content.has_key("image"):
        payload = Payload(alert=u"收到一张图片", sound="default", badge=1)
    else:
        payload = Payload(alert=u"收到一条消息", sound="default", badge=1)

    for i in range(2):
        if i == 1:
            logging.warn("resend notification")
        try:
            logging.debug("ios push:%s", payload.alert)
            apns.gateway_server.send_notification(token, payload)
            break
        except Exception, e:
            print_exception_traceback()
            apns = APNs(use_sandbox=False, cert_file=config.BAUHINIA_CERT_FILE)
    
def ng_push(u, body):
    global npush_conn
    token = u.ng_device_token
    token = binascii.a2b_hex(token)
    content = json.loads(body)

    obj = {}
    obj["title"] = u"羊蹄甲"
    obj["push_type"] = 1
    obj["is_ring"] = True
    obj["is_vibrate"] = True
    if content.has_key("text"):
        obj["content"] = content["text"]
    elif content.has_key("audio"):
        obj["content"] = u"收到一条语音"
    elif content.has_key("image"):
        obj["content"] = u"收到一张图片"
    else:
        obj["content"] = u"收到一条消息"

    obj["package_name"] = "com.beetle.bauhinia"
    obj["app_params"] = {}

    for i in range(2):
        if i == 1:
            logging.warn("resend notification")
        try:
            notification = npush.EnhancedNotification()
            notification.token = token
            notification.identifier = 1
            notification.expiry = int(time.time()+3600)
            notification.payload = json.dumps(obj)
            logging.debug("ng notification:%s", notification.payload)
            s = notification.to_data()
            s = npush.ENHANCED_NOTIFICATION_COMMAND + s
            npush_conn.write(s)
            break
        except Exception, e:
            print_exception_traceback()
            npush_conn = npush.Connection(config.NPUSH_CERT_FILE, config.NPUSH_KEY_FILE)

def receive_offline_message():
    appid = 17
    while True:
        item = rds.blpop("push_queue_17")
        if not item:
            continue
        _, msg = item
        obj = json.loads(msg)
        u = get_user(rds, appid, obj['receiver'])
        if u is None:
            logging.info("uid:%d nonexist", obj["recieiver"])
            continue

        if u.apns_device_token:
            ios_push(u, obj["content"])
        elif u.ng_device_token:
            ng_push(u, obj["content"])
        else:
            logging.info("uid:%d has't device token", obj['receiver'])
            continue

def main():
    while True:
        try:
            receive_offline_message()
        except Exception, e:
            print_exception_traceback()
            time.sleep(1)
            continue

def print_exception_traceback():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    logging.warn("exception traceback:%s", traceback.format_exc())

def init_logger(logger):
    root = logger
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(filename)s:%(lineno)d -  %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)

if __name__ == "__main__":
    init_logger(logging.getLogger(''))
    main()