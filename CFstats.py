#!/usr/bin/env python
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
import logging
from prettytable import PrettyTable
try:
    import pyrax
except ImportError as e:
    print '%s\n' % e
    print "Please install pyrax with pip and try again!"
    sys.exit(1)
#==============================================================================
# EDIT THE GLOBAL VARIABLES BELOW AS NECESSARY FOR EACH TEST
#==============================================================================
#Set the time threshold.  Any API call taking longer than MAX_TIME will be
#considered a BAD TIME.  Floating point is acceptable
MAX_TIME = 0.2

#Set MAX_REPS to limit the number of tests to the assigned value.
MAX_REPS = 25

USERNAME = 'YOURUSERNAME'
APIKEY = 'YOURAPIKEY'

#Set the target region that contains your cloud file(s)
REGION = 'DFW'

#Set SNET to True if you are running this from a cloud server in the same region
#as your cloud files. [default = False]
SNET = False

#Set CDN to True if you would like to test response times from the CDN edge node
#closest to you
CDN = False

#Set RANDOM to True if you want 10 randomly selected objects for testing.
#If RANDOM is set to 'True' then you can safely disregard the CONTAINER and
#FILE variables.
RANDOM = False

#If RANDOM is set to 'False', you **MUST** set the FILE and CONTAINER variables.
#If RANDOM is 'True', you can disregard
CONTAINER = 'container_name'
FILE = 'file_object_name'

#=================================================########=====================
#=================================================########=====================
#DO NOT EDIT BELOW THIS LINE             DO NOT EDIT BELOW THIS LINE
#=================================================########=====================
#=================================================########=====================
#Initialize the STARTUP variable to the value of TRUE.  Set to false to stop
#the 'program_loading()' meter below.
STARTUP = True
#Print progress message to screen during app load.  I have to create a class
#here so I can utilize threading.
class program_loading(threading.Thread):
    """
    This will provide a progress meter that prints periods while loading.
    Set 'STOP' or 'KILL' to True to stop the meter.
    """
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
            except KeyboardInterrupt,Exception:
                STARTUP = False
                print '\rABORTING!!!'

