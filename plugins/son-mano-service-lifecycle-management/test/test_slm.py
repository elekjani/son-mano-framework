"""
Copyright (c) 2015 SONATA-NFV
ALL RIGHTS RESERVED.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
Neither the name of the SONATA-NFV [, ANY ADDITIONAL AFFILIATION]
nor the names of its contributors may be used to endorse or promote
products derived from this software without specific prior written
permission.
This work has been performed in the framework of the SONATA project,
funded by the European Commission under Grant number 671517 through
the Horizon 2020 and 5G-PPP programmes. The authors would like to
acknowledge the contributions of their colleagues of the SONATA
partner consortium (www.sonata-nfv.eu).
"""

import unittest
import time
import json
import yaml
import threading
import logging
import uuid
import son_mano_slm.slm_helpers as tools

from unittest import mock
from multiprocessing import Process
from son_mano_slm.slm import ServiceLifecycleManager
from sonmanobase.messaging import ManoBrokerRequestResponseConnection

logging.basicConfig(level=logging.INFO)
logging.getLogger('amqp-storm').setLevel(logging.INFO)
LOG = logging.getLogger("son-mano-plugins:slm_test")
logging.getLogger("son-mano-base:messaging").setLevel(logging.INFO)
logging.getLogger("son-mano-base:plugin").setLevel(logging.INFO)
LOG.setLevel(logging.INFO)


class testSlmRegistrationAndHeartbeat(unittest.TestCase):
    """
    Tests the registration process of the SLM to the broker
    and the plugin manager, and the heartbeat process.
    """

    def setUp(self):
        #a new SLM in another process for each test
        self.slm_proc = Process(target=ServiceLifecycleManager)
        self.slm_proc.daemon = True
        #make a new connection with the broker before each test
        self.manoconn = ManoBrokerRequestResponseConnection('son-plugin.SonPluginManager')

        #Some threading events that can be used during the tests
        self.wait_for_event = threading.Event()
        self.wait_for_event.clear()

        #The uuid that can be assigned to the plugin
        self.uuid = '1'

    def tearDown(self):
        #Killing the slm
        if self.slm_proc is not None:
            self.slm_proc.terminate()
        del self.slm_proc

        #Killing the connection with the broker
        try:
            self.manoconn.stop_connection()
        except Exception as e:
            LOG.exception("Stop connection exception.")

        #Clearing the threading helpers
        del self.wait_for_event

    #Method that terminates the timer that waits for an event
    def eventFinished(self):
        self.wait_for_event.set()

    #Method that starts a timer, waiting for an event
    def waitForEvent(self, timeout=5, msg="Event timed out."):
        if not self.wait_for_event.wait(timeout):
            self.assertEqual(True, False, msg=msg)

    def testSlmHeartbeat(self):
        """
        TEST: This test verifies whether the SLM sends out a heartbeat
        as intended, once it is registered and whether this heartbeat
        message is correctly formatted.
        """

        def on_registration_trigger(ch, method, properties, message):
            """
            When the registration request from the plugin is received,
            this method replies as if it were the plugin manager
            """
            self.eventFinished()
            return json.dumps({'status': 'OK', 'uuid': self.uuid})

        def on_heartbeat_receive(ch, method, properties, message):
            """
            When the heartbeat message is received, this
            method checks if it is formatted correctly
            """
            msg = json.loads(str(message))
            #CHECK: The message should be a dictionary.
            self.assertTrue(isinstance(msg, dict), msg="Message is not a dictionary.")
            #CHECK: The dictionary should have a key 'uuid'.
            self.assertTrue("uuid" in msg.keys(), msg="uuid is not a key.")
            #CHECK: The value of 'uuid' should be a string.
            self.assertTrue(isinstance(msg["uuid"], str), msg="uuid is not a string.")
            #CHECK: The uuid in the message should be the same as the assigned uuid.
            self.assertEqual(self.uuid, msg["uuid"], msg="uuid not correct.")
            #CHECK: The dictionary should have a key 'state'.
            self.assertTrue("state" in msg.keys(), msg="state is not a key.")
            #CHECK: The value of 'state' should be a 'READY', 'RUNNING', 'PAUSED' or 'FAILED'.
            self.assertTrue(msg["state"] in ["READY", "RUNNING", "PAUSED", "FAILED"], msg="Not a valid state.")

            #Stop the wait
            self.eventFinished()

        #STEP1: subscribe to the correct topics
        self.manoconn.register_async_endpoint(on_registration_trigger, 'platform.management.plugin.register')
        self.manoconn.subscribe(on_heartbeat_receive, 'platform.management.plugin.' + self.uuid + '.heartbeat')

        #STEP2: Start the SLM
        self.slm_proc.start()

        #STEP3: Wait until the registration request has been answered
        self.waitForEvent(msg="No registration request received")

        self.wait_for_event.clear()

        #STEP4: Wait until the heartbeat message is received.

    def testSlmRegistration(self):
        """
        TEST: This test verifies whether the SLM is sending out a message,
        and whether it contains all the needed info on the
        platform.management.plugin.register topic to register to the plugin
        manager.
        """

        #STEP3a: When receiving the message, we need to check whether all fields present. TODO: check properties
        def on_register_receive(ch, method, properties, message):

            msg = json.loads(str(message))
            #CHECK: The message should be a dictionary.
            self.assertTrue(isinstance(msg, dict), msg='message is not a dictionary')
            #CHECK: The dictionary should have a key 'name'.
            self.assertIn('name', msg.keys(), msg='No name provided in message.')
            if isinstance(msg['name'], str):
                #CHECK: The value of 'name' should not be an empty string.
                self.assertTrue(len(msg['name']) > 0, msg='empty name provided.')
            else:
                #CHECK: The value of 'name' should be a string
                self.assertEqual(True, False, msg='name is not a string')
            #CHECK: The dictionary should have a key 'version'.
            self.assertIn('version', msg.keys(), msg='No version provided in message.')
            if isinstance(msg['version'], str):
                #CHECK: The value of 'version' should not be an empty string.
                self.assertTrue(len(msg['version']) > 0, msg='empty version provided.')
            else:
                #CHECK: The value of 'version' should be a string
                self.assertEqual(True, False, msg='version is not a string')
            #CHECK: The dictionary should have a key 'description'
            self.assertIn('description', msg.keys(), msg='No description provided in message.')
            if isinstance(msg['description'], str):
                #CHECK: The value of 'description' should not be an empty string.
                self.assertTrue(len(msg['description']) > 0, msg='empty description provided.')
            else:
                #CHECK: The value of 'description' should be a string
                self.assertEqual(True, False, msg='description is not a string')

            # stop waiting
            self.eventFinished()

        #STEP1: Listen to the platform.management.plugin.register topic
        self.manoconn.subscribe(on_register_receive, 'platform.management.plugin.register')

        #STEP2: Start the SLM
        self.slm_proc.start()

        #STEP3b: When not receiving the message, the test failed 
        self.waitForEvent(timeout=5, msg="message not received.")


