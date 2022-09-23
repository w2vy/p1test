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
import mysql.connector
import os

max_nodes = 0
num_nodes = 0
num_checked = 0
num_good = 0

def include(filename):
    if os.path.exists(filename): 
        os.execfile(filename)

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
    now = cur_time.strftime("%Y-%m-%d %H:%M:%S ")
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
        error = "Refused"
        sock.close()
        sock = None
    except TimeoutError:
        error = "TimeoutError"
        sock.close()
        sock = None
    except socket.error:
        error = "NoRoute"
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
def add_db(db, node, node_ip, nstatus, health, status):
    ADD_NODE_STATUS = ("INSERT INTO node_status (node_hash, node_ip, node_state, node_health, node_comment) VALUES ( %s, %s, %s, %s, %s)")
    ADD_NODE_VALUES = (str(node), node_ip, nstatus, health, status)
    if db is not None:
        cursorObject = db.cursor()
        cursorObject.execute(ADD_NODE_STATUS, ADD_NODE_VALUES)
        db.commit()
        #print("MYSQL", ADD_NODE_STATUS, ADD_NODE_VALUES)

def fix_db(db):
    '''Check all running instances and see if we can reach the app'''
    url = "https://api.runonflux.io/daemon/viewdeterministiczelnodelist/"
    req = requests.get(url)
    # Get the list of nodes where our app is deployed
    SET_HASH = "UPDATE `node_status` SET `node_hash`= %s WHERE `node_ip`= %s AND `node_hash` IS NULL"
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
            nodes = values["data"]
            updates = 0
            for this_node in nodes:
                sys.stdout.flush()
                cursorObject = db.cursor()
                cursorObject.execute(SET_HASH, (this_node["collateral"], this_node["ip"]))
                db.commit()
                updates = updates + cursorObject.rowcount
            print("Updated ", updates, " records")
    db.close()

def node_details(db, node):
    print(node)
    DETAILS = "SELECT * from `node_status` WHERE `node_hash` LIKE '" + node[2] + "' ORDER BY `node_status`.`time` ASC"
    #print(DETAILS)
    cur = db.cursor()
    cur.execute(DETAILS)
    list = cur.fetchall()
    for row in list:
        print(row[1].strftime("%m/%d/%Y, %H:%M:%S"), row[4], row[5], row[6])

def examine_db(db):
    '''Examine the db to find nodes that are failing'''
    SUMMARY = "SELECT count(*) as count, sum(`node_health`) as health,`node_hash`,`node_ip` FROM `node_status`" + \
        " WHERE 1 GROUP BY `node_hash` ORDER BY count(*)  DESC"
    cur = db.cursor()
    cur.execute(SUMMARY)
    nodes = cur.fetchall()
    summary = {}
    summary["Mixed"] = 0
    for node in nodes:
        count = int(node[0])
        health = int(str(node[1]))
        avg = health / count
        node_summary = {}
        if count < 8:
            node_summary["Young"] = 1
        else:
            if avg < 99.0:
                DETAILS = "SELECT * from `node_status` WHERE `node_hash` LIKE '" + node[2] + "' ORDER BY `node_status`.`time` ASC"
                cur = db.cursor()
                cur.execute(DETAILS)
                list = cur.fetchall()
                for row in list:
                    if row[5] not in node_summary:
                        node_summary[row[5]] = 0
                    node_summary[row[5]] = node_summary[row[5]] + 1
            else:
                node_summary["Perfect"] = 1
        if len(node_summary) == 1:
            for key in node_summary:
                if key not in summary:
                    summary[key] = 1
                else:
                    summary[key] = summary[key] + 1
        else:
            summary["Mixed"] = summary["Mixed"] + 1
    print(summary)
    db.close()

