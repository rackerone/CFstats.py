#/usr/bin/env python
# -*- coding: utf-8 -*-
#Copyright 2013 Aaron Smith
#Thanks to Bruce Stringer basic idea here.  I based this script on a small script he wrote to just check API calls
#against a 'max time' value.

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.


import subprocess
import sys
import datetime
import os
import time
import threading
import random
import json
import collections
from prettytable import PrettyTable
try:
    import pyrax
except ImportError as e:
    print '%s\n' % e
    print "Please install pyrax and try again!"
    sys.exit(1)

#===================================================================================================================
# EDIT THE GLOBAL VARIABLES BELOW AS NECESSARY FOR EACH TEST
#===================================================================================================================
#Set the time threshold.  Any API call taking longer than MAX_TIME will be considered a BAD TIME.  Floating point is acceptable
MAX_TIME = 0.3

#Set MAX_REPS to limit the number of tests to the assigned value.
MAX_REPS = 100

#Set Rackspace credentials
APIKEY = 'YOURAPIKEY'
USERNAME = 'YOURUSERNAME'

#Set the target region that contains your cloud file(s)
REGION = 'DFW'

#Set SNET to True if you are running this from a cloud server in the same region as your cloud files. [default = False]
SNET = False

#Set RANDOM to True if you want 10 randomly selected objects for testing.  If RANDOM is set to 'True' then you
#can safely disregard the CONTAINER and FILE variables.
RANDOM = False

#If RANDOM is set to 'False', you **MUST** set the FILE and CONTAINER variables.  If RANDOM is 'True', you can disregard
CONTAINER = 'YOURCONTAINER'
FILE = 'YOUROBJECT'

#=================================================########==================================================================
#=================================================########==================================================================
#DO NOT EDIT BELOW THIS LINE     DO NOT EDIT BELOW THIS LINE     DO NOT EDIT BELOW THIS LINE     DO NOT EDIT BELOW THIS LINE
#=================================================########==================================================================
#=================================================########==================================================================
#Initialize the STARTUP variable to the value of TRUE.  Set to false to stop the 'program_loading()' meter below.
STARTUP = True
#Print progress message to screen during app load.  I have to create a class here so I can utilize threading.
class program_loading(threading.Thread):
    """This will provide a progress meter that prints periods while loading.  Set 'STOP' or 'KILL' to True to stop the meter."""
    def run(self):
            global STARTUP
            #print '\rLoading....  ',
            sys.stdout.flush()
            try:
                i = 1
                while STARTUP == True:
                    symbol = '+'
                    sys.stdout.write('\rLoading application %s' % (symbol * i),)
                    sys.stdout.flush()
                    time.sleep(0.2)
                    i+=1
            except KeyboardInterrupt:
                STARTUP = False
                print '\rABORTING!!!'