#A mockup function that will be used to mock http POST responses.
def mocked_post_requests(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, json_code):
            self.json_data = json_data
            self.status_code = status_code

    print('#################################################')
    print('In the mock')
    return MockResponse('failed', 422)


class testSlmFunctionality(unittest.TestCase):
    """
    Tests the tasks that the SLM should perform in the service
    life cycle of the network services.
    """

    slm_proc    = None
    manoconn_pm = None
    uuid        = '1'
    corr_id     = '1ba347d6-6210-4de7-9ca3-a383e50d0330'

########################
#SETUP
########################
#    @classmethod
#    def setUpClass(cls):
#        """
#        Starts the SLM instance and takes care if its registration.
#        """
#        def on_register_trigger(ch, method, properties, message):
#            return json.dumps({'status':'OK','uuid':cls.uuid})

#        #Some threading events that can be used during the tests
#        cls.wait_for_first_event = threading.Event()
#        cls.wait_for_first_event.clear()

#        cls.wait_for_second_event = threading.Event()
#        cls.wait_for_second_event.clear()

        #Deploy SLM and a connection to the broker
#        cls.slm_proc = Process(target=ServiceLifecycleManager)
#        cls.slm_proc.daemon = True
#        cls.manoconn_pm = ManoBrokerRequestResponseConnection('Son-plugin.SonPluginManager')
#        cls.manoconn_pm.subscribe(on_register_trigger,'platform.management.plugin.register')
#        cls.slm_proc.start()
        #wait until registration process finishes