#==============================================================================
#START THE 'program_loading()' METER AND BEGIN BUILD APP IN MEMORY
#==============================================================================
#Create an instance of the 'program_loading' meter and start it.  This will be
#killed when testing begins.  We are wrapping the entire program intialization
#with a try statement so that if anything crashes during initialization it won't
#leave the 'loading meter' running with no way to break out.
try:
    #Starting program load meter
    pl = program_loading()
    pl.start()
    #Set up variables that will STOP or KILL the progress_bar_loading() meter that
    #we will create later
    KILL = False
    STOP = False
    #We will use this to parse all available cloud files endpoints for this
    #particular user
    IDENTITY_ENDPOINT = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
    #Make sure that service net defaults to False if the value of SNET isn't
    #specifically set to True
    if SNET != True:
        SNET = False

    #==========================================================================
    #ESTABLISH DATA BANKS TO HOLD INFOMRATION DURING SCRIPT LIFETIME
    #==========================================================================
    #Create list to hold our dictionaries.  This includes transaction ID,
    #container, object, HTTP error code, and time.
    BAD_TRANSACTIONS = []
    #Errors returned by the python 'subprocess' module
    SUBPROCESS_ERRORS = []
    #Create a 'collections' object that we can use to keep track of HTTP error
    #codes easily.
    HTTP_CODE_COLLECTION = []
    #Initialize a dict containing a random container from account as the key
    #and a random object in that container as the value
    MY_OBJECT = {}
    #MY_ROW will contain a list of table rows used for pretty table
    MY_ROW = []
    #Set up 'MY_ROW_LIST' to keep running tally of values for bad transactions.
    #TODO - NOTE this is not used at this time
    MY_ROW_LIST = []
    #This will hold the rackspace service catalog.
    CATALOG = []
    # #Initialize the COUNTER variable and set to 1.
    COUNTER = 1
    #Initialize the ENDPOINT variable.  This will be assigned a value inside
    #the main() function
    ENDPOINT = ''

    #==========================================================================
    #SET UP PYRAX ENVIRONMENT
    #==========================================================================
    ticks = 0
    max_ticks = 3
    loop = True
    while loop:
        try:
            pyrax.set_setting("identity_type", "rackspace")
            pyrax.set_default_region(REGION)
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
        finally:
            loop = False
    #Rackspace service catalog
    CATALOG = pyrax.identity.services
    #Get customer account number
    DDI = int(pyrax.identity.tenant_id)
    try:
        #Create connection to cloud files
        cfiles = pyrax.connect_to_cloudfiles(REGION)
        #Get a list of container Objects
        CONTAINER_OBJS = cfiles.get_all_containers()
        #Get list CDN enabled containers
        CDN_CONTAINER_OBJS = []
        for cont in CONTAINER_OBJS:
            if cont.cdn_enabled:
                CDN_CONTAINER_OBJS.append(cont)
    except Exception as e:
        print e, '\nError during pyrax setup'

    #==============================================================================
    #SET UP LOGGING
    #==============================================================================
    #Log file that we will send to customer's cloud files account
    LOG_FILE = 'CFStats-%s-%d.log' % (USERNAME,DDI)
    #Initialize the file handle for our log file
    f_log = ''
    #Set up logging to file--->  remove the filemode ('w') to make the logs append to file rather than overwrite
    logging.basicConfig(level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s ==> %(message)s',
                datefmt='%m-%d-%Y %H:%M:%S',
                filename=LOG_FILE,
                filemode='w')
    #Define a 'console' Handler which writes to the console instead of a log file.
    #This will provide screen output IN ADDITION TO the logging to file.
    console = logging.StreamHandler()
    #Set console handler logging level to DEBUG for console output
    console.setLevel(logging.WARNING)
    #Set a format for the console output
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    #Tell the console handler to use the 'formatter'
    console.setFormatter(formatter)
    #Add the handler to the root logger.  We can add multiple handlers.  Notice
    #Add a handler to the root logger
    logging.getLogger('').addHandler(console)
    ##Now we can begin logging.  First we will log a message to the root logger
    #logging.info('This is my root logger - info.')
    #Create a name for a logger.  If we omitted this then the %(name) variable would be 'root', hence 'root' logger.
    cflogger = logging.getLogger('CFStats')
    #adapter = CustomAdapter(logger, {'connid': COUNTER})
    #Begin logging to console and file
    cflogger.info("**** Starting CFStats ****")
    if RANDOM:
        cflogger.info("Script is set to 'random' for testing")

    #==========================================================================
    #SET UP CLASSES AND FUNCTIONS
    #==========================================================================
    class progress_bar_loading(threading.Thread):
        """
        This will provide a spinning progress meter.  Set 'STOP' or 'KILL' to
        True to stop the meter.
        """
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

    def get_endpoint(catalog=CATALOG, region=REGION, snet=SNET, cdn=CDN):
        """
        Parse service catalog.  Specifically, return the endpoint for the
        target region
        """
        if not (catalog and region):
            raise AttributeError
        if cdn:
            catalog = catalog['object_cdn']['endpoints']
            snet = False
        else:
            catalog = catalog['object_store']['endpoints']
        #This will be our list of available endpoints based on our config
        endpoints = {}
        #If using service net, else public net...
        if snet:
            for key,value in catalog.iteritems():
                rgn = key
                val = value['internal_url']
                endpoints.update({rgn:val})
        else:
            for key,value in catalog.iteritems():
                rgn = key
                val = value['public_url']
                endpoints.update({rgn:val})
        return endpoints[region]

    def random_object(region=REGION, cdn=CDN, cdn_containers=CDN_CONTAINER_OBJS, all_containers=CONTAINER_OBJS):
        """
        This function will return a single key:value pair representing a random
        container for the key and a random object within that container as the
        value.  Each iteration within our main() function will this resulting
        in a new key:value pair per iteration
        """
        global MY_OBJECT
        #Initialize a list of containers.  It will hold only containers with 1
        #or more objects in it.  We will be unable to test a container if it
        #is empty.
        my_containers = []
        # Initialize a list of dicts containing cdn enabled containers to be pulled from 'cdn_containers'
        # my_cdn_container = {}
        #Populate list 'my_containers'/'my_cdn_containers' with containers that have an object count
        #of more than 0
        if cdn:
            for cont in cdn_containers:
                if cont.object_count > 0:
                    my_cdn_container = {}
                    my_cdn_container.update({'container':cont.name,'link':cont.cdn_uri})
                my_containers.append(my_cdn_container)
        else:
            for cont in all_containers:
                if int(cont.object_count) > 0:
                    temp_dict = {}
                    temp_dict.update({'container':cont.name})
                my_containers.append(temp_dict)
        if len(my_containers) == 0:
            print "\rOops!  There are no containers in the '%s' region.  Please choose a different region and try again" % REGION
            KILL = True
            STOP = True
            sys.exit()
        #random_container will be a dictionary
        random_container = random.sample(my_containers, 1)[0]
        print "\r----->Found random container [%s]" % random_container['container']
        obj_names = cfiles.get_container_object_names(random_container['container'])
        rand_object = random.sample(obj_names, 1)[0]
        print "\r----->Found random object [%s]" % rand_object
        if cdn:
            http_link = random_container['link']
            cdn_container = random_container['container']
            MY_OBJECT.update({'link':http_link, 'container':cdn_container, 'object':rand_object})
        else:
            MY_OBJECT.update({'container':random_container['container'], 'object':rand_object})
        return MY_OBJECT
        #return results[0]

    def truncate(string):
        """
        When printing the summary table we have to limit the length of container
        and object names to prevent the table from 'wrapping' preventing readibility
        """
        if len(string) > 50:
            string = ("...trunc... " + string[-40:])
            # start = (len(string) - 30)
            # string = ("..." + string[-int(start):])
        return string

    def timed_curl_head(token=TOKEN, endpoint=ENDPOINT, container=CONTAINER, file=FILE, region=REGION, cdn=CDN):
        """
        Curl an object and return header.  This call will be timed and if the
        call exceeds the MAX_TIME value it will log the transaction.  We consider
        anything taking longer than the MAX_TIME to be a BAD_TRANSACTION
        """
        global COUNTER
        global BAD_TRANSACTIONS
        global SUBPROCESS_ERRORS
        global HTTP_CODE_COLLECTION
        if not (token and endpoint and container and file):
            raise AttributeError
        if cdn:
            formatter = {
                    'endpoint': endpoint,
                    'file': file
                    }
            command = 'time -p curl -s -I {endpoint}/{file}'.format(**formatter)
        else:
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
            #Example:
            #Command 'time -p curl -s -I -H "X-Auth-Token: 4dd0a00b632840129ed47daa2644f718"
            #https://storage101.dfw1.clouddrive.com/v1/MossoCloudFS_adabd673-1859-48ba-8f91-951ff2331300/Hosted - DO NOT DELETE/sshpass-1.05.tar.gz'
            #returned non-zero exit status 2
            print '\r', exit
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
                #time = '%.1f' % time
        if time >= MAX_TIME:
            msg = "\rBAD TRANSACTION ID: %s\tHTTP RESPONSE CODE: %s\t\tTIME: %s" % (trans,response_code,time)
            print msg
            bad_log_message = "[%d] %s", (COUNTER, command)
            cflogger.info(command)
            BAD_TRANSACTIONS.append({
                    'Container':container,
                    'Time Stamp':tstamp,
                    'Object Name':file,
                    'Transaction ID':trans,
                    'Response Code':response_code,
                    'Time':str(time),
                    'Number':COUNTER
                    })
        else:
            print "Good Transaction!"

    def timed_curl_download(token=TOKEN, endpoint=ENDPOINT, container=CONTAINER, file=FILE, region=REGION):
        """
        Test a succession of downloads by timing each download.  Again, if the
        length of time taken exceeds the MAX_TIME variable, or if any other error
        causes it to fail, it will be considered a 'bad' download and reported
        accordingly.
        """
        if not (token and endpoint and container and file):
            raise AttributeError
        if cdn:
            formatter = {
                    'endpoint': endpoint,
                    'file': file
                    }
            command = 'time -p curl -s -I {endpoint}/{file}'.format(**formatter)
        else:
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
        """
        Feed this function a list (of dictionaries) and it will create a
        PrettyTable with it.
        """
        #Import and Initialize the global variable MY_ROW_LIST.  Used by
        #Counter() later
        global MY_ROW_LIST
        #Initialize the table and set the headers using the keys in this
        table = PrettyTable(list_of_dicts[0].keys())
        #Left align the 'container' column
        table.align['Container'] = 'l'
        table.align['Object Name'] = 'l'
        #Pad each cell with 1 space in every direction
        table.padding_width = 1
        #Populate the table with values from bad trancation dictionary
        for i in xrange(len(list_of_dicts)):
            MY_ROW = []
            for key,value in list_of_dicts[i].iteritems():
                if key == "Object Name":
                    value = truncate(value)
                MY_ROW.append(value)
                MY_ROW_LIST.append(value)
            table.add_row(MY_ROW)
        try:
            os.system('cls' if os.name=='nt' else 'clear')
        except Exception as e:
            #Simply passing if we get an error here because it is of no consequence.
            #We will print a couple of newlines instead
            print "\n\n"
        #table = table.get_string(sortby='Time',reversesort=False,start=0,end=1)
        table = table.get_string(sortby='Time',reversesort=True)
        print "\n\n"
        print "============================== SUMMARY TABLE =============================="
        return table

    #==========================================================================
    # MAIN()
    #==========================================================================
    def main(cdn=CDN):
        """
        Run this main function in '__main__' section
        """
        #Import and initialize the TOKEN, CONTAINER, RANDOM, and FILE variables
        global CONTAINER
        global TOKEN
        global FILE
        global RANDOM
        global MY_OBJECT
        #Import and initialize COUNTER to control the number of loops.  COUNTER
        #value is set to 1
        global COUNTER
        #Establish the endpoint we will use.  The 'get_endpoint' function
        #automatically uses the REGION variable to get the correct endpoint for
        #that specific region
        global ENDPOINT
        # if CDN:
        #     cdn_link = random_object()
        #     ENDPOINT = cdn_link['link']
        # else:
        #     ENDPOINT = get_endpoint()
        try:
            os.system('cls' if os.name=='nt' else 'clear')
        except Exception as e:
            pass
        #Initialize and start the rotating progress meter
        pb = progress_bar_loading()
        pb.start()
        #Begin executing commands in repitition
        try:
            if RANDOM:
                while COUNTER <= MAX_REPS:
                    MY_OBJECT = random_object()
                    CONTAINER = MY_OBJECT['container']
                    FILE = MY_OBJECT['object']
                    if cdn:
                        ENDPOINT = MY_OBJECT['link']
                    else:
                        ENDPOINT = get_endpoint()
                    timed_curl_head(TOKEN, ENDPOINT, CONTAINER, FILE)
                    COUNTER += 1
            else:
                while COUNTER <= MAX_REPS:
                    if cdn:
                        ENDPOINT = MY_OBJECT['link']
                    else:
                        ENDPOINT = get_endpoint()
                    timed_curl_head(TOKEN, ENDPOINT, CONTAINER, FILE)
                    COUNTER += 1
                STOP = True
                print "\r"
        except Exception as e:
            print "Error encountered in main() function\n%s" % e
            KILL = True
            STOP = True
            STARTUP = False
