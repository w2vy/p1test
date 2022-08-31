#!/usr/bin/python3
'''This module is a single file that supports the loading of secrets into a Flux Node'''
import json
import sys
import requests
from fluxvault import FluxAgent
from datetime import datetime

VAULT_NAME = "home.moulton.us"                    # EDIT ME
FILE_DIR = "./files/"   # EDIT ME
VAULT_PORT = 39289                                # EDIT ME
APP_NAME = "p1"                            # EDIT ME
VERBOSE = False

def logmsg(msg):
    '''Format message with date and time'''
    cur_time = datetime.now()
    now = cur_time.strftime("%b-%d-%Y %H:%M:%S ")
    return now+msg

def print_log(node_ip, mylog):
    '''Print log for a node'''
    print(" ")
    print(node_ip, "Min", mylog['min'], "Max", mylog['max'], "Avg", mylog['avg'])
    for line in mylog['log']:
        print(line)

# pylint: disable=W0702
def dump_report():
    '''Print report stored in json file'''
    try:
        with open(FILE_DIR+"node_log.json", encoding="utf-8") as file:
            json_data = file.read()
        node_log = json.loads(json_data)
    except:
        print("Error opening data file " + FILE_DIR+"node_log.json")
        return
    for node_ip in node_log.keys():
        print_log(node_ip, node_log[node_ip])

def get_public_ip():
    '''Get public ip or return None'''
    url = "http://ifconfig.me/ip"
    req = requests.get(url)
    pub_ip = None
    if req.status_code == 200:
        pub_ip = req.text
    return pub_ip

def get_flux(the_node, path):
    '''Call flux API'''
    if len(the_node) == 0:
        the_node = "api.runonflux.io"
    else:
        if len(the_node.split(":")) == 1:
            the_node = the_node + ":16127"
    url = "http://" + the_node + "/" + path
    try:
        req = requests.get(url, timeout=10)
    except:
        return None
    # Get the list of nodes where our app is deplolyed
    ret_data = None
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
            ret_data = values["data"]
    return ret_data

class MyFluxAgent(FluxAgent):
    '''User class to allow easy configuration, see EDIT ME above'''
    def __init__(self) -> None:
        super().__init__()
        self.vault_name = VAULT_NAME
        self.file_dir = FILE_DIR
        self.vault_port = VAULT_PORT
        self.verbose = VERBOSE