#        if not cls.wait_for_first_event.wait(timeout=5):
#            pass

    @classmethod
    def tearDownClass(cls):
        if cls.slm_proc is not None:
            cls.slm_proc.terminate()
            del cls.slm_proc
#        cls.manoconn_pm.stop_connection()

    def setUp(self):
        def on_register_trigger(ch, method, properties, message):
            return json.dumps({'status': 'OK', 'uuid': self.uuid})

        #Generate a new corr_id for every test
        self.corr_id = str(uuid.uuid4())

        #Some threading events that can be used during the tests
        self.wait_for_first_event = threading.Event()
        self.wait_for_first_event.clear()

        self.wait_for_second_event = threading.Event()
        self.wait_for_second_event.clear()

        #Deploy SLM and a connection to the broker
        self.slm_proc = Process(target=ServiceLifecycleManager)
        self.slm_proc.daemon = True
        self.manoconn_pm = ManoBrokerRequestResponseConnection('son-plugin.SonPluginManager')
        self.manoconn_pm.subscribe(on_register_trigger, 'platform.management.plugin.register')
        self.slm_proc.start()
        #wait until registration process finishes
        if not self.wait_for_first_event.wait(timeout=5):
            pass

        #We make a spy connection to listen to the different topics on the broker
        self.manoconn_spy = ManoBrokerRequestResponseConnection('son-plugin.SonSpy')
        #we need a connection to simulate messages from the gatekeeper
        self.manoconn_gk = ManoBrokerRequestResponseConnection('son-plugin.SonGateKeeper')
        #we need a connection to simulate messages from the infrastructure adaptor
        self.manoconn_ia = ManoBrokerRequestResponseConnection('son-plugin.SonInfrastructureAdapter')

    def tearDown(self):
        try:
            self.manoconn_spy.stop_connection()
            self.manoconn_gk.stop_connection()
            self.manoconn_ia.stop_connection()
        except Exception as e:
            LOG.exception("Stop connection exception.")

########################
#GENERAL
########################
    def createGkNewServiceRequestMessage(self, correctlyFormatted=True):
        """
        This method helps creating messages for the service request packets.
        If it needs to be wrongly formatted, the nsd part of the request is
        removed.
        """

        path_descriptors = '/plugins/son-mano-service-lifecycle-management/test/test_descriptors/'

        nsd_descriptor   = open(path_descriptors + 'sonata-demo.yml', 'r')
        vnfd1_descriptor = open(path_descriptors + 'firewall-vnfd.yml', 'r')
        vnfd2_descriptor = open(path_descriptors + 'iperf-vnfd.yml', 'r')
        vnfd3_descriptor = open(path_descriptors + 'tcpdump-vnfd.yml', 'r')

        #import the nsd and vnfds that form the service
        if correctlyFormatted:
            service_request = {'NSD': yaml.load(nsd_descriptor), 'VNFD1': yaml.load(vnfd1_descriptor), 'VNFD2': yaml.load(vnfd2_descriptor), 'VNFD3': yaml.load(vnfd3_descriptor)}
        else:
            service_request = {'VNFD1': yaml.load(vnfd1_descriptor), 'VNFD2': yaml.load(vnfd2_descriptor), 'VNFD3': yaml.load(vnfd3_descriptor)}

        return yaml.dump(service_request)

    #Method that terminates the timer that waits for an event
    def firstEventFinished(self):
        self.wait_for_first_event.set()

    def secondEventFinished(self):
        self.wait_for_second_event.set()

    #Method that starts a timer, waiting for an event
    def waitForFirstEvent(self, timeout=5, msg="Event timed out."):
        if not self.wait_for_first_event.wait(timeout):
            self.assertEqual(True, False, msg=msg)

    def waitForSecondEvent(self, timeout=5, msg="Event timed out."):
        if not self.wait_for_second_event.wait(timeout):
            self.assertEqual(True, False, msg=msg)

    def dummy(self, ch, method, properties, message):
        """
        Sometimes, we need a cbf for a async_call, without actually needing it.
        """

        return

