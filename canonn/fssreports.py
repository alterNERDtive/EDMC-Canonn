try:
    from urllib.parse import quote_plus
    from urllib.parse import urlencode
except:
    from urllib import quote_plus
    from urllib import urlencode


import threading
import requests
import sys
import json
from canonn.emitter import Emitter
import canonn.emitter
from canonn.debug import Debug
from canonn.debug import debug, error
from canonn.systems import Systems
import random
import time
from queue import Queue


class fssProcess(threading.Thread):
    def __init__(self, dummy):
        threading.Thread.__init__(self)

    def run(self):
        FSS.process()


class FSS():

    events = Queue()

    @classmethod
    def put(cls, cmdr, system, x, y, z, entry):
        data = {"cmdr": cmdr, "system": system,
                "coords": [x, y, z], "entry": entry}
        debug("Putting FSS Signal on queue")
        cls.events.put(data)

    @classmethod
    def process(cls):

        while not cls.events.empty():
            # process each of the entries
            data = cls.events.get()
            entry = data.get("entry")

            isStation = (entry.get("IsStation"))
            FleetCarrier = (entry.get("SignalName") and entry.get(
                "SignalName")[-4] == '-' and entry.get("SignalName")[-8] == ' ' and isStation)
            FSSSignalDiscovered = (entry.get("event") == "FSSSignalDiscovered")
            USS = ("$USS" in entry.get("SignalName"))

            if not FleetCarrier and not USS:
                debug("posting fss to gcloud")
                FSS.postFSS(data)

    @classmethod
    def postFSS(cls, payload):
        url = "https://europe-west1-canonn-api-236217.cloudfunctions.net/postFSSSignal"
        x, y, z = payload.get("coords")
        entry = payload.get("entry")
        system = payload.get("system")
        cmdr = payload.get("system")

        data = {
            "signalname": entry.get("SignalName"),
            "signalNameLocalised": entry.get("SignalName_Localised"),
            "cmdr": cmdr,
            "system": system,
            "x": x,
            "y": y,
            "z": z,
            "raw_json": entry,
        }
        debug(data)
        r = requests.gut(url, data)
        if not r.status_code == requests.codes.ok:
            headers = r.headers
            contentType = str(headers['content-type'])
            if 'json' in contentType:
                error(json.dumps(r.content))
            else:
                error(r.content)
            error(r.status_code)


class fssEmitter(Emitter):
    types = {}
    reporttypes = {}
    excludefss = {}
    fssFlag = False

    def __init__(self, cmdr, is_beta, system, x, y, z, entry, body, lat, lon, client):
        Emitter.__init__(self, cmdr, is_beta, system, x, y,
                         z, entry, body, lat, lon, client)
        self.modelreport = "xxreports"
        self.modeltype = "xxtypes"

    def getFssPayload(self):
        payload = self.setPayload()
        payload["reportStatus"] = "pending"
        payload["systemAddress"] = self.entry.get("SystemAddress")
        payload["signalName"] = self.entry.get("SignalName")
        payload["signalNameLocalised"] = self.entry.get("SignalName_Localised")

        payload["spawningState"] = self.entry.get("SpawningState")
        payload["spawningStateLocalised"] = self.entry.get(
            "SpawningState_Localised")
        payload["spawningFaction"] = self.entry.get("SpawningFaction")

        payload["rawJson"] = self.entry

        return payload

    def getLcPayload(self):
        payload = self.setPayload()
        payload["reportStatus"] = "pending"
        payload["systemAddress"] = self.entry.get("SystemAddress")
        payload["signalName"] = self.entry.get("SignalName")
        payload["signalNameLocalised"] = self.entry.get("SignalName_Localised")

        debug(payload)

        payload["rawJson"] = self.entry

        return payload

    def getAXPayload(self):
        payload = self.setPayload()
        payload["reportStatus"] = "pending"
        payload["systemAddress"] = self.entry.get("SystemAddress")
        # can remove these from strapi model because they will always be the same
        # payload["signalName"]=self.entry.get("signalName")
        # payload["signalNameLocalised"]=self.entry.get("signalNameLocalised")
        payload["rawJson"] = self.entry

        return payload

    def gSubmitAXCZ(self, payload):
        p = payload.copy()
        p["x"], p["y"], p["z"] = Systems.edsmGetSystem(
            payload.get("systemName"))
        if p.get("isBeta"):
            p["isBeta"] = 'Y'
        else:
            p["isBeta"] = 'N'

        p["rawJson"] = json.dumps(payload.get(
            "rawJson"), ensure_ascii=False).encode('utf8')

        url = "https://us-central1-canonn-api-236217.cloudfunctions.net/submitAXCZ"
        debug("gSubmitAXCZ {}".format(p.get("systemName")))

        getstr = "{}?{}".format(url, urlencode(p))

        debug("gsubmit {}".format(getstr))
        r = requests.get(getstr)

        if not r.status_code == requests.codes.ok:
            error(getstr)
            error(r.status_code)

    def getExcluded(self):

        # sleep a random amount of time to avoid race conditions
        timeDelay = random.randrange(1, 100)
        time.sleep(1/timeDelay)

        if not fssEmitter.fssFlag:
            fssEmitter.fssFlag = True
            debug("Getting FSS exclusions")
            r = requests.get(
                "{}/excludefsses?_limit=1000".format(self.getUrl()))
            debug("{}/excludefsses?_limit=1000".format(self.getUrl()))
            if r.status_code == requests.codes.ok:
                for exc in r.json():
                    fssEmitter.excludefss[exc.get("fssName")] = True
            else:
                debug("FFS exclusion failed")
                debug("status: {}".format(r.status_code))

    def run(self):

        self.getExcluded()

        FSSSignalDiscovered = (self.entry.get(
            "event") == "FSSSignalDiscovered")
        USS = ("$USS" in self.entry.get("SignalName"))
        isStation = (self.entry.get("IsStation"))
        FleetCarrier = (self.entry.get("SignalName") and self.entry.get(
            "SignalName")[-4] == '-' and isStation)
        life_event = ("$Fixed_Event_Life" in self.entry.get("SignalName"))
        excluded = fssEmitter.excludefss.get(self.entry.get("SignalName"))

        # is this a code entry and do we want to record it?
        # We don't want to record any that don't begin with $ and and with ;
        if FSSSignalDiscovered and not excluded and not USS and not isStation and '$' in self.entry.get("SignalName"):

            url = self.getUrl()

            if "$Warzone_TG" in self.entry.get("SignalName"):
                payload = self.getAXPayload()
                self.gSubmitAXCZ(payload)
                self.modelreport = "axczfssreports"
            elif life_event:
                debug(self.entry.get("SignalName"))

                payload = self.getLcPayload()
                self.modelreport = "lcfssreports"
            else:
                payload = self.getFssPayload()
                self.modelreport = "reportfsses"

            self.send(payload, url)


def submit(cmdr, is_beta, system, x, y, z, entry, body, lat, lon, client):
    if entry.get("event") == "FSSSignalDiscovered":
        fssEmitter(cmdr, is_beta, system, x, y, z,
                   entry, body, lat, lon, client).start()

    if entry.get("event") == "FSSSignalDiscovered" and not is_beta:
        FSS.put(cmdr, system, x, y, z, entry)

    if entry.get("event") in ("StartJump", "Location", "Docked", "Shutdown", "ShutDown", "SupercruiseExit", "SupercruiseEntry ") and not is_beta:
        debug("FSS Process")
        fssProcess(None).start()