#Create an instance of the 'program_loading' meter and start it.  This will be killed when testing begins.
#We are wrapping the entire program intialization with a try statement so that if anything crashes during 
#initialization it won't leave the 'loading meter' running with no way to break out.
try:
    #Starting program load meter
    pl = program_loading()
    pl.start()
    #Set up variables that will STOP or KILL the progress_bar_loading() meter that we will create later
    KILL = False
    STOP = False
    #We will use this to parse all available cloud files endpoints for this particular user
    IDENTITY_ENDPOINT = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
    # #Initialize the COUNTER variable and set to 0.
    COUNTER = 1
    #Initialize the ENDPOINT variable.  This will be assigned a value inside the main() function
    ENDPOINT = ''
    #Make that service net defaults to False if the value of SNET isn't specifically set to True
    if SNET != True:
        SNET = False

    #===================================================================================================================
    #ESTABLISH DATA BANKS TO HOLD INFOMRATION DURING SCRIPT LIFETIME
    #===================================================================================================================
    #Create list to hold our dictionaries.  This includes transaction ID, container, object, HTTP error code, and time.
    BAD_TRANSACTIONS = []
    #Errors returned by the python 'subprocess' module
    SUBPROCESS_ERRORS = []
    #Create a 'collections' object that we can use to keep track of HTTP error codes easily.
    HTTP_CODE_COLLECTION = []
    #Initialize a dict containing a random container from account as the key and a random object in that container as the value
    MY_OBJECT = {}
    #MY_ROW will container a list of table rows used for pretty table
    MY_ROW = []
    
    #Set up 'MY_ROW_LIST' to keep running tally of values for bad transactions.
    #TODO - NOTE this is not used at this time
    MY_ROW_LIST =[]

    #===================================================================================================================
    #SET UP PYRAX AND AUTH TO GET CURRENT TOKEN
    #===================================================================================================================
    ticks = 0
    max_ticks = 3
    try:
        pyrax.set_setting("identity_type", "rackspace")
        pyrax.set_default_region("DFW")
        pyrax.set_credentials(USERNAME, APIKEY)
        TOKEN = pyrax.identity.token
    except Exception as e:
        if ticks == max_ticks:
            print "\r\n\r%s\n" % e
            print "\rEXITING DUE TO ERROR DURING PYRAX AUTHENTICATION SETUP!"
            sys.exit(1)
        print "\rERROR!\n\r%s" % e
        print "\rSleeping 1 second and retrying..."
        time.sleep(1.0)
        ticks += 1

    #===================================================================================================================
    #SET UP CLASSES AND FUNCTIONS
    #===================================================================================================================
    class progress_bar_loading(threading.Thread):
        """This will provide a spinning progress meter.  Set 'STOP' or 'KILL' to True to stop the meter."""
        def run(self):
                global STOP
                global KILL
                sys.stdout.flush()
                try:
                    i = 0
                    while STOP != True:
                            print '\rLoading....  ',
                            if (i%4) == 0:
                                sys.stdout.write('\b/')
                            elif (i%4) == 1:
                                sys.stdout.write('\b-')
                            elif (i%4) == 2:
                                sys.stdout.write('\b\\')
                            elif (i%4) == 3:
                                sys.stdout.write('\b|')
                            sys.stdout.flush()
                            time.sleep(0.2)
                            i+=1
                    if KILL == True:
                        print '\rABORTING!!!'
                    else:
                        print "\r \n"
                except KeyboardInterrupt:
                    print '\rABORTING!!!'
                finally:
                    STOP = True

    def timestamp():
        """Create a timestamp in appropriate format"""
        ts = time.time()
        formatted_time = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        return formatted_time

    def get_endpoint(region=REGION, apikey=APIKEY, username=USERNAME, identity=IDENTITY_ENDPOINT, snet=SNET):
        """Parse services for cloud files URL.  Specifically, return the endpoint for the target 'region'"""
        if not (region and apikey and username and identity):
            raise AttributeError
        command = """curl -s %s -XPOST -d '{"auth":{"RAX-KSKEY:apiKeyCredentials" {"username":"%s", "apiKey":"%s"}}}' -H 'Content-Type: application/json'""" % (identity,username,apikey)
        try:
            #print "Attempting command\n%s" % command
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
            #return output
            #print "\bSubprocess has returned output."
        except subprocess.CalledProcessError as e:
            print e
            return None
        #Convert text string to json data
        output = json.loads(output)
        #Retrieve the service catalog for cloud files
        cfcatalog = output['access']['serviceCatalog'][1]['endpoints']
        endpoints = {}
        if snet:
            for url in cfcatalog:
                endpoints.update({url['region']:url['internalURL']})
        else:
            for url in cfcatalog:
                endpoints.update({url['region']:url['publicURL']})
        return endpoints[region]

    def random_object(region=REGION):
        """This function will return a single key:value pair representing a random container for the key and a random object
        within that container as the value.  Each iteration within our main() function will this resulting in a new key:value pair
        per iteration"""
        global MY_OBJECT
        MY_OBJECT = {}

        #Create connection to cloud files
        cfiles = pyrax.connect_to_cloudfiles(region)

        #Get a list of container Objects
        container_objs = cfiles.get_all_containers()

        #Initialize a list of containers.  It will hold only containers with 1 or more objects in it.  We will be unable to test
        #a container if it is empty.
        my_containers = []

        #Populate list 'my_containers' with containers that have an object count of more than 0
        for cont in container_objs:
            if int(cont.object_count) > 0:
                my_containers.append(cont.name)

        #Calculate the number of containers available for testing (containers with one or more object)
        num_containers = len(my_containers)

        #If no containers in REGION then print message and exit
        if num_containers == 0:
            print "\rOops!  There are no containers in the '%s' region.  Please choose a different region and try again" % REGION
            sys.exit()
        else:
            #print "\r---===> BEGINING RANDOM TESTS -- TOTAL # OF CONTAINER IN TEST BED [%s] <===---" % num_containers
            #Verify that at least one container has an object in it.
            random_container = random.sample(my_containers, 1)[0]
            print "\r----->Found random container [%s]" % random_container
            obj_names = cfiles.get_container_object_names(random_container)
            rand_object = random.sample(obj_names, 1)[0]
            print "\r----->Found random object [%s]" % rand_object
            # my_container = []
            # my_containers.append({random_container:rand_object})
            # MY_OBJECT = my_containers[0]
            # print 'my_containers', my_containers
            # print 'MY_OBJECT',MY_OBJECT
            rand = []
            rand.append({random_container:rand_object})
            print "this is rand ", rand
            print 'type of rand', type(rand)
            return rand
            

    def timed_curl_head(token=TOKEN, endpoint=ENDPOINT, container=CONTAINER, file=FILE, use_snet=SNET, region=REGION):
        """Curl an object and return header.  This call will be timed and if the call exceeds the MAX_TIME value
        it will log the transaction.  We consider anything taking longer than the MAX_TIME to be a BAD_TRANSACTION"""
        global COUNTER
        global BAD_TRANSACTIONS
        global SUBPROCESS_ERRORS
        global HTTP_CODE_COLLECTION
        if not (token and endpoint and container and file):
            raise AttributeError

        formatter = {
                'token': token,
                'endpoint': endpoint,
                'container': container,
                'file': file
                }

        command = 'time -p curl -s -I -H "X-Auth-Token: {token}" {endpoint}/{container}/{file}'.format(**formatter)
        try:
            #print "\rAttempting command\n%s" % command
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
            print "\rAPI call [%s] sent..." % COUNTER
        except subprocess.CalledProcessError as e:
            print '\r', e
            SUBPROCESS_ERRORS.append(e)
            return None
        cleaned_output = [output.strip().split('\n')][0]
        response_head = cleaned_output[0].strip().split(' ')
        response_code = response_head[1]
        success = response_code.startswith('2')
        #Compile list of all HTTP response codes
        HTTP_CODE_COLLECTION.append(response_code)
        if not success:
            print "\rHTTP Error %s returned by curl!" % response_code
        trans = ""
        time = ""
        tstamp = timestamp()
        for line in cleaned_output:
            if line.startswith('X-Trans-Id'):
                trans = line.strip('\r').split(': ')[1]
            elif line.startswith('real'):
                time = float(line.strip('\r').split(' ')[1])
        if time >= MAX_TIME:
            msg = "\rBAD TRANSACTION ID: %s\tHTTP RESPONSE CODE: %s\t\tTIME: %s" % (trans,response_code,time)
            print msg
            BAD_TRANSACTIONS.append({
                    'Container':container,
                    'Time Stamp':tstamp,
                    'Object Name':file,
                    'Transaction ID':trans,
                    'Response Code':response_code,
                    'Time':time,
                    'Number':(str(COUNTER) + '/100')
                    })
        else:
            print "Good Transaction!"

    #curl -o 100MBTESTDOWNLOAD -H"X-Auth-Token: fcabf04da6c045c399d296fc70785617" https://storage101.dfw1.clouddrive.com/v1/MossoCloudFS_adabd673-1859-48ba-8f91-951ff2331300/testcontainer/100MB.testfile
    def timed_curl_download(token=APIKEY, endpoint=ENDPOINT, container=CONTAINER, file=FILE, use_snet=SNET, region=REGION):
        if not (token and endpoint and container and file):
            raise AttributeError
        formatter = {
                'token': token,
                'endpoint': endpoint,
                'container': container,
                'file': file
                }
        command = 'time -p curl -o {file} -s -I -H "X-Auth-Token: {token}" {endpoint}/{container}/{file}'.format(**formatter)
        try:
            #print "Attempting command\n%s" % command
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
            #print "\bSubprocess has returned output."
        except subprocess.CalledProcessError as e:
            print e
            return None
        cleaned_output = [output.strip().split('\n')][0]
        print cleaned_output
        trans = ''
        time = ''

    def make_table(list_of_dicts):
        """Feed this function a list (of dictionaries) and it will create a PrettyTable with it."""
        #Import and Initialize the global variable MY_ROW_LIST.  Used by Counter() later
        global MY_ROW_LIST
        #Initialize the table and set the headers using the keys in this 
        table = PrettyTable(list_of_dicts[0].keys())
        #Left align the 'container' column
        table.align['Container'] = 'l'
        #Pad each cell with 1 space in every direction
        table.padding_width = 1
        #Populate the table with values from bad trancation dictionary
        for i in xrange(len(list_of_dicts)):
            MY_ROW = []
            for key,value in list_of_dicts[i].iteritems():
                MY_ROW.append(value)
                MY_ROW_LIST.append(value)
            table.add_row(MY_ROW)
        try:
            os.system('cls' if os.name=='nt' else 'clear')
        except Exception as e:
            #Simply passing if we get an error here because it is of no consequence.  We will print a couple
            # of newlines instead
            print "\n\n"
        table = table.get_string(sortby='Number',reversesort=False)
        print "============================== SUMMARY TABLE =============================="
        return table

    #===================================================================================================================
    # MAIN()
    #===================================================================================================================
    def main():
        try:
            os.system('cls' if os.name=='nt' else 'clear')
        except Exception as e:
            pass
        #print random_object()
        #Initialize and start the rotating progress meter
        pb = progress_bar_loading()
        pb.start()
        #Establish the endpoint we will use.  The 'get_endpoint' function automatically uses the REGION variable to get
        #the correct endpoint for that specific region
        global ENDPOINT
        ENDPOINT = get_endpoint()
        #Import and initialize the TOKEN, CONTAINER, RANDOM, and FILE variables
        global CONTAINER
        global TOKEN
        global FILE
        global RANDOM
        #Import and initialize COUNTER to control the number of loops.  COUNTER value is set to 0
        global COUNTER
        #Begin exicuting commands in repitition
        try:
            if RANDOM:
                while COUNTER <= MAX_REPS:
                    #for key,value in rand_obj_dict.iteritems():
                    print 'bad trandsaction', BAD_TRANSACTIONS
                    print '\rCOUNTER    ',COUNTER
                    print 'MAX',MAX_REPS
                    rand_obj_dict = random_object()
                    CONTAINER = rand_obj_dict.keys()[0]
                    FILE = rand_obj_dict.values()[0]
                    print "%s:%s", (CONTAINER,FILE)
                    timed_curl_head(TOKEN, ENDPOINT, CONTAINER, FILE)
                    COUNTER += 1
            else:
                while COUNTER <= MAX_REPS:
                    timed_curl_head(TOKEN, ENDPOINT, CONTAINER, FILE)
                    COUNTER += 1
                STOP = True
                print "\r"
        except Exception as e:
            print "Error encountered in main() function\n%s" % e
            KILL = True
            STOP = True