#############################################################
#TEST1: Test Reaction To Correctly Formatted Service Request.
#############################################################
    def on_slm_infra_adaptor_vim_list_test1(self, ch, method, properties, message):
        """
        This method checks what the SLM sends towards the IA when it receives a
        valid request from the gk.
        """
        msg = yaml.load(message)

        #The message should have an empty body and a correlation_id different from the original correlation_id
        self.assertEqual(msg, {}, msg='message is not empty.')
        self.assertNotEqual(properties.correlation_id, self.corr_id, msg='message does not contain a new correlation_id.')
        self.assertEqual(properties.reply_to, 'infrastructure.management.compute.list', msg='not the correct reply_to topic.')

        self.firstEventFinished()

    def on_gk_response_to_correct_service_request(self, ch, method, properties, message):
        """
        This method checks whether the SLM responds to a correctly formatted
        new service request it receives from the GK.
        """

        msg = yaml.load(message)
        self.assertTrue(isinstance(msg, dict), msg='response to service request is not a dictionary.')
        self.assertEqual(msg['status'], 'INSTANTIATING', msg='not correct response, should be INSTANTIATING.')
        self.assertEqual(msg['error'], None, msg='not correct response, should be None.')
        self.assertTrue(isinstance(msg['timestamp'], float), msg='timestamp is not a float')
        self.assertEqual(properties.correlation_id, self.corr_id, msg='response to async call doesnt have the same correlation_id')

        self.secondEventFinished()

    def testReactionToCorrectlyFormattedServiceRequest(self):
        """
        If the gk sends a request on the service.instances.create topic that is
        correctly formatted, then the SLM should respond by doing 2 things:
        1. Replying with the message {'status':'INSTANTIATING',
            'error':NULL, 'timestamp':<timestamp>} with the same correlation_id
            as the one in the request.
        2. Requesting the available vims from the IA on the
            infrastructure.management.compute.list topic with a new correlation
            id and an empty body.
        """

        self.wait_for_first_event.clear()
        self.wait_for_second_event.clear()

        #STEP1: Spy the topic on which the SLM will contact the infrastructure adaptor
        self.manoconn_spy.subscribe(self.on_slm_infra_adaptor_vim_list_test1, 'infrastructure.management.compute.list')

        #STEP2: Send a correctly formatted service request message (from the gk) to the SLM
        self.manoconn_gk.call_async(self.on_gk_response_to_correct_service_request, 'service.instances.create', msg=self.createGkNewServiceRequestMessage(correctlyFormatted=True), content_type='application/yaml', correlation_id=self.corr_id)

        #STEP3: Start waiting for the messages that are triggered by this request
        self.waitForFirstEvent(timeout=10, msg='Wait for message from SLM to IA to request resources timed out.')
        self.waitForSecondEvent(timeout=10, msg='Wait for reply to request from GK timed out.')

###########################################################
#TEST2: Test reaction to wrongly formatted service request.
###########################################################
    def on_gk_response_to_wrong_service_request(self, ch, method, properties, message):
        """
        This method checks whether the SLM responds to a wrongly formatted new
        service request it receives from the GK.
        """

        msg = yaml.load(message)
        self.assertTrue(isinstance(msg, dict), msg='response to service request is not a dictionary.')
        self.assertEqual(msg['status'], 'ERROR', msg='not correct response, should be ERROR')
        self.assertTrue(isinstance(msg['error'], str), msg='Error message is not a string.')
        self.assertTrue(isinstance(msg['timestamp'], float), msg='timestamp is not a float')
        self.assertEqual(properties.correlation_id, self.corr_id, msg='response to async call doesnt have the same correlation_id')

        self.firstEventFinished()

    def testReactionToWronglyFormattedServiceRequest(self):
        """
        If the gk sends a request on the service.instances.create topic that is
        wrongly formatted, then the SLM should respond by
        replying with the message {'status':'ERROR', 'error':<error message>,
        'timestamp':<timestamp>} with the same correlation_id as the one in the
        request.
        """

        self.wait_for_first_event.clear()

        #STEP1: Send a wrongly formatted service request message (from the gk) to the SLM
        self.manoconn_gk.call_async(self.on_gk_response_to_wrong_service_request, 'service.instances.create', msg=self.createGkNewServiceRequestMessage(correctlyFormatted=False), content_type='application/yaml', correlation_id=self.corr_id)

        #STEP2: Start waiting for the messages that are triggered by this request
        self.waitForFirstEvent(timeout=10, msg='Wait for reply to request from GK timed out.')

