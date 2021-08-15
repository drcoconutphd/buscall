import json, urllib.request
import requests
from sys import exit, argv
from flask import Flask, request, jsonify, render_template
from datetime import datetime
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
#app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["DEBUG"] = True

if len(argv) != 2:
    print("missing command-line argument")
    exit(1)
    
accountkey = argv[1]

#url link settings
headers = {'AccountKey': accountkey, 'accept': 'application/json'}
arrival_url = "http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2"
stops_url = "http://datamall2.mytransport.sg/ltaodataservice/BusStops"
routes_url = 'http://datamall2.mytransport.sg/ltaodataservice/BusRoutes'
    
@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')


@app.route('/enquirestops', methods=['GET', 'POST'])
def enquirestops():
    if request.method == 'POST':
        
        #setting query parameters
        serviceno = request.form.get('serviceno')
        busstopcode = request.form.get('busstopcode')
        arrival_params = {'BusStopCode': busstopcode, 'ServiceNo': serviceno}
        
        #querying arrrival results from arrival API
        response = requests.get(arrival_url, headers=headers, params=arrival_params)
        if response.status_code != 200:
            message = f"error {response.status_code}"
            return render_template('error.html', message=message)
        businfo = response.json()
        if not businfo['Services']:
            message = f"bus stop code {busstopcode} does not exist OR service number {serviceno} is not found at bus stop code {busstopcode}"
            return render_template('error.html', message=message)
        services = businfo['Services']
        
        #querying bus stop details
        i = 0
        roadname = ''
        while not roadname:
            allstops = requests.get(stops_url, headers=headers, params={'$skip': i})
            stops = allstops.json()['value']        #a list of 500 entries
            for stop in stops:
                if stop['BusStopCode'] == str(busstopcode):
                    roadname = stop['RoadName']
                    description = stop['Description']
                    break
            i += 500
        if not roadname:
            message = 'cannot find bus stop details'
            return render_template('error.html', message=message)
        
        #time settings
        now = datetime.now().time()
        search_min = int(now.strftime("%M"))
        
        buses = {}
        for service in services:
            buses[service['ServiceNo']] = []        # = dict bus
            for i in ['NextBus', 'NextBus2', 'NextBus3']:
                bus = buses[service['ServiceNo']]
                crowd = service[i]['Load']
                deck = service[i]['Type']
                wheelchair = service[i]['Feature']
                if service[i]['EstimatedArrival'][14:16]:
                    diff = int(service[i]['EstimatedArrival'][14:16]) - search_min
                    if diff == 0:
                        time = 'ARRIVING'
                    elif diff == (-1 or -2 or 59 or 58):
                        time = 'LEAVING'
                    elif diff < 0:
                        time = str(diff + 60) + ' min'
                    else:
                        time = str(diff) + ' min'
                else:
                    time = ''
                bus.append([crowd, deck, time, wheelchair])

        return render_template('stopsresults.html', buses=buses, roadname=roadname, description=description, busstopcode=busstopcode)
    else:
        return render_template('enquirestops.html')

@app.route('/enquireservices', methods=['GET', 'POST'])
def enquireservices():
    if request.method == 'POST':
        serviceno = request.form.get('serviceno')
        if not serviceno[0] in ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'c', 'C', 'n', 'N']:
            message = 'invalid bus service number'
            return render_template('error.html', message=message)
        
        #speeding up the search via indexing, since total dict size is 26177
        searchdict = [[1, 0],
              [2, 9500],
              [3, 11500],
              [4, 13500],
              [5, 14500],
              [6, 16000],
              [7, 18000],
              [8, 19500],
              [9, 22000],
              [0, 25500]
             ]
        if serviceno[0] in ['c', 'C', 'n', 'N']:
            i = 25500
            limit = 26500
        else:
            for pair in searchdict:
                if str(pair[0]) == serviceno[0]:
                    i = pair[1]
                    limit = 500 + searchdict[pair[0]][1]
                    break
        
        #curating list of stops
        stops = []
        searching = True     
        while searching == True:
            if i == limit:
                message = 'invalid bus service'
                return render_template('error.html', message=message)
            response = requests.get(routes_url, headers=headers, params={'$skip': i})
            services = response.json()['value']
            if stops == []:
                for service in services:
                    if (service['ServiceNo'] == serviceno.upper() or service['ServiceNo'] == serviceno.lower()) and service['Direction'] == 1:
                        stops.append([service['BusStopCode']])
                        printservice = service['ServiceNo']
                    else:
                        if not stops == []:
                            searching = False
                i += 500
            else:
                for service in services:
                    if (service['ServiceNo'] == serviceno.upper() or service['ServiceNo'] == serviceno.lower()) and service['Direction'] == 1:
                        stops.append([service['BusStopCode']])
                    else:
                        searching = False
        
        #determining bus service type
        if stops.count(stops[0]) == 2:
            trip = 'LOOP'
        else:
            trip = 'TRUNK'
        status = ''
        if printservice[0] == 'C':
            status = ', Chinatown Express'
        elif printservice in ['160', '170',	'170X', '950']:
            status = ', Cross Border Service'
        elif 'NR' in printservice:
            status = ', Night Rider Service'
        elif ('e' or 'E') in printservice:
            status = ', Express Service'
        elif printservice in ['502', '502A', '518', '518A', '506', '513', '188R', '963R']:
            status = ', Express Service'
        elif printservice[-1].isdigit():
            if int(printservice) in range(651, 673):
                status = ', City Express Service'
        servicetype = f"{trip}{status}"
            
        
        #searching info for all stops
        a = 0
        filled = 0
        while not filled == len(stops):
            response = requests.get(stops_url, headers=headers, params={'$skip': a})
            allstops = response.json()['value']
            for allstop in allstops:
                for k in stops:
                    if k[0] == allstop['BusStopCode']:
                        k.append(allstop['RoadName'])
                        k.append(allstop['Description'])
                        filled += 1
            a += 500
        return render_template('servicesresults.html', stops=stops, serviceno=printservice, servicetype=servicetype)
    else:
        return render_template('enquireservices.html')


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    message = 'page not found'
    return render_template('error.html', message=message)
    
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
    
app.run()