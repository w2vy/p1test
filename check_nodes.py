#!/usr/bin/python3
'''This module is a single file that supports the loading of secrets into a Flux Node'''
from asyncio import open_connection
import json
import sys
import requests
import socket
from datetime import datetime
import time
import signal
#import readchar

max_nodes = 0
num_nodes = 0
num_checked = 0
num_good = 0

def handler(signum, frame):
    print("Checked ", num_checked, " of ", num_nodes, "/", max_nodes, " and ", num_good, " had no errors")
    msg = "Ctrl-c was pressed. Do you really want to exit? y/n "
    print(msg, end="", flush=True)
    res = sys.stdin.read(1)
    if res == 'y':
        print("")
        raise signal.SIGTERM
        exit(1)
    else:
        print("", end="\r", flush=True)
        print(" " * len(msg), end="", flush=True) # clear the printed line
        print("    ", end="\r", flush=True)
 
def timestamp():
    cur_time = datetime.now()
    now = cur_time.strftime("%b-%d-%Y %H:%M:%S ")
    return now

def logmsg(msg):
    '''Format message with date and time'''
    return timestamp()+msg

def print_log(node_ip, mylog):
    '''Print log for a node'''
    print(" ")
    print(node_ip, "Min", mylog['min'], "Max", mylog['max'], "Avg", mylog['avg'])
    for line in mylog['log']:
        print(line)

def get_public_ip():
    '''Get public ip or return None'''
    url = "http://ifconfig.me/ip"
    req = requests.get(url)
    pub_ip = None
    if req.status_code == 200:
        pub_ip = req.text
    return pub_ip

def non_routable_ip(ip_adr):
    '''Check IPv4 or IPv6 Encoded IPv4 address for Private IPs'''
    ipadr = ip_adr
    if ipadr.startswith("::ffff:"):
        ipadr = ipadr[7:]
    bytes = ipadr.split(".")
    a = int(bytes[0])
    b = int(bytes[1])
    if a == 10:
        return True
    if a == 192 and b == 168:
        return True
    if a == 172 and b >= 16 and b <= 31:
        return True
    if a == 169 and b == 254:
        # Link Local does not make sense in a networkin environment
        return True
    return False

def get_flux(the_node, path):
    '''Call flux API'''
    if len(the_node) == 0:
        the_node = "api.runonflux.io"
    else:
        if len(the_node.split(":")) == 1:
            the_node = the_node + ":16127"
    url = "http://" + the_node + "/" + path
    try:
        req = requests.get(url, timeout=5)
    except KeyboardInterrupt:
        raise KeyboardInterrupt
    except:
        return None
    # Get the list of nodes where our app is deplolyed
    ret_data = None
    if req.status_code == 200:
        try:
            values = json.loads(req.text)
            if values["status"] == "success":
                # json looks good and status correct, iterate through node list
                ret_data = values["data"]
        except ValueError:
            ret_data = None
    return ret_data

def node_connection(port, appip):
    '''Open socket to Node'''
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error:
        return 'Failed to create socket'

    try:
        remote_ip = socket.gethostbyname( appip )
    except socket.gaierror:
        return 'Hostname could not be resolved'

    # Set short timeout
    sock.settimeout(30)

    # Connect to remote server
    try:
        error = None
        #  print('# Connecting to server, ' + appip + ' (' + remote_ip + ')')
        sock.connect((remote_ip , port))
    except ConnectionRefusedError:
        error = appip + " connection refused"
        sock.close()
        sock = None
    except TimeoutError:
        error = appip + " Connect TimeoutError"
        sock.close()
        sock = None
    except socket.error:
        error = appip + " No route to host"
        sock.close()
        sock = None

    if sock is None:
        return error

    sock.settimeout(None)
    # Set longer timeout
    sock.settimeout(60)
    return sock

def check_app(app_name):
    '''Check all running instances and see if we can reach the app'''
    url = "https://api.runonflux.io/apps/location/" + app_name
    req = requests.get(url, timeout=10)
    # Get the list of nodes where our app is deplolyed
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
            nodes = values["data"]

            for this_node in nodes:
                data = get_flux(this_node['ip'], "daemon/getzelnodestatus")
                #print(data)
                status = data['status']
                if status == "CONFIRMED":
                    tier = data['tier']
                else:
                    tier = "none"
                print(this_node['ip'] + " " + status + " " + tier)
                data = get_flux(this_node['ip'], "apps/listrunningapps")
                for app in data:
                    app_state = ""
                    if app["Names"][0].startswith("/flux") and app["Names"][0].endswith("_" + name):
                        app_state += app["Names"][0]
                        app_state += " State " + app["State"] + " Status " + app["Status"] + " "
                        ports = app["Ports"]
                        for port in ports:
                            if "IP" in port and port["IP"] == "0.0.0.0" and port["Type"] == "tcp":
                                app_state += str(port["PublicPort"]) + " "
                                node_ip = this_node['ip'].split(":")[0]
                                sock = node_connection(port["PublicPort"], node_ip)
                                if isinstance(sock, str):
                                    app_state += sock + " "
                                else:
                                    app_state += "OK "
                                    sock.close()
                        print(" App: " + app_state)

# CSV Format
# Timestamp, NodeIP, Status (CONFIRMED, expired, noapiport), Tier, App, port, status
def add_csv(f, node, nstatus, tier="", app="", port="", status=""):
    if f is not None:
        f.write(timestamp() + "," + node + "," + nstatus + "," + tier + "," + app + "," + port + "," + status + "\n")
        f.flush()