###############################################################
#TEST3: Test Reaction when SLM receives a valid list of VIMs.
###############################################################
    def on_slm_infra_adaptor_vim_list_test3(self, ch, method, properties, message):
        """
        This method replies to a request of the SLM to the IA to get the
        VIM-list.
        """

        if properties.app_id == 'son-plugin.ServiceLifecycleManager':
            VIM_list = [{'vim_uuid': uuid.uuid4().hex}, {'vim_uuid': uuid.uuid4().hex}, {'vim_uuid': uuid.uuid4().hex}]
            self.manoconn_ia.notify('infrastructure.management.compute.list', yaml.dump(VIM_list), correlation_id=properties.correlation_id)

    def on_slm_infra_adaptor_service_deploy_request_test3(self, ch, method, properties, message):
        """
        This method checks whether the request from the SLM to the IA to deploy
        a service is correctly formatted.
        """

        msg = yaml.load(message)

        self.assertTrue(isinstance(msg, dict), msg="message is not a dictionary.")
        self.assertIn('vim_uuid', msg.keys(), msg="vim_uuid is not a key in the dictionary.")
        self.assertIn('nsd', msg.keys(), msg="nsd is not a key in the dictionary.")
        self.assertIn('vnfds', msg.keys(), msg="vnfds is not a key in the dictionary.")
        self.assertIn('instance_uuid', msg['nsd'].keys(), msg="instance_uuid is not a key in the dictionary.")

        for vnfd in msg['vnfds']:
            self.assertIn('instance_uuid', vnfd.keys(), msg='intance_uuid is not a key in the dictionary.')

        self.firstEventFinished()

    def testReactionToCorrectlyFormattedVimList(self):
        """
        This method tests the response of the SLM when it receives a valid VIM
        list. The SLM should choose a VIM out of the list, and request whether
        it has enough resources to host the service.
        """

        self.wait_for_first_event.clear()
        self.wait_for_second_event.clear()

        #STEP1: Spy the topic on which the SLM will contact the infrastructure adaptor
        self.manoconn_spy.subscribe(self.on_slm_infra_adaptor_vim_list_test3, 'infrastructure.management.compute.list')

        #STEP2: Spy the topic on which the SLM will contact the infrastructure adaptor the first time, to request the resource availability.
        self.manoconn_spy.subscribe(self.on_slm_infra_adaptor_service_deploy_request_test3, 'infrastructure.service.deploy')

        #STEP3: Send a correctly formatted service request message (from the gk) to the SLM
        self.manoconn_gk.call_async(self.dummy, 'service.instances.create', msg=self.createGkNewServiceRequestMessage(correctlyFormatted=True), content_type='application/yaml', correlation_id=self.corr_id)

        #STEP4: Start waiting for the messages that are triggered by this request
        self.waitForFirstEvent(timeout=10, msg='Wait for message from SLM to IA to request resources timed out.')

