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
import os
import pyrax
import time
import threading
import random
import json
import collections
from prettytable import PrettyTable

#===================================================================================================================
# EDIT THE GLOBAL VARIABLES BELOW AS NECESSARY FOR EACH TEST
#===================================================================================================================
#Set the time threshold.  Any API call taking longer than MAX_TIME will be considered a BAD TIME.  Floating point is acceptable
MAX_TIME = 3.0

#Set MAX_REPS to limit the number of tests to the assigned value.  If set to '-1' it will go forever until manually killed
#or stopped.  The default value is 100 (100 seconds)
MAX_REPS = 15


APIKEY = ''
USERNAME = ''
REGION = 'DFW'

#Set SNET to True if you are running this from a cloud server in the same region as your cloud files. [default = False]
SNET = False

#Set RANDOM to True if you want 10 randomly selected objects for testing.  If RANDOM is set to 'True' then you
#can safely disregard the CONTAINER and FILE variables.
#.
#RANDOM = True
RANDOM = False

#If RANDOM is set to 'False', you **MUST** set the FILE and CONTAINER variables.  If RANDOM is 'True', you can disregard
CONTAINER = ''
FILE = ''

#=================================================########==================================================================
#=================================================########==================================================================
#DO NOT EDIT BELOW THIS LINE     DO NOT EDIT BELOW THIS LINE     DO NOT EDIT BELOW THIS LINE     DO NOT EDIT BELOW THIS LINE
#=================================================########==================================================================
#=================================================########==================================================================

#---------------Begin program loading meter
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


#Create an instance of the 'program_loading' meter and start it
# try:
#     pl = program_loading()
#     pl.start()
# except KeyboardInterrupt:
#     STARTUP = False
#     pl.exit()
#     sys.exit()
try:
    pl = program_loading()
    pl.start()

    #---------------End program loading meter

    #Set up variables that will STOP or KILL the progress_bar_loading() meter that we will create later
    KILL = False
    STOP = False
    #We will use this to parse all available cloud files endpoints for this particular user
    IDENTITY_ENDPOINT = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
    # #Initialize the COUNTER variable and set to 0.
    COUNTER = 0
    #Initialize the ENDPOINT variable.  This will be assigned a value inside the main() function
    ENDPOINT = ''

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

    #Set up 'my_row_list' to keep running tally of values
    my_row_list =[]

    #===================================================================================================================
    #SET UP PYRAX AND AUTH TO GET CURRENT TOKEN
    #===================================================================================================================
    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_default_region("DFW")
    pyrax.set_credentials(USERNAME, APIKEY)
    TOKEN = pyrax.identity.token

    #===================================================================================================================
    #SET UP CLASSES AND FUNCTIONS
    #===================================================================================================================
    class progress_bar_loading(threading.Thread):
        """This will provide a spinning progress meter.  Set 'STOP' or 'KILL' to True to stop the meter."""
        def run(self):
                global STOP
                global KILL
                #print '\rLoading....  ',
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
            yield rand
            return
            #yield my_random_cont_obj
            # working_set = {}
            # for key,value in MY_OBJECT.iteritems():
            #     working_set.update({key:value})
            # return working_set

    #TODO test service net and/or regular
    def timed_curl_head(token=TOKEN, endpoint=ENDPOINT, container=CONTAINER, file=FILE, use_snet=SNET, region=REGION):
        # pb = progress_bar_loading()
        # pb.start()

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
            print "\rAPI call [%s] sent..." % (COUNTER + 1)
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
            #return response_head.strip()
        #return cleaned_output
        trans = ""
        time = ""
        for line in cleaned_output:
            if line.startswith('X-Trans-Id'):
                trans = line.strip('\r').split(': ')[1]
            elif line.startswith('real'):
                time = float(line.strip('\r').split(' ')[1])

        if time >= MAX_TIME:
            msg = "\rBAD TRANSACTION ID: %s\tHTTP RESPONSE CODE: %s\t\tTIME: %s" % (trans,response_code,time)
            print msg
            BAD_TRANSACTIONS.append({'Container':container, 'Object Name':file, 'Transaction ID':trans, 'Response Code':response_code, 'Time':time})
            # BAD_TRANSIT_IDS.append(trans)
            # TIME_LIST.append(time)
            #print BAD_TRANSACTIONS
        else:
            print "Good Transaction!"
        # yield BAD_TRANSACTIONS

        # if (BAD_TRANSIT_IDS and TIME_LIST):
        #     print TIME_LIST


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
        #global MY_ROW

        # #Here wa will create an instance of the rand_obj_dict just so we can access the keys from multipl locations
        # rand_obj_keys = rand_obj_dict.iteritems():

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
                    print "just printed container and file"
                    timed_curl_head(TOKEN, ENDPOINT, CONTAINER, FILE)
                    COUNTER += 1
            else:
                while COUNTER <= MAX_REPS:
                    timed_curl_head(TOKEN, ENDPOINT, CONTAINER, FILE)
                    COUNTER += 1
                STOP = True
                print "\r"
                return
        except Exception:
            #print '\r%s\n\n' % e
            KILL = True
        finally:
            STOP = True