except KeyboardInterrupt, Exception:
    #Killing progress meters
    print "ABORTING!"
    print "Killing progress meters"
    STARTUP = False
    KILL = True
    STOP = True
    print '\r'
    sys.exit()

#==============================================================================
#EXECUTION LOGIC
#==============================================================================
if __name__ == "__main__":
    try:
        #set STARTUP to False to stop the 'program_loading' progress meter.
        #This just runs during app initialization
        STARTUP = False
        #Running main()
        main()
        #Set STOP to True to cancel the 'progress_bar_loading' meter.  This one
        #runs during curl calls.
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
            print "____STATS FOR THIS RUN____"
            net_reps = ((COUNTER -1) - len(SUBPROCESS_ERRORS))
            print "Total number of successful API calls: %d" % net_reps
            print "Number of API calls exceeding MAX_TIME: %d" % len(BAD_TRANSACTIONS)
            percentage = (len(BAD_TRANSACTIONS) * 100 / net_reps)
            print "Percentage of API calls that exceed MAX_TIME: %.1f" % percentage + '%'
            print "Number of errors returned by cURL: %d" % len(SUBPROCESS_ERRORS)
            print '\n'
            if SUBPROCESS_ERRORS:
                print "____CURL ERRORS____"
                for error in SUBPROCESS_ERRORS:
                    print "%s" % error
            print '\n\n'
        else:
            print '\n\n'
            s = 'seconds'
            if MAX_TIME == 1:
                s = 'second'
            print "All transactions successlly completed in under %.1f %s" % (MAX_TIME,s)

            """    TODO
            Add support for windows....do not rely on 'curl' or 'time'.  need to find python library to time functions.

            Need to fix table formatting.  If object names are too long it causes a word-wrap that makes it difficult to
            read in a terminal windows.  --DONE  12/10/2013


            Sometimes curl will error and return the following output
            "Use exit() or Ctrl-D (i.e. EOF) to exit"
            This error will add the following to the SUBPROCESS_ERRORS list
            "returned non-zero exit status 35"
                A problem occurred somewhere in the SSL/TLS handshake.
                You really want the error buffer and read the message
                there as it pinpoints the problem slightly more. Could
                be certificates (file formats, paths, permissions),
                passwords, and others.
            AND
            "returned non-zero exit status 2"
                Very early initialization code failed. This is likely to be
                an internal error or problem, or a resource problem where
                something fundamental couldn't get done at init time.
            AND
            "returned non-zero exit status 56"
                Failure with receiving network data.

            This next sync with git will contain:
            updated code to be more efficient
            added CDN support
            cleaned up extra code

            EXAMPLE OUTPUT ==>
            ============================== SUMMARY TABLE ==============================
            +---------------+--------------+----------------------------------------+---------------------+--------+------+---------------+
            | Container     | Object Name  |             Transaction ID             |      Time Stamp     | Number | Time | Response Code |
            +---------------+--------------+----------------------------------------+---------------------+--------+------+---------------+
            | ord_container | Snowball.mp4 | tx0a623922fd4e415998c9b-0052a8b200dfw1 | 2013-12-11 12:42:08 |   1    | 0.6  |      404      |
            | ord_container | Snowball.mp4 | txa60d910a7345450eab39e-0052a8b203dfw1 | 2013-12-11 12:42:11 |   15   | 0.29 |      404      |
            | ord_container | Snowball.mp4 | tx9266fe843fab4c71ab4bb-0052a8b202dfw1 | 2013-12-11 12:42:10 |   11   | 0.29 |      404      |
            +---------------+--------------+----------------------------------------+---------------------+--------+------+---------------+


            ____HTTP Response Codes____
            404's : 25 responses


            ____STATS FOR THIS RUN____
            Total number of successful API calls: 25
            Number of API calls exceeding MAX_TIME: 3
            Percentage of API calls that exceed MAX_TIME: 12.0%
            Number of errors returned by cURL: 0


            random_object() output when CDN = False:
            {'container': 'testcontainer', 'object': 'test_object_04042013.txt'}

            random_object() output when CDN = True:
            {'link': 'http://a4b9ce250ff7760633d4-faf4433dc2bfd7c8cc69e68c89e8dc6c.r28.cf1.rackcdn.com',
             'object': 'videotest.html'}

            """

    except KeyboardInterrupt or EOFError:
        print "\rShutting down..."
        KILL = True
        STOP = True
        sys.exit()