except KeyboardInterrupt:
    #Killing progress meters
    STARTUP = False
    KILL = True
    STOP = True
    print '\r'
    sys.exit()

#===================================================================================================================
#EXECUTION LOGIC
#===================================================================================================================
if __name__ == "__main__":
    try:
        #set STARTUP to False to stop the 'program_loading' progress meter.  This just runs during app initialization
        STARTUP = False
        #Running main()
        main()
        #Set STOP to True to cancel the 'progress_bar_loading' meter.  This one runs during curl calls.
        STOP = True
        #-------------->Set up our summary tables------------------------>
        if len(BAD_TRANSACTIONS) > 0:
            bad_trans_table = make_table(BAD_TRANSACTIONS)
            print bad_trans_table
            print "\n"
            Collection_data = dict(collections.Counter(HTTP_CODE_COLLECTION))
            print "____HTTP Response Codes____"
            for key,value in Collection_data.iteritems():
                resp = 'responses'
                if value == '1':
                    resp = 'response'
                print "%s's : %s %s" % (key,value,resp)
            print "\n"
            print "Total number of API calls: %d" % (COUNTER - 1)
            print "Number of API calls exceeding MAX_TIME: %d" % int(len(BAD_TRANSACTIONS))
            percentage = (int(len(BAD_TRANSACTIONS) * 100) / MAX_REPS)
            print "Percentage of API calls that exceed MAX_TIME: %.2f" % percentage + '%'
            print "Number of errors returned by cURL: %d" % int(len(SUBPROCESS_ERRORS))
            if SUBPROCESS_ERRORS:
                print "CURL ERRORS:"
                for error in SUBPROCESS_ERRORS:
                    print error
        else:
            print '\n\n'
            s = 'seconds'
            if MAX_TIME == 1:
                s = 'second'
            print "All transactions successlly completed in under %.1f %s" % (MAX_TIME,s)

            """TODO from here i need to create a pretty table using the collection data for response codes.  it works now 
            but just need to formulate the table headers and populate table.  I would like percentages added to reponse codes as well 
            also need to add 'total api calls', 'total errors', and 'percentage failure'

            ERROR 
            API call [27] sent...
            Good Transaction!
            Command 'time -p curl -s -I -H "X-Auth-Token: c6424d6c8fd845df8687d6de0bf6f36e" https://storage101.dfw1.clouddrive.com/v1/MossoCloudFS_adabd673-1859-48ba-8f91-951ff2331300/stream/Snowball.mp4' returned non-zero exit status 35
            API call [29] sent...
            Good Transaction!
            """

    except KeyboardInterrupt or EOFError:
        print "\rShutting down..."
        KILL = True
        STOP = True
        sys.exit()