###############################################################
#TEST4: Test Reaction when SLM receives an empty list of VIMs.
###############################################################
    def on_slm_infra_adaptor_vim_list_test4(self, ch, method, properties, message):
        """
        This method replies to a request of the SLM to the IA to get the
        VIM-list.
        """

        if properties.app_id == 'son-plugin.ServiceLifecycleManager':
            VIM_list = []
            self.manoconn_ia.notify('infrastructure.management.compute.list', yaml.dump(VIM_list), correlation_id=properties.correlation_id)

    def on_slm_response_to_gk_with_empty_vim_list(self, ch, method, properties, message):
        """
        This method checks the content of the message send from SLM to the GK
        to indicate that there are no vims available.
        """
        msg = yaml.load(message)

        #We don't want to trigger on the first response (the async_call), butonly on the second(the notify) and we don't want to trigger on our outgoing message.
        if properties.app_id == 'son-plugin.ServiceLifecycleManager':
            if msg['status'] != 'INSTANTIATING':

                self.assertTrue(isinstance(msg, dict), msg='message is not a dictionary.')
                self.assertEqual(msg['status'], 'ERROR', msg='status is not correct.')
                self.assertEqual(msg['error'], 'No VIM.', msg='error message is not correct.')
                self.assertTrue(isinstance(msg['timestamp'], float), msg='timestamp is not a float.')

                self.firstEventFinished()

    def testReactionToWronglyFormattedVimList(self):
        """
        This method tests the response of the SLM when it receives an empty VIM
        list. The SLM should report back to the gk with an error.
        """

        self.wait_for_first_event.clear()

        #STEP1: Spy the topic on which the SLM will contact the infrastructure adaptor
        self.manoconn_spy.subscribe(self.on_slm_infra_adaptor_vim_list_test4, 'infrastructure.management.compute.list')

        #STEP2: Spy the topic on which the SLM will contact the GK, to indicate that the deployment is stopped due to lack of resources.
        self.manoconn_spy.subscribe(self.on_slm_response_to_gk_with_empty_vim_list, 'service.instances.create')

        #STEP3: Send a correctly formatted service request message (from the gk) to the SLM
        self.manoconn_gk.call_async(self.on_slm_response_to_gk_with_empty_vim_list, 'service.instances.create', msg=self.createGkNewServiceRequestMessage(correctlyFormatted=True), content_type='application/yaml', correlation_id=self.corr_id)

        #STEP4: Start waiting for the messages that are triggered by this request
        self.waitForFirstEvent(timeout=10, msg='Wait for message from SLM to IA to request resources timed out.')


###############################################################################
#TEST7: Test reaction to negative response on deployment message to/from IA
###############################################################################
    def on_slm_infra_adaptor_vim_list_test7(self, ch, method, properties, message):
        """
        This method replies to a request of the SLM to the IA to get the
        VIM-list.
        """

        if properties.app_id == 'son-plugin.ServiceLifecycleManager':
            VIM_list = [{'vim_uuid':uuid.uuid4().hex}]
            self.manoconn_ia.notify('infrastructure.management.compute.list', yaml.dump(VIM_list), correlation_id=properties.correlation_id)

    def on_slm_infra_adaptor_service_deploy_request_test7(self, ch, method, properties, message):
        """
        This method fakes a message from the IA to the SLM that indicates that
        the deployment has failed.
        """

        if properties.app_id == 'son-plugin.ServiceLifecycleManager':
            reply_message = {'request_status':'failed'}
            self.manoconn_ia.notify('infrastructure.service.deploy', yaml.dump(reply_message), correlation_id=properties.correlation_id)

    def on_slm_gk_service_deploy_request_failed(self, ch, method, properties, message):
        """
        This method checks whether the message from the SLM to the GK to
        indicate that the deployment failed is correctly formatted.
        """
        msg = yaml.load(message)

        #We don't want to trigger on the first response (the async_call), but only on the second(the notify) and we don't want to trigger on our outgoing message.
        if properties.app_id == 'son-plugin.ServiceLifecycleManager':
            if msg['status'] != 'INSTANTIATING':

                self.assertTrue(isinstance(msg, dict), msg='message is not a dictionary.')
                self.assertEqual(msg['status'], "ERROR", msg='status is not correct.')
                self.assertEqual(msg['error'], 'Deployment result: failed', msg='error message is not correct.')
                self.assertTrue(isinstance(msg['timestamp'], float), msg='timestamp is not a float.')

                self.firstEventFinished()

    def testReactionToNegativeReplyOnDeploymentFromIA(self):
        """
        When the SLM contacts the IA to request whether enough resources are
        available, it gets a response from the IA.
        If this response indicates that the resources are available, the SLM
        should requestthe deployment of the service to the IA.
        """

        self.wait_for_first_event.clear()

        #STEP1: Spy the topic on which the SLM will contact the infrastructure adaptor
        self.manoconn_spy.subscribe(self.on_slm_infra_adaptor_vim_list_test7, 'infrastructure.management.compute.list')

        #STEP2: Spy the topic on which the SLM will contact the IA the second time, to request the deployment of the service
        self.manoconn_ia.subscribe(self.on_slm_infra_adaptor_service_deploy_request_test7, 'infrastructure.service.deploy')

        #STEP3: Spy the topic on which the SLM will contact the GK to respond that the deployment has failed.
        self.manoconn_gk.subscribe(self.on_slm_gk_service_deploy_request_failed, 'service.instances.create')

        #STEP4: Send a correctly formatted service request message (from the gk) to the SLM
        self.manoconn_gk.call_async(self.dummy, 'service.instances.create', msg=self.createGkNewServiceRequestMessage(correctlyFormatted=True), content_type='application/yaml', correlation_id=self.corr_id)

        #STEP5: Start waiting for the messages that are triggered by this request
        self.waitForFirstEvent(timeout=15, msg='Wait for message from SLM to IA to request deployment timed out.')

