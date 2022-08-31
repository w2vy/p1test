#!/usr/bin/python3
'''This module is a single file that supports the loading of secrets into a Flux Node'''
from asyncio import open_connection
import json
import sys
import requests
import socket
from datetime import datetime
import time

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
        req = requests.get(url, timeout=5)
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
                print(data)
                status = data['status']
                if status == "CONFIRMED":
                    tier = data['tier']
                else:
                    tier = "none"
                data = get_flux(this_node['ip'], "apps/listrunningapps")
                app_state = ""
                for app in data:
                    if app["Names"][0].startswith("/flux") and app["Names"][0].endswith("_" + name):
                        app_state += "Found " + app["Names"][0]
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
                print(logmsg(this_node['ip'] + " " + status + " " + tier + " " + app_state))

def check_nodes(filter):
    '''Check all running instances and see if we can reach the app'''
    url = "https://api.runonflux.io/daemon/viewdeterministiczelnodelist/" + filter
    req = requests.get(url)
    # Get the list of nodes where our app is deplolyed
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
            nodes = values["data"]
            for this_node in nodes:
                data = get_flux(this_node['ip'], "daemon/getzelnodestatus")
                #print("Node Status:", data)
                if data is None:
                    print(logmsg(this_node["ip"] + " API Port FAILED"))
                    continue
                status = data['status']
                if status == "CONFIRMED":
                    tier = data['tier']
                else:
                    tier = "none"
                data = get_flux(this_node['ip'], "apps/listrunningapps")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get running apps"))
                    continue
                for app in data:
                    app_state = ""
                    found_ports = False
                    app_state += "Found " + app["Names"][0]
                    app_state += " State " + app["State"] + " Status " + app["Status"] + " "
                    ports = app["Ports"]
                    for port in ports:
                        if "IP" in port and port["IP"] == "0.0.0.0" and port["Type"] == "tcp":
                            found_ports = True
                            app_state += str(port["PublicPort"]) + " "
                            node_ip = this_node['ip'].split(":")[0]
                            sock = node_connection(port["PublicPort"], node_ip)
                            if isinstance(sock, str):
                                app_state += "FAILED " + sock + " "
                            else:
                                app_state += "OK "
                                sock.close()
                    if found_ports:
                         print(logmsg(this_node['ip'] + " " + status + " " + tier + " " + app_state))
        else:
            print(values)
    else:
        print(req)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == "--all":
            check_nodes("")
            sys.exit(0)
        if sys.argv[1].lower() == "--filter":
            if len(sys.argv) > 2:
                filter = sys.argv[2]
                check_nodes(filter)
                sys.exit(0)
        if sys.argv[1].lower() == "--check_app":
            if len(sys.argv) > 2:
                name = sys.argv[2]
                check_app(name)
                sys.exit(0)
    print("Incorrect arguments:")
    print(sys.argv[0], "--all    check all nodes for running applications to test")
    print(sys.argv[0], "--filter check nodes matching the supplied `filter` for running applications to test")
    print(sys.argv[0], "--app    test nodes running application 'app'")
    sys.exit(1)