def check_nodes(filter, csv):
    '''Check all running instances and see if we can reach the app'''
    global max_nodes, num_checked, num_good, num_nodes
    url = "https://api.runonflux.io/daemon/viewdeterministiczelnodelist/" + filter
    req = requests.get(url)
    # Get the list of nodes where our app is deployed
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
            fcsv = None
            if csv is not None:
                try:
                    fcsv = open(csv, "a")
                except:
                    print("Open of ", csv, " failed")
                    return
            nodes = values["data"]
            max_nodes = len(nodes)
            num_nodes = 0
            num_checked = 0
            num_good = 0
            for this_node in nodes:
                sys.stdout.flush()
                num_nodes += 1
                data = get_flux(this_node['ip'], "daemon/getzelnodestatus")
                #print("Node Status:", data)
                if data is None:
                    print(logmsg(this_node["ip"] + " API Port FAILED"))
                    add_csv(fcsv, this_node["ip"], "noapiport")
                    continue
                status = data['status']
                if status == "CONFIRMED":
                    tier = data['tier']
                else:
                    tier = "none"
                data = get_flux(this_node['ip'], "flux/connectedpeers")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get connected peers"))
                    add_csv(fcsv, this_node["ip"], "getpeersfailed", tier)
                    continue
                for peer in data:
                    failed = False
                    if non_routable_ip(peer):
                        print(logmsg(this_node["ip"] + " " + status + " " + tier + " non routable peer " + peer))
                        add_csv(fcsv, this_node["ip"], "nonroutablepeer", tier)
                        failed = True
                        break
                if failed:
                    continue
                data = get_flux(this_node['ip'], "flux/incomingconnections")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get incoming connection"))
                    add_csv(fcsv, this_node["ip"], "incomingfailed", tier)
                    continue
                for peer in data:
                    failed = False
                    if non_routable_ip(peer):
                        print(logmsg(this_node["ip"] + " " + status + " " + tier + " non routable incoming " + peer))
                        add_csv(fcsv, this_node["ip"], "nonroutableincoming", tier)
                        failed = True
                        break
                if failed:
                    continue
                data = get_flux(this_node['ip'], "apps/listrunningapps")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get running apps"))
                    add_csv(fcsv, this_node["ip"], "nolistapps", tier)
                    continue
                for app in data:
                    app_state = ""
                    found_ports = False
                    found_error = False
                    any_good = False
                    app_state += "Found " + app["Names"][0]
                    app_state += " State " + app["State"] + " Status " + app["Status"] + " "
                    ports = app["Ports"]
                    nports = 0
                    for port in ports:
                        if "IP" in port and port["IP"] == "0.0.0.0" and port["Type"] == "tcp":
                            found_ports = True
                            nports += 1
                            sport = str(port["PublicPort"])
                            app_state += sport + " "
                            node_ip = this_node['ip'].split(":")[0]
                            sock = node_connection(port["PublicPort"], node_ip)
                            if isinstance(sock, str):
                                app_state += "FAILED " + sock + " "
                                found_error = True
                                add_csv(fcsv, this_node["ip"], status, tier, app["Names"][0], sport, sock)
                            else:
                                app_state += "OK "
                                any_good = True
                                sock.close()
                                add_csv(fcsv, this_node["ip"], status, tier, app["Names"][0], sport, "OK")
                    if found_ports:
                        num_checked += 1
                        if not found_error:
                            num_good += 1
                        #print(logmsg(this_node['ip'] + " " + status + " " + tier + " " + app_state))
                        if not any_good:
                            print(logmsg(this_node['ip'] + " " + status + " " + tier + " All Ports " + str(nports) + " failed"))
                    else:
                        add_csv(fcsv, this_node["ip"], status, tier, app["Names"][0])
            print("Summary: ", num_nodes, " found, ", num_checked, " nodes checked, ", num_good, " found with no issues")
            if csv is not None:
                fcsv.close()
        else:
            print(values)
    else:
        print(req)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)

    if len(sys.argv) > 1:
        if sys.argv[1].lower() == "--all":
            csv_name = None
            if len(sys.argv) > 3:
                if sys.argv[2].lower() == "--csv":
                    csv_name = sys.argv[3]
            check_nodes("", csv_name)
            sys.exit(0)
        if sys.argv[1].lower() == "--filter":
            if len(sys.argv) > 2:
                filter = sys.argv[2]
                csv_name = None
                if len(sys.argv) > 4:
                    if sys.argv[3].lower() == "--csv":
                        csv_name = sys.argv[4]
                check_nodes(filter, csv_name)
                sys.exit(0)
        if sys.argv[1].lower() == "--app":
            if len(sys.argv) > 2:
                name = sys.argv[2]
                check_app(name)
                sys.exit(0)
    print("Incorrect arguments:")
    print(sys.argv[0], "--all    check all nodes for running applications to test")
    time.sleep(5)
    print(sys.argv[0], "--filter check nodes matching the supplied `filter` for running applications to test")
    time.sleep(5)
    print(sys.argv[0], "--app    test nodes running application 'app'")
    # peers = get_flux("192.168.8.89:16197", "flux/connectedpeers")
    # print(peers)
    # data = get_flux("192.168.8.89:16197", "flux/incomingconnections")
    # print(data)
    # if "::ffff:185.218.126.171" in data:
    #     print("Test Passed")
    # else:
    #     print("Test Failed")
    # for peer in peers:
    #     if "::ffff:"+peer in data:
    #         print("Found", peer)
    sys.exit(1)