###############################################################################
#TEST8: Test Monitoring message creation.
###############################################################################
    def testMonitoringMessageGeneration(self):

        """
        SLM should generate a message for the monitoring
        module in order to start the monitoring process
        to the deployed network service. This message is
        generated from the information existing in NSD,
        VNFDs, NSRs and VNFs. The test checks that, given
        the sonata-demo network service, SLM correctly
        generates the expected message for the monitoring
        module.
        """

        #STEP1: create NSD and VNFD by reading test descriptors.
        gk_request = yaml.load(self.createGkNewServiceRequestMessage())

        #STEP2: add ids to NSD and VNFDs (those used in the expected message)
        gk_request['NSD']['uuid'] = '005606ed-be7d-4ce3-983c-847039e3a5a2'
        gk_request['VNFD1']['uuid'] = '6a15313f-cb0a-4540-baa2-77cc6b3f5b68'
        gk_request['VNFD2']['uuid'] = '645db4fa-a714-4cba-9617-4001477d1281'
        gk_request['VNFD3']['uuid'] = '8a0aa837-ec1c-44e5-9907-898f6401c3ae'

        #STEP3: load nsr_file, containing both NSR and the list of VNFRs
        message_from_ia = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/ia-nsr.yml', 'r'))
        nsr_file = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/sonata-demo-nsr.yml', 'r'))
        vnfrs_file = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/sonata-demo-vnfrs.yml', 'r'))

        #STEP4: call real method
        message = tools.build_monitoring_message(gk_request, message_from_ia, nsr_file, vnfrs_file)

        #STEP5: read expected message from descriptor file
        expected_message = json.load(open('/plugins/son-mano-service-lifecycle-management/test/test_descriptors/monitoring-message.json', 'r'))

        #STEP6: compare that generated message is equals to the expected one
        self.assertEqual(message, expected_message, "messages are not equals")

###############################################################################
#TEST9: Test creation of the message addressed to the Monitoring Repository
###############################################################################

    def testNsrCreation(self):

        """
        Once the Infrastructure Adapter has deployed the network
        service, it would build the entire NSR from the information
        provided by the Infrastructure Adapter. This test checks
        that, given the sonata-demo network service, the IA is able
        to build the correct NSR.
        """

        #STEP1: create NSD and VNFD by reading test descriptors.
        gk_request = yaml.load(self.createGkNewServiceRequestMessage())

        #STEP2: read IA response and the expected NSR
        ia_nsr = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/ia-nsr.yml', 'r'))
        expected_nsr = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/sonata-demo-nsr.yml', 'r'))

        #STEP3: call real method
        message = tools.build_nsr(gk_request, ia_nsr)

        #STEP4: comprare the generated message is equals to the expected one
        self.assertEqual(message, expected_nsr, "Built NSR is not equal to the expected one")

###############################################################################
#TEST10: Test creation of the NSR
###############################################################################

    def testVnfrsCreation(self):
        #STEP1: create NSD and VNFD by reading test descriptors.
        gk_request = yaml.load(self.createGkNewServiceRequestMessage())

        #STEP2: read IA response and the expected NSR
        ia_nsr = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/ia-nsr.yml', 'r'))
        expected_vnfrs = yaml.load(open('/plugins/son-mano-service-lifecycle-management/test/test_records/sonata-demo-vnfrs.yml', 'r'))

        message = tools.build_vnfrs(gk_request, ia_nsr['vnfrs'])

        self.assertEqual(message, expected_vnfrs, "Built VNFRs are not equals to the expected ones")


###############################################################################
#TEST11: Test creation of the NSR
###############################################################################

if __name__ == '__main__':
    unittest.main()