def check_nodes(filter, db):
    '''Check all running instances and see if we can reach the app'''
    global max_nodes, num_checked, num_good, num_nodes
    url = "https://api.runonflux.io/daemon/viewdeterministiczelnodelist/" + filter
    req = requests.get(url)
    # Get the list of nodes where our app is deployed
    if req.status_code == 200:
        values = json.loads(req.text)
        if values["status"] == "success":
            # json looks good and status correct, iterate through node list
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
                    add_db(db, this_node["collateral"], this_node["ip"], "noapiport", 0, "API Port unreachable")
                    continue
                status = data['status']
                if status == "CONFIRMED":
                    tier = data['tier']
                else:
                    tier = "none"
                data = get_flux(this_node['ip'], "flux/connectedpeers")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get connected peers"))
                    add_db(db, this_node["collateral"], this_node["ip"], "getpeersfailed", 10, tier + "API Port usable but request failed")
                    continue
                for peer in data:
                    failed = False
                    if non_routable_ip(peer):
                        print(logmsg(this_node["ip"] + " " + status + " " + tier + " non routable peer " + peer))
                        add_db(db, this_node["collateral"], this_node["ip"], "nonroutablepeer", 20, tier + " Found a peer with Private IP")
                        failed = True
                        break
                if failed:
                    continue
                data = get_flux(this_node['ip'], "flux/incomingconnections")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get incoming connection"))
                    add_db(db, this_node["collateral"], this_node["ip"], "incomingfailed", 21, tier + " API Port usable but request failed")
                    continue
                for peer in data:
                    failed = False
                    if non_routable_ip(peer):
                        print(logmsg(this_node["ip"] + " " + status + " " + tier + " non routable incoming " + peer))
                        add_db(db, this_node["collateral"], this_node["ip"], "nonroutableincoming", 22, tier + " Found incoming connection with Private IP")
                        failed = True
                        break
                if failed:
                    continue
                data = get_flux(this_node['ip'], "apps/listrunningapps")
                if data is None:
                    print(logmsg(this_node["ip"] + " " + status + " " + tier + " FAILED get running apps"))
                    add_db(db, this_node["collateral"], this_node["ip"], "nolistapps", 50, tier + " App list returned NONE - Error?")
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
                    # If this is the P1 app (or Gammonbot?) then wait for the Private Key (or rejected IP)
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
                                add_db(db, this_node["collateral"], this_node["ip"], status, 100, tier + " " + app["Names"][0] +" " +str(sport) + " Error: " + sock)
                            else:
                                app_state += "OK "
                                any_good = True
                                sock.close()
                                add_db(db, this_node["collateral"], this_node["ip"], status, 100, tier + " " + app["Names"][0] +" " +str(sport) + " OK")
                    if found_ports:
                        num_checked += 1
                        if not found_error:
                            num_good += 1
                        #print(logmsg(this_node['ip'] + " " + status + " " + tier + " " + app_state))
                        if not any_good:
                            print(logmsg(this_node['ip'] + " " + status + " " + tier + " All Ports " + str(nports) + " failed"))
                    else:
                        add_db(db, this_node["collateral"], this_node["ip"], status, 100, tier + " " + app["Names"][0])
            print("Summary: ", num_nodes, " found, ", num_checked, " nodes checked, ", num_good, " found with no issues")
            if db is not None:
                db.close()
        else:
            print(values)
    else:
        print(req)

def mysql_init(my_host, my_user, my_passwd, my_db):
    '''Check DB to see that it exists and create tables if needed'''
    NODE_STATUS_TABLE = '''CREATE TABLE `fluxdb`.`node_status` (
        `node_status_id` INT(11) NOT NULL AUTO_INCREMENT ,
        `time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ,
        `node_ip` VARCHAR(64) NOT NULL ,
        `node_health` TINYINT(4) NOT NULL,
        `node_state` VARCHAR(64) NOT NULL ,
        `node_comment` VARCHAR(255) NOT NULL,
        PRIMARY KEY (`node_status_id`)) ENGINE = InnoDB;'''
  
    dataBase = mysql.connector.connect(host = my_host, user = my_user, passwd = my_passwd, database = my_db)
    cursorObject = dataBase.cursor()
    cursorObject.execute("SHOW TABLES;")
    result = cursorObject.fetchall()
    if len(result) == 0: # Empty db create table(s)
        cursorObject.execute(NODE_STATUS_TABLE)
    cursorObject.close()
    return dataBase


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)

    if len(sys.argv) > 1:
        dataBase = None
        filter = None
        arg = 1
        if sys.argv[arg].lower() == "--mysql" and len(sys.argv)> arg+4:
            dataBase = mysql_init(sys.argv[arg+1], sys.argv[arg+2], sys.argv[arg+3], sys.argv[arg+4])
        arg = arg + 5
        if len(sys.argv) > arg and sys.argv[arg].lower() == "--examine":
            examine_db(dataBase)
            sys.exit(0)
        if len(sys.argv) > arg and sys.argv[arg].lower() == "--all":
            filter = ""
            arg = arg + 1
        if len(sys.argv) > arg and sys.argv[arg].lower() == "--filter":
            if len(sys.argv) > arg+1:
                filter = sys.argv[arg+1]
        if filter is not None:
            check_nodes(filter, dataBase)
            sys.exit(0)
        if len(sys.argv) > arg and sys.argv[arg].lower() == "--app":
            if len(sys.argv) > arg+1:
                name = sys.argv[arg+1]
                check_app(name)
                sys.exit(0)
    print("Incorrect arguments:")
    print(sys.argv[0], "--mysql host-ip-dns username passwd dbname - must be first if present")
    print(sys.argv[0], "--all    check all nodes for running applications to test")
    print(sys.argv[0], "--filter check nodes matching the supplied `filter` for running applications to test")
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