def node_vault():
    '''Vault runs this to poll every Flux node running their app'''
    url = "https://api.runonflux.io/apps/location/" + APP_NAME
    req = requests.get(url, timeout=10)
    # Get the list of nodes where our app is deplolyed
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
            nodes = values["data"]
            try:
                with open(FILE_DIR+"node_log.json", encoding="utf-8") as file:
                    fdata = file.read()
                node_log = json.loads(fdata)
            except:
                node_log = {}

            for ip in node_log.keys():
                node_log[ip]['active'] = 0

            for this_node in nodes:
                data = get_flux(this_node['ip'], "daemon/getzelnodestatus")
                if data is None:
                    print(logmsg(this_node['ip'] + "get status failed"))
                    continue
                status = data['status']
                tier = data['tier']
                data = get_flux(this_node['ip'], "apps/listrunningapps")
                if data is None:
                    print(logmsg(this_node['ip'] + "get running apps failed"))
                    continue
                app_state = ""
                for app in data:
                    if app["Names"][0] == "/fluxp1test_p1":
                        app_state += "Found " + app["Names"][0]
                        app_state += " State " + app["State"] + " Status " + app["Status"] + " "
                print(logmsg(this_node['ip'] + " " + status + " " + tier + " " + app_state))
                if this_node['ip'] in node_log:
                    mylog = node_log[this_node['ip']]
                    mylog['active'] = 1
                else:
                    if VERBOSE:
                        print("New Node " + this_node['ip'])
                    msg = logmsg("New Instance " + this_node['ip'])
                    mylog = { 'log': [msg], 'min':999999999, 'max':0, 'avg':0,
                        'active':1, 'reported':0 }
                start = datetime.now()
                agent = MyFluxAgent() # Each connection to a node get a fresh agent
                ipadr = this_node['ip'].split(':')[0]
                if VERBOSE:
                    print(this_node['name'], ipadr)
                agent.node_vault_ip(ipadr)
                dt = datetime.now() - start
                ms = round(dt.microseconds/1000)+dt.seconds*1000
                if VERBOSE:
                    print(ms, " ms")
                    print(this_node['name'], ipadr, agent.result)
                if 'min' not in mylog:
                    mylog['min'] = mylog['max'] = mylog['avg'] = 0
                if ms < mylog['min']:
                    mylog['min'] = ms
                if ms > mylog['max']:
                    mylog['max'] = ms
                if mylog['avg'] == 0:
                    mylog['avg'] = ms
                else:
                    # Smoothed average 7/8 of average plus 1/8 new sample
                    mylog['avg'] = round(mylog['avg'] - (mylog['avg']/8) + (ms/8))
                mylog['log'] += agent.log
                node_log[this_node['ip']] = mylog
                for log in agent.log:
                    print(log)
            if VERBOSE:
                print("************************ REPORT *****************************")
            pop_nodes = []
            for ip in node_log.keys():
                if node_log[ip]['active'] == 0:
                    msg = logmsg("Node removed " + ip)
                    node_log[ip]['log'] += [msg]
                    print_log(ip, node_log[ip])
                    pop_nodes += [ip]
                else:
                    if len(node_log[ip]['log']) > node_log[ip]['reported']:
                        print_log(ip, node_log[ip])
                        node_log[ip]['reported'] = len(node_log[ip]['log'])
            for ip in pop_nodes:
                node_log.pop(ip, None)

            try:
                with open(FILE_DIR+"node_log.json", 'w', encoding="utf-8") as file:
                    data = file.write(json.dumps(node_log))
            except:
                print("Save log failed")

        else:
            print("Error", req.text)
    else:
        print("Error", url, "Status", req.status_code)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        node_vault()
        sys.exit(0)
    if sys.argv[1].lower() == "--ip":
        if len(sys.argv) > 2:
            ipaddr = sys.argv[2]
            one_node = MyFluxAgent()
            one_node.node_vault_ip(ipaddr)
            print(ipaddr, one_node.result)
            sys.exit(0)
        else:
            print("Missing Node IP Address: --ip ipaddress")
    if sys.argv[1].lower() == "--dump":
        dump_report()
        sys.exit(0)
    if sys.argv[1].lower() == "--check":
        if len(sys.argv) > 2:
            node = sys.argv[2]
            cdata = get_flux(node, "daemon/getzelnodestatus")
            cstatus = cdata['status']
            ctier = cdata['tier']
            cdata = get_flux(node, "apps/listrunningapps")
            capp_state = ""
            for capp in cdata:
                if capp["Names"][0] == "/fluxp1test_p1":
                    capp_state += "Found " + capp["Names"][0]
                    capp_state += " State " + capp["State"] + " Status " + capp["Status"] + " "
                if capp["Names"][0] == "/fluxgammonbot_gammonbot":
                    capp_state += "Found " + capp["Names"][0]
                    capp_state += " State " + capp["State"] + " Status " + capp["Status"] + " "
            print(node, cstatus, ctier,  capp_state)
            sys.exit(0)
    if sys.argv[1].lower() == "--test":
#        data = get_flux("", "apps/location/gammonbot")
#        print("gammonbot", data)
        tdata = get_flux("192.168.8.90:16177","daemon/getzelnodestatus")
        print("node 1", tdata)
#        tdata = get_flux("65.21.232.4","daemon/getzelnodestatus")
#        print("node 2", tdata)
        tdata = get_public_ip()
        print("IP = ", tdata)
        sys.exit(0)
    print("Incorrect arguments:")
    print("With no arguments all nodes running ", APP_NAME, " will be polled")
    print("If you specify '--ip ipaddress' then that ipaddress will be polled")
    sys.exit(1)