except KeyboardInterrupt:
    STARTUP = False
    print '\r'
    sys.exit()
#===================================================================================================================
#EXECUTION LOGIC
#===================================================================================================================
if __name__ == "__main__":
    try:
        #set STARTUP to False to stop the 'program_loading' progress meter
        STARTUP = False
        #Run the main() function
        #global BAD_TRANSACTIONS
        main()
        #Set STOP to True to cancel the 'progress_bar_loading' meter
        STOP = True
        #-------------->Set up our summary tables------------------------>
        if len(BAD_TRANSACTIONS) > 0:
            #Initialize a table and set the headers
            Bad_Trans_Table = PrettyTable(BAD_TRANSACTIONS[0].keys())
            #Left align the container column
            Bad_Trans_Table.align['Container'] = 'l'
            #Pad each cell with 1 space in every direction
            Bad_Trans_Table.padding_width = 1
            #Populate the table
            for i in xrange(len(BAD_TRANSACTIONS)):
                MY_ROW = []
                for key,value in BAD_TRANSACTIONS[i].iteritems():
                    MY_ROW.append(value)
                Bad_Trans_Table.add_row(MY_ROW)

            try:
                os.system('cls' if os.name=='nt' else 'clear')
            except Exception as e:
                print "\n\n"

            print "--==* SUMMARY TABLE *==--"
            print Bad_Trans_Table.get_string(sortby='Time',reversesort=True)

            for i in xrange(len(BAD_TRANSACTIONS)):
                MY_ROW = []
                for key,value in BAD_TRANSACTIONS[i].iteritems():
                    MY_ROW.append(value)
                    my_row_list.append(value)
            #print "MY_ROW; %s" % MY_ROW
            #print MY_ROW
            print "\n"
            #print "attempting collection data..."
            Collection_data = collections.Counter(HTTP_CODE_COLLECTION)

            # Collection_data = collections.Counter(my_row_list)
            # # for i in xrange(len(BAD_TRANSACTIONS)):
            # #     for key,value in BAD_TRANSACTIONS[i].iteritems():
            # #         Collection_data.append(value)
            # # Collection_table = PrettyTable(Collection_data.keys())
            # # Collection_table.align['container'] = 'l'
            # # Collection_table.padding_width = 1
            # # Collection_table.add_row(Collection_data)
            # # print Collection_table
            # for k,v in Collection_data.iteritems():
            #     print "%s : %s" % (k,v)
            print Collection_data
            print ""
            print ""
            percentage = (int(len(BAD_TRANSACTIONS) * 100) / MAX_REPS)
            print "Percentage of bad API calls that exceed MAX_TIME: %s" % percentage + '%'
        else:
            print '\n\n'
            print "All transactions successlly completed faster than the MAX_TIME setting"


            """TODO from here i need to create a pretty table using the collection data for response codes.  it works now 
            but just need to formulate the table headers and populate table.  I would like percentages added to reponse codes as well 
            also need to add 'total api calls', 'total errors', and 'percentage failure'
            """


    except KeyboardInterrupt or EOFError:
        print "\rShutting down..."
        KILL = True
        STOP = True
        sys.exit()